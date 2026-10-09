"""Объединённая страница оптимизации.

Внутри — переключатель разделов (Очистка, Автозагрузка, Службы, Память).
Каждый раздел остаётся отдельным выбираемым экраном.
"""
from __future__ import annotations

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QHBoxLayout,
    QLabel,
    QPushButton,
    QStackedWidget,
    QVBoxLayout,
    QWidget,
)

from ..widgets import make_header
from .cleanup import CleanupPage
from .memory import MemoryPage
from .services import ServicesPage
from .startup import StartupPage

_SECTIONS: list[tuple[str, str]] = [
    (
        "Очистка",
        "Отметьте категории, просканируйте объём и очистите выбранное. "
        "Занятые файлы пропускаются.",
    ),
    (
        "Автозагрузка",
        "Отключённые записи сохраняются в папке данных приложения и включаются обратно. "
        "Записи системы (HKLM) требуют прав администратора.",
    ),
    (
        "Службы",
        "Изменение типа запуска и остановка служб обычно требуют прав администратора. "
        "Отключайте только те службы, в назначении которых уверены.",
    ),
    (
        "Память",
        "Освобождает рабочие наборы процессов и (при наличии прав) список ожидания. "
        "Это временная мера: память быстро заполняется снова.",
    ),
]


class OptimizePage(QWidget):
    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        root = QVBoxLayout(self)
        root.setContentsMargins(24, 20, 24, 20)
        root.setSpacing(12)

        root.addWidget(make_header("Оптимизация"))

        self.hint_label = QLabel()
        self.hint_label.setObjectName("PageHint")
        self.hint_label.setWordWrap(True)
        root.addWidget(self.hint_label)

        self.stack = QStackedWidget()
        self.pages: list[QWidget] = [
            CleanupPage(show_header=False),
            StartupPage(show_header=False),
            ServicesPage(show_header=False),
            MemoryPage(show_header=False),
        ]

        segment = QHBoxLayout()
        segment.setSpacing(8)
        self.buttons: list[QPushButton] = []
        for index, (name, _hint) in enumerate(_SECTIONS):
            button = QPushButton(name.upper())
            button.setObjectName("Segment")
            button.setCheckable(True)
            button.setCursor(Qt.PointingHandCursor)
            button.clicked.connect(lambda _checked=False, idx=index: self._select(idx))
            segment.addWidget(button)
            self.buttons.append(button)
        segment.addStretch(1)
        root.addLayout(segment)

        for page in self.pages:
            self.stack.addWidget(page)
        root.addWidget(self.stack, 1)

        self._select(0)

    def _select(self, index: int) -> None:
        for i, button in enumerate(self.buttons):
            button.setChecked(i == index)
        self.stack.setCurrentIndex(index)
        self.hint_label.setText(_SECTIONS[index][1])

    def on_theme_changed(self) -> None:
        for page in self.pages:
            hook = getattr(page, "on_theme_changed", None)
            if callable(hook):
                hook()
