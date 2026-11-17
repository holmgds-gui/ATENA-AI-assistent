"""O 'maestro' da ATENA: junta ouvido, cérebro, voz e ferramentas num ciclo só.

Não depende da interface: avisa o que está acontecendo pela função `evento(tipo, dados)`.
Tipos de evento: estado ('dormindo'|'ouvindo'|'pensando'|'falando'|'mudo'|'erro'),
                 voce (o que você falou), atena (o que ela respondeu), log, acao.
"""
from __future__ import annotations

import datetime as dt
import queue
import random
import re
import threading
import traceback

from . import atalhos
from . import habilidades as hab_mod
from .agenda import Agenda
from .cerebro import ErroCerebro, criar_cerebro
from .config import PASTA_USUARIO
from .ferramentas import Contexto
from .sistema import normalizar
from .voz import Voz

SIM = r"\b(sim|pode|confirmo|confirma|claro|manda|isso|positivo|faz|faca|vai|bora|com certeza|ok|beleza)\b"
NAO = r"\b(nao|cancela|cancelar|negativo|para|deixa|esquece)\b"
CANCELAR = r"^(nada|cancela|cancelar|deixa|deixa pra la|esquece|esquece isso|nao e nada|nao era nada)$"


class CanalAgenda:
    """Rotina agendada: fala no PC (e avisa no Telegram, se conectado). Não dá pra confirmar nada sozinho."""
    nome = "agenda"

    def __init__(self, assistente):
        self.a = assistente

    def enviar(self, texto: str) -> None:
        self.a._falar_pc(texto)
        tg = self.a.telegram
        if tg is not None and tg.conectado and self.a.config.get("telegram.avisar_rotinas", True):
            tg.enviar(f"⏰ {texto}")

    def confirmar(self, pergunta: str) -> bool:
        return False

    def perguntar(self, pergunta: str) -> str:
        return ""


class _FalaAoVivo:
    """Recebe as frases da IA conforme ela escreve e já vai falando (sem esperar a resposta inteira)."""

    def __init__(self, a):
        import queue as _q
        self.a = a
        self.fila = _q.Queue()
        self.thread = None
        self.textos: list[str] = []

    def frase(self, texto: str) -> None:
        self.textos.append(texto)
        self.a.evento("atena", " ".join(self.textos))
        self.fila.put(texto)
        if self.thread is None:
            self.thread = threading.Thread(target=self._rodar, daemon=True)
            self.thread.start()

    def _rodar(self) -> None:
        a = self.a
        if a.ouvido:
            a.ouvido.surdo(True)
        try:
            a.voz.falar_fila(self.fila, ao_comecar=lambda: a._estado("falando"))
        except Exception as e:
            a._log(f"[voz] erro: {e}")
        finally:
            if a.ouvido and not a.mudo:
                a.ouvido.surdo(False)

    def terminar(self) -> None:
        """Fecha o que está sendo falado agora (dá pra continuar depois com novas frases)."""
        if self.thread is not None:
            import queue as _q
            self.fila.put(None)
            if self.thread is not threading.current_thread():
                self.thread.join(timeout=120)
            self.thread = None
            self.fila = _q.Queue()


