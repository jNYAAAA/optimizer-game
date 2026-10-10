"""Оптимизация игр: сетка игр и экран настроек с выбором значений."""
from __future__ import annotations

from PySide6.QtCore import Qt, QThreadPool, Signal
from PySide6.QtGui import QPixmap
from PySide6.QtWidgets import (
    QComboBox,
    QFrame,
    QGridLayout,
    QHBoxLayout,
    QLabel,
    QProgressBar,
    QPushButton,
    QStackedWidget,
    QVBoxLayout,
    QWidget,
)

from ...core.games import (
    GAMES,
    GameProfile,
    GameSettingsResult,
    Setting,
    apply_setting_values,
    find_game_files,
    running_game_keys,
)
from ...core.workers import Worker, start_worker
from ...utils import resource_path
from .. import theme
from ..widgets import Card, LogView, make_header


class _GameTile(QFrame):
    clicked = Signal()

    def __init__(self, profile: GameProfile, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setObjectName("Card")
        self.setCursor(Qt.PointingHandCursor)
        self.setFixedSize(260, 190)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(18, 18, 18, 14)
        layout.setSpacing(10)

        logo = QLabel()
        logo.setAlignment(Qt.AlignCenter)
        pixmap = QPixmap(resource_path(f"assets/{profile.logo}"))
        if not pixmap.isNull():
            logo.setPixmap(pixmap.scaled(200, 96, Qt.KeepAspectRatio, Qt.SmoothTransformation))
        layout.addWidget(logo, 1)

        name = QLabel(profile.name)
        name.setObjectName("Value")
        name.setAlignment(Qt.AlignCenter)
        name.setWordWrap(True)
        layout.addWidget(name)

    def mousePressEvent(self, event) -> None:  # noqa: N802 - Qt API
        self.clicked.emit()
        super().mousePressEvent(event)


class _SettingRow(QWidget):
    apply_requested = Signal(object, str)

    def __init__(self, setting: Setting, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setting = setting

        layout = QHBoxLayout(self)
        layout.setContentsMargins(0, 3, 0, 3)
        layout.setSpacing(8)

        info = QLabel()
        pixmap = QPixmap(resource_path("assets/info.png"))
        if not pixmap.isNull():
            info.setPixmap(pixmap)
        info.setToolTip(setting.help or setting.label)
        info.setCursor(Qt.WhatsThisCursor)
        layout.addWidget(info)

        name = QLabel(setting.label)
        name.setObjectName("Caption")
        name.setWordWrap(True)
        layout.addWidget(name, 1)

        self.combo = QComboBox()
        options = setting.options or [(setting.value, setting.value)]
        for value, label in options:
            self.combo.addItem(label, value)
        index = self.combo.findData(setting.value)
        if index >= 0:
            self.combo.setCurrentIndex(index)
        self.combo.setMinimumWidth(160)
        layout.addWidget(self.combo)

        self.apply_btn = QPushButton("ПРИМЕНИТЬ")
        self.apply_btn.setObjectName("Segment")
        self.apply_btn.clicked.connect(
            lambda: self.apply_requested.emit(self.setting, self.combo.currentData())
        )
        layout.addWidget(self.apply_btn)

    def value(self) -> str:
        return self.combo.currentData()


class _GamePanel(QWidget):
    back_requested = Signal()

    def __init__(self, profile: GameProfile, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.profile = profile

        root = QVBoxLayout(self)
        root.setContentsMargins(0, 0, 0, 0)
        root.setSpacing(12)

        top = QHBoxLayout()
        back = QPushButton("НАЗАД")
        back.clicked.connect(self.back_requested.emit)
        top.addWidget(back)
        top.addStretch(1)
        root.addLayout(top)

        card = Card(profile.name)
        logo = QLabel()
        pixmap = QPixmap(resource_path(f"assets/{profile.logo}"))
        if not pixmap.isNull():
            logo.setPixmap(pixmap.scaled(140, 48, Qt.KeepAspectRatio, Qt.SmoothTransformation))
        card.add_header_widget(logo)

        self._rows: list[_SettingRow] = []
        for setting in profile.settings:
            row = _SettingRow(setting)
            row.apply_requested.connect(self._apply_one)
            card.body.addWidget(row, card.body.rowCount(), 0, 1, 2)
            self._rows.append(row)
        root.addWidget(card)

        controls = QHBoxLayout()
        self.apply_btn = QPushButton("ПРИМЕНИТЬ ВСЁ")
        self.apply_btn.setObjectName("Primary")
        self.apply_btn.clicked.connect(self._apply_all)
        controls.addWidget(self.apply_btn)
        self.status = QLabel("Проверка файлов…")
        self.status.setObjectName("PageHint")
        self.status.setWordWrap(True)
        controls.addWidget(self.status, 1)
        root.addLayout(controls)

        self.progress = QProgressBar()
        self.progress.setRange(0, 100)
        self.progress.setValue(0)
        root.addWidget(self.progress)

        self.log = LogView()
        self.log.setMaximumHeight(100)
        root.addWidget(self.log)

        self._loaded = False

    def showEvent(self, event) -> None:  # noqa: N802 - Qt API
        super().showEvent(event)
        if not self._loaded:
            self._loaded = True
            self.refresh()

    def refresh(self) -> None:
        self.progress.setRange(0, 0)
        worker = Worker(find_game_files, self.profile)
        worker.signals.finished.connect(self._on_files)
        worker.signals.failed.connect(self._on_failed)
        start_worker(worker)

    def _on_files(self, files: list) -> None:
        self.progress.setRange(0, 100)
        self.progress.setValue(100)
        running = self.profile.key in running_game_keys()
        if not files:
            self.status.setText(f"Файлы настроек {self.profile.name} не найдены.")
            self.status.setStyleSheet(f"color: {theme.palette()['TEXT_DIM']};")
            self.apply_btn.setEnabled(False)
            return
        self.apply_btn.setEnabled(True)
        note = f"{self.profile.name} запущена — закройте игру." if running else ""
        self.status.setText(f"Найдено профилей: {len(files)}. {note}".strip())
        self.status.setStyleSheet(
            f"color: {theme.palette()['WARN'] if running else theme.palette()['TEXT_DIM']};"
        )

    def _set_busy(self, busy: bool) -> None:
        self.apply_btn.setEnabled(not busy)
        for row in self._rows:
            row.apply_btn.setEnabled(not busy)

    def _apply_all(self) -> None:
        items = [(row.setting, row.value()) for row in self._rows]
        self._run(items, "Применение настроек…")

    def _apply_one(self, setting: Setting, value: str) -> None:
        self._run([(setting, value)], f"Применение: {setting.label}…")

    def _run(self, items: list, label: str) -> None:
        self._set_busy(True)
        self.progress.setRange(0, 100)
        self.progress.setValue(0)
        self.status.setText(label)
        self.status.setStyleSheet("")
        worker = Worker(apply_setting_values, self.profile, items, pass_progress=True)
        worker.signals.progress.connect(self._on_progress)
        worker.signals.finished.connect(self._on_applied)
        worker.signals.failed.connect(self._on_failed)
        start_worker(worker)

    def _on_progress(self, percent: int, message: str) -> None:
        self.progress.setValue(percent)
        if message:
            self.status.setText(message)

    def _on_applied(self, result: GameSettingsResult) -> None:
        palette = theme.palette()
        self._set_busy(False)
        self.progress.setValue(100)
        self.status.setText(result.message)
        self.status.setStyleSheet(f"color: {palette['OK'] if result.ok else palette['DANGER']};")
        self.log.log(result.message)
        if result.backup_dir:
            self.log.log(f"Резервные копии: {result.backup_dir}")

    def _on_failed(self, message: str) -> None:
        self._set_busy(False)
        self.progress.setRange(0, 100)
        self.progress.setValue(0)
        self.status.setText(f"Ошибка: {message}")
        self.status.setStyleSheet(f"color: {theme.palette()['DANGER']};")
        self.log.log(f"Ошибка: {message}")


class GamesPage(QWidget):
    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        root = QVBoxLayout(self)
        root.setContentsMargins(24, 20, 24, 20)
        root.setSpacing(14)

        root.addWidget(
            make_header(
                "Оптимизация игр",
                "Выберите игру — приложение применит профиль настроек «максимум FPS без "
                "потери качества». Настройки можно менять и применять по отдельности.",
            )
        )

        self._stack = QStackedWidget()

        grid_page = QWidget()
        grid = QGridLayout(grid_page)
        grid.setContentsMargins(0, 4, 0, 0)
        grid.setSpacing(16)
        for index, profile in enumerate(GAMES):
            tile = _GameTile(profile)
            tile.clicked.connect(lambda idx=index: self._stack.setCurrentIndex(idx + 1))
            grid.addWidget(tile, index // 3, index % 3)
        grid.setColumnStretch(0, 1)
        grid.setColumnStretch(1, 1)
        grid.setColumnStretch(2, 1)
        grid.setRowStretch((len(GAMES) + 2) // 3, 1)
        self._stack.addWidget(grid_page)

        for profile in GAMES:
            panel = _GamePanel(profile)
            panel.back_requested.connect(lambda: self._stack.setCurrentIndex(0))
            self._stack.addWidget(panel)

        root.addWidget(self._stack, 1)
