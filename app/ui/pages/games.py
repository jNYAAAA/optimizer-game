"""Оптимизация игр: сетка игр и экран настроек с выбором значений и откатом."""
from __future__ import annotations

from pathlib import Path

from PySide6.QtCore import Qt, QThreadPool, Signal
from PySide6.QtGui import QPixmap
from PySide6.QtWidgets import (
    QComboBox,
    QFrame,
    QGridLayout,
    QHBoxLayout,
    QLabel,
    QMessageBox,
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
    restore_game_settings,
    running_game_keys,
)
from ...core.workers import Worker, start_worker
from ...utils import resource_path
from .. import theme
from ..widgets import Card, LogView, make_header

COVER_W, COVER_H = 155, 232


def _cover_pixmap(profile: GameProfile, width: int, height: int) -> QPixmap:
    pixmap = QPixmap(resource_path(f"assets/{profile.logo}"))
    if pixmap.isNull():
        return pixmap
    return pixmap.scaled(width, height, Qt.KeepAspectRatio, Qt.SmoothTransformation)


class _GameTile(QFrame):
    clicked = Signal()

    def __init__(self, profile: GameProfile, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setObjectName("Card")
        self.setCursor(Qt.PointingHandCursor)
        self.setFixedSize(205, 320)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(16, 16, 16, 14)
        layout.setSpacing(12)

        cover = QLabel()
        cover.setAlignment(Qt.AlignCenter)
        pixmap = _cover_pixmap(profile, COVER_W, COVER_H)
        if not pixmap.isNull():
            cover.setPixmap(pixmap)
        layout.addWidget(cover, 0, Qt.AlignHCenter)

        name = QLabel(profile.name)
        name.setAlignment(Qt.AlignCenter)
        name.setWordWrap(True)
        name.setStyleSheet("font-size: 15px; font-weight: 600;")
        layout.addWidget(name)
        layout.addStretch(1)

    def mousePressEvent(self, event) -> None:  # noqa: N802 - Qt API
        self.clicked.emit()
        super().mousePressEvent(event)


class _InfoIcon(QLabel):
    hovered = Signal(str)

    def __init__(self, text: str, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self._text = text
        pixmap = QPixmap(resource_path("assets/info.png"))
        if not pixmap.isNull():
            self.setPixmap(pixmap)
        self.setCursor(Qt.WhatsThisCursor)
        self.setToolTip(text)

    def enterEvent(self, event) -> None:  # noqa: N802 - Qt API
        self.hovered.emit(self._text)
        super().enterEvent(event)

    def leaveEvent(self, event) -> None:  # noqa: N802 - Qt API
        self.hovered.emit("")
        super().leaveEvent(event)


class _SettingRow(QWidget):
    apply_requested = Signal(object, str)
    help_hovered = Signal(str)

    def __init__(self, setting: Setting, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setting = setting

        layout = QHBoxLayout(self)
        layout.setContentsMargins(0, 3, 0, 3)
        layout.setSpacing(8)

        self.info = _InfoIcon(setting.help or setting.label)
        self.info.hovered.connect(self.help_hovered.emit)
        layout.addWidget(self.info)

        name = QLabel(setting.label)
        name.setObjectName("Caption")
        name.setWordWrap(True)
        layout.addWidget(name, 1)

        self.combo = QComboBox()
        for value, label in (setting.options or [(setting.value, setting.value)]):
            self.combo.addItem(label, value)
        index = self.combo.findData(setting.value)
        if index >= 0:
            self.combo.setCurrentIndex(index)
        self.combo.setMinimumWidth(170)
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
        back = QPushButton("←  НАЗАД")
        back.setObjectName("Back")
        back.setCursor(Qt.PointingHandCursor)
        back.clicked.connect(self.back_requested.emit)
        top.addWidget(back)
        top.addStretch(1)
        root.addLayout(top)

        header = QHBoxLayout()
        header.setSpacing(18)
        cover = QLabel()
        cover.setPixmap(_cover_pixmap(profile, 170, 255))
        header.addWidget(cover, 0, Qt.AlignTop)
        info = QVBoxLayout()
        info.setSpacing(6)
        name = QLabel(profile.name)
        name.setObjectName("PageTitle")
        info.addWidget(name)
        caption = QLabel(
            f"{len(profile.settings)} настроек · профиль «максимум FPS без потери качества»"
        )
        caption.setObjectName("Caption")
        info.addWidget(caption)
        self.help_label = QLabel("Наведите на значок (i), чтобы узнать, за что отвечает настройка.")
        self.help_label.setObjectName("PageHint")
        self.help_label.setWordWrap(True)
        info.addWidget(self.help_label)
        info.addStretch(1)
        header.addLayout(info, 1)
        root.addLayout(header)

        card = Card("Настройки")
        self._rows: list[_SettingRow] = []
        for setting in profile.settings:
            row = _SettingRow(setting)
            row.apply_requested.connect(self._apply_one)
            row.help_hovered.connect(self._on_help)
            card.body.addWidget(row, card.body.rowCount(), 0, 1, 2)
            self._rows.append(row)
        root.addWidget(card)

        controls = QHBoxLayout()
        self.apply_btn = QPushButton("ПРИМЕНИТЬ ВСЁ")
        self.apply_btn.setObjectName("Primary")
        self.apply_btn.clicked.connect(self._apply_all)
        controls.addWidget(self.apply_btn)
        self.restore_btn = QPushButton("ОТКАТ")
        self.restore_btn.setObjectName("Danger")
        self.restore_btn.clicked.connect(self._restore)
        controls.addWidget(self.restore_btn)
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
        self.log.setMaximumHeight(90)
        root.addWidget(self.log)
        root.addStretch(1)

        self._loaded = False

    def showEvent(self, event) -> None:  # noqa: N802 - Qt API
        super().showEvent(event)
        if not self._loaded:
            self._loaded = True
            self.refresh()

    def _on_help(self, text: str) -> None:
        self.help_label.setText(
            text or "Наведите на значок (i), чтобы узнать, за что отвечает настройка."
        )

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
        existing = [f for f in files if Path(f).is_file()]
        if not files:
            self.status.setText(f"Файлы настроек {self.profile.name} не найдены.")
            self.status.setStyleSheet(f"color: {theme.palette()['TEXT_DIM']};")
            self.apply_btn.setEnabled(False)
            self.restore_btn.setEnabled(False)
            return
        self.apply_btn.setEnabled(True)
        self.restore_btn.setEnabled(True)
        if not existing:
            self.status.setText(
                f"{self.profile.name} не запускалась — файл настроек будет создан при применении."
            )
            self.status.setStyleSheet(f"color: {theme.palette()['TEXT_DIM']};")
            return
        note = f"{self.profile.name} запущена — закройте игру." if running else ""
        self.status.setText(f"Найдено профилей: {len(existing)}. {note}".strip())
        self.status.setStyleSheet(
            f"color: {theme.palette()['WARN'] if running else theme.palette()['TEXT_DIM']};"
        )

    def _set_busy(self, busy: bool) -> None:
        self.apply_btn.setEnabled(not busy)
        self.restore_btn.setEnabled(not busy)
        for row in self._rows:
            row.apply_btn.setEnabled(not busy)

    def _apply_all(self) -> None:
        items = [(row.setting, row.value()) for row in self._rows]
        self._run("Применение настроек…", apply_setting_values, self.profile, items)

    def _apply_one(self, setting: Setting, value: str) -> None:
        self._run(
            f"Применение: {setting.label}…",
            apply_setting_values,
            self.profile,
            [(setting, value)],
        )

    def _restore(self) -> None:
        answer = QMessageBox.question(
            self,
            "Откат настроек",
            f"Вернуть исходные настройки {self.profile.name} из резервной копии?",
            QMessageBox.Yes | QMessageBox.No,
            QMessageBox.No,
        )
        if answer != QMessageBox.Yes:
            return
        self._run("Откат настроек…", restore_game_settings, self.profile)

    def _run(self, label: str, fn, *args) -> None:
        self._set_busy(True)
        self.progress.setRange(0, 100)
        self.progress.setValue(0)
        self.status.setText(label)
        self.status.setStyleSheet("")
        worker = Worker(fn, *args, pass_progress=True)
        worker.signals.progress.connect(self._on_progress)
        worker.signals.finished.connect(self._on_done)
        worker.signals.failed.connect(self._on_failed)
        start_worker(worker)

    def _on_progress(self, percent: int, message: str) -> None:
        self.progress.setValue(percent)
        if message:
            self.status.setText(message)

    def _on_done(self, result: GameSettingsResult) -> None:
        palette = theme.palette()
        self._set_busy(False)
        self.progress.setValue(100)
        self.status.setText(result.message)
        self.status.setStyleSheet(f"color: {palette['OK'] if result.ok else palette['DANGER']};")
        self.log.log(result.message)

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
                "потери качества». Каждую настройку можно менять и применять отдельно, "
                "а также откатить изменения.",
            )
        )

        self._stack = QStackedWidget()

        grid_page = QWidget()
        outer = QVBoxLayout(grid_page)
        outer.setContentsMargins(0, 0, 0, 0)
        row = QHBoxLayout()
        row.addStretch(1)
        grid = QGridLayout()
        grid.setSpacing(20)
        for index, profile in enumerate(GAMES):
            tile = _GameTile(profile)
            tile.clicked.connect(lambda idx=index: self._stack.setCurrentIndex(idx + 1))
            grid.addWidget(tile, index // 4, index % 4, Qt.AlignCenter)
        row.addLayout(grid)
        row.addStretch(1)
        outer.addLayout(row)
        outer.addStretch(1)
        self._stack.addWidget(grid_page)

        for profile in GAMES:
            panel = _GamePanel(profile)
            panel.back_requested.connect(lambda: self._stack.setCurrentIndex(0))
            self._stack.addWidget(panel)

        root.addWidget(self._stack, 1)
