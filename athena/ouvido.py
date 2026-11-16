"""O ouvido da ATHENA: microfone, palavra de ativação ("Atena") e transcrição da fala.

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
            from faster_whisper import WhisperModel
            tamanho = self.config.get("ouvido.modelo_whisper", "small")
            disp = self.config.get("ouvido.dispositivo", "cpu")
            self.log(f"[ouvido] carregando Whisper '{tamanho}' (a primeira vez baixa o modelo)...")
            self._whisper = WhisperModel(tamanho, device=disp, compute_type="int8" if disp == "cpu" else "float16")
            self.log("[ouvido] Whisper pronto")
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

    # ------------------------------------------------------------------ utilidades
    @staticmethod
    def _rms(bloco: bytes) -> float:
        a = np.frombuffer(bloco, dtype=np.int16).astype(np.float32)
        return float(np.sqrt(np.mean(a * a))) if a.size else 0.0

    @property
    def _limiar(self) -> float:
        return max(self._ruido * float(self.config.get("ouvido.sensibilidade", 2.5)), 250.0)

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
        """Bloqueia até ouvir 'Atena' (ou `cancelar` ser ligado). Retorna (ativou, comando_junto)."""
        if self._vosk is not None:
            return self._esperar_com_vosk(cancelar)
        return self._esperar_com_whisper(cancelar)

    def _esperar_com_vosk(self, cancelar: threading.Event) -> tuple[bool, str]:
        pre = collections.deque(maxlen=int(BLOCOS_POR_SEG * 0.5))  # meio segundo antes da fala
        fala: list[bytes] = []
        while not cancelar.is_set():
            try:
                bloco = self._fila.get(timeout=0.2)
            except queue.Empty:
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
                if not any(normalizar(a) in texto.split()
                           for a in self.config.get("ativacao.palavras", ["atena"])):
                    continue
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
            try:
                b = self._fila.get(timeout=0.3)
            except queue.Empty:
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
        silencio_fim = float(self.config.get("ouvido.silencio_fim", 1.0))
        pre = collections.deque(maxlen=int(BLOCOS_POR_SEG * 0.4))
        fala: list[bytes] = []
        quietos = 0
        inicio = time.time()
        while True:
            if cancelar is not None and cancelar.is_set():
                return None
            try:
                bloco = self._fila.get(timeout=0.2)
            except queue.Empty:
                bloco = None
            if bloco is None:
                if not fala and espera_max is not None and time.time() - inicio > espera_max:
                    return None
                continue
            rms = self._rms(bloco)
            self._atualiza_nivel(rms)
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
    def transcrever(self, audio: bytes) -> str:
        self._whisper_pronto.wait(timeout=120)
        if self._whisper is None or not audio:
            return ""
        amostras = np.frombuffer(audio, dtype=np.int16).astype(np.float32) / 32768.0
        nome = self.config.nome_ia.capitalize()
        segmentos, _ = self._whisper.transcribe(
            amostras, language="pt", beam_size=3, vad_filter=False,
            condition_on_previous_text=False,
            initial_prompt=f"{nome}, abre o Spotify. {nome}, pesquisa no Google.",
        )
        texto = " ".join(s.text.strip() for s in segmentos).strip()
        # Whisper às vezes "alucina" em silêncio
        if "amara org" in normalizar(texto) or "inscreva se no canal" in normalizar(texto):
            return ""
        return texto
