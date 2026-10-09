"""Просмотр и управление службами Windows."""
from __future__ import annotations

import re
from dataclasses import dataclass

from ..utils import as_list, powershell_json, run_powershell

_NAME_RE = re.compile(r"^[\w .\-]+$", re.UNICODE)

START_MODES = ["Automatic", "Manual", "Disabled"]
START_MODE_LABELS = {
    "Auto": "Автоматически",
    "Automatic": "Автоматически",
    "Manual": "Вручную",
    "Disabled": "Отключена",
    "Boot": "Загрузка",
    "System": "Система",
    "Unknown": "—",
}
STATE_LABELS = {"Running": "Работает", "Stopped": "Остановлена"}

# Службы, которые обычно безопасно отключать, с пояснением и уровнем риска.
RECOMMENDED_DISABLE: dict[str, tuple[str, str]] = {
    "DiagTrack": ("Телеметрия Windows", "low"),
    "dmwappushservice": ("WAP-push сообщения телеметрии", "low"),
    "RemoteRegistry": ("Удалённое редактирование реестра", "low"),
    "Fax": ("Факс", "low"),
    "RetailDemo": ("Демонстрационный режим в магазинах", "low"),
    "MapsBroker": ("Загрузка офлайн-карт", "low"),
    "XblAuthManager": ("Проверка входа Xbox Live", "low"),
    "XblGameSave": ("Сохранение игр Xbox Live", "low"),
    "XboxNetApiSvc": ("Сетевые игры Xbox Live", "low"),
    "WSearch": ("Индексация поиска Windows", "medium"),
    "SysMain": ("Предзагрузка приложений (SuperFetch)", "medium"),
    "PrintNotify": ("Уведомления принтеров", "low"),
    "WerSvc": ("Отчёты об ошибках Windows", "low"),
    "DoSvc": ("Оптимизация доставки обновлений", "low"),
}


@dataclass
class ServiceInfo:
    name: str
    display_name: str
    state: str
    start_mode: str
    path: str
    account: str
    description: str

    @property
    def is_recommended(self) -> bool:
        return self.name in RECOMMENDED_DISABLE

    @property
    def recommendation(self) -> str:
        return RECOMMENDED_DISABLE.get(self.name, ("", ""))[0]

    @property
    def risk(self) -> str:
        return RECOMMENDED_DISABLE.get(self.name, ("", "low"))[1]


_LIST_SCRIPT = r"""
$ErrorActionPreference = 'SilentlyContinue'
$items = Get-CimInstance Win32_Service | Select-Object `
    Name, DisplayName, State, StartMode, PathName, StartName, Description
$items | ConvertTo-Json -Depth 3 -Compress
"""


def list_services() -> list[ServiceInfo]:
    data = powershell_json(_LIST_SCRIPT, timeout=90)
    services: list[ServiceInfo] = []
    for entry in as_list(data):
        if not isinstance(entry, dict):
            continue
        services.append(
            ServiceInfo(
                name=str(entry.get("Name") or ""),
                display_name=str(entry.get("DisplayName") or entry.get("Name") or ""),
                state=str(entry.get("State") or "Unknown"),
                start_mode=str(entry.get("StartMode") or "Unknown"),
                path=str(entry.get("PathName") or ""),
                account=str(entry.get("StartName") or ""),
                description=str(entry.get("Description") or ""),
            )
        )
    services.sort(key=lambda s: s.display_name.lower())
    return services


def _valid_name(name: str) -> bool:
    return bool(name) and _NAME_RE.match(name) is not None


def _escape(name: str) -> str:
    return name.replace("'", "''")


def _run(script: str, timeout: int = 60) -> tuple[bool, str]:
    proc = run_powershell(f"$ErrorActionPreference='Stop'; {script}", timeout=timeout)
    if proc.returncode == 0:
        return True, (proc.stdout or "").strip()
    message = (proc.stderr or proc.stdout or "").strip()
    return False, message or "Неизвестная ошибка"


def set_start_mode(name: str, mode: str) -> tuple[bool, str]:
    """mode: Automatic | Manual | Disabled."""
    if not _valid_name(name):
        return False, "Недопустимое имя службы"
    if mode not in START_MODES:
        return False, "Недопустимый тип запуска"
    return _run(f"Set-Service -Name '{_escape(name)}' -StartupType {mode}; 'OK'")


def start_service(name: str) -> tuple[bool, str]:
    if not _valid_name(name):
        return False, "Недопустимое имя службы"
    return _run(f"Start-Service -Name '{_escape(name)}'; 'OK'")


def stop_service(name: str) -> tuple[bool, str]:
    if not _valid_name(name):
        return False, "Недопустимое имя службы"
    return _run(f"Stop-Service -Name '{_escape(name)}' -Force; 'OK'")


def disable_service(name: str) -> tuple[bool, str]:
    stop_ok, stop_message = stop_service(name)
    mode_ok, mode_message = set_start_mode(name, "Disabled")
    if mode_ok:
        return True, "Служба отключена"
    if stop_ok:
        return False, f"Остановлена, но тип запуска не изменён: {mode_message}"
    return False, mode_message or stop_message
