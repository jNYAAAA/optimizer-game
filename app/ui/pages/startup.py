"""Управление автозагрузкой."""
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

from ...admin import relaunch_as_admin
from ...core.startup import StartupItem, list_startup_items, restore_all, set_enabled
from ...core.workers import Worker, start_worker
from ..widgets import AdminBanner, LogView, make_header


class StartupPage(QWidget):
    def __init__(self, parent: QWidget | None = None, show_header: bool = True) -> None:
        super().__init__(parent)
        root = QVBoxLayout(self)
        root.setContentsMargins(24, 20, 24, 20)
        root.setSpacing(14)

        if show_header:
            root.addWidget(
                make_header(
                    "Автозагрузка",
                    "Отключённые записи сохраняются в папке данных приложения и могут "
                    "быть включены обратно. Записи системы (HKLM) требуют прав администратора.",
                )
            )

        self.banner = AdminBanner()
        self.banner.elevate_requested.connect(relaunch_as_admin)
        root.addWidget(self.banner)

        self.table = QTableWidget(0, 5)
        self.table.setHorizontalHeaderLabels(["Вкл.", "Название", "Команда", "Источник", "Область"])
        self.table.verticalHeader().setVisible(False)
        self.table.setSelectionBehavior(QAbstractItemView.SelectRows)
        self.table.setEditTriggers(QAbstractItemView.NoEditTriggers)
        self.table.setAlternatingRowColors(True)
        header = self.table.horizontalHeader()
        header.setSectionResizeMode(0, QHeaderView.ResizeToContents)
        header.setSectionResizeMode(1, QHeaderView.ResizeToContents)
        header.setSectionResizeMode(2, QHeaderView.Stretch)
        header.setSectionResizeMode(3, QHeaderView.ResizeToContents)
        header.setSectionResizeMode(4, QHeaderView.ResizeToContents)
        root.addWidget(self.table, 1)

        self.items: list[StartupItem] = []

        controls = QHBoxLayout()
        self.refresh_btn = QPushButton("Обновить")
        self.refresh_btn.clicked.connect(self.load)
        controls.addWidget(self.refresh_btn)
        self.restore_btn = QPushButton("Восстановить отключённые")
        self.restore_btn.clicked.connect(self._restore_all)
        controls.addWidget(self.restore_btn)
        controls.addStretch(1)
        self.apply_btn = QPushButton("Применить изменения")
        self.apply_btn.setObjectName("Primary")
        self.apply_btn.clicked.connect(self._apply)
        controls.addWidget(self.apply_btn)
        root.addLayout(controls)

        self.progress = QProgressBar()
        self.progress.setRange(0, 100)
        self.progress.setValue(0)
        root.addWidget(self.progress)

        self.status = QLabel("Загрузка списка…")
        self.status.setObjectName("PageHint")
        root.addWidget(self.status)

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
        self.refresh_btn.setEnabled(False)
        self.status.setText("Чтение списка автозагрузки…")
        worker = Worker(list_startup_items)
        worker.signals.finished.connect(self._on_items)
        worker.signals.failed.connect(self._on_failed)
        start_worker(worker)

    def _on_items(self, items: list[StartupItem]) -> None:
        self.items = items
        self.refresh_btn.setEnabled(True)
        self.table.setRowCount(0)
        for item in items:
            row = self.table.rowCount()
            self.table.insertRow(row)
            check = QTableWidgetItem()
            check.setFlags(Qt.ItemIsUserCheckable | Qt.ItemIsEnabled)
            check.setCheckState(Qt.Checked if item.enabled else Qt.Unchecked)
            self.table.setItem(row, 0, check)
            self.table.setItem(row, 1, QTableWidgetItem(item.name))
            self.table.setItem(row, 2, QTableWidgetItem(item.command))
            self.table.setItem(row, 3, QTableWidgetItem(item.source))
            scope = "Система" if item.scope == "machine" else "Пользователь"
            self.table.setItem(row, 4, QTableWidgetItem(scope))
        self.status.setText(f"Записей: {len(items)}")
        self.progress.setValue(100)

    def _pairs(self) -> list[tuple[StartupItem, bool]]:
        pairs: list[tuple[StartupItem, bool]] = []
        for row, item in enumerate(self.items):
            desired = self.table.item(row, 0).checkState() == Qt.Checked
            if desired != item.enabled:
                pairs.append((item, desired))
        return pairs

    def _apply(self) -> None:
        pairs = self._pairs()
        if not pairs:
            self.status.setText("Изменений нет.")
            return
        self.apply_btn.setEnabled(False)
        self.progress.setValue(0)

        def task(progress):
            results = []
            total = max(len(pairs), 1)
            for index, (item, desired) in enumerate(pairs):
                progress(int(index / total * 100), item.name)
                ok, message = set_enabled(item, desired)
                results.append((item.name, desired, ok, message))
            return results

        worker = Worker(task, pass_progress=True)
        worker.signals.progress.connect(self._on_progress)
        worker.signals.finished.connect(self._on_applied)
        worker.signals.failed.connect(self._on_failed)
        start_worker(worker)

    def _on_applied(self, results: list[tuple[str, bool, bool, str]]) -> None:
        self.apply_btn.setEnabled(True)
        self.progress.setValue(100)
        failures = 0
        for name, desired, ok, message in results:
            action = "включено" if desired else "отключено"
            if ok:
                self.log.log(f"{name}: {action}")
            else:
                failures += 1
                self.log.log(f"{name}: ошибка — {message}")
        self.status.setText(
            "Изменения применены." if not failures else f"Применено с ошибками: {failures}"
        )
        self.load()

    def _restore_all(self) -> None:
        self.restore_btn.setEnabled(False)

        def task():
            return restore_all()

        worker = Worker(task)
        worker.signals.finished.connect(self._on_restored)
        worker.signals.failed.connect(self._on_failed)
        start_worker(worker)

    def _on_restored(self, count: int) -> None:
        self.restore_btn.setEnabled(True)
        self.log.log(f"Восстановлено записей: {count}")
        self.load()

    def _on_progress(self, percent: int, message: str) -> None:
        self.progress.setValue(percent)
        if message:
            self.status.setText(message)

    def _on_failed(self, message: str) -> None:
        self.refresh_btn.setEnabled(True)
        self.apply_btn.setEnabled(True)
        self.restore_btn.setEnabled(True)
        self.status.setText(f"Ошибка: {message}")
        self.log.log(f"Ошибка: {message}")
