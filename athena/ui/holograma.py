"""Holograma da ATHENA: globo de malha 3D, anéis de giroscópio, rede neural e partículas.

Tudo é desenhado com linhas e luz (mistura aditiva), sem esfera sólida.
A cor vem da paleta escolhida nas configurações.
"""
from __future__ import annotations

import math
import time

import numpy as np
from PySide6.QtCore import QPointF, QRectF, Qt, QTimer
from PySide6.QtGui import QColor, QImage, QPainter, QPainterPath, QPen, QRadialGradient
from PySide6.QtWidgets import QWidget

PALETAS = {
    "dourado": ("Dourado holográfico", "#FFA62B", "#FFE2A0"),
    "ciano": ("Ciano", "#3DDCFF", "#B5F4FF"),
    "dourado_ciano": ("Dourado + ciano", "#FFA62B", "#3DDCFF"),
    "vermelho": ("Vermelho", "#FF4A4A", "#FFC0A8"),
    "verde": ("Verde matriz", "#3BFF8A", "#C2FFDA"),
    "roxo": ("Roxo", "#9F7BFF", "#E2D6FF"),
    "branco": ("Branco gelo", "#DCE8F5", "#7FD6FF"),
}


def _rot(ax: float, ay: float, az: float = 0.0) -> np.ndarray:
    cx, sx, cy, sy, cz, sz = math.cos(ax), math.sin(ax), math.cos(ay), math.sin(ay), math.cos(az), math.sin(az)
    rx = np.array([[1, 0, 0], [0, cx, -sx], [0, sx, cx]])
    ry = np.array([[cy, 0, sy], [0, 1, 0], [-sy, 0, cy]])
    rz = np.array([[cz, -sz, 0], [sz, cz, 0], [0, 0, 1]])
    return rx @ ry @ rz


def _fibonacci(n: int) -> np.ndarray:
    i = np.arange(n) + 0.5
    phi = np.arccos(1 - 2 * i / n)
    theta = math.pi * (1 + 5 ** 0.5) * i
    return np.stack([np.cos(theta) * np.sin(phi), np.cos(phi), np.sin(theta) * np.sin(phi)], axis=1)


