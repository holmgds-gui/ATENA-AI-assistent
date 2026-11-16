"""Monitor do PC: uso, temperaturas, clocks, ventoinhas, memória, disco, rede e processos.

- psutil: CPU, RAM, disco, rede, bateria, processos (funciona sempre).
- LibreHardwareMonitor (opcional, Windows): temperaturas, clocks, ventoinhas, energia e GPU.
  Precisa estar aberto com "Options > Remote Web Server > Run" ligado (porta 8085).
"""
from __future__ import annotations

import platform
import re
import subprocess
import time
from dataclasses import dataclass, field

import requests

URL_LHM = "http://localhost:8085/data.json"
_SEM_JANELA = 0x08000000 if platform.system() == "Windows" else 0


@dataclass
class Sensor:
    nome: str
    tipo: str        # Temperature, Load, Clock, Fan, Power, Voltage, Data, SmallData, Throughput...
    valor: float
    maximo: float | None
    hardware: str    # cpu, gpu, ram, disco, placa, rede, outro
    nome_hw: str


@dataclass
class Leitura:
    momento: float = 0.0
    cpu_uso: float = 0.0
    cpu_nucleos: list[float] = field(default_factory=list)
    cpu_freq: float = 0.0
    cpu_freq_max: float = 0.0
    ram_usada: float = 0.0
    ram_total: float = 0.0
    ram_pct: float = 0.0
    swap_pct: float = 0.0
    discos: list[dict] = field(default_factory=list)
    disco_leitura: float = 0.0   # MB/s
    disco_escrita: float = 0.0
    rede_down: float = 0.0       # KB/s
    rede_up: float = 0.0
    ligado_ha: float = 0.0       # segundos
    bateria: dict | None = None
    processos: list[dict] = field(default_factory=list)
    n_processos: int = 0
    # vindos do LibreHardwareMonitor (None quando não disponível)
    lhm: bool = False
    cpu_temp: float | None = None
    cpu_potencia: float | None = None
    cpu_clock_lhm: float | None = None
    gpu_uso: float | None = None
    gpu_temp: float | None = None
    gpu_hotspot: float | None = None
    gpu_clock: float | None = None
    gpu_clock_mem: float | None = None
    gpu_potencia: float | None = None
    gpu_vram_usada: float | None = None
    gpu_vram_total: float | None = None
    ventoinhas: list[tuple[str, float]] = field(default_factory=list)
    temps_extras: list[tuple[str, float]] = field(default_factory=list)
    sensores: list[Sensor] = field(default_factory=list)


def _num(texto) -> float | None:
    if texto is None:
        return None
    if isinstance(texto, (int, float)):
        return float(texto)
    m = re.search(r"-?\d+(?:[.,]\d+)?", str(texto))
    return float(m.group(0).replace(",", ".")) if m else None


def _tipo_hw(no: dict) -> str:
    chave = (no.get("HardwareId") or no.get("SensorId") or no.get("ImageURL") or "").lower()
    texto = (no.get("Text") or "").lower()
    if "cpu" in chave or "ryzen" in texto or "intel core" in texto:
        return "cpu"
    if "gpu" in chave or "nvidia" in chave or "ati" in chave or "radeon" in texto or "geforce" in texto:
        return "gpu"
    if "ram" in chave or "memory" in texto:
        return "ram"
    if any(k in chave for k in ("hdd", "nvme", "ssd", "storage")):
        return "disco"
    if "mainboard" in chave or "lpc" in chave or "motherboard" in chave:
        return "placa"
    if "nic" in chave or "network" in chave:
        return "rede"
    return "outro"


def _tipo_sensor(no: dict, grupo: str) -> str:
    if no.get("Type"):
        return str(no["Type"])
    sid = (no.get("SensorId") or "").lower()
    for t in ("temperature", "load", "clock", "fan", "power", "voltage", "smalldata", "data", "throughput"):
        if f"/{t}/" in sid:
            return {"smalldata": "SmallData"}.get(t, t.capitalize())
    g = grupo.lower()
    return {"temperatures": "Temperature", "clocks": "Clock", "load": "Load", "fans": "Fan", "powers": "Power",
            "voltages": "Voltage", "data": "Data"}.get(g, g.capitalize())


def ler_lhm(timeout: float = 0.8) -> list[Sensor] | None:
    try:
        raiz = requests.get(URL_LHM, timeout=timeout).json()
    except Exception:
        return None
    sensores: list[Sensor] = []

    def andar(no, hw="outro", nome_hw="", grupo="", nivel=0):
        filhos = no.get("Children") or []
        if nivel == 2:  # nível do hardware (raiz > computador > hardware)
            hw, nome_hw = _tipo_hw(no), no.get("Text", "")
        if not filhos:
            v = _num(no.get("Value"))
            if v is not None and nivel >= 3:
                sensores.append(Sensor(no.get("Text", ""), _tipo_sensor(no, grupo), v, _num(no.get("Max")), hw, nome_hw))
            return
        for f in filhos:
            andar(f, hw, nome_hw, no.get("Text", "") if nivel >= 2 else grupo, nivel + 1)

    andar(raiz)
    return sensores


