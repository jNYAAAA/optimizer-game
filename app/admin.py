"""Проверка и получение прав администратора."""
from __future__ import annotations

import ctypes
import os
import subprocess
import sys


def is_admin() -> bool:
    """True, если процесс запущен с повышенными правами."""
    try:
        return bool(ctypes.windll.shell32.IsUserAnAdmin())
    except Exception:  # noqa: BLE001
        return False


def relaunch_as_admin(extra_args: list[str] | None = None) -> bool:
    """Перезапускает приложение с запросом UAC.

    Возвращает True, если новая (админская) копия была запущена.
    """
    if is_admin():
        return False

    argv = list(sys.argv)
    if getattr(sys, "frozen", False):
        executable = sys.executable
        params = subprocess.list2cmdline(argv[1:])
        workdir = os.path.dirname(executable) or None
    else:
        script = os.path.abspath(argv[0]) if argv else ""
        executable = sys.executable
        params = subprocess.list2cmdline([script, *argv[1:]])
        workdir = os.path.dirname(script) or None

    if extra_args:
        params = (params + " " + subprocess.list2cmdline(extra_args)).strip()

    try:
        result = ctypes.windll.shell32.ShellExecuteW(
            None, "runas", executable, params, workdir, 1
        )
    except Exception:  # noqa: BLE001
        return False
    return result > 32


def auto_elevate() -> bool:
    """Запускает админскую копию, если прав нет.

    Возвращает True, если текущий процесс нужно завершить (запущена копия с
    правами администратора). Если пользователь отклонил запрос UAC — False.
    """
    if is_admin():
        return False
    return relaunch_as_admin()
