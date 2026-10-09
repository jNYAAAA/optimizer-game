"""Темы оформления приложения: тёмная («киберпанк-минимализм») и светлая.

Палитры описаны словарями, QSS-шаблон подставляет цвета через ``str.format``.
Переключение делается в рантайме: ``set_current`` + ``styles()``.
"""
from __future__ import annotations

MONO = '"Cascadia Mono", "Consolas", "JetBrains Mono", "Courier New", monospace'

DARK = {
    "MONO": MONO,
    "BG": "#06070c",
    "BG_ALT": "#0a0c13",
    "PANEL": "#0d1019",
    "BORDER": "#1b2130",
    "ACCENT": "#22e0ff",
    "ACCENT_DIM": "#12a7c4",
    "MAGENTA": "#ff2e97",
    "TEXT": "#d9e6ee",
    "TEXT_DIM": "#5d7484",
    "TEXT_FAINT": "#33414d",
    "ON_ACCENT": "#04060a",
    "DANGER": "#ff3d5a",
    "WARN": "#f5d90a",
    "OK": "#39ff9e",
}

LIGHT = {
    "MONO": MONO,
    "BG": "#eef1f5",
    "BG_ALT": "#e2e8ef",
    "PANEL": "#ffffff",
    "BORDER": "#c9d4df",
    "ACCENT": "#0a7ea4",
    "ACCENT_DIM": "#086685",
    "MAGENTA": "#b0197a",
    "TEXT": "#16202a",
    "TEXT_DIM": "#5c6b79",
    "TEXT_FAINT": "#9aa7b3",
    "ON_ACCENT": "#ffffff",
    "DANGER": "#c62828",
    "WARN": "#a86e00",
    "OK": "#177a48",
}

PALETTES = {"dark": DARK, "light": LIGHT}

_current = "dark"


def palette(mode: str | None = None) -> dict:
    return PALETTES.get(mode or _current, DARK)


def current() -> str:
    return _current


def set_current(mode: str) -> None:
    global _current
    if mode in PALETTES:
        _current = mode


def is_dark(mode: str | None = None) -> bool:
    return (mode or _current) == "dark"


def risk_colors(mode: str | None = None) -> dict[str, str]:
    p = palette(mode)
    return {"low": p["OK"], "medium": p["WARN"], "high": p["DANGER"]}


# Для обратной совместимости (тёмная тема).
RISK_COLORS = risk_colors("dark")

