"""Настройки NVIDIA для игры: выбор значений NVIDIA и быстрый переход.

Параметры драйвера хранятся в профиле NVAPI, поэтому приложение показывает
рекомендованные значения с выбором вариантов и копирует готовый список для
быстрой настройки в NVIDIA App.
"""
from __future__ import annotations

import os

from PySide6.QtGui import QGuiApplication
from PySide6.QtWidgets import (
    QHBoxLayout,
    QLabel,
    QPushButton,
    QVBoxLayout,
    QWidget,
)

from ...core.nvidia import format_profile, profile_for
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
                    "Рекомендованные параметры драйвера для этой игры. Задаются в NVIDIA App / "
                    "панели управления NVIDIA (программные настройки для .exe игры).",
                )
            )
        else:
            root.setContentsMargins(0, 0, 0, 0)

        self.help_label = QLabel("Наведите на значок (i), чтобы узнать, что делает параметр.")
        self.help_label.setObjectName("PageHint")
        self.help_label.setWordWrap(True)
        root.addWidget(self.help_label)

        card = Card("Параметры драйвера NVIDIA")
        self._rows: list[tuple[object, OptionRow]] = []
        for setting in self.settings:
            row = OptionRow(setting.name, setting.help, setting.options, setting.value, show_apply=False)
            row.help_hovered.connect(self._on_help)
            card.body.addWidget(row, card.body.rowCount(), 0, 1, 2)
            self._rows.append((setting, row))
        root.addWidget(card)

        controls = QHBoxLayout()
        copy_btn = QPushButton("СКОПИРОВАТЬ СПИСОК")
        copy_btn.setObjectName("Primary")
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

    # ------------------------------------------------------------------
    def _on_help(self, text: str) -> None:
        self.help_label.setText(
            text or "Наведите на значок (i), чтобы узнать, что делает параметр."
        )

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
