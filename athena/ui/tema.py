"""Cores e estilo visual da ATHENA (tema escuro futurista)."""
from PySide6.QtGui import QColor

FUNDO = "#0A0E14"
SUPERFICIE = "#111823"
SUPERFICIE_2 = "#16202D"
LINHA = "#223044"
TEXTO = "#E8F1FA"
APAGADO = "#8193A8"
DESTAQUE = "#FFA62B"      # muda com a paleta escolhida (aplicar_paleta)
DESTAQUE_2 = "#7A5CFF"    # violeta (pensando)
OURO = "#FFC861"
PERIGO = "#FF5C6C"
OK = "#45E0A0"

# Cores do orbe em cada estado
CORES_ESTADO = {
    "dormindo": QColor(61, 220, 255),
    "ouvindo": QColor(90, 235, 255),
    "pensando": QColor(140, 110, 255),
    "falando": QColor(61, 220, 255),
    "mudo": QColor(110, 122, 140),
    "erro": QColor(255, 92, 108),
}

FONTE = '"Segoe UI Variable Text", "Segoe UI", "SF Pro Text", "Inter", "Ubuntu", sans-serif'
FONTE_TITULO = '"Segoe UI Variable Display", "Segoe UI", "SF Pro Display", "Inter", sans-serif'

def _mix(hex_a: str, hex_b: str, t: float) -> str:
    a, b = QColor(hex_a), QColor(hex_b)
    return QColor(int(a.red() + (b.red() - a.red()) * t), int(a.green() + (b.green() - a.green()) * t),
                  int(a.blue() + (b.blue() - a.blue()) * t)).name()


def cores_da_config(config) -> tuple[str, str]:
    """(primária, secundária) da paleta escolhida."""
    from .holograma import PALETAS
    nome = config.get("interface.paleta", "dourado")
    if nome == "personalizada":
        prim = config.get("interface.cor_personalizada") or "#FFA62B"
        return prim, _mix(prim, "#FFFFFF", 0.6)
    _, prim, sec = PALETAS.get(nome, PALETAS["dourado"])
    return prim, sec


def aplicar_paleta(config) -> str:
    """Muda a cor de destaque de toda a interface e devolve o estilo (QSS) pronto."""
    global DESTAQUE, FUNDO_SEL
    DESTAQUE = cores_da_config(config)[0]
    FUNDO_SEL = _mix(DESTAQUE, FUNDO, 0.86)
    return gerar_qss()


FUNDO_SEL = _mix(DESTAQUE, FUNDO, 0.86)


def gerar_qss() -> str:
    CLARO = _mix(DESTAQUE, "#FFFFFF", 0.3)
    ESCURO = _mix(DESTAQUE, FUNDO, 0.7)
    ESCURO_TXT = _mix(DESTAQUE, FUNDO, 0.4)
    return f"""
* {{ font-family: {FONTE}; color: {TEXTO}; font-size: 14px; }}
QWidget#janela, QDialog#janela {{ background: {FUNDO}; }}
QLabel#titulo {{ font-family: {FONTE_TITULO}; font-size: 28px; font-weight: 700; }}
QLabel#subtitulo {{ color: {APAGADO}; font-size: 14.5px; }}
QLabel#apagado {{ color: {APAGADO}; font-size: 12.5px; }}
QLabel#secao {{ color: {APAGADO}; font-size: 11px; font-weight: 700; letter-spacing: 1.5px; }}

QPushButton {{
    background: {SUPERFICIE_2}; border: 1px solid {LINHA}; border-radius: 12px;
    padding: 10px 18px; font-weight: 600;
}}
QPushButton:hover {{ border-color: {DESTAQUE}; }}
QPushButton:disabled {{ color: {APAGADO}; border-color: {LINHA}; }}
QPushButton#primario {{ background: {DESTAQUE}; color: #00131A; border: none; }}
QPushButton#primario:hover {{ background: {CLARO}; }}
QPushButton#primario:disabled {{ background: {ESCURO}; color: {ESCURO_TXT}; }}
QPushButton#link {{ background: transparent; border: none; color: {APAGADO}; padding: 6px 8px; }}
QPushButton#link:hover {{ color: {TEXTO}; }}

QLineEdit, QTextEdit, QPlainTextEdit, QComboBox, QSpinBox, QDoubleSpinBox {{
    background: {SUPERFICIE}; border: 1px solid {LINHA}; border-radius: 10px; padding: 9px 11px;
    selection-background-color: {DESTAQUE}; selection-color: #00131A;
}}
QLineEdit:focus, QTextEdit:focus, QPlainTextEdit:focus, QComboBox:focus {{ border-color: {DESTAQUE}; }}
QComboBox::drop-down {{ border: none; width: 26px; }}
QComboBox QAbstractItemView {{ background: {SUPERFICIE}; border: 1px solid {LINHA}; selection-background-color: {SUPERFICIE_2}; }}

QSlider::groove:horizontal {{ height: 4px; background: {LINHA}; border-radius: 2px; }}
QSlider::sub-page:horizontal {{ background: {DESTAQUE}; border-radius: 2px; }}
QSlider::handle:horizontal {{ background: {TEXTO}; width: 16px; height: 16px; margin: -6px 0; border-radius: 8px; }}

QTabWidget::pane {{ border: none; }}
QTabBar::tab {{ background: transparent; color: {APAGADO}; padding: 10px 14px; border: none;
               border-bottom: 2px solid transparent; font-weight: 600; }}
QTabBar::tab:selected {{ color: {TEXTO}; border-bottom-color: {DESTAQUE}; }}
QTabBar::tab:hover {{ color: {TEXTO}; }}

QScrollArea {{ background: transparent; border: none; }}
QScrollArea > QWidget > QWidget {{ background: transparent; }}
QScrollBar:vertical {{ background: transparent; width: 8px; margin: 2px; }}
QScrollBar::handle:vertical {{ background: {LINHA}; border-radius: 4px; min-height: 30px; }}
QScrollBar::add-line, QScrollBar::sub-line {{ height: 0; }}

QFrame#cartao {{ background: {SUPERFICIE}; border: 1px solid {LINHA}; border-radius: 14px; }}
QFrame#cartao[selecionado="true"] {{ border: 1.5px solid {DESTAQUE}; background: {FUNDO_SEL}; }}

QRadioButton {{ spacing: 10px; padding: 4px 0; }}
QRadioButton::indicator {{ width: 16px; height: 16px; border-radius: 9px; border: 2px solid {LINHA}; }}
QRadioButton::indicator:checked {{ background: {DESTAQUE}; border-color: {DESTAQUE}; }}

QCheckBox {{ spacing: 10px; padding: 4px 0; }}
QCheckBox::indicator {{ width: 16px; height: 16px; border-radius: 5px; border: 2px solid {LINHA}; }}
QCheckBox::indicator:checked {{ background: {DESTAQUE}; border-color: {DESTAQUE}; }}
QSpinBox::up-button, QSpinBox::down-button, QDoubleSpinBox::up-button, QDoubleSpinBox::down-button {{ width: 0; border: none; }}
QMenu {{ background: {SUPERFICIE}; border: 1px solid {LINHA}; border-radius: 10px; padding: 6px; }}
QMenu::item {{ padding: 8px 18px; border-radius: 6px; }}
QMenu::item:selected {{ background: {SUPERFICIE_2}; }}
QToolTip {{ background: {SUPERFICIE}; color: {TEXTO}; border: 1px solid {LINHA}; padding: 6px; }}
"""


QSS = gerar_qss()