_TEMPLATE = """
    * {{
        font-family: {MONO};
        font-size: 13px;
        color: {TEXT};
    }}
    QMainWindow, QWidget#Root {{
        background: {BG};
    }}
    QScrollArea {{
        background: {BG};
        border: none;
    }}
    QScrollArea > QWidget {{
        background: {BG};
    }}
    QScrollArea > QWidget > QWidget {{
        background: transparent;
    }}
    QWidget#Sidebar {{
        background: {BG_ALT};
        border-right: 1px solid {BORDER};
    }}
    QLabel#AppTitle {{
        font-size: 16px;
        font-weight: 700;
        color: {ACCENT};
        padding: 20px 16px 12px 16px;
    }}
    QLabel#PageTitle {{
        font-size: 20px;
        font-weight: 700;
        color: {TEXT};
    }}
    QLabel#PageHint {{
        color: {TEXT_DIM};
        font-size: 12px;
    }}
    QLabel#Value {{
        color: {TEXT};
        font-size: 14px;
        font-weight: 600;
    }}
    QLabel#Caption {{
        color: {TEXT_DIM};
        font-size: 11px;
    }}
    QFrame#AccentLine {{
        background: {ACCENT};
        border: none;
    }}

    QListWidget#Nav {{
        background: transparent;
        border: none;
        outline: none;
        padding: 6px;
    }}
    QListWidget#Nav::item {{
        padding: 9px 10px;
        border-left: 2px solid transparent;
        color: {TEXT_DIM};
    }}
    QListWidget#Nav::item:hover {{
        color: {TEXT};
        background: {PANEL};
    }}
    QListWidget#Nav::item:selected {{
        color: {ACCENT};
        border-left: 2px solid {ACCENT};
        background: {PANEL};
        font-weight: 600;
    }}

    QFrame#Card {{
        background: {PANEL};
        border: 1px solid {BORDER};
        border-left: 2px solid {ACCENT};
        border-radius: 2px;
    }}
    QFrame#Card QLabel#CardTitle {{
        color: {ACCENT};
        font-size: 12px;
        font-weight: 700;
    }}

    QLabel#Badge {{
        border-radius: 2px;
        padding: 2px 7px;
        font-size: 10px;
        font-weight: 700;
    }}

    QPushButton {{
        background: transparent;
        border: 1px solid {BORDER};
        border-radius: 2px;
        padding: 8px 14px;
        color: {TEXT};
    }}
    QPushButton:hover {{
        border-color: {ACCENT};
        color: {ACCENT};
    }}
    QPushButton:pressed {{
        background: {PANEL};
    }}
    QPushButton:disabled {{
        color: {TEXT_FAINT};
        border-color: {BORDER};
    }}
    QPushButton#Primary {{
        background: {ACCENT};
        border: 1px solid {ACCENT};
        color: {ON_ACCENT};
        font-weight: 700;
    }}
    QPushButton#Primary:hover {{
        background: {ACCENT_DIM};
        border-color: {ACCENT_DIM};
        color: {ON_ACCENT};
    }}
    QPushButton#Primary:disabled {{
        background: {PANEL};
        border-color: {BORDER};
        color: {TEXT_FAINT};
    }}
    QPushButton#Danger {{
        color: {DANGER};
        border-color: {DANGER};
    }}
    QPushButton#Danger:hover {{
        background: {DANGER};
        border-color: {DANGER};
        color: {ON_ACCENT};
    }}
    QPushButton#Segment {{
        padding: 7px 16px;
        color: {TEXT_DIM};
        border: 1px solid {BORDER};
        background: transparent;
        font-weight: 600;
    }}
    QPushButton#Segment:hover {{
        color: {TEXT};
        border-color: {ACCENT};
    }}
    QPushButton#Segment:checked {{
        background: {ACCENT};
        border-color: {ACCENT};
        color: {ON_ACCENT};
    }}

    QProgressBar {{
        background: {BG};
        border: 1px solid {BORDER};
        border-radius: 2px;
        height: 14px;
        text-align: center;
        color: {TEXT_DIM};
        font-size: 10px;
    }}
    QProgressBar::chunk {{
        background: {ACCENT};
    }}

    QLineEdit, QComboBox, QSpinBox {{
        background: {PANEL};
        border: 1px solid {BORDER};
        border-radius: 2px;
        padding: 6px 10px;
        color: {TEXT};
    }}
    QLineEdit:focus, QComboBox:focus, QSpinBox:focus {{
        border-color: {ACCENT};
    }}
    QComboBox::drop-down {{
        border: none;
        width: 18px;
    }}
    QComboBox QAbstractItemView {{
        background: {PANEL};
        border: 1px solid {ACCENT};
        selection-background-color: {ACCENT};
        selection-color: {ON_ACCENT};
        outline: none;
    }}

    QTableWidget, QTableWidget QTableCornerButton::section {{
        background: {PANEL};
        border: 1px solid {BORDER};
        border-radius: 2px;
        gridline-color: {BORDER};
        selection-background-color: {ACCENT};
        selection-color: {ON_ACCENT};
        alternate-background-color: {BG_ALT};
        outline: none;
    }}
    QTableWidget::item {{
        padding: 4px;
    }}
    QTableView::indicator {{
        width: 14px;
        height: 14px;
        border: 1px solid {BORDER};
        border-radius: 1px;
        background: {BG};
    }}
    QTableView::indicator:checked {{
        background: {ACCENT};
        border-color: {ACCENT};
    }}
    QHeaderView::section {{
        background: {BG_ALT};
        border: none;
        border-right: 1px solid {BORDER};
        border-bottom: 1px solid {ACCENT};
        padding: 8px;
        color: {TEXT_DIM};
        font-weight: 700;
    }}

    QPlainTextEdit {{
        background: {BG};
        border: 1px solid {BORDER};
        border-radius: 2px;
        padding: 6px;
        color: {TEXT_DIM};
        font-size: 12px;
    }}

    QScrollBar:vertical {{
        background: transparent;
        width: 10px;
        margin: 2px;
    }}
    QScrollBar::handle:vertical {{
        background: {BORDER};
        border-radius: 1px;
        min-height: 30px;
    }}
    QScrollBar::handle:vertical:hover {{
        background: {ACCENT_DIM};
    }}
    QScrollBar:horizontal {{
        background: transparent;
        height: 10px;
        margin: 2px;
    }}
    QScrollBar::handle:horizontal {{
        background: {BORDER};
        border-radius: 1px;
        min-width: 30px;
    }}
    QScrollBar::handle:horizontal:hover {{
        background: {ACCENT_DIM};
    }}
    QScrollBar::add-line, QScrollBar::sub-line {{
        height: 0;
        width: 0;
    }}

    QStatusBar {{
        background: {BG_ALT};
        border-top: 1px solid {BORDER};
        color: {TEXT_DIM};
        font-size: 11px;
    }}

    QCheckBox {{
        spacing: 8px;
        color: {TEXT};
    }}
    QCheckBox::indicator {{
        width: 14px;
        height: 14px;
        border: 1px solid {BORDER};
        border-radius: 1px;
        background: {BG};
    }}
    QCheckBox::indicator:hover {{
        border-color: {ACCENT};
    }}
    QCheckBox::indicator:checked {{
        background: {ACCENT};
        border-color: {ACCENT};
    }}

    QToolTip {{
        background: {PANEL};
        color: {TEXT};
        border: 1px solid {ACCENT};
        padding: 4px;
    }}
"""


def styles(mode: str | None = None) -> str:
    return _TEMPLATE.format(**palette(mode))
