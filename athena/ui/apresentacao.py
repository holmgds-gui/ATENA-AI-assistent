"""Apresentação da 1ª vez: carrossel explicando a ATHENA + configuração (nome, personalidade,
permissões e voz). Mesmo esquema do Muscle Atlas: barrinhas no topo, 'Pular', Voltar/Próximo.
"""
from __future__ import annotations

import threading

from PySide6.QtCore import QEasingCurve, QPoint, QPropertyAnimation, Qt, QTimer, Signal
from PySide6.QtWidgets import (QDialog, QFrame, QHBoxLayout, QLabel, QLineEdit, QPushButton, QScrollArea,
                               QStackedWidget, QVBoxLayout, QWidget)

from . import tema
from .componentes import ListaPermissoes, SeletorPersonalidade, SeletorVoz
from .orbe import Orbe


def _rotulo(texto, nome="subtitulo", wrap=True, centro=True):
    l = QLabel(texto)
    l.setObjectName(nome)
    l.setWordWrap(wrap)
    l.setTextFormat(Qt.RichText)
    if centro:
        l.setAlignment(Qt.AlignHCenter)
    return l


def _balao(texto, de_quem="voce"):
    l = QLabel(texto)
    l.setWordWrap(True)
    if de_quem == "voce":
        l.setStyleSheet(f"background:{tema.SUPERFICIE_2}; border:1px solid {tema.LINHA}; border-radius:14px;"
                        f"padding:10px 14px; font-size:14.5px;")
    else:
        l.setStyleSheet(f"background:{tema.FUNDO_SEL}; border:1px solid {tema.DESTAQUE}; border-radius:14px;"
                        f"padding:10px 14px; font-size:14.5px; color:{tema.TEXTO};")
    linha = QHBoxLayout()
    if de_quem == "voce":
        linha.addStretch(1)
        linha.addWidget(l, 4)
    else:
        linha.addWidget(l, 4)
        linha.addStretch(1)
    return linha


class Pagina(QWidget):
    """Uma tela do carrossel (com rolagem se precisar)."""

    def __init__(self, titulo: str, texto: str = "", centralizar=True):
        super().__init__()
        externo = QVBoxLayout(self)
        externo.setContentsMargins(0, 0, 0, 0)
        area = QScrollArea()
        area.setWidgetResizable(True)
        area.setFrameShape(QFrame.NoFrame)
        area.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        conteudo = QWidget()
        self.lay = QVBoxLayout(conteudo)
        self.lay.setContentsMargins(28, 10, 28, 10)
        self.lay.setSpacing(14)
        if centralizar:
            self.lay.addStretch(1)
        t = _rotulo(titulo, "titulo")
        self.lay.addWidget(t)
        if texto:
            self.lay.addWidget(_rotulo(texto))
        self._centralizar = centralizar
        area.setWidget(conteudo)
        externo.addWidget(area)

    def fechar(self):
        self.lay.addStretch(1)


