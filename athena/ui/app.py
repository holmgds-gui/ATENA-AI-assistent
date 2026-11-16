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
    """Leva os eventos da thread da ATHENA pra thread da interface (com segurança)."""
    evento = Signal(str, object)
    chamar = Signal()


def icone_athena(tamanho=64) -> QIcon:
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


class AppAthena:
    def __init__(self, argv, usar_microfone=True):
        self.qt = QApplication(argv)
        self.qt.setQuitOnLastWindowClosed(False)
        self.qt.setApplicationName("ATHENA")
        self.config = Config()
        self.qt.setStyleSheet(tema.aplicar_paleta(self.config))
        self.qt.setWindowIcon(icone_athena())

        self.ponte = Ponte()
        self.ponte.evento.connect(self._ao_evento)
        self.ponte.chamar.connect(lambda: self.assistente.chamar())
        self.assistente = Assistente(self.config, evento=lambda t, d=None: self.ponte.evento.emit(t, d),
                                     usar_microfone=usar_microfone)
        self.orbe = JanelaOrbe(int(self.config.get("interface.orbe_tamanho", 190)),
                               bool(self.config.get("interface.legenda", True)),
                               *tema.cores_da_config(self.config))
        self.orbe.orbe.nivel_externo = lambda: self.assistente.ouvido.nivel if self.assistente.ouvido else 0.0
        self.orbe.clicado.connect(self.assistente.chamar)
        self.orbe.abrir_painel.connect(self.abrir_painel)
        self.orbe.alternar_mudo.connect(self.assistente.alternar_mudo)
        self.orbe.sair.connect(self.sair)
        self.painel = None
        self._criar_bandeja()
        self._hotkey = None

    # ------------------------------------------------------------------
    def _criar_bandeja(self):
        self.bandeja = QSystemTrayIcon(icone_athena(), self.qt)
        self.bandeja.setToolTip("ATHENA")
        menu = QMenu()
        for texto, fn in (("Chamar", self.assistente.chamar), ("Configurações", self.abrir_painel),
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
            lambda motivo: self.abrir_painel() if motivo == QSystemTrayIcon.DoubleClick else None)
        self._menu_bandeja = menu
        self.bandeja.show()

    def _alternar_orbe(self):
        self.orbe.setVisible(not self.orbe.isVisible())

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

    def abrir_painel(self):
        if self.painel is None:
            self.painel = Painel(self.config, self.assistente.cerebro)
            self.painel.enviar_texto.connect(self.assistente.enviar_texto)
            self.painel.salvo.connect(self._config_salva)
            self.painel.cores_mudaram.connect(self.orbe.orbe.set_cores)
            self.painel.rever_apresentacao.connect(lambda: Apresentacao(self.config, so_carrossel=True).exec())
        self.painel.show()
        self.painel.raise_()
        self.painel.activateWindow()

    def _config_salva(self):
        self.assistente.recarregar_config()
        self.orbe.orbe.set_cores(*tema.cores_da_config(self.config))
        self.orbe._mostrar_legenda = bool(self.config.get("interface.legenda", True))
        self._registrar_atalho()

    def _ao_evento(self, tipo, dados):
        if tipo == "estado":
            self.orbe.orbe.set_estado(dados)
        elif tipo in ("voce", "athena"):
            self.orbe.mostrar_texto(dados, tipo)
            if self.painel is not None:
                self.painel.adicionar_mensagem(tipo, dados)

    def sair(self):
        self.assistente.encerrar()
        if self._hotkey:
            self._hotkey.stop()
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
        self.orbe.show()
        self._registrar_atalho()
        self.assistente.iniciar()
        return self.qt.exec()


def main(argv=None):
    argv = argv if argv is not None else sys.argv
    app = AppAthena(argv, usar_microfone="--sem-microfone" not in argv)
    sys.exit(app.rodar())
