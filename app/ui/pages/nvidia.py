"""Настройки NVIDIA: список рекомендованных параметров и быстрый переход.

Параметры драйвера NVIDIA хранятся в его профиле (NVAPI), а не в конфиге игры.
Приложение показывает рекомендованные значения и открывает нужные утилиты.
"""
from __future__ import annotations

import os

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QHBoxLayout,
    QLabel,
    QPushButton,
    QVBoxLayout,
    QWidget,
)

from ...core.win_settings import cs2_exe_path
from ...utils import open_path
from ..widgets import Card, InfoIcon, LogView, make_header

# (название, рекомендуемое значение, пояснение)
NVIDIA_SETTINGS: list[tuple[str, str, str]] = [
    ("Image Scaling", "Off", "Апскейл изображения на уровне драйвера. Лучше выключить и использовать FSR/DLSS в игре."),
    ("Low Latency Mode", "Ultra", "Снижает задержку ввода. В игре NVIDIA Reflex приоритетнее."),
    ("Power management mode", "Prefer maximum performance", "Не даёт GPU сбрасывать частоты в игре."),
    ("Texture filtering — Quality", "High performance", "Чуть менее качественная фильтрация ради FPS."),
    ("Texture filtering — Negative LOD bias", "Allow", "Разрешает отрицательный LOD bias (резкость текстур)."),
    ("Texture filtering — Anisotropic sample optimization", "On", "Ускоряет анизотропную фильтрацию."),
    ("Texture filtering — Trilinear optimization", "On", "Ускоряет трилинейную фильтрацию."),
    ("Threaded optimization", "On", "Многопоточная обработка драйвера."),
    ("Vertical sync", "Off", "VSync добавляет задержку; выключить."),
    ("Preferred refresh rate", "Highest available", "Всегда берёт максимальную частоту монитора."),
    ("Shader Cache Size", "10 GB (или Unlimited)", "Большой кэш шейдеров уменьшает подгрузки."),
    ("Monitor Technology", "Fixed refresh (при G-Sync — G-Sync)", "Режим синхронизации монитора."),
    ("Max Frame Rate", "Off (или ~237 для 240 Гц)", "Ограничение FPS; чуть ниже герцовки снижает задержку."),
    ("Background Application Max Frame Rate", "Off", "Ограничение FPS фоновых приложений."),
    ("Vulkan/OpenGL present method", "Prefer layered on DXGI Swapchain", "Метод вывода Vulkan/OpenGL."),
]

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
    def __init__(self, parent: QWidget | None = None, show_header: bool = True) -> None:
        super().__init__(parent)
        root = QVBoxLayout(self)
        root.setSpacing(14)
        if show_header:
            root.setContentsMargins(24, 20, 24, 20)
            root.addWidget(
                make_header(
                    "Настройки NVIDIA",
                    "Рекомендованные параметры для Counter-Strike 2. Задаются в NVIDIA App / "
                    "панели управления NVIDIA для cs2.exe (программные настройки).",
                )
            )
        else:
            root.setContentsMargins(0, 0, 0, 0)

        self.help_label = QLabel(
            "Наведите на значок (i), чтобы узнать, что делает параметр."
        )
        self.help_label.setObjectName("PageHint")
        self.help_label.setWordWrap(True)
        root.addWidget(self.help_label)

        card = Card("Параметры драйвера для cs2.exe")
        for name, value, help_text in NVIDIA_SETTINGS:
            row = QWidget()
            layout = QHBoxLayout(row)
            layout.setContentsMargins(0, 3, 0, 3)
            layout.setSpacing(8)
            info = InfoIcon(help_text)
            info.hovered.connect(self._on_help)
            layout.addWidget(info)
            caption = QLabel(name)
            caption.setObjectName("Caption")
            caption.setWordWrap(True)
            layout.addWidget(caption, 1)
            value_label = QLabel(value)
            value_label.setObjectName("Value")
            value_label.setWordWrap(True)
            value_label.setMinimumWidth(240)
            layout.addWidget(value_label)
            card.body.addWidget(row, card.body.rowCount(), 0, 1, 2)
        root.addWidget(card)

        controls = QHBoxLayout()
        app_btn = QPushButton("ОТКРЫТЬ NVIDIA APP")
        app_btn.setObjectName("Primary")
        app_btn.clicked.connect(self._open_app)
        controls.addWidget(app_btn)
        cp_btn = QPushButton("ПАНЕЛЬ УПРАВЛЕНИЯ NVIDIA")
        cp_btn.clicked.connect(self._open_cp)
        controls.addWidget(cp_btn)
        cs2_btn = QPushButton("ОТКРЫТЬ ПАПКУ CS2")
        cs2_btn.clicked.connect(self._open_cs2)
        controls.addWidget(cs2_btn)
        controls.addStretch(1)
        root.addLayout(controls)

        self.log = LogView()
        self.log.setMaximumHeight(90)
        root.addWidget(self.log)
        root.addStretch(1)

    def _on_help(self, text: str) -> None:
        self.help_label.setText(
            text or "Наведите на значок (i), чтобы узнать, что делает параметр."
        )

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
