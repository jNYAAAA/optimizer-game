"""Настройки и информация о приложении."""
from __future__ import annotations

from PySide6.QtWidgets import QHBoxLayout, QLabel, QPushButton, QVBoxLayout, QWidget

from ...admin import admin_status_text, is_admin, relaunch_as_admin
from ...config import APP_DISPLAY_NAME, APP_VERSION, app_data_dir
from ...utils import open_path
from ..widgets import Card, make_header


class SettingsPage(QWidget):
    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        root = QVBoxLayout(self)
        root.setContentsMargins(24, 20, 24, 20)
        root.setSpacing(14)

        root.addWidget(make_header("Настройки", "Права доступа, расположение данных и сведения о приложении."))

        admin_card = Card("Права доступа")
        self.admin_label = QLabel(admin_status_text())
        self.admin_label.setObjectName("Value")
        self.admin_label.setWordWrap(True)
        admin_card.body.addWidget(self.admin_label, 0, 0, 1, 2)
        admin_buttons = QHBoxLayout()
        self.elevate_btn = QPushButton("Перезапустить от имени администратора")
        self.elevate_btn.setObjectName("Primary")
        self.elevate_btn.clicked.connect(relaunch_as_admin)
        self.elevate_btn.setEnabled(not is_admin())
        admin_buttons.addWidget(self.elevate_btn)
        admin_buttons.addStretch(1)
        admin_card.body.addLayout(admin_buttons, 1, 0, 1, 2)
        root.addWidget(admin_card)

        data_card = Card("Данные приложения")
        data_card.add_row("Папка", str(app_data_dir()))
        data_card.add_row(
            "Содержимое",
            "Настройки, резервные копии отключённой автозагрузки и изменённых твиков.",
        )
        buttons = QHBoxLayout()
        open_btn = QPushButton("Открыть папку данных")
        open_btn.clicked.connect(lambda: open_path(app_data_dir()))
        buttons.addWidget(open_btn)
        buttons.addStretch(1)
        data_card.body.addLayout(buttons, data_card.body.rowCount(), 0, 1, 2)
        root.addWidget(data_card)

        about_card = Card("О приложении")
        about_card.add_row("Название", APP_DISPLAY_NAME)
        about_card.add_row("Версия", APP_VERSION)
        about_card.add_row(
            "Назначение",
            "Просмотр характеристик ПК и аккуратная оптимизация Windows с "
            "возможностью отката изменений.",
        )
        root.addWidget(about_card)
        root.addStretch(1)
