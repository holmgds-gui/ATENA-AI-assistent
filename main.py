"""ATENA — Assistente Tecnológica de Execução e Navegação Artificial.

Uso:
    python main.py                  abre a ATENA com orbe, voz e microfone
    python main.py --sem-microfone  abre sem microfone (só por texto no painel)
    python main.py --terminal       conversa pelo terminal, sem interface (bom pra testar)
    python main.py --apresentacao   mostra de novo a configuração da primeira vez
"""
import os
import sys


def _preparar_exe():
    """No .exe (sem janela de terminal), manda as mensagens pra um arquivo de log."""
    if getattr(sys, "frozen", False) and (sys.stdout is None or sys.stderr is None):
        from atena.config import PASTA_USUARIO
        PASTA_USUARIO.mkdir(parents=True, exist_ok=True)
        log = open(PASTA_USUARIO / "atena.log", "a", encoding="utf-8", buffering=1)
        sys.stdout = sys.stdout or log
        sys.stderr = sys.stderr or log


def verificar() -> int:
    """Confere se todas as peças carregam (usado pra testar o .exe). Grava o resultado em verificar.txt."""
    import importlib
    import traceback
    linhas, falhas = [], 0
    modulos = ["PySide6.QtWidgets", "requests", "yaml", "numpy", "sounddevice", "vosk", "faster_whisper",
               "ctranslate2", "edge_tts", "pygame", "pyttsx3", "pyautogui", "pyperclip", "psutil", "pynput",
               "ddgs", "mss", "PIL", "atena.assistente", "atena.ui.app", "atena.visao", "atena.monitor",
               "atena.telegram", "atena.agenda", "atena.habilidades"]
    if sys.platform == "win32":
        modulos += ["uiautomation", "winrt.windows.media.ocr", "winrt.windows.graphics.imaging",
                    "winrt.windows.storage.streams", "winrt.windows.globalization"]
    for m in modulos:
        try:
            importlib.import_module(m)
            linhas.append(f"OK    {m}")
        except Exception as e:
            falhas += 1
            linhas.append(f"FALHA {m}: {e!r}")
    from atena.config import Config
    cfg = Config()
    linhas.append(f"OK    config ({len(cfg.geral)} seções); vosk existe: "
                  f"{cfg.caminho(cfg.get('ativacao.modelo_vosk')).exists()}")
    try:  # testes reais no Windows (não derrubam o resultado)
        from PIL import Image, ImageDraw
        from atena import visao
        img = Image.new("RGB", (600, 120), "white")
        ImageDraw.Draw(img).text((20, 40), "ATENA 2026 OK", fill="black", font_size=48)
        linhas.append(f"INFO  OCR leu: {[l[0] for l in visao.ocr(img)]}")
        titulo, ui = visao.elementos_acessibilidade()
        linhas.append(f"INFO  acessibilidade: janela '{titulo}', {len(ui)} elementos")
        tela, origem = visao.capturar_tela()
        linhas.append(f"INFO  captura de tela: {tela.size} em {origem}")
    except Exception:
        linhas.append("AVISO visão:\n" + traceback.format_exc())
    destino = os.environ.get("ATENA_VERIFICAR", "verificar.txt")
    with open(destino, "w", encoding="utf-8") as f:
        f.write("\n".join(linhas) + f"\n\n{falhas} falha(s)\n")
    return 1 if falhas else 0

    from atena.assistente import Assistente
    from atena.config import Config

    cfg = Config()
    if not cfg.personalidade.get("como_me_chamar"):
        nome = input("Como a ATENA deve te chamar? ").strip()
        if nome:
            cfg.salvar_personalidade({"como_me_chamar": nome})

    def evento(tipo, dados=None):
        if tipo == "atena":
            print(f"\n{cfg.nome_ia}: {dados}")
        elif tipo == "acao" and dados:
            print(f"   [ação] {dados}")

    a = Assistente(cfg, evento=evento, usar_microfone=False)
    a.voz.falar = lambda texto, ao_comecar=None: None  # no terminal, só texto
    a._confirmar = lambda pergunta: input(f"\n{cfg.nome_ia}: {pergunta} (s/n) ").strip().lower().startswith("s")
    print(f"{cfg.nome_ia} no terminal. Escreva 'sair' pra fechar.")
    while True:
        try:
            t = input("\nVocê: ").strip()
        except (EOFError, KeyboardInterrupt):
            break
        if t.lower() in ("sair", "exit", "quit"):
            break
        a.processar(t)


if __name__ == "__main__":
    _preparar_exe()
    if "--verificar" in sys.argv:
        sys.exit(verificar())
    if "--terminal" in sys.argv:
        terminal()
    else:
        if "--apresentacao" in sys.argv:
            from atena.config import Config
            Config().salvar_geral({"primeira_vez": True})
        from atena.ui.app import main
        main()
