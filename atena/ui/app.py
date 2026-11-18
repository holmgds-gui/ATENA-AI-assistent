"""Liga tudo: orbe + painel + apresentação + bandeja + atalho de teclado + assistente."""
from __future__ import annotations

import sys

from PySide6.QtCore import QObject, Qt, Signal
from PySide6.QtGui import QAction, QColor, QIcon, QPainter, QPixmap, QRadialGradient
from PySide6.QtWidgets import QApplication, QMenu, QSystemTrayIcon

from ..assistente import Assistente
from ..config import Config
from . import tema
from .apresentacao import Apresentacao
from .orbe import JanelaOrbe
from .painel import Painel


class Ponte(QObject):
    """Leva os eventos da thread da ATENA pra thread da interface (com segurança)."""
    evento = Signal(str, object)
    chamar = Signal()
    panico = Signal()


def icone_atena(tamanho=64) -> QIcon:
    """Ícone: anel de holograma na cor de destaque."""
    pm = QPixmap(tamanho, tamanho)
    pm.fill(Qt.transparent)
    p = QPainter(pm)
    p.setRenderHint(QPainter.Antialiasing)
    from PySide6.QtGui import QPen
    cor = QColor(tema.DESTAQUE)
    g = QRadialGradient(tamanho / 2, tamanho / 2, tamanho * 0.5)
    g.setColorAt(0, QColor("#FFFFFF"))
    g.setColorAt(0.18, cor)
    g.setColorAt(0.45, QColor(cor.red(), cor.green(), cor.blue(), 60))
    g.setColorAt(1, QColor(0, 0, 0, 0))
    p.setBrush(g)
    p.setPen(Qt.NoPen)
    p.drawEllipse(0, 0, tamanho, tamanho)
    p.setBrush(Qt.NoBrush)
    for k, f in enumerate((0.42, 0.3)):
        p.setPen(QPen(cor, 3 if k == 0 else 2))
        r = tamanho * f
        p.drawEllipse(int(tamanho / 2 - r), int(tamanho / 2 - r), int(r * 2), int(r * 2))
    p.end()
    return QIcon(pm)


def _converter_atalho(texto: str) -> str:
    """'ctrl+alt+a' -> '<ctrl>+<alt>+a' (formato do pynput)"""
    especiais = {"ctrl", "alt", "shift", "cmd", "win", "space", "enter", "tab", "esc"}
    partes = []
    for p in texto.lower().replace(" ", "").split("+"):
        p = "cmd" if p == "win" else p
        partes.append(f"<{p}>" if p in especiais or (p.startswith("f") and p[1:].isdigit()) else p)
    return "+".join(partes)


def _prioridade_alta() -> None:
    """Dá prioridade 'acima do normal' pra ATENA: o holograma não engasga quando o PC está ocupado
    (ex.: o Ollama usando o processador)."""
    try:
        import sys
        import psutil
        if sys.platform == "win32":
            psutil.Process().nice(psutil.ABOVE_NORMAL_PRIORITY_CLASS)
    except Exception as e:
        print(f"[app] não deu pra subir a prioridade: {e}")


