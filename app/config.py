"""Константы приложения и работа с файлами настроек.

Все пользовательские данные (настройки, резервные копии твиков и отключённой
автозагрузки) хранятся в ``%APPDATA%\\OptimizerGame``.
"""
from __future__ import annotations

import json
import os
from pathlib import Path
from typing import Any

APP_NAME = "OptimizerGame"
APP_DISPLAY_NAME = "Optimizer Game"
APP_VERSION = "0.1.0"

# Имена файлов хранилища внутри папки данных приложения.
SETTINGS_FILE = "settings.json"
DISABLED_STARTUP_FILE = "disabled_startup.json"
TWEAK_BACKUP_FILE = "tweak_backup.json"


def app_data_dir() -> Path:
    """Возвращает (создавая при необходимости) папку данных приложения."""
    base = os.environ.get("APPDATA")
    root = Path(base) if base else Path.home() / "AppData" / "Roaming"
    path = root / APP_NAME
    path.mkdir(parents=True, exist_ok=True)
    return path


def disabled_startup_dir() -> Path:
    """Папка, куда перемещаются отключённые элементы автозагрузки."""
    path = app_data_dir() / "disabled_startup"
    path.mkdir(parents=True, exist_ok=True)
    return path


def load_json(name: str, default: Any) -> Any:
    """Читает JSON-файл из папки данных, возвращая ``default`` при ошибке."""
    path = app_data_dir() / name
    try:
        with path.open("r", encoding="utf-8") as handle:
            return json.load(handle)
    except (OSError, ValueError):
        return default


def save_json(name: str, data: Any) -> None:
    """Атомарно сохраняет ``data`` в JSON-файл внутри папки данных."""
    path = app_data_dir() / name
    tmp = path.with_suffix(path.suffix + ".tmp")
    with tmp.open("w", encoding="utf-8") as handle:
        json.dump(data, handle, ensure_ascii=False, indent=2)
    os.replace(tmp, path)


def load_settings() -> dict:
    return load_json(SETTINGS_FILE, {})


def save_settings(settings: dict) -> None:
    save_json(SETTINGS_FILE, settings)
