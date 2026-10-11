"""Тема оформления в стиле Windows 11 (тёмная).

Одна палитра; QSS-шаблон подставляет цвета через ``str.format``, галочки
чекбоксов берутся из PNG-ресурса.
"""
from __future__ import annotations

import os

from ..utils import resource_path

FONT = '"Segoe UI Variable Text", "Segoe UI", "Bahnschrift", "Verdana", sans-serif'
FONT_TITLE = '"Bahnschrift SemiBold", "Bahnschrift", "Segoe UI Variable Display", "Segoe UI", sans-serif'
FONT_MONO = '"Cascadia Mono", "Consolas", "Courier New", monospace'

DARK = {
    "NAME": "dark",
    "MONO": FONT,
    "FONT": FONT,
    "FONT_TITLE": FONT_TITLE,
    "FONT_MONO": FONT_MONO,
    "BG": "#1c2026",
    "BG_ALT": "rgba(38, 44, 52, 0.55)",
    "PANEL": "rgba(46, 52, 61, 0.72)",
    "BORDER": "rgba(120, 135, 155, 0.28)",
    "CONTROL": "rgba(46, 52, 61, 0.66)",
    "CONTROL_HOVER": "rgba(58, 66, 78, 0.72)",
    "CONTROL_PRESSED": "rgba(40, 46, 54, 0.8)",
    "ACCENT": "#60cdff",
    "ACCENT_DIM": "#4cc2ff",
    "ACCENT_SOFT": "rgba(96, 205, 255, 0.16)",
    "MAGENTA": "#ff2e97",
    "TEXT": "#ffffff",
    "TEXT_DIM": "#c9c9c9",
    "TEXT_FAINT": "#8a8a8a",
    "ON_ACCENT": "#003a5c",
    "DANGER": "#ff99a4",
    "WARN": "#fce100",
    "OK": "#6ccb5f",
}


def palette() -> dict:
    return DARK


def risk_colors() -> dict[str, str]:
    p = palette()
    return {"low": p["OK"], "medium": p["WARN"], "high": p["DANGER"]}


RISK_COLORS = risk_colors()


def _check_icon() -> str:
    return resource_path(os.path.join("assets", "check_dark.png")).replace("\\", "/")


