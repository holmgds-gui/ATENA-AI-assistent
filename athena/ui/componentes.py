"""Peças reaproveitadas na apresentação e no painel: personalidade, permissões e voz."""
from __future__ import annotations

import threading

from PySide6.QtCore import Property, QEasingCurve, QPropertyAnimation, QRectF, Qt, Signal
from PySide6.QtGui import QColor, QPainter
from PySide6.QtWidgets import (QAbstractButton, QButtonGroup, QCheckBox, QComboBox, QFrame, QGridLayout, QHBoxLayout,
                               QLabel, QPlainTextEdit, QPushButton, QRadioButton, QSizePolicy, QSlider,
                               QVBoxLayout, QWidget)

from ..config import PERMISSOES, PRESETS
from ..voz import VOZES_EDGE
from . import tema

NOMES_PRESETS = {
    "elegante_com_humor": ("Elegante com humor", "Estilo JARVIS: educada, precisa e com ironia fina"),
    "formal": ("Formal", "Assistente executiva, direta e discreta"),
    "amigavel": ("Amigável", "Descontraída, animada, tipo uma amiga que manja"),
    "sarcastica": ("Sarcástica", "Debochada e engraçada, mas resolve tudo"),
    "personalizada": ("Personalizada", "Você escreve do seu jeito"),
}

AUTONOMIAS = [
    ("confirmar_arriscadas", "Perguntar antes de ações arriscadas", "Recomendado. Fechar programas, desligar o PC..."),
    ("confirmar_tudo", "Perguntar antes de qualquer ação", "Mais seguro, porém mais lento"),
    ("livre", "Nunca perguntar", "Ela faz tudo direto, sem confirmar"),
]


class Interruptor(QAbstractButton):
    """Botão liga/desliga estilo celular."""

    def __init__(self, ligado=True, parent=None):
        super().__init__(parent)
        self.setCheckable(True)
        self.setChecked(ligado)
        self.setCursor(Qt.PointingHandCursor)
        self.setFixedSize(46, 26)
        self._pos = 1.0 if ligado else 0.0
        self._anim = QPropertyAnimation(self, b"pos", self)
        self._anim.setDuration(160)
        self._anim.setEasingCurve(QEasingCurve.OutCubic)
        self.toggled.connect(self._animar)

    def _animar(self, ligado):
        self._anim.stop()
        self._anim.setEndValue(1.0 if ligado else 0.0)
        self._anim.start()

    def _get_pos(self):
        return self._pos

    def _set_pos(self, v):
        self._pos = v
        self.update()

    pos = Property(float, _get_pos, _set_pos)

    def paintEvent(self, _):
        p = QPainter(self)
        p.setRenderHint(QPainter.Antialiasing)
        fundo = QColor(tema.DESTAQUE) if self.isChecked() else QColor(tema.LINHA)
        p.setPen(Qt.NoPen)
        p.setBrush(fundo)
        p.drawRoundedRect(QRectF(0, 0, self.width(), self.height()), 13, 13)
        x = 3 + self._pos * (self.width() - 26)
        p.setBrush(QColor("#FFFFFF"))
        p.drawEllipse(QRectF(x, 3, 20, 20))
        p.end()


class Cartao(QFrame):
    clicado = Signal()

    def __init__(self, titulo: str, descricao: str, parent=None):
        super().__init__(parent)
        self.setObjectName("cartao")
        self.setCursor(Qt.PointingHandCursor)
        lay = QVBoxLayout(self)
        lay.setContentsMargins(14, 11, 14, 11)
        lay.setSpacing(2)
        t = QLabel(titulo)
        t.setStyleSheet("font-weight: 700; font-size: 14.5px; background: transparent;")
        d = QLabel(descricao)
        d.setObjectName("apagado")
        d.setWordWrap(True)
        d.setStyleSheet("background: transparent;")
        lay.addWidget(t)
        lay.addWidget(d)

    def set_selecionado(self, v: bool):
        self.setProperty("selecionado", "true" if v else "false")
        self.style().unpolish(self)
        self.style().polish(self)

    def mouseReleaseEvent(self, ev):
        if ev.button() == Qt.LeftButton:
            self.clicado.emit()