class Assistente:
    def __init__(self, config, evento=None, usar_microfone: bool = True):
        self.config = config
        self.evento = evento or (lambda tipo, dados=None: None)
        self.usar_microfone = usar_microfone
        self.cerebro = criar_cerebro(config)
        self.voz = Voz(config)
        self.ouvido = None
        self._cancelar = threading.Event()
        self.habilidades = hab_mod.Habilidades(PASTA_USUARIO)
        config._listar_habilidades = lambda: self.habilidades.lista
        self.agenda = Agenda(PASTA_USUARIO, ao_disparar=self._ao_disparar_agenda)
        self.telegram = None
        self.canal = None            # de onde veio o pedido atual (None = voz/painel no PC)
        self._whisper_extra = None
        self.ctx = Contexto(config=config, falar=self.falar_async,
                            extras={"cancelar": self._cancelar, "mira": self._mira,
                                    "habilidades": self.habilidades, "agenda": self.agenda,
                                    "rodar_habilidade": self._rodar_habilidade})
        self.executando = False
        self._rodando = threading.Event()
        self._interromper = threading.Event()
        self._chamado_manual = False
        self._textos: queue.Queue[tuple[str, object]] = queue.Queue()
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
        threading.Thread(target=self._preparar_e_rodar, daemon=True, name="atena").start()

    def encerrar(self) -> None:
        self._rodando.clear()
        self.agenda.parar()
        if self.telegram:
            self.telegram.parar()
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

    def panico(self) -> None:
        """Tecla de pânico: para tudo que ela estiver fazendo no PC."""
        if self.executando or self.voz.falando:
            self._cancelar.set()
            self.voz.parar()
            self.evento("atena", "⛔ Parei tudo.")
            self._log("[pânico] ações canceladas")

    def _mira(self, x: int, y: int, rotulo: str = "") -> None:
        self.evento("mira", {"x": x, "y": y, "rotulo": rotulo})

    def enviar_texto(self, texto: str, canal=None) -> None:
        """Manda um pedido escrito (painel, terminal, Telegram ou rotina agendada)."""
        if texto.strip():
            self._textos.put((texto.strip(), canal))
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
        """Responde pelo canal certo: voz no PC, ou mensagem no Telegram."""
        if not texto:
            return
        if self.canal is not None:
            self.evento("atena", texto)
            self.canal.enviar(texto)
            return
        self._falar_pc(texto)

    def _falar_pc(self, texto: str) -> None:
        if not texto:
            return
        fluxo = getattr(self, "_fluxo", None)
        if fluxo is not None:      # termina a fala ao vivo antes (ex.: pergunta de confirmação)
            fluxo.terminar()
        self.evento("atena", texto)
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
        import time as _t
        inicio = _t.time()
        ouvido_pronto = threading.Event()

        def preparar_ouvido():  # carrega microfone e detector enquanto ela já dá oi
            if self.usar_microfone:
                try:
                    from .ouvido import Ouvido
                    o = Ouvido(self.config, log=self._log)
                    o.iniciar()
                    self.ouvido = o
                except Exception as e:
                    self.ouvido = None
                    self._log(f"[ouvido] microfone indisponível ({e}). Use o atalho ou escreva no painel.")
            ouvido_pronto.set()

        threading.Thread(target=preparar_ouvido, daemon=True).start()
        threading.Thread(target=self._carregar_extras, daemon=True).start()
        self.agenda.iniciar()
        self.conectar_telegram()
        self.falar(self._saudacao())
        self._log(f"[tempo] saudação em {_t.time() - inicio:.1f}s depois de abrir")
        ouvido_pronto.wait(timeout=60)
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
        # 1) texto digitado / Telegram / rotina agendada têm prioridade
        if not self._textos.empty():
            texto, canal = self._textos.get()
            self._origem_texto = True
            self.canal = canal
            try:
                self.processar(texto)
            finally:
                self.canal = None
            return
        self._origem_texto = False

        if self.mudo or self.ouvido is None:
            self._interromper.wait(timeout=0.5)
            if self._chamado_manual:
                self._chamado_manual = False
                self.evento("atena", "Meu microfone está desligado. Pode escrever no painel.")
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
            else:
                self._estado("ouvindo")
                self.voz.bip()  # resposta na hora: você sabe que ela ouviu
            self.cerebro.aquecer_se_frio()  # se o modelo saiu da memória, já recarrega enquanto você fala
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
        frase = (r.get("frase") or "").replace("{nome}", nome).replace("[nome]", nome).strip()
        if not frase and tem_acoes:
            frase = f"Bem-vindo de volta, {nome}. Preparando tudo."
        elif not frase:
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

        hab = self.habilidades.procurar(texto)
        if hab is not None:
            self.falar(f"Ativando {hab['nome']}.")
            self.falar(self._rodar_habilidade(hab))
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
        self._cancelar.clear()
        self.executando = True
        fluxo = _FalaAoVivo(self) if self.canal is None else None
        self._fluxo = fluxo
        try:
            resposta = self.cerebro.responder(texto, self.ctx, confirmar=self._confirmar,
                                              ao_usar_ferramenta=self._ao_usar_ferramenta,
                                              ao_frase=fluxo.frase if fluxo else None)
        except ErroCerebro as e:
            self._estado("erro")
            resposta = str(e)
            self.cerebro.final_transmitido = False
        finally:
            self.executando = False
            if fluxo:
                fluxo.terminar()   # espera ela acabar de falar o que já veio
            self._fluxo = None
        if self._cancelar.is_set():
            self._cancelar.clear()
            resposta = "Parei, como você pediu."
            self.falar(resposta)
            return
        if getattr(self.cerebro, "final_transmitido", False):
            resposta = ""          # já foi falada ao vivo, frase por frase
        passos = hab_mod.converter_passos(self.cerebro.ultimas_execucoes)
        sugerir = (self.config.get("habilidades.sugerir", True) and self.config.permitido("memoria")
                   and len(passos) >= int(self.config.get("habilidades.minimo_passos", 3))
                   and not isinstance(self.canal, CanalAgenda)
                   and not any(n == "executar_habilidade" for n, _, _ in self.cerebro.ultimas_execucoes))
        if not sugerir:
            self.falar(resposta)
            return
        self.falar((resposta + " " if resposta else "") + "Quer que eu salve isso como uma habilidade?")
        self._oferecer_habilidade(passos)

    # ================================================================== habilidades
    def _perguntar(self, pergunta: str | None = None) -> str:
        """Espera uma resposta curta pelo mesmo canal (voz, painel ou Telegram)."""
        if pergunta:
            if self.canal is not None:
                self.evento("atena", pergunta)
                return self.canal.perguntar(pergunta)
            self.falar(pergunta)
        elif self.canal is not None:
            return self.canal.perguntar("…")
        if self._origem_texto or self.ouvido is None:
            try:
                return self._textos.get(timeout=40)[0]
            except queue.Empty:
                return ""
        self._estado("ouvindo")
        audio = self.ouvido.gravar_fala(espera_max=7)
        return self.ouvido.transcrever(audio) if audio else ""

    def _oferecer_habilidade(self, passos: list[dict]) -> None:
        resp = self._perguntar(None if self.canal is None else "")
        if self.canal is not None and not resp:
            return
        r = normalizar(resp)
        if not r or re.search(NAO, r) and not re.search(r"(salva|chama)", r):
            self.falar("Tudo bem, não salvei.")
            return
        nome = re.sub(r"^(sim|pode|claro|isso|ok|beleza|bora|salva|salvar|quero)\b[ ,]*", "", r)
        nome = re.sub(r"^(sim|pode|claro|ok)\b[ ,]*", "", nome)
        nome = re.sub(r"^(salva|salvar|salve|chama|chame|bota|coloca)?\s*(como|de|o nome de)?\s*", "", nome).strip()
        if not nome or len(nome) < 3:
            nome = normalizar(self._perguntar("Como quer chamar essa habilidade?"))
            nome = re.sub(r"^(chama|chame|de|como)\s+", "", nome).strip()
        if not nome:
            self.falar("Fica pra próxima.")
            return
        h = self.habilidades.salvar(nome, passos)
        self.falar(f"Salvei como {h['nome']}. Da próxima vez é só falar {h['nome']}.")

    def _rodar_habilidade(self, hab: dict) -> str:
        autonomia = self.config.get("seguranca.autonomia", "confirmar_arriscadas")

        def executor(nome, args):
            self._ao_usar_ferramenta(nome, args)
            return self.cerebro._executar_com_seguranca(nome, args, self.ctx, autonomia, self._confirmar)

        self._cancelar.clear()
        self.executando = True
        try:
            resultados = hab_mod.executar(hab, executor, self._cancelar)
        finally:
            self.executando = False
        self.habilidades.registrar_uso(hab)
        if "cancelado" in resultados:
            self._cancelar.clear()
            return "Parei no meio, como você pediu."
        falhas = [r for r in resultados if normalizar(r).startswith(tuple(normalizar(f) for f in hab_mod.FALHAS))]
        if falhas:
            return f"{hab['nome'].capitalize()} rodou, mas {len(falhas)} passo(s) não deram certo."
        return random.choice([f"{hab['nome'].capitalize()} pronto.", "Tudo pronto.", "Feito."])

    # ================================================================== agenda e Telegram
    def _ao_disparar_agenda(self, r: dict) -> None:
        self._log(f"[agenda] rodando: {r.get('habilidade') or r.get('pedido')}")
        self.enviar_texto(r.get("habilidade") or r.get("pedido") or "", CanalAgenda(self))

    def conectar_telegram(self) -> None:
        if self.telegram is not None:
            self.telegram.parar()
            self.telegram = None
        if not self.config.get("telegram.token"):
            return
        from .telegram import CanalTelegram, print_jpeg
        self.telegram = CanalTelegram(self.config, ao_receber=self.enviar_texto,
                                      transcrever=self._transcrever_arquivo, ao_panico=self.panico,
                                      print_tela=print_jpeg, log=self._log)
        self.telegram.iniciar()

    def _transcrever_arquivo(self, caminho: str) -> str:
        modelo = getattr(self.ouvido, "_whisper", None) if self.ouvido else None
        if modelo is None:
            if self._whisper_extra is None:
                from faster_whisper import WhisperModel
                self._whisper_extra = WhisperModel(self.config.get("ouvido.modelo_whisper", "small"),
                                                   device="cpu", compute_type="int8")
            modelo = self._whisper_extra
        segmentos, _ = modelo.transcribe(caminho, language="pt", beam_size=3)
        return " ".join(s.text.strip() for s in segmentos).strip()

    _ROTULOS = {
        "abrir_app": "abrindo {nome}", "fechar_app": "fechando {nome}", "abrir_site": "abrindo {url}",
        "pesquisar_web": "pesquisando: {consulta}", "mostrar_pesquisa": "pesquisando: {consulta}",
        "tocar_youtube": "tocando {consulta}", "digitar_texto": "digitando…", "apertar_teclas": "teclas {teclas}",
        "ver_tela": "olhando a tela…", "ler_tela": "lendo a tela…", "clicar": "clicando em {alvo}",
        "rolar": "rolando pra {direcao}", "focar_janela": "indo pra janela {nome}", "info_sistema": "checando o PC…",
        "volume": "volume: {acao}", "controle_midia": "mídia: {acao}", "timer": "timer de {minutos} min",
        "criar_nota": "anotando…", "lembrar": "guardando na memória…", "energia": "{acao} o PC",
        "salvar_habilidade": "aprendendo {nome}", "executar_habilidade": "rodando {nome}",
        "agendar": "agendando pras {hora}", "listar_agendamentos": "vendo a agenda…",
    }

    def _ao_usar_ferramenta(self, nome: str, args: dict) -> None:
        if nome == "_fala":
            self.evento("atena", args.get("texto", ""))
            return
        modelo = self._ROTULOS.get(nome, nome)
        try:
            rotulo = modelo.format(**{k: str(v)[:40] for k, v in args.items()})
        except (KeyError, IndexError):
            rotulo = modelo.split(" {")[0]
        self.evento("acao", f"▸ {rotulo}")

    def _confirmar(self, pergunta: str) -> bool:
        if self.canal is not None:
            self.evento("atena", pergunta)
            return self.canal.confirmar(pergunta)
        self.falar(pergunta)
        if self._origem_texto or self.ouvido is None:
            try:
                resp = self._textos.get(timeout=30)[0]
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
