"""Peças visuais de HUD: fundo com grade, painéis angulares, medidores, gráficos e navegação."""
from __future__ import annotations

import math
import time

from PySide6.QtCore import QPointF, QRectF, Qt, QTimer, Signal
from PySide6.QtGui import (QColor, QFont, QLinearGradient, QPainter, QPainterPath, QPen, QPolygonF,
                           QRadialGradient)
from PySide6.QtWidgets import QFrame, QLabel, QSizePolicy, QVBoxLayout, QWidget

from . import tema


def fonte(familia="Rajdhani", tamanho=12.0, peso=QFont.Medium, espacamento=0.0) -> QFont:
    f = QFont(familia)
    f.setPointSizeF(tamanho)
    f.setWeight(peso)
    if espacamento:
        f.setLetterSpacing(QFont.AbsoluteSpacing, espacamento)
    return f


# ======================================================================
#  Fundo
# ======================================================================
def pintar_fundo(p: QPainter, r: QRectF, varredura: float | None = None) -> None:
    d = tema.DESTAQUE
    p.fillRect(r, QColor(tema.FUNDO))
    for (fx, fy, raio, a) in ((0.1, 0.0, 0.9, 0.10), (1.0, 1.0, 0.8, 0.07)):
        g = QRadialGradient(QPointF(r.width() * fx, r.height() * fy), max(r.width(), r.height()) * raio)
        g.setColorAt(0, tema.cor(d, a))
        g.setColorAt(1, tema.cor(d, 0))
        p.fillRect(r, g)
    passo = 28
    p.setPen(QPen(tema.cor(d, 0.045), 1))
    x = 0.0
    while x < r.width():
        p.drawLine(QPointF(x, 0), QPointF(x, r.height()))
        x += passo
    y = 0.0
    while y < r.height():
        p.drawLine(QPointF(0, y), QPointF(r.width(), y))
        y += passo
    p.setPen(Qt.NoPen)
    p.setBrush(tema.cor(d, 0.16))
    for i in range(0, int(r.width() / passo) + 1, 4):
        for j in range(0, int(r.height() / passo) + 1, 4):
            p.drawRect(QRectF(i * passo - 1, j * passo - 1, 2, 2))
    if varredura is not None:  # faixa de varredura descendo
        y = (varredura % 1.0) * (r.height() + 120) - 60
        g = QLinearGradient(0, y - 60, 0, y + 2)
        g.setColorAt(0, tema.cor(d, 0))
        g.setColorAt(1, tema.cor(d, 0.05))
        p.fillRect(QRectF(0, y - 60, r.width(), 62), g)
    v = QRadialGradient(r.center(), max(r.width(), r.height()) * 0.75)
    v.setColorAt(0.6, QColor(0, 0, 0, 0))
    v.setColorAt(1, QColor(0, 0, 0, 150))
    p.fillRect(r, v)


class FundoHud(QWidget):
    """QWidget com fundo de HUD (grade + brilho + varredura lenta)."""

    def __init__(self, parent=None, animado=True):
        super().__init__(parent)
        self.setAttribute(Qt.WA_StyledBackground, False)
        self._t0 = time.time()
        if animado:
            self._timer = QTimer(self)
            self._timer.timeout.connect(self.update)
            self._timer.start(66)

    def paintEvent(self, _):
        p = QPainter(self)
        pintar_fundo(p, QRectF(self.rect()), (time.time() - self._t0) / 9)
        p.end()


# ======================================================================
#  Painel angular
# ======================================================================
def caminho_chanfrado(r: QRectF, c: float = 10) -> QPainterPath:
    path = QPainterPath()
    path.addPolygon(QPolygonF([QPointF(r.left() + c, r.top()), QPointF(r.right(), r.top()),
                               QPointF(r.right(), r.bottom() - c), QPointF(r.right() - c, r.bottom()),
                               QPointF(r.left(), r.bottom()), QPointF(r.left(), r.top() + c)]))
    path.closeSubpath()
    return path


