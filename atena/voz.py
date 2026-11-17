"""A voz da ATENA (texto -> fala).

- edge: vozes neurais grátis da Microsoft (Francisca, Thalita, Antonio). Precisa de internet.
- offline: voz do próprio Windows (pyttsx3). Mais robótica, mas funciona sem internet.
"""
from __future__ import annotations

import asyncio
import math
import os
import queue
import re
import tempfile
import threading
import time

VOZES_EDGE = {
    "pt-BR-FranciscaNeural": "Francisca (feminina, clara)",
    "pt-BR-ThalitaMultilingualNeural": "Thalita (feminina, jovem)",
    "pt-BR-ThalitaNeural": "Thalita (feminina)",
    "pt-BR-AntonioNeural": "Antonio (masculina)",
    "pt-PT-RaquelNeural": "Raquel (portuguesa de Portugal)",
}


N_BANDAS = 48
QUADRO = 1 / 60  # análise a 60 quadros por segundo


def analisar_audio(amostras, taxa: int) -> tuple:
    """Pré-calcula, pra cada 1/60 s da fala, o volume e 48 bandas de frequência (o equalizador)."""
    import numpy as np
    x = np.asarray(amostras, dtype=np.float32)
    if x.ndim == 2:
        x = x.mean(axis=1)
    x /= 32768.0
    passo = max(1, int(taxa * QUADRO))
    janela = 1024
    n = max(1, len(x) // passo)
    pad = np.pad(x, (0, janela))
    idx = np.arange(n)[:, None] * passo + np.arange(janela)[None, :]
    quadros = pad[idx] * np.hanning(janela)
    rms = np.sqrt(np.mean((pad[np.arange(n)[:, None] * passo + np.arange(passo)[None, :]]) ** 2, axis=1))
    espectro = np.abs(np.fft.rfft(quadros, axis=1))
    freqs = np.fft.rfftfreq(janela, 1 / taxa)
    limites = np.geomspace(90, min(9000, taxa / 2 - 1), N_BANDAS + 1)
    bandas = np.zeros((n, N_BANDAS), dtype=np.float32)
    for b in range(N_BANDAS):
        m = (freqs >= limites[b]) & (freqs < limites[b + 1])
        if m.any():
            bandas[:, b] = espectro[:, m].mean(axis=1)
    bandas = np.log1p(bandas * 8)
    bandas /= max(1e-6, np.percentile(bandas, 98))
    nivel = rms / max(1e-6, np.percentile(rms, 97))
    return np.clip(nivel, 0, 1).astype(np.float32), np.clip(bandas, 0, 1)


def dividir_frases(texto: str) -> list[str]:
    partes = re.split(r"(?<=[.!?…])\s+", texto.strip())
    return [p for p in partes if p.strip()]


class Voz:
    def __init__(self, config):
        self.config = config
        self._parar = threading.Event()
        self.falando = False
        self._mixer_ok = False
        self._offline = None
        self._trava = threading.Lock()
        self._analise = None  # (inicio, nivel[], bandas[][]) da frase tocando agora

    # --------------------------------------------------------------
    def _iniciar_mixer(self) -> None:
        if self._mixer_ok:
            return
        os.environ.setdefault("PYGAME_HIDE_SUPPORT_PROMPT", "1")
        import pygame
        pygame.mixer.init()
        self._mixer_ok = True

    def _gerar_edge(self, texto: str, caminho: str) -> None:
        import edge_tts

        async def _rodar():
            com = edge_tts.Communicate(
                texto,
                voice=self.config.get("voz.voz", "pt-BR-FranciscaNeural"),
                rate=self.config.get("voz.velocidade", "+0%"),
                pitch=self.config.get("voz.tom", "+0Hz"),
            )
            await com.save(caminho)

        asyncio.run(_rodar())

    def _tocar_arquivo(self, caminho: str) -> None:
        import pygame
        self._iniciar_mixer()
        try:  # Sound deixa ler as amostras: a esfera mexe junto com cada sílaba
            som = pygame.mixer.Sound(caminho)
            taxa = pygame.mixer.get_init()[0]
            try:
                nivel, bandas = analisar_audio(pygame.sndarray.array(som), taxa)
            except Exception:
                nivel, bandas = None, None
            canal = som.play()
            self._analise = (time.time(), nivel, bandas) if nivel is not None else None
            while canal is not None and canal.get_busy():
                if self._parar.is_set():
                    canal.stop()
                    break
                time.sleep(0.02)
        except pygame.error:  # formato que o Sound não lê: toca do jeito simples
            pygame.mixer.music.load(caminho)
            pygame.mixer.music.play()
            while pygame.mixer.music.get_busy():
                if self._parar.is_set():
                    pygame.mixer.music.stop()
                    break
                time.sleep(0.03)
            pygame.mixer.music.unload()
        finally:
            self._analise = None

    def bip(self) -> None:
        """Som curto de 'estou ouvindo' (gerado na hora, sem arquivo e sem internet)."""
        try:
            import numpy as np
            import pygame
            self._iniciar_mixer()
            if getattr(self, "_som_bip", None) is None:
                taxa, canais = pygame.mixer.get_init()[0], pygame.mixer.get_init()[2]
                t = np.arange(int(taxa * 0.16)) / taxa
                freq = np.where(t < 0.07, 880.0, 1320.0)
                onda = np.sin(2 * np.pi * freq * t) * np.minimum(1, t / 0.005) * np.exp(-t * 14) * 0.35
                pcm = (onda * 32767).astype(np.int16)
                if canais == 2:
                    pcm = np.stack([pcm, pcm], 1)
                self._som_bip = pygame.sndarray.make_sound(np.ascontiguousarray(pcm))
            self._som_bip.play()
        except Exception as e:
            print(f"[voz] bip falhou: {e}")

    def analise_agora(self):
        """(volume 0..1, 48 bandas 0..1) do pedaço da fala que está tocando agora, ou (0, None)."""
        a = self._analise
        if not a:
            return 0.0, None
        inicio, nivel, bandas = a
        i = int((time.time() - inicio) / QUADRO)
        if i < 0 or i >= len(nivel):
            return 0.0, None
        return float(nivel[i]), bandas[i]

    def _falar_offline(self, texto: str) -> None:
        import pyttsx3
        if self._offline is None:
            self._offline = pyttsx3.init()
            for v in self._offline.getProperty("voices"):
                if "pt" in (v.id or "").lower() or "brazil" in (v.name or "").lower():
                    self._offline.setProperty("voice", v.id)
                    break
        self._offline.say(texto)
        self._offline.runAndWait()

    # --------------------------------------------------------------
    def falar(self, texto: str, ao_comecar=None) -> None:
        """Fala o texto (bloqueia até terminar ou até alguém chamar parar())."""
        if not texto:
            return
        with self._trava:
            self._parar.clear()
            self.falando = True
            try:
                if self.config.get("voz.motor", "edge") == "edge":
                    try:
                        self._falar_edge(texto, ao_comecar)
                        return
                    except Exception as e:
                        print(f"[voz] edge-tts falhou ({e}); usando voz offline")
                if ao_comecar:
                    ao_comecar()
                self._falar_offline(texto)
            finally:
                self.falando = False

    def _falar_edge(self, texto: str, ao_comecar) -> None:
        fila: "queue.Queue[str | None]" = queue.Queue()
        for frase in (dividir_frases(texto) or [texto]):
            fila.put(frase)
        fila.put(None)
        self._falar_edge_fila(fila, ao_comecar)

    def _falar_edge_fila(self, fila, ao_comecar) -> None:
        """Gera e toca frase por frase, na ordem em que chegam na fila (None = acabou).
        A frase seguinte é gerada enquanto a anterior toca."""
        pasta = tempfile.mkdtemp(prefix="atena_")
        prontos: "queue.Queue[tuple[str | None, Exception | None]]" = queue.Queue()
        self._consumidas = []

        def gerar_todas():
            i = 0
            while True:
                frase = fila.get()
                if frase is None or self._parar.is_set():
                    prontos.put((None, None))
                    return
                frase = frase.strip()
                if not frase:
                    continue
                self._consumidas.append(frase)
                caminho = os.path.join(pasta, f"{i}.mp3")
                i += 1
                try:
                    self._gerar_edge(frase, caminho)
                    prontos.put((caminho, None))
                except Exception as e:
                    prontos.put((None, e))
                    return

        threading.Thread(target=gerar_todas, daemon=True).start()
        comecou = False
        tocados = []
        while True:
            try:
                arq, erro = prontos.get(timeout=60)
            except queue.Empty:
                break
            if erro is not None:
                if not comecou:
                    raise erro
                break
            if arq is None or self._parar.is_set():
                break
            if not comecou and ao_comecar:
                ao_comecar()
            comecou = True
            self._tocar_arquivo(arq)
            tocados.append(arq)
        for arq in tocados:
            try:
                os.remove(arq)
            except OSError:
                pass

    def falar_fila(self, fila, ao_comecar=None) -> None:
        """Fala frases que vão chegando (resposta da IA em tempo real). Bloqueia até a fila acabar."""
        with self._trava:
            self._parar.clear()
            self.falando = True
            try:
                if self.config.get("voz.motor", "edge") == "edge":
                    try:
                        self._falar_edge_fila(fila, ao_comecar)
                        return
                    except Exception as e:
                        print(f"[voz] edge-tts falhou ({e}); usando voz offline")
                # offline: junta o resto e fala de uma vez
                partes = list(getattr(self, "_consumidas", []))
                while True:
                    f = fila.get()
                    if f is None:
                        break
                    partes.append(f)
                if partes:
                    if ao_comecar:
                        ao_comecar()
                    self._falar_offline(" ".join(partes))
            finally:
                self.falando = False

    def parar(self) -> None:
        self._parar.set()


async def listar_vozes_pt() -> list[str]:
    import edge_tts
    vozes = await edge_tts.list_voices()
    return sorted(v["ShortName"] for v in vozes if v["Locale"].startswith("pt-"))
