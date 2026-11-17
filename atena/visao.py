"""Os "olhos" da ATENA. Três camadas, da mais precisa pra mais esperta:

1. Acessibilidade do Windows (UI Automation): lista botões, campos, abas e menus da janela ativa,
   com nome e posição exata. É como o leitor de tela do Windows enxerga.
2. OCR do Windows: lê todo texto visível na tela (sites, jogos, PDFs, apps que a camada 1 não vê).
3. IA de visão (Qwen3-VL no Ollama): olha a captura de tela inteira, descreve o que tem nela e
   acha ícones/imagens sem texto.

Cada elemento encontrado ganha um número. A IA diz "clica no 12" e a ATENA clica no lugar certo.
"""
from __future__ import annotations

import asyncio
import base64
import difflib
import io
import json
import platform
import re
import threading
import time
from dataclasses import dataclass

import requests

from .sistema import normalizar

NO_WINDOWS = platform.system() == "Windows"

if NO_WINDOWS:  # coordenadas em pixels reais, mesmo com escala de tela 125%/150%
    try:
        import ctypes
        ctypes.windll.shcore.SetProcessDpiAwareness(2)
    except Exception:
        pass

TIPOS_CLICAVEIS = {
    "ButtonControl", "MenuItemControl", "TabItemControl", "HyperlinkControl", "ListItemControl",
    "TreeItemControl", "CheckBoxControl", "RadioButtonControl", "ComboBoxControl", "EditControl",
    "SplitButtonControl", "DataItemControl", "DocumentControl", "MenuBarControl",
}
NOMES_TIPO = {
    "ButtonControl": "botão", "MenuItemControl": "menu", "TabItemControl": "aba", "HyperlinkControl": "link",
    "ListItemControl": "item", "TreeItemControl": "item", "CheckBoxControl": "caixa", "RadioButtonControl": "opção",
    "ComboBoxControl": "lista", "EditControl": "campo", "SplitButtonControl": "botão", "DataItemControl": "item",
    "DocumentControl": "documento", "TextControl": "texto", "ocr": "texto",
}
PALAVRAS_PERIGOSAS = r"\b(excluir|apagar|deletar|delete|remover|desinstalar|formatar|comprar|pagar|finalizar compra|" \
                     r"confirmar pagamento|transferir|pix|enviar|send|publicar|postar|sair sem salvar|descartar)\b"


@dataclass
class Elemento:
    id: int
    texto: str
    tipo: str      # ButtonControl, EditControl..., ou "ocr"
    x: int
    y: int
    w: int
    h: int
    origem: str    # "ui" ou "ocr"

    @property
    def centro(self) -> tuple[int, int]:
        return self.x + self.w // 2, self.y + self.h // 2

    def resumo(self) -> str:
        return f"[{self.id}] {NOMES_TIPO.get(self.tipo, 'elemento')}: {self.texto[:60]}"


@dataclass
class Varredura:
    momento: float
    janela: str
    elementos: list[Elemento]
    imagem: object            # PIL.Image
    origem_tela: tuple[int, int]


# ======================================================================
#  Captura
# ======================================================================
def capturar_tela():
    """Captura todos os monitores. Devolve (PIL.Image, (x0, y0) do canto da área virtual)."""
    import mss
    from PIL import Image
    with mss.mss() as s:
        mon = s.monitors[0]
        bruto = s.grab(mon)
        img = Image.frombytes("RGB", bruto.size, bruto.bgra, "raw", "BGRX")
    return img, (mon["left"], mon["top"])


# ======================================================================
#  Camada 1: acessibilidade do Windows
# ======================================================================
def elementos_acessibilidade(limite: int = 220, tempo_max: float = 1.6) -> tuple[str, list[tuple]]:
    if not NO_WINDOWS:
        return "", []
    import uiautomation as auto
    saida, inicio = [], time.time()
    with auto.UIAutomationInitializerInThread():
        janela = auto.GetForegroundControl()
        if janela is None:
            return "", []
        titulo = janela.Name or ""
        pilha = [(janela, 0)]
        while pilha and len(saida) < limite and time.time() - inicio < tempo_max:
            ctrl, prof = pilha.pop()
            try:
                tipo = ctrl.ControlTypeName
                nome = (ctrl.Name or "").strip()
                r = ctrl.BoundingRectangle
                visivel = not ctrl.IsOffScreen and r.width() > 4 and r.height() > 4
                if visivel and tipo in TIPOS_CLICAVEIS and (nome or tipo == "EditControl"):
                    saida.append((nome or "(campo de texto)", tipo, r.left, r.top, r.width(), r.height()))
                if prof < 14:
                    filhos = ctrl.GetChildren()
                    pilha.extend((f, prof + 1) for f in reversed(filhos))
            except Exception:
                continue
    return titulo, saida


