"""A voz da ATENA (texto -> fala).

- edge: vozes neurais grátis da Microsoft (Francisca, Thalita, Antonio). Precisa de internet.
- offline: voz do próprio Windows (pyttsx3). Mais robótica, mas funciona sem internet.
"""
from __future__ import annotations

import asyncio
import os
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
        pygame.mixer.music.load(caminho)
        pygame.mixer.music.play()
        while pygame.mixer.music.get_busy():
            if self._parar.is_set():
                pygame.mixer.music.stop()
                break
            time.sleep(0.03)
        pygame.mixer.music.unload()

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
        # Gera frase por frase: a primeira começa a tocar enquanto as outras são geradas.
        frases = dividir_frases(texto) or [texto]
        pasta = tempfile.mkdtemp(prefix="atena_")
        arquivos: list[str | None] = [None] * len(frases)
        erros: list[Exception] = []
        prontos = [threading.Event() for _ in frases]

        def gerar_todas():
            for i, frase in enumerate(frases):
                if self._parar.is_set():
                    break
                caminho = os.path.join(pasta, f"{i}.mp3")
                try:
                    self._gerar_edge(frase, caminho)
                    arquivos[i] = caminho
                except Exception as e:
                    erros.append(e)
                prontos[i].set()
                if erros:
                    for ev in prontos:
                        ev.set()
                    break

        threading.Thread(target=gerar_todas, daemon=True).start()
        comecou = False
        for i in range(len(frases)):
            prontos[i].wait(timeout=20)
            if self._parar.is_set():
                break
            if arquivos[i] is None:
                if erros and not comecou:
                    raise erros[0]
                break
            if not comecou and ao_comecar:
                ao_comecar()
            comecou = True
            self._tocar_arquivo(arquivos[i])
        for arq in arquivos:
            if arq:
                try:
                    os.remove(arq)
                except OSError:
                    pass

    def parar(self) -> None:
        self._parar.set()


async def listar_vozes_pt() -> list[str]:
    import edge_tts
    vozes = await edge_tts.list_voices()
    return sorted(v["ShortName"] for v in vozes if v["Locale"].startswith("pt-"))
