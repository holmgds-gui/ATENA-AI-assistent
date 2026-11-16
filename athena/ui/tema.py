"""Visual HUD sci-fi da ATHENA: fundo com grade, bordas angulares, fontes tech e cor de destaque da paleta."""
from __future__ import annotations

from pathlib import Path

from PySide6.QtGui import QColor, QFontDatabase

FUNDO = "#04070B"
SUPERFICIE = "#0A1018"
SUPERFICIE_2 = "#0F1823"
LINHA = "#1C2A3A"
TEXTO = "#E6EEF7"
APAGADO = "#7E8FA3"
DESTAQUE = "#2E9BFF"      # muda com a paleta (aplicar_paleta)
ALERTA = "#FF6B8B"       # aviso (sem amarelo)
PERIGO = "#FF4A5C"
OK = "#3BE8A0"

FONTE = '"Rajdhani", "Segoe UI", sans-serif'
FONTE_TITULO = '"Orbitron", "Rajdhani", "Segoe UI", sans-serif'
FONTE_MONO = '"Share Tech Mono", "Consolas", monospace'

_PASTA_FONTES = Path(__file__).resolve().parent / "fontes"


def carregar_fontes() -> None:
    for arq in _PASTA_FONTES.glob("*.ttf"):
        QFontDatabase.addApplicationFont(str(arq))


def _mix(hex_a: str, hex_b: str, t: float) -> str:
    a, b = QColor(hex_a), QColor(hex_b)
    return QColor(int(a.red() + (b.red() - a.red()) * t), int(a.green() + (b.green() - a.green()) * t),
                  int(a.blue() + (b.blue() - a.blue()) * t)).name()


def rgba(hex_cor: str, alpha: float) -> str:
    c = QColor(hex_cor)
    return f"rgba({c.red()},{c.green()},{c.blue()},{int(alpha * 255)})"


def cor(hex_cor: str, alpha: float = 1.0) -> QColor:
    c = QColor(hex_cor)
    c.setAlphaF(max(0.0, min(1.0, alpha)))
    return c


def cores_da_config(config) -> tuple[str, str]:
    """(primária, secundária) da paleta escolhida."""
    from .holograma import PALETAS
    nome = config.get("interface.paleta", "azul")
    if nome == "personalizada":
        prim = config.get("interface.cor_personalizada") or "#2E9BFF"
        return prim, _mix(prim, "#FFFFFF", 0.6)
    _, prim, sec = PALETAS.get(nome, PALETAS["azul"])
    return prim, sec


def aplicar_paleta(config) -> str:
    """Muda a cor de destaque da interface toda e devolve o estilo (QSS) pronto."""
    global DESTAQUE, FUNDO_SEL
    DESTAQUE = cores_da_config(config)[0]
    FUNDO_SEL = _mix(DESTAQUE, FUNDO, 0.88)
    return gerar_qss()


FUNDO_SEL = _mix(DESTAQUE, FUNDO, 0.88)


