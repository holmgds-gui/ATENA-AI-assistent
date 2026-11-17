"""Peças reaproveitadas na apresentação e no painel: personalidade, permissões e voz."""
from __future__ import annotations

import threading

from PySide6.QtCore import Property, QEasingCurve, QPropertyAnimation, QRectF, Qt, Signal
from PySide6.QtGui import QColor, QPainter, QPen
from PySide6.QtWidgets import (QAbstractButton, QButtonGroup, QCheckBox, QComboBox, QFrame, QGridLayout, QHBoxLayout,
                               QLabel, QPlainTextEdit, QPushButton, QRadioButton, QSizePolicy, QSlider,
                               QVBoxLayout, QWidget)

from ..config import PERMISSOES, PRESETS
from ..voz import VOZES_EDGE
from . import tema
from .hud import PainelHud, rotulo_secao

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
        d = tema.DESTAQUE
        p.setPen(QPen(tema.cor(d, 0.35 + 0.6 * self._pos), 1))
        p.setBrush(tema.cor(d, 0.05 + 0.2 * self._pos))
        p.drawRect(QRectF(0.5, 3.5, self.width() - 1, self.height() - 7))
        x = 4 + self._pos * (self.width() - 22)
        p.setPen(Qt.NoPen)
        p.setBrush(tema.cor(d, 1) if self.isChecked() else QColor(tema.APAGADO))
        p.drawRect(QRectF(x, 7, 14, self.height() - 14))
        p.setBrush(tema.cor(d, 0.25 * self._pos))
        p.drawRect(QRectF(x - 3, 4, 20, self.height() - 8))
        p.end()


class Cartao(PainelHud):
    def __init__(self, titulo: str, descricao: str, parent=None):
        super().__init__("", parent, clicavel=True, chanfro=9)
        self.lay.setContentsMargins(14, 10, 14, 10)
        self.lay.setSpacing(1)
        t = QLabel(titulo.upper())
        t.setStyleSheet(f"font-weight: 700; font-size: 14px; letter-spacing: 1.5px;")
        d = QLabel(descricao)
        d.setObjectName("apagado")
        d.setWordWrap(True)
        self.lay.addWidget(t)
        self.lay.addWidget(d)


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
        lay.addWidget(rotulo_secao("Como ela é (dá pra editar)"))
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
            linha = PainelHud("", chanfro=8)
            linha.lay.setContentsMargins(0, 0, 0, 0)
            h = QHBoxLayout()
            linha.lay.addLayout(h)
            h.setContentsMargins(14, 8, 12, 8)
            v = QVBoxLayout()
            v.setSpacing(1)
            t = QLabel(titulo.upper())
            t.setStyleSheet("font-weight: 700; letter-spacing: 1.2px;")
            d = QLabel(desc)
            d.setObjectName("apagado")
            d.setWordWrap(True)
            v.addWidget(t)
            v.addWidget(d)
            h.addLayout(v, 1)
            sw = Interruptor(bool(permissoes.get(chave, True)))
            h.addWidget(sw)
            self.chaves[chave] = sw
            lay.addWidget(linha)

        rot = rotulo_secao("Confirmação")
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

        self.testar = QPushButton("▶  OUVIR EXEMPLO")
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
        self.testar.setText("TRANSMITINDO…")

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
        self.testar.setText("▶  OUVIR EXEMPLO")
