"""Сбор температур и оборотов вентиляторов.

Источники (по убыванию приоритета):

* ``nvidia-smi`` — температура GPU NVIDIA;
* LibreHardwareMonitor / OpenHardwareMonitor (WMI) — CPU, GPU, диски,
  обороты вентиляторов и др., если программа запущена;
* ``Get-StorageReliabilityCounter`` — температура накопителей;
* ``MSStorageDriver_ATAPISmartData`` — SMART-температура SATA-накопителей
  (нужны права администратора);
* ``Win32_PerfFormattedData_Counters_ThermalZoneInformation`` и
  ``MSAcpi_ThermalZoneTemperature`` — ACPI-термозоны (приблизительно);
* ``Win32_Fan`` — обороты вентиляторов (редко доступны).

Универсального способа получить все датчики на Windows без стороннего ПО нет:
производители не отдают температуру CPU и обороты вентиляторов через
стандартный WMI. Приложение умеет находить и запускать LibreHardwareMonitor,
который открывает эти данные через WMI.
"""
from __future__ import annotations

import ctypes
import os
from dataclasses import dataclass
from pathlib import Path

from ..utils import as_list, powershell_json, run_command

LHM_DOWNLOAD_URL = (
    "https://github.com/LibreHardwareMonitor/LibreHardwareMonitor/releases"
)

_HM_NAMES = ["LibreHardwareMonitor.exe", "OpenHardwareMonitor.exe"]
_HM_DIRS = [
    r"C:\Program Files\LibreHardwareMonitor",
    r"C:\Program Files (x86)\LibreHardwareMonitor",
    r"C:\Program Files\OpenHardwareMonitor",
    r"C:\Program Files (x86)\OpenHardwareMonitor",
]


@dataclass
class SensorReading:
    component: str
    name: str
    value: float
    source: str
    unit: str = "°C"


_PS_SENSORS = r"""
$ErrorActionPreference = 'SilentlyContinue'
$out = [ordered]@{ disks = @(); smart = @(); lhmTemp = @(); lhmFan = @(); acpi = @(); thermal = @(); fan = @() }

# Температура накопителей (счётчики надёжности)
$disks = foreach ($d in (Get-PhysicalDisk)) {
    $r = $d | Get-StorageReliabilityCounter
    $t = $null
    if ($r -and $r.Temperature) { $t = [double]$r.Temperature }
    [ordered]@{ name = "$($d.FriendlyName)"; media = "$($d.MediaType)"; temp = $t }
}
$out.disks = @($disks)

# SMART-температура SATA-накопителей (атрибут 194/190), обычно нужны права администратора
$smart = Get-CimInstance -Namespace 'root\WMI' -ClassName MSStorageDriver_ATAPISmartData
if ($smart) {
    $items = foreach ($s in $smart) {
        $v = $s.VendorSpecific
        $temp = $null
        if ($v -and $v.Length -ge 14) {
            for ($i = 2; $i + 12 -le $v.Length; $i += 12) {
                $id = $v[$i]
                if ($id -eq 194) { $temp = [int]$v[$i + 5]; break }
                if ($id -eq 190 -and -not $temp) { $temp = [int]$v[$i + 5] }
            }
        }
        if ($temp) { [ordered]@{ name = "$($s.InstanceName)"; value = [double]$temp } }
    }
    $out.smart = @($items)
}

# Датчики LibreHardwareMonitor / OpenHardwareMonitor
foreach ($ns in @('root\LibreHardwareMonitor', 'root\OpenHardwareMonitor')) {
    $s = Get-CimInstance -Namespace $ns -ClassName Sensor
    if ($s) {
        $out.lhmTemp = @($s | Where-Object { $_.SensorType -eq 'Temperature' } | ForEach-Object {
            [ordered]@{ name = "$($_.Name)"; value = [double]$_.Value }
        })
        $out.lhmFan = @($s | Where-Object { $_.SensorType -eq 'Fan' } | ForEach-Object {
            [ordered]@{ name = "$($_.Name)"; value = [double]$_.Value }
        })
        break
    }
}

# ACPI-термозоны
$acpi = Get-CimInstance -Namespace 'root\WMI' -ClassName MSAcpi_ThermalZoneTemperature
if ($acpi) {
    $out.acpi = @($acpi | ForEach-Object {
        [ordered]@{
            name  = "$($_.InstanceName)"
            value = [math]::Round(($_.CurrentTemperature / 10.0) - 273.15, 1)
        }
    })
}

# Термозоны через счётчики производительности (значение в Кельвинах)
$tz = Get-CimInstance -ClassName Win32_PerfFormattedData_Counters_ThermalZoneInformation
if ($tz) {
    $out.thermal = @($tz | ForEach-Object {
        $kelvin = if ($_.HighPrecisionTemperature) { $_.HighPrecisionTemperature / 10.0 } else { [double]$_.Temperature }
        $name = ("$($_.Name)" -replace '^\\?_TZ\.', '')
        [ordered]@{ name = $name; value = [math]::Round($kelvin - 273.15, 1) }
    })
}

# Вентиляторы (Win32_Fan, если система отдаёт)
$fan = Get-CimInstance Win32_Fan
if ($fan) {
    $out.fan = @($fan | ForEach-Object {
        [ordered]@{ name = "$($_.Name)"; value = [double]$_.DesiredSpeed }
    })
}

$out | ConvertTo-Json -Depth 4 -Compress
"""