def _escolher(sensores, hw, tipo, preferidos=(), evitar=()) -> Sensor | None:
    cands = [s for s in sensores if s.hardware == hw and s.tipo == tipo]
    for pref in preferidos:
        for s in cands:
            if pref in s.nome.lower() and not any(e in s.nome.lower() for e in evitar):
                return s
    cands = [s for s in cands if not any(e in s.nome.lower() for e in evitar)]
    return cands[0] if cands else None


class Monitor:
    def __init__(self):
        import psutil
        self.ps = psutil
        self._io_disco = psutil.disk_io_counters()
        self._io_rede = psutil.net_io_counters()
        self._t = time.time()
        self._lhm_ok = None
        self._proximo_teste_lhm = 0.0
        psutil.cpu_percent(percpu=True)
        self.cpu_nome = nome_cpu()
        self.gpu_nome = None
        self.sistema = f"{platform.system()} {platform.release()}"

    def ler(self, com_processos: bool = True) -> Leitura:
        ps = self.ps
        agora = time.time()
        dt = max(0.2, agora - self._t)
        self._t = agora
        L = Leitura(momento=agora)
        nucleos = ps.cpu_percent(percpu=True)
        L.cpu_nucleos = nucleos
        L.cpu_uso = sum(nucleos) / max(1, len(nucleos))
        try:
            f = ps.cpu_freq()
            L.cpu_freq, L.cpu_freq_max = f.current, f.max or f.current
        except Exception:
            pass
        vm = ps.virtual_memory()
        L.ram_usada, L.ram_total, L.ram_pct = vm.used / 1e9, vm.total / 1e9, vm.percent
        try:
            L.swap_pct = ps.swap_memory().percent
        except Exception:
            pass
        for part in ps.disk_partitions(all=False):
            if "cdrom" in part.opts or not part.fstype:
                continue
            try:
                u = ps.disk_usage(part.mountpoint)
                if u.total < 2e9:
                    continue
                L.discos.append({"nome": part.mountpoint, "usado": u.used / 1e9, "total": u.total / 1e9,
                                 "pct": u.percent})
            except Exception:
                continue
        io = ps.disk_io_counters()
        if io and self._io_disco:
            L.disco_leitura = (io.read_bytes - self._io_disco.read_bytes) / dt / 1e6
            L.disco_escrita = (io.write_bytes - self._io_disco.write_bytes) / dt / 1e6
        self._io_disco = io
        rede = ps.net_io_counters()
        L.rede_down = (rede.bytes_recv - self._io_rede.bytes_recv) / dt / 1e3
        L.rede_up = (rede.bytes_sent - self._io_rede.bytes_sent) / dt / 1e3
        self._io_rede = rede
        L.ligado_ha = agora - ps.boot_time()
        try:
            b = ps.sensors_battery()
            if b:
                L.bateria = {"pct": b.percent, "carregando": b.power_plugged}
        except Exception:
            pass
        if com_processos:
            procs = []
            for p in ps.process_iter(["name", "cpu_percent", "memory_info"]):
                try:
                    procs.append({"nome": p.info["name"] or "?", "cpu": (p.info["cpu_percent"] or 0) / ps.cpu_count(),
                                  "ram": (p.info["memory_info"].rss if p.info["memory_info"] else 0) / 1e6})
                except Exception:
                    continue
            L.n_processos = len(procs)
            procs = [p for p in procs if p["nome"].lower() not in ("system idle process", "idle")]
            L.processos = sorted(procs, key=lambda p: (p["cpu"], p["ram"]), reverse=True)[:6]

        # LibreHardwareMonitor: se falhar, só tenta de novo a cada 15 s
        if self._lhm_ok is not False or agora >= self._proximo_teste_lhm:
            sensores = ler_lhm()
            self._lhm_ok = sensores is not None
            if not self._lhm_ok:
                self._proximo_teste_lhm = agora + 15
            else:
                self._aplicar_lhm(L, sensores)
        return L

    def _aplicar_lhm(self, L: Leitura, s: list[Sensor]) -> None:
        L.lhm, L.sensores = True, s
        v = lambda x: x.valor if x else None  # noqa: E731
        L.cpu_temp = v(_escolher(s, "cpu", "Temperature", ("package", "tctl", "tdie", "core (tctl", "cpu")))
        L.cpu_potencia = v(_escolher(s, "cpu", "Power", ("package",)))
        clocks = [x.valor for x in s if x.hardware == "cpu" and x.tipo == "Clock" and "core" in x.nome.lower()
                  and "bus" not in x.nome.lower()]
        L.cpu_clock_lhm = sum(clocks) / len(clocks) if clocks else None
        L.gpu_uso = v(_escolher(s, "gpu", "Load", ("gpu core", "d3d 3d", "core")))
        L.gpu_temp = v(_escolher(s, "gpu", "Temperature", ("gpu core", "core", "edge", "gpu")))
        L.gpu_hotspot = v(_escolher(s, "gpu", "Temperature", ("hot spot", "hotspot", "junction")))
        L.gpu_clock = v(_escolher(s, "gpu", "Clock", ("gpu core", "core")))
        L.gpu_clock_mem = v(_escolher(s, "gpu", "Clock", ("memory",)))
        L.gpu_potencia = v(_escolher(s, "gpu", "Power", ("package", "total", "gpu")))
        usada = _escolher(s, "gpu", "SmallData", ("memory used", "dedicated memory used", "d3d dedicated memory used"))
        total = _escolher(s, "gpu", "SmallData", ("memory total", "dedicated memory total"))
        if usada:
            L.gpu_vram_usada = usada.valor / 1024
        if total:
            L.gpu_vram_total = total.valor / 1024
        L.ventoinhas = [(f"{x.nome}", x.valor) for x in s if x.tipo == "Fan" and x.valor > 0][:6]
        L.temps_extras = [(f"{x.nome_hw.split()[0]} {x.nome}", x.valor) for x in s
                          if x.tipo == "Temperature" and x.hardware in ("disco", "placa") and 0 < x.valor < 120][:6]
        if not self.gpu_nome:
            g = next((x.nome_hw for x in s if x.hardware == "gpu"), None)
            self.gpu_nome = g


