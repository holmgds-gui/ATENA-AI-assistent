"""Ícones de linha desenhados à mão (não dependem de fonte nem de arquivo)."""
from __future__ import annotations

import math

from PySide6.QtCore import QPointF, QRectF, Qt
from PySide6.QtGui import QPainter, QPainterPath, QPen


def desenhar(p: QPainter, nome: str, r: QRectF, cor, espessura: float = 1.6) -> None:
    p.save()
    pen = QPen(cor, espessura)
    pen.setCapStyle(Qt.RoundCap)
    pen.setJoinStyle(Qt.RoundJoin)
    p.setPen(pen)
    p.setBrush(Qt.NoBrush)
    s = min(r.width(), r.height())
    x0, y0 = r.center().x() - s / 2, r.center().y() - s / 2

    def P(x, y):  # coordenadas 0..1 dentro do quadrado
        return QPointF(x0 + x * s, y0 + y * s)

    def R(x, y, w, h):
        return QRectF(x0 + x * s, y0 + y * s, w * s, h * s)

    if nome == "menu":
        for y in (0.28, 0.5, 0.72):
            p.drawLine(P(0.18, y), P(0.82, y))
    elif nome == "fechar_menu":
        p.drawLine(P(0.18, 0.28), P(0.82, 0.28))
        p.drawLine(P(0.18, 0.5), P(0.62, 0.5))
        p.drawLine(P(0.18, 0.72), P(0.82, 0.72))
        p.drawLine(P(0.82, 0.42), P(0.72, 0.5))
        p.drawLine(P(0.82, 0.58), P(0.72, 0.5))
    elif nome == "inicio":  # mini holograma
        p.drawEllipse(R(0.2, 0.2, 0.6, 0.6))
        p.drawEllipse(R(0.36, 0.2, 0.28, 0.6))
        p.drawLine(P(0.2, 0.5), P(0.8, 0.5))
        p.drawEllipse(R(0.44, 0.44, 0.12, 0.12))
    elif nome == "conversa":
        path = QPainterPath(P(0.18, 0.25))
        path.lineTo(P(0.82, 0.25))
        path.lineTo(P(0.82, 0.66))
        path.lineTo(P(0.45, 0.66))
        path.lineTo(P(0.3, 0.8))
        path.lineTo(P(0.3, 0.66))
        path.lineTo(P(0.18, 0.66))
        path.closeSubpath()
        p.drawPath(path)
        for x in (0.36, 0.5, 0.64):
            p.drawPoint(P(x, 0.45))
    elif nome == "sistema":  # chip
        p.drawRect(R(0.28, 0.28, 0.44, 0.44))
        p.drawRect(R(0.4, 0.4, 0.2, 0.2))
        for k in (0.36, 0.5, 0.64):
            p.drawLine(P(k, 0.14), P(k, 0.28))
            p.drawLine(P(k, 0.72), P(k, 0.86))
            p.drawLine(P(0.14, k), P(0.28, k))
            p.drawLine(P(0.72, k), P(0.86, k))
    elif nome == "habilidades":  # raio/estrela
        path = QPainterPath(P(0.56, 0.12))
        for x, y in ((0.28, 0.54), (0.5, 0.54), (0.42, 0.88), (0.74, 0.42), (0.52, 0.42), (0.56, 0.12)):
            path.lineTo(P(x, y))
        p.drawPath(path)
    elif nome == "rotinas":  # relógio
        p.drawEllipse(R(0.18, 0.18, 0.64, 0.64))
        p.drawLine(P(0.5, 0.5), P(0.5, 0.3))
        p.drawLine(P(0.5, 0.5), P(0.65, 0.58))
    elif nome == "celular":
        p.drawRoundedRect(R(0.3, 0.14, 0.4, 0.72), 3, 3)
        p.drawLine(P(0.44, 0.76), P(0.56, 0.76))
    elif nome == "personalidade":  # rosto
        p.drawEllipse(R(0.22, 0.18, 0.56, 0.64))
        p.drawPoint(P(0.4, 0.42))
        p.drawPoint(P(0.6, 0.42))
        p.drawArc(R(0.36, 0.44, 0.28, 0.2), 200 * 16, 140 * 16)
    elif nome == "permissoes":  # escudo
        path = QPainterPath(P(0.5, 0.14))
        path.lineTo(P(0.8, 0.26))
        path.quadTo(P(0.78, 0.7), P(0.5, 0.86))
        path.quadTo(P(0.22, 0.7), P(0.2, 0.26))
        path.closeSubpath()
        p.drawPath(path)
        p.drawLine(P(0.38, 0.5), P(0.47, 0.6))
        p.drawLine(P(0.47, 0.6), P(0.64, 0.4))
    elif nome == "aparencia":  # gota/paleta
        p.drawEllipse(R(0.18, 0.18, 0.64, 0.64))
        for ang in (200, 250, 300, 350):
            a = math.radians(ang)
            p.drawEllipse(QRectF(P(0.5 + 0.18 * math.cos(a), 0.5 + 0.18 * math.sin(a)) - QPointF(2, 2),
                                 P(0.5 + 0.18 * math.cos(a), 0.5 + 0.18 * math.sin(a)) + QPointF(2, 2)))
    elif nome == "voz":  # microfone
        p.drawRoundedRect(R(0.38, 0.14, 0.24, 0.42), 0.12 * s, 0.12 * s)
        p.drawArc(R(0.26, 0.3, 0.48, 0.4), 180 * 16, 180 * 16)
        p.drawLine(P(0.5, 0.7), P(0.5, 0.84))
        p.drawLine(P(0.38, 0.84), P(0.62, 0.84))
    elif nome == "cerebro":  # rede de nós
        pts = [(0.5, 0.2), (0.24, 0.42), (0.76, 0.42), (0.34, 0.76), (0.66, 0.76), (0.5, 0.52)]
        for a, b in ((0, 1), (0, 2), (1, 3), (2, 4), (3, 4), (5, 0), (5, 3), (5, 4), (1, 5), (2, 5)):
            p.drawLine(P(*pts[a]), P(*pts[b]))
        for x, y in pts:
            p.drawEllipse(P(x, y), 1.8, 1.8)
    elif nome == "memoria":  # banco de dados
        p.drawEllipse(R(0.24, 0.16, 0.52, 0.18))
        p.drawLine(P(0.24, 0.25), P(0.24, 0.75))
        p.drawLine(P(0.76, 0.25), P(0.76, 0.75))
        p.drawArc(R(0.24, 0.41, 0.52, 0.18), 180 * 16, 180 * 16)
        p.drawArc(R(0.24, 0.66, 0.52, 0.18), 180 * 16, 180 * 16)
    elif nome == "sobre":
        p.drawEllipse(R(0.2, 0.2, 0.6, 0.6))
        p.drawLine(P(0.5, 0.46), P(0.5, 0.66))
        p.drawPoint(P(0.5, 0.34))
    elif nome == "microfone_off":
        desenhar(p, "voz", r, cor, espessura)
        p.drawLine(P(0.2, 0.84), P(0.8, 0.16))
    elif nome == "teclado":
        p.drawRoundedRect(R(0.14, 0.3, 0.72, 0.42), 3, 3)
        for x in (0.26, 0.4, 0.54, 0.68):
            p.drawPoint(P(x, 0.43))
        p.drawLine(P(0.32, 0.58), P(0.68, 0.58))
    elif nome == "engrenagem":
        p.drawEllipse(R(0.36, 0.36, 0.28, 0.28))
        for k in range(8):
            a = k * math.pi / 4
            p.drawLine(P(0.5 + 0.22 * math.cos(a), 0.5 + 0.22 * math.sin(a)),
                       P(0.5 + 0.33 * math.cos(a), 0.5 + 0.33 * math.sin(a)))
        p.drawEllipse(R(0.28, 0.28, 0.44, 0.44))
    elif nome == "chamar":  # onda de voz
        for x, h in ((0.22, 0.16), (0.36, 0.36), (0.5, 0.56), (0.64, 0.36), (0.78, 0.16)):
            p.drawLine(P(x, 0.5 - h / 2), P(x, 0.5 + h / 2))
    p.restore()