def gerar_qss() -> str:
    D = DESTAQUE
    return f"""
* {{ font-family: {FONTE}; color: {TEXTO}; font-size: 15px; font-weight: 500; }}
QWidget#janela, QDialog#janela {{ background: {FUNDO}; }}
QWidget#transparente, QStackedWidget, QScrollArea, QScrollArea > QWidget > QWidget {{ background: transparent; border: none; }}

QLabel {{ background: transparent; }}
QLabel#titulo {{ font-family: {FONTE_TITULO}; font-size: 24px; font-weight: 700; letter-spacing: 3px; }}
QLabel#subtitulo {{ color: {APAGADO}; font-size: 15.5px; }}
QLabel#apagado {{ color: {APAGADO}; font-size: 13.5px; }}
QLabel#secao {{ color: {D}; font-family: {FONTE_MONO}; font-size: 11.5px; letter-spacing: 2px; }}
QLabel#mono {{ font-family: {FONTE_MONO}; }}

QPushButton {{
    background: {rgba(D, 0.04)}; border: 1px solid {rgba(D, 0.35)}; border-radius: 2px;
    padding: 9px 18px; font-weight: 700; letter-spacing: 1.5px; color: {TEXTO};
}}
QPushButton:hover {{ background: {rgba(D, 0.12)}; border-color: {D}; }}
QPushButton:pressed {{ background: {rgba(D, 0.22)}; }}
QPushButton:disabled {{ color: {APAGADO}; border-color: {LINHA}; background: transparent; }}
QPushButton#primario {{ background: {rgba(D, 0.16)}; color: {_mix(D, '#FFFFFF', 0.35)}; border: 1px solid {D}; }}
QPushButton#primario:hover {{ background: {rgba(D, 0.3)}; color: #FFFFFF; }}
QPushButton#primario:disabled {{ background: transparent; color: {APAGADO}; border-color: {LINHA}; }}
QPushButton#link {{ background: transparent; border: none; color: {APAGADO}; padding: 6px 8px; letter-spacing: 2px; }}
QPushButton#link:hover {{ color: {D}; }}

QLineEdit, QTextEdit, QPlainTextEdit, QComboBox, QSpinBox, QDoubleSpinBox, QTextBrowser, QListWidget {{
    background: {rgba('#000000', 0.35)}; border: 1px solid {rgba(D, 0.22)}; border-radius: 2px; padding: 8px 10px;
    selection-background-color: {rgba(D, 0.45)}; selection-color: #FFFFFF;
}}
QLineEdit:focus, QTextEdit:focus, QPlainTextEdit:focus, QComboBox:focus, QSpinBox:focus, QDoubleSpinBox:focus {{
    border: 1px solid {D}; background: {rgba(D, 0.05)};
}}
QComboBox::drop-down {{ border: none; width: 24px; }}
QComboBox QAbstractItemView {{ background: {SUPERFICIE}; border: 1px solid {rgba(D, 0.4)}; selection-background-color: {rgba(D, 0.25)}; }}
QSpinBox::up-button, QSpinBox::down-button, QDoubleSpinBox::up-button, QDoubleSpinBox::down-button {{ width: 0; border: none; }}
QListWidget::item {{ padding: 6px; border-bottom: 1px solid {LINHA}; }}
QListWidget::item:selected {{ background: {rgba(D, 0.18)}; color: #FFFFFF; }}

QSlider::groove:horizontal {{ height: 2px; background: {LINHA}; }}
QSlider::sub-page:horizontal {{ background: {D}; }}
QSlider::handle:horizontal {{ background: {D}; width: 10px; height: 18px; margin: -8px 0; border-radius: 1px; }}

QScrollBar:vertical {{ background: transparent; width: 6px; margin: 2px; }}
QScrollBar::handle:vertical {{ background: {rgba(D, 0.35)}; min-height: 30px; }}
QScrollBar::add-line, QScrollBar::sub-line {{ height: 0; width: 0; }}
QScrollBar::add-page, QScrollBar::sub-page {{ background: transparent; }}

QRadioButton, QCheckBox {{ spacing: 10px; padding: 4px 0; background: transparent; }}
QRadioButton::indicator {{ width: 12px; height: 12px; border: 1px solid {rgba(D, 0.6)}; border-radius: 7px; }}
QRadioButton::indicator:checked {{ background: {D}; border: 3px solid {FUNDO}; outline: 1px solid {D}; }}
QCheckBox::indicator {{ width: 13px; height: 13px; border: 1px solid {rgba(D, 0.6)}; border-radius: 1px; }}
QCheckBox::indicator:checked {{ background: {D}; }}

QMenu {{ background: {SUPERFICIE}; border: 1px solid {rgba(D, 0.45)}; padding: 6px; }}
QMenu::item {{ padding: 8px 20px; letter-spacing: 1px; }}
QMenu::item:selected {{ background: {rgba(D, 0.18)}; color: #FFFFFF; }}
QMenu::separator {{ height: 1px; background: {LINHA}; margin: 4px 8px; }}
QToolTip {{ background: {SUPERFICIE}; color: {TEXTO}; border: 1px solid {rgba(D, 0.5)}; padding: 6px; }}
QFormLayout QLabel {{ color: {APAGADO}; }}
"""


QSS = gerar_qss()