class AppAtena:
    def __init__(self, argv, usar_microfone=True):
        from PySide6.QtCore import QCoreApplication
        QCoreApplication.setAttribute(Qt.AA_ShareOpenGLContexts)  # vários hologramas OpenGL na mesma app
        self.qt = QApplication(argv)
        if _ja_aberta():          # já tem uma ATENA aberta: só mostra ela e sai
            sys.exit(0)
        _prioridade_alta()
        self.qt.setQuitOnLastWindowClosed(False)
        self.qt.setApplicationName("ATENA")
        tema.carregar_fontes()
        self.config = Config()
        self.qt.setStyleSheet(tema.aplicar_paleta(self.config))
        self.qt.setWindowIcon(icone_atena())

        self.ponte = Ponte()
        self.ponte.evento.connect(self._ao_evento)
        self.ponte.chamar.connect(lambda: self.assistente.chamar())
        self.ponte.panico.connect(lambda: self.assistente.panico())
        self.assistente = Assistente(self.config, evento=lambda t, d=None: self.ponte.evento.emit(t, d),
                                     usar_microfone=usar_microfone)
        self.orbe = JanelaOrbe(int(self.config.get("interface.orbe_tamanho", 190)),
                               bool(self.config.get("interface.legenda", True)),
                               *tema.cores_da_config(self.config))
        self.orbe.orbe.nivel_externo = lambda: self.assistente.ouvido.nivel if self.assistente.ouvido else 0.0
        self.orbe.orbe.fonte_audio = self._audio_agora
        self.orbe.clicado.connect(self.assistente.chamar)
        self.orbe.abrir_painel.connect(self.abrir_painel)
        self.orbe.alternar_mudo.connect(self.assistente.alternar_mudo)
        self.orbe.sair.connect(self.sair)
        self.painel = None
        from .mira import Mira
        self.mira = Mira()
        self._criar_bandeja()
        self._hotkey = None
        self._escuta_esc = None

    # ------------------------------------------------------------------
    def _audio_agora(self):
        """O que a esfera usa pra se mexer: a voz da ATENA (falando) ou a sua (ouvindo)."""
        a = self.assistente
        if a.voz.falando:
            return a.voz.analise_agora()
        if a.ouvido is not None and a.estado == "ouvindo":
            return a.ouvido.nivel, a.ouvido.bandas
        return 0.0, None

    def _painel_na_tela(self) -> bool:
        return self.painel is not None and self.painel.isVisible() and not self.painel.isMinimized()

    def _criar_bandeja(self):
        self.bandeja = QSystemTrayIcon(icone_atena(), self.qt)
        self.bandeja.setToolTip("ATENA")
        menu = QMenu()
        for texto, fn in (("Abrir a ATENA", self.abrir_painel), ("Chamar", self.assistente.chamar),
                          ("Mostrar/esconder orbe", self._alternar_orbe),
                          ("Ligar/desligar microfone", self.assistente.alternar_mudo)):
            a = QAction(texto, menu)
            a.triggered.connect(fn)
            menu.addAction(a)
        menu.addSeparator()
        s = QAction("Sair", menu)
        s.triggered.connect(self.sair)
        menu.addAction(s)
        self.bandeja.setContextMenu(menu)
        self.bandeja.activated.connect(
            lambda motivo: self.abrir_painel() if motivo in (QSystemTrayIcon.DoubleClick, QSystemTrayIcon.Trigger)
            else None)
        self._menu_bandeja = menu
        self.bandeja.show()

    def _alternar_orbe(self):
        if self.orbe.isVisible():
            self.orbe.hide()
        else:
            self.orbe.setWindowOpacity(1.0)
            self.orbe.show()
            self.orbe.orbe.materializar()

    def _registrar_atalho(self):
        if self._hotkey:
            self._hotkey.stop()
            self._hotkey = None
        try:
            from pynput import keyboard
            combo = _converter_atalho(self.config.get("ativacao.atalho", "ctrl+alt+a"))
            self._hotkey = keyboard.GlobalHotKeys({combo: self.ponte.chamar.emit})
            self._hotkey.daemon = True
            self._hotkey.start()
        except Exception as e:
            print(f"[atalho] não consegui registrar o atalho de teclado: {e}")
        if self._escuta_esc is None:  # tecla de pânico: Esc enquanto ela está agindo
            try:
                from pynput import keyboard

                def ao_apertar(tecla):
                    if tecla == keyboard.Key.esc and (self.assistente.executando or self.assistente.voz.falando):
                        self.ponte.panico.emit()
                self._escuta_esc = keyboard.Listener(on_press=ao_apertar)
                self._escuta_esc.daemon = True
                self._escuta_esc.start()
            except Exception as e:
                print(f"[pânico] não consegui escutar a tecla Esc: {e}")

    def abrir_painel(self):
        if self.painel is None:
            self.painel = Painel(self.config, self.assistente.cerebro, self.assistente)
            self.painel.orbe_inicio.fonte_audio = self._audio_agora
            self.painel.orbe_inicio.nivel_externo = self.orbe.orbe.nivel_externo
            self.painel.alternar_microfone.connect(self.assistente.alternar_mudo)
            self.painel.chamar.connect(self.assistente.chamar)
            self.painel.enviar_texto.connect(self.assistente.enviar_texto)
            self.painel.salvo.connect(self._config_salva)
            self.painel.cores_mudaram.connect(self.orbe.orbe.set_cores)
            self.painel.rever_apresentacao.connect(lambda: Apresentacao(self.config, so_carrossel=True).exec())
        self.painel.abrir_animado()
        if self._invisivel:
            self.orbe.hide()

    def _config_salva(self):
        self.assistente.recarregar_config()
        self.orbe.orbe.set_cores(*tema.cores_da_config(self.config))
        self.orbe._mostrar_legenda = bool(self.config.get("interface.legenda", True))
        if not self._invisivel:
            self.orbe.setWindowOpacity(1.0)
            self.orbe.show()
        self._registrar_atalho()

    @property
    def _invisivel(self) -> bool:
        return self.config.get("interface.modo", "invisivel") == "invisivel"

    def _ao_evento(self, tipo, dados):
        if self.painel is not None:
            if tipo == "estado":
                self.painel.mostrar_estado(dados)
            elif tipo in ("voce", "atena"):
                self.painel.mostrar_fala(tipo, dados)
            elif tipo == "acao" and isinstance(dados, str) and dados.startswith("▸"):
                self.painel.mostrar_fala("acao", dados)
        if tipo == "estado":
            self.orbe.orbe.set_estado(dados)
            if self._painel_na_tela():  # a janela principal já mostra a esfera grande
                pass
            elif self._invisivel:
                if dados in ("ouvindo", "pensando", "falando", "erro"):
                    self.orbe.surgir()
                elif dados in ("dormindo", "mudo"):
                    self.orbe.sumir_depois(float(self.config.get("interface.segundos_ate_sumir", 6)))
        elif tipo == "acao" and dados == "ativou" and self._invisivel and not self._painel_na_tela():
            self.orbe.surgir()
        elif tipo == "acao" and isinstance(dados, str) and dados.startswith("▸"):
            if not self._painel_na_tela():
                self.orbe.mostrar_texto(dados[1:].strip(), "acao", 4)
            if self.painel is not None:
                self.painel.adicionar_mensagem("acao", dados)
        elif tipo == "mira" and isinstance(dados, dict):
            self.mira.apontar(int(dados["x"]), int(dados["y"]), dados.get("rotulo", ""))
        elif tipo in ("voce", "atena"):
            self.orbe.mostrar_texto(dados, tipo)
            if self.painel is not None:
                self.painel.adicionar_mensagem(tipo, dados)

    def sair(self):
        self.assistente.encerrar()
        if self._hotkey:
            self._hotkey.stop()
        if self._escuta_esc:
            self._escuta_esc.stop()
        self.bandeja.hide()
        self.qt.quit()

    # ------------------------------------------------------------------
    def rodar(self) -> int:
        if self.config.get("primeira_vez", True):
            ap = Apresentacao(self.config)
            if ap.exec() != Apresentacao.Accepted:
                return 0  # fechou a apresentação sem terminar
            self.config.recarregar()
            self.qt.setStyleSheet(tema.aplicar_paleta(self.config))
            self.orbe.orbe.set_cores(*tema.cores_da_config(self.config))
        self.orbe.posicionar_canto()
        self.abrir_painel()  # abre na tela Início, limpa, com a esfera grande
        if not self._invisivel:
            self.orbe.show()
        self._registrar_atalho()
        self.assistente.iniciar()
        return self.qt.exec()


NOME_INSTANCIA = "ATENA-instancia-unica"


def _ja_aberta() -> bool:
    """Se a ATENA já está rodando, pede pra ela aparecer e retorna True (essa cópia fecha).
    Evita duas ATENAs ouvindo o microfone e falando ao mesmo tempo."""
    from PySide6.QtNetwork import QLocalSocket
    s = QLocalSocket()
    s.connectToServer(NOME_INSTANCIA)
    if s.waitForConnected(400):
        s.write(b"mostrar")
        s.flush()
        s.waitForBytesWritten(400)
        s.disconnectFromServer()
        return True
    return False


def main(argv=None):
    argv = argv if argv is not None else sys.argv
    app = AppAtena(argv, usar_microfone="--sem-microfone" not in argv)
    from PySide6.QtNetwork import QLocalServer
    QLocalServer.removeServer(NOME_INSTANCIA)
    servidor = QLocalServer()
    servidor.listen(NOME_INSTANCIA)

    def nova_conexao():
        c = servidor.nextPendingConnection()
        if c is not None:
            c.readyRead.connect(lambda: (c.readAll(), app.abrir_painel()))
    servidor.newConnection.connect(nova_conexao)
    app._servidor_unico = servidor
    sys.exit(app.rodar())
