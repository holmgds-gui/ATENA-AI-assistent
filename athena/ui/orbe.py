"""O orbe da ATHENA: esfera animada estilo JARVIS que muda com o estado."""
from __future__ import annotations

import math
import random
import time

from PySide6.QtCore import QPointF, QRectF, Qt, QTimer, Signal
from PySide6.QtGui import (QAction, QColor, QFont, QPainter, QPainterPath, QPen, QRadialGradient)
from PySide6.QtWidgets import QApplication, QLabel, QMenu, QVBoxLayout, QWidget

from . import tema


def _misturar(a: QColor, b: QColor, t: float) -> QColor:
    return QColor(int(a.red() + (b.red() - a.red()) * t), int(a.green() + (b.green() - a.green()) * t),
                  int(a.blue() + (b.blue() - a.blue()) * t))


class Orbe(QWidget):
    """Só o desenho. Use set_estado() e set_nivel()."""

    def __init__(self, tamanho: int = 170, parent=None):
        super().__init__(parent)
        self.setFixedSize(tamanho, tamanho)
        self.setAttribute(Qt.WA_TranslucentBackground)
        self.estado = "dormindo"
        self.nivel_externo = None          # função que devolve 0..1 (volume do microfone)
        self._cor = QColor(tema.CORES_ESTADO["dormindo"])
        self._energia = 0.0                # 0..1, suavizado
        self._t0 = time.time()
        self._ondas: list[float] = []      # anéis que se expandem quando ela fala
        self._particulas = [(random.uniform(0, 6.283), random.uniform(0.55, 0.95), random.uniform(0.2, 0.7))
                            for _ in range(26)]
        self._timer = QTimer(self)
        self._timer.timeout.connect(self.update)
        self._timer.start(16)

    def set_estado(self, estado: str) -> None:
        if estado != self.estado and estado == "falando":
            self._ondas.append(0.0)
        self.estado = estado

    # ------------------------------------------------------------------
    def paintEvent(self, _):
        t = time.time() - self._t0
        w = self.width()
        c = QPointF(w / 2, w / 2)
        r = w * 0.24

        alvo = tema.CORES_ESTADO.get(self.estado, tema.CORES_ESTADO["dormindo"])
        self._cor = _misturar(self._cor, alvo, 0.08)
        cor = self._cor

        # energia de cada estado
        if self.estado == "falando":
            alvo_e = 0.55 + 0.35 * abs(math.sin(t * 7.3)) * abs(math.sin(t * 3.1 + 1))
            if random.random() < 0.03:
                self._ondas.append(0.0)
        elif self.estado == "ouvindo":
            nivel = self.nivel_externo() if self.nivel_externo else 0.0
            alvo_e = 0.45 + 0.55 * min(1.0, nivel * 1.6)
        elif self.estado == "pensando":
            alvo_e = 0.5 + 0.1 * math.sin(t * 6)
        elif self.estado in ("mudo", "erro"):
            alvo_e = 0.15
        else:
            alvo_e = 0.18 + 0.08 * (0.5 + 0.5 * math.sin(t * 1.4))  # respirando
        self._energia += (alvo_e - self._energia) * 0.18
        e = self._energia

        p = QPainter(self)
        p.setRenderHint(QPainter.Antialiasing)

        # 1) brilho externo
        brilho = QRadialGradient(c, w / 2)
        c1 = QColor(cor); c1.setAlpha(int(70 + 90 * e))
        c2 = QColor(cor); c2.setAlpha(int(18 + 30 * e))
        c3 = QColor(cor); c3.setAlpha(0)
        brilho.setColorAt(0.0, c1); brilho.setColorAt(0.45, c2); brilho.setColorAt(1.0, c3)
        p.setPen(Qt.NoPen); p.setBrush(brilho)
        p.drawEllipse(c, w / 2, w / 2)

        # 2) ondas (falando)
        novas = []
        for o in self._ondas:
            o += 0.018
            if o < 1:
                novas.append(o)
                cc = QColor(cor); cc.setAlpha(int(160 * (1 - o)))
                p.setPen(QPen(cc, 1.6)); p.setBrush(Qt.NoBrush)
                rr = r * (1.05 + o * 0.95)
                p.drawEllipse(c, rr, rr)
        self._ondas = novas

        # 3) anéis girando (arcos tipo HUD)
        rapidez = 3.2 if self.estado == "pensando" else 1.0
        aneis = [(1.32, 0.55, 70, 2.0), (1.5, -0.35, 110, 1.4), (1.68, 0.22, 40, 1.1), (1.68, 0.22, 40, 1.1)]
        for i, (fator, vel, tamanho_arco, espessura) in enumerate(aneis):
            cc = QColor(cor); cc.setAlpha(int(110 + 120 * e) if i < 2 else int(60 + 90 * e))
            pen = QPen(cc, espessura); pen.setCapStyle(Qt.RoundCap)
            p.setPen(pen); p.setBrush(Qt.NoBrush)
            rr = r * fator * (1 + 0.05 * e)
            rect = QRectF(c.x() - rr, c.y() - rr, rr * 2, rr * 2)
            inicio = (t * 60 * vel * rapidez + i * 180) % 360
            p.drawArc(rect, int(inicio * 16), int((tamanho_arco + 40 * e) * 16))
        # marcas de régua no anel externo
        cc = QColor(cor); cc.setAlpha(int(40 + 70 * e))
        p.setPen(QPen(cc, 1))
        rr = r * 1.85
        giro = t * 8 * rapidez
        for k in range(48):
            ang = math.radians(k * 7.5 + giro)
            l = 4 if k % 4 else 8
            p.drawLine(QPointF(c.x() + math.cos(ang) * rr, c.y() + math.sin(ang) * rr),
                       QPointF(c.x() + math.cos(ang) * (rr - l), c.y() + math.sin(ang) * (rr - l)))

        # 4) partículas orbitando
        for ang0, dist, vel in self._particulas:
            ang = ang0 + t * vel * (2.5 if self.estado == "pensando" else 1)
            d = r * (1.1 + dist * 0.5) * (1 + 0.15 * e)
            cc = QColor(cor); cc.setAlpha(int(90 + 120 * e))
            p.setPen(Qt.NoPen); p.setBrush(cc)
            p.drawEllipse(QPointF(c.x() + math.cos(ang) * d, c.y() + math.sin(ang) * d), 1.3, 1.3)

        # 5) núcleo (esfera) com borda ondulada
        caminho = QPainterPath()
        pontos = 90
        for k in range(pontos + 1):
            a = k / pontos * math.tau
            onda = (math.sin(a * 5 + t * 4) * 0.5 + math.sin(a * 3 - t * 3) * 0.5) * 0.06 * e
            rr = r * (0.92 + 0.12 * e + onda)
            pt = QPointF(c.x() + math.cos(a) * rr, c.y() + math.sin(a) * rr)
            caminho.moveTo(pt) if k == 0 else caminho.lineTo(pt)
        caminho.closeSubpath()
        g = QRadialGradient(QPointF(c.x() - r * 0.3, c.y() - r * 0.35), r * 1.4)
        claro = _misturar(cor, QColor(255, 255, 255), 0.75)
        escuro = _misturar(cor, QColor(4, 10, 20), 0.75)
        g.setColorAt(0.0, claro); g.setColorAt(0.35, cor); g.setColorAt(1.0, escuro)
        p.setBrush(g)
        borda = QColor(_misturar(cor, QColor(255, 255, 255), 0.4)); borda.setAlpha(200)
        p.setPen(QPen(borda, 1.2))
        p.drawPath(caminho)

        # 6) reflexo
        ref = QRadialGradient(QPointF(c.x() - r * 0.35, c.y() - r * 0.45), r * 0.5)
        ref.setColorAt(0, QColor(255, 255, 255, 120)); ref.setColorAt(1, QColor(255, 255, 255, 0))
        p.setPen(Qt.NoPen); p.setBrush(ref)
        p.drawEllipse(QPointF(c.x() - r * 0.3, c.y() - r * 0.38), r * 0.45, r * 0.32)

        # 7) mudo: risco
        if self.estado == "mudo":
            pen = QPen(QColor(230, 235, 245, 200), 3)
            pen.setCapStyle(Qt.RoundCap)
            p.setPen(pen)
            p.drawLine(QPointF(c.x() - r * 0.45, c.y() + r * 0.45), QPointF(c.x() + r * 0.45, c.y() - r * 0.45))
        p.end()


class JanelaOrbe(QWidget):
    """Janela flutuante (sem borda, sempre por cima) com o orbe e a legenda."""
    clicado = Signal()
    abrir_painel = Signal()
    alternar_mudo = Signal()
    sair = Signal()

    def __init__(self, tamanho: int = 170, legenda: bool = True):
        super().__init__(None, Qt.FramelessWindowHint | Qt.WindowStaysOnTopHint | Qt.Tool)
        self.setAttribute(Qt.WA_TranslucentBackground)
        self.orbe = Orbe(tamanho)
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
