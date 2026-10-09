"""Управление автозагрузкой.

Перечисляются записи из веток ``Run`` (пользователь, система, 32-битная ветка) и
из папок «Автозагрузка». Отключение удаляет запись, сохраняя её резервную копию
в ``%APPDATA%\\OptimizerGame``; включение восстанавливает запись.
"""
from __future__ import annotations

import os
import shutil
from dataclasses import dataclass, field
from typing import Any

from ..config import DISABLED_STARTUP_FILE, disabled_startup_dir, load_json, save_json
from . import registry

RUN_KEYS: list[tuple[str, str, str, str]] = [
    ("HKCU", r"Software\Microsoft\Windows\CurrentVersion\Run", "Пользователь (HKCU)", "user"),
    ("HKLM", r"SOFTWARE\Microsoft\Windows\CurrentVersion\Run", "Система (HKLM)", "machine"),
    ("HKLM", r"SOFTWARE\WOW6432Node\Microsoft\Windows\CurrentVersion\Run", "Система (32-бит)", "machine"),
]

APPROVED_KEYS: list[tuple[str, str]] = [
    ("HKCU", r"Software\Microsoft\Windows\CurrentVersion\Explorer\StartupApproved\Run"),
    ("HKLM", r"SOFTWARE\Microsoft\Windows\CurrentVersion\Explorer\StartupApproved\Run"),
]


@dataclass
class StartupItem:
    key: str
    name: str
    command: str
    source: str
    scope: str
    kind: str  # registry | folder
    enabled: bool = True
    windows_disabled: bool = False
    hive: str | None = None
    registry_path: str | None = None
    file_path: str | None = None
    data_type: str | None = None


# ---------------------------------------------------------------------------
# Хранилище отключённых записей
# ---------------------------------------------------------------------------
def _load_disabled() -> list[dict]:
    data = load_json(DISABLED_STARTUP_FILE, [])
    return data if isinstance(data, list) else []


def _save_disabled(items: list[dict]) -> None:
    save_json(DISABLED_STARTUP_FILE, items)


def _encode_value(value: Any) -> dict:
    if isinstance(value, bytes):
        return {"__bytes__": value.hex()}
    return {"value": value}


def _decode_value(encoded: dict) -> Any:
    if "__bytes__" in encoded:
        return bytes.fromhex(encoded["__bytes__"])
    return encoded.get("value")


def _disabled_entry_id(item: StartupItem) -> str:
    if item.kind == "registry":
        return f"reg|{item.hive}|{item.registry_path}|{item.name}"
    return f"file|{item.file_path}"


def _find_disabled(item: StartupItem) -> dict | None:
    target = _disabled_entry_id(item)
    for entry in _load_disabled():
        if entry.get("id") == target:
            return entry
    return None


# ---------------------------------------------------------------------------
# Перечисление
# ---------------------------------------------------------------------------
def _startup_folders() -> list[tuple[str, str]]:
    folders: list[tuple[str, str]] = []
    appdata = os.environ.get("APPDATA")
    programdata = os.environ.get("ProgramData")
    if appdata:
        folders.append((os.path.join(appdata, r"Microsoft\Windows\Start Menu\Programs\Startup"), "user"))
    if programdata:
        folders.append((os.path.join(programdata, r"Microsoft\Windows\Start Menu\Programs\Startup"), "machine"))
    return folders


def _windows_disabled(hive: str, name: str) -> bool:
    for approved_hive, approved_path in APPROVED_KEYS:
        if approved_hive != hive:
            continue
        exists, _vtype, value = registry.read_value(approved_hive, approved_path, name)
        if exists and isinstance(value, (bytes, bytearray)) and len(value) >= 1:
            return value[0] in (0x03, 0x07)
    return False


