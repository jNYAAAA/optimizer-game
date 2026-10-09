"""Настройки и информация о приложении."""
from __future__ import annotations

from PySide6.QtWidgets import QHBoxLayout, QPushButton, QVBoxLayout, QWidget

from ...config import APP_DISPLAY_NAME, APP_VERSION, app_data_dir
from ...utils import open_path
from ..widgets import Card, make_header


class SettingsPage(QWidget):
    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        root = QVBoxLayout(self)
        root.setContentsMargins(24, 20, 24, 20)
        root.setSpacing(14)

        root.addWidget(
            make_header("Настройки", "Расположение данных и сведения о приложении.")
        )

        data_card = Card("Данные приложения")
        data_card.add_row("Папка", str(app_data_dir()))
        data_card.add_row(
            "Содержимое",
            "Настройки, резервные копии отключённой автозагрузки и изменённых твиков.",
        )
        buttons = QHBoxLayout()
        open_btn = QPushButton("ОТКРЫТЬ ПАПКУ ДАННЫХ")
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