class PainelHud(QFrame):
    """Painel com cantos chanfrados, borda luminosa e etiqueta '// TÍTULO'."""
    clicado = Signal()

    def __init__(self, titulo: str = "", parent=None, clicavel=False, chanfro=10):
        super().__init__(parent)
        self.titulo = titulo.upper()
        self.selecionado = False
        self.clicavel = clicavel
        self._hover = False
        self.chanfro = chanfro
        if clicavel:
            self.setCursor(Qt.PointingHandCursor)
            self.setAttribute(Qt.WA_Hover, True)
        self.lay = QVBoxLayout(self)
        topo = 26 if titulo else 12
        self.lay.setContentsMargins(14, topo, 14, 12)
        self.lay.setSpacing(6)

    def set_selecionado(self, v: bool):
        self.selecionado = v
        self.update()

    def enterEvent(self, e):
        self._hover = True
        self.update()

    def leaveEvent(self, e):
        self._hover = False
        self.update()

    def mouseReleaseEvent(self, ev):
        if self.clicavel and ev.button() == Qt.LeftButton:
            self.clicado.emit()

    def paintEvent(self, _):
        d = tema.DESTAQUE
        p = QPainter(self)
        p.setRenderHint(QPainter.Antialiasing)
        r = QRectF(self.rect()).adjusted(0.5, 0.5, -0.5, -0.5)
        path = caminho_chanfrado(r, self.chanfro)
        ativo = self.selecionado or (self.clicavel and self._hover)
        g = QLinearGradient(0, 0, 0, r.height())
        g.setColorAt(0, tema.cor(d, 0.10 if self.selecionado else 0.045))
        g.setColorAt(1, tema.cor("#000000", 0.35))
        p.fillPath(path, g)
        p.setPen(QPen(tema.cor(d, 0.95 if self.selecionado else 0.55 if ativo else 0.22), 1))
        p.drawPath(path)
        # cantos destacados
        p.setPen(QPen(tema.cor(d, 0.9), 2))
        c = self.chanfro
        p.drawLine(QPointF(r.left(), r.top() + c), QPointF(r.left() + c, r.top()))
        p.drawLine(QPointF(r.right() - c, r.bottom()), QPointF(r.right(), r.bottom() - c))
        p.drawLine(QPointF(r.right() - 18, r.top() + 0.5), QPointF(r.right(), r.top() + 0.5))
        if self.titulo:
            p.setFont(fonte("Share Tech Mono", 8.5, espacamento=1.8))
            p.setPen(tema.cor(d, 0.95))
            p.drawText(QPointF(r.left() + c + 6, r.top() + 15), f"// {self.titulo}")
        if self.selecionado:
            p.setPen(Qt.NoPen)
            p.setBrush(tema.cor(d, 1))
            p.drawRect(QRectF(r.right() - 9, r.top() + 6, 4, 4))
        p.end()


