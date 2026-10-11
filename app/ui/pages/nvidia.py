"""Настройки NVIDIA для игры: выбор значений NVIDIA и быстрый переход.

Параметры драйвера хранятся в профиле NVAPI, поэтому приложение показывает
рекомендованные значения с выбором вариантов и копирует готовый список для
быстрой настройки в NVIDIA App.
"""
from __future__ import annotations

import os

from PySide6.QtCore import Qt
from PySide6.QtGui import QGuiApplication
from PySide6.QtWidgets import (
    QHBoxLayout,
    QLabel,
    QPushButton,
    QVBoxLayout,
    QWidget,
)

from ...core import nvidia_drs
from ...core.nvidia import (
    PRESETS,
    PRESETS_BY_KEY,
    apply_to_driver,
    format_profile,
    load_saved,
    profile_for,
    save_profile,
)
from ...core.workers import Worker, start_worker
from ...core.win_settings import cs2_exe_path
from ...utils import open_path
from ..widgets import Card, LogView, OptionRow, make_header

_NVIDIA_APP_PATHS = [
    r"C:\Program Files\NVIDIA Corporation\NVIDIA App\NVIDIA App.exe",
    r"C:\Program Files\NVIDIA Corporation\NVIDIA App\CEF\NVIDIA App.exe",
]
_NVIDIA_CP_PATHS = [
    r"C:\Program Files\NVIDIA Corporation\Control Panel Client\nvcplui.exe",
    r"C:\Windows\System32\nvcplui.exe",
]


def _open_first(paths: list[str]) -> bool:
    for path in paths:
        if path and os.path.exists(path):
            try:
                os.startfile(path)  # type: ignore[attr-defined]
                return True
            except OSError:
                continue
    return False


