"""Очистка временных файлов."""
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
from ...core.cleanup import (
    CleanResult,
    ScanResult,
    clean_targets,
    default_targets,
    scan_targets,
)
from ...core.workers import Worker, start_worker
from ...utils import format_bytes, format_count
from ..widgets import AdminBanner, LogView, make_header


class CleanupPage(QWidget):
    def __init__(self, parent: QWidget | None = None, show_header: bool = True) -> None:
        super().__init__(parent)
        root = QVBoxLayout(self)
        root.setContentsMargins(24, 20, 24, 20)
        root.setSpacing(14)

        if show_header:
            root.addWidget(
                make_header(
                    "Очистка файлов",
                    "Отметьте категории и нажмите «Сканировать», чтобы оценить объём, "
                    "затем «Очистить выбранное». Занятые файлы будут пропущены.",
                )
            )

        self.banner = AdminBanner()
        self.banner.elevate_requested.connect(relaunch_as_admin)
        root.addWidget(self.banner)

        self.targets = default_targets()

        self.table = QTableWidget(0, 5)
        self.table.setHorizontalHeaderLabels(["", "Категория", "Описание", "Размер", "Файлов"])
        self.table.verticalHeader().setVisible(False)
        self.table.setSelectionMode(QAbstractItemView.NoSelection)
        self.table.setEditTriggers(QAbstractItemView.NoEditTriggers)
        self.table.setAlternatingRowColors(True)
        header = self.table.horizontalHeader()
        header.setSectionResizeMode(0, QHeaderView.ResizeToContents)
        header.setSectionResizeMode(1, QHeaderView.ResizeToContents)
        header.setSectionResizeMode(2, QHeaderView.Stretch)
        header.setSectionResizeMode(3, QHeaderView.ResizeToContents)
        header.setSectionResizeMode(4, QHeaderView.ResizeToContents)
        root.addWidget(self.table, 1)
        self._populate(None)

        controls = QHBoxLayout()
        self.select_all_btn = QPushButton("Выбрать всё")
        self.select_all_btn.clicked.connect(lambda: self._set_all(True))
        self.deselect_all_btn = QPushButton("Снять всё")
        self.deselect_all_btn.clicked.connect(lambda: self._set_all(False))
        controls.addWidget(self.select_all_btn)
        controls.addWidget(self.deselect_all_btn)
        controls.addStretch(1)
        self.scan_btn = QPushButton("Сканировать")
        self.scan_btn.clicked.connect(self._scan)
        controls.addWidget(self.scan_btn)
        self.clean_btn = QPushButton("Очистить выбранное")
        self.clean_btn.setObjectName("Primary")
        self.clean_btn.clicked.connect(self._clean)
        controls.addWidget(self.clean_btn)
        root.addLayout(controls)

        self.progress = QProgressBar()
        self.progress.setRange(0, 100)
        self.progress.setValue(0)
        root.addWidget(self.progress)

        self.status = QLabel("Нажмите «Сканировать» для оценки объёма.")
        self.status.setObjectName("PageHint")
        root.addWidget(self.status)

        self.log = LogView()
        self.log.setMaximumHeight(120)
        root.addWidget(self.log)

    # ------------------------------------------------------------------
    def _populate(self, results: dict[str, ScanResult] | None) -> None:
        self.table.setRowCount(0)
        for target in self.targets:
            row = self.table.rowCount()
            self.table.insertRow(row)
            check = QTableWidgetItem()
            check.setFlags(Qt.ItemIsUserCheckable | Qt.ItemIsEnabled)
            check.setCheckState(Qt.Checked)
            self.table.setItem(row, 0, check)
            self.table.setItem(row, 1, QTableWidgetItem(target.name))
            description = target.description
            if target.requires_admin:
                description += " [нужны права администратора]"
            self.table.setItem(row, 2, QTableWidgetItem(description))
            size_text = files_text = "—"
            if results and target.key in results:
                result = results[target.key]
                size_text = format_bytes(result.size_bytes)
                files_text = format_count(result.file_count)
            self.table.setItem(row, 3, QTableWidgetItem(size_text))
            self.table.setItem(row, 4, QTableWidgetItem(files_text))

    def _set_all(self, checked: bool) -> None:
        state = Qt.Checked if checked else Qt.Unchecked
        for row in range(self.table.rowCount()):
            self.table.item(row, 0).setCheckState(state)

    def _selected_keys(self) -> list[str]:
        keys: list[str] = []
        for row in range(self.table.rowCount()):
            if self.table.item(row, 0).checkState() == Qt.Checked:
                keys.append(self.targets[row].key)
        return keys

    # ------------------------------------------------------------------
    def _scan(self) -> None:
        self.scan_btn.setEnabled(False)
        self.clean_btn.setEnabled(False)
        self.progress.setValue(0)
        worker = Worker(scan_targets, self.targets, pass_progress=True)
        worker.signals.progress.connect(self._on_progress)
        worker.signals.finished.connect(self._on_scanned)
        worker.signals.failed.connect(self._on_failed)
        start_worker(worker)

    def _on_scanned(self, results: dict[str, ScanResult]) -> None:
        self.scan_btn.setEnabled(True)
        self.clean_btn.setEnabled(True)
        self._populate(results)
        total_size = sum(r.size_bytes for r in results.values())
        total_files = sum(r.file_count for r in results.values())
        self.progress.setValue(100)
        self.status.setText(
            f"Найдено: {format_bytes(total_size)} в {format_count(total_files)} файлах."
        )
        self.log.log(f"Сканирование завершено: {format_bytes(total_size)}")

    def _clean(self) -> None:
        keys = self._selected_keys()
        if not keys:
            self.status.setText("Не выбрано ни одной категории.")
            return
        self.scan_btn.setEnabled(False)
        self.clean_btn.setEnabled(False)
        self.progress.setValue(0)
        worker = Worker(clean_targets, self.targets, keys, pass_progress=True)
        worker.signals.progress.connect(self._on_progress)
        worker.signals.finished.connect(self._on_cleaned)
        worker.signals.failed.connect(self._on_failed)
        start_worker(worker)

    def _on_cleaned(self, result: CleanResult) -> None:
        self.scan_btn.setEnabled(True)
        self.clean_btn.setEnabled(True)
        self.progress.setValue(100)
        self.status.setText(
            f"Освобождено {format_bytes(result.freed_bytes)} "
            f"({format_count(result.deleted)} файлов, пропущено {format_count(result.skipped)})."
        )
        self.log.log(
            f"Очистка завершена: {format_bytes(result.freed_bytes)}, "
            f"пропущено файлов: {result.skipped}"
        )
        self._scan()

    def _on_progress(self, percent: int, message: str) -> None:
        self.progress.setValue(percent)
        if message:
            self.status.setText(message)

    def _on_failed(self, message: str) -> None:
        self.scan_btn.setEnabled(True)
        self.clean_btn.setEnabled(True)
        self.status.setText(f"Ошибка: {message}")
        self.log.log(f"Ошибка: {message}")
