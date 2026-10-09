"""Информация о драйверах и проверка обновлений через Windows Update.

* ``Get-CimInstance Win32_PnPSignedDriver`` — установленные драйверы и их версии;
* ``Microsoft.Update.Session`` — поиск доступных обновлений драйверов.

Проверка обновлений охватывает только то, что публикует Microsoft (Windows
Update). Собственные утилиты NVIDIA/AMD/Intel могут предлагать более свежие
версии — это указано в интерфейсе.
"""
from __future__ import annotations

from dataclasses import dataclass, field

from ..utils import as_list, powershell_json

# Порядок отображения важных классов устройств.
CLASS_ORDER = [
    "DISPLAY",
    "NET",
    "MEDIA",
    "SYSTEM",
    "HDC",
    "SCSIADAPTER",
    "USB",
    "BLUETOOTH",
    "MONITOR",
    "PROCESSOR",
    "IMAGE",
    "BATTERY",
    "HIDCLASS",
    "KEYBOARD",
    "MOUSE",
]
CLASS_SET = set(CLASS_ORDER)

CLASS_LABELS = {
    "DISPLAY": "Видео",
    "NET": "Сеть",
    "MEDIA": "Звук",
    "SYSTEM": "Система",
    "HDC": "Диски",
    "SCSIADAPTER": "Контроллер",
    "USB": "USB",
    "BLUETOOTH": "Bluetooth",
    "MONITOR": "Монитор",
    "PROCESSOR": "Процессор",
    "IMAGE": "Камера",
    "BATTERY": "Питание",
    "HIDCLASS": "HID",
    "KEYBOARD": "Клавиатура",
    "MOUSE": "Мышь",
}


@dataclass
class DriverInfo:
    name: str
    version: str
    date: str
    manufacturer: str
    device_class: str

    @property
    def class_label(self) -> str:
        return CLASS_LABELS.get(self.device_class.upper(), self.device_class or "—")


@dataclass
class DriverUpdate:
    title: str
    provider: str
    date: str


@dataclass
class DriverUpdateResult:
    ok: bool
    updates: list[DriverUpdate] = field(default_factory=list)
    message: str = ""


_LIST_SCRIPT = r"""
$ErrorActionPreference = 'SilentlyContinue'
$items = Get-CimInstance Win32_PnPSignedDriver | Where-Object { $_.DeviceName } | ForEach-Object {
    $date = ''
    if ($_.DriverDate) { $date = $_.DriverDate.ToString('yyyy-MM-dd') }
    [ordered]@{
        name         = "$($_.DeviceName)"
        version      = "$($_.DriverVersion)"
        date         = $date
        manufacturer = "$($_.Manufacturer)"
        deviceClass  = "$($_.DeviceClass)"
    }
}
$items | ConvertTo-Json -Depth 3 -Compress
"""

_UPDATE_SCRIPT = r"""
$ErrorActionPreference = 'Stop'
$session = New-Object -ComObject Microsoft.Update.Session
$searcher = $session.CreateUpdateSearcher()
$result = $searcher.Search("IsInstalled=0 and Type='Driver'")
$updates = foreach ($u in $result.Updates) {
    [ordered]@{
        title    = "$($u.Title)"
        provider = "$($u.DriverProvider)"
        date     = "$($u.DriverVerDate)"
    }
}
[ordered]@{ count = [int]$result.Updates.Count; updates = @($updates) } | ConvertTo-Json -Depth 4 -Compress
"""


def list_drivers() -> list[DriverInfo]:
    """Возвращает установленные драйверы ключевых классов устройств."""
    try:
        data = powershell_json(_LIST_SCRIPT, timeout=120)
    except Exception:  # noqa: BLE001
        return []

    drivers: list[DriverInfo] = []
    seen: set[tuple[str, str]] = set()
    for entry in as_list(data):
        if not isinstance(entry, dict):
            continue
        device_class = str(entry.get("deviceClass") or "").strip()
        if device_class.upper() not in CLASS_SET:
            continue
        name = str(entry.get("name") or "").strip()
        version = str(entry.get("version") or "").strip()
        if not name:
            continue
        key = (name, version)
        if key in seen:
            continue
        seen.add(key)
        drivers.append(
            DriverInfo(
                name=name,
                version=version or "—",
                date=str(entry.get("date") or "—"),
                manufacturer=str(entry.get("manufacturer") or "—"),
                device_class=device_class,
            )
        )

    def sort_key(driver: DriverInfo) -> tuple[int, str]:
        upper = driver.device_class.upper()
        index = CLASS_ORDER.index(upper) if upper in CLASS_SET else len(CLASS_ORDER)
        return (index, driver.name.lower())

    drivers.sort(key=sort_key)
    return drivers


def check_driver_updates() -> DriverUpdateResult:
    """Ищет доступные обновления драйверов через Windows Update."""
    try:
        data = powershell_json(_UPDATE_SCRIPT, timeout=300)
    except Exception as exc:  # noqa: BLE001
        return DriverUpdateResult(False, [], f"Не удалось проверить обновления: {exc}")

    if not isinstance(data, dict):
        return DriverUpdateResult(False, [], "Служба обновления вернула пустой ответ.")

    updates = [
        DriverUpdate(
            title=str(item.get("title") or "—"),
            provider=str(item.get("provider") or "—"),
            date=str(item.get("date") or ""),
        )
        for item in as_list(data.get("updates"))
        if isinstance(item, dict)
    ]
    try:
        count = int(data.get("count") or len(updates))
    except (TypeError, ValueError):
        count = len(updates)

    if count == 0 and not updates:
        return DriverUpdateResult(
            True, [], "Обновления драйверов не найдены — установленные версии актуальны."
        )
    return DriverUpdateResult(
        True, updates, f"Доступно обновлений драйверов: {count}"
    )