# ======================================================================
#  Camada 2: OCR do Windows
# ======================================================================
async def _ocr_windows(img, idioma: str):
    try:
        from winrt.windows.globalization import Language
        from winrt.windows.graphics.imaging import BitmapPixelFormat, SoftwareBitmap
        from winrt.windows.media.ocr import OcrEngine
        from winrt.windows.storage.streams import DataWriter
    except ImportError:  # pacote antigo
        from winsdk.windows.globalization import Language
        from winsdk.windows.graphics.imaging import BitmapPixelFormat, SoftwareBitmap
        from winsdk.windows.media.ocr import OcrEngine
        from winsdk.windows.storage.streams import DataWriter
    motor = None
    try:
        motor = OcrEngine.try_create_from_language(Language(idioma))
    except Exception:
        pass
    motor = motor or OcrEngine.try_create_from_user_profile_languages()
    if motor is None:
        raise RuntimeError("Nenhum idioma de OCR instalado no Windows")
    rgba = img.convert("RGBA")
    escritor = DataWriter()
    escritor.write_bytes(rgba.tobytes())
    bitmap = SoftwareBitmap.create_copy_from_buffer(escritor.detach_buffer(), BitmapPixelFormat.RGBA8,
                                                    rgba.width, rgba.height)
    return await motor.recognize_async(bitmap)


def ocr(img, idioma: str = "pt-BR") -> list[tuple]:
    """Devolve linhas [(texto, x, y, w, h)] em pixels da imagem."""
    if not NO_WINDOWS:
        return []
    from PIL import Image
    escala = 1.0
    if max(img.size) > 9000:  # limite do motor de OCR do Windows
        escala = 9000 / max(img.size)
        img = img.resize((int(img.width * escala), int(img.height * escala)), Image.BILINEAR)
    resultado = asyncio.run(_ocr_windows(img, idioma))
    linhas = []
    for linha in resultado.lines:
        palavras = list(linha.words)
        if not palavras:
            continue
        xs = [p.bounding_rect.x for p in palavras]
        ys = [p.bounding_rect.y for p in palavras]
        x2 = [p.bounding_rect.x + p.bounding_rect.width for p in palavras]
        y2 = [p.bounding_rect.y + p.bounding_rect.height for p in palavras]
        x, y = min(xs) / escala, min(ys) / escala
        linhas.append((linha.text, int(x), int(y), int((max(x2) / escala) - x), int((max(y2) / escala) - y)))
    return linhas


# ======================================================================
#  Juntar tudo
# ======================================================================
def _sobrepoe(a: tuple, b: Elemento) -> bool:
    ax, ay, aw, ah = a
    cx, cy = ax + aw / 2, ay + ah / 2
    return b.x <= cx <= b.x + b.w and b.y <= cy <= b.y + b.h


