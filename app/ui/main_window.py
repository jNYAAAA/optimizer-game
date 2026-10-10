"""Главное окно приложения."""
from __future__ import annotations

import math
import os
import sys

from PySide6.QtCore import QSize, Qt, QTimer
from PySide6.QtGui import QIcon
from PySide6.QtWidgets import (
    QApplication,
    QHBoxLayout,
    QLabel,
    QListWidget,
    QListWidgetItem,
    QMainWindow,
    QStackedWidget,
    QVBoxLayout,
    QWidget,
)

from ..config import (
    APP_DISPLAY_NAME,
    APP_NAME,
    APP_VERSION,
    load_settings,
    save_settings,
)
from ..utils import resource_path
from . import theme
from .pages.dashboard import DashboardPage
from .pages.drivers import DriversPage
from .pages.games import GamesPage
from .pages.nvidia import NvidiaPage
from .pages.optimize import OptimizePage
from .pages.settings import SettingsPage
from .pages.tweaks import TweaksPage
from .pages.win_settings import WinSettingsPage
from .splash import SplashScreen
from .widgets import ThemeToggleButton, nav_icon, scrollable


class MainWindow(QMainWindow):
    def __init__(self) -> None:
        super().__init__()
        self.setWindowTitle(f"{APP_DISPLAY_NAME} {APP_VERSION}")
        self.resize(1200, 800)

        root = QWidget()
        root.setObjectName("Root")
        self.setCentralWidget(root)
        layout = QHBoxLayout(root)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)

        # Боковая панель
        sidebar = QWidget()
        sidebar.setObjectName("Sidebar")
        sidebar.setFixedWidth(240)
        side_layout = QVBoxLayout(sidebar)
        side_layout.setContentsMargins(0, 0, 0, 0)
        side_layout.setSpacing(0)

        title = QLabel(APP_DISPLAY_NAME.upper())
        title.setObjectName("AppTitle")
        side_layout.addWidget(title)

        self.nav = QListWidget()
        self.nav.setObjectName("Nav")
        self.nav.setIconSize(QSize(22, 22))
        side_layout.addWidget(self.nav, 1)

        footer = QLabel(f"версия {APP_VERSION}")
        footer.setObjectName("SidebarFooter")
        footer.setAlignment(Qt.AlignCenter)
        side_layout.addWidget(footer)
        layout.addWidget(sidebar)

        # Область содержимого: верхняя панель с переключателем темы + страницы
        content = QWidget()
        content_layout = QVBoxLayout(content)
        content_layout.setContentsMargins(0, 0, 0, 0)
        content_layout.setSpacing(0)

        top_bar = QWidget()
        top_bar.setObjectName("TopBar")
        top_layout = QHBoxLayout(top_bar)
        top_layout.setContentsMargins(24, 12, 24, 0)
        top_layout.setSpacing(0)
        top_layout.addStretch(1)
        self.theme_btn = ThemeToggleButton()
        self.theme_btn.clicked.connect(self.toggle_theme)
        top_layout.addWidget(self.theme_btn)
        content_layout.addWidget(top_bar)

        self.stack = QStackedWidget()
        content_layout.addWidget(self.stack, 1)
        layout.addWidget(content, 1)

        definitions: list[tuple[str, QWidget, bool]] = [
            ("Характеристики", DashboardPage(), True),
            ("Драйверы", DriversPage(), True),
            ("Оптимизация", OptimizePage(), False),
            ("Игры", GamesPage(), True),
            ("NVIDIA", NvidiaPage(), True),
            ("Windows", WinSettingsPage(), True),
            ("Твики", TweaksPage(), False),
            ("Настройки", SettingsPage(), True),
        ]
        self._nav_kinds = ["info", "driver", "speed", "games", "nvidia", "windows", "tweaks", "settings"]
        self.pages: list[tuple[str, QWidget]] = []
        for name, page, use_scroll in definitions:
            container = scrollable(page) if use_scroll else page
            self.nav.addItem(QListWidgetItem(name))
            self.stack.addWidget(container)
            self.pages.append((name, page))

        self.nav.currentRowChanged.connect(self.stack.setCurrentIndex)
        self.nav.currentRowChanged.connect(self._update_nav_icons)
        self.nav.setCurrentRow(0)

        self._update_theme_button()
        self._update_nav_icons()

    # ------------------------------------------------------------------
    def _update_nav_icons(self) -> None:
        current = self.nav.currentRow()
        palette = theme.palette()
        for index in range(self.nav.count()):
            item = self.nav.item(index)
            kind = self._nav_kinds[index] if index < len(self._nav_kinds) else "info"
            color = palette["ACCENT"] if index == current else palette["TEXT_DIM"]
            item.setIcon(nav_icon(kind, color))

    def _update_theme_button(self) -> None:
        if theme.current() == "dark":
            self.theme_btn.setToolTip("Включить светлую тему")
        else:
            self.theme_btn.setToolTip("Включить тёмную тему")
        self.theme_btn.update()

    def toggle_theme(self) -> None:
        new_mode = "light" if theme.current() == "dark" else "dark"
        theme.set_current(new_mode)
        app = QApplication.instance()
        if app is not None:
            app.setStyleSheet(theme.styles())
        self._update_theme_button()
        for _name, page in self.pages:
            hook = getattr(page, "on_theme_changed", None)
            if callable(hook):
                hook()
        self._update_nav_icons()
        settings = load_settings()
        settings["theme"] = new_mode
        save_settings(settings)


def _splash_message(value: float) -> str:
    if value < 30:
        return "Инициализация…"
    if value < 60:
        return "Чтение настроек…"
    if value < 90:
        return "Подготовка интерфейса…"
    return "Почти готово…"


def run() -> int:
    app = QApplication.instance() or QApplication(sys.argv)
    app.setApplicationName(APP_NAME)
    app.setApplicationDisplayName(APP_DISPLAY_NAME)
    app.setStyle("Fusion")

    icon_path = resource_path(os.path.join("assets", "icon.ico"))
    if os.path.exists(icon_path):
        app.setWindowIcon(QIcon(icon_path))

    theme.set_current(str(load_settings().get("theme", "dark")))
    app.setStyleSheet(theme.styles())

    splash = SplashScreen()
    splash.show()
    app.processEvents()

    state = {"value": 0.0, "phase": 0.0}
    tick = QTimer()
    tick.setInterval(30)

    def on_tick() -> None:
        state["value"] = min(state["value"] + 2.4, 100.0)
        state["phase"] = (state["phase"] + 0.09) % (2 * math.pi)
        splash.update_progress(state["value"], state["phase"], _splash_message(state["value"]))

    tick.timeout.connect(on_tick)
    tick.start()

    def finish() -> None:
        tick.stop()
        splash.update_progress(100.0, state["phase"], "Готово")
        window = MainWindow()
        app.main_window = window  # type: ignore[attr-defined] - держим ссылку живой
        window.show()
        splash.finish(window)

    QTimer.singleShot(1500, finish)
    return app.exec()
