"""Camada que mexe no computador: abrir apps e sites, digitar, teclas, volume, energia.

Feita pra Windows primeiro, mas já com caminhos pra macOS e Linux.
"""
from __future__ import annotations

import difflib
import glob
import json
import os
import platform
import re
import subprocess
import time
import unicodedata
import urllib.parse
import webbrowser
from dataclasses import dataclass

SO = platform.system()  # "Windows" | "Darwin" | "Linux"
NO_WINDOWS = SO == "Windows"

# Esconde a janela preta do PowerShell/cmd no Windows
_SEM_JANELA = 0x08000000 if NO_WINDOWS else 0


def normalizar(texto: str) -> str:
    """'Configurações do Windows' -> 'configuracoes do windows'"""
    texto = unicodedata.normalize("NFKD", texto or "")
    texto = "".join(c for c in texto if not unicodedata.combining(c))
    texto = re.sub(r"[^a-z0-9+#. ]+", " ", texto.lower())
    return re.sub(r"\s+", " ", texto).strip()


# ======================================================================
#  Índice de aplicativos instalados
# ======================================================================
@dataclass
class App:
    nome: str
    alvo: str          # AppID (Windows), caminho .app (mac) ou comando (Linux)
    chave: str = ""

    def __post_init__(self):
        self.chave = normalizar(self.nome)


class IndiceApps:
    def __init__(self):
        self.apps: list[App] = []
        self.carregado = False

    def carregar(self) -> None:
        try:
            if NO_WINDOWS:
                self.apps = self._apps_windows()
            elif SO == "Darwin":
                self.apps = self._apps_mac()
            else:
                self.apps = self._apps_linux()
        except Exception as e:  # nunca deixa a ATENA cair por causa disso
            print(f"[apps] não consegui listar os apps: {e}")
            self.apps = []
        self.carregado = True
        print(f"[apps] {len(self.apps)} aplicativos encontrados")

    # --- Windows: Get-StartApps pega apps normais E da Microsoft Store (Spotify, WhatsApp...)
    def _apps_windows(self) -> list[App]:
        cmd = ["powershell", "-NoProfile", "-Command",
               "[Console]::OutputEncoding=[Text.Encoding]::UTF8; Get-StartApps | ConvertTo-Json -Compress"]
        saida = subprocess.run(cmd, capture_output=True, text=True, encoding="utf-8",
                               creationflags=_SEM_JANELA, timeout=30).stdout
        dados = json.loads(saida or "[]")
        if isinstance(dados, dict):
            dados = [dados]
        return [App(d["Name"], d["AppID"]) for d in dados if d.get("Name") and d.get("AppID")]

    def _apps_mac(self) -> list[App]:
        caminhos = glob.glob("/Applications/*.app") + glob.glob("/System/Applications/*.app") \
            + glob.glob(os.path.expanduser("~/Applications/*.app"))
        return [App(os.path.basename(p)[:-4], p) for p in caminhos]

    def _apps_linux(self) -> list[App]:
        apps = []
        pastas = ["/usr/share/applications", os.path.expanduser("~/.local/share/applications"),
                  "/var/lib/flatpak/exports/share/applications"]
        for pasta in pastas:
            for arq in glob.glob(os.path.join(pasta, "*.desktop")):
                nome, execu = None, None
                try:
                    with open(arq, encoding="utf-8", errors="ignore") as f:
                        for linha in f:
                            if linha.startswith("Name=") and not nome:
                                nome = linha[5:].strip()
                            elif linha.startswith("Exec=") and not execu:
                                execu = re.sub(r"\s%[a-zA-Z]", "", linha[5:].strip())
                except OSError:
                    continue
                if nome and execu:
                    apps.append(App(nome, execu))
        return apps

    def procurar(self, nome: str) -> App | None:
        if not self.carregado:
            self.carregar()
        alvo = normalizar(nome)
        if not alvo or not self.apps:
            return None
        # 1) nome exato  2) começa com  3) contém  4) parecido (erros de transcrição)
        for app in self.apps:
            if app.chave == alvo:
                return app
        candidatos = [a for a in self.apps if a.chave.startswith(alvo)]
        if not candidatos:
            candidatos = [a for a in self.apps if re.search(rf"\b{re.escape(alvo)}\b", a.chave)]
        if candidatos:
            return min(candidatos, key=lambda a: len(a.chave))
        chaves = [a.chave for a in self.apps]
        parecidos = difflib.get_close_matches(alvo, chaves, n=1, cutoff=0.72)
        if parecidos:
            return next(a for a in self.apps if a.chave == parecidos[0])
        return None


