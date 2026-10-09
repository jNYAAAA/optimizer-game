"""Страница драйверов: текущие версии, Windows Update и сайты производителей."""
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

from ...core.drivers import (
    DriverInfo,
    DriverUpdateResult,
    VendorDriverInfo,
    check_driver_updates,
    check_gpu_drivers,
    list_drivers,
)
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
                "Текущие версии драйверов устройств, проверка Windows Update и "
                "официальных сайтов производителей.",
            )
        )

        self.gpu_card = Card("Видеодрайвер")
        self.gpu_card.add_row("Статус", "Чтение драйверов…")
        root.addWidget(self.gpu_card)

        self.vendor_card = Card("Обновления с сайтов производителей")
        self.vendor_card.add_row("Статус", "Нажмите «Проверить обновления».")
        root.addWidget(self.vendor_card)

        controls = QHBoxLayout()
        self.check_btn = QPushButton("ПРОВЕРИТЬ ОБНОВЛЕНИЯ")
        self.check_btn.setObjectName("Primary")
        self.check_btn.clicked.connect(self._check)
        controls.addWidget(self.check_btn)
        self.status = QLabel("Проверка ещё не выполнялась.")
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

        self._displays: list[DriverInfo] = []
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
        self._displays = [d for d in drivers if d.device_class.upper() == "DISPLAY"]

        self.gpu_card.clear()
        if self._displays:
            for driver in self._displays:
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

    # ------------------------------------------------------------------
    def _check(self) -> None:
        self.check_btn.setEnabled(False)
        self.progress.setRange(0, 0)
        self.status.setText("Проверка Windows Update и сайтов производителей…")
        displays = self._displays

        def task(progress):
            progress(5, "Запрос к Windows Update…")
            windows_update = check_driver_updates()
            progress(55, "Проверка сайтов производителей…")
            vendors = check_gpu_drivers(displays)
            return windows_update, vendors

        worker = Worker(task, pass_progress=True)
        worker.signals.progress.connect(lambda _p, m: self.status.setText(m))
        worker.signals.finished.connect(self._on_results)
        worker.signals.failed.connect(self._on_failed)
        start_worker(worker)

    def _on_results(self, result) -> None:
        windows_update, vendors = result
        self.check_btn.setEnabled(True)
        self.progress.setRange(0, 100)
        self.progress.setValue(100)
        palette = theme.palette()

        any_update = False
        self.vendor_card.clear()
        if not vendors:
            self.vendor_card.add_row("Видеодрайверы", "Не найдены")
        for info in vendors:
            any_update = self._add_vendor_row(info, palette) or any_update

        if windows_update.updates:
            any_update = True
            for update in windows_update.updates:
                self.log.log(f"Windows Update: {update.title} ({update.provider})".strip())
        self.log.log(windows_update.message)

        if any_update:
            self.status.setText("Есть доступные обновления драйверов — см. карточки выше.")
            self.status.setStyleSheet(f"color: {palette['WARN']};")
        else:
            self.status.setText("Доступных обновлений не найдено — версии актуальны.")
            self.status.setStyleSheet(f"color: {palette['OK']};")

    def _add_vendor_row(self, info: VendorDriverInfo, palette: dict) -> bool:
        caption = info.device
        if info.latest and info.latest != "—":
            text = f"{info.installed} → {info.latest}"
            if info.release_date:
                text += f" · {info.release_date}"
            if info.update_available:
                text += " · ДОСТУПНО ОБНОВЛЕНИЕ"
            elif info.note:
                text += f" · {info.note}"
        else:
            text = info.installed
            if info.note:
                text += f" · {info.note}"

        label = self.vendor_card.add_row(caption, text)
        if info.url:
            label.setText(f"{text} · <a href=\"{info.url}\">сайт</a>")
            label.setOpenExternalLinks(True)
            label.setTextInteractionFlags(Qt.TextBrowserInteraction)

        if info.update_available:
            label.setStyleSheet(f"color: {palette['WARN']};")
            self.log.log(f"{info.device}: доступна версия {info.latest} (установлена {info.installed})")
        elif info.latest and info.latest != "—":
            label.setStyleSheet(f"color: {palette['OK']};")
            self.log.log(f"{info.device}: установлена последняя версия {info.installed}")
        else:
            self.log.log(f"{info.device}: {info.note or 'нет данных об обновлениях'}")
        return info.update_available

    def _on_failed(self, message: str) -> None:
        self.check_btn.setEnabled(True)
        self.progress.setRange(0, 100)
        self.progress.setValue(0)
        self.status.setText(f"Ошибка: {message}")
        self.status.setStyleSheet(f"color: {theme.palette()['DANGER']};")
        self.log.log(f"Ошибка: {message}")
