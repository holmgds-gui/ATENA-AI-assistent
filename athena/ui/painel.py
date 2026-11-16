"""Painel de configurações da ATHENA (abre pelo botão direito no orbe ou pela bandeja)."""
from __future__ import annotations

import threading

from PySide6.QtCore import Qt, Signal
from PySide6.QtWidgets import (QCheckBox, QComboBox, QDoubleSpinBox, QFormLayout, QFrame, QHBoxLayout, QLabel,
                               QLineEdit, QListWidget, QPlainTextEdit, QPushButton, QScrollArea, QSpinBox,
                               QTabWidget, QTextBrowser, QVBoxLayout, QWidget)

from . import tema
from .componentes import ListaPermissoes, SeletorPersonalidade, SeletorVoz


def _rolavel(widget: QWidget) -> QScrollArea:
    area = QScrollArea()
    area.setWidgetResizable(True)
    area.setFrameShape(QFrame.NoFrame)
    area.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
    caixa = QWidget()
    lay = QVBoxLayout(caixa)
    lay.setContentsMargins(22, 16, 22, 16)
    lay.addWidget(widget)
    lay.addStretch(1)
    area.setWidget(caixa)
    return area


def _secao(texto):
    l = QLabel(texto.upper())
    l.setObjectName("secao")
    return l