def nome_cpu() -> str:
    try:
        if platform.system() == "Windows":
            import winreg
            k = winreg.OpenKey(winreg.HKEY_LOCAL_MACHINE, r"HARDWARE\DESCRIPTION\System\CentralProcessor\0")
            return winreg.QueryValueEx(k, "ProcessorNameString")[0].strip()
        if platform.system() == "Darwin":
            return subprocess.run(["sysctl", "-n", "machdep.cpu.brand_string"], capture_output=True,
                                  text=True).stdout.strip()
        with open("/proc/cpuinfo") as f:
            for linha in f:
                if linha.startswith("model name"):
                    return linha.split(":", 1)[1].strip()
    except Exception:
        pass
    return platform.processor() or "CPU"


def nome_gpu() -> str | None:
    try:
        if platform.system() == "Windows":
            out = subprocess.run(["powershell", "-NoProfile", "-Command",
                                  "(Get-CimInstance Win32_VideoController).Name"], capture_output=True, text=True,
                                 creationflags=_SEM_JANELA, timeout=10).stdout
            nomes = [n.strip() for n in out.splitlines() if n.strip()]
            dedicadas = [n for n in nomes if not re.search(r"basic|microsoft|virtual", n, re.I)]
            return (dedicadas or nomes or [None])[0]
    except Exception:
        pass
    return None


def resumo_falado(L: Leitura) -> dict:
    """Usado pela IA quando você pergunta sobre o PC."""
    r = {"cpu_uso": f"{L.cpu_uso:.0f}%", "ram": f"{L.ram_usada:.1f} de {L.ram_total:.1f} GB ({L.ram_pct:.0f}%)"}
    if L.cpu_temp is not None:
        r["cpu_temperatura"] = f"{L.cpu_temp:.0f} °C"
    if L.gpu_temp is not None:
        r["gpu_temperatura"] = f"{L.gpu_temp:.0f} °C"
    if L.gpu_uso is not None:
        r["gpu_uso"] = f"{L.gpu_uso:.0f}%"
    if L.cpu_clock_lhm or L.cpu_freq:
        r["cpu_clock"] = f"{(L.cpu_clock_lhm or L.cpu_freq):.0f} MHz"
    if L.ventoinhas:
        r["ventoinhas"] = ", ".join(f"{n} {v:.0f} RPM" for n, v in L.ventoinhas[:3])
    if L.discos:
        r["disco"] = ", ".join(f"{d['nome']} {d['pct']:.0f}% cheio" for d in L.discos[:3])
    if L.processos:
        r["mais_pesado"] = L.processos[0]["nome"]
    if not L.lhm:
        r["observacao"] = "temperaturas indisponíveis (LibreHardwareMonitor não está aberto)"
    return r