class Orbe(QWidget):
    """Holograma animado. Use set_estado(), set_cores() e nivel_externo (0..1 do microfone)."""

    FPS = 40

    def __init__(self, tamanho: int = 170, primaria="#FFA62B", secundaria="#FFE2A0", parent=None):
        super().__init__(parent)
        self.setFixedSize(tamanho, tamanho)
        self.setAttribute(Qt.WA_TranslucentBackground)
        self.estado = "dormindo"
        self.nivel_externo = None
        self._t0 = time.time()
        self._energia = 0.2
        self._giro = 0.0
        self._ultimo = time.time()
        self._ondas: list[float] = []
        self.set_cores(primaria, secundaria)
        self._cor_atual = QColor(self._prim)

        # --- geometria (gerada uma vez)
        amostras = 44
        self._linhas = []                                    # malha: latitudes + longitudes
        for lat in np.linspace(-60, 60, 5):
            a = np.linspace(0, 2 * math.pi, amostras)
            r = math.cos(math.radians(lat))
            self._linhas.append(np.stack([np.cos(a) * r, np.full_like(a, math.sin(math.radians(lat))),
                                          np.sin(a) * r], axis=1))
        for lon in np.linspace(0, 180, 8, endpoint=False):
            b = np.linspace(-math.pi / 2, math.pi / 2, amostras // 2)
            lr = math.radians(lon)
            self._linhas.append(np.stack([np.cos(b) * math.cos(lr), np.sin(b), np.cos(b) * math.sin(lr)], axis=1))
            self._linhas.append(np.stack([-np.cos(b) * math.cos(lr), np.sin(b), -np.cos(b) * math.sin(lr)], axis=1))

        rng = np.random.default_rng(7)
        self._nos = _fibonacci(46) * 0.97                    # rede neural na superfície
        dots = self._nos @ self._nos.T
        idx = np.argwhere(np.triu(dots > 0.80, 1))
        self._arestas = idx
        self._fase_arestas = rng.uniform(0, 6.283, len(idx))

        self._aneis = [                                      # giroscópio: (raio, eixo inicial, velocidades)
            (1.22, (1.15, 0.0, 0.2), (0.0, 0.0, 0.9)),
            (1.36, (0.35, 0.9, 0.0), (0.6, 0.0, 0.0)),
            (1.50, (-0.6, 0.3, 0.8), (0.0, -0.45, 0.25)),
        ]
        a = np.linspace(0, 2 * math.pi, 72)
        self._circulo = np.stack([np.cos(a), np.zeros_like(a), np.sin(a)], axis=1)

        n = 130                                              # partículas
        self._p_dir = _fibonacci(n)[rng.permutation(n)]
        self._p_raio = rng.uniform(0.25, 1.75, n)
        self._p_vel = rng.uniform(0.15, 0.7, n) * rng.choice([-1, 1], n)
        self._p_fase = rng.uniform(0, 6.283, n)

        self._timer = QTimer(self)
        self._timer.timeout.connect(self.update)
        self._timer.start(int(1000 / 24))

    # ------------------------------------------------------------------ API
    def set_cores(self, primaria: str, secundaria: str) -> None:
        self._prim = QColor(primaria)
        self._sec = QColor(secundaria)

    def set_estado(self, estado: str) -> None:
        if estado != self.estado and estado == "falando":
            self._ondas.append(0.0)
        self.estado = estado
        # parado gasta menos CPU; em ação fica mais fluido
        fps = 24 if estado in ("dormindo", "mudo") else self.FPS
        self._timer.setInterval(int(1000 / fps))

    # ------------------------------------------------------------------ desenho
    def _cor_alvo(self) -> QColor:
        if self.estado == "erro":
            return QColor("#FF4A4A")
        if self.estado == "mudo":
            g = int(0.3 * self._prim.red() + 0.5 * self._prim.green() + 0.2 * self._prim.blue())
            return QColor(int(g * 0.6), int(g * 0.62), int(g * 0.68))
        return self._prim

    @staticmethod
    def _misturar(a: QColor, b: QColor, t: float) -> QColor:
        return QColor(int(a.red() + (b.red() - a.red()) * t), int(a.green() + (b.green() - a.green()) * t),
                      int(a.blue() + (b.blue() - a.blue()) * t))

    def _com_alpha(self, cor: QColor, a: float) -> QColor:
        c = QColor(cor)
        c.setAlphaF(max(0.0, min(1.0, a)))
        return c

    def paintEvent(self, _):
        agora = time.time()
        dt = min(0.1, agora - self._ultimo)
        self._ultimo = agora
        t = agora - self._t0
        w = self.width()
        cx = cy = w / 2
        R = w * 0.27

        est = self.estado
        nivel = self.nivel_externo() if (self.nivel_externo and est == "ouvindo") else 0.0
        if est == "falando":
            alvo = 0.6 + 0.4 * abs(math.sin(t * 6.7) * math.sin(t * 2.3 + 1.2))
            if np.random.random() < 0.05:
                self._ondas.append(0.0)
        elif est == "ouvindo":
            alvo = 0.5 + 0.5 * min(1.0, nivel * 1.6)
        elif est == "pensando":
            alvo = 0.65
        elif est in ("mudo", "erro"):
            alvo = 0.15
        else:
            alvo = 0.28 + 0.07 * math.sin(t * 1.3)
        self._energia += (alvo - self._energia) * 0.2
        e = self._energia
        vel_giro = {"pensando": 1.6, "falando": 0.7, "ouvindo": 0.55}.get(est, 0.3)
        self._giro += dt * vel_giro
        self._cor_atual = self._misturar(self._cor_atual, self._cor_alvo(), 0.1)
        cor = self._cor_atual
        sec = self._sec if est not in ("mudo", "erro") else cor
        destaque = self._misturar(cor, QColor(255, 255, 255), 0.55)

        img = QImage(w, w, QImage.Format_ARGB32_Premultiplied)
        img.fill(Qt.transparent)
        p = QPainter(img)
        p.setRenderHint(QPainter.Antialiasing)
        p.setCompositionMode(QPainter.CompositionMode_Plus)   # luz soma com luz = brilho de holograma

        # ---- halo de fundo suave
        g = QRadialGradient(QPointF(cx, cy), w * 0.5)
        g.setColorAt(0.0, self._com_alpha(cor, 0.22 + 0.25 * e))
        g.setColorAt(0.35, self._com_alpha(cor, 0.07 + 0.08 * e))
        g.setColorAt(1.0, self._com_alpha(cor, 0.0))
        p.setPen(Qt.NoPen)
        p.setBrush(g)
        p.drawEllipse(QPointF(cx, cy), w / 2, w / 2)

        rot = _rot(0.38 + 0.08 * math.sin(t * 0.4), self._giro, 0.12 * math.sin(t * 0.3))

        def projetar(pts: np.ndarray, escala: float = 1.0):
            q = pts @ rot.T
            persp = 1.0 / (1.0 - q[:, 2] * 0.18)
            x = cx + q[:, 0] * R * escala * persp
            y = cy - q[:, 1] * R * escala * persp
            prof = (q[:, 2] + 1) / 2                            # 0 = atrás, 1 = na frente
            return x, y, prof

        # deformação da malha quando ela fala (ondas na superfície)
        def deformar(pts):
            if est != "falando" and est != "ouvindo":
                return pts
            k = 0.07 * e
            fator = 1 + k * np.sin(pts[:, 1] * 6 + t * 8) * np.cos(pts[:, 0] * 4 - t * 5)
            return pts * fator[:, None]

        # ---- 1) malha do globo (dividida por profundidade: atrás fraco, frente forte)
        baldes = [QPainterPath() for _ in range(4)]
        for linha in self._linhas:
            x, y, prof = projetar(deformar(linha), 1.0 + 0.04 * e)
            for i in range(len(x) - 1):
                b = min(3, int((prof[i] + prof[i + 1]) * 2))
                baldes[b].moveTo(x[i], y[i])
                baldes[b].lineTo(x[i + 1], y[i + 1])
        for b, caminho in enumerate(baldes):
            forca = (0.12 + 0.88 * (b / 3) ** 1.6) * (0.45 + 0.75 * e)
            p.setPen(QPen(self._com_alpha(cor, 0.16 * forca), 3.2))
            p.drawPath(caminho)
            p.setPen(QPen(self._com_alpha(destaque if b == 3 else cor, 0.75 * forca), 0.9))
            p.drawPath(caminho)

        # ---- 2) rede neural: nós e conexões que acendem
        x, y, prof = projetar(self._nos, 1.0 + 0.04 * e)
        vel_pulso = 5.0 if est == "pensando" else 1.6
        brilho_arestas = 0.5 + 0.5 * np.sin(self._fase_arestas + t * vel_pulso)
        for k, (i, j) in enumerate(self._arestas):
            pz = (prof[i] + prof[j]) / 2
            if pz < 0.3:
                continue
            a = (brilho_arestas[k] ** 3) * pz * (0.35 + 0.9 * e)
            if a < 0.04:
                continue
            c = sec if (est == "pensando" and brilho_arestas[k] > 0.8) else cor
            p.setPen(QPen(self._com_alpha(c, a), 1.1))
            p.drawLine(QPointF(x[i], y[i]), QPointF(x[j], y[j]))
            if est == "pensando" and brilho_arestas[k] > 0.85:  # pulso viajando pela conexão
                f = (t * 2 + k * 0.37) % 1.0
                px, py = x[i] + (x[j] - x[i]) * f, y[i] + (y[j] - y[i]) * f
                p.setPen(Qt.NoPen)
                p.setBrush(self._com_alpha(QColor(255, 255, 255), 0.8 * pz))
                p.drawEllipse(QPointF(px, py), 1.4, 1.4)
        p.setPen(Qt.NoPen)
        for i in range(len(x)):
            if prof[i] < 0.35:
                continue
            tw = 0.5 + 0.5 * math.sin(t * 3 + i)
            p.setBrush(self._com_alpha(destaque, prof[i] * (0.4 + 0.6 * tw) * (0.5 + 0.6 * e)))
            p.drawEllipse(QPointF(x[i], y[i]), 1.5 + prof[i], 1.5 + prof[i])

        # ---- 3) anéis de giroscópio com "contas" correndo
        rapidez = {"pensando": 2.6, "falando": 1.3, "ouvindo": 1.1}.get(est, 0.6)
        for n_anel, (raio, base, vel) in enumerate(self._aneis):
            ang = [base[k] + vel[k] * t * rapidez for k in range(3)]
            r_anel = _rot(*ang)
            pts = (self._circulo * raio * (1 + 0.06 * e)) @ r_anel.T
            q = pts @ rot.T
            xs = cx + q[:, 0] * R
            ys = cy - q[:, 1] * R
            prof_a = (q[:, 2] / raio + 1) / 2
            for k in range(len(xs) - 1):
                a = (0.15 + 0.85 * prof_a[k]) * (0.35 + 0.8 * e)
                # anel tracejado: falhas regulares deixam com cara de HUD
                if (k + n_anel * 5) % 12 in (0, 1):
                    continue
                p.setPen(QPen(self._com_alpha(cor if n_anel != 1 else sec, a * 0.55), 1.2))
                p.drawLine(QPointF(xs[k], ys[k]), QPointF(xs[k + 1], ys[k + 1]))
            for c in range(2):
                k = int(((t * (0.25 + 0.1 * n_anel) * rapidez + c * 0.5 + n_anel * 0.3) % 1.0) * (len(xs) - 1))
                a = 0.4 + 0.6 * prof_a[k]
                p.setPen(Qt.NoPen)
                p.setBrush(self._com_alpha(destaque, a))
                p.drawEllipse(QPointF(xs[k], ys[k]), 2.2, 2.2)
                p.setBrush(self._com_alpha(cor, a * 0.35))
                p.drawEllipse(QPointF(xs[k], ys[k]), 5, 5)

        # ---- 4) partículas e faíscas
        ang = self._p_fase + t * self._p_vel * (2.2 if est == "pensando" else 1)
        expandir = 1 + 0.35 * e if est == "falando" else 1 + 0.15 * e
        base = self._p_dir * self._p_raio[:, None] * expandir
        ca, sa = np.cos(ang), np.sin(ang)
        pts = np.stack([base[:, 0] * ca - base[:, 2] * sa, base[:, 1], base[:, 0] * sa + base[:, 2] * ca], axis=1)
        q = pts @ rot.T
        xs = cx + q[:, 0] * R
        ys = cy - q[:, 1] * R
        prof_p = np.clip((q[:, 2] / 1.8 + 1) / 2, 0, 1)
        brilho = 0.5 + 0.5 * np.sin(t * 4 + self._p_fase * 3)
        p.setPen(Qt.NoPen)
        for k in range(len(xs)):
            a = prof_p[k] * brilho[k] * (0.35 + 0.8 * e)
            if a < 0.05:
                continue
            tam = 0.7 + 1.1 * prof_p[k] * brilho[k]
            p.setBrush(self._com_alpha(destaque if brilho[k] > 0.9 else cor, a))
            p.drawEllipse(QPointF(xs[k], ys[k]), tam, tam)

        # ---- 5) núcleo: olho de luz com anéis finos (não é uma bola)
        nucleo = R * (0.16 + 0.09 * e)
        g = QRadialGradient(QPointF(cx, cy), nucleo * 2.6)
        g.setColorAt(0.0, self._com_alpha(QColor(255, 255, 255), 0.55 + 0.4 * e))
        g.setColorAt(0.18, self._com_alpha(destaque, 0.55 + 0.3 * e))
        g.setColorAt(0.5, self._com_alpha(cor, 0.25 + 0.2 * e))
        g.setColorAt(1.0, self._com_alpha(cor, 0.0))
        p.setBrush(g)
        p.drawEllipse(QPointF(cx, cy), nucleo * 2.6, nucleo * 2.6)
        p.setBrush(Qt.NoBrush)
        for k, (f, v) in enumerate(((1.0, 1.4), (1.45, -0.9), (1.9, 0.6))):
            pen = QPen(self._com_alpha(destaque if k == 0 else cor, 0.7 - k * 0.15), 1.0 if k else 1.4)
            pen.setCapStyle(Qt.RoundCap)
            p.setPen(pen)
            rr = nucleo * f
            ini = (t * 90 * v * rapidez) % 360
            p.drawArc(QRectF(cx - rr, cy - rr, rr * 2, rr * 2), int(ini * 16), int((200 + 80 * e) * 16))

        # ---- 6) ondas de voz (falando)
        vivas = []
        for o in self._ondas:
            o += dt * 1.1
            if o < 1:
                vivas.append(o)
                p.setPen(QPen(self._com_alpha(cor, 0.6 * (1 - o)), 1.3))
                rr = R * (0.4 + o * 1.4)
                p.drawEllipse(QPointF(cx, cy), rr, rr)
        self._ondas = vivas

        # ---- 7) régua externa de HUD
        rr = R * 1.72
        giro_hud = t * 6 * rapidez
        for k in range(60):
            if (k + int(t * 2)) % 15 in (0, 1, 2):
                continue
            ang = math.radians(k * 6 + giro_hud)
            l = 6 if k % 5 == 0 else 3
            p.setPen(QPen(self._com_alpha(cor, 0.3 + 0.35 * e), 1))
            p.drawLine(QPointF(cx + math.cos(ang) * rr, cy + math.sin(ang) * rr),
                       QPointF(cx + math.cos(ang) * (rr - l), cy + math.sin(ang) * (rr - l)))

        # ---- 8) microfone desligado: um risco discreto
        if est == "mudo":
            p.setCompositionMode(QPainter.CompositionMode_SourceOver)
            pen = QPen(QColor(235, 240, 248, 210), 2.4)
            pen.setCapStyle(Qt.RoundCap)
            p.setPen(pen)
            p.drawLine(QPointF(cx - R * 0.35, cy + R * 0.35), QPointF(cx + R * 0.35, cy - R * 0.35))
        p.end()

        tela = QPainter(self)
        tela.drawImage(0, 0, img)
        tela.end()