def mesclar(ui: list[tuple], linhas_ocr: list[tuple], origem: tuple[int, int]) -> list[Elemento]:
    """UI Automation tem prioridade; OCR entra só onde não tem elemento de UI com o mesmo texto."""
    elems: list[Elemento] = []
    for nome, tipo, x, y, w, h in ui:
        elems.append(Elemento(0, nome, tipo, int(x), int(y), int(w), int(h), "ui"))
    ox, oy = origem
    for texto, x, y, w, h in linhas_ocr:
        texto = texto.strip()
        if len(texto) < 2:
            continue
        caixa = (x + ox, y + oy, w, h)
        repetido = any(_sobrepoe(caixa, e) and (normalizar(texto) in normalizar(e.texto)
                                                or normalizar(e.texto) in normalizar(texto)) for e in elems)
        if not repetido:
            elems.append(Elemento(0, texto, "ocr", caixa[0], caixa[1], w, h, "ocr"))
    elems.sort(key=lambda e: (e.y // 18, e.x))  # ordem de leitura
    for i, e in enumerate(elems, 1):
        e.id = i
    return elems


def achar(alvo: str, elems: list[Elemento]) -> Elemento | None:
    """Acha um elemento pelo número ('12', '#12') ou pelo texto (tolera erro de digitação/transcrição)."""
    alvo = (alvo or "").strip()
    m = re.fullmatch(r"#?\[?(\d+)\]?", alvo)
    if m:
        n = int(m.group(1))
        return next((e for e in elems if e.id == n), None)
    a = normalizar(alvo)
    if not a:
        return None

    def pontos(e: Elemento) -> float:
        t = normalizar(e.texto)
        if not t:
            return 0
        if t == a:
            base = 1.0
        elif t.startswith(a) or a in t.split():
            base = 0.85
        elif a in t:
            base = 0.7 - min(0.3, (len(t) - len(a)) / 200)
        else:
            base = difflib.SequenceMatcher(None, a, t).ratio() * 0.8
        if e.origem == "ui" and e.tipo in TIPOS_CLICAVEIS:
            base += 0.08  # botões de verdade ganham dos textos soltos
        return base

    melhor = max(elems, key=pontos, default=None)
    return melhor if melhor and pontos(melhor) >= 0.55 else None


def parece_perigoso(texto: str) -> bool:
    return bool(re.search(PALAVRAS_PERIGOSAS, normalizar(texto)))


def interpretar_ponto(resposta: str, largura: int, altura: int) -> tuple[int, int] | None:
    """Lê a resposta da IA de visão. Aceita JSON {"x","y"} na escala 0-1000 (padrão do Qwen3-VL),
    em pixels, ou uma caixa [x1,y1,x2,y2]."""
    texto = re.sub(r"<think>.*?</think>", "", resposta or "", flags=re.S)
    if re.search(r"nao_encontrado|não encontrado|not found", texto, re.I):
        return None
    m = re.search(r"\{.*?\}", texto, re.S)
    x = y = None
    if m:
        try:
            d = json.loads(m.group(0))
            if "bbox_2d" in d or "bbox" in d:
                x1, y1, x2, y2 = d.get("bbox_2d") or d.get("bbox")
                x, y = (x1 + x2) / 2, (y1 + y2) / 2
            else:
                x, y = float(d["x"]), float(d["y"])
        except Exception:
            pass
    if x is None:
        nums = [float(n) for n in re.findall(r"-?\d+(?:\.\d+)?", texto)]
        if len(nums) >= 4:
            x, y = (nums[0] + nums[2]) / 2, (nums[1] + nums[3]) / 2
        elif len(nums) >= 2:
            x, y = nums[0], nums[1]
        else:
            return None
    if x <= 1.0 and y <= 1.0:          # 0..1
        return int(x * largura), int(y * altura)
    if x <= 1000 and y <= 1000:        # 0..1000 (Qwen3-VL)
        return int(x / 1000 * largura), int(y / 1000 * altura)
    return int(x), int(y)              # pixels da imagem enviada


# ======================================================================
#  A classe que as ferramentas usam
# ======================================================================
class Visao:
    def __init__(self, config):
        self.config = config
        self.ultima: Varredura | None = None
        self._trava = threading.Lock()

    # ---------------------------------------------------------------- varredura
    def escanear(self, com_ocr: bool = True) -> Varredura:
        with self._trava:
            img, origem = capturar_tela()
            titulo, ui = "", []
            try:
                titulo, ui = elementos_acessibilidade()
            except Exception as e:
                print(f"[visão] acessibilidade falhou: {e}")
            linhas = []
            if com_ocr:
                try:
                    linhas = ocr(img, self.config.get("visao.idioma_ocr", "pt-BR"))
                except Exception as e:
                    print(f"[visão] OCR falhou: {e}")
            self.ultima = Varredura(time.time(), titulo, mesclar(ui, linhas, origem), img, origem)
            return self.ultima

    def recente(self, segundos: float = 4.0) -> Varredura:
        if self.ultima is None or time.time() - self.ultima.momento > segundos:
            return self.escanear()
        return self.ultima

    # ---------------------------------------------------------------- IA de visão
    def _imagem_b64(self, img, largura_max: int = 1344) -> tuple[str, int, int]:
        from PIL import Image
        if img.width > largura_max:
            img = img.resize((largura_max, int(img.height * largura_max / img.width)), Image.BILINEAR)
        buf = io.BytesIO()
        img.save(buf, format="JPEG", quality=82)
        return base64.b64encode(buf.getvalue()).decode(), img.width, img.height

    def _perguntar_ia(self, img, pergunta: str, timeout: float = 120) -> str:
        url = str(self.config.get("cerebro.url", "http://localhost:11434")).rstrip("/")
        modelo = self.config.get("visao.modelo", "qwen3-vl:8b")
        b64, _, _ = self._imagem_b64(img)
        corpo = {"model": modelo, "stream": False, "keep_alive": "30m", "think": False,
                 "options": {"temperature": 0.1},
                 "messages": [{"role": "user", "content": pergunta, "images": [b64]}]}
        r = requests.post(url + "/api/chat", json=corpo, timeout=timeout)
        if r.status_code == 400 and "think" in r.text.lower():
            corpo.pop("think")
            r = requests.post(url + "/api/chat", json=corpo, timeout=timeout)
        if r.status_code == 404:
            raise RuntimeError(f"Modelo de visão {modelo} não instalado (ollama pull {modelo})")
        r.raise_for_status()
        return r.json().get("message", {}).get("content", "")

    def descrever(self, pergunta: str = "") -> str:
        v = self.recente()
        p = ("Esta é uma captura da tela do computador do usuário. Em português, em até 5 frases curtas, "
             "diga qual app/janela está em foco e o que aparece de importante.")
        if pergunta:
            p += f" Responda também, com precisão: {pergunta}"
        return self._perguntar_ia(v.imagem, p)

    def localizar_com_ia(self, alvo: str) -> tuple[int, int] | None:
        v = self.recente()
        _, w, h = self._imagem_b64(v.imagem)
        resp = self._perguntar_ia(v.imagem, (
            f'Na captura de tela, encontre: "{alvo}". Responda SOMENTE um JSON {{"x": X, "y": Y}} com o centro '
            f'desse elemento, usando coordenadas de 0 a 1000 (0,0 = canto superior esquerdo). '
            f'Se não existir, responda {{"nao_encontrado": true}}.'))
        ponto = interpretar_ponto(resp, w, h)
        if ponto is None:
            return None
        escala = v.imagem.width / w
        return int(ponto[0] * escala) + v.origem_tela[0], int(ponto[1] * escala) + v.origem_tela[1]

    # ---------------------------------------------------------------- ações
    def resolver_alvo(self, alvo: str) -> tuple[int, int, str] | None:
        """(x, y, descrição) de um alvo: número, texto, ou o que a IA de visão achar."""
        v = self.recente()
        e = achar(alvo, v.elementos)
        if e is None and not re.fullmatch(r"#?\d+", alvo.strip()):
            v = self.escanear()  # a tela pode ter mudado
            e = achar(alvo, v.elementos)
        if e is not None:
            x, y = e.centro
            return x, y, e.texto
        if self.config.get("visao.usar_ia", True):
            p = self.localizar_com_ia(alvo)
            if p:
                return p[0], p[1], alvo
        return None

    def clicar(self, x: int, y: int, tipo: str = "esquerdo", mira=None, rotulo: str = "") -> None:
        import pyautogui
        pyautogui.FAILSAFE = True  # mouse no canto superior esquerdo = parar
        if mira:
            mira(x, y, rotulo)
            time.sleep(0.45)
        pyautogui.moveTo(x, y, duration=0.18)
        if tipo == "duplo":
            pyautogui.doubleClick()
        elif tipo == "direito":
            pyautogui.rightClick()
        else:
            pyautogui.click()
        self.ultima = None  # a tela mudou

    def rolar(self, direcao: str, quantidade: int = 5) -> None:
        import pyautogui
        passo = max(1, min(int(quantidade), 30)) * 120
        pyautogui.scroll(passo if normalizar(direcao) in ("cima", "up", "subir") else -passo)
        self.ultima = None

    def focar_janela(self, nome: str) -> str | None:
        if not NO_WINDOWS:
            return None
        import uiautomation as auto
        alvo = normalizar(nome)
        with auto.UIAutomationInitializerInThread():
            janelas = auto.GetRootControl().GetChildren()
            nomes = [(j, normalizar(j.Name or "")) for j in janelas if j.Name]
            escolhida = next((j for j, n in nomes if alvo in n), None)
            if escolhida is None:
                parecidos = difflib.get_close_matches(alvo, [n for _, n in nomes], n=1, cutoff=0.5)
                escolhida = next((j for j, n in nomes if parecidos and n == parecidos[0]), None)
            if escolhida is None:
                return None
            try:
                escolhida.SetActive()
            except Exception:
                escolhida.SetFocus()
            self.ultima = None
            return escolhida.Name


_VISAO: Visao | None = None


def obter(config) -> Visao:
    global _VISAO
    if _VISAO is None:
        _VISAO = Visao(config)
    return _VISAO
