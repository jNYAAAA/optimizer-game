"""Твики реестра и сети с возможностью отката."""
from __future__ import annotations

from PySide6.QtCore import Qt, QThreadPool
from PySide6.QtGui import QBrush, QColor
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

from ...admin import is_admin, relaunch_as_admin
from ...core import services
from ...core.tweaks import Tweak, apply_tweak, build_tweaks, evaluate_applied, revert_tweak
from ...core.workers import Worker, start_worker
from ..widgets import AdminBanner, LogView, make_header
from ..theme import risk_colors


class TweaksPage(QWidget):
    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        root = QVBoxLayout(self)
        root.setContentsMargins(24, 20, 24, 20)
        root.setSpacing(14)

        root.addWidget(
            make_header(
                "Твики системы",
                "Отмеченный флажок — твик применён. Снимите флажок и нажмите "
                "«Применить изменения», чтобы откатить. Оригинальные значения "
                "сохраняются автоматически.",
            )
        )

        self.banner = AdminBanner()
        self.banner.elevate_requested.connect(relaunch_as_admin)
        root.addWidget(self.banner)

        self.tweaks: list[Tweak] = build_tweaks()

        self.table = QTableWidget(0, 5)
        self.table.setHorizontalHeaderLabels(["", "Твик", "Категория", "Риск", "Описание"])
        self.table.verticalHeader().setVisible(False)
        self.table.setSelectionMode(QAbstractItemView.NoSelection)
        self.table.setEditTriggers(QAbstractItemView.NoEditTriggers)
        self.table.setAlternatingRowColors(True)
        header = self.table.horizontalHeader()
        header.setSectionResizeMode(0, QHeaderView.ResizeToContents)
        header.setSectionResizeMode(1, QHeaderView.ResizeToContents)
        header.setSectionResizeMode(2, QHeaderView.ResizeToContents)
        header.setSectionResizeMode(3, QHeaderView.ResizeToContents)
        header.setSectionResizeMode(4, QHeaderView.Stretch)
        root.addWidget(self.table, 1)

        controls = QHBoxLayout()
        self.refresh_btn = QPushButton("Обновить")
        self.refresh_btn.clicked.connect(self.load)
        controls.addWidget(self.refresh_btn)
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

        self.status = QLabel("Чтение текущего состояния…")
        self.status.setObjectName("PageHint")
        root.addWidget(self.status)

        self.log = LogView()
        self.log.setMaximumHeight(120)
        root.addWidget(self.log)

        self.applied: dict[str, bool] = {}
        self._loaded = False

    # ------------------------------------------------------------------
    def on_theme_changed(self) -> None:
        if self.applied:
            self._on_applied_state(self.applied)

    def showEvent(self, event) -> None:  # noqa: N802 - Qt API
        super().showEvent(event)
        if not self._loaded:
            self._loaded = True
            self.load()

    def load(self) -> None:
        self.refresh_btn.setEnabled(False)
        self.progress.setRange(0, 0)
        self.status.setText("Чтение текущего состояния…")
        worker = Worker(evaluate_applied, self.tweaks)
        worker.signals.finished.connect(self._on_applied_state)
        worker.signals.failed.connect(self._on_failed)
        start_worker(worker)

    def _on_applied_state(self, applied: dict[str, bool]) -> None:
        self.applied = applied
        self.refresh_btn.setEnabled(True)
        self.progress.setRange(0, 100)
        self.progress.setValue(100)
        self.table.setRowCount(0)
        for tweak in self.tweaks:
            row = self.table.rowCount()
            self.table.insertRow(row)
            check = QTableWidgetItem()
            check.setFlags(Qt.ItemIsUserCheckable | Qt.ItemIsEnabled)
            check.setCheckState(Qt.Checked if applied.get(tweak.key) else Qt.Unchecked)
            self.table.setItem(row, 0, check)
            name_item = QTableWidgetItem(tweak.name)
            if tweak.requires_admin and not is_admin():
                name_item.setToolTip("Требуются права администратора")
            self.table.setItem(row, 1, name_item)
            self.table.setItem(row, 2, QTableWidgetItem(tweak.category))
            risk_item = QTableWidgetItem(tweak.risk_label)
            risk_item.setForeground(QBrush(QColor(risk_colors().get(tweak.risk, "#98a2b3"))))
            self.table.setItem(row, 3, risk_item)
            description = tweak.description
            if tweak.requires_admin:
                description += " (нужны права администратора)"
            self.table.setItem(row, 4, QTableWidgetItem(description))
        applied_count = sum(1 for value in applied.values() if value)
        self.status.setText(f"Применено твиков: {applied_count} из {len(self.tweaks)}")

    def _actions(self) -> list[tuple[Tweak, str]]:
        actions: list[tuple[Tweak, str]] = []
        for row, tweak in enumerate(self.tweaks):
            desired = self.table.item(row, 0).checkState() == Qt.Checked
            current = self.applied.get(tweak.key, False)
            if desired and not current:
                actions.append((tweak, "apply"))
            elif not desired and current:
                actions.append((tweak, "revert"))
        return actions

    def _apply(self) -> None:
        actions = self._actions()
        if not actions:
            self.status.setText("Изменений нет.")
            return
        self.apply_btn.setEnabled(False)
        self.progress.setValue(0)

        def task(progress):
            mode_map: dict[str, str] = {}
            if any(tweak.services for tweak, _ in actions):
                try:
                    mode_map = {s.name: s.start_mode for s in services.list_services()}
                except Exception:  # noqa: BLE001
                    mode_map = {}
            results = []
            total = max(len(actions), 1)
            for index, (tweak, action) in enumerate(actions):
                progress(int(index / total * 100), tweak.name)
                if action == "apply":
                    ok, message = apply_tweak(tweak, mode_map)
                else:
                    ok, message = revert_tweak(tweak)
                results.append((tweak.name, action, ok, message))
            return results

        worker = Worker(task, pass_progress=True)
        worker.signals.progress.connect(self._on_progress)
        worker.signals.finished.connect(self._on_done)
        worker.signals.failed.connect(self._on_failed)
        start_worker(worker)

    def _on_done(self, results: list[tuple[str, str, bool, str]]) -> None:
        self.apply_btn.setEnabled(True)
        self.progress.setValue(100)
        failures = 0
        for name, action, ok, message in results:
            verb = "применён" if action == "apply" else "откачен"
            if ok:
                self.log.log(f"{name}: {verb}")
            else:
                failures += 1
                self.log.log(f"{name}: ошибка — {message}")
        self.status.setText(
            "Изменения применены." if not failures else f"Применено с ошибками: {failures}"
        )
        self.load()

    def _on_progress(self, percent: int, message: str) -> None:
        self.progress.setValue(percent)
        if message:
            self.status.setText(message)

    def _on_failed(self, message: str) -> None:
        self.refresh_btn.setEnabled(True)
        self.apply_btn.setEnabled(True)
        self.progress.setRange(0, 100)
        self.progress.setValue(0)
        self.status.setText(f"Ошибка: {message}")
        self.log.log(f"Ошибка: {message}")
