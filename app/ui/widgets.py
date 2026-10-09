"""Переиспользуемые элементы интерфейса."""
from __future__ import annotations

from datetime import datetime

from PySide6.QtCore import QRectF, Qt
from PySide6.QtGui import QColor, QPainter, QPainterPath, QPen
from PySide6.QtWidgets import (
    QAbstractButton,
    QFrame,
    QGridLayout,
    QHBoxLayout,
    QLabel,
    QPlainTextEdit,
    QScrollArea,
    QVBoxLayout,
    QWidget,
)

from . import theme


def make_header(title: str, hint: str = "") -> QWidget:
    widget = QWidget()
    layout = QVBoxLayout(widget)
    layout.setContentsMargins(0, 0, 0, 0)
    layout.setSpacing(6)
    title_label = QLabel(title.upper())
    title_label.setObjectName("PageTitle")
    layout.addWidget(title_label)
    accent = QFrame()
    accent.setObjectName("AccentLine")
    accent.setFixedHeight(2)
    accent.setFixedWidth(56)
    layout.addWidget(accent)
    if hint:
        hint_label = QLabel(hint)
        hint_label.setObjectName("PageHint")
        hint_label.setWordWrap(True)
        layout.addWidget(hint_label)
    return widget


def make_badge(text: str, color: str) -> QLabel:
    label = QLabel(text.upper())
    label.setObjectName("Badge")
    label.setStyleSheet(
        f"background: transparent; border: 1px solid {color}; color: {color};"
        "border-radius: 2px; padding: 2px 7px; font-size: 10px; font-weight: 700;"
    )
    label.setAlignment(Qt.AlignCenter)
    return label


class Card(QFrame):
    """Панель со списком пар «подпись — значение»."""

    def __init__(self, title: str, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setObjectName("Card")
        outer = QVBoxLayout(self)
        outer.setContentsMargins(16, 14, 16, 14)
        outer.setSpacing(10)

        header = QHBoxLayout()
        self.title_label = QLabel(title.upper())
        self.title_label.setObjectName("CardTitle")
        header.addWidget(self.title_label)
        header.addStretch(1)
        self._header_layout = header
        outer.addLayout(header)

        self.body = QGridLayout()
        self.body.setHorizontalSpacing(12)
        self.body.setVerticalSpacing(6)
        self.body.setColumnStretch(1, 1)
        outer.addLayout(self.body)
        outer.addStretch(1)

        self._rows: dict[str, QLabel] = {}

    def add_header_widget(self, widget: QWidget) -> None:
        self._header_layout.addWidget(widget)

    def add_row(self, label: str, value: str = "—") -> QLabel:
        row = self.body.rowCount()
        name = QLabel(label.upper())
        name.setObjectName("Caption")
        name.setWordWrap(True)
        value_label = QLabel(value)
        value_label.setObjectName("Value")
        value_label.setWordWrap(True)
        value_label.setTextInteractionFlags(Qt.TextSelectableByMouse)
        self.body.addWidget(name, row, 0, Qt.AlignTop)
        self.body.addWidget(value_label, row, 1)
        self._rows[label] = value_label
        return value_label

    def set(self, label: str, value: str) -> None:
        if label in self._rows:
            self._rows[label].setText(value)

    def clear(self) -> None:
        while self.body.count():
            item = self.body.takeAt(0)
            widget = item.widget()
            if widget is not None:
                widget.deleteLater()
        self._rows.clear()


class LogView(QPlainTextEdit):
    """Журнал событий с отметкой времени."""

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setReadOnly(True)
        self.setMaximumBlockCount(5000)

    def log(self, message: str) -> None:
        self.appendPlainText(f"[{datetime.now():%H:%M:%S}] {message}")


class ThemeToggleButton(QAbstractButton):
    """Иконка луны: цвет берётся из акцента текущей темы."""

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setCursor(Qt.PointingHandCursor)
        self.setFocusPolicy(Qt.NoFocus)
        self.setFixedSize(36, 36)
        self._hover = False

    def enterEvent(self, event) -> None:  # noqa: N802 - Qt API
        self._hover = True
        self.update()
        super().enterEvent(event)

    def leaveEvent(self, event) -> None:  # noqa: N802 - Qt API
        self._hover = False
        self.update()
        super().leaveEvent(event)

    def paintEvent(self, event) -> None:  # noqa: N802 - Qt API
        colors = theme.palette()
        painter = QPainter(self)
        painter.setRenderHint(QPainter.Antialiasing, True)

        if self._hover:
            ring = QRectF(self.rect()).adjusted(1.5, 1.5, -1.5, -1.5)
            painter.setPen(QPen(QColor(colors["BORDER"]), 1))
            painter.setBrush(Qt.NoBrush)
            painter.drawEllipse(ring)

        inner = QRectF(self.rect()).adjusted(10, 10, -10, -10)
        radius = inner.width()
        full = QPainterPath()
        full.addEllipse(inner)
        cut = QPainterPath()
        cut.addEllipse(inner.translated(radius * 0.45, -radius * 0.45))
        crescent = full.subtracted(cut)

        color = QColor(colors["ACCENT_DIM"] if self._hover else colors["ACCENT"])
        painter.setPen(Qt.NoPen)
        painter.setBrush(color)
        painter.drawPath(crescent)
        painter.end()


def scrollable(widget: QWidget) -> QScrollArea:
    """Оборачивает страницу в вертикальную прокрутку."""
    area = QScrollArea()
    area.setWidgetResizable(True)
    area.setFrameShape(QFrame.NoFrame)
    area.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
    area.setWidget(widget)
    return area