_TEMPLATE = """
    * {{
        font-family: {FONT};
        font-size: 13px;
        color: {TEXT};
    }}
    QMainWindow, QWidget#Root {{
        background: {BG};
    }}
    QScrollArea {{
        background: transparent;
        border: none;
    }}
    QScrollArea > QWidget {{
        background: transparent;
    }}
    QScrollArea > QWidget > QWidget {{
        background: transparent;
    }}
    QWidget#Sidebar {{
        background: {BG_ALT};
        border-right: 1px solid {BORDER};
    }}
    QLabel#AppTitle {{
        font-family: {FONT_TITLE};
        font-size: 15px;
        font-weight: 600;
        color: {TEXT};
        padding: 18px 16px 8px 18px;
    }}
    QLabel#SidebarFooter {{
        color: {TEXT_FAINT};
        font-size: 11px;
        padding: 10px 8px 12px 8px;
    }}
    QLabel#PageTitle {{
        font-family: {FONT_TITLE};
        font-size: 22px;
        font-weight: 600;
        color: {TEXT};
    }}
    QLabel#PageHint {{
        color: {TEXT_DIM};
        font-size: 12px;
    }}
    QLabel#Value {{
        color: {TEXT};
        font-size: 13px;
        font-weight: 600;
    }}
    QLabel#Caption {{
        color: {TEXT_DIM};
        font-size: 12px;
    }}
    QFrame#AccentLine {{
        background: {ACCENT};
        border: none;
    }}
    QFrame#OptionRow {{
        background: {BG_ALT};
        border: 1px solid {BORDER};
        border-radius: 6px;
    }}
    QFrame#OptionRow:hover {{
        border-color: {ACCENT};
    }}

    QListWidget#Nav {{
        background: transparent;
        border: none;
        outline: none;
        padding: 4px 8px;
    }}
    QListWidget#Nav::item {{
        padding: 10px 12px;
        margin: 3px 0;
        border-radius: 8px;
        color: {TEXT};
    }}
    QListWidget#Nav::item:hover {{
        background: {CONTROL_HOVER};
    }}
    QListWidget#Nav::item:selected {{
        background: {ACCENT_SOFT};
        color: {TEXT};
        font-weight: 600;
    }}
    QListWidget#Nav::item:selected:hover {{
        background: {ACCENT_SOFT};
    }}

    QFrame#Card {{
        background: {PANEL};
        border: 1px solid {BORDER};
        border-radius: 8px;
    }}
    QFrame#Card QLabel#CardTitle {{
        font-family: {FONT_TITLE};
        color: {TEXT};
        font-size: 13px;
        font-weight: 600;
    }}

    QLabel#Badge {{
        border-radius: 4px;
        padding: 2px 8px;
        font-size: 11px;
        font-weight: 600;
    }}

    QPushButton {{
        background: {CONTROL};
        border: 1px solid {BORDER};
        border-radius: 5px;
        padding: 7px 16px;
        color: {TEXT};
        font-family: {FONT_TITLE};
        min-height: 18px;
    }}
    QPushButton:hover {{
        background: {CONTROL_HOVER};
    }}
    QPushButton:pressed {{
        background: {CONTROL_PRESSED};
        color: {TEXT_DIM};
    }}
    QPushButton:disabled {{
        background: transparent;
        color: {TEXT_FAINT};
        border-color: {BORDER};
    }}
    QPushButton#Primary {{
        background: {ACCENT};
        border: 1px solid transparent;
        border-radius: 5px;
        padding: 7px 18px;
        color: {ON_ACCENT};
        font-weight: 600;
    }}
    QPushButton#Primary:hover {{
        background: {ACCENT_DIM};
        color: {ON_ACCENT};
    }}
    QPushButton#Primary:pressed {{
        background: {ACCENT_DIM};
        color: {ON_ACCENT};
    }}
    QPushButton#Primary:disabled {{
        background: {CONTROL};
        border-color: {BORDER};
        color: {TEXT_FAINT};
    }}
    QPushButton#Danger {{
        background: transparent;
        color: {DANGER};
        border: 1px solid {BORDER};
    }}
    QPushButton#Danger:hover {{
        background: {CONTROL_HOVER};
        border-color: {DANGER};
        color: {DANGER};
    }}
    QPushButton#Segment {{
        background: {CONTROL};
        border: 1px solid {BORDER};
        border-radius: 5px;
        padding: 6px 14px;
        color: {TEXT};
        font-weight: 500;
    }}
    QPushButton#Segment:hover {{
        background: {CONTROL_HOVER};
    }}
    QPushButton#Segment:checked {{
        background: {ACCENT};
        border-color: {ACCENT};
        color: {ON_ACCENT};
        font-weight: 600;
    }}
    QPushButton#Segment:checked:hover {{
        background: {ACCENT_DIM};
        border-color: {ACCENT_DIM};
        color: {ON_ACCENT};
    }}
    QPushButton#Back {{
        color: {ACCENT};
        border: 1px solid {ACCENT};
        border-radius: 5px;
        padding: 8px 18px;
        font-weight: 600;
    }}
    QPushButton#Back:hover {{
        background: {ACCENT};
        border-color: {ACCENT};
        color: {ON_ACCENT};
    }}

    QProgressBar {{
        background: {CONTROL};
        border: none;
        border-radius: 3px;
        height: 6px;
        text-align: center;
        color: {TEXT_DIM};
        font-size: 10px;
    }}
    QProgressBar::chunk {{
        background: {ACCENT};
        border-radius: 3px;
    }}

    QLineEdit, QComboBox, QSpinBox {{
        background: {CONTROL};
        border: 1px solid {BORDER};
        border-radius: 4px;
        padding: 6px 10px;
        color: {TEXT};
        selection-background-color: {ACCENT};
        selection-color: {ON_ACCENT};
    }}
    QLineEdit:hover, QComboBox:hover {{
        background: {CONTROL_HOVER};
    }}
    QLineEdit:focus, QComboBox:focus, QSpinBox:focus {{
        border-bottom: 2px solid {ACCENT};
    }}
    QComboBox::drop-down {{
        border: none;
        width: 24px;
    }}
    QComboBox QAbstractItemView {{
        background: {PANEL};
        border: 1px solid {BORDER};
        border-radius: 6px;
        padding: 4px;
        selection-background-color: {CONTROL_HOVER};
        selection-color: {TEXT};
        outline: none;
    }}

    QTableWidget, QTableWidget QTableCornerButton::section {{
        background: {PANEL};
        border: 1px solid {BORDER};
        border-radius: 8px;
        gridline-color: transparent;
        selection-background-color: {ACCENT};
        selection-color: {ON_ACCENT};
        alternate-background-color: {BG_ALT};
        outline: none;
    }}
    QTableWidget::item {{
        padding: 6px 8px;
    }}
    QTableView::indicator {{
        width: 16px;
        height: 16px;
        border: 1px solid {TEXT_DIM};
        border-radius: 4px;
        background: transparent;
    }}
    QTableView::indicator:hover {{
        border-color: {ACCENT};
    }}
    QTableView::indicator:checked {{
        background: {ACCENT};
        border-color: {ACCENT};
        image: url("{CHECK}");
    }}
    QHeaderView::section {{
        background: transparent;
        border: none;
        border-bottom: 1px solid {BORDER};
        padding: 8px;
        color: {TEXT_DIM};
        font-family: {FONT_TITLE};
        font-weight: 600;
    }}

    QPlainTextEdit {{
        background: {PANEL};
        border: 1px solid {BORDER};
        border-radius: 6px;
        padding: 8px;
        color: {TEXT_DIM};
        font-family: {FONT_MONO};
        font-size: 12px;
    }}

    QScrollBar:vertical {{
        background: transparent;
        width: 12px;
        margin: 2px;
    }}
    QScrollBar::handle:vertical {{
        background: {BORDER};
        border-radius: 3px;
        min-height: 24px;
    }}
    QScrollBar::handle:vertical:hover {{
        background: {TEXT_FAINT};
    }}
    QScrollBar:horizontal {{
        background: transparent;
        height: 12px;
        margin: 2px;
    }}
    QScrollBar::handle:horizontal {{
        background: {BORDER};
        border-radius: 3px;
        min-width: 24px;
    }}
    QScrollBar::handle:horizontal:hover {{
        background: {TEXT_FAINT};
    }}
    QScrollBar::add-line, QScrollBar::sub-line {{
        height: 0;
        width: 0;
    }}

    QCheckBox {{
        spacing: 8px;
        color: {TEXT};
    }}
    QCheckBox::indicator {{
        width: 18px;
        height: 18px;
        border: 1px solid {TEXT_DIM};
        border-radius: 4px;
        background: transparent;
    }}
    QCheckBox::indicator:hover {{
        border-color: {ACCENT};
    }}
    QCheckBox::indicator:checked {{
        background: {ACCENT};
        border-color: {ACCENT};
        image: url("{CHECK}");
    }}

    QToolTip {{
        background: {PANEL};
        color: {TEXT};
        border: 1px solid {BORDER};
        border-radius: 4px;
        padding: 6px 8px;
    }}
"""


def styles() -> str:
    p = dict(palette())
    p["CHECK"] = _check_icon()
    return _TEMPLATE.format(**p)
