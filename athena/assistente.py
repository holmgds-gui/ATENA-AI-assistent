"""O 'maestro' da ATHENA: junta ouvido, cérebro, voz e ferramentas num ciclo só.

Não depende da interface: avisa o que está acontecendo pela função `evento(tipo, dados)`.
Tipos de evento: estado ('dormindo'|'ouvindo'|'pensando'|'falando'|'mudo'|'erro'),
                 voce (o que você falou), athena (o que ela respondeu), log, acao.
"""
from __future__ import annotations

import datetime as dt
import queue
import random
import re
import threading
import traceback

from . import atalhos
from .cerebro import ErroCerebro, criar_cerebro
from .ferramentas import Contexto
from .sistema import normalizar
from .voz import Voz

SIM = r"\b(sim|pode|confirmo|confirma|claro|manda|isso|positivo|faz|faca|vai|bora|com certeza|ok|beleza)\b"
NAO = r"\b(nao|cancela|cancelar|negativo|para|deixa|esquece)\b"
CANCELAR = r"^(nada|cancela|cancelar|deixa|deixa pra la|esquece|esquece isso|nao e nada|nao era nada)$"


class Assistente:
    def __init__(self, config, evento=None, usar_microfone: bool = True):
        self.config = config
        self.evento = evento or (lambda tipo, dados=None: None)
        self.usar_microfone = usar_microfone
        self.cerebro = criar_cerebro(config)
        self.voz = Voz(config)
        self.ouvido = None
        self.ctx = Contexto(config=config, falar=self.falar_async)
        self._rodando = threading.Event()
        self._interromper = threading.Event()
        self._chamado_manual = False
        self._textos: queue.Queue[str] = queue.Queue()
        self._origem_texto = False
        self.mudo = False
        self.estado = "dormindo"

    # ================================================================== básico
    def _log(self, msg: str) -> None:
        print(msg)
        self.evento("log", msg)

    def _estado(self, e: str) -> None:
        self.estado = e
        self.evento("estado", e)

    def iniciar(self) -> None:
        self._rodando.set()
        threading.Thread(target=self._preparar_e_rodar, daemon=True, name="athena").start()

    def encerrar(self) -> None:
        self._rodando.clear()
        self._interromper.set()
        self.voz.parar()
        if self.ouvido:
            self.ouvido.parar()

    # ================================================================== entradas externas
    def chamar(self) -> None:
        """Ativação manual (atalho de teclado ou clique no orbe). Se estiver falando, cala."""
        if self.voz.falando:
            self.voz.parar()
            return
        self._chamado_manual = True
        self._interromper.set()

    def enviar_texto(self, texto: str) -> None:
        """Manda um comando escrito (pelo painel ou terminal)."""
        if texto.strip():
            self._textos.put(texto.strip())
            self._interromper.set()

    def alternar_mudo(self) -> bool:
        self.mudo = not self.mudo
        if self.ouvido:
            self.ouvido.surdo(self.mudo)
        self._estado("mudo" if self.mudo else "dormindo")
        return self.mudo

    def recarregar_config(self) -> None:
        self.config.recarregar()
        self._log("[config] configurações recarregadas")

    # ================================================================== voz
    def falar(self, texto: str) -> None:
        if not texto:
            return
        self.evento("athena", texto)
        if self.ouvido:
            self.ouvido.surdo(True)
        try:
            self.voz.falar(texto, ao_comecar=lambda: self._estado("falando"))
        except Exception as e:
            self._log(f"[voz] erro: {e}")
        finally:
            if self.ouvido and not self.mudo:
                self.ouvido.surdo(False)

    def falar_async(self, texto: str) -> None:
        """Usado por timers: fala sem travar o ciclo principal."""
        threading.Thread(target=self.falar, args=(texto,), daemon=True).start()

    def _saudacao(self) -> str:
        h = dt.datetime.now().hour
        periodo = "Bom dia" if 5 <= h < 12 else "Boa tarde" if 12 <= h < 18 else "Boa noite"
        return f"{self.config.nome_ia} online. {periodo}, {self.config.nome_usuario}."

    # ================================================================== ciclo principal
    def _preparar_e_rodar(self) -> None:
        if self.usar_microfone:
            try:
                from .ouvido import Ouvido
                self.ouvido = Ouvido(self.config, log=self._log)
                self.ouvido.iniciar()
            except Exception as e:
                self.ouvido = None
                self._log(f"[ouvido] microfone indisponível ({e}). Use o atalho ou escreva no painel.")

        threading.Thread(target=self._carregar_extras, daemon=True).start()
        self.falar(self._saudacao())
        if not self.cerebro.esta_online():
            self.falar("Aviso: não estou encontrando o Ollama. Os comandos rápidos funcionam, "
                       "mas pra conversar comigo abra o Ollama.")
        self._estado("mudo" if self.mudo else "dormindo")

        while self._rodando.is_set():
            try:
                self._uma_rodada()
            except Exception:
                self._log("[erro]\n" + traceback.format_exc())
                self._estado("erro")
                self.falar("Tive um problema interno. Já me recuperei.")
                self._estado("dormindo")

    def _carregar_extras(self) -> None:
        from .sistema import INDICE
        INDICE.carregar()
        self.cerebro.aquecer()

    def _uma_rodada(self) -> None:
        self._interromper.clear()
        # 1) texto digitado tem prioridade
        if not self._textos.empty():
            self._origem_texto = True
            self.processar(self._textos.get())
            return
        self._origem_texto = False

        if self.mudo or self.ouvido is None:
            self._interromper.wait(timeout=0.5)
            if self._chamado_manual:
                self._chamado_manual = False
                self.evento("athena", "Meu microfone está desligado. Pode escrever no painel.")
            return

        # 2) espera "Atena" (ou clique/atalho)
        self._estado("dormindo")
        comando = ""
        if not self._chamado_manual:
            ativou, comando = self.ouvido.esperar_ativacao(self._interromper)
            if not ativou and not self._chamado_manual:
                return  # chegou texto ou foi encerrado
        if self._chamado_manual:
            self.evento("acao", "ativou")
        self._chamado_manual = False

        # 3) se você só disse "Atena" (ou bateu palmas), ela responde e escuta
        if not comando:
            self.evento("acao", "ativou")
            if self.ouvido.ultima_ativacao == "palmas":
                if not self.executar_rotina_palmas():
                    self._estado("dormindo")
                    return
            self._estado("ouvindo")
            comando = self._ouvir_comando(espera=7)
            if not comando:
                self._estado("dormindo")
                return
        self.processar(comando)

        # 4) conversa contínua: escuta mais um pouco sem precisar chamar de novo
        while self.config.get("ativacao.conversa_continua", True) and self._rodando.is_set() \
                and self._textos.empty() and not self.mudo:
            self._estado("ouvindo")
            comando = self._ouvir_comando(espera=float(self.config.get("ativacao.segundos_conversa_continua", 6)))
            if not comando:
                break
            self.processar(comando)
        self._estado("dormindo")

    def executar_rotina_palmas(self) -> bool:
        """Palmas: fala a frase, abre apps/sites, toca música. Devolve se deve ouvir um pedido depois."""
        from . import sistema
        r = self.config.get("rotina_palmas", {}) or {}
        nome = self.config.nome_usuario
        apps, sites, musica = r.get("apps") or [], r.get("sites") or [], (r.get("musica") or "").strip()
        tem_acoes = bool(apps or sites or musica)
        frase = (r.get("frase") or "").replace("{nome}", nome).strip()
        if not frase:
            frase = random.choice([f"Às ordens, {nome}.", "Pois não?", f"Sistemas prontos, {nome}."])
        elif not tem_acoes and "preparando" in frase.lower():
            frase = random.choice([f"Às ordens, {nome}.", "Pois não?", f"Estou aqui, {nome}.",
                                   "Online. O que manda?", f"Sistemas prontos, {nome}."])
        # abre tudo em paralelo enquanto ela fala
        def abrir():
            for app in apps:
                if self.config.permitido("apps"):
                    ok, info = sistema.abrir_app(str(app), self.config.apelidos_apps)
                    self._log(f"[rotina] {info}")
            for site in sites:
                if self.config.permitido("navegador"):
                    sistema.abrir_site(str(site), self.config.apelidos_sites)
            if musica and self.config.permitido("navegador"):
                sistema.tocar_no_youtube(musica)
        if tem_acoes:
            threading.Thread(target=abrir, daemon=True).start()
        self.falar(frase)
        return bool(r.get("ouvir_depois", True)) or not tem_acoes

    def _ouvir_comando(self, espera: float) -> str:
        audio = self.ouvido.gravar_fala(espera_max=espera, cancelar=self._interromper)
        if audio is None:
            return ""
        self._estado("pensando")
        texto = self.ouvido.transcrever(audio)
        # se você repetiu "Atena, ..." no começo, tira
        achou, resto = self.ouvido.contem_palavra(texto)
        return resto if achou and resto else texto

    # ================================================================== processamento
    def processar(self, texto: str) -> None:
        texto = texto.strip()
        if not texto:
            return
        self.evento("voce", texto)
        t = normalizar(texto)

        if re.match(CANCELAR, t):
            self.falar(random.choice(["Tudo bem.", "Sem problemas.", "Certo, fico de prontidão."]))
            return
        if re.search(r"\b(nova conversa|esquece (a|essa) conversa|limpa (a )?conversa)\b", t):
            self.cerebro.esquecer_conversa()
            self.falar("Conversa reiniciada. Do que precisa?")
            return

        if self.config.get("atalhos_rapidos", True):
            try:
                r = atalhos.tentar(texto, self.config)
            except Exception as e:
                self._log(f"[atalho] erro: {e}")
                r = None
            if r:
                self.evento("acao", r.acao)
                self.falar(r.resposta)
                return

        self._estado("pensando")
        try:
            resposta = self.cerebro.responder(
                texto, self.ctx, confirmar=self._confirmar,
                ao_usar_ferramenta=lambda nome, args: self.evento("acao", f"{nome} {args}"))
        except ErroCerebro as e:
            self._estado("erro")
            resposta = str(e)
        self.falar(resposta)

    def _confirmar(self, pergunta: str) -> bool:
        self.falar(pergunta)
        if self._origem_texto or self.ouvido is None:
            try:
                resp = self._textos.get(timeout=30)
            except queue.Empty:
                return False
        else:
            self._estado("ouvindo")
            audio = self.ouvido.gravar_fala(espera_max=7)
            resp = self.ouvido.transcrever(audio) if audio else ""
            self._estado("pensando")
        self.evento("voce", resp or "(sem resposta)")
        r = normalizar(resp)
        if re.search(NAO, r):
            return False
        return bool(re.search(SIM, r))