INDICE = IndiceApps()


def abrir_app(nome: str, apelidos: dict | None = None) -> tuple[bool, str]:
    """Abre um app pelo nome falado. Retorna (deu_certo, nome_real_ou_erro)."""
    chave = normalizar(nome)
    if apelidos:
        for apelido, real in apelidos.items():
            if normalizar(apelido) == chave:
                nome = real
                break
    app = INDICE.procurar(nome)
    if not app:
        return False, f"não encontrei nenhum app chamado {nome}"
    try:
        if NO_WINDOWS:
            subprocess.Popen(["explorer.exe", f"shell:AppsFolder\\{app.alvo}"], creationflags=_SEM_JANELA)
        elif SO == "Darwin":
            subprocess.Popen(["open", app.alvo])
        else:
            subprocess.Popen(app.alvo, shell=True, start_new_session=True,
                             stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        return True, app.nome
    except Exception as e:
        return False, f"erro ao abrir {app.nome}: {e}"


def fechar_app(nome: str) -> tuple[bool, str]:
    import psutil
    alvo = normalizar(nome)
    fechados = set()
    for proc in psutil.process_iter(["name"]):
        nome_proc = normalizar((proc.info.get("name") or "").rsplit(".", 1)[0])
        if nome_proc and (nome_proc == alvo or alvo in nome_proc):
            try:
                proc.terminate()
                fechados.add(proc.info["name"])
            except Exception:
                pass
    if not fechados:
        return False, f"nenhum programa aberto chamado {nome}"
    return True, ", ".join(sorted(fechados))


# ======================================================================
#  Navegador
# ======================================================================
def abrir_site(url_ou_nome: str, apelidos: dict | None = None) -> tuple[bool, str]:
    alvo = url_ou_nome.strip()
    if apelidos and normalizar(alvo) in {normalizar(k) for k in apelidos}:
        alvo = next(v for k, v in apelidos.items() if normalizar(k) == normalizar(alvo))
    if not re.match(r"^https?://", alvo):
        if re.search(r"\.[a-z]{2,}(/|$)", alvo.lower()):
            alvo = "https://" + alvo.replace(" ", "")
        else:  # não parece um site: pesquisa no Google
            alvo = "https://www.google.com/search?q=" + urllib.parse.quote_plus(alvo)
    webbrowser.open(alvo)
    return True, alvo


def pesquisar_no_navegador(consulta: str, onde: str = "google") -> str:
    q = urllib.parse.quote_plus(consulta)
    urls = {
        "google": f"https://www.google.com/search?q={q}",
        "youtube": f"https://www.youtube.com/results?search_query={q}",
        "imagens": f"https://www.google.com/search?tbm=isch&q={q}",
        "maps": f"https://www.google.com/maps/search/{q}",
        "wikipedia": f"https://pt.wikipedia.org/w/index.php?search={q}",
    }
    url = urls.get(normalizar(onde), urls["google"])
    webbrowser.open(url)
    return url


def pesquisar_na_web(consulta: str, max_resultados: int = 5) -> list[dict]:
    """Pesquisa de verdade (DuckDuckGo) e devolve títulos + resumos pra IA ler."""
    try:
        from ddgs import DDGS
    except ImportError:
        from duckduckgo_search import DDGS  # nome antigo do pacote
    with DDGS() as ddgs:
        res = list(ddgs.text(consulta, region="br-pt", max_results=max_resultados))
    return [{"titulo": r.get("title", ""), "resumo": r.get("body", ""), "link": r.get("href", "")} for r in res]


def tocar_no_youtube(consulta: str) -> str:
    """Tenta abrir direto o primeiro vídeo; se não der, abre a busca."""
    try:
        try:
            from ddgs import DDGS
        except ImportError:
            from duckduckgo_search import DDGS
        with DDGS() as ddgs:
            for v in ddgs.videos(consulta + " youtube", max_results=5):
                url = v.get("content") or ""
                if "youtube.com/watch" in url or "youtu.be/" in url:
                    webbrowser.open(url)
                    return v.get("title") or url
    except Exception as e:
        print(f"[youtube] busca direta falhou: {e}")
    pesquisar_no_navegador(consulta, "youtube")
    return f"busca por {consulta}"


# ======================================================================
#  Teclado e mouse
# ======================================================================
def digitar(texto: str) -> None:
    """Digita usando a área de transferência (assim acentos funcionam)."""
    import pyautogui
    import pyperclip
    antigo = None
    try:
        antigo = pyperclip.paste()
    except Exception:
        pass
    pyperclip.copy(texto)
    time.sleep(0.05)
    pyautogui.hotkey("command" if SO == "Darwin" else "ctrl", "v")
    time.sleep(0.15)
    if antigo is not None:
        try:
            pyperclip.copy(antigo)
        except Exception:
            pass


_NOMES_TECLAS = {
    "control": "ctrl", "controle": "ctrl", "enter": "enter", "entra": "enter", "esc": "esc",
    "espaço": "space", "espaco": "space", "tab": "tab", "apagar": "backspace", "deletar": "delete",
    "cima": "up", "baixo": "down", "esquerda": "left", "direita": "right", "windows": "win",
    "super": "win", "cmd": "command",
}


def pressionar(teclas: str) -> str:
    """'ctrl+s', 'alt+tab', 'enter'"""
    import pyautogui
    partes = [p.strip().lower() for p in re.split(r"[+ ]+", teclas) if p.strip()]
    partes = [_NOMES_TECLAS.get(p, p) for p in partes]
    if len(partes) == 1:
        pyautogui.press(partes[0])
    else:
        pyautogui.hotkey(*partes)
    return "+".join(partes)


def volume(acao: str, passos: int = 5) -> str:
    import pyautogui
    acao = normalizar(acao)
    if acao in ("mudo", "mutar", "silenciar", "desmutar"):
        pyautogui.press("volumemute")
        return "mudo alternado"
    tecla = "volumeup" if acao in ("aumentar", "subir", "mais", "aumenta") else "volumedown"
    pyautogui.press(tecla, presses=max(1, min(int(passos), 50)))
    return f"volume {'aumentado' if tecla == 'volumeup' else 'diminuído'}"


def midia(acao: str) -> str:
    import pyautogui
    mapa = {"pausar": "playpause", "tocar": "playpause", "play": "playpause", "pause": "playpause",
            "proxima": "nexttrack", "proximo": "nexttrack", "anterior": "prevtrack", "voltar": "prevtrack"}
    tecla = mapa.get(normalizar(acao), "playpause")
    pyautogui.press(tecla)
    return tecla


# ======================================================================
#  Energia / sistema
# ======================================================================
def energia(acao: str) -> str:
    acao = normalizar(acao)
    if NO_WINDOWS:
        cmds = {
            "bloquear": ["rundll32.exe", "user32.dll,LockWorkStation"],
            "desligar": ["shutdown", "/s", "/t", "5"],
            "reiniciar": ["shutdown", "/r", "/t", "5"],
            "suspender": ["rundll32.exe", "powrprof.dll,SetSuspendState", "0,1,0"],
        }
    elif SO == "Darwin":
        cmds = {
            "bloquear": ["pmset", "displaysleepnow"],
            "desligar": ["osascript", "-e", 'tell app "System Events" to shut down'],
            "reiniciar": ["osascript", "-e", 'tell app "System Events" to restart'],
            "suspender": ["pmset", "sleepnow"],
        }
    else:
        cmds = {
            "bloquear": ["loginctl", "lock-session"],
            "desligar": ["systemctl", "poweroff"],
            "reiniciar": ["systemctl", "reboot"],
            "suspender": ["systemctl", "suspend"],
        }
    if acao not in cmds:
        return f"ação desconhecida: {acao}"
    subprocess.Popen(cmds[acao], creationflags=_SEM_JANELA)
    return acao


def info_sistema() -> dict:
    import psutil
    info = {
        "cpu_uso": f"{psutil.cpu_percent(interval=0.4):.0f}%",
        "ram_uso": f"{psutil.virtual_memory().percent:.0f}%",
        "ram_total": f"{psutil.virtual_memory().total / 1e9:.1f} GB",
        "sistema": f"{platform.system()} {platform.release()}",
    }
    try:
        disco = psutil.disk_usage("C:\\" if NO_WINDOWS else "/")
        info["disco_livre"] = f"{disco.free / 1e9:.0f} GB livres de {disco.total / 1e9:.0f} GB"
    except Exception:
        pass
    bat = psutil.sensors_battery() if hasattr(psutil, "sensors_battery") else None
    if bat:
        info["bateria"] = f"{bat.percent:.0f}%" + (" carregando" if bat.power_plugged else "")
    return info


def pasta_documentos() -> str:
    pasta = os.path.join(os.path.expanduser("~"), "Documents", "ATENA")
    os.makedirs(pasta, exist_ok=True)
    return pasta
