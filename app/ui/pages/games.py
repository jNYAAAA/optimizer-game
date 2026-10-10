"""Оптимизация игр: под-вкладки по играм с применением настроек."""
from __future__ import annotations

from PySide6.QtCore import QSize, Qt, QThreadPool
from PySide6.QtGui import QIcon, QPixmap
from PySide6.QtWidgets import (
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
    apply_game_settings,
    find_game_files,
    running_game_keys,
)
from ...core.workers import Worker, start_worker
from ...utils import resource_path
from .. import theme
from ..widgets import Card, LogView, make_header


class _GamePanel(QWidget):
    def __init__(self, profile: GameProfile, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.profile = profile

        root = QVBoxLayout(self)
        root.setContentsMargins(0, 0, 0, 0)
        root.setSpacing(12)

        card = Card(profile.name)
        logo = QLabel()
        pixmap = QPixmap(resource_path(f"assets/{profile.logo}"))
        if not pixmap.isNull():
            logo.setPixmap(pixmap.scaled(30, 30, Qt.KeepAspectRatio, Qt.SmoothTransformation))
        card.add_header_widget(logo)
        for setting in profile.settings:
            card.add_row(setting.label, "будет применено")
        root.addWidget(card)

        controls = QHBoxLayout()
        self.apply_btn = QPushButton("ПРИМЕНИТЬ НАСТРОЙКИ")
        self.apply_btn.setObjectName("Primary")
        self.apply_btn.clicked.connect(self._apply)
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
        self.log.setMaximumHeight(120)
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

    def _apply(self) -> None:
        self.apply_btn.setEnabled(False)
        self.progress.setRange(0, 100)
        self.progress.setValue(0)
        worker = Worker(apply_game_settings, self.profile, pass_progress=True)
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
        self.apply_btn.setEnabled(True)
        self.progress.setValue(100)
        self.status.setText(result.message)
        self.status.setStyleSheet(f"color: {palette['OK'] if result.ok else palette['DANGER']};")
        self.log.log(result.message)
        if result.backup_dir:
            self.log.log(f"Резервные копии: {result.backup_dir}")
        for path in result.files:
            self.log.log(f"Обновлено: {path}")

    def _on_failed(self, message: str) -> None:
        self.apply_btn.setEnabled(True)
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
        root.setSpacing(12)

        root.addWidget(
            make_header(
                "Оптимизация игр",
                "Готовые профили настроек с применением в один клик. Исходные файлы "
                "сохраняются в папке данных приложения.",
            )
        )

        segment = QHBoxLayout()
        segment.setSpacing(8)
        self._buttons: list[QPushButton] = []
        self._stack = QStackedWidget()
        for index, profile in enumerate(GAMES):
            button = QPushButton(profile.name)
            button.setObjectName("Segment")
            button.setCheckable(True)
            button.setCursor(Qt.PointingHandCursor)
            icon = QIcon(resource_path(f"assets/{profile.logo}"))
            if not icon.isNull():
                button.setIcon(icon)
                button.setIconSize(QSize(20, 20))
            button.clicked.connect(lambda _checked=False, idx=index: self._select(idx))
            segment.addWidget(button)
            self._buttons.append(button)
            self._stack.addWidget(_GamePanel(profile))
        segment.addStretch(1)
        root.addLayout(segment)
        root.addWidget(self._stack, 1)

        self._select(0)

    def _select(self, index: int) -> None:
        for i, button in enumerate(self._buttons):
            button.setChecked(i == index)
        self._stack.setCurrentIndex(index)
