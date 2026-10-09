"""Оптимизация оперативной памяти."""
from __future__ import annotations

from PySide6.QtCore import QThreadPool, QTimer
from PySide6.QtWidgets import (
    QCheckBox,
    QHBoxLayout,
    QLabel,
    QProgressBar,
    QPushButton,
    QVBoxLayout,
    QWidget,
)

from ...core import memory
from ...core.workers import Worker, start_worker
from ...utils import format_bytes
from ..widgets import Card, LogView, make_header


class MemoryPage(QWidget):
    def __init__(self, parent: QWidget | None = None, show_header: bool = True) -> None:
        super().__init__(parent)
        root = QVBoxLayout(self)
        root.setContentsMargins(24, 20, 24, 20)
        root.setSpacing(14)

        if show_header:
            root.addWidget(
                make_header(
                    "Оптимизация памяти",
                    "Освобождает рабочие наборы процессов и список ожидания. "
                    "Это временная мера: память быстро заполняется снова.",
                )
            )

        self.stats_card = Card("Текущее состояние памяти")
        self._rows = {
            "total": self.stats_card.add_row("Всего"),
            "used": self.stats_card.add_row("Использовано"),
            "available": self.stats_card.add_row("Доступно"),
            "percent": self.stats_card.add_row("Загрузка"),
        }
        root.addWidget(self.stats_card)

        controls = QHBoxLayout()
        self.standby_check = QCheckBox("Очищать список ожидания (может временно замедлить систему)")
        self.standby_check.setChecked(True)
        controls.addWidget(self.standby_check)
        controls.addStretch(1)
        self.run_btn = QPushButton("ОПТИМИЗИРОВАТЬ ПАМЯТЬ")
        self.run_btn.setObjectName("Primary")
        self.run_btn.clicked.connect(self._run)
        controls.addWidget(self.run_btn)
        root.addLayout(controls)

        self.progress = QProgressBar()
        self.progress.setRange(0, 100)
        self.progress.setValue(0)
        root.addWidget(self.progress)

        self.log = LogView()
        root.addWidget(self.log, 1)

        self._refresh()
        self._timer = QTimer(self)
        self._timer.setInterval(2000)
        self._timer.timeout.connect(self._refresh)
        self._timer.start()

    # ------------------------------------------------------------------
    def _refresh(self) -> None:
        stats = memory.MemoryStats.current()
        self._rows["total"].setText(format_bytes(stats.total))
        self._rows["used"].setText(format_bytes(stats.used))
        self._rows["available"].setText(format_bytes(stats.available))
        self._rows["percent"].setText(f"{stats.percent:.0f}%")

    def _run(self) -> None:
        self.run_btn.setEnabled(False)
        self.progress.setValue(0)
        clear_standby = self.standby_check.isChecked()
        worker = Worker(memory.optimize_memory, clear_standby, pass_progress=True)
        worker.signals.progress.connect(self._on_progress)
        worker.signals.finished.connect(self._on_done)
        worker.signals.failed.connect(self._on_failed)
        start_worker(worker)

    def _on_progress(self, percent: int, message: str) -> None:
        self.progress.setValue(percent)
        if message:
            self.log.log(message)

    def _on_done(self, result: memory.OptimizeResult) -> None:
        self.run_btn.setEnabled(True)
        self.progress.setValue(100)
        self.log.log(f"{result.message}. Освобождено ~{format_bytes(result.freed)}")
        self._refresh()

    def _on_failed(self, message: str) -> None:
        self.run_btn.setEnabled(True)
        self.log.log(f"Ошибка: {message}")
