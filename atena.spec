# -*- mode: python ; coding: utf-8 -*-
# Receita do PyInstaller pra gerar a pasta dist/ATENA com o ATENA.exe
# Uso: pyinstaller atena.spec --noconfirm
from PyInstaller.utils.hooks import collect_all

datas = [("config", "config"), ("atena/ui/fontes", "atena/ui/fontes"), ("assets", "assets")]
import os
if os.path.isdir("modelos"):
    datas.append(("modelos", "modelos"))
binaries, hiddenimports = [], []

for pacote in ["vosk", "faster_whisper", "ctranslate2", "uiautomation", "winrt", "edge_tts", "pyttsx3",
               "pynput", "ddgs", "primp", "av", "tokenizers", "comtypes", "sounddevice", "_sounddevice_data",
               "pygame", "mss", "pyautogui", "pyscreeze", "pymsgbox", "pytweening", "mouseinfo"]:
    try:
        d, b, h = collect_all(pacote)
        datas += d
        binaries += b
        hiddenimports += h
    except Exception as e:
        print(f"[spec] pulando {pacote}: {e}")

hiddenimports += ["pyttsx3.drivers", "pyttsx3.drivers.sapi5", "pynput.keyboard._win32", "pynput.mouse._win32",
                  "win32timezone", "atena.ui.app", "atena.visao", "atena.monitor", "atena.telegram"]

a = Analysis(
    ["main.py"],
    pathex=["."],
    binaries=binaries,
    datas=datas,
    hiddenimports=hiddenimports,
    excludes=["tkinter", "matplotlib", "PyQt5", "PyQt6", "IPython", "pytest"],
    noarchive=False,
)
pyz = PYZ(a.pure)
exe = EXE(
    pyz,
    a.scripts,
    [],
    exclude_binaries=True,
    name="ATENA",
    icon="assets/atena.ico",
    console=False,
    upx=False,
    version=None,
)
coll = COLLECT(exe, a.binaries, a.datas, name="ATENA", upx=False)
