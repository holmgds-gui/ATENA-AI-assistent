"""Aba SISTEMA: monitor do PC em tempo real (uso, temperaturas, clocks, memória, disco, rede, processos)."""
from __future__ import annotations

import platform
import subprocess
import threading
import time
import webbrowser

from PySide6.QtCore import Qt, Signal
from PySide6.QtWidgets import (QFrame, QGridLayout, QHBoxLayout, QLabel, QPushButton, QScrollArea, QVBoxLayout,
                               QWidget)

from . import tema
from .hud import Barra, Grafico, Medidor, PainelHud


def _fmt_tempo(seg: float) -> str:
    d, r = divmod(int(seg), 86400)
    h, r = divmod(r, 3600)
    m = r // 60
    return (f"{d}d " if d else "") + f"{h:02d}h {m:02d}m"


def _linha_info(nome: str) -> tuple[QLabel, QLabel]:
    a = QLabel(nome.upper())
    a.setStyleSheet(f"color:{tema.APAGADO}; font-size:12.5px; letter-spacing:1.5px; font-weight:700;")
    b = QLabel("--")
    b.setObjectName("mono")
    b.setStyleSheet(f"font-family:{tema.FONTE_MONO}; font-size:13.5px;")
    b.setAlignment(Qt.AlignRight | Qt.AlignVCenter)
    return a, b


