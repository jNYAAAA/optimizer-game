"""Системные утилиты: запуск команд, форматирование, PowerShell."""
from __future__ import annotations

import base64
import json
import os
import subprocess
import sys
from typing import Any, Sequence

CREATE_NO_WINDOW = 0x08000000
_POWERSHELL_PREFIX = (
    "$ProgressPreference='SilentlyContinue';"
    "[Console]::OutputEncoding=[System.Text.Encoding]::UTF8;"
)


def is_windows() -> bool:
    return os.name == "nt"


def format_bytes(num: float | int | None) -> str:
    """Человекочитаемый размер (русские единицы)."""
    if num is None:
        return "—"
    value = float(num)
    units = ("Б", "КБ", "МБ", "ГБ", "ТБ", "ПБ")
    index = 0
    while abs(value) >= 1024.0 and index < len(units) - 1:
        value /= 1024.0
        index += 1
    if index == 0:
        return f"{int(value)} {units[index]}"
    return f"{value:.2f} {units[index]}"


def format_count(num: int | None) -> str:
    if num is None:
        return "—"
    return f"{num:,}".replace(",", " ")


def format_mhz(mhz: float | int | None) -> str:
    if not mhz:
        return "—"
    return f"{int(mhz)} МГц"


def run_hidden(
    args: Sequence[str],
    timeout: int | None = 60,
    encoding: str = "utf-8",
) -> subprocess.CompletedProcess:
    """Запускает процесс без окна консоли."""
    creationflags = CREATE_NO_WINDOW if is_windows() else 0
    return subprocess.run(
        list(args),
        capture_output=True,
        text=True,
        timeout=timeout,
        creationflags=creationflags,
        encoding=encoding,
        errors="replace",
    )


def run_command(command: str, timeout: int = 300) -> tuple[int, str]:
    """Запускает команду через оболочку, возвращает (код, вывод)."""
    creationflags = CREATE_NO_WINDOW if is_windows() else 0
    proc = subprocess.run(
        command,
        shell=True,
        capture_output=True,
        text=True,
        timeout=timeout,
        creationflags=creationflags,
        encoding="utf-8",
        errors="replace",
    )
    output = (proc.stdout or "") + (proc.stderr or "")
    return proc.returncode, output.strip()


def run_powershell(script: str, timeout: int = 120) -> subprocess.CompletedProcess:
    """Выполняет PowerShell-скрипт, передавая его в кодировке Base64.

    ``-EncodedCommand`` избавляет от проблем с кавычками и переводами строк.
    """
    if not is_windows():
        raise RuntimeError("PowerShell доступен только в Windows")
    encoded = base64.b64encode(
        (_POWERSHELL_PREFIX + script).encode("utf-16-le")
    ).decode("ascii")
    args = [
        "powershell.exe",
        "-NoProfile",
        "-NonInteractive",
        "-ExecutionPolicy",
        "Bypass",
        "-EncodedCommand",
        encoded,
    ]
    return run_hidden(args, timeout=timeout)


def powershell_json(script: str, timeout: int = 120) -> Any:
    """Выполняет PowerShell-скрипт и разбирает его вывод как JSON."""
    proc = run_powershell(script, timeout=timeout)
    text = (proc.stdout or "").strip().lstrip("\ufeff")
    if not text:
        message = (proc.stderr or "").strip()
        if proc.returncode != 0 or message:
            raise RuntimeError(message or f"PowerShell завершился с кодом {proc.returncode}")
        return None
    try:
        return json.loads(text)
    except ValueError as exc:  # покажем начало вывода для диагностики
        snippet = text[:400]
        raise RuntimeError(f"Не удалось разобрать JSON от PowerShell: {exc}\n{snippet}") from exc


def as_list(value: Any) -> list:
    """PowerShell схлопывает одноэлементные массивы — нормализуем."""
    if value is None:
        return []
    if isinstance(value, list):
        return value
    return [value]


def open_path(path: str | os.PathLike) -> None:
    """Открывает файл или папку в проводнике по умолчанию."""
    if sys.platform == "win32":
        os.startfile(str(path))  # type: ignore[attr-defined]
    else:  # pragma: no cover - приложение рассчитано на Windows
        subprocess.Popen(["xdg-open", str(path)])
