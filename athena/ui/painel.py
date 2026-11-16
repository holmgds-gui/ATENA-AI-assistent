"""Painel de configurações da ATHENA (abre pelo botão direito no orbe ou pela bandeja)."""
from __future__ import annotations

import threading
import time

from PySide6.QtCore import Qt, Signal
from PySide6.QtWidgets import (QCheckBox, QComboBox, QDoubleSpinBox, QFormLayout, QFrame, QGridLayout,
                               QHBoxLayout, QLabel,
                               QLineEdit, QListWidget, QPlainTextEdit, QPushButton, QScrollArea, QSpinBox,
                               QStackedWidget, QTabWidget, QTextBrowser, QVBoxLayout, QWidget)

from . import tema
from .componentes import ListaPermissoes, SeletorPersonalidade, SeletorVoz
from .hud import BotaoNav, FundoHud, Indicador, PainelHud, rotulo_secao


def _rolavel(widget: QWidget, titulo: str = "") -> QScrollArea:
    area = QScrollArea()
    area.setWidgetResizable(True)
    area.setFrameShape(QFrame.NoFrame)
    area.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
    caixa = QWidget()
    caixa.setObjectName("transparente")
    lay = QVBoxLayout(caixa)
    lay.setContentsMargins(4, 4, 10, 12)
    moldura = PainelHud(titulo)
    moldura.lay.setContentsMargins(18, 30 if titulo else 16, 18, 16)
    moldura.lay.addWidget(widget)
    lay.addWidget(moldura)
    lay.addStretch(1)
    area.setWidget(caixa)
    return area


def _secao(texto):
    return rotulo_secao(texto)


PAGINAS = [("01", "Conversa"), ("02", "Sistema"), ("03", "Personalidade"), ("04", "Permissões"),
           ("05", "Aparência"), ("06", "Voz"), ("07", "Cérebro"), ("08", "Memória"), ("09", "Sobre")]


