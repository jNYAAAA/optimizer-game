"""Оптимизация игр: карточки игр с применением рекомендованных настроек."""
from __future__ import annotations

from PySide6.QtCore import Qt, QThreadPool
from PySide6.QtGui import QPixmap
from PySide6.QtWidgets import (
    QHBoxLayout,
    QLabel,
    QProgressBar,
    QPushButton,
    QVBoxLayout,
    QWidget,
)

from ...core.games import (
    CS2_SETTINGS,
    GameSettingsResult,
    apply_cs2_settings,
    find_cs2_video_files,
    is_cs2_running,
)
from ...core.workers import Worker, start_worker
from ...utils import resource_path
from .. import theme
from ..widgets import Card, LogView, make_header


class GamesPage(QWidget):
    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        root = QVBoxLayout(self)
        root.setContentsMargins(24, 20, 24, 20)
        root.setSpacing(14)

        root.addWidget(
            make_header(
                "Оптимизация игр",
                "Готовые профили настроек для игр с применением в один клик. "
                "Исходные файлы сохраняются в папке данных приложения.",
            )
        )

        self.cs2_card = Card("Counter-Strike 2")
        logo = QLabel()
        pixmap = QPixmap(resource_path("assets/cs2.png"))
        if not pixmap.isNull():
            logo.setPixmap(pixmap.scaled(30, 30, Qt.KeepAspectRatio, Qt.SmoothTransformation))
        self.cs2_card.add_header_widget(logo)
        for _key, _value, label in CS2_SETTINGS:
            self.cs2_card.add_row(label, "будет применено")
        root.addWidget(self.cs2_card)

        controls = QHBoxLayout()
        self.apply_btn = QPushButton("ПРИМЕНИТЬ НАСТРОЙКИ")
        self.apply_btn.setObjectName("Primary")
        self.apply_btn.clicked.connect(self._apply)
        controls.addWidget(self.apply_btn)
        self.status = QLabel("Проверка профилей CS2…")
        self.status.setObjectName("PageHint")
        self.status.setWordWrap(True)
        controls.addWidget(self.status, 1)
        root.addLayout(controls)

        self.progress = QProgressBar()
        self.progress.setRange(0, 100)
        self.progress.setValue(0)
        root.addWidget(self.progress)

        self.log = LogView()
        self.log.setMaximumHeight(140)
        root.addWidget(self.log)

        self._loaded = False

    # ------------------------------------------------------------------
    def showEvent(self, event) -> None:  # noqa: N802 - Qt API
        super().showEvent(event)
        if not self._loaded:
            self._loaded = True
            self.refresh()

    def refresh(self) -> None:
        self.progress.setRange(0, 0)
        worker = Worker(find_cs2_video_files)
        worker.signals.finished.connect(self._on_files)
        worker.signals.failed.connect(self._on_failed)
        start_worker(worker)

    def _on_files(self, files: list) -> None:
        self.progress.setRange(0, 100)
        self.progress.setValue(100)
        running = is_cs2_running()
        if not files:
            self.status.setText("Профили CS2 не найдены (игра не установлена?).")
            self.status.setStyleSheet(f"color: {theme.palette()['TEXT_DIM']};")
            self.apply_btn.setEnabled(False)
            return
        self.apply_btn.setEnabled(True)
        note = "CS2 запущена — закройте игру перед применением." if running else ""
        self.status.setText(
            f"Найдено профилей: {len(files)}. {note}".strip()
        )
        self.status.setStyleSheet(
            f"color: {theme.palette()['WARN'] if running else theme.palette()['TEXT_DIM']};"
        )
        for path in files:
            self.log.log(f"Профиль: {path}")

    # ------------------------------------------------------------------
    def _apply(self) -> None:
        self.apply_btn.setEnabled(False)
        self.progress.setRange(0, 100)
        self.progress.setValue(0)
        worker = Worker(apply_cs2_settings, pass_progress=True)
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
