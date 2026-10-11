"""Оптимизация игр: сетка игр и экран настроек с под-разделами."""
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
    GAME_PRESETS,
    GAMES,
    GameProfile,
    GameSettingsResult,
    Setting,
    apply_setting_values,
    find_game_files,
    preset_value,
    restore_game_settings,
    running_game_keys,
)
from ...core.workers import Worker, start_worker
from ...utils import resource_path
from .. import theme
from ..widgets import Card, InfoIcon, LogView, make_header
from .launch import LaunchOptionsPage
from .nvidia import NvidiaPage
from .win_settings import WinSettingsPage

COVER_W, COVER_H = 155, 232

# Под-разделы экрана игры.
SECTIONS = ["ИГРА", "NVIDIA", "ЗАПУСК", "WINDOWS"]


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


class _SettingRow(QFrame):
    apply_requested = Signal(object, str)
    help_hovered = Signal(str)

    def __init__(self, setting: Setting, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setting = setting
        self.setObjectName("OptionRow")

        layout = QHBoxLayout(self)
        layout.setContentsMargins(12, 8, 12, 8)
        layout.setSpacing(10)

        self.info = InfoIcon(setting.help or setting.label)
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

    def set_value(self, value: str) -> None:
        index = self.combo.findData(value)
        if index >= 0:
            self.combo.setCurrentIndex(index)


class _GameSettingsSection(QWidget):
    """Настройки самой игры (файл конфигурации)."""

    def __init__(self, profile: GameProfile, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.profile = profile

        root = QVBoxLayout(self)
        root.setContentsMargins(0, 0, 0, 0)
        root.setSpacing(12)

        self.help_label = QLabel("Наведите на значок (i), чтобы узнать, за что отвечает настройка.")
        self.help_label.setObjectName("PageHint")
        self.help_label.setWordWrap(True)
        root.addWidget(self.help_label)

        preset_bar = QWidget()
        preset_row = QHBoxLayout(preset_bar)
        preset_row.setContentsMargins(0, 0, 0, 0)
        preset_row.setSpacing(8)
        preset_label = QLabel("Профиль:")
        preset_label.setObjectName("Caption")
        preset_row.addWidget(preset_label)
        self._preset_buttons: list[QPushButton] = []
        for key, label in GAME_PRESETS:
            button = QPushButton(label)
            button.setObjectName("Segment")
            button.setCheckable(True)
            button.setCursor(Qt.PointingHandCursor)
            button.clicked.connect(lambda _checked=False, k=key: self._apply_preset(k))
            preset_row.addWidget(button)
            self._preset_buttons.append(button)
        preset_row.addStretch(1)
        root.addWidget(preset_bar)
        self._preset_buttons[0].setChecked(True)
        preset_bar.setVisible(bool(profile.settings))

        card = Card("Настройки")
        self._rows: list[_SettingRow] = []
        for setting in profile.settings:
            row = _SettingRow(setting)
            row.apply_requested.connect(self._apply_one)
            row.help_hovered.connect(self._on_help)
            card.body.addWidget(row, card.body.rowCount(), 0, 1, 2)
            self._rows.append(row)
        card.setVisible(bool(profile.settings))
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
        if not profile.settings:
            self.status.setText("Настройки для этой игры ещё не добавлены.")
        controls.addWidget(self.status, 1)
        root.addLayout(controls)

        self.progress = QProgressBar()
        self.progress.setRange(0, 100)
        self.progress.setValue(0)
        root.addWidget(self.progress)

        self.log = LogView()
        self.log.setMaximumHeight(90)
        root.addWidget(self.log)

        # Блоки NVIDIA и параметров запуска собраны в этом же разделе, чтобы всё
        # нужное для игры было в одном месте. Создаются при первом показе
        # раздела — так открытие панели и смена темы остаются быстрыми.
        self.extras = QVBoxLayout()
        self.extras.setContentsMargins(0, 0, 0, 0)
        self.extras.setSpacing(14)
        root.addLayout(self.extras)
        self.extra_pages: list[QWidget] = []
        self._extras_built = False

        root.addStretch(1)

        self._loaded = False

    def showEvent(self, event) -> None:  # noqa: N802 - Qt API
        super().showEvent(event)
        if not self._loaded:
            self._loaded = True
            self._build_extras()
            self.refresh()

    def _build_extras(self) -> None:
        """Добавляет в раздел «Игра» блоки NVIDIA и параметров запуска."""
        if self._extras_built:
            return
        self._extras_built = True
        for page in (
            NvidiaPage(self.profile.key, show_header=False),
            LaunchOptionsPage(self.profile.key, show_header=False),
        ):
            self.extra_pages.append(page)
            self.extras.addWidget(page)

    def _on_help(self, text: str) -> None:
        self.help_label.setText(
            text or "Наведите на значок (i), чтобы узнать, за что отвечает настройка."
        )

    def _apply_preset(self, key: str) -> None:
        for row in self._rows:
            row.set_value(preset_value(self.profile.key, row.setting, key))
        for button, (preset_key, _label) in zip(self._preset_buttons, GAME_PRESETS):
            button.setChecked(preset_key == key)
        label = dict(GAME_PRESETS).get(key, key)
        self.log.log(f"Выбран профиль «{label}». Нажмите «ПРИМЕНИТЬ ВСЁ», чтобы записать.")

    def refresh(self) -> None:
        if not self.profile.settings:
            self.apply_btn.setEnabled(False)
            self.restore_btn.setEnabled(False)
            self.progress.setRange(0, 100)
            self.progress.setValue(0)
            self.status.setText("Настройки для этой игры ещё не добавлены.")
            return
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
            f"{len(profile.settings)} настроек игры · ниже в этом же разделе — "
            "параметры NVIDIA и запуска Steam"
        )
        caption.setObjectName("Caption")
        info.addWidget(caption)
        info.addStretch(1)
        header.addLayout(info, 1)
        root.addLayout(header)

        self._section_stack = QStackedWidget()
        self._section_buttons: list[QPushButton] = []
        settings_section = _GameSettingsSection(profile)
        # Под-разделы создаются только при первом открытии —
        # это заметно ускоряет запуск и смену темы.
        self._section_pages: list[QWidget | None] = [settings_section, None, None, None]
        segment = QHBoxLayout()
        segment.setSpacing(8)
        for index, title in enumerate(SECTIONS):
            button = QPushButton(title)
            button.setObjectName("Segment")
            button.setCheckable(True)
            button.setCursor(Qt.PointingHandCursor)
            button.clicked.connect(lambda _checked=False, idx=index: self._select_section(idx))
            segment.addWidget(button)
            self._section_buttons.append(button)
        segment.addStretch(1)
        self._section_stack.addWidget(settings_section)
        root.addLayout(segment)
        root.addWidget(self._section_stack, 1)
        self._select_section(0)

        root.addStretch(0)

    def _ensure_section(self, index: int) -> QWidget:
        page = self._section_pages[index]
        if page is None:
            if index == 1:
                page = NvidiaPage(self.profile.key, show_header=False)
            elif index == 2:
                page = LaunchOptionsPage(self.profile.key, show_header=False)
            else:
                page = WinSettingsPage(self.profile.key, show_header=False)
            self._section_pages[index] = page
            self._section_stack.addWidget(page)
        return page

    def _select_section(self, index: int) -> None:
        page = self._ensure_section(index)
        for i, button in enumerate(self._section_buttons):
            button.setChecked(i == index)
        self._section_stack.setCurrentWidget(page)


class GamesPage(QWidget):
    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        root = QVBoxLayout(self)
        root.setContentsMargins(24, 20, 24, 20)
        root.setSpacing(14)

        root.addWidget(
            make_header(
                "Оптимизация игр",
                "Выберите игру — у каждой есть под-разделы «Игра» (настройки игры с "
                "пресетами «Макс. производительность / Баланс / Качество», а также блоки "
                "NVIDIA и параметры запуска Steam), «NVIDIA», «Запуск» и «Windows».",
            )
        )

        self._stack = QStackedWidget()
        self._grid_index = 0
        # Панель игры создаётся при первом открытии: так при старте и при смене
        # темы пересобирается значительно меньше виджетов.
        self._panels: dict[int, int] = {}

        grid_page = QWidget()
        outer = QVBoxLayout(grid_page)
        outer.setContentsMargins(0, 0, 0, 0)
        row = QHBoxLayout()
        row.addStretch(1)
        grid = QGridLayout()
        grid.setSpacing(20)
        for index, profile in enumerate(GAMES):
            tile = _GameTile(profile)
            tile.clicked.connect(lambda idx=index: self._open_game(idx))
            grid.addWidget(tile, index // 4, index % 4, Qt.AlignCenter)
        row.addLayout(grid)
        row.addStretch(1)
        outer.addLayout(row)
        outer.addStretch(1)
        self._stack.addWidget(grid_page)

        root.addWidget(self._stack, 1)

    def _open_game(self, index: int) -> None:
        stack_index = self._panels.get(index)
        if stack_index is None:
            panel = _GamePanel(GAMES[index])
            panel.back_requested.connect(lambda: self._stack.setCurrentIndex(self._grid_index))
            stack_index = self._stack.addWidget(panel)
            self._panels[index] = stack_index
        self._stack.setCurrentIndex(stack_index)