def list_startup_items() -> list[StartupItem]:
    items: list[StartupItem] = []
    for hive, path, label, scope in RUN_KEYS:
        for name, data_type, value in registry.list_values(hive, path):
            if not name:
                continue
            item = StartupItem(
                key=f"{hive}:{path}:{name}",
                name=name,
                command=str(value),
                source=label,
                scope=scope,
                kind="registry",
                hive=hive,
                registry_path=path,
                data_type=data_type,
            )
            item.enabled = _find_disabled(item) is None
            item.windows_disabled = _windows_disabled(hive, name)
            items.append(item)

    for folder, scope in _startup_folders():
        if not os.path.isdir(folder):
            continue
        for entry in sorted(os.listdir(folder)):
            full = os.path.join(folder, entry)
            if not os.path.isfile(full):
                continue
            item = StartupItem(
                key=f"folder:{full}",
                name=entry,
                command=full,
                source="Папка «Автозагрузка»" + (" (система)" if scope == "machine" else ""),
                scope=scope,
                kind="folder",
                file_path=full,
            )
            item.enabled = os.path.exists(full)
            items.append(item)

    # Дополняем список записями, отключёнными приложением (их уже нет в системе).
    run_labels = {(hive, path): (label, scope) for hive, path, label, scope in RUN_KEYS}
    for entry in _load_disabled():
        if entry.get("kind") == "registry":
            hive = entry.get("hive")
            path = entry.get("registry_path")
            label, scope = run_labels.get((hive, path), ("Автозагрузка", "user"))
            items.append(
                StartupItem(
                    key=entry.get("id", ""),
                    name=entry.get("name", ""),
                    command="",
                    source=f"{label} (отключено)",
                    scope=scope,
                    kind="registry",
                    hive=hive,
                    registry_path=path,
                    data_type=entry.get("data_type"),
                    enabled=False,
                )
            )
        elif entry.get("kind") == "file":
            original = entry.get("original_path")
            if not original:
                continue
            items.append(
                StartupItem(
                    key=entry.get("id", ""),
                    name=os.path.basename(original),
                    command=entry.get("stored_path", ""),
                    source="Папка «Автозагрузка» (отключено)",
                    scope="user",
                    kind="folder",
                    file_path=original,
                    enabled=False,
                )
            )

    items.sort(key=lambda i: (not i.enabled, i.name.lower()))
    return items

# ---------------------------------------------------------------------------
# Включение / отключение
# ---------------------------------------------------------------------------
def disable_item(item: StartupItem) -> tuple[bool, str]:
    if item.kind == "registry":
        exists, data_type, value = registry.read_value(item.hive, item.registry_path, item.name)
        if not exists:
            return False, "Запись не найдена"
        store = _load_disabled()
        entry_id = _disabled_entry_id(item)
        store = [entry for entry in store if entry.get("id") != entry_id]
        store.append(
            {
                "id": entry_id,
                "kind": "registry",
                "hive": item.hive,
                "registry_path": item.registry_path,
                "name": item.name,
                "data_type": data_type,
                "data": _encode_value(value),
            }
        )
        _save_disabled(store)
        registry.delete_value(item.hive, item.registry_path, item.name)
        return True, "Отключено"

    # Папка «Автозагрузка»
    if not item.file_path or not os.path.exists(item.file_path):
        return False, "Файл не найден"
    store = _load_disabled()
    entry_id = _disabled_entry_id(item)
    destination = disabled_startup_dir() / os.path.basename(item.file_path)
    candidate = destination
    counter = 1
    while candidate.exists():
        candidate = destination.with_name(f"{destination.stem}_{counter}{destination.suffix}")
        counter += 1
    try:
        shutil.move(item.file_path, candidate)
    except OSError as exc:
        return False, f"Не удалось переместить: {exc}"
    store = [entry for entry in store if entry.get("id") != entry_id]
    store.append(
        {
            "id": entry_id,
            "kind": "file",
            "original_path": item.file_path,
            "stored_path": str(candidate),
        }
    )
    _save_disabled(store)
    return True, "Отключено"


def enable_item(item: StartupItem) -> tuple[bool, str]:
    entry = _find_disabled(item)
    if entry is None:
        # Возможно, запись была отключена штатными средствами Windows.
        if item.windows_disabled:
            _clear_windows_disabled(item)
            return True, "Включено"
        return False, "Не найдено в резервных копиях"

    if entry.get("kind") == "registry":
        try:
            registry.write_value(
                entry["hive"],
                entry["registry_path"],
                entry["name"],
                entry["data_type"],
                _decode_value(entry["data"]),
            )
        except OSError as exc:
            return False, f"Ошибка записи в реестр: {exc}"
    else:
        stored = entry.get("stored_path")
        original = entry.get("original_path")
        if stored and original and os.path.exists(stored):
            os.makedirs(os.path.dirname(original), exist_ok=True)
            try:
                shutil.move(stored, original)
            except OSError as exc:
                return False, f"Не удалось вернуть файл: {exc}"

    store = [e for e in _load_disabled() if e.get("id") != entry.get("id")]
    _save_disabled(store)
    return True, "Включено"


def _clear_windows_disabled(item: StartupItem) -> None:
    if item.kind != "registry":
        return
    for approved_hive, approved_path in APPROVED_KEYS:
        if approved_hive == item.hive:
            registry.delete_value(approved_hive, approved_path, item.name)


def set_enabled(item: StartupItem, enabled: bool) -> tuple[bool, str]:
    if enabled:
        return enable_item(item)
    return disable_item(item)


def restore_all() -> int:
    """Включает все ранее отключённые приложением записи."""
    restored = 0
    for entry in _load_disabled():
        item = StartupItem(
            key=entry.get("id", ""),
            name=entry.get("name", ""),
            command="",
            source="",
            scope="",
            kind=entry.get("kind", "registry"),
            hive=entry.get("hive"),
            registry_path=entry.get("registry_path"),
            file_path=entry.get("original_path"),
        )
        ok, _message = enable_item(item)
        if ok:
            restored += 1
    return restored