class Apresentacao(QDialog):
    concluido = Signal()

    def __init__(self, config, so_carrossel: bool = False, parent=None):
        super().__init__(parent)
        self.config = config
        self.so_carrossel = so_carrossel
        self.setObjectName("janela")
        self.setWindowTitle("Bem-vindo à ATHENA")
        self.setFixedSize(480, 760)

        raiz = QVBoxLayout(self)
        raiz.setContentsMargins(0, 0, 0, 0)
        raiz.setSpacing(0)

        # ---- topo: barrinhas de progresso + Pular
        topo = QHBoxLayout()
        topo.setContentsMargins(20, 16, 14, 6)
        self.barras_lay = QHBoxLayout()
        self.barras_lay.setSpacing(4)
        topo.addLayout(self.barras_lay, 1)
        self.pular = QPushButton("Pular")
        self.pular.setObjectName("link")
        self.pular.clicked.connect(self._pular)
        topo.addWidget(self.pular)
        raiz.addLayout(topo)

        # ---- páginas
        self.pilha = QStackedWidget()
        raiz.addWidget(self.pilha, 1)
        self._montar_paginas()

        # ---- rodapé: Voltar / Próximo
        rod = QHBoxLayout()
        rod.setContentsMargins(20, 8, 20, 18)
        self.voltar = QPushButton("Voltar")
        self.voltar.clicked.connect(lambda: self.ir(self.pilha.currentIndex() - 1))
        self.proximo = QPushButton("Próximo")
        self.proximo.setObjectName("primario")
        self.proximo.setMinimumHeight(48)
        self.voltar.setMinimumHeight(48)
        self.proximo.clicked.connect(self._avancar)
        rod.addWidget(self.voltar)
        rod.addWidget(self.proximo, 1)
        raiz.addLayout(rod)

        self.barras = []
        for _ in range(self.pilha.count()):
            b = QFrame()
            b.setFixedHeight(4)
            self.barras.append(b)
            self.barras_lay.addWidget(b)
        self.ir(0, animar=False)

    # ------------------------------------------------------------------ páginas
    def _montar_paginas(self):
        cfg = self.config
        # 1. boas-vindas
        p = Pagina("", "")
        p.lay.takeAt(p.lay.count() - 1).widget().deleteLater()  # tira o título vazio
        orbe = Orbe(210, *tema.cores_da_config(cfg))
        p.lay.addWidget(orbe, 0, Qt.AlignHCenter)
        marca = QLabel(f'<span style="letter-spacing:6px">ATHE<span style="color:{tema.DESTAQUE}">NA</span></span>')
        marca.setAlignment(Qt.AlignHCenter)
        marca.setStyleSheet(f"font-family:{tema.FONTE_TITULO}; font-size:40px; font-weight:800;")
        p.lay.addWidget(marca)
        p.lay.addWidget(_rotulo("Assistente Tecnológica de Execução<br>e Navegação Artificial", "apagado"))
        p.lay.addWidget(_rotulo("Sua assistente de voz que <b>conversa</b>, <b>pesquisa</b> e <b>mexe no seu PC</b> "
                                "por você. Igual ao JARVIS, só que sua."))
        p.fechar()
        self.pilha.addWidget(p)

        # 2. como chamar
        p = Pagina("É só chamar", "Fale <b>“Atena”</b> e peça o que quiser, numa frase só. "
                                  "Também dá pra clicar duas vezes no orbe ou usar o atalho <b>Ctrl+Alt+A</b>.")
        for txt, quem in (("Atena, abre o Spotify", "voce"), ("Abrindo o Spotify.", "athena"),
                          ("Atena, quanto tá o dólar hoje?", "voce"),
                          ("Pesquisei aqui: o dólar está em…", "athena"),
                          ("Atena, me lembra de beber água em 30 minutos", "voce"),
                          ("Timer criado. Hidratação também é eficiência.", "athena")):
            p.lay.addLayout(_balao(txt, quem))
        p.lay.addWidget(_rotulo("Depois que ela responde, continua ouvindo por alguns segundos, "
                                "então dá pra emendar outro pedido sem chamar de novo.", "apagado"))
        p.fechar()
        self.pilha.addWidget(p)

        # 3. o que ela faz
        p = Pagina("O que ela sabe fazer", "")
        for titulo, desc in (("Abrir apps e sites", "“abre o Discord”, “entra no Gmail”"),
                             ("Pesquisar e responder", "notícias, preços, clima, dúvidas"),
                             ("Tocar música e vídeo", "“toca lo-fi no YouTube”, “próxima”"),
                             ("Escrever por você", "digita textos e aperta atalhos no app aberto"),
                             ("Controlar o PC", "volume, bloquear a tela, desligar"),
                             ("Notas, timers e memória", "anota, avisa e lembra do que você contou")):
            c = QFrame()
            c.setObjectName("cartao")
            v = QVBoxLayout(c)
            v.setContentsMargins(14, 10, 14, 10)
            v.setSpacing(1)
            a = QLabel(f'<span style="color:{tema.DESTAQUE}">●</span>&nbsp;&nbsp;<b>{titulo}</b>')
            a.setStyleSheet("background:transparent;")
            b = QLabel(desc)
            b.setObjectName("apagado")
            b.setStyleSheet("background:transparent; padding-left: 20px;")
            v.addWidget(a)
            v.addWidget(b)
            p.lay.addWidget(c)
        p.fechar()
        self.pilha.addWidget(p)

        # 4. privacidade
        p = Pagina("Roda no seu computador",
                   "O cérebro da ATHENA é uma IA <b>local</b> (Ollama): suas conversas ficam no seu PC "
                   "e não tem mensalidade.")
        for t in ("Só vai pra internet o que precisa: pesquisas e a geração da voz.",
                  "Você escolhe o que ela pode fazer no PC na tela de permissões.",
                  "Ações arriscadas (fechar programas, desligar) pedem confirmação.",
                  "Tudo pode ser mudado depois em Configurações."):
            p.lay.addWidget(_rotulo(f'<span style="color:{tema.OK}">✓</span>&nbsp; {t}', "subtitulo", centro=False))
        p.fechar()
        if not self.so_carrossel:
            self._fim_carrossel = 4
        self.pilha.addWidget(p)

        if self.so_carrossel:
            return

        # 5. nome
        p = Pagina("Primeiro, como te chamo?", "É assim que ela vai falar com você.")
        self.campo_nome = QLineEdit(cfg.personalidade.get("como_me_chamar", ""))
        self.campo_nome.setPlaceholderText("Seu nome ou apelido")
        self.campo_nome.setStyleSheet("font-size: 18px; padding: 14px;")
        self.campo_nome.textChanged.connect(self._atualizar_botoes)
        p.lay.addWidget(self.campo_nome)
        p.lay.addWidget(_rotulo("NOME DA ASSISTENTE", "secao", centro=False))
        self.campo_ia = QLineEdit(cfg.personalidade.get("nome", "ATHENA"))
        self.campo_ia.setPlaceholderText("ATHENA")
        p.lay.addWidget(self.campo_ia)
        p.lay.addWidget(_rotulo("Se mudar o nome, mude também a palavra de ativação nas Configurações.",
                                "apagado", centro=False))
        p.fechar()
        self.pilha.addWidget(p)

        # 6. personalidade
        p = Pagina("Personalidade", "Escolha um estilo ou escreva o seu.", centralizar=False)
        self.sel_pers = SeletorPersonalidade(cfg.personalidade.get("preset", "elegante_com_humor"),
                                             cfg.personalidade.get("estilo", ""))
        p.lay.addWidget(self.sel_pers)
        p.fechar()
        self.pilha.addWidget(p)

        # 7. permissões
        p = Pagina("Permissões", "O que a ATHENA pode fazer no seu computador?", centralizar=False)
        self.sel_perm = ListaPermissoes(cfg.get("permissoes", {}), cfg.get("seguranca.autonomia"))
        p.lay.addWidget(self.sel_perm)
        p.fechar()
        self.pilha.addWidget(p)

        # 8. voz
        p = Pagina("Voz", "Escolha como ela fala. Toque em “Ouvir exemplo”.")
        self.sel_voz = SeletorVoz(cfg)
        p.lay.addWidget(self.sel_voz)
        p.fechar()
        self.pilha.addWidget(p)

        # 9. verificação final
        p = Pagina("Quase lá", "")
        self.status_final = _rotulo("Conferindo se está tudo instalado…")
        p.lay.addWidget(self.status_final)
        self.checks = {}
        for chave, texto in (("ollama", "Ollama (cérebro) rodando"), ("modelo", "Modelo de IA baixado"),
                             ("mic", "Microfone encontrado"), ("vosk", "Detector da palavra “Atena”")):
            l = _rotulo(f"…&nbsp; {texto}", "subtitulo", centro=False)
            l.setProperty("texto", texto)
            self.checks[chave] = l
            p.lay.addWidget(l)
        self.dica_final = _rotulo("", "apagado", centro=False)
        p.lay.addWidget(self.dica_final)
        p.fechar()
        self.pilha.addWidget(p)

    # ------------------------------------------------------------------ navegação
    def ir(self, i: int, animar=True):
        i = max(0, min(i, self.pilha.count() - 1))
        anterior = self.pilha.currentIndex()
        self.pilha.setCurrentIndex(i)
        if animar and anterior != i:
            w = self.pilha.currentWidget()
            anim = QPropertyAnimation(w, b"pos", self)
            dx = 60 if i > anterior else -60
            anim.setStartValue(QPoint(dx, 0))
            anim.setEndValue(QPoint(0, 0))
            anim.setDuration(220)
            anim.setEasingCurve(QEasingCurve.OutCubic)
            anim.start()
            self._anim = anim
        for k, b in enumerate(self.barras):
            cor = tema.DESTAQUE if k <= i else tema.LINHA
            b.setStyleSheet(f"background:{cor}; border-radius:2px;")
        if not self.so_carrossel and i == self.pilha.count() - 1:
            self._verificar()
        self._atualizar_botoes()

    def _atualizar_botoes(self):
        i = self.pilha.currentIndex()
        ultimo = i == self.pilha.count() - 1
        self.voltar.setVisible(i > 0)
        no_carrossel = self.so_carrossel or i < getattr(self, "_fim_carrossel", 99)
        self.pular.setVisible(no_carrossel and not ultimo)
        self.proximo.setText("Começar" if ultimo else "Próximo")
        if not self.so_carrossel and i == 4:  # página do nome: obrigatório
            self.proximo.setEnabled(bool(self.campo_nome.text().strip()))
        else:
            self.proximo.setEnabled(True)

    def _pular(self):
        self.ir(self.pilha.count() - 1 if self.so_carrossel else self._fim_carrossel)

    def _avancar(self):
        if self.pilha.currentIndex() == self.pilha.count() - 1:
            self._salvar()
            self.concluido.emit()
            self.accept()
        else:
            self.ir(self.pilha.currentIndex() + 1)

    def keyPressEvent(self, ev):
        if ev.key() == Qt.Key_Right and self.proximo.isEnabled():
            self._avancar()
        elif ev.key() == Qt.Key_Left:
            self.ir(self.pilha.currentIndex() - 1)
        elif ev.key() == Qt.Key_Escape and self.so_carrossel:
            self.reject()
        else:
            super().keyPressEvent(ev)

    # ------------------------------------------------------------------ verificação e salvar
    _resultado = Signal(dict)

    def _verificar(self):
        if getattr(self, "_verificando", False):
            return
        self._verificando = True
        self._resultado.connect(self._mostrar_verificacao)

        def rodar():
            import requests
            r = {}
            modelo = self.config.get("cerebro.modelo", "qwen3:8b")
            try:
                tags = requests.get(self.config.get("cerebro.url") + "/api/tags", timeout=3).json()
                nomes = [m["name"] for m in tags.get("models", [])]
                r["ollama"] = True
                r["modelo"] = any(n == modelo or n.split(":")[0] == modelo for n in nomes)
            except Exception:
                r["ollama"] = r["modelo"] = False
            try:
                import sounddevice as sd
                r["mic"] = sd.query_devices(kind="input") is not None
            except Exception:
                r["mic"] = False
            r["vosk"] = self.config.caminho(self.config.get("ativacao.modelo_vosk")).exists()
            r["_modelo"] = modelo
            self._resultado.emit(r)

        threading.Thread(target=rodar, daemon=True).start()

    def _mostrar_verificacao(self, r: dict):
        dicas = []
        for chave, l in self.checks.items():
            ok = r.get(chave)
            icone = f'<span style="color:{tema.OK}">✓</span>' if ok else f'<span style="color:{tema.OURO}">!</span>'
            l.setText(f"{icone}&nbsp; {l.property('texto')}")
        if not r.get("ollama"):
            dicas.append("Instale e abra o Ollama (ollama.com). Sem ele, só os comandos rápidos funcionam.")
        elif not r.get("modelo"):
            dicas.append(f"Baixe o modelo: abra o terminal e rode  <b>ollama pull {r['_modelo']}</b>")
        if not r.get("mic"):
            dicas.append("Nenhum microfone encontrado. Você ainda pode escrever pra ela no painel.")
        if not r.get("vosk"):
            dicas.append("Rode o instalar.bat pra baixar o detector de “Atena”. Sem ele, ela gasta mais CPU ouvindo.")
        self.status_final.setText("Faltam alguns detalhes, mas dá pra começar:" if dicas else "Tudo instalado.")
        self.dica_final.setText("<br><br>".join(dicas) if dicas else
                                f'<span style="color:{tema.OK}">Tudo certo. Diga “Atena” quando quiser.</span>')

    def _salvar(self):
        if self.so_carrossel:
            return
        pers = self.sel_pers.valores()
        self.config.salvar_personalidade({
            "como_me_chamar": self.campo_nome.text().strip(),
            "nome": self.campo_ia.text().strip() or "ATHENA",
            **pers,
        })
        geral = {**self.sel_perm.valores(), **self.sel_voz.valores(), "primeira_vez": False}
        self.config.salvar_geral(geral)