class Painel(QWidget):
    salvo = Signal()
    rever_apresentacao = Signal()
    enviar_texto = Signal(str)
    _modelos_prontos = Signal(list)

    def __init__(self, config, cerebro=None):
        super().__init__()
        self.config = config
        self.cerebro = cerebro
        self.setObjectName("janela")
        self.setWindowTitle(f"{config.nome_ia} — Configurações")
        self.resize(820, 720)

        raiz = QVBoxLayout(self)
        raiz.setContentsMargins(0, 12, 0, 0)
        raiz.setSpacing(0)
        cab = QHBoxLayout()
        cab.setContentsMargins(22, 4, 22, 6)
        titulo = QLabel(f'{config.nome_ia}<span style="color:{tema.DESTAQUE}">.</span>')
        titulo.setObjectName("titulo")
        cab.addWidget(titulo)
        cab.addStretch(1)
        raiz.addLayout(cab)

        self.abas = QTabWidget()
        raiz.addWidget(self.abas, 1)
        self.abas.addTab(self._aba_conversa(), "Conversa")
        self.abas.addTab(self._aba_personalidade(), "Personalidade")
        self.abas.addTab(self._aba_permissoes(), "Permissões")
        self.abas.addTab(self._aba_voz_ouvido(), "Voz e ativação")
        self.abas.addTab(self._aba_cerebro(), "Cérebro")
        self.abas.addTab(self._aba_memoria(), "Memória")
        self.abas.addTab(self._aba_sobre(), "Sobre")

        rod = QHBoxLayout()
        rod.setContentsMargins(22, 10, 22, 16)
        self.aviso = QLabel("")
        self.aviso.setObjectName("apagado")
        rod.addWidget(self.aviso, 1)
        salvar = QPushButton("Salvar")
        salvar.setObjectName("primario")
        salvar.clicked.connect(self._salvar)
        rod.addWidget(salvar)
        raiz.addLayout(rod)

    # ------------------------------------------------------------------ abas
    def _aba_conversa(self):
        w = QWidget()
        lay = QVBoxLayout(w)
        lay.setContentsMargins(22, 14, 22, 8)
        self.historico = QTextBrowser()
        self.historico.setStyleSheet(f"background:{tema.SUPERFICIE}; border:1px solid {tema.LINHA};"
                                     f"border-radius:12px; padding:8px;")
        lay.addWidget(self.historico, 1)
        h = QHBoxLayout()
        self.entrada = QLineEdit()
        self.entrada.setPlaceholderText("Escreva um pedido pra ATHENA e aperte Enter…")
        self.entrada.returnPressed.connect(self._enviar)
        h.addWidget(self.entrada, 1)
        b = QPushButton("Enviar")
        b.clicked.connect(self._enviar)
        h.addWidget(b)
        lay.addLayout(h)
        return w

    def _aba_personalidade(self):
        w = QWidget()
        lay = QVBoxLayout(w)
        lay.setContentsMargins(0, 0, 0, 0)
        lay.setSpacing(10)
        form = QFormLayout()
        self.nome_usuario = QLineEdit(self.config.personalidade.get("como_me_chamar", ""))
        self.nome_ia = QLineEdit(self.config.personalidade.get("nome", "ATHENA"))
        form.addRow("Como ela te chama", self.nome_usuario)
        form.addRow("Nome da assistente", self.nome_ia)
        lay.addLayout(form)
        self.sel_pers = SeletorPersonalidade(self.config.personalidade.get("preset", "elegante_com_humor"),
                                             self.config.personalidade.get("estilo", ""))
        lay.addWidget(self.sel_pers)
        lay.addWidget(_secao("Regras extras"))
        self.regras = QPlainTextEdit(self.config.personalidade.get("regras_extras", ""))
        self.regras.setMinimumHeight(110)
        lay.addWidget(self.regras)
        return _rolavel(w)

    def _aba_permissoes(self):
        self.sel_perm = ListaPermissoes(self.config.get("permissoes", {}), self.config.get("seguranca.autonomia"))
        return _rolavel(self.sel_perm)

    def _aba_voz_ouvido(self):
        w = QWidget()
        lay = QVBoxLayout(w)
        lay.setContentsMargins(0, 0, 0, 0)
        lay.setSpacing(10)
        lay.addWidget(_secao("Voz"))
        self.sel_voz = SeletorVoz(self.config)
        lay.addWidget(self.sel_voz)

        lay.addWidget(_secao("Ativação"))
        form = QFormLayout()
        self.palavras = QLineEdit(", ".join(self.config.get("ativacao.palavras", ["atena"])))
        form.addRow("Palavras de ativação", self.palavras)
        self.atalho = QLineEdit(self.config.get("ativacao.atalho", "ctrl+alt+a"))
        form.addRow("Atalho de teclado", self.atalho)
        self.continua = QCheckBox("Continuar ouvindo depois de responder")
        self.continua.setChecked(bool(self.config.get("ativacao.conversa_continua", True)))
        form.addRow("", self.continua)
        self.sens = QDoubleSpinBox()
        self.sens.setRange(1.2, 8.0)
        self.sens.setSingleStep(0.1)
        self.sens.setValue(float(self.config.get("ouvido.sensibilidade", 2.5)))
        self.sens.setToolTip("Maior = precisa falar mais alto (bom em lugar barulhento)")
        form.addRow("Exigência de volume", self.sens)
        self.whisper = QComboBox()
        for t, d in (("tiny", "tiny — muito rápido, erra mais"), ("base", "base — rápido"),
                     ("small", "small — equilibrado (recomendado)"), ("medium", "medium — preciso, lento")):
            self.whisper.addItem(d, t)
        self.whisper.setCurrentIndex(max(0, self.whisper.findData(self.config.get("ouvido.modelo_whisper", "small"))))
        form.addRow("Reconhecimento de fala", self.whisper)
        self.atalhos_rapidos = QCheckBox("Comandos rápidos sem IA (abrir apps, horas, volume)")
        self.atalhos_rapidos.setChecked(bool(self.config.get("atalhos_rapidos", True)))
        form.addRow("", self.atalhos_rapidos)
        lay.addLayout(form)
        lay.addWidget(QLabel("Mudanças no reconhecimento de fala valem depois de reiniciar a ATHENA.",
                             objectName="apagado"))
        return _rolavel(w)

    def _aba_cerebro(self):
        w = QWidget()
        lay = QVBoxLayout(w)
        lay.setContentsMargins(0, 0, 0, 0)
        lay.setSpacing(10)
        form = QFormLayout()
        self.modelo = QComboBox()
        self.modelo.setEditable(True)
        self.modelo.addItem(self.config.get("cerebro.modelo", "qwen3:8b"))
        form.addRow("Modelo (Ollama)", self.modelo)
        self.url = QLineEdit(self.config.get("cerebro.url", "http://localhost:11434"))
        form.addRow("Endereço do Ollama", self.url)
        self.temp = QDoubleSpinBox()
        self.temp.setRange(0, 1.5)
        self.temp.setSingleStep(0.1)
        self.temp.setValue(float(self.config.get("cerebro.temperatura", 0.6)))
        self.temp.setToolTip("Mais alto = mais criativa; mais baixo = mais certinha")
        form.addRow("Criatividade", self.temp)
        self.hist = QSpinBox()
        self.hist.setRange(2, 60)
        self.hist.setValue(int(self.config.get("cerebro.max_historico", 16)))
        form.addRow("Mensagens lembradas", self.hist)
        lay.addLayout(form)
        dica = QLabel("Placa de vídeo com 8 GB ou mais: <b>qwen3:8b</b>. Placa mais fraca: <b>qwen3:4b</b>.<br>"
                      "Pra baixar outro modelo: <b>ollama pull nome-do-modelo</b> no terminal.")
        dica.setObjectName("apagado")
        dica.setWordWrap(True)
        lay.addWidget(dica)
        self._modelos_prontos.connect(self._preencher_modelos)
        threading.Thread(target=self._buscar_modelos, daemon=True).start()
        return _rolavel(w)

    def _aba_memoria(self):
        w = QWidget()
        lay = QVBoxLayout(w)
        lay.setContentsMargins(0, 0, 0, 0)
        lay.addWidget(QLabel("Coisas que a ATHENA guardou sobre você. Peça “lembra que…” pra adicionar.",
                             objectName="apagado", wordWrap=True))
        self.lista_mem = QListWidget()
        self.lista_mem.setStyleSheet(f"background:{tema.SUPERFICIE}; border:1px solid {tema.LINHA};"
                                     f"border-radius:12px; padding:6px;")
        self.lista_mem.setMinimumHeight(320)
        lay.addWidget(self.lista_mem)
        h = QHBoxLayout()
        apagar = QPushButton("Apagar selecionado")
        apagar.clicked.connect(self._apagar_memoria)
        h.addWidget(apagar)
        h.addStretch(1)
        lay.addLayout(h)
        self._carregar_memoria()
        return _rolavel(w)

    def _aba_sobre(self):
        w = QWidget()
        lay = QVBoxLayout(w)
        lay.setContentsMargins(0, 0, 0, 0)
        lay.setSpacing(12)
        t = QLabel(f"<b>{self.config.nome_ia}</b><br>Assistente Tecnológica de Execução e Navegação Artificial")
        t.setWordWrap(True)
        lay.addWidget(t)
        dicas = QLabel("• Diga “Atena” e o pedido, numa frase só.<br>"
                       "• Clique duas vezes no orbe ou use o atalho pra chamar sem falar.<br>"
                       "• Enquanto ela fala, clique no orbe pra interromper.<br>"
                       "• “Nova conversa” apaga o contexto da conversa atual.<br>"
                       "• Arraste o orbe pra onde quiser na tela.")
        dicas.setObjectName("subtitulo")
        dicas.setWordWrap(True)
        lay.addWidget(dicas)
        rever = QPushButton("Rever apresentação")
        rever.clicked.connect(self.rever_apresentacao.emit)
        lay.addWidget(rever, 0, Qt.AlignLeft)
        from ..config import PASTA_USUARIO
        local = QLabel(f"Suas configurações ficam em:<br><code>{PASTA_USUARIO}</code>")
        local.setObjectName("apagado")
        local.setTextInteractionFlags(Qt.TextSelectableByMouse)
        lay.addWidget(local)
        return _rolavel(w)

    # ------------------------------------------------------------------ ações
    def adicionar_mensagem(self, de_quem: str, texto: str):
        if de_quem == "voce":
            html = f'<p style="margin:6px 0"><span style="color:{tema.APAGADO}">Você</span><br>{texto}</p>'
        else:
            html = (f'<p style="margin:6px 0"><span style="color:{tema.DESTAQUE}">{self.config.nome_ia}</span>'
                    f'<br>{texto}</p>')
        self.historico.append(html)

    def _enviar(self):
        t = self.entrada.text().strip()
        if t:
            self.entrada.clear()
            self.enviar_texto.emit(t)

    def _buscar_modelos(self):
        if self.cerebro is not None:
            self._modelos_prontos.emit(self.cerebro.modelos_instalados())

    def _preencher_modelos(self, modelos):
        atual = self.modelo.currentText()
        self.modelo.clear()
        for m in modelos:
            self.modelo.addItem(m)
        if atual not in modelos:
            self.modelo.addItem(atual)
        self.modelo.setCurrentText(atual)

    def _carregar_memoria(self):
        self.lista_mem.clear()
        for m in self.config.memoria:
            self.lista_mem.addItem(m)

    def _apagar_memoria(self):
        item = self.lista_mem.currentItem()
        if item:
            self.config.esquecer(item.text())
            self._carregar_memoria()

    def showEvent(self, ev):
        self.config.recarregar()
        self._carregar_memoria()
        super().showEvent(ev)

    def _salvar(self):
        pers = self.sel_pers.valores()
        self.config.salvar_personalidade({
            "como_me_chamar": self.nome_usuario.text().strip(),
            "nome": self.nome_ia.text().strip() or "ATHENA",
            "regras_extras": self.regras.toPlainText().strip(),
            **pers,
        })
        palavras = [p.strip().lower() for p in self.palavras.text().split(",") if p.strip()] or ["atena"]
        self.config.salvar_geral({
            **self.sel_perm.valores(),
            **self.sel_voz.valores(),
            "ativacao": {"palavras": palavras, "atalho": self.atalho.text().strip() or "ctrl+alt+a",
                         "conversa_continua": self.continua.isChecked()},
            "ouvido": {"sensibilidade": round(self.sens.value(), 2), "modelo_whisper": self.whisper.currentData()},
            "cerebro": {"modelo": self.modelo.currentText().strip(), "url": self.url.text().strip(),
                        "temperatura": round(self.temp.value(), 2), "max_historico": self.hist.value()},
            "atalhos_rapidos": self.atalhos_rapidos.isChecked(),
        })
        self.aviso.setText("Salvo ✓")
        self.salvo.emit()
