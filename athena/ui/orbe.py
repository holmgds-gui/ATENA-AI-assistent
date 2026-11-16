"""Janela flutuante da ATHENA com o holograma (orbe) e a legenda."""
from __future__ import annotations

from PySide6.QtCore import Qt, QTimer, Signal
from PySide6.QtGui import QAction
from PySide6.QtWidgets import QApplication, QLabel, QMenu, QVBoxLayout, QWidget

from . import tema
from .holograma import Orbe  # noqa: F401  (reexportado)


class JanelaOrbe(QWidget):
    """Janela flutuante (sem borda, sempre por cima) com o orbe e a legenda."""
    clicado = Signal()
    abrir_painel = Signal()
    alternar_mudo = Signal()
    sair = Signal()

    def __init__(self, tamanho: int = 170, legenda: bool = True, primaria="#FFA62B", secundaria="#FFE2A0"):
        super().__init__(None, Qt.FramelessWindowHint | Qt.WindowStaysOnTopHint | Qt.Tool)
        self.setAttribute(Qt.WA_TranslucentBackground)
        self.orbe = Orbe(tamanho, primaria=primaria, secundaria=secundaria)
        self.legenda = QLabel("")
        self.legenda.setWordWrap(True)
        self.legenda.setAlignment(Qt.AlignCenter)
        self.legenda.setFixedWidth(max(260, tamanho + 90))
        self.legenda.setStyleSheet(
            f"background: rgba(10,14,20,215); border: 1px solid {tema.LINHA}; border-radius: 12px;"
            f"padding: 8px 12px; color: {tema.TEXTO}; font-size: 13px;")
        self.legenda.hide()
        self._mostrar_legenda = legenda

        lay = QVBoxLayout(self)
        lay.setContentsMargins(0, 0, 0, 0)
        lay.setSpacing(4)
        lay.addWidget(self.orbe, 0, Qt.AlignHCenter)
        lay.addWidget(self.legenda, 0, Qt.AlignHCenter)
        self.setFixedWidth(self.legenda.width())
        self._arrastando = None
        self._apagar = QTimer(self, singleShot=True, timeout=self._esconder_legenda)
        self.setToolTip("Clique duas vezes pra chamar a ATHENA · botão direito: opções")

    def posicionar_canto(self) -> None:
        tela = QApplication.primaryScreen().availableGeometry()
        self.adjustSize()
        self.move(tela.right() - self.width() - 24, tela.bottom() - self.orbe.height() - 110)

    def mostrar_texto(self, texto: str, de_quem: str = "athena", segundos: float = 7) -> None:
        if not self._mostrar_legenda or not texto:
            return
        cor = tema.DESTAQUE if de_quem == "athena" else tema.APAGADO
        prefixo = "" if de_quem == "athena" else "Você: "
        curto = texto if len(texto) < 220 else texto[:217] + "…"
        self.legenda.setText(f'<span style="color:{cor}">{prefixo}</span>{curto}')
        self.legenda.show()
        self.adjustSize()
        self._apagar.start(int(segundos * 1000 + len(texto) * 45))

    def _esconder_legenda(self):
        self.legenda.hide()
        self.adjustSize()

    # ---- mouse: arrastar, duplo clique, menu
    def mousePressEvent(self, ev):
        if ev.button() == Qt.LeftButton:
            self._arrastando = ev.globalPosition().toPoint() - self.frameGeometry().topLeft()

    def mouseMoveEvent(self, ev):
        if self._arrastando is not None and ev.buttons() & Qt.LeftButton:
            self.move(ev.globalPosition().toPoint() - self._arrastando)

    def mouseReleaseEvent(self, ev):
        self._arrastando = None

    def mouseDoubleClickEvent(self, ev):
        self.clicado.emit()

    def contextMenuEvent(self, ev):
        menu = QMenu(self)
        for texto, sinal in (("Chamar a ATHENA", self.clicado), ("Configurações", self.abrir_painel),
                             ("Ligar/desligar microfone", self.alternar_mudo)):
            acao = QAction(texto, menu)
            acao.triggered.connect(sinal.emit)
            menu.addAction(acao)
        menu.addSeparator()
        sair = QAction("Sair", menu)
        sair.triggered.connect(self.sair.emit)
        menu.addAction(sair)
        menu.exec(ev.globalPos())
