"""Оптимизация игр: сетка игр и экран настроек с под-разделами."""
from __future__ import annotations

from pathlib import Path

from PySide6.QtCore import QRectF, Qt, QThreadPool, Signal
from PySide6.QtGui import (
    QBrush,
    QColor,
    QFont,
    QLinearGradient,
    QPainter,
    QPainterPath,
    QPen,
    QPixmap,
)
from PySide6.QtWidgets import (
    QComboBox,
    QFrame,
    QGridLayout,
    QHBoxLayout,
    QLabel,
    QLineEdit,
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
from .shadows import NoShadowsPage
from .win_settings import WinSettingsPage

# Обложка в сетке занимает всю плитку (соотношение картинок 2:3).
TILE_MIN, TILE_MAX = 150, 340
TILE_RATIO = 1.5
TILE_RADIUS = 10
GRID_SPACING = 22
GRID_SPACING_MAX = 46

# Под-разделы экрана игры. «Убрать тени» — сразу после «Игра» и только у игр,
# у которых включён флаг profile.disable_shadows.
SECTIONS = ["ИГРА", "NVIDIA", "ЗАПУСК", "WINDOWS"]
SHADOW_SECTION = "УБРАТЬ ТЕНИ"


def _cover_pixmap(profile: GameProfile, width: int, height: int, fill: bool = False) -> QPixmap:
    source = QPixmap(resource_path(f"assets/{profile.logo}"))
    if source.isNull():
        return source
    if fill:
        return _fill_pixmap(source, width, height)
    return source.scaled(width, height, Qt.KeepAspectRatio, Qt.SmoothTransformation)


def _fill_pixmap(source: QPixmap, width: int, height: int) -> QPixmap:
    """Обрезает картинку «под заполнение» плитки; скругление делает сама плитка."""
    if source.isNull():
        return source
    scaled = source.scaled(
        width, height, Qt.KeepAspectRatioByExpanding, Qt.SmoothTransformation
    )
    x = max((scaled.width() - width) // 2, 0)
    y = max((scaled.height() - height) // 2, 0)
    return scaled.copy(x, y, width, height)


class _GameTile(QFrame):
    """Плитка игры: обложка, градиент, название и обводка — всё рисуется вручную.

    QLabel внутри плитки не используется: так скругление и подсветка ложатся
    ровно по контуру, без «просветов» рамки по краям.
    """

    clicked = Signal()

    def __init__(self, profile: GameProfile, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.profile = profile
        self.setObjectName("GameTile")
        self.setCursor(Qt.PointingHandCursor)
        self.setAttribute(Qt.WA_Hover, True)
        self._hover = False
        self._source = QPixmap(resource_path(f"assets/{profile.logo}"))
        self._cover = QPixmap()
        # Стартовый размер — минимальный, иначе фиксированные плитки не дают
        # странице ужаться и сетка вылезает за край окна.
        self.set_size(TILE_MIN, int(TILE_MIN * TILE_RATIO))

    # ------------------------------------------------------------------
    def set_size(self, width: int, height: int) -> None:
        """Меняет размер плитки и пересобирает обложку под новый размер."""
        self.setFixedSize(width, height)
        self._cover = _fill_pixmap(self._source, width, height)
        self.update()

    def enterEvent(self, event) -> None:  # noqa: N802 - Qt API
        self._hover = True
        self.update()
        super().enterEvent(event)

    def leaveEvent(self, event) -> None:  # noqa: N802 - Qt API
        self._hover = False
        self.update()
        super().leaveEvent(event)

    def paintEvent(self, event) -> None:  # noqa: N802 - Qt API
        colors = theme.palette()
        painter = QPainter(self)
        painter.setRenderHint(QPainter.Antialiasing, True)
        painter.setRenderHint(QPainter.SmoothPixmapTransform, True)

        width, height = self.width(), self.height()
        # Обложка кладётся ровно по контуру плитки: скругляет её только маска,
        # поэтому по краям не остаётся ни окантовки, ни «вылезающих» углов.
        clip = QPainterPath()
        clip.addRoundedRect(QRectF(0, 0, width, height), TILE_RADIUS, TILE_RADIUS)
        painter.setClipPath(clip)

        if self._cover.isNull():
            painter.fillRect(self.rect(), QColor(38, 44, 52))
        else:
            painter.drawPixmap(0, 0, self._cover)

        # Затемнение снизу под название.
        gradient = QLinearGradient(0, height * 0.55, 0, height)
        gradient.setColorAt(0.0, QColor(0, 0, 0, 0))
        gradient.setColorAt(0.6, QColor(0, 0, 0, 130))
        gradient.setColorAt(1.0, QColor(0, 0, 0, 215))
        painter.fillPath(clip, QBrush(gradient))

        font = QFont(self.font())
        font.setPointSizeF(max(10.0, width * 0.05))
        font.setBold(True)
        painter.setFont(font)
        painter.setPen(QColor("#FFFFFF"))
        text_area = QRectF(8, height - 56, width - 16, 44)
        painter.drawText(
            text_area, int(Qt.AlignHCenter | Qt.AlignBottom | Qt.TextWordWrap), self.profile.name
        )

        # Подсветка при наведении — по контуру, ровно внутри плитки.
        if self._hover:
            painter.setClipping(False)
            painter.setBrush(Qt.NoBrush)
            painter.setPen(QPen(QColor(colors["ACCENT"]), 2))
            painter.drawRoundedRect(
                QRectF(1, 1, width - 2, height - 2), TILE_RADIUS, TILE_RADIUS
            )
        painter.end()

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

        # Подсказка показывает ключ в файле и точное значение, которое будет
        # записано, — удобно сверять с GameUserSettings.ini.
        self.info.set_text(self.hint())
        self.combo.currentIndexChanged.connect(lambda _index=0: self.info.set_text(self.hint()))

        self.apply_btn = QPushButton("ПРИМЕНИТЬ")
        self.apply_btn.setObjectName("Segment")
        self.apply_btn.clicked.connect(
            lambda: self.apply_requested.emit(self.setting, self.combo.currentData())
        )
        layout.addWidget(self.apply_btn)

    def hint(self) -> str:
        base = self.setting.help or self.setting.label
        return (
            f"{base}\n\nКлюч в файле: {self.setting.key}\n"
            f"Будет записано: {self.setting.key}={self.value()}"
        )

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
        root.addStretch(1)

        self._loaded = False

    def showEvent(self, event) -> None:  # noqa: N802 - Qt API
        super().showEvent(event)
        if not self._loaded:
            self._loaded = True
            self.refresh()

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
        caption = QLabel(self._caption_text(profile))
        caption.setObjectName("Caption")
        info.addWidget(caption)
        info.addStretch(1)
        header.addLayout(info, 1)
        root.addLayout(header)

        self._section_stack = QStackedWidget()
        self._section_buttons: list[QPushButton] = []
        self.sections = list(SECTIONS)
        if profile.disable_shadows:
            self.sections.insert(self.sections.index("ИГРА") + 1, SHADOW_SECTION)
        # Под-разделы создаются только при первом открытии —
        # это заметно ускоряет запуск и смену темы.
        self._section_pages: list[QWidget | None] = [None] * len(self.sections)
        segment = QHBoxLayout()
        segment.setSpacing(8)
        for index, title in enumerate(self.sections):
            button = QPushButton(title)
            button.setObjectName("Segment")
            button.setCheckable(True)
            button.setCursor(Qt.PointingHandCursor)
            button.clicked.connect(lambda _checked=False, idx=index: self._select_section(idx))
            segment.addWidget(button)
            self._section_buttons.append(button)
        segment.addStretch(1)
        root.addLayout(segment)
        root.addWidget(self._section_stack, 1)
        self._select_section(self.sections.index("ИГРА"))

        root.addStretch(0)

    @staticmethod
    def _caption_text(profile: GameProfile) -> str:
        parts: list[str] = []
        parts.append(
            f"{len(profile.settings)} настроек игры"
            if profile.settings
            else "Настройки файла игры ещё не добавлены"
        )
        if profile.disable_shadows:
            parts.append("«Убрать тени»")
        parts.extend(["NVIDIA", "параметры запуска", "Windows"])
        return " · ".join(parts) + " — в своих разделах"

    def _ensure_section(self, index: int) -> QWidget:
        page = self._section_pages[index]
        if page is None:
            title = self.sections[index]
            if title == SHADOW_SECTION:
                page = NoShadowsPage(self.profile, show_header=False)
            elif title == "NVIDIA":
                page = NvidiaPage(self.profile.key, show_header=False)
            elif title == "ЗАПУСК":
                page = LaunchOptionsPage(self.profile.key, show_header=False)
            elif title == "WINDOWS":
                page = WinSettingsPage(self.profile.key, show_header=False)
            else:
                page = _GameSettingsSection(self.profile)
            self._section_pages[index] = page
            self._section_stack.addWidget(page)
        return page

    def _select_section(self, index: int) -> None:
        page = self._ensure_section(index)
        for i, button in enumerate(self._section_buttons):
            button.setChecked(i == index)
        self._section_stack.setCurrentWidget(page)


class GamesPage(QWidget):
    #: сколько плиток в строке сетки
    COLUMNS = 4

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        root = QVBoxLayout(self)
        root.setContentsMargins(24, 20, 24, 20)
        root.setSpacing(14)

        self._header = make_header(
            "Оптимизация игр",
            "Найдите игру в поиске или выберите из списка: настройки игры, NVIDIA, "
            "параметры запуска Steam и Windows.",
        )
        root.addWidget(self._header)

        self._stack = QStackedWidget()
        self._grid_index = 0
        # Панель игры создаётся при первом открытии: так при старте пересобирается
        # значительно меньше виджетов.
        self._panels: dict[int, int] = {}

        grid_page = QWidget()
        outer = QVBoxLayout(grid_page)
        outer.setContentsMargins(0, 0, 0, 0)

        search_row = QHBoxLayout()
        self.search = QLineEdit()
        self.search.setPlaceholderText("Поиск игры…")
        self.search.setClearButtonEnabled(True)
        self.search.textChanged.connect(self._apply_filter)
        search_row.addWidget(self.search, 0)
        search_row.addStretch(1)
        self.search.setMinimumWidth(320)
        outer.addLayout(search_row)

        row = QHBoxLayout()
        row.addStretch(1)
        self._grid = QGridLayout()
        self._grid.setSpacing(GRID_SPACING)
        self._tiles: list[_GameTile] = []
        self._visible_tiles: list[_GameTile] = list(self._tiles)
        self._grid_spacing = GRID_SPACING
        for index, profile in enumerate(GAMES):
            tile = _GameTile(profile)
            tile.clicked.connect(lambda idx=index: self._open_game(idx))
            self._grid.addWidget(tile, index // self.COLUMNS, index % self.COLUMNS)
            self._tiles.append(tile)
        self._visible_tiles = list(self._tiles)
        row.addLayout(self._grid)
        row.addStretch(1)
        outer.addLayout(row)
        self._empty_label = QLabel("Ничего не найдено — попробуйте другое название.")
        self._empty_label.setObjectName("PageHint")
        self._empty_label.setAlignment(Qt.AlignCenter)
        self._empty_label.setVisible(False)
        outer.addWidget(self._empty_label)
        outer.addStretch(1)
        self._stack.addWidget(grid_page)
        #: текущая ширина плитки — чтобы не пересобирать обложки на каждый пиксель
        self._tile_width = 0

        root.addWidget(self._stack, 1)

    # ------------------------------------------------------------------
    def _apply_filter(self, text: str) -> None:
        """Показывает только игры, в названии которых есть введённый текст."""
        query = text.strip().lower()
        self._visible_tiles = [
            tile for tile in self._tiles if not query or query in tile.profile.name.lower()
        ]
        for tile in self._tiles:
            if tile not in self._visible_tiles:
                tile.setVisible(False)
        while self._grid.count():
            self._grid.takeAt(0)
        for index, tile in enumerate(self._visible_tiles):
            tile.setVisible(True)
            self._grid.addWidget(tile, index // self.COLUMNS, index % self.COLUMNS)
        self._empty_label.setVisible(not self._visible_tiles)
        self._tile_width = 0
        self._relayout()

    # ------------------------------------------------------------------
    def resizeEvent(self, event) -> None:  # noqa: N802 - Qt API
        super().resizeEvent(event)
        self._relayout()

    def showEvent(self, event) -> None:  # noqa: N802 - Qt API
        super().showEvent(event)
        self._relayout()

    def _relayout(self) -> None:
        """Подбирает размер плиток так, чтобы они занимали доступное место."""
        if not self._visible_tiles:
            return
        margins = self.layout().contentsMargins()
        columns = self.COLUMNS
        rows = -(-len(self._visible_tiles) // columns)
        search_height = self.search.sizeHint().height() + self.layout().spacing()
        avail_w = self.width() - margins.left() - margins.right()
        avail_h = (
            self.height()
            - margins.top()
            - margins.bottom()
            - self._header.sizeHint().height()
            - self.layout().spacing()
            - search_height
            - 16  # небольшой запас, чтобы нижний ряд не упирался в край
        )
        # Ширину плитки ограничивают и ширина, и высота окна: нужно уместить
        # все колонки в ряд и все ряды по высоте.
        by_width = (avail_w - GRID_SPACING * (columns - 1)) / columns
        by_height = (avail_h - GRID_SPACING * (rows - 1)) / rows / TILE_RATIO
        width = int(max(TILE_MIN, min(TILE_MAX, by_width, by_height)))
        spacing = GRID_SPACING
        free = avail_w - width * columns
        if free > 0 and columns > 1:
            spacing = int(max(GRID_SPACING, min(GRID_SPACING_MAX, free / (columns - 1))))
        if abs(width - self._tile_width) < 2 and spacing == self._grid_spacing:
            return
        self._tile_width = width
        self._grid_spacing = spacing
        self._grid.setSpacing(spacing)
        for tile in self._visible_tiles:
            tile.set_size(width, int(width * TILE_RATIO))

    def _open_game(self, index: int) -> None:
        stack_index = self._panels.get(index)
        if stack_index is None:
            panel = _GamePanel(GAMES[index])
            panel.back_requested.connect(lambda: self._stack.setCurrentIndex(self._grid_index))
            stack_index = self._stack.addWidget(panel)
            self._panels[index] = stack_index
        self._stack.setCurrentIndex(stack_index)