# ======================================================================
#  Medidor circular
# ======================================================================
class Medidor(QWidget):
    def __init__(self, rotulo: str, unidade: str = "%", maximo: float = 100, alerta: float | None = None,
                 perigo: float | None = None, tamanho: int = 112, parent=None):
        super().__init__(parent)
        self.rotulo, self.unidade, self.maximo = rotulo.upper(), unidade, maximo
        self.alerta, self.perigo = alerta, perigo
        self.valor = None
        self._mostrado = 0.0
        self.detalhe = ""
        self.setMinimumSize(tamanho, tamanho + 16)
        self.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Fixed)
        self._timer = QTimer(self)
        self._timer.timeout.connect(self._passo)
        self._timer.start(33)
        self._t0 = time.time()

    def set_valor(self, v: float | None, detalhe: str = ""):
        self.valor = v
        self.detalhe = detalhe

    def _passo(self):
        alvo = self.valor if self.valor is not None else 0.0
        if abs(alvo - self._mostrado) > 0.05:
            self._mostrado += (alvo - self._mostrado) * 0.2
            self.update()
        elif int(time.time() * 2) % 2 == 0:
            self.update()

    def _cor(self) -> str:
        if self.valor is None:
            return tema.APAGADO
        if self.perigo is not None and self.valor >= self.perigo:
            return tema.PERIGO
        if self.alerta is not None and self.valor >= self.alerta:
            return tema.ALERTA
        return tema.DESTAQUE

    def paintEvent(self, _):
        p = QPainter(self)
        p.setRenderHint(QPainter.Antialiasing)
        lado = min(self.width(), self.height() - 16)
        cx, cy = self.width() / 2, lado / 2 + 2
        raio = lado / 2 - 8
        cor = self._cor()
        ini, total = 225, -270
        rect = QRectF(cx - raio, cy - raio, raio * 2, raio * 2)
        # trilho com marcas
        p.setPen(QPen(tema.cor(cor, 0.14), 6, Qt.SolidLine, Qt.FlatCap))
        p.drawArc(rect, ini * 16, total * 16)
        frac = max(0.0, min(1.0, self._mostrado / self.maximo)) if self.valor is not None else 0
        # brilho + arco
        p.setPen(QPen(tema.cor(cor, 0.25), 12, Qt.SolidLine, Qt.FlatCap))
        p.drawArc(rect, ini * 16, int(total * frac * 16))
        p.setPen(QPen(tema.cor(cor, 1), 4, Qt.SolidLine, Qt.FlatCap))
        p.drawArc(rect, ini * 16, int(total * frac * 16))
        for k in range(28):
            a = math.radians(ini + total * k / 27)
            r1, r2 = raio + 8, raio + (12 if k % 9 == 0 else 10)
            p.setPen(QPen(tema.cor(cor, 0.55 if k / 27 <= frac else 0.18), 1))
            p.drawLine(QPointF(cx + math.cos(a) * r1, cy - math.sin(a) * r1),
                       QPointF(cx + math.cos(a) * r2, cy - math.sin(a) * r2))
        # anel interno girando
        giro = (time.time() - self._t0) * 40
        p.setPen(QPen(tema.cor(cor, 0.35), 1))
        ri = raio - 12
        p.drawArc(QRectF(cx - ri, cy - ri, ri * 2, ri * 2), int(giro * 16), 70 * 16)
        p.drawArc(QRectF(cx - ri, cy - ri, ri * 2, ri * 2), int((giro + 180) * 16), 70 * 16)
        # texto
        p.setPen(QColor(tema.TEXTO))
        p.setFont(fonte("Share Tech Mono", max(11, lado * 0.15)))
        txt = "--" if self.valor is None else (f"{self._mostrado:.0f}" if self.maximo >= 20 else f"{self._mostrado:.1f}")
        p.drawText(QRectF(cx - raio, cy - lado * 0.16, raio * 2, lado * 0.24), Qt.AlignCenter, txt)
        p.setPen(tema.cor(cor, 0.9))
        p.setFont(fonte("Share Tech Mono", max(7, lado * 0.065)))
        p.drawText(QRectF(cx - raio, cy + lado * 0.07, raio * 2, lado * 0.12), Qt.AlignCenter, self.unidade)
        if self.detalhe:
            p.setPen(QColor(tema.APAGADO))
            p.drawText(QRectF(cx - raio, cy + lado * 0.18, raio * 2, lado * 0.12), Qt.AlignCenter, self.detalhe)
        p.setPen(QColor(tema.APAGADO))
        p.setFont(fonte("Rajdhani", 9.5, QFont.Bold, 2))
        p.drawText(QRectF(0, self.height() - 18, self.width(), 18), Qt.AlignCenter, self.rotulo)
        p.end()