class SeletorPersonalidade(QWidget):
    def __init__(self, preset: str, estilo: str, parent=None):
        super().__init__(parent)
        lay = QVBoxLayout(self)
        lay.setContentsMargins(0, 0, 0, 0)
        lay.setSpacing(10)
        grade = QGridLayout()
        grade.setSpacing(8)
        self.cartoes: dict[str, Cartao] = {}
        for i, (chave, (titulo, desc)) in enumerate(NOMES_PRESETS.items()):
            c = Cartao(titulo, desc)
            c.clicado.connect(lambda k=chave: self.escolher(k))
            self.cartoes[chave] = c
            grade.addWidget(c, i // 2, i % 2, 1, 2 if chave == "personalizada" else 1)
        lay.addLayout(grade)
        rot = QLabel("COMO ELA É (DÁ PRA EDITAR)")
        rot.setObjectName("secao")
        lay.addWidget(rot)
        self.texto = QPlainTextEdit()
        self.texto.setPlaceholderText("Descreva a personalidade: jeito de falar, humor, manias...")
        self.texto.setMinimumHeight(110)
        self.texto.textChanged.connect(self._editado)
        lay.addWidget(self.texto)
        self._ignorar = False
        self.preset = preset if preset in NOMES_PRESETS else "elegante_com_humor"
        self.escolher(self.preset, estilo or PRESETS.get(self.preset, ""))

    def escolher(self, chave: str, texto: str | None = None):
        self.preset = chave
        for k, c in self.cartoes.items():
            c.set_selecionado(k == chave)
        if texto is None:
            texto = PRESETS.get(chave, "") if chave != "personalizada" else self.texto.toPlainText()
        self._ignorar = True
        self.texto.setPlainText(texto)
        self._ignorar = False

    def _editado(self):
        if self._ignorar:
            return
        if self.preset != "personalizada" and self.texto.toPlainText().strip() != PRESETS.get(self.preset, "").strip():
            self.preset = "personalizada"
            for k, c in self.cartoes.items():
                c.set_selecionado(k == "personalizada")

    def valores(self) -> dict:
        return {"preset": self.preset, "estilo": self.texto.toPlainText().strip()}


class ListaPermissoes(QWidget):
    def __init__(self, permissoes: dict, autonomia: str, parent=None):
        super().__init__(parent)
        lay = QVBoxLayout(self)
        lay.setContentsMargins(0, 0, 0, 0)
        lay.setSpacing(6)
        self.chaves: dict[str, Interruptor] = {}
        for chave, (titulo, desc) in PERMISSOES.items():
            linha = QFrame()
            linha.setObjectName("cartao")
            h = QHBoxLayout(linha)
            h.setContentsMargins(14, 9, 12, 9)
            v = QVBoxLayout()
            v.setSpacing(1)
            t = QLabel(titulo)
            t.setStyleSheet("font-weight: 600; background: transparent;")
            d = QLabel(desc)
            d.setObjectName("apagado")
            d.setStyleSheet("background: transparent;")
            d.setWordWrap(True)
            v.addWidget(t)
            v.addWidget(d)
            h.addLayout(v, 1)
            sw = Interruptor(bool(permissoes.get(chave, True)))
            h.addWidget(sw)
            self.chaves[chave] = sw
            lay.addWidget(linha)

        rot = QLabel("CONFIRMAÇÃO")
        rot.setObjectName("secao")
        rot.setContentsMargins(0, 10, 0, 0)
        lay.addWidget(rot)
        self.grupo = QButtonGroup(self)
        for chave, titulo, desc in AUTONOMIAS:
            rb = QRadioButton(titulo)
            rb.setProperty("chave", chave)
            rb.setChecked(chave == autonomia)
            self.grupo.addButton(rb)
            lay.addWidget(rb)
            d = QLabel(desc)
            d.setObjectName("apagado")
            d.setWordWrap(True)
            d.setContentsMargins(28, 0, 0, 4)
            lay.addWidget(d)
        if not self.grupo.checkedButton():
            self.grupo.buttons()[0].setChecked(True)

    def valores(self) -> dict:
        return {"permissoes": {k: sw.isChecked() for k, sw in self.chaves.items()},
                "seguranca": {"autonomia": self.grupo.checkedButton().property("chave")}}


class SeletorVoz(QWidget):
    _fim_teste = Signal()

    def __init__(self, config, parent=None):
        super().__init__(parent)
        self.config = config
        self._fim_teste.connect(self._reset_botao)
        lay = QVBoxLayout(self)
        lay.setContentsMargins(0, 0, 0, 0)
        lay.setSpacing(8)

        self.combo = QComboBox()
        atual = config.get("voz.voz", "pt-BR-FranciscaNeural")
        for chave, nome in VOZES_EDGE.items():
            self.combo.addItem(nome, chave)
        if self.combo.findData(atual) < 0:
            self.combo.addItem(atual, atual)
        self.combo.setCurrentIndex(self.combo.findData(atual))
        lay.addWidget(self.combo)

        h = QHBoxLayout()
        lab = QLabel("Velocidade")
        lab.setObjectName("apagado")
        h.addWidget(lab)
        self.vel = QSlider(Qt.Horizontal)
        self.vel.setRange(-30, 40)
        try:
            self.vel.setValue(int(str(config.get("voz.velocidade", "+0%")).rstrip("%")))
        except ValueError:
            self.vel.setValue(0)
        h.addWidget(self.vel, 1)
        self.vel_txt = QLabel()
        self.vel_txt.setFixedWidth(44)
        self.vel.valueChanged.connect(lambda v: self.vel_txt.setText(f"{v:+d}%"))
        self.vel_txt.setText(f"{self.vel.value():+d}%")
        h.addWidget(self.vel_txt)
        lay.addLayout(h)

        self.motor_offline = QCheckBox("Usar voz offline")
        self.motor_offline.setChecked(config.get("voz.motor", "edge") == "offline")
        lay.addWidget(self.motor_offline)
        d = QLabel("Voz do próprio sistema: mais robótica, mas funciona sem internet.")
        d.setObjectName("apagado")
        d.setWordWrap(True)
        d.setContentsMargins(28, 0, 0, 0)
        lay.addWidget(d)

        self.testar = QPushButton("▶  Ouvir exemplo")
        self.testar.clicked.connect(self._testar)
        self.testar.setSizePolicy(QSizePolicy.Maximum, QSizePolicy.Fixed)
        lay.addWidget(self.testar)

    def valores(self) -> dict:
        return {"voz": {"voz": self.combo.currentData(), "velocidade": f"{self.vel.value():+d}%",
                        "motor": "offline" if self.motor_offline.isChecked() else "edge"}}

    def _testar(self):
        from ..voz import Voz

        class _Cfg:  # config temporária só pro teste
            def __init__(s, base, extra):
                s.base, s.extra = base, extra

            def get(s, caminho, padrao=None):
                chave = caminho.split(".")[-1]
                if caminho.startswith("voz.") and chave in s.extra["voz"]:
                    return s.extra["voz"][chave]
                return s.base.get(caminho, padrao)

        nome = self.config.personalidade.get("como_me_chamar") or ""
        frase = f"Olá{', ' + nome if nome else ''}. Sou a {self.config.nome_ia}. Todos os sistemas operacionais."
        voz = Voz(_Cfg(self.config, self.valores()))
        self.testar.setEnabled(False)
        self.testar.setText("Falando…")

        def rodar():
            try:
                voz.falar(frase)
            except Exception as e:
                print(f"[voz] teste falhou: {e}")
            finally:
                self._fim_teste.emit()  # volta pra thread da interface com segurança

        threading.Thread(target=rodar, daemon=True).start()

    def _reset_botao(self):
        self.testar.setEnabled(True)
        self.testar.setText("▶  Ouvir exemplo")
