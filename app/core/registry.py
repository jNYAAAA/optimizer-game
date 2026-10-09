"""Обёртка над ``winreg``: чтение, запись и удаление значений реестра."""
from __future__ import annotations

import winreg
from typing import Any

HIVES: dict[str, Any] = {
    "HKCU": winreg.HKEY_CURRENT_USER,
    "HKLM": winreg.HKEY_LOCAL_MACHINE,
    "HKCR": winreg.HKEY_CLASSES_ROOT,
    "HKU": winreg.HKEY_USERS,
}

VALUE_TYPES: dict[str, int] = {
    "REG_SZ": winreg.REG_SZ,
    "REG_EXPAND_SZ": winreg.REG_EXPAND_SZ,
    "REG_DWORD": winreg.REG_DWORD,
    "REG_QWORD": winreg.REG_QWORD,
    "REG_BINARY": winreg.REG_BINARY,
    "REG_MULTI_SZ": winreg.REG_MULTI_SZ,
}

TYPE_NAMES: dict[int, str] = {value: key for key, value in VALUE_TYPES.items()}


def read_value(hive: str, path: str, name: str) -> tuple[bool, str | None, Any]:
    """Возвращает ``(существует, тип, значение)``."""
    try:
        with winreg.OpenKey(HIVES[hive], path, 0, winreg.KEY_READ) as key:
            try:
                value, value_type = winreg.QueryValueEx(key, name)
            except FileNotFoundError:
                return False, None, None
            return True, TYPE_NAMES.get(value_type, str(value_type)), value
    except FileNotFoundError:
        return False, None, None


def write_value(hive: str, path: str, name: str, type_name: str, value: Any) -> None:
    """Создаёт (при необходимости) ключ и записывает значение."""
    with winreg.CreateKeyEx(HIVES[hive], path, 0, winreg.KEY_SET_VALUE) as key:
        winreg.SetValueEx(key, name, 0, VALUE_TYPES[type_name], value)


def delete_value(hive: str, path: str, name: str) -> bool:
    """Удаляет значение. Возвращает ``True``, если оно было удалено."""
    try:
        key = winreg.OpenKey(HIVES[hive], path, 0, winreg.KEY_SET_VALUE)
    except FileNotFoundError:
        return False
    try:
        try:
            winreg.DeleteValue(key, name)
            return True
        except FileNotFoundError:
            return False
    finally:
        winreg.CloseKey(key)


def list_values(hive: str, path: str) -> list[tuple[str, str, Any]]:
    """Перечисляет значения ключа как ``[(имя, тип, значение), ...]``."""
    result: list[tuple[str, str, Any]] = []
    try:
        with winreg.OpenKey(HIVES[hive], path, 0, winreg.KEY_READ) as key:
            index = 0
            while True:
                try:
                    name, value, value_type = winreg.EnumValue(key, index)
                except OSError:
                    break
                result.append((name, TYPE_NAMES.get(value_type, str(value_type)), value))
                index += 1
    except FileNotFoundError:
        pass
    return result


def list_subkeys(hive: str, path: str) -> list[str]:
    """Перечисляет имена дочерних ключей."""
    result: list[str] = []
    try:
        with winreg.OpenKey(HIVES[hive], path, 0, winreg.KEY_READ) as key:
            index = 0
            while True:
                try:
                    result.append(winreg.EnumKey(key, index))
                except OSError:
                    break
                index += 1
    except FileNotFoundError:
        pass
    return result
