"""Страница драйверов: текущие версии и проверка обновлений."""
from __future__ import annotations

from PySide6.QtCore import Qt, QThreadPool
from PySide6.QtWidgets import (
    QAbstractItemView,
    QHBoxLayout,
    QHeaderView,
    QLabel,
    QProgressBar,
    QPushButton,
    QTableWidget,
    QTableWidgetItem,
    QVBoxLayout,
    QWidget,
)

from ...core.drivers import DriverInfo, DriverUpdateResult, check_driver_updates, list_drivers
from ...core.workers import Worker, start_worker
from .. import theme
from ..widgets import Card, LogView, make_header


class DriversPage(QWidget):
    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        root = QVBoxLayout(self)
        root.setContentsMargins(24, 20, 24, 20)
        root.setSpacing(14)

        root.addWidget(
            make_header(
                "Драйверы",
                "Текущие версии драйверов устройств и проверка доступных обновлений "
                "через Windows Update.",
            )
        )

        self.gpu_card = Card("Видеодрайвер")
        self.gpu_card.add_row("Статус", "Чтение драйверов…")
        root.addWidget(self.gpu_card)

        controls = QHBoxLayout()
        self.check_btn = QPushButton("ПРОВЕРИТЬ ОБНОВЛЕНИЯ")
        self.check_btn.setObjectName("Primary")
        self.check_btn.clicked.connect(self._check)
        controls.addWidget(self.check_btn)
        self.status = QLabel("Нажмите «Проверить обновления», чтобы запросить Windows Update.")
        self.status.setObjectName("PageHint")
        self.status.setWordWrap(True)
        controls.addWidget(self.status, 1)
        root.addLayout(controls)

        self.progress = QProgressBar()
        self.progress.setRange(0, 100)
        self.progress.setValue(0)
        root.addWidget(self.progress)

        self.table = QTableWidget(0, 5)
        self.table.setHorizontalHeaderLabels(
            ["Устройство", "Класс", "Версия", "Дата", "Поставщик"]
        )
        self.table.verticalHeader().setVisible(False)
        self.table.setSelectionMode(QAbstractItemView.NoSelection)
        self.table.setEditTriggers(QAbstractItemView.NoEditTriggers)
        self.table.setAlternatingRowColors(True)
        header = self.table.horizontalHeader()
        header.setSectionResizeMode(0, QHeaderView.Stretch)
        header.setSectionResizeMode(1, QHeaderView.ResizeToContents)
        header.setSectionResizeMode(2, QHeaderView.ResizeToContents)
        header.setSectionResizeMode(3, QHeaderView.ResizeToContents)
        header.setSectionResizeMode(4, QHeaderView.ResizeToContents)
        root.addWidget(self.table, 1)

        self.log = LogView()
        self.log.setMaximumHeight(120)
        root.addWidget(self.log)

        self._loaded = False

    # ------------------------------------------------------------------
    def showEvent(self, event) -> None:  # noqa: N802 - Qt API
        super().showEvent(event)
        if not self._loaded:
            self._loaded = True
            self.load()

    def load(self) -> None:
        self.progress.setRange(0, 0)
        worker = Worker(list_drivers)
        worker.signals.finished.connect(self._on_drivers)
        worker.signals.failed.connect(self._on_failed)
        start_worker(worker)

    def _on_drivers(self, drivers: list[DriverInfo]) -> None:
        self.progress.setRange(0, 100)
        self.progress.setValue(100)

        displays = [d for d in drivers if d.device_class.upper() == "DISPLAY"]
        self.gpu_card.clear()
        if displays:
            for driver in displays:
                self.gpu_card.add_row(driver.name, f"{driver.version} · {driver.date}")
        else:
            self.gpu_card.add_row("Видеодрайвер", "Не найден")

        self.table.setRowCount(0)
        for driver in drivers:
            row = self.table.rowCount()
            self.table.insertRow(row)
            self.table.setItem(row, 0, QTableWidgetItem(driver.name))
            self.table.setItem(row, 1, QTableWidgetItem(driver.class_label))
            self.table.setItem(row, 2, QTableWidgetItem(driver.version))
            self.table.setItem(row, 3, QTableWidgetItem(driver.date))
            self.table.setItem(row, 4, QTableWidgetItem(driver.manufacturer))
        self.log.log(f"Найдено драйверов: {len(drivers)}")

    def _check(self) -> None:
        self.check_btn.setEnabled(False)
        self.progress.setRange(0, 0)
        self.status.setText("Запрос к Windows Update… это может занять до минуты.")
        worker = Worker(check_driver_updates)
        worker.signals.finished.connect(self._on_updates)
        worker.signals.failed.connect(self._on_failed)
        start_worker(worker)

    def _on_updates(self, result: DriverUpdateResult) -> None:
        self.check_btn.setEnabled(True)
        self.progress.setRange(0, 100)
        self.progress.setValue(100)
        palette = theme.palette()

        if not result.ok:
            self.status.setText(result.message)
            self.status.setStyleSheet(f"color: {palette['DANGER']};")
            self.log.log(result.message)
            return

        if result.updates:
            self.status.setText(f"{result.message}. Список — в журнале ниже.")
            self.status.setStyleSheet(f"color: {palette['WARN']};")
            for update in result.updates:
                self.log.log(f"Обновление: {update.title} ({update.provider}) {update.date}".strip())
        else:
            self.status.setText(result.message)
            self.status.setStyleSheet(f"color: {palette['OK']};")
            self.log.log(result.message)
        self.log.log("Совет: NVIDIA/AMD/Intel могут предлагать более свежие драйверы, чем Windows Update.")

    def _on_failed(self, message: str) -> None:
        self.check_btn.setEnabled(True)
        self.progress.setRange(0, 100)
        self.progress.setValue(0)
        self.status.setText(f"Ошибка: {message}")
        self.status.setStyleSheet(f"color: {theme.palette()['DANGER']};")
        self.log.log(f"Ошибка: {message}")