_ORDER = ["CPU", "GPU", "Датчик", "Накопитель", "Вентилятор", "Термозона ACPI"]


def find_hardware_monitor() -> str | None:
    """Ищет установленный LibreHardwareMonitor / OpenHardwareMonitor."""
    candidates: list[Path] = []
    for directory in _HM_DIRS:
        for name in _HM_NAMES:
            candidates.append(Path(directory) / name)
    for base in (
        os.environ.get("LOCALAPPDATA"),
        os.environ.get("ProgramData"),
        os.environ.get("USERPROFILE"),
    ):
        if not base:
            continue
        root = Path(base)
        for name in _HM_NAMES:
            candidates.append(root / name)
            candidates.append(root / "Downloads" / name)
            candidates.append(root / "Desktop" / name)
    for candidate in candidates:
        try:
            if candidate.is_file():
                return str(candidate)
        except OSError:
            continue
    return None


def launch_hardware_monitor() -> tuple[bool, str]:
    """Запускает найденный монитор с правами администратора (нужно для драйвера)."""
    executable = find_hardware_monitor()
    if not executable:
        return False, "LibreHardwareMonitor не найден"
    try:
        result = ctypes.windll.shell32.ShellExecuteW(None, "runas", executable, None, None, 1)
    except Exception as exc:  # noqa: BLE001
        return False, f"Не удалось запустить: {exc}"
    if result > 32:
        return True, "LibreHardwareMonitor запускается…"
    return False, "Запуск отменён"


def _gpu_temps() -> list[SensorReading]:
    try:
        code, output = run_command(
            "nvidia-smi --query-gpu=name,temperature.gpu --format=csv,noheader,nounits",
            timeout=15,
        )
    except Exception:  # noqa: BLE001 - nvidia-smi может отсутствовать
        return []
    if code != 0:
        return []

    readings: list[SensorReading] = []
    for line in output.splitlines():
        parts = [part.strip() for part in line.split(",")]
        if len(parts) < 2:
            continue
        try:
            temperature = float(parts[1])
        except ValueError:
            continue
        if temperature > 0:
            readings.append(SensorReading("GPU", parts[0], temperature, "nvidia-smi"))
    return readings


def collect_temperatures() -> list[SensorReading]:
    """Возвращает найденные температуры и обороты (может быть пустым)."""
    readings = _gpu_temps()

    try:
        data = powershell_json(_PS_SENSORS, timeout=60) or {}
    except Exception:  # noqa: BLE001
        data = {}
    if not isinstance(data, dict):
        data = {}

    for disk in as_list(data.get("disks")):
        temp = disk.get("temp")
        if temp:
            media = disk.get("media") or ""
            label = disk.get("name") or "Накопитель"
            if media and media.lower() not in ("unspecified", ""):
                label = f"{label} ({media})"
            readings.append(SensorReading("Накопитель", label, float(temp), "SMART"))

    for disk in as_list(data.get("smart")):
        value = disk.get("value")
        if value:
            readings.append(
                SensorReading("Накопитель", str(disk.get("name") or "SATA"), float(value), "SMART-ATA")
            )

    for sensor in as_list(data.get("lhmTemp")):
        value = sensor.get("value")
        if value:
            readings.append(
                SensorReading("Датчик", str(sensor.get("name") or "—"), float(value), "LHM")
            )

    for sensor in as_list(data.get("lhmFan")):
        value = sensor.get("value")
        if value:
            readings.append(
                SensorReading(
                    "Вентилятор", str(sensor.get("name") or "—"), float(value), "LHM", "RPM"
                )
            )

    for zone in as_list(data.get("acpi")):
        value = zone.get("value")
        if value:
            readings.append(
                SensorReading("Термозона ACPI", str(zone.get("name") or "—"), float(value), "ACPI")
            )

    for zone in as_list(data.get("thermal")):
        value = zone.get("value")
        if value and value > -50:
            readings.append(
                SensorReading(
                    "Термозона ACPI",
                    str(zone.get("name") or "—"),
                    float(value),
                    "PerfCounter",
                )
            )

    for fan in as_list(data.get("fan")):
        value = fan.get("value")
        if value:
            readings.append(
                SensorReading(
                    "Вентилятор", str(fan.get("name") or "—"), float(value), "Win32_Fan", "RPM"
                )
            )

    readings.sort(
        key=lambda r: (_ORDER.index(r.component) if r.component in _ORDER else 99, r.name.lower())
    )
    return readings
