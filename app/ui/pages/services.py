"""Просмотр и управление службами Windows."""
from __future__ import annotations

from PySide6.QtCore import Qt, QThreadPool
from PySide6.QtWidgets import (
    QAbstractItemView,
    QCheckBox,
    QComboBox,
    QHBoxLayout,
    QHeaderView,
    QLabel,
    QLineEdit,
    QProgressBar,
    QPushButton,
    QTableWidget,
    QTableWidgetItem,
    QVBoxLayout,
    QWidget,
)

from ...admin import is_admin, relaunch_as_admin
from ...core import services
from ...core.services import (
    START_MODE_LABELS,
    STATE_LABELS,
    ServiceInfo,
    list_services,
)
from ...core.workers import Worker, start_worker
from ..widgets import AdminBanner, Card, LogView, make_header

_MODE_CHOICES = [("Automatic", "Автоматически"), ("Manual", "Вручную"), ("Disabled", "Отключена")]
_CIM_TO_MODE = {"Auto": "Automatic", "Manual": "Manual", "Disabled": "Disabled"}


class ServicesPage(QWidget):
    def __init__(self, parent: QWidget | None = None, show_header: bool = True) -> None:
        super().__init__(parent)
        root = QVBoxLayout(self)
        root.setContentsMargins(24, 20, 24, 20)
        root.setSpacing(12)

        if show_header:
            root.addWidget(
                make_header(
                    "Службы Windows",
                    "Изменение типа запуска и остановка служб обычно требуют прав "
                    "администратора. Отключайте только те службы, в назначении которых уверены.",
                )
            )

        self.banner = AdminBanner()
        self.banner.elevate_requested.connect(relaunch_as_admin)
        root.addWidget(self.banner)

        filters = QHBoxLayout()
        self.search = QLineEdit()
        self.search.setPlaceholderText("Поиск по названию или службе…")
        self.search.textChanged.connect(self._render)
        filters.addWidget(self.search, 1)
        self.recommended_only = QCheckBox("Только рекомендуемые к отключению")
        self.recommended_only.stateChanged.connect(self._render)
        filters.addWidget(self.recommended_only)
        self.refresh_btn = QPushButton("Обновить")
        self.refresh_btn.clicked.connect(self.load)
        filters.addWidget(self.refresh_btn)
        root.addLayout(filters)

        self.table = QTableWidget(0, 4)
        self.table.setHorizontalHeaderLabels(["Служба", "Имя", "Состояние", "Запуск"])
        self.table.verticalHeader().setVisible(False)
        self.table.setSelectionBehavior(QAbstractItemView.SelectRows)
        self.table.setSelectionMode(QAbstractItemView.SingleSelection)
        self.table.setEditTriggers(QAbstractItemView.NoEditTriggers)
        self.table.setAlternatingRowColors(True)
        header = self.table.horizontalHeader()
        header.setSectionResizeMode(0, QHeaderView.Stretch)
        header.setSectionResizeMode(1, QHeaderView.ResizeToContents)
        header.setSectionResizeMode(2, QHeaderView.ResizeToContents)
        header.setSectionResizeMode(3, QHeaderView.ResizeToContents)
        self.table.itemSelectionChanged.connect(self._on_select)
        root.addWidget(self.table, 1)

        self.details = Card("Описание службы")
        self.details.add_row("Служба", "Выберите службу в списке")
        self.details.add_row("Путь", "—")
        self.details.add_row("Учётная запись", "—")
        root.addWidget(self.details)

        controls = QHBoxLayout()
        controls.addWidget(QLabel("Тип запуска:"))
        self.mode_combo = QComboBox()
        for value, label in _MODE_CHOICES:
            self.mode_combo.addItem(label, value)
        controls.addWidget(self.mode_combo)
        self.apply_mode_btn = QPushButton("Применить")
        self.apply_mode_btn.clicked.connect(self._apply_mode)
        controls.addWidget(self.apply_mode_btn)
        controls.addSpacing(12)
        self.start_btn = QPushButton("Запустить")
        self.start_btn.clicked.connect(lambda: self._change("start"))
        controls.addWidget(self.start_btn)
        self.stop_btn = QPushButton("Остановить")
        self.stop_btn.clicked.connect(lambda: self._change("stop"))
        controls.addWidget(self.stop_btn)
        self.disable_btn = QPushButton("Отключить")
        self.disable_btn.setObjectName("Danger")
        self.disable_btn.clicked.connect(lambda: self._change("disable"))
        controls.addWidget(self.disable_btn)
        controls.addStretch(1)
        root.addLayout(controls)

        self.progress = QProgressBar()
        self.progress.setRange(0, 100)
        self.progress.setValue(0)
        root.addWidget(self.progress)

        self.log = LogView()
        self.log.setMaximumHeight(110)
        root.addWidget(self.log)

        self.services: list[ServiceInfo] = []
        self._visible: list[ServiceInfo] = []
        self._loaded = False

    # ------------------------------------------------------------------
    def showEvent(self, event) -> None:  # noqa: N802 - Qt API
        super().showEvent(event)
        if not self._loaded:
            self._loaded = True
            self.load()

    def load(self) -> None:
        self.refresh_btn.setEnabled(False)
        self.progress.setRange(0, 0)
        worker = Worker(list_services)
        worker.signals.finished.connect(self._on_services)
        worker.signals.failed.connect(self._on_failed)
        start_worker(worker)

    def _on_services(self, services_list: list[ServiceInfo]) -> None:
        self.services = services_list
        self.refresh_btn.setEnabled(True)
        self.progress.setRange(0, 100)
        self.progress.setValue(100)
        self._render()
        self.log.log(f"Загружено служб: {len(services_list)}")

    def _render(self) -> None:
        query = self.search.text().strip().lower()
        only_recommended = self.recommended_only.isChecked()
        visible: list[ServiceInfo] = []
        for service in self.services:
            if only_recommended and not service.is_recommended:
                continue
            if query and query not in service.display_name.lower() and query not in service.name.lower():
                continue
            visible.append(service)
        self._visible = visible
        self.table.setRowCount(0)
        for service in visible:
            row = self.table.rowCount()
            self.table.insertRow(row)
            name_item = QTableWidgetItem(service.display_name)
            if service.is_recommended:
                name_item.setToolTip(f"Рекомендуется отключить: {service.recommendation}")
            self.table.setItem(row, 0, name_item)
            self.table.setItem(row, 1, QTableWidgetItem(service.name))
            self.table.setItem(
                row, 2, QTableWidgetItem(STATE_LABELS.get(service.state, service.state))
            )
            self.table.setItem(
                row, 3, QTableWidgetItem(START_MODE_LABELS.get(service.start_mode, service.start_mode))
            )

    def _selected(self) -> ServiceInfo | None:
        rows = self.table.selectionModel().selectedRows() if self.table.selectionModel() else []
        if not rows:
            return None
        index = rows[0].row()
        if 0 <= index < len(self._visible):
            return self._visible[index]
        return None

    def _on_select(self) -> None:
        service = self._selected()
        if service is None:
            return
        self.details.clear()
        self.details.add_row("Служба", service.display_name)
        self.details.add_row("Описание", service.description or "—")
        self.details.add_row("Путь", service.path or "—")
        self.details.add_row("Учётная запись", service.account or "—")
        mode = _CIM_TO_MODE.get(service.start_mode, "Manual")
        index = self.mode_combo.findData(mode)
        if index >= 0:
            self.mode_combo.setCurrentIndex(index)

    # ------------------------------------------------------------------
    def _run_action(self, label: str, fn, *args) -> None:
        self.progress.setRange(0, 0)
        self.refresh_btn.setEnabled(False)
        worker = Worker(fn, *args)
        worker.signals.finished.connect(lambda result: self._on_action(label, result))
        worker.signals.failed.connect(self._on_failed)
        start_worker(worker)

    def _apply_mode(self) -> None:
        service = self._selected()
        if service is None:
            self.log.log("Служба не выбрана.")
            return
        mode = self.mode_combo.currentData()
        self._run_action(f"{service.name}: тип запуска", services.set_start_mode, service.name, mode)

    def _change(self, action: str) -> None:
        service = self._selected()
        if service is None:
            self.log.log("Служба не выбрана.")
            return
        if action == "start":
            self._run_action(f"{service.name}: запуск", services.start_service, service.name)
        elif action == "stop":
            self._run_action(f"{service.name}: остановка", services.stop_service, service.name)
        else:
            if not is_admin():
                self.log.log("Для отключения службы нужны права администратора.")
            self._run_action(f"{service.name}: отключение", services.disable_service, service.name)

    def _on_action(self, label: str, result: tuple[bool, str]) -> None:
        ok, message = result if isinstance(result, tuple) else (bool(result), "")
        self.progress.setRange(0, 100)
        self.progress.setValue(100)
        self.log.log(f"{label}: {'OK' if ok else 'ошибка'} — {message}")
        self.load()

    def _on_failed(self, message: str) -> None:
        self.progress.setRange(0, 100)
        self.progress.setValue(0)
        self.refresh_btn.setEnabled(True)
        self.log.log(f"Ошибка: {message}")
