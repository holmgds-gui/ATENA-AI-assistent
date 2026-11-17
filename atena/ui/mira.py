"""Mira holográfica: aparece onde a ATENA vai clicar, pra você ver o que ela está fazendo."""
from __future__ import annotations

import math
import time

from PySide6.QtCore import QPointF, QRectF, Qt, QTimer
from PySide6.QtGui import QColor, QFont, QPainter, QPen
from PySide6.QtWidgets import QApplication, QWidget

from . import tema

TAM = 150


class Mira(QWidget):
    def __init__(self):
        super().__init__(None, Qt.FramelessWindowHint | Qt.WindowStaysOnTopHint | Qt.Tool
                         | Qt.WindowTransparentForInput | Qt.WindowDoesNotAcceptFocus)
        self.setAttribute(Qt.WA_TranslucentBackground)
        self.setAttribute(Qt.WA_ShowWithoutActivating)
        self.setFixedSize(TAM + 220, TAM)
        self.rotulo = ""
        self._t0 = 0.0
        self._timer = QTimer(self, timeout=self._passo)

    def apontar(self, x_fisico: int, y_fisico: int, rotulo: str = "") -> None:
        """Recebe pixels reais da tela (os mesmos do clique) e converte pra coordenadas do Qt."""
        tela = QApplication.primaryScreen()
        for s in QApplication.screens():  # acha o monitor certo
            g, r = s.geometry(), s.devicePixelRatio()
            if g.x() * r <= x_fisico < (g.x() + g.width()) * r and g.y() * r <= y_fisico < (g.y() + g.height()) * r:
                tela = s
                break
        r = tela.devicePixelRatio()
        x, y = x_fisico / r, y_fisico / r
        self.rotulo = (rotulo or "")[:32]
        self.move(int(x - TAM / 2), int(y - TAM / 2))
        self._t0 = time.time()
        self.show()
        self.raise_()
        self._timer.start(16)

    def _passo(self):
        if time.time() - self._t0 > 1.4:
            self._timer.stop()
            self.hide()
            return
        self.update()

    def paintEvent(self, _):
        t = time.time() - self._t0
        p = QPainter(self)
        p.setRenderHint(QPainter.Antialiasing)
        c = QPointF(TAM / 2, TAM / 2)
        d = tema.DESTAQUE
        entrada = min(1.0, t / 0.35)
        saida = 1.0 if t < 1.0 else max(0.0, 1 - (t - 1.0) / 0.4)
        a = saida
        raio = 60 - 36 * (1 - (1 - entrada) ** 3)   # fecha de 60 pra 24
        # anéis girando
        for k, (f, vel, arco) in enumerate(((1.0, 220, 70), (1.45, -140, 50))):
            pen = QPen(tema.cor(d, 0.9 * a), 2 if k == 0 else 1.2)
            pen.setCapStyle(Qt.FlatCap)
            p.setPen(pen)
            rr = raio * f
            for q in range(3 if k == 0 else 2):
                ini = (t * vel + q * (360 / (3 if k == 0 else 2))) % 360
                p.drawArc(QRectF(c.x() - rr, c.y() - rr, rr * 2, rr * 2), int(ini * 16), arco * 16)
        # cruz
        p.setPen(QPen(tema.cor(d, a), 1.4))
        for ang in (0, 90, 180, 270):
            rad = math.radians(ang)
            p.drawLine(QPointF(c.x() + math.cos(rad) * (raio * 0.35), c.y() + math.sin(rad) * (raio * 0.35)),
                       QPointF(c.x() + math.cos(rad) * (raio * 0.8), c.y() + math.sin(rad) * (raio * 0.8)))
        # ponto central + pulso
        p.setPen(Qt.NoPen)
        p.setBrush(tema.cor("#FFFFFF", a))
        p.drawEllipse(c, 2.5, 2.5)
        pulso = (t * 1.6) % 1.0
        p.setPen(QPen(tema.cor(d, (1 - pulso) * 0.6 * a), 1.5))
        p.setBrush(Qt.NoBrush)
        p.drawEllipse(c, 8 + pulso * 40, 8 + pulso * 40)
        # etiqueta
        if self.rotulo:
            f = QFont("Share Tech Mono")
            f.setPointSizeF(9)
            p.setFont(f)
            txt = f"› {self.rotulo.upper()}"
            w = p.fontMetrics().horizontalAdvance(txt) + 16
            caixa = QRectF(c.x() + raio + 14, c.y() - 11, w, 22)
            p.setPen(QPen(tema.cor(d, 0.8 * a), 1))
            p.setBrush(QColor(4, 7, 11, int(215 * a)))
            p.drawRect(caixa)
            p.setPen(tema.cor("#FFFFFF", a))
            p.drawText(caixa, Qt.AlignCenter, txt)
            p.setPen(QPen(tema.cor(d, 0.7 * a), 1))
            p.drawLine(QPointF(c.x() + raio * 0.8, c.y()), QPointF(caixa.left(), c.y()))
        p.end()