class Painel(FundoHud):
    salvo = Signal()
    cores_mudaram = Signal(str, str)
    rever_apresentacao = Signal()
    enviar_texto = Signal(str)
    _modelos_prontos = Signal(list)
    _status_cerebro = Signal(bool)

    def __init__(self, config, cerebro=None):
        super().__init__()
        self.config = config
        self.cerebro = cerebro
        self.setObjectName("janela")
        self.setWindowTitle(f"{config.nome_ia} — Painel de controle")
        self.resize(1080, 760)
        self.setMinimumSize(900, 620)

        raiz = QVBoxLayout(self)
        raiz.setContentsMargins(0, 0, 0, 0)
        raiz.setSpacing(0)

        # ---- cabeçalho
        cab = QHBoxLayout()
        cab.setContentsMargins(18, 12, 22, 10)
        cab.setSpacing(12)
        from .holograma import Orbe
        self.mini = Orbe(58, *tema.cores_da_config(config))
        cab.addWidget(self.mini)
        nomes = QVBoxLayout()
        nomes.setSpacing(0)
        titulo = QLabel(f'{config.nome_ia.upper()}<span style="color:{tema.DESTAQUE}">_</span>')
        titulo.setObjectName("titulo")
        from .. import __version__
        sub = QLabel(f"PAINEL DE CONTROLE  //  v{__version__}")
        sub.setObjectName("secao")
        nomes.addWidget(titulo)
        nomes.addWidget(sub)
        cab.addLayout(nomes)
        cab.addStretch(1)
        self.ind_cerebro = Indicador("Cérebro: verificando")
        self.ind_cerebro.set(None, "Cérebro: verificando")
        self.ind_usuario = Indicador("")
        self.ind_usuario.set(True, f"Operador: {config.nome_usuario}")
        cab.addWidget(self.ind_usuario)
        cab.addWidget(self.ind_cerebro)
        self.relogio = QLabel("")
        self.relogio.setStyleSheet(f"font-family:{tema.FONTE_MONO}; font-size:20px; color:{tema.DESTAQUE};"
                                   f"padding-left:10px;")
        cab.addWidget(self.relogio)
        raiz.addLayout(cab)
        linha = QFrame()
        linha.setFixedHeight(1)
        linha.setStyleSheet(f"background: {tema.rgba(tema.DESTAQUE, 0.35)};")
        raiz.addWidget(linha)

        # ---- corpo: menu lateral + páginas
        corpo = QHBoxLayout()
        corpo.setContentsMargins(0, 10, 14, 0)
        corpo.setSpacing(10)
        lateral = QVBoxLayout()
        lateral.setContentsMargins(4, 4, 0, 14)
        lateral.setSpacing(2)
        self.botoes_nav = []
        for i, (cod, nome) in enumerate(PAGINAS):
            b = BotaoNav(cod, nome)
            b.setFixedWidth(200)
            b.clicado.connect(lambda i=i: self.ir_para(i))
            lateral.addWidget(b)
            self.botoes_nav.append(b)
        lateral.addStretch(1)
        self.aviso = QLabel("")
        self.aviso.setObjectName("secao")
        self.aviso.setContentsMargins(12, 0, 0, 4)
        lateral.addWidget(self.aviso)
        salvar = QPushButton("SALVAR  ▸")
        salvar.setObjectName("primario")
        salvar.setMinimumHeight(42)
        salvar.clicked.connect(self._salvar)
        cont = QHBoxLayout()
        cont.setContentsMargins(10, 0, 0, 0)
        cont.addWidget(salvar)
        lateral.addLayout(cont)
        corpo.addLayout(lateral)

        self.paginas = QStackedWidget()
        from .aba_sistema import AbaSistema
        self.aba_sistema = AbaSistema()
        for w in (self._aba_conversa(), self.aba_sistema, self._aba_personalidade(), self._aba_permissoes(),
                  self._aba_aparencia(), self._aba_voz_ouvido(), self._aba_cerebro(), self._aba_memoria(),
                  self._aba_sobre()):
            self.paginas.addWidget(w)
        corpo.addWidget(self.paginas, 1)
        raiz.addLayout(corpo, 1)
        self.ir_para(0)

        from PySide6.QtCore import QTimer
        self._relogio_timer = QTimer(self, timeout=self._tique)
        self._relogio_timer.start(1000)
        self._tique()
        self._status_cerebro.connect(lambda ok: self.ind_cerebro.set(ok, "Cérebro online" if ok else "Cérebro offline"))
        self.mini.set_estado("dormindo")

    def ir_para(self, i: int):
        self.paginas.setCurrentIndex(i)
        for k, b in enumerate(self.botoes_nav):
            b.ativo = k == i
            b.update()
        if PAGINAS[i][1] == "Sistema" and self.isVisible():
            self.aba_sistema.iniciar()
        else:
            self.aba_sistema.parar()

    def _tique(self):
        import datetime as _dt
        self.relogio.setText(_dt.datetime.now().strftime("%H:%M:%S"))
        if self.cerebro is not None and int(time.time()) % 10 == 0:
            threading.Thread(target=lambda: self._status_cerebro.emit(self.cerebro.esta_online()), daemon=True).start()

    def hideEvent(self, ev):
        self.aba_sistema.parar()
        super().hideEvent(ev)

    # ------------------------------------------------------------------ abas
    def _aba_conversa(self):
        w = QWidget()
        w.setObjectName("transparente")
        lay = QVBoxLayout(w)
        lay.setContentsMargins(4, 4, 10, 14)
        moldura = PainelHud("Canal de comunicação")
        self.historico = QTextBrowser()
        self.historico.setStyleSheet("background: transparent; border: none; padding: 4px;")
        moldura.lay.addWidget(self.historico)
        lay.addWidget(moldura, 1)
        h = QHBoxLayout()
        self.entrada = QLineEdit()
        self.entrada.setPlaceholderText("› digite um comando e aperte Enter…")
        self.entrada.setMinimumHeight(42)
        self.entrada.returnPressed.connect(self._enviar)
        h.addWidget(self.entrada, 1)
        b = QPushButton("ENVIAR ▸")
        b.setObjectName("primario")
        b.setMinimumHeight(42)
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
        return _rolavel(w, "Identidade e personalidade")

    def _aba_permissoes(self):
        self.sel_perm = ListaPermissoes(self.config.get("permissoes", {}), self.config.get("seguranca.autonomia"))
        return _rolavel(self.sel_perm, "Permissões no computador")

    def _aba_aparencia(self):
        from .holograma import PALETAS, Orbe
        w = QWidget()
        lay = QVBoxLayout(w)
        lay.setContentsMargins(0, 0, 0, 0)
        lay.setSpacing(12)
        self.paleta = self.config.get("interface.paleta", "dourado")
        self.cor_custom = self.config.get("interface.cor_personalizada") or "#FF3DCB"
        self.preview = Orbe(230, *tema.cores_da_config(self.config))
        self.preview.set_estado("pensando")
        lay.addWidget(self.preview, 0, Qt.AlignHCenter)
        lay.addWidget(_secao("Cor do holograma"))
        grade = QGridLayout()
        grade.setSpacing(8)
        self.botoes_cor = {}
        opcoes = list(PALETAS.items()) + [("personalizada", ("Personalizada…", self.cor_custom, "#FFFFFF"))]
        for i, (chave, (nome, prim, sec)) in enumerate(opcoes):
            b = QPushButton(nome)
            b.setCheckable(True)
            b.setProperty("prim", prim)
            b.setProperty("sec", sec)
            b.clicked.connect(lambda _=False, k=chave: self._escolher_paleta(k))
            self.botoes_cor[chave] = b
            grade.addWidget(b, i // 4, i % 4)
        lay.addLayout(grade)
        self._pintar_botoes_cor()

        form = QFormLayout()
        self.tam_orbe = QSpinBox()
        self.tam_orbe.setRange(120, 320)
        self.tam_orbe.setSingleStep(10)
        self.tam_orbe.setValue(int(self.config.get("interface.orbe_tamanho", 190)))
        form.addRow("Tamanho do holograma (px)", self.tam_orbe)
        self.legenda = QCheckBox("Mostrar legenda (o que você falou e a resposta) embaixo do holograma")
        self.legenda.setChecked(bool(self.config.get("interface.legenda", True)))
        form.addRow("", self.legenda)
        lay.addLayout(form)
        nota = QLabel("A cor do holograma muda na hora. A cor das janelas muda ao reabrir a ATHENA.")
        nota.setObjectName("apagado")
        nota.setWordWrap(True)
        lay.addWidget(nota)
        return _rolavel(w, "Aparência do holograma")

    def _pintar_botoes_cor(self):
        from PySide6.QtCore import QSize
        from PySide6.QtGui import QColor, QIcon, QPainter, QPixmap, QRadialGradient
        for chave, b in self.botoes_cor.items():
            prim = self.cor_custom if chave == "personalizada" else b.property("prim")
            sel = chave == self.paleta
            b.setChecked(sel)
            pm = QPixmap(36, 36)
            pm.fill(Qt.transparent)
            p = QPainter(pm)
            p.setRenderHint(QPainter.Antialiasing)
            g = QRadialGradient(18, 18, 18)
            g.setColorAt(0, QColor("#FFFFFF"))
            g.setColorAt(0.35, QColor(prim))
            g.setColorAt(1, QColor(0, 0, 0, 0))
            p.setBrush(g)
            p.setPen(Qt.NoPen)
            p.drawEllipse(0, 0, 36, 36)
            p.end()
            b.setIcon(QIcon(pm))
            b.setIconSize(QSize(20, 20))
            b.setStyleSheet(f"QPushButton {{ border: {2 if sel else 1}px solid {prim if sel else tema.LINHA};"
                            f" text-align: left; padding: 9px 10px; }}")

    def _escolher_paleta(self, chave):
        if chave == "personalizada":
            from PySide6.QtGui import QColor
            from PySide6.QtWidgets import QColorDialog
            cor = QColorDialog.getColor(QColor(self.cor_custom), self, "Escolha a cor do holograma")
            if not cor.isValid():
                self._pintar_botoes_cor()
                return
            self.cor_custom = cor.name()
        self.paleta = chave
        self._pintar_botoes_cor()
        prim, sec = self._cores_escolhidas()
        self.preview.set_cores(prim, sec)
        self.mini.set_cores(prim, sec)
        self.cores_mudaram.emit(prim, sec)

    def _cores_escolhidas(self):
        from .holograma import PALETAS
        if self.paleta == "personalizada":
            return self.cor_custom, tema._mix(self.cor_custom, "#FFFFFF", 0.6)
        _, prim, sec = PALETAS[self.paleta]
        return prim, sec

    def _aba_voz_ouvido(self):
        w = QWidget()
        lay = QVBoxLayout(w)
        lay.setContentsMargins(0, 0, 0, 0)
        lay.setSpacing(10)
        lay.addWidget(_secao("Voz"))
        self.sel_voz = SeletorVoz(self.config)
        lay.addWidget(self.sel_voz)

        lay.addWidget(_secao("Palmas"))
        fp = QFormLayout()
        self.palmas_on = QCheckBox("Bater palmas chama a ATHENA")
        self.palmas_on.setChecked(bool(self.config.get("ativacao.palmas", True)))
        fp.addRow("", self.palmas_on)
        self.num_palmas = QComboBox()
        for n in (1, 2, 3):
            self.num_palmas.addItem(f"{n} palma{'s' if n > 1 else ''}", n)
        self.num_palmas.setCurrentIndex(max(0, self.num_palmas.findData(int(self.config.get("ativacao.num_palmas", 2)))))
        fp.addRow("Quantidade", self.num_palmas)
        self.exig_palmas = QDoubleSpinBox()
        self.exig_palmas.setRange(0.5, 4.0)
        self.exig_palmas.setSingleStep(0.1)
        self.exig_palmas.setValue(float(self.config.get("ativacao.exigencia_palmas", 1.0)))
        self.exig_palmas.setToolTip("Se ela acordar sozinha com barulhos, aumente. Se não reconhecer suas palmas, diminua.")
        fp.addRow("Força da palma", self.exig_palmas)
        r = self.config.get("rotina_palmas", {}) or {}
        self.rot_frase = QLineEdit(r.get("frase", ""))
        self.rot_frase.setPlaceholderText("Bem-vindo de volta, {nome}. Preparando tudo.")
        fp.addRow("Frase", self.rot_frase)
        self.rot_apps = QLineEdit(", ".join(r.get("apps") or []))
        self.rot_apps.setPlaceholderText("spotify, discord, visual studio code")
        fp.addRow("Abrir apps", self.rot_apps)
        self.rot_sites = QLineEdit(", ".join(r.get("sites") or []))
        self.rot_sites.setPlaceholderText("youtube, github.com")
        fp.addRow("Abrir sites", self.rot_sites)
        self.rot_musica = QLineEdit(r.get("musica", ""))
        self.rot_musica.setPlaceholderText("ex: back in black ac dc  (toca no YouTube)")
        fp.addRow("Tocar música", self.rot_musica)
        self.rot_ouvir = QCheckBox("Depois da rotina, esperar meu pedido")
        self.rot_ouvir.setChecked(bool(r.get("ouvir_depois", True)))
        fp.addRow("", self.rot_ouvir)
        lay.addLayout(fp)

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
        return _rolavel(w, "Voz e ativação")

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
        return _rolavel(w, "Cérebro (IA local)")

    def _aba_memoria(self):
        w = QWidget()
        lay = QVBoxLayout(w)
        lay.setContentsMargins(0, 0, 0, 0)
        lay.addWidget(QLabel("Coisas que a ATHENA guardou sobre você. Peça “lembra que…” pra adicionar.",
                             objectName="apagado", wordWrap=True))
        self.lista_mem = QListWidget()

        self.lista_mem.setMinimumHeight(320)
        lay.addWidget(self.lista_mem)
        h = QHBoxLayout()
        apagar = QPushButton("APAGAR SELECIONADO")
        apagar.clicked.connect(self._apagar_memoria)
        h.addWidget(apagar)
        h.addStretch(1)
        lay.addLayout(h)
        self._carregar_memoria()
        return _rolavel(w, "Memória de longo prazo")

    def _aba_sobre(self):
        w = QWidget()
        lay = QVBoxLayout(w)
        lay.setContentsMargins(0, 0, 0, 0)
        lay.setSpacing(12)
        from .. import __version__
        t = QLabel(f"<b>{self.config.nome_ia}</b>  v{__version__}<br>Assistente Tecnológica de Execução e Navegação Artificial")
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
        rever = QPushButton("REVER APRESENTAÇÃO")
        rever.clicked.connect(self.rever_apresentacao.emit)
        lay.addWidget(rever, 0, Qt.AlignLeft)
        from ..config import PASTA_USUARIO
        local = QLabel(f"Suas configurações ficam em:<br><code>{PASTA_USUARIO}</code>")
        local.setObjectName("apagado")
        local.setTextInteractionFlags(Qt.TextSelectableByMouse)
        lay.addWidget(local)
        return _rolavel(w, "Sobre")

    # ------------------------------------------------------------------ ações
    def adicionar_mensagem(self, de_quem: str, texto: str):
        import datetime as _dt
        hora = _dt.datetime.now().strftime("%H:%M:%S")
        mono = "font-family:'Share Tech Mono',monospace; font-size:11px; letter-spacing:1px"
        if de_quem == "voce":
            quem = self.config.nome_usuario.upper()
            html = (f'<p style="margin:8px 0"><span style="{mono}; color:{tema.APAGADO}">[{hora}] {quem} ›</span>'
                    f'<br>{texto}</p>')
        else:
            html = (f'<p style="margin:8px 0"><span style="{mono}; color:{tema.DESTAQUE}">[{hora}] '
                    f'{self.config.nome_ia.upper()} ›</span><br><span style="color:#FFFFFF">{texto}</span></p>')
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
        if PAGINAS[self.paginas.currentIndex()][1] == "Sistema":
            self.aba_sistema.iniciar()

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
                         "conversa_continua": self.continua.isChecked(), "palmas": self.palmas_on.isChecked(),
                         "num_palmas": self.num_palmas.currentData(),
                         "exigencia_palmas": round(self.exig_palmas.value(), 2)},
            "rotina_palmas": {
                "frase": self.rot_frase.text().strip(),
                "apps": [a.strip() for a in self.rot_apps.text().split(",") if a.strip()],
                "sites": [a.strip() for a in self.rot_sites.text().split(",") if a.strip()],
                "musica": self.rot_musica.text().strip(), "ouvir_depois": self.rot_ouvir.isChecked()},
            "ouvido": {"sensibilidade": round(self.sens.value(), 2), "modelo_whisper": self.whisper.currentData()},
            "cerebro": {"modelo": self.modelo.currentText().strip(), "url": self.url.text().strip(),
                        "temperatura": round(self.temp.value(), 2), "max_historico": self.hist.value()},
            "atalhos_rapidos": self.atalhos_rapidos.isChecked(),
            "interface": {"paleta": self.paleta, "cor_personalizada": self.cor_custom,
                          "orbe_tamanho": self.tam_orbe.value(), "legenda": self.legenda.isChecked()},
        })
        self.aviso.setText("// CONFIGURAÇÃO SALVA ✓")
        self.salvo.emit()
