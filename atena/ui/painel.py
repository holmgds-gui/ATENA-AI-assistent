"""Painel de configurações da ATENA (abre pelo botão direito no orbe ou pela bandeja)."""
from __future__ import annotations

import threading
import time

from PySide6.QtCore import Qt, Signal
from PySide6.QtWidgets import (QApplication, QCheckBox, QComboBox, QDoubleSpinBox, QFormLayout, QFrame, QGridLayout,
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


class BotaoIcone(QPushButton):
    """Botão redondo com ícone desenhado (tela Início)."""

    def __init__(self, icone: str, dica: str, parent=None):
        super().__init__(parent)
        self.icone = icone
        self.setToolTip(dica)
        self.setFixedSize(58, 58)
        self.setCursor(Qt.PointingHandCursor)
        self.setStyleSheet("QPushButton { border-radius: 29px; padding: 0; }")

    def paintEvent(self, ev):
        super().paintEvent(ev)
        from PySide6.QtCore import QRectF
        from PySide6.QtGui import QColor, QPainter
        from . import icones
        p = QPainter(self)
        p.setRenderHint(QPainter.Antialiasing)
        icones.desenhar(p, self.icone, QRectF(17, 17, 24, 24), QColor(tema.TEXTO), 1.8)
        p.end()


# (ícone, nome por extenso)
PAGINAS = [("inicio", "Início"), ("conversa", "Conversa"), ("sistema", "Monitor do sistema"),
           ("habilidades", "Habilidades aprendidas"), ("rotinas", "Rotinas agendadas"),
           ("celular", "Celular · Telegram"), ("personalidade", "Personalidade"), ("permissoes", "Permissões"),
           ("aparencia", "Aparência"), ("voz", "Voz e ativação"), ("cerebro", "Cérebro (IA)"),
           ("memoria", "Memória"), ("sobre", "Sobre a ATENA")]
LARGURA_FECHADA, LARGURA_ABERTA = 64, 272


class ItemBarra(QWidget):
    """Item da barra lateral: ícone sempre visível + nome completo quando a barra abre."""
    clicado = Signal()

    def __init__(self, icone: str, texto: str, parent=None):
        super().__init__(parent)
        self.icone, self.texto = icone, texto
        self.ativo = False
        self._hover = False
        self.aberta = 0.0  # 0 = só ícone, 1 = com nome
        self.setFixedHeight(44)
        self.setCursor(Qt.PointingHandCursor)
        self.setAttribute(Qt.WA_Hover, True)
        self.setToolTip(texto)

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
        from PySide6.QtCore import QRectF
        from PySide6.QtGui import QColor, QLinearGradient, QPainter
        from . import icones
        from .hud import caminho_chanfrado, fonte
        d = tema.DESTAQUE
        p = QPainter(self)
        p.setRenderHint(QPainter.Antialiasing)
        r = QRectF(self.rect()).adjusted(8, 3, -8, -3)
        if self.ativo or self._hover:
            g = QLinearGradient(r.left(), 0, r.right(), 0)
            g.setColorAt(0, tema.cor(d, 0.30 if self.ativo else 0.12))
            g.setColorAt(1, tema.cor(d, 0.02))
            p.fillPath(caminho_chanfrado(r, 7), g)
        if self.ativo:
            p.fillRect(QRectF(0, r.top() + 6, 3, r.height() - 12), tema.cor(d, 1))
        cor_ic = QColor("#FFFFFF") if self.ativo else (QColor(tema.TEXTO) if self._hover else QColor(tema.APAGADO))
        icones.desenhar(p, self.icone, QRectF(r.left() + 10, r.center().y() - 11, 22, 22), cor_ic)
        if self.aberta > 0.05:
            p.setOpacity(min(1.0, self.aberta * 1.4))
            from PySide6.QtGui import QFont
            p.setFont(fonte("Rajdhani", 11.5, QFont.Bold, 1.2))
            p.setPen(cor_ic)
            p.drawText(QRectF(r.left() + 44, r.top(), r.width() - 48, r.height()), Qt.AlignVCenter, self.texto.upper())
        p.end()


class RotuloStatus(QWidget):
    """Status do salvamento: '// SALVO ✓' com a barra aberta, só '✓' com ela fechada."""

    def __init__(self):
        super().__init__()
        self._texto = ""
        self.curto = True
        self.setFixedHeight(22)

    def setText(self, t: str):
        self._texto = t
        self.update()

    def text(self) -> str:
        return self._texto

    def paintEvent(self, _):
        from PySide6.QtGui import QPainter
        from .hud import fonte
        if not self._texto:
            return
        p = QPainter(self)
        p.setFont(fonte("Share Tech Mono", 8.5, espacamento=1.5))
        p.setPen(tema.cor(tema.DESTAQUE, 0.9))
        t = self._texto
        if self.curto:
            t = "✓" if "✓" in t else "…"
        p.drawText(self.rect(), Qt.AlignCenter, t)
        p.end()


class BarraLateral(QWidget):
    """Barra recolhível: fechada mostra só ícones; o botão de cima abre com os nomes completos."""
    escolheu = Signal(int)

    def __init__(self, parent=None):
        super().__init__(parent)
        from PySide6.QtCore import QEasingCurve, QPropertyAnimation
        self.setFixedWidth(LARGURA_FECHADA)
        self.aberta = False
        lay = QVBoxLayout(self)
        lay.setContentsMargins(0, 10, 0, 12)
        lay.setSpacing(2)
        self.botao = ItemBarra("menu", "Recolher menu")
        self.botao.setToolTip("Abrir/fechar menu")
        self.botao.clicado.connect(self.alternar)
        lay.addWidget(self.botao)
        lay.addSpacing(10)
        self.itens = []
        for i, (ic, nome) in enumerate(PAGINAS):
            it = ItemBarra(ic, nome)
            it.clicado.connect(lambda i=i: self.escolheu.emit(i))
            lay.addWidget(it)
            self.itens.append(it)
        lay.addStretch(1)
        self.status = RotuloStatus()
        lay.addWidget(self.status)
        self._anim_min = QPropertyAnimation(self, b"minimumWidth", self)
        self._anim_max = QPropertyAnimation(self, b"maximumWidth", self)
        for a in (self._anim_min, self._anim_max):
            a.setDuration(260)
            a.setEasingCurve(QEasingCurve.OutCubic)
        self._anim_max.valueChanged.connect(self._ao_animar)

    def _ao_animar(self, v):
        frac = (v - LARGURA_FECHADA) / (LARGURA_ABERTA - LARGURA_FECHADA)
        self.status.curto = frac < 0.6
        self.status.update()
        for it in [self.botao] + self.itens:
            it.aberta = max(0.0, min(1.0, frac))
            it.update()

    def alternar(self):
        self.aberta = not self.aberta
        self.botao.icone = "fechar_menu" if self.aberta else "menu"
        alvo = LARGURA_ABERTA if self.aberta else LARGURA_FECHADA
        for a in (self._anim_min, self._anim_max):
            a.stop()
            a.setStartValue(self.width())
            a.setEndValue(alvo)
            a.start()

    def marcar(self, i: int):
        for k, it in enumerate(self.itens):
            it.ativo = k == i
            it.update()

    def paintEvent(self, _):
        from PySide6.QtGui import QPainter
        p = QPainter(self)
        p.fillRect(self.rect(), tema.cor("#000000", 0.35))
        p.setPen(tema.cor(tema.DESTAQUE, 0.28))
        p.drawLine(self.width() - 1, 0, self.width() - 1, self.height())
        p.end()


class Painel(FundoHud):
    salvo = Signal()
    cores_mudaram = Signal(str, str)
    rever_apresentacao = Signal()
    enviar_texto = Signal(str)
    alternar_microfone = Signal()
    chamar = Signal()
    _modelos_prontos = Signal(list)
    _status_cerebro = Signal(bool)
    _atualizacao = Signal(object)
    _progresso_att = Signal(str)
    _sair_para_atualizar = Signal()

    def __init__(self, config, cerebro=None, assistente=None):
        super().__init__()
        self.config = config
        self.cerebro = cerebro
        self.assistente = assistente
        self.setObjectName("janela")
        self.setWindowTitle(config.nome_ia)
        self.resize(1100, 760)
        self.setMinimumSize(820, 600)
        self._carregando = True

        raiz = QHBoxLayout(self)
        raiz.setContentsMargins(0, 0, 0, 0)
        raiz.setSpacing(0)
        self.barra = BarraLateral()
        self.barra.escolheu.connect(self.ir_para)
        raiz.addWidget(self.barra)

        direita = QVBoxLayout()
        direita.setContentsMargins(0, 0, 0, 0)
        direita.setSpacing(0)
        # ---- cabeçalho (some na tela Início, pra ela ficar limpa)
        self.cabecalho = QWidget()
        self.cabecalho.setObjectName("transparente")
        cab = QHBoxLayout(self.cabecalho)
        cab.setContentsMargins(22, 12, 22, 10)
        self.titulo_pagina = QLabel("")
        self.titulo_pagina.setObjectName("titulo")
        self.titulo_pagina.setStyleSheet("font-size: 21px;")
        from PySide6.QtWidgets import QSizePolicy
        self.titulo_pagina.setSizePolicy(QSizePolicy.Ignored, QSizePolicy.Preferred)
        cab.addWidget(self.titulo_pagina)
        cab.addStretch(1)
        self.ind_cerebro = Indicador("Cérebro: verificando")
        self.ind_cerebro.set(None, "Cérebro: verificando")
        cab.addWidget(self.ind_cerebro)
        self.relogio = QLabel("")
        self.relogio.setStyleSheet(f"font-family:{tema.FONTE_MONO}; font-size:18px; color:{tema.DESTAQUE};"
                                   f"padding-left:10px;")
        cab.addWidget(self.relogio)
        direita.addWidget(self.cabecalho)

        self.paginas = QStackedWidget()
        from .aba_sistema import AbaSistema
        self.aba_sistema = AbaSistema()
        self.aviso = self.barra.status
        for w in (self._aba_inicio(), self._aba_conversa(), self.aba_sistema, self._aba_habilidades(),
                  self._aba_rotinas(), self._aba_celular(), self._aba_personalidade(), self._aba_permissoes(),
                  self._aba_aparencia(), self._aba_voz_ouvido(), self._aba_cerebro(), self._aba_memoria(),
                  self._aba_sobre()):
            if w is not self.paginas.widget(0):
                self.paginas.addWidget(w)
        margem = QHBoxLayout()
        margem.setContentsMargins(14, 0, 14, 0)
        margem.addWidget(self.paginas)
        direita.addLayout(margem, 1)
        raiz.addLayout(direita, 1)

        from PySide6.QtCore import QTimer
        self._timer_salvar = QTimer(self, singleShot=True, timeout=self._salvar)
        self._ligar_salvamento_automatico()
        self._relogio_timer = QTimer(self, timeout=self._tique)
        self._relogio_timer.start(1000)
        self._tique()
        self._status_cerebro.connect(lambda ok: self.ind_cerebro.set(ok, "Cérebro online" if ok else "Cérebro offline"))
        self._atual = 0
        self.ir_para(0, animar=False)
        self._carregando = False

    # ---------------------------------------------------------------- tela inicial (limpa)
    def _aba_inicio(self):
        from .holograma import criar_orbe
        w = QWidget()
        w.setObjectName("transparente")
        lay = QVBoxLayout(w)
        lay.setContentsMargins(0, 18, 0, 22)
        lay.setSpacing(6)
        # aviso de versão nova (fica escondido até existir uma)
        self.b_atualizar = QPushButton("")
        self.b_atualizar.setObjectName("primario")
        self.b_atualizar.setCursor(Qt.PointingHandCursor)
        self.b_atualizar.setMinimumHeight(40)
        self.b_atualizar.hide()
        self.b_atualizar.clicked.connect(self._atualizar_agora)
        lay.addWidget(self.b_atualizar, 0, Qt.AlignHCenter)
        self._info_att = None
        self._atualizacao.connect(self._mostrar_atualizacao)
        self._progresso_att.connect(self.b_atualizar.setText)
        self._sair_para_atualizar.connect(lambda: QApplication.instance().quit())
        threading.Thread(target=self._checar_atualizacao, daemon=True).start()
        # aviso: cérebro rodando no processador (lento)
        self.b_gpu = QPushButton("  ⚠  O CÉREBRO ESTÁ USANDO O PROCESSADOR (LENTO) — TOQUE PRA RESOLVER  ")
        self.b_gpu.setObjectName("perigo")
        self.b_gpu.setCursor(Qt.PointingHandCursor)
        self.b_gpu.setMinimumHeight(38)
        self.b_gpu.hide()
        self.b_gpu.clicked.connect(self._explicar_gpu)
        lay.addWidget(self.b_gpu, 0, Qt.AlignHCenter)
        from PySide6.QtCore import QTimer
        self._t_gpu = QTimer(self)
        self._t_gpu.timeout.connect(self._checar_gpu)
        self._t_gpu.start(5000)
        lay.addStretch(1)
        self.orbe_inicio = criar_orbe(430, *tema.cores_da_config(self.config))
        lay.addWidget(self.orbe_inicio, 0, Qt.AlignHCenter)
        self.estado_inicio = QLabel("// EM ESPERA")
        self.estado_inicio.setObjectName("secao")
        self.estado_inicio.setAlignment(Qt.AlignHCenter)
        lay.addWidget(self.estado_inicio)
        self.fala_inicio = QLabel(f"Diga “{self.config.nome_ia.capitalize()}” ou bata duas palmas.")
        self.fala_inicio.setWordWrap(True)
        self.fala_inicio.setAlignment(Qt.AlignHCenter)
        self.fala_inicio.setMinimumHeight(64)
        self.fala_inicio.setStyleSheet(f"font-size: 21px; color: {tema.TEXTO}; padding: 0 60px;")
        lay.addWidget(self.fala_inicio)
        lay.addStretch(1)
        # poucos botões: microfone, digitar, chamar, configurações
        linha = QHBoxLayout()
        linha.setSpacing(14)
        linha.addStretch(1)
        self.b_mic = BotaoIcone("voz", "Microfone ligado")
        self.b_mic.clicked.connect(self.alternar_microfone.emit)
        self.b_chamar = BotaoIcone("chamar", "Chamar a ATENA")
        self.b_chamar.clicked.connect(self.chamar.emit)
        self.b_digitar = BotaoIcone("teclado", "Digitar um pedido")
        self.b_digitar.clicked.connect(self._mostrar_digitar)
        self.b_config = BotaoIcone("engrenagem", "Configurações")
        self.b_config.clicked.connect(lambda: (self.barra.aberta or self.barra.alternar()))
        for b in (self.b_mic, self.b_chamar, self.b_digitar, self.b_config):
            linha.addWidget(b)
        linha.addStretch(1)
        lay.addLayout(linha)
        self.digitar_inicio = QLineEdit()
        self.digitar_inicio.setPlaceholderText("› digite e aperte Enter…")
        self.digitar_inicio.setMaximumWidth(560)
        self.digitar_inicio.setMinimumHeight(42)
        self.digitar_inicio.returnPressed.connect(self._enviar_inicio)
        self.digitar_inicio.hide()
        lay.addWidget(self.digitar_inicio, 0, Qt.AlignHCenter)
        self.paginas.addWidget(w)
        return w

    # ---------------------------------------------------------------- placa de vídeo
    def _checar_gpu(self):
        baixando = getattr(self.cerebro, "baixando_rapido", None)
        if baixando:
            self.b_gpu.setObjectName("primario")
            self.b_gpu.setText(f"  ⬇  BAIXANDO A VERSÃO RÁPIDA DO CÉREBRO… {baixando}  ")
            self.b_gpu.setEnabled(False)
            self.b_gpu.style().polish(self.b_gpu)
            self.b_gpu.show()
            return
        est = getattr(self.cerebro, "estado_gpu", None) or {}
        self.b_gpu.setObjectName("perigo")
        self.b_gpu.setText("  ⚠  O CÉREBRO ESTÁ USANDO O PROCESSADOR (LENTO) — TOQUE PRA RESOLVER  ")
        self.b_gpu.setEnabled(True)
        self.b_gpu.style().polish(self.b_gpu)
        self.b_gpu.setVisible(est.get("na_gpu") is False)

    def _explicar_gpu(self):
        from PySide6.QtWidgets import QMessageBox
        est = getattr(self.cerebro, "estado_gpu", None) or {}
        vel = getattr(self.cerebro, "ultima_velocidade", 0) or 0
        QMessageBox.information(self, "Deixar a ATENA rápida", (
            f"O modelo está só {est.get('porcentagem_gpu', 0)}% na placa de vídeo"
            + (f" (escrevendo a {vel:.0f} palavras/s)" if vel else "") + ".\n"
            "No processador ela demora 10–40 s pra responder; na placa, 1–3 s.\n\n"
            "Como resolver (tudo grátis):\n"
            "1. Atualize o Ollama: baixe de novo em ollama.com e instale por cima. "
            "As versões novas usam a placa AMD sozinhas (Vulkan).\n"
            "2. Atualize o driver da AMD pelo app AMD Software: Adrenalin.\n"
            "3. Reinicie o PC e abra a ATENA de novo.\n\n"
            "Se continuar: na aba Cérebro (IA) troque pra um modelo menor (qwen3-vl:4b-instruct ou 2b)."))

    # ---------------------------------------------------------------- atualização automática
    def _checar_atualizacao(self):
        time.sleep(4)
        try:
            from .. import atualizador
            info = atualizador.verificar()
        except Exception as e:
            print(f"[atualizar] não deu pra checar: {e}")
            return
        if info:
            self._atualizacao.emit(info)

    def _mostrar_atualizacao(self, info):
        self._info_att = info
        self.b_atualizar.setText(f"  ▲  NOVA VERSÃO {info['versao']} — ATUALIZAR AGORA  ")
        self.b_atualizar.setEnabled(True)
        self.b_atualizar.show()

    def _atualizar_agora(self):
        info = self._info_att
        if not info:
            return
        self.b_atualizar.setEnabled(False)
        self.b_atualizar.setText("  BAIXANDO…  ")

        def trabalho():
            from .. import atualizador
            try:
                caminho = atualizador.baixar(
                    info, lambda f: self._progresso_att.emit(f"  BAIXANDO… {int(f * 100)}%  "))
                self._progresso_att.emit("  INSTALANDO — A ATENA VAI REABRIR SOZINHA  ")
                atualizador.instalar(caminho)
                time.sleep(1.5)
                self._sair_para_atualizar.emit()
            except Exception as e:
                print(f"[atualizar] falhou: {e}")
                self._atualizacao.emit(info)
                self._progresso_att.emit("  FALHOU — TOQUE PARA TENTAR DE NOVO  ")

        threading.Thread(target=trabalho, daemon=True).start()

    def _mostrar_digitar(self):
        self.digitar_inicio.setVisible(not self.digitar_inicio.isVisible())
        if self.digitar_inicio.isVisible():
            self.digitar_inicio.setFocus()

    def _enviar_inicio(self):
        t = self.digitar_inicio.text().strip()
        if t:
            self.digitar_inicio.clear()
            self.enviar_texto.emit(t)

    _ROTULO_ESTADO = {"dormindo": "// EM ESPERA", "ouvindo": "// OUVINDO", "pensando": "// PROCESSANDO",
                      "falando": "// TRANSMITINDO", "mudo": "// MICROFONE DESLIGADO", "erro": "// FALHA"}

    def mostrar_estado(self, estado: str):
        self.orbe_inicio.set_estado(estado)
        self.estado_inicio.setText(self._ROTULO_ESTADO.get(estado, ""))
        self.b_mic.icone = "microfone_off" if estado == "mudo" else "voz"
        self.b_mic.setToolTip("Microfone desligado" if estado == "mudo" else "Microfone ligado")
        self.b_mic.update()

    def mostrar_fala(self, de_quem: str, texto: str):
        if de_quem == "atena":
            self.fala_inicio.setStyleSheet(f"font-size: 21px; color: {tema.TEXTO}; padding: 0 60px;")
            self.fala_inicio.setText(texto)
        elif de_quem == "voce":
            self.fala_inicio.setStyleSheet(f"font-size: 19px; color: {tema.APAGADO}; padding: 0 60px;")
            self.fala_inicio.setText(f"“{texto}”")
        elif de_quem == "acao":
            self.estado_inicio.setText("// " + texto.replace("▸", "").strip().upper())

    def resizeEvent(self, ev):
        super().resizeEvent(ev)
        if hasattr(self, "orbe_inicio"):
            lado = int(max(240, min(self.width() - 140, self.height() - 290, 560)))
            if abs(self.orbe_inicio.width() - lado) > 8:
                self.orbe_inicio.setFixedSize(lado, lado)

    # ---------------------------------------------------------------- navegação com transição suave
    def ir_para(self, i: int, animar: bool = True):
        from PySide6.QtCore import QEasingCurve, QParallelAnimationGroup, QPoint, QPropertyAnimation
        from PySide6.QtWidgets import QGraphicsOpacityEffect
        anterior = self.paginas.currentWidget()
        if animar and anterior is not None and i != self.paginas.currentIndex() and self.isVisible():
            foto = QLabel(self.paginas)  # "foto" da página antiga some enquanto a nova desliza
            foto.setPixmap(anterior.grab())
            foto.setGeometry(anterior.geometry())
            efeito = QGraphicsOpacityEffect(foto)
            foto.setGraphicsEffect(efeito)
            foto.show()
            foto.raise_()
        else:
            foto = None
        self.paginas.setCurrentIndex(i)
        self._atual = i
        self.barra.marcar(i)
        ic, nome = PAGINAS[i]
        self.cabecalho.setVisible(ic != "inicio")
        self.titulo_pagina.setText(nome.upper())
        if foto is not None:
            novo = self.paginas.currentWidget()
            grupo = QParallelAnimationGroup(self)
            a1 = QPropertyAnimation(efeito, b"opacity")
            a1.setDuration(240)
            a1.setStartValue(1.0)
            a1.setEndValue(0.0)
            a2 = QPropertyAnimation(novo, b"pos")
            a2.setDuration(280)
            a2.setStartValue(QPoint(28, 0))
            a2.setEndValue(QPoint(0, 0))
            for a in (a1, a2):
                a.setEasingCurve(QEasingCurve.OutCubic)
                grupo.addAnimation(a)
            grupo.finished.connect(foto.deleteLater)
            grupo.start()
            self._anim_pagina = grupo
        if ic == "habilidades":
            self._carregar_hab()
        elif ic == "rotinas":
            self._carregar_rot()
        if ic == "sistema" and self.isVisible():
            self.aba_sistema.iniciar()
        else:
            self.aba_sistema.parar()

    def _tique(self):
        import datetime as _dt
        self.relogio.setText(_dt.datetime.now().strftime("%H:%M:%S"))
        self._atualizar_tg()
        if self.cerebro is not None and int(time.time()) % 10 == 0:
            threading.Thread(target=lambda: self._status_cerebro.emit(self.cerebro.esta_online()), daemon=True).start()

    def hideEvent(self, ev):
        self.aba_sistema.parar()
        super().hideEvent(ev)

    # ---------------------------------------------------------------- abrir/fechar com fade
    def abrir_animado(self):
        from PySide6.QtCore import QEasingCurve, QPropertyAnimation
        if self.isVisible() and not self.isMinimized():
            self.raise_()
            self.activateWindow()
            return
        self.setWindowOpacity(0.0)
        self.showNormal()
        self.raise_()
        self.activateWindow()
        a = QPropertyAnimation(self, b"windowOpacity", self)
        a.setDuration(260)
        a.setStartValue(0.0)
        a.setEndValue(1.0)
        a.setEasingCurve(QEasingCurve.OutCubic)
        a.start()
        self._anim_janela = a
        if hasattr(self, "orbe_inicio"):
            self.orbe_inicio.materializar()

    def closeEvent(self, ev):
        """Fechar a janela só esconde (a ATENA continua rodando na bandeja), com fade."""
        from PySide6.QtCore import QEasingCurve, QPropertyAnimation
        if getattr(self, "_fechando", False):
            self._fechando = False
            ev.accept()
            return
        ev.ignore()
        self._fechando = True
        a = QPropertyAnimation(self, b"windowOpacity", self)
        a.setDuration(200)
        a.setStartValue(self.windowOpacity())
        a.setEndValue(0.0)
        a.setEasingCurve(QEasingCurve.InCubic)
        a.finished.connect(lambda: (self.hide(), self.setWindowOpacity(1.0)))
        a.finished.connect(lambda: setattr(self, "_fechando", False))
        a.start()
        self._anim_janela = a

    # ---------------------------------------------------------------- salvamento automático
    def _ligar_salvamento_automatico(self):
        from PySide6.QtWidgets import (QAbstractButton, QAbstractSlider, QAbstractSpinBox, QComboBox,
                                       QLineEdit, QPlainTextEdit)
        ignorar = {getattr(self, n, None) for n in ("entrada", "digitar_inicio", "rot_pedido", "tg_token",
                                                     "rot_hora", "rot_rep")}
        for w in self.findChildren(QWidget):
            if w in ignorar:
                continue
            if isinstance(w, QLineEdit) and not isinstance(w.parent(), QAbstractSpinBox):
                w.textEdited.connect(self._agendar_salvar)
            elif isinstance(w, QPlainTextEdit):
                w.textChanged.connect(self._agendar_salvar)
            elif isinstance(w, QAbstractButton) and w.isCheckable():
                w.toggled.connect(self._agendar_salvar)
            elif isinstance(w, QComboBox):
                w.currentIndexChanged.connect(self._agendar_salvar)
                if w.isEditable():
                    w.editTextChanged.connect(self._agendar_salvar)
            elif isinstance(w, QAbstractSlider):
                w.valueChanged.connect(self._agendar_salvar)
            elif isinstance(w, QAbstractSpinBox) and hasattr(w, "valueChanged"):
                w.valueChanged.connect(self._agendar_salvar)

    def _agendar_salvar(self, *_):
        if not self._carregando:
            self.aviso.setText("// SALVANDO…")
            self._timer_salvar.start(700)

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

    # ---------------- habilidades
    def _aba_habilidades(self):
        w = QWidget()
        lay = QVBoxLayout(w)
        lay.setContentsMargins(0, 0, 0, 0)
        lay.setSpacing(10)
        dica = QLabel("Rotinas que a ATENA aprendeu. Depois de uma tarefa com vários passos ela pergunta se quer "
                      "salvar, ou você pede direto: <i>“Atena, cria a habilidade modo estudo que abre o Notion e toca "
                      "lo-fi”</i>. Pra usar, é só falar o nome.")
        dica.setObjectName("subtitulo")
        dica.setWordWrap(True)
        lay.addWidget(dica)
        self.lista_hab = QListWidget()
        self.lista_hab.setMinimumHeight(340)
        self.lista_hab.setWordWrap(True)
        lay.addWidget(self.lista_hab)
        h = QHBoxLayout()
        b1 = QPushButton("▶ RODAR")
        b1.clicked.connect(self._rodar_hab)
        b2 = QPushButton("APAGAR")
        b2.clicked.connect(self._apagar_hab)
        h.addWidget(b1)
        h.addWidget(b2)
        h.addStretch(1)
        lay.addLayout(h)
        return _rolavel(w, "Habilidades aprendidas")

    def _carregar_hab(self):
        if not hasattr(self, "lista_hab"):
            return
        from ..habilidades import Habilidades, descrever_passos
        from ..config import PASTA_USUARIO
        hab = self.assistente.habilidades if self.assistente else Habilidades(PASTA_USUARIO)
        hab.carregar()
        self.lista_hab.clear()
        for h in hab.lista:
            self.lista_hab.addItem(f"{h['nome'].upper()}   ·   {descrever_passos(h['passos'])}   ·   usada {h.get('usos', 0)}x")
            self.lista_hab.item(self.lista_hab.count() - 1).setData(Qt.UserRole, h["nome"])
        if not hab.lista:
            self.lista_hab.addItem("Nenhuma habilidade ainda.")

    def _rodar_hab(self):
        it = self.lista_hab.currentItem()
        if it and it.data(Qt.UserRole) and self.assistente:
            self.assistente.enviar_texto(it.data(Qt.UserRole))

    def _apagar_hab(self):
        it = self.lista_hab.currentItem()
        if it and it.data(Qt.UserRole) and self.assistente:
            self.assistente.habilidades.apagar(it.data(Qt.UserRole))
            self._carregar_hab()

    # ---------------- rotinas agendadas
    def _aba_rotinas(self):
        from PySide6.QtCore import QTime
        from PySide6.QtWidgets import QTimeEdit
        w = QWidget()
        lay = QVBoxLayout(w)
        lay.setContentsMargins(0, 0, 0, 0)
        lay.setSpacing(10)
        dica = QLabel("Coisas que ela faz sozinha no horário. Também dá pra pedir por voz: "
                      "<i>“Atena, todo dia às 7 me dá o resumo do dia”</i>.")
        dica.setObjectName("subtitulo")
        dica.setWordWrap(True)
        lay.addWidget(dica)
        self.lista_rot = QListWidget()
        self.lista_rot.setMinimumHeight(240)
        lay.addWidget(self.lista_rot)
        lay.addWidget(_secao("Nova rotina"))
        form = QFormLayout()
        self.rot_hora = QTimeEdit(QTime(7, 0))
        self.rot_hora.setDisplayFormat("HH:mm")
        form.addRow("Horário", self.rot_hora)
        self.rot_rep = QComboBox()
        for chave, nome in (("todo_dia", "Todo dia"), ("dias_uteis", "Dias úteis (seg–sex)"),
                            ("fim_de_semana", "Fim de semana"), ("nao", "Só uma vez")):
            self.rot_rep.addItem(nome, chave)
        form.addRow("Repetir", self.rot_rep)
        self.rot_pedido = QLineEdit()
        self.rot_pedido.setPlaceholderText("o que ela deve fazer, ex: me dá o resumo do dia  /  modo estudo")
        form.addRow("Pedido", self.rot_pedido)
        lay.addLayout(form)
        h = QHBoxLayout()
        add = QPushButton("+ ADICIONAR")
        add.setObjectName("primario")
        add.clicked.connect(self._add_rotina)
        rem = QPushButton("APAGAR SELECIONADA")
        rem.clicked.connect(self._apagar_rotina)
        h.addWidget(add)
        h.addWidget(rem)
        h.addStretch(1)
        lay.addLayout(h)
        return _rolavel(w, "Rotinas agendadas")

    def _agenda(self):
        if self.assistente:
            return self.assistente.agenda
        from ..agenda import Agenda
        from ..config import PASTA_USUARIO
        return Agenda(PASTA_USUARIO)

    def _carregar_rot(self):
        if not hasattr(self, "lista_rot"):
            return
        from ..agenda import descrever
        ag = self._agenda()
        self.lista_rot.clear()
        for r in ag.lista:
            if r.get("ativa", True):
                self.lista_rot.addItem(f"⏰  {descrever(r)}")
                self.lista_rot.item(self.lista_rot.count() - 1).setData(Qt.UserRole, r["id"])
        if not self.lista_rot.count():
            self.lista_rot.addItem("Nenhuma rotina agendada.")

    def _add_rotina(self):
        pedido = self.rot_pedido.text().strip()
        if not pedido:
            return
        rep = self.rot_rep.currentData()
        ag = self._agenda()
        hab = self.assistente.habilidades.procurar(pedido) if self.assistente else None
        ag.adicionar(self.rot_hora.time().toString("HH:mm"), pedido="" if hab else pedido,
                     habilidade=hab["nome"] if hab else "", dias="" if rep == "nao" else rep)
        self.rot_pedido.clear()
        self._carregar_rot()

    def _apagar_rotina(self):
        it = self.lista_rot.currentItem()
        if it and it.data(Qt.UserRole):
            self._agenda().cancelar(it.data(Qt.UserRole))
            self._carregar_rot()

    # ---------------- celular (Telegram)
    def _aba_celular(self):
        w = QWidget()
        lay = QVBoxLayout(w)
        lay.setContentsMargins(0, 0, 0, 0)
        lay.setSpacing(10)
        passos = QLabel(
            "Fale com a ATENA pelo <b>Telegram</b> de qualquer lugar. Ela executa no PC e responde no chat "
            "(texto ou áudio).<br><br>"
            "<b>1.</b> No Telegram, abra o <b>@BotFather</b>, mande <b>/newbot</b> e escolha um nome.<br>"
            "<b>2.</b> Ele te dá um <b>token</b> (algo como 123456:ABC…). Cole aqui embaixo e clique em CONECTAR.<br>"
            "<b>3.</b> Abra o seu bot e mande o <b>código de 6 dígitos</b> que vai aparecer aqui.<br><br>"
            "Comandos no chat: <b>/tela</b> (print da tela) · <b>/pc</b> (status) · <b>/parar</b> (pânico).")
        passos.setObjectName("subtitulo")
        passos.setWordWrap(True)
        lay.addWidget(passos)
        form = QFormLayout()
        self.tg_token = QLineEdit(self.config.get("telegram.token") or "")
        self.tg_token.setEchoMode(QLineEdit.Password)
        self.tg_token.setPlaceholderText("cole o token do @BotFather")
        form.addRow("Token do bot", self.tg_token)
        self.tg_avisar = QCheckBox("Avisar no celular quando uma rotina agendada rodar")
        self.tg_avisar.setChecked(bool(self.config.get("telegram.avisar_rotinas", True)))
        form.addRow("", self.tg_avisar)
        lay.addLayout(form)
        h = QHBoxLayout()
        con = QPushButton("CONECTAR ▸")
        con.setObjectName("primario")
        con.clicked.connect(self._conectar_tg)
        des = QPushButton("DESCONECTAR CELULAR")
        des.clicked.connect(self._desconectar_tg)
        h.addWidget(con)
        h.addWidget(des)
        h.addStretch(1)
        lay.addLayout(h)
        self.tg_status = Indicador("Telegram: desligado")
        self.tg_status.set(None, "Telegram: desligado")
        lay.addWidget(self.tg_status)
        lay.addWidget(_secao("Código de pareamento"))
        self.tg_codigo = QLabel("------")
        self.tg_codigo.setStyleSheet(f"font-family:{tema.FONTE_MONO}; font-size:42px; letter-spacing:12px;"
                                     f"color:{tema.DESTAQUE};")
        lay.addWidget(self.tg_codigo)
        return _rolavel(w, "Celular · Telegram")

    def _atualizar_tg(self):
        if not hasattr(self, "tg_status"):
            return
        tg = self.assistente.telegram if self.assistente else None
        if tg is None:
            self.tg_status.set(None, "Telegram: desligado")
            self.tg_codigo.setText("------")
            return
        self.tg_codigo.setText(tg.codigo)
        if tg.erro:
            self.tg_status.set(False, f"Telegram: {tg.erro}")
        elif tg.conectado and tg.chat:
            self.tg_status.set(True, f"Conectado ao celular via {tg.nome_bot}")
            self.tg_codigo.setText("✓ PAREADO")
        elif tg.conectado:
            self.tg_status.set(None, f"{tg.nome_bot} online · mande o código pro bot")
        else:
            self.tg_status.set(None, "Telegram: conectando…")

    def _conectar_tg(self):
        self.config.salvar_geral({"telegram": {"token": self.tg_token.text().strip(),
                                               "avisar_rotinas": self.tg_avisar.isChecked()}})
        if self.assistente:
            self.assistente.conectar_telegram()
        self.aviso.setText("// TELEGRAM CONECTANDO…")

    def _desconectar_tg(self):
        self.config.salvar_geral({"telegram": {"chat_autorizado": None}})
        if self.assistente:
            self.assistente.conectar_telegram()  # novo código de pareamento

    def _aba_personalidade(self):
        w = QWidget()
        lay = QVBoxLayout(w)
        lay.setContentsMargins(0, 0, 0, 0)
        lay.setSpacing(10)
        form = QFormLayout()
        self.nome_usuario = QLineEdit(self.config.personalidade.get("como_me_chamar", ""))
        self.nome_ia = QLineEdit(self.config.personalidade.get("nome", "ATENA"))
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
        self.paleta = self.config.get("interface.paleta", "azul")
        self.cor_custom = self.config.get("interface.cor_personalizada") or "#2E9BFF"
        from .holograma import criar_orbe
        self.preview = criar_orbe(240, *tema.cores_da_config(self.config))
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
        nota = QLabel("A cor do holograma muda na hora. A cor das janelas muda ao reabrir a ATENA.")
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
        self.orbe_inicio.set_cores(prim, sec)
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
        self.palmas_on = QCheckBox("Bater palmas chama a ATENA")
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
        self.rot_frase.setPlaceholderText("vazio = “Bem-vindo de volta, <seu nome>. Preparando tudo.”")
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
        for t, d in (("tiny", "tiny — instantâneo, erra muito"), ("base", "base — rápido, erra nomes"),
                     ("small", "small — preciso (recomendado)"), ("medium", "medium — o mais preciso, lento")):
            self.whisper.addItem(d, t)
        self.whisper.setCurrentIndex(max(0, self.whisper.findData(self.config.get("ouvido.modelo_whisper", "small"))))
        form.addRow("Reconhecimento de fala", self.whisper)
        self.atalhos_rapidos = QCheckBox("Comandos rápidos sem IA (abrir apps, horas, volume)")
        self.atalhos_rapidos.setChecked(bool(self.config.get("atalhos_rapidos", True)))
        form.addRow("", self.atalhos_rapidos)
        lay.addLayout(form)
        lay.addWidget(QLabel("Mudanças no reconhecimento de fala valem depois de reiniciar a ATENA.",
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
        self.modelo_visao = QComboBox()
        self.modelo_visao.setEditable(True)
        self.modelo_visao.addItem(self.config.get("visao.modelo", "qwen3-vl:8b-instruct"))
        form.addRow("Modelo de visão", self.modelo_visao)
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
        dica = QLabel("Recomendado: <b>qwen3-vl:8b-instruct</b> nos dois campos (pensa e enxerga, sem trocar de modelo). "
                      "Placa com 8 GB: <b>qwen3-vl:4b-instruct</b>.<br>"
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
        lay.addWidget(QLabel("Coisas que a ATENA guardou sobre você. Peça “lembra que…” pra adicionar.",
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
                       "• <b>Esc</b> enquanto ela mexe no PC = para tudo na hora (tecla de pânico).<br>"
                       "• Levar o mouse pro canto superior esquerdo também trava os cliques.<br>"
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
        if de_quem == "acao":
            html = (f'<p style="margin:2px 0 2px 14px"><span style="{mono}; color:{tema.APAGADO}">'
                    f'[{hora}] {texto}</span></p>')
        elif de_quem == "voce":
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
        for combo in (self.modelo, self.modelo_visao):
            atual = combo.currentText()
            combo.clear()
            for m in modelos:
                combo.addItem(m)
            if atual not in modelos:
                combo.addItem(atual)
            combo.setCurrentText(atual)

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
        if PAGINAS[self.paginas.currentIndex()][0] == "sistema":
            self.aba_sistema.iniciar()

    def _salvar(self):
        pers = self.sel_pers.valores()
        self.config.salvar_personalidade({
            "como_me_chamar": self.nome_usuario.text().strip(),
            "nome": self.nome_ia.text().strip() or "ATENA",
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
            "visao": {"modelo": self.modelo_visao.currentText().strip()},
            "interface": {"paleta": self.paleta, "cor_personalizada": self.cor_custom,
                          "orbe_tamanho": self.tam_orbe.value(), "legenda": self.legenda.isChecked()},
        })
        self.aviso.setText("// SALVO ✓")
        self.salvo.emit()
