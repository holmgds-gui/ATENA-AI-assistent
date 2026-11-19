"""O ouvido da ATENA: microfone, palavra de ativação ("Atena") e transcrição da fala.

Como funciona:
1. O microfone fica sempre aberto, mas só o Vosk (leve, offline) escuta, procurando a palavra "atena".
2. Quando o Vosk acha algo parecido, o Whisper (mais preciso) confere e transcreve a frase inteira.
   Assim dá pra falar tudo de uma vez: "Atena, abre o Spotify".
3. Se você falar só "Atena", ela responde e escuta o próximo comando.
"""
from __future__ import annotations

import collections
import difflib
import json
import queue
import threading
import time

import numpy as np

from .palmas import DetectorPalmas
from .sistema import normalizar

TAXA = 16000           # Hz — o que Vosk e Whisper esperam
BLOCO = 480            # 30 ms por bloco
BLOCOS_POR_SEG = TAXA // BLOCO


class Ouvido:
    def __init__(self, config, log=print):
        self.config = config
        self.log = log
        self._fila: queue.Queue = queue.Queue()
        self._stream = None
        self._surdo = threading.Event()        # ligado enquanto ela fala (não ouve a própria voz)
        self._ruido = 200.0                     # nível do ruído ambiente (atualiza sozinho)
        self._vosk = None
        self._whisper = None
        self._whisper_pronto = threading.Event()
        self.nivel = 0.0                        # 0..1 — usado pelo orbe pra pulsar com a sua voz
        self.bandas = None                      # equalizador da sua voz (enquanto ela ouve)
        self.ultima_ativacao = ""               # "voz" ou "palmas"
        self._palmas = DetectorPalmas()
        self._esperando = False                 # só procura palmas enquanto espera ativação
        self._bateu_palmas = False

    # ------------------------------------------------------------------ inicialização
    def iniciar(self) -> None:
        import sounddevice as sd
        mic = self.config.get("ouvido.microfone")
        self._stream = sd.InputStream(samplerate=TAXA, channels=1, dtype="int16", blocksize=BLOCO,
                                      device=mic, callback=self._callback)
        self._stream.start()
        self._carregar_vosk()
        threading.Thread(target=self._carregar_whisper, daemon=True).start()
        self._calibrar()

    def _callback(self, dados, frames, tempo, status):
        if self._surdo.is_set():
            return
        self._fila.put(bytes(dados))

    def _carregar_vosk(self) -> None:
        pasta = self.config.caminho(self.config.get("ativacao.modelo_vosk", "modelos/vosk-pt"))
        if not pasta.exists():
            self.log(f"[ouvido] modelo Vosk não encontrado em {pasta}. Vou usar só o Whisper (gasta mais CPU).")
            return
        try:
            import vosk
            vosk.SetLogLevel(-1)
            modelo = vosk.Model(str(pasta))
            palavras = [normalizar(p) for p in self.config.get("ativacao.palavras", ["atena"])]
            extras = ["antena", "a tela", "atenas"]  # palavras parecidas ajudam o Vosk a não confundir
            gramatica = json.dumps(sorted(set(palavras + extras)) + ["[unk]"], ensure_ascii=False)
            self._vosk = vosk.KaldiRecognizer(modelo, TAXA, gramatica)
            self.log("[ouvido] Vosk pronto (detector de 'Atena')")
        except Exception as e:
            self.log(f"[ouvido] erro ao carregar Vosk: {e}")
            self._vosk = None

    def _carregar_whisper(self) -> None:
        try:
            import os
            from faster_whisper import WhisperModel
            tamanho = self.config.get("ouvido.modelo_whisper", "small")
            disp = self.config.get("ouvido.dispositivo", "cpu")
            local = self.config.caminho(f"modelos/whisper-{tamanho}")  # vem dentro do instalador
            origem = str(local) if local.exists() else tamanho
            inicio = time.time()
            self.log(f"[ouvido] carregando Whisper '{tamanho}' ({'embutido' if local.exists() else 'baixando na 1ª vez'})")
            self._whisper = WhisperModel(origem, device=disp, compute_type="int8" if disp == "cpu" else "float16",
                                         cpu_threads=max(2, min(8, (os.cpu_count() or 4) // 2)))
            # aquece: a 1ª transcrição é sempre mais lenta, então faz uma "de mentira" agora
            list(self._whisper.transcribe(np.zeros(TAXA // 2, dtype=np.float32), language="pt", beam_size=1)[0])
            self.log(f"[ouvido] Whisper pronto em {time.time() - inicio:.1f}s")
        except Exception as e:
            self.log(f"[ouvido] erro ao carregar Whisper: {e}")
        finally:
            self._whisper_pronto.set()

    def _calibrar(self, segundos: float = 1.0) -> None:
        niveis = []
        fim = time.time() + segundos
        while time.time() < fim:
            try:
                niveis.append(self._rms(self._fila.get(timeout=0.5)))
            except queue.Empty:
                break
        if niveis:
            self._ruido = max(80.0, float(np.percentile(niveis, 50)))
        self.log(f"[ouvido] ruído ambiente: {self._ruido:.0f}")

    def parar(self) -> None:
        if self._stream:
            self._stream.stop()
            self._stream.close()

    # ------------------------------------------------------------------ leitura
    def _ler(self, timeout: float = 0.2) -> bytes | None:
        """Pega o próximo bloco do microfone e, se estiver esperando ativação, procura palmas."""
        try:
            bloco = self._fila.get(timeout=timeout)
        except queue.Empty:
            return None
        if self._esperando and self.config.get("ativacao.palmas", True):
            self._palmas.quantidade = int(self.config.get("ativacao.num_palmas", 2))
            self._palmas.sensibilidade = float(self.config.get("ativacao.exigencia_palmas", 1.0))
            if self._palmas.alimentar(bloco):
                self._bateu_palmas = True
        return bloco

    def _checar_palmas(self) -> bool:
        if self._bateu_palmas:
            self._bateu_palmas = False
            self.ultima_ativacao = "palmas"
            self._palmas.reiniciar()
            if self._vosk:
                self._vosk.Reset()
            return True
        return False

    # ------------------------------------------------------------------ utilidades
    @staticmethod
    def _rms(bloco: bytes) -> float:
        a = np.frombuffer(bloco, dtype=np.int16).astype(np.float32)
        return float(np.sqrt(np.mean(a * a))) if a.size else 0.0

    @property
    def _limiar(self) -> float:
        return max(self._ruido * float(self.config.get("ouvido.sensibilidade", 2.5)), 250.0)

    def bandas_microfone(self, bloco: bytes):
        """48 bandas do último pedaço do microfone (pra esfera reagir à SUA voz enquanto ouve)."""
        a = np.frombuffer(bloco, dtype=np.int16).astype(np.float32) / 32768.0
        esp = np.abs(np.fft.rfft(a * np.hanning(len(a)), n=1024))
        freqs = np.fft.rfftfreq(1024, 1 / TAXA)
        lim = np.geomspace(90, 7900, 49)
        b = np.array([esp[(freqs >= lim[k]) & (freqs < lim[k + 1])].mean() if ((freqs >= lim[k]) & (freqs < lim[k + 1])).any()
                      else 0.0 for k in range(48)], dtype=np.float32)
        return np.clip(np.log1p(b * 6) / 2.2, 0, 1)

    def _atualiza_nivel(self, rms: float) -> None:
        self.nivel = min(1.0, rms / (self._limiar * 4))
        if rms < self._limiar:  # ajusta devagar o ruído ambiente quando ninguém está falando
            self._ruido = 0.98 * self._ruido + 0.02 * max(rms, 50.0)

    def surdo(self, ligado: bool) -> None:
        """Liga/desliga o microfone lógico (pra ela não ouvir a própria voz)."""
        if ligado:
            self._surdo.set()
        else:
            time.sleep(0.25)  # rabicho do som do alto-falante
            self.limpar()
            self._surdo.clear()
            if self._vosk:
                self._vosk.Reset()

    def limpar(self) -> None:
        while not self._fila.empty():
            try:
                self._fila.get_nowait()
            except queue.Empty:
                break

    # ------------------------------------------------------------------ ativação
    def contem_palavra(self, texto: str) -> tuple[bool, str]:
        """Procura 'atena' no texto (tolera erros) e devolve (achou, resto_da_frase)."""
        palavras = normalizar(texto).split()
        alvos = [normalizar(p) for p in self.config.get("ativacao.palavras", ["atena"])]
        for i, p in enumerate(palavras[:4]):  # tem que estar no começo da frase
            if any(p == a or difflib.SequenceMatcher(None, p, a).ratio() >= 0.8 for a in alvos):
                resto = " ".join(texto.split()[i + 1:]).strip(" ,.!?")
                return True, resto
        return False, ""

    def esperar_ativacao(self, cancelar: threading.Event) -> tuple[bool, str]:
        """Bloqueia até ouvir 'Atena' ou palmas (ou `cancelar` ser ligado). Retorna (ativou, comando_junto).
        Depois, `ultima_ativacao` diz se foi "voz" ou "palmas"."""
        self.ultima_ativacao = ""
        self._bateu_palmas = False
        self._palmas.reiniciar()
        self._esperando = True
        try:
            if self._vosk is not None:
                ativou, comando = self._esperar_com_vosk(cancelar)
            else:
                ativou, comando = self._esperar_com_whisper(cancelar)
        finally:
            self._esperando = False
        if ativou and not self.ultima_ativacao:
            self.ultima_ativacao = "voz"
        return ativou, comando

    def _esperar_com_vosk(self, cancelar: threading.Event) -> tuple[bool, str]:
        pre = collections.deque(maxlen=int(BLOCOS_POR_SEG * 0.5))  # meio segundo antes da fala
        fala: list[bytes] = []
        while not cancelar.is_set():
            bloco = self._ler()
            if self._checar_palmas():
                return True, ""
            if bloco is None:
                continue
            rms = self._rms(bloco)
            self._atualiza_nivel(rms)
            if fala or rms > self._limiar:
                if not fala:
                    fala.extend(pre)
                fala.append(bloco)
            else:
                pre.append(bloco)
            if len(fala) > BLOCOS_POR_SEG * 12:  # fala longa demais sem 'atena': descarta
                fala.clear()
            if self._vosk.AcceptWaveform(bloco):
                texto = json.loads(self._vosk.Result()).get("text", "")
                audio, fala = fala, []
                palavras = texto.split()
                alvos = [normalizar(a) for a in self.config.get("ativacao.palavras", ["atena"])]
                if not any(a in palavras for a in alvos):
                    continue
                # Só "Atena" (nada depois): responde NA HORA, sem esperar o Whisper conferir
                pos = max(i for i, p in enumerate(palavras) if p in alvos)
                if not palavras[pos + 1:] and len(palavras) <= 2:
                    return True, ""
                # Vosk achou. Confere com o Whisper e pega o comando que veio junto.
                audio += self._continuar_gravando(0.4)
                frase = self.transcrever(b"".join(audio))
                if not frase:  # whisper indisponível: confia no Vosk
                    return True, ""
                achou, resto = self.contem_palavra(frase)
                if achou:
                    return True, resto
                self.log(f"[ouvido] alarme falso ignorado: '{frase}'")
        return False, ""

    def _esperar_com_whisper(self, cancelar: threading.Event) -> tuple[bool, str]:
        while not cancelar.is_set():
            audio = self.gravar_fala(espera_max=None, cancelar=cancelar, max_seg=6)
            if self._checar_palmas():
                return True, ""
            if audio is None:
                continue
            frase = self.transcrever(audio)
            achou, resto = self.contem_palavra(frase)
            if achou:
                return True, resto
        return False, ""

    def _continuar_gravando(self, silencio: float) -> list[bytes]:
        """Depois do Vosk, grava mais um pouco caso você ainda esteja falando."""
        blocos, quietos = [], 0
        limite = int(silencio * BLOCOS_POR_SEG)
        inicio = time.time()
        while time.time() - inicio < 10:
            b = self._ler(0.3)
            if b is None:
                break
            blocos.append(b)
            rms = self._rms(b)
            self._atualiza_nivel(rms)
            quietos = quietos + 1 if rms < self._limiar else 0
            if quietos >= limite:
                break
        return blocos

    # ------------------------------------------------------------------ gravação de comando
    def gravar_fala(self, espera_max: float | None = 6.0, cancelar: threading.Event | None = None,
                    max_seg: float | None = None) -> bytes | None:
        """Espera você começar a falar e grava até um silêncio. None se ninguém falou."""
        max_seg = max_seg or float(self.config.get("ouvido.max_fala", 15))
        silencio_fim = float(self.config.get("ouvido.silencio_fim", 1.2))
        pre = collections.deque(maxlen=int(BLOCOS_POR_SEG * 0.4))
        fala: list[bytes] = []
        quietos = 0
        inicio = time.time()
        while True:
            if cancelar is not None and cancelar.is_set():
                return None
            bloco = self._ler()
            if self._esperando and self._bateu_palmas:
                return None
            if bloco is None:
                if not fala and espera_max is not None and time.time() - inicio > espera_max:
                    return None
                continue
            rms = self._rms(bloco)
            self._atualiza_nivel(rms)
            self.bandas = self.bandas_microfone(bloco) if self.nivel > 0.02 else None
            alto = rms > self._limiar
            if not fala:
                if alto:
                    fala.extend(pre)
                    fala.append(bloco)
                else:
                    pre.append(bloco)
                    if espera_max is not None and time.time() - inicio > espera_max:
                        return None
                continue
            fala.append(bloco)
            quietos = 0 if alto else quietos + 1
            if quietos >= silencio_fim * BLOCOS_POR_SEG or len(fala) >= max_seg * BLOCOS_POR_SEG:
                break
        self.nivel = 0.0
        if len(fala) < BLOCOS_POR_SEG * 0.3:  # barulho curto demais (tosse, clique)
            return None
        return b"".join(fala)

    # ------------------------------------------------------------------ transcrição
    # apps que muita gente tem: se estiverem no PC, entram no "vocabulário" do reconhecimento
    _APPS_COMUNS = ("Spotify", "WhatsApp", "Claude", "Chrome", "Google", "YouTube", "Discord", "Steam",
                    "Instagram", "TikTok", "Netflix", "Gmail", "Word", "Excel", "PowerPoint", "Edge",
                    "Bloco de Notas", "Calculadora", "Explorador de Arquivos", "Telegram", "Roblox",
                    "Valorant", "Epic Games", "Gemini", "ChatGPT", "VS Code", "Notion", "Canva", "Outlook")

    def _vocabulario(self, nome: str) -> str:
        """Frase de exemplo que 'ensina' ao Whisper os nomes certos (Claude, não 'cloud')."""
        if getattr(self, "_vocab_cache", None) and time.time() - self._vocab_cache[0] < 600:
            return self._vocab_cache[1]
        nomes = []
        try:
            from . import sistema
            instalados = {normalizar(a.nome) for a in sistema.INDICE.apps} if sistema.INDICE.carregado else set()
            for n in self._APPS_COMUNS:
                k = normalizar(n)
                if not instalados or any(k == i or i.startswith(k + " ") for i in instalados):
                    nomes.append(n)
            for apelido in (self.config.apelidos_apps or {}):
                nomes.append(str(apelido))
        except Exception:
            nomes = list(self._APPS_COMUNS)
        nomes = list(dict.fromkeys(nomes))[:28]
        texto = (f"{nome}, abre o Spotify. {nome}, toca uma música. {nome}, pesquisa no Google. "
                 f"Apps: {', '.join(nomes)}.")
        self._vocab_cache = (time.time(), texto)
        return texto

    def transcrever(self, audio: bytes) -> str:
        self._whisper_pronto.wait(timeout=120)
        if self._whisper is None or not audio:
            return ""
        amostras = np.frombuffer(audio, dtype=np.int16).astype(np.float32) / 32768.0
        nome = self.config.nome_ia.capitalize()
        inicio = time.time()
        segmentos, _ = self._whisper.transcribe(
            amostras, language="pt", beam_size=int(self.config.get("ouvido.precisao", 1)), vad_filter=False,
            condition_on_previous_text=False, without_timestamps=True,
            initial_prompt=self._vocabulario(nome),
        )
        texto = " ".join(s.text.strip() for s in segmentos).strip()
        self.log(f"[tempo] transcrição {len(amostras) / TAXA:.1f}s de áudio em {time.time() - inicio:.2f}s: {texto!r}")
        # Whisper às vezes "alucina" em silêncio
        if "amara org" in normalizar(texto) or "inscreva se no canal" in normalizar(texto):
            return ""
        return texto