class NvidiaPage(QWidget):
    def __init__(
        self,
        game_key: str = "cs2",
        parent: QWidget | None = None,
        show_header: bool = True,
    ) -> None:
        super().__init__(parent)
        self.game_key = game_key
        self.settings = profile_for(game_key)

        root = QVBoxLayout(self)
        root.setSpacing(14)
        if show_header:
            root.setContentsMargins(24, 20, 24, 20)
            root.addWidget(
                make_header(
                    "Настройки NVIDIA",
                    "Рекомендованные параметры драйвера для этой игры. Кнопка "
                    "«Применить выбранное» записывает значения прямо в профиль драйвера "
                    "NVIDIA для .exe игры. Чтобы увидеть изменения в панели управления "
                    "NVIDIA, закройте и снова откройте её.",
                )
            )
        else:
            root.setContentsMargins(0, 0, 0, 0)

        preset_row = QHBoxLayout()
        preset_row.setSpacing(8)
        preset_label = QLabel("Профиль:")
        preset_label.setObjectName("Caption")
        preset_row.addWidget(preset_label)
        self._preset_buttons: list[QPushButton] = []
        for key, label, _values in PRESETS:
            button = QPushButton(label)
            button.setObjectName("Segment")
            button.setCheckable(True)
            button.setCursor(Qt.PointingHandCursor)
            button.clicked.connect(lambda _checked=False, k=key: self._apply_preset(k))
            preset_row.addWidget(button)
            self._preset_buttons.append(button)
        preset_row.addStretch(1)
        root.addLayout(preset_row)

        card = Card("Параметры драйвера NVIDIA")
        self._rows: list[tuple[object, OptionRow]] = []
        for setting in self.settings:
            row = OptionRow(setting.name, setting.help, setting.options, setting.value, show_apply=False)
            card.body.addWidget(row, card.body.rowCount(), 0, 1, 2)
            self._rows.append((setting, row))
        root.addWidget(card)

        controls = QHBoxLayout()
        self.apply_btn = QPushButton("ПРИМЕНИТЬ ВЫБРАННОЕ")
        self.apply_btn.setObjectName("Primary")
        self.apply_btn.clicked.connect(self._apply)
        controls.addWidget(self.apply_btn)
        copy_btn = QPushButton("СКОПИРОВАТЬ СПИСОК")
        copy_btn.clicked.connect(self._copy)
        controls.addWidget(copy_btn)
        app_btn = QPushButton("ОТКРЫТЬ NVIDIA APP")
        app_btn.clicked.connect(self._open_app)
        controls.addWidget(app_btn)
        cp_btn = QPushButton("ПАНЕЛЬ УПРАВЛЕНИЯ NVIDIA")
        cp_btn.clicked.connect(self._open_cp)
        controls.addWidget(cp_btn)
        if game_key == "cs2":
            cs2_btn = QPushButton("ОТКРЫТЬ ПАПКУ CS2")
            cs2_btn.clicked.connect(self._open_cs2)
            controls.addWidget(cs2_btn)
        controls.addStretch(1)
        root.addLayout(controls)

        self.log = LogView()
        self.log.setMaximumHeight(90)
        root.addWidget(self.log)
        root.addStretch(1)

        self._loaded = False

    # ------------------------------------------------------------------
    def showEvent(self, event) -> None:  # noqa: N802 - Qt API
        super().showEvent(event)
        if self._loaded:
            return
        self._loaded = True
        saved = load_saved(self.game_key)
        if saved:
            for setting, row in self._rows:
                if setting.key in saved:
                    row.set_value(saved[setting.key])
            self.log.log("Загружен сохранённый профиль NVIDIA для этой игры.")

    def _apply_preset(self, key: str) -> None:
        values = PRESETS_BY_KEY.get(key, {})
        for setting, row in self._rows:
            if setting.key in values:
                row.set_value(values[setting.key])
        for button, (preset_key, _label, _values) in zip(self._preset_buttons, PRESETS):
            button.setChecked(preset_key == key)
        label = next((l for k, l, _v in PRESETS if k == key), key)
        self.log.log(f"Выбран профиль «{label}».")

    def _apply(self) -> None:
        values = self._values()
        save_profile(self.game_key, values)
        self.apply_btn.setEnabled(False)
        self.log.log("Применение настроек в профиль драйвера NVIDIA…")
        worker = Worker(apply_to_driver, self.game_key, values)
        worker.signals.finished.connect(self._on_applied)
        worker.signals.failed.connect(self._on_apply_failed)
        start_worker(worker)

    def _on_applied(self, result: tuple[bool, str]) -> None:
        self.apply_btn.setEnabled(True)
        ok, message = result
        self.log.log(message)
        if ok:
            self.log.log(
                "Готово. Чтобы увидеть значения в панели управления NVIDIA, "
                "закройте и снова откройте её."
            )
        else:
            self.log.log("Часть настроек применить не удалось.")
            if not nvidia_drs.available():
                self.log.log(
                    "NVAPI недоступен: нужна видеокарта NVIDIA с установленным драйвером."
                )

    def _on_apply_failed(self, message: str) -> None:
        self.apply_btn.setEnabled(True)
        self.log.log(f"Не удалось применить настройки NVIDIA: {message}")

    def _values(self) -> dict:
        return {setting.key: row.value() for setting, row in self._rows}

    def _copy(self) -> None:
        text = format_profile(self.settings, self._values())
        QGuiApplication.clipboard().setText(text)
        self.log.log("Список значений скопирован в буфер обмена — вставьте в NVIDIA App.")

    def _open_app(self) -> None:
        if not _open_first(_NVIDIA_APP_PATHS):
            os.startfile("ms-windows-store://search/?query=NVIDIA%20App")  # type: ignore[attr-defined]
            self.log.log("NVIDIA App не найден — открыт поиск в Microsoft Store.")
        else:
            self.log.log("Открыт NVIDIA App.")

    def _open_cp(self) -> None:
        if not _open_first(_NVIDIA_CP_PATHS):
            os.startfile("ms-settings:display-advancedgraphics")  # type: ignore[attr-defined]
            self.log.log("Панель управления NVIDIA не найдена — открыты параметры графики Windows.")
        else:
            self.log.log("Открыта панель управления NVIDIA.")

    def _open_cs2(self) -> None:
        exe = cs2_exe_path()
        if exe:
            open_path(os.path.dirname(exe))
            self.log.log(f"Открыта папка CS2: {os.path.dirname(exe)}")
        else:
            self.log.log("cs2.exe не найден (игра не установлена?).")
