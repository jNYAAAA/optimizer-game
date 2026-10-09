"""Проверка и получение прав администратора."""
from __future__ import annotations

import ctypes
import subprocess
import sys

from .config import APP_DISPLAY_NAME


def is_admin() -> bool:
    """True, если процесс запущен с повышенными правами."""
    try:
        return bool(ctypes.windll.shell32.IsUserAnAdmin())
    except Exception:  # noqa: BLE001
        return False


def relaunch_as_admin(extra_args: list[str] | None = None) -> bool:
    """Перезапускает приложение с запросом UAC. Возвращает True при запуске."""
    if is_admin():
        return False

    argv = list(sys.argv)
    if getattr(sys, "frozen", False):
        executable = sys.executable
        params = subprocess.list2cmdline(argv[1:])
    else:
        executable = sys.executable
        params = subprocess.list2cmdline(argv)

    if extra_args:
        params = (params + " " + subprocess.list2cmdline(extra_args)).strip()

    try:
        result = ctypes.windll.shell32.ShellExecuteW(
            None, "runas", executable, params, None, 1
        )
    except Exception:  # noqa: BLE001
        return False
    return result > 32


def admin_status_text() -> str:
    if is_admin():
        return "Права администратора: да"
    return "Права администратора: нет — часть функций недоступна"