# ======================================================================
#  Gráfico de linhas (histórico)
# ======================================================================
class Grafico(QWidget):
    def __init__(self, series: list[tuple[str, str]], maximo: float | None = 100, pontos: int = 60,
                 unidade: str = "%", parent=None):
        """series: [(nome, cor_hex ou 'destaque')]"""
        super().__init__(parent)
        self.series = series
        self.maximo = maximo
        self.pontos = pontos
        self.unidade = unidade
        self.dados = {n: [] for n, _ in series}
        self.setMinimumHeight(110)

    def adicionar(self, **valores):
        for n, v in valores.items():
            if n in self.dados:
                self.dados[n] = (self.dados[n] + [v if v is not None else 0.0])[-self.pontos:]
        self.update()

    def paintEvent(self, _):
        p = QPainter(self)
        p.setRenderHint(QPainter.Antialiasing)
        w, h = self.width(), self.height()
        topo, base = 18, h - 4
        mx = self.maximo or max([max(v) for v in self.dados.values() if v] + [1]) * 1.2
        p.setPen(QPen(tema.cor(tema.DESTAQUE, 0.08), 1))
        for k in range(5):
            y = topo + (base - topo) * k / 4
            p.drawLine(QPointF(0, y), QPointF(w, y))
        for k in range(0, self.pontos, 10):
            x = w * k / (self.pontos - 1)
            p.drawLine(QPointF(x, topo), QPointF(x, base))
        x_leg = 4
        for nome, c in self.series:
            c = tema.DESTAQUE if c == "destaque" else c
            vals = self.dados[nome]
            if len(vals) >= 2:
                passo = w / (self.pontos - 1)
                x0 = w - passo * (len(vals) - 1)
                pts = [QPointF(x0 + i * passo, base - (base - topo) * min(1, v / mx)) for i, v in enumerate(vals)]
                area = QPainterPath(QPointF(pts[0].x(), base))
                for pt in pts:
                    area.lineTo(pt)
                area.lineTo(QPointF(pts[-1].x(), base))
                g = QLinearGradient(0, topo, 0, base)
                g.setColorAt(0, tema.cor(c, 0.28))
                g.setColorAt(1, tema.cor(c, 0.0))
                p.fillPath(area, g)
                linha = QPainterPath(pts[0])
                for pt in pts[1:]:
                    linha.lineTo(pt)
                p.setPen(QPen(tema.cor(c, 1), 1.6))
                p.setBrush(Qt.NoBrush)
                p.drawPath(linha)
                p.setPen(Qt.NoPen)
                p.setBrush(tema.cor(c, 1))
                p.drawEllipse(pts[-1], 2.5, 2.5)
            atual = f"{vals[-1]:.0f}{self.unidade}" if vals else "--"
            p.setFont(fonte("Share Tech Mono", 8.5))
            p.setPen(tema.cor(c, 1))
            txt = f"■ {nome.upper()} {atual}"
            p.drawText(QPointF(x_leg, 12), txt)
            x_leg += p.fontMetrics().horizontalAdvance(txt) + 14
        p.end()


# ======================================================================
#  Barra segmentada
# ======================================================================
class Barra(QWidget):
    def __init__(self, rotulo: str, parent=None, segmentos=32):
        super().__init__(parent)
        self.rotulo = rotulo.upper()
        self.frac = 0.0
        self.texto = ""
        self.segmentos = segmentos
        self.setFixedHeight(34)

    def set(self, frac: float, texto: str, rotulo: str | None = None):
        self.frac = max(0.0, min(1.0, frac))
        self.texto = texto
        if rotulo is not None:
            self.rotulo = rotulo.upper()
        self.update()

    def paintEvent(self, _):
        p = QPainter(self)
        w = self.width()
        cor = tema.PERIGO if self.frac > 0.9 else tema.DESTAQUE
        p.setFont(fonte("Rajdhani", 9.5, QFont.Bold, 1.5))
        p.setPen(QColor(tema.APAGADO))
        p.drawText(QRectF(0, 0, w * 0.6, 16), Qt.AlignLeft | Qt.AlignVCenter, self.rotulo)
        p.setFont(fonte("Share Tech Mono", 9))
        p.setPen(QColor(tema.TEXTO))
        p.drawText(QRectF(w * 0.3, 0, w * 0.7, 16), Qt.AlignRight | Qt.AlignVCenter, self.texto)
        n = self.segmentos
        larg = (w - (n - 1) * 2) / n
        cheios = round(self.frac * n)
        for i in range(n):
            x = i * (larg + 2)
            p.fillRect(QRectF(x, 20, larg, 10), tema.cor(cor, 0.95 if i < cheios else 0.10))
        p.end()


