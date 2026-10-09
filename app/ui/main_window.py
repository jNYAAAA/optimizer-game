"""Главное окно приложения."""
from __future__ import annotations

import math
import os
import sys

from PySide6.QtCore import QTimer
from PySide6.QtGui import QIcon
from PySide6.QtWidgets import (
    QApplication,
    QHBoxLayout,
    QLabel,
    QListWidget,
    QListWidgetItem,
    QMainWindow,
    QStackedWidget,
    QStatusBar,
    QVBoxLayout,
    QWidget,
)

from ..admin import admin_status_text
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
from .pages.optimize import OptimizePage
from .pages.settings import SettingsPage
from .pages.tweaks import TweaksPage
from .splash import SplashScreen
from .widgets import ThemeToggleButton


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
        side_layout.addWidget(self.nav, 1)
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

        self.pages: list[tuple[str, QWidget]] = [
            ("Характеристики", DashboardPage()),
            ("Оптимизация", OptimizePage()),
            ("Твики", TweaksPage()),
            ("Настройки", SettingsPage()),
        ]
        for name, page in self.pages:
            self.nav.addItem(QListWidgetItem(name))
            self.stack.addWidget(page)

        self.nav.currentRowChanged.connect(self.stack.setCurrentIndex)
        self.nav.setCurrentRow(0)

        status = QStatusBar()
        status.showMessage(admin_status_text())
        self.setStatusBar(status)

        self._update_theme_button()

    # ------------------------------------------------------------------
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