class AbaSistema(QWidget):
    _nova_leitura = Signal(object)

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setObjectName("transparente")
        self._monitor = None
        self._ativo = False
        self._nova_leitura.connect(self._mostrar)

        externo = QVBoxLayout(self)
        externo.setContentsMargins(0, 0, 0, 0)
        area = QScrollArea()
        area.setWidgetResizable(True)
        area.setFrameShape(QFrame.NoFrame)
        area.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        caixa = QWidget()
        caixa.setObjectName("transparente")
        lay = QVBoxLayout(caixa)
        lay.setContentsMargins(4, 4, 8, 12)
        lay.setSpacing(12)
        area.setWidget(caixa)
        externo.addWidget(area)

        # ---- aviso do LibreHardwareMonitor
        self.aviso = PainelHud("Sensores avançados desligados")
        txt = QLabel("Temperaturas, clocks, ventoinhas e dados da placa de vídeo vêm do <b>LibreHardwareMonitor</b> "
                     "(grátis). Instale, abra como administrador e ligue <b>Options → Remote Web Server → Run</b>.")
        txt.setWordWrap(True)
        txt.setObjectName("subtitulo")
        txt.setMinimumWidth(0)
        self.aviso.lay.addWidget(txt)
        h = QHBoxLayout()
        b1 = QPushButton("INSTALAR (WINGET)")
        b1.clicked.connect(self._instalar_lhm)
        b2 = QPushButton("SITE OFICIAL")
        b2.clicked.connect(lambda: webbrowser.open("https://github.com/LibreHardwareMonitor/LibreHardwareMonitor/releases"))
        h.addWidget(b1)
        h.addWidget(b2)
        h.addStretch(1)
        self.aviso.lay.addLayout(h)
        self.aviso.hide()
        lay.addWidget(self.aviso)

        # ---- medidores principais
        nucleo = PainelHud("Núcleo")
        grade = QGridLayout()
        self._grade_medidores = grade
        self.m_cpu = Medidor("CPU", "%", 100, 80, 95)
        self.m_cpu_t = Medidor("CPU temp", "°C", 105, 75, 90)
        self.m_gpu = Medidor("GPU", "%", 100, 85, 98)
        self.m_gpu_t = Medidor("GPU temp", "°C", 110, 78, 92)
        self.m_ram = Medidor("RAM", "%", 100, 80, 92)
        self._medidores = [self.m_cpu, self.m_cpu_t, self.m_gpu, self.m_gpu_t, self.m_ram]
        self._colunas = 0
        self._arrumar_medidores(5)
        nucleo.lay.addLayout(grade)
        lay.addWidget(nucleo)

        # ---- clocks + memória
        linha = QHBoxLayout()
        linha.setSpacing(12)
        self._linhas = [linha]
        clocks = PainelHud("Clocks · Potência")
        g = QGridLayout()
        g.setVerticalSpacing(7)
        self.info = {}
        for i, nome in enumerate(("CPU clock", "CPU máximo", "Boost", "CPU potência", "GPU core", "GPU memória",
                                  "GPU potência", "GPU hotspot")):
            a, b = _linha_info(nome)
            g.addWidget(a, i, 0)
            g.addWidget(b, i, 1)
            self.info[nome] = b
        clocks.lay.addLayout(g)
        linha.addWidget(clocks, 1)

        mem = PainelHud("Memória · Armazenamento")
        self.b_ram = Barra("RAM")
        self.b_vram = Barra("VRAM (placa de vídeo)")
        self.b_swap = Barra("Memória virtual")
        for b in (self.b_ram, self.b_vram, self.b_swap):
            mem.lay.addWidget(b)
        self.discos_lay = QVBoxLayout()
        self.discos_lay.setSpacing(4)
        mem.lay.addLayout(self.discos_lay)
        self.barras_disco: dict[str, Barra] = {}
        linha.addWidget(mem, 1)
        lay.addLayout(linha)

        # ---- gráficos
        linha2 = QHBoxLayout()
        linha2.setSpacing(12)
        self._linhas.append(linha2)
        hist = PainelHud("Histórico · 60 s")
        self.g_uso = Grafico([("cpu", "destaque"), ("gpu", "#3DDCFF"), ("ram", "#B98CFF")], 100, 60, "%")
        hist.lay.addWidget(self.g_uso)
        linha2.addWidget(hist, 3)
        rede = PainelHud("Rede · Disco")
        self.g_rede = Grafico([("down", "destaque"), ("up", "#3DDCFF")], None, 60, "")
        rede.lay.addWidget(self.g_rede)
        self.rede_txt = QLabel("--")
        self.rede_txt.setWordWrap(True)
        self.rede_txt.setStyleSheet(f"font-family:{tema.FONTE_MONO}; font-size:12.5px; color:{tema.APAGADO};")
        rede.lay.addWidget(self.rede_txt)
        linha2.addWidget(rede, 2)
        lay.addLayout(linha2)

        # ---- ventoinhas/sensores + processos
        linha3 = QHBoxLayout()
        linha3.setSpacing(12)
        self._linhas.append(linha3)
        self.p_sensores = PainelHud("Ventoinhas · Sensores")
        self.sens_lay = QGridLayout()
        self.sens_lay.setVerticalSpacing(5)
        self.p_sensores.lay.addLayout(self.sens_lay)
        linha3.addWidget(self.p_sensores, 1)
        procs = PainelHud("Processos mais pesados")
        self.proc_lay = QGridLayout()
        self.proc_lay.setVerticalSpacing(5)
        procs.lay.addLayout(self.proc_lay)
        self.proc_labels = []
        for i in range(6):
            n, c, r = QLabel(""), QLabel(""), QLabel("")
            for k, w in enumerate((n, c, r)):
                w.setStyleSheet(f"font-family:{tema.FONTE_MONO}; font-size:12.5px;")
                if k:
                    w.setAlignment(Qt.AlignRight)
                self.proc_lay.addWidget(w, i, k)
            self.proc_labels.append((n, c, r))
        linha3.addWidget(procs, 1)
        lay.addLayout(linha3)

        # ---- identificação
        ident = PainelHud("Identificação")
        g = QGridLayout()
        for i, nome in enumerate(("Processador", "Placa de vídeo", "Sistema", "Ligado há", "Processos", "Bateria")):
            a, b = _linha_info(nome)
            b.setAlignment(Qt.AlignLeft | Qt.AlignVCenter)
            b.setWordWrap(True)
            g.addWidget(a, i // 2, (i % 2) * 2)
            g.addWidget(b, i // 2, (i % 2) * 2 + 1)
            self.info[nome] = b
        g.setColumnStretch(1, 1)
        g.setColumnStretch(3, 1)
        ident.lay.addLayout(g)
        lay.addWidget(ident)
        lay.addStretch(1)

    # ------------------------------------------------------------------ layout que se adapta
    def _arrumar_medidores(self, colunas: int):
        if colunas == self._colunas:
            return
        self._colunas = colunas
        for m in self._medidores:
            self._grade_medidores.removeWidget(m)
        for i, m in enumerate(self._medidores):
            self._grade_medidores.addWidget(m, i // colunas, i % colunas)

    def resizeEvent(self, ev):
        super().resizeEvent(ev)
        from PySide6.QtWidgets import QBoxLayout
        w = self.width()
        self._arrumar_medidores(5 if w > 700 else 3)
        direcao = QBoxLayout.LeftToRight if w > 760 else QBoxLayout.TopToBottom
        for l in self._linhas:
            l.setDirection(direcao)

    # ------------------------------------------------------------------ coleta (thread separada)
    def iniciar(self):
        if self._ativo:
            return
        self._ativo = True
        threading.Thread(target=self._loop, daemon=True, name="monitor").start()

    def parar(self):
        self._ativo = False

    def _loop(self):
        from ..monitor import Monitor, nome_gpu
        if self._monitor is None:
            try:
                self._monitor = Monitor()
            except Exception as e:
                print(f"[monitor] indisponível: {e}")
                self._ativo = False
                return
            if not self._monitor.gpu_nome:
                self._monitor.gpu_nome = nome_gpu()
        n = 0
        while self._ativo:
            try:
                leitura = self._monitor.ler(com_processos=(n % 2 == 0))
                self._nova_leitura.emit(leitura)
            except Exception as e:
                print(f"[monitor] erro: {e}")
            n += 1
            time.sleep(1.0)

    def _instalar_lhm(self):
        if platform.system() == "Windows":
            subprocess.Popen(["cmd", "/c", "start", "cmd", "/k",
                              "winget install -e --id LibreHardwareMonitor.LibreHardwareMonitor"])
        else:
            webbrowser.open("https://github.com/LibreHardwareMonitor/LibreHardwareMonitor")

    # ------------------------------------------------------------------ mostrar
    def _mostrar(self, L):
        mon = self._monitor
        self.aviso.setVisible(not L.lhm)
        self.m_cpu.set_valor(L.cpu_uso)
        self.m_cpu_t.set_valor(L.cpu_temp)
        self.m_gpu.set_valor(L.gpu_uso)
        self.m_gpu_t.set_valor(L.gpu_temp)
        self.m_ram.set_valor(L.ram_pct, f"{L.ram_usada:.1f}/{L.ram_total:.0f} GB")

        clock = L.cpu_clock_lhm or L.cpu_freq
        fmt = lambda v, u, d=0: "--" if v is None else f"{v:.{d}f} {u}"  # noqa: E731
        self.info["CPU clock"].setText(fmt(clock, "MHz"))
        self.info["CPU máximo"].setText(fmt(L.cpu_freq_max or None, "MHz"))
        if clock and L.cpu_freq_max:
            boost = clock > L.cpu_freq_max * 1.02
            self.info["Boost"].setText("ATIVO ▲" if boost else "base")
            self.info["Boost"].setStyleSheet(f"font-family:{tema.FONTE_MONO}; font-size:13.5px; "
                                             f"color:{tema.OK if boost else tema.TEXTO};")
        self.info["CPU potência"].setText(fmt(L.cpu_potencia, "W", 1))
        self.info["GPU core"].setText(fmt(L.gpu_clock, "MHz"))
        self.info["GPU memória"].setText(fmt(L.gpu_clock_mem, "MHz"))
        self.info["GPU potência"].setText(fmt(L.gpu_potencia, "W", 1))
        self.info["GPU hotspot"].setText(fmt(L.gpu_hotspot, "°C"))

        self.b_ram.set(L.ram_pct / 100, f"{L.ram_usada:.1f} / {L.ram_total:.1f} GB")
        if L.gpu_vram_usada is not None and L.gpu_vram_total:
            self.b_vram.set(L.gpu_vram_usada / L.gpu_vram_total, f"{L.gpu_vram_usada:.1f} / {L.gpu_vram_total:.1f} GB")
        else:
            self.b_vram.set(0, "--")
        self.b_swap.set(L.swap_pct / 100, f"{L.swap_pct:.0f}%")
        for d in L.discos:
            b = self.barras_disco.get(d["nome"])
            if b is None:
                b = Barra(f"Disco {d['nome']}")
                self.barras_disco[d["nome"]] = b
                self.discos_lay.addWidget(b)
            b.set(d["pct"] / 100, f"{d['usado']:.0f} / {d['total']:.0f} GB")

        self.g_uso.adicionar(cpu=L.cpu_uso, gpu=L.gpu_uso or 0, ram=L.ram_pct)
        self.g_rede.adicionar(down=L.rede_down, up=L.rede_up)
        self.rede_txt.setText(f"▼ {L.rede_down:,.0f} KB/s   ▲ {L.rede_up:,.0f} KB/s   "
                              f"DISCO  R {L.disco_leitura:.1f}  W {L.disco_escrita:.1f} MB/s")

        # sensores extras
        while self.sens_lay.count():
            w = self.sens_lay.takeAt(0).widget()
            if w:
                w.deleteLater()
        itens = [(n, f"{v:.0f} RPM") for n, v in L.ventoinhas] + [(n, f"{v:.0f} °C") for n, v in L.temps_extras]
        if not itens:
            itens = [("Sem dados", "abra o LibreHardwareMonitor" if not L.lhm else "nenhum sensor extra")]
        for i, (n, v) in enumerate(itens[:10]):
            a, b = _linha_info(n)
            b.setText(v)
            self.sens_lay.addWidget(a, i, 0)
            self.sens_lay.addWidget(b, i, 1)

        if L.processos:
            for (n, c, r), p in zip(self.proc_labels, L.processos + [None] * 6):
                if p:
                    n.setText(p["nome"][:24])
                    c.setText(f"{p['cpu']:.1f}%")
                    r.setText(f"{p['ram']:.0f} MB")
                else:
                    n.setText(""), c.setText(""), r.setText("")
            self.info["Processos"].setText(str(L.n_processos))

        if mon:
            self.info["Processador"].setText(mon.cpu_nome)
            self.info["Placa de vídeo"].setText(mon.gpu_nome or "--")
            self.info["Sistema"].setText(mon.sistema)
        self.info["Ligado há"].setText(_fmt_tempo(L.ligado_ha))
        self.info["Bateria"].setText(f"{L.bateria['pct']:.0f}%{' ⚡' if L.bateria['carregando'] else ''}"
                                     if L.bateria else "desktop")