# ======================================================================
#  Navegação lateral
# ======================================================================
class BotaoNav(QWidget):
    clicado = Signal()

    def __init__(self, codigo: str, texto: str, parent=None):
        super().__init__(parent)
        self.codigo, self.texto = codigo, texto.upper()
        self.ativo = False
        self._hover = False
        self.setFixedHeight(42)
        self.setCursor(Qt.PointingHandCursor)
        self.setAttribute(Qt.WA_Hover, True)

    def enterEvent(self, e):
        self._hover = True
        self.update()

    def leaveEvent(self, e):
        self._hover = False
        self.update()

    def mouseReleaseEvent(self, e):
        if e.button() == Qt.LeftButton:
            self.clicado.emit()

    def paintEvent(self, _):
        d = tema.DESTAQUE
        p = QPainter(self)
        p.setRenderHint(QPainter.Antialiasing)
        r = QRectF(self.rect()).adjusted(6, 3, -4, -3)
        if self.ativo or self._hover:
            path = caminho_chanfrado(r, 8)
            g = QLinearGradient(r.left(), 0, r.right(), 0)
            g.setColorAt(0, tema.cor(d, 0.28 if self.ativo else 0.10))
            g.setColorAt(1, tema.cor(d, 0.0))
            p.fillPath(path, g)
        if self.ativo:
            p.fillRect(QRectF(0, r.top() + 4, 3, r.height() - 8), tema.cor(d, 1))
        p.setFont(fonte("Share Tech Mono", 8.5))
        p.setPen(tema.cor(d, 0.95 if self.ativo else 0.45))
        p.drawText(QRectF(r.left() + 12, r.top(), 30, r.height()), Qt.AlignVCenter, self.codigo)
        p.setFont(fonte("Rajdhani", 11, QFont.Bold, 2.2))
        p.setPen(QColor("#FFFFFF") if self.ativo else QColor(tema.TEXTO if self._hover else tema.APAGADO))
        p.drawText(QRectF(r.left() + 42, r.top(), r.width() - 42, r.height()), Qt.AlignVCenter, self.texto)
        p.end()


class Indicador(QWidget):
    """Bolinha de status piscando + texto (ex: ● CÉREBRO ONLINE)."""

    def __init__(self, texto: str, parent=None):
        super().__init__(parent)
        self.texto = texto.upper()
        self.ok = None
        self.setFixedHeight(22)
        self._timer = QTimer(self)
        self._timer.timeout.connect(self.update)
        self._timer.start(500)

    def set(self, ok: bool | None, texto: str | None = None):
        self.ok = ok
        if texto:
            self.texto = texto.upper()
        f = fonte("Share Tech Mono", 8.5, espacamento=1.2)
        from PySide6.QtGui import QFontMetrics
        self.setFixedWidth(QFontMetrics(f).horizontalAdvance(self.texto) + 30)
        self.update()

    def paintEvent(self, _):
        p = QPainter(self)
        p.setRenderHint(QPainter.Antialiasing)
        c = tema.OK if self.ok else tema.PERIGO if self.ok is False else tema.APAGADO
        pisca = 1.0 if int(time.time() * 2) % 2 else 0.45
        p.setPen(Qt.NoPen)
        p.setBrush(tema.cor(c, 0.25 * pisca))
        p.drawEllipse(QPointF(9, 11), 7, 7)
        p.setBrush(tema.cor(c, pisca))
        p.drawEllipse(QPointF(9, 11), 3.2, 3.2)
        p.setFont(fonte("Share Tech Mono", 8.5, espacamento=1.2))
        p.setPen(tema.cor(c, 0.95))
        p.drawText(QRectF(22, 0, self.width() - 22, 22), Qt.AlignVCenter, self.texto)
        p.end()


def rotulo_secao(texto: str) -> QLabel:
    l = QLabel(f"// {texto.upper()}")
    l.setObjectName("secao")
    return l
