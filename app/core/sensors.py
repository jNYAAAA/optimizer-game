"""Сбор температур и оборотов вентиляторов.

Основной источник — встроенный **SensorHelper.exe** на базе
``LibreHardwareMonitorLib`` (в комплекте приложения): он отдаёт температуры CPU,
GPU, накопителей, чипсета, модулей памяти и обороты вентиляторов. Хелперу нужны
права администратора (их приложение запрашивает при запуске).

Если хелпер недоступен, используется резервный путь:
``nvidia-smi``, SMART накопителей, ACPI-термозоны и ``Win32_Fan``.
"""
from __future__ import annotations

import json
import os
import subprocess
from dataclasses import dataclass

from ..utils import CREATE_NO_WINDOW, as_list, powershell_json, resource_path, run_command

_HELPER_REL = os.path.join("assets", "LibreHardwareMonitor", "SensorHelper.exe")
_ORDER = ["CPU", "GPU", "ОЗУ", "Накопитель", "Материнская плата", "Вентилятор", "Датчик", "Термозона ACPI"]


@dataclass
class SensorReading:
    component: str
    name: str
    value: float
    source: str
    unit: str = "°C"


# ---------------------------------------------------------------------------
# Встроенный монитор (LibreHardwareMonitorLib)
# ---------------------------------------------------------------------------
def _helper_path() -> str | None:
    path = resource_path(_HELPER_REL)
    return path if os.path.exists(path) else None


def _component_for(hardware: str, name: str) -> str:
    text = f"{hardware} {name}".lower()
    if any(k in text for k in ("geforce", "radeon", "nvidia", "rtx", "gtx", "gpu")):
        return "GPU"
    if any(k in text for k in ("ryzen", "intel", "core", "cpu", "tctl", "tdie", "package")):
        return "CPU"
    if any(k in text for k in ("nvme", "ssd", "hdd", "storage", "drive", "hdd")):
        return "Накопитель"
    if any(k in text for k in ("dimm", "ddr", "memory", "ram")):
        return "ОЗУ"
    if any(
        k in text
        for k in ("it8", "nuvoton", "lpc", "motherboard", "chipset", "mainboard", "gigabyte", "asus", "msi", "asrock")
    ):
        return "Материнская плата"
    return "Датчик"


def _monitor_readings() -> list[SensorReading]:
    helper = _helper_path()
    if not helper:
        return []
    try:
        proc = subprocess.run(
            [helper],
            capture_output=True,
            text=True,
            timeout=40,
            creationflags=CREATE_NO_WINDOW,
            encoding="utf-8",
            errors="replace",
        )
    except Exception:  # noqa: BLE001
        return []

    text = (proc.stdout or "").strip()
    if not text or text.startswith("{"):
        return []
    try:
        data = json.loads(text)
    except ValueError:
        return []
    if not isinstance(data, list):
        return []

    readings: list[SensorReading] = []
    for item in data:
        if not isinstance(item, dict):
            continue
        hardware = str(item.get("hw") or "")
        name = str(item.get("name") or "")
        sensor_type = str(item.get("type") or "")
        try:
            value = float(item.get("value"))
        except (TypeError, ValueError):
            continue

        if sensor_type == "Fan":
            if value <= 0:
                continue
            readings.append(
                SensorReading("Вентилятор", f"{hardware} · {name}", value, "LHM", "RPM")
            )
            continue

        if value <= 0:
            continue
        component = _component_for(hardware, name)
        display = f"{hardware} · {name}" if component in ("GPU", "Накопитель", "ОЗУ", "Материнская плата") else name
        readings.append(SensorReading(component, display, value, "LHM"))
    return readings


# ---------------------------------------------------------------------------
# Резервный путь (без встроенного монитора)
# ---------------------------------------------------------------------------
_PS_SENSORS = r"""
$ErrorActionPreference = 'SilentlyContinue'
$out = [ordered]@{ disks = @(); smart = @(); acpi = @(); thermal = @(); fan = @() }

$disks = foreach ($d in (Get-PhysicalDisk)) {
    $r = $d | Get-StorageReliabilityCounter
    $t = $null
    if ($r -and $r.Temperature) { $t = [double]$r.Temperature }
    [ordered]@{ name = "$($d.FriendlyName)"; media = "$($d.MediaType)"; temp = $t }
}
$out.disks = @($disks)

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

$acpi = Get-CimInstance -Namespace 'root\WMI' -ClassName MSAcpi_ThermalZoneTemperature
if ($acpi) {
    $out.acpi = @($acpi | ForEach-Object {
        [ordered]@{ name = "$($_.InstanceName)"; value = [math]::Round(($_.CurrentTemperature / 10.0) - 273.15, 1) }
    })
}

$tz = Get-CimInstance -ClassName Win32_PerfFormattedData_Counters_ThermalZoneInformation
if ($tz) {
    $out.thermal = @($tz | ForEach-Object {
        $kelvin = if ($_.HighPrecisionTemperature) { $_.HighPrecisionTemperature / 10.0 } else { [double]$_.Temperature }
        $name = ("$($_.Name)" -replace '^\\?_TZ\.', '')
        [ordered]@{ name = $name; value = [math]::Round($kelvin - 273.15, 1) }
    })
}

$fan = Get-CimInstance Win32_Fan
if ($fan) {
    $out.fan = @($fan | ForEach-Object { [ordered]@{ name = "$($_.Name)"; value = [double]$_.DesiredSpeed } })
}

$out | ConvertTo-Json -Depth 4 -Compress
"""


def _gpu_temps() -> list[SensorReading]:
    try:
        code, output = run_command(
            "nvidia-smi --query-gpu=name,temperature.gpu --format=csv,noheader,nounits",
            timeout=15,
        )
    except Exception:  # noqa: BLE001
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


def _fallback_readings() -> list[SensorReading]:
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
            readings.append(SensorReading("Накопитель", str(disk.get("name") or "SATA"), float(value), "SMART-ATA"))

    for zone in as_list(data.get("acpi")):
        value = zone.get("value")
        if value:
            readings.append(SensorReading("Термозона ACPI", str(zone.get("name") or "—"), float(value), "ACPI"))

    for zone in as_list(data.get("thermal")):
        value = zone.get("value")
        if value and value > -50:
            readings.append(SensorReading("Термозона ACPI", str(zone.get("name") or "—"), float(value), "PerfCounter"))

    for fan in as_list(data.get("fan")):
        value = fan.get("value")
        if value:
            readings.append(SensorReading("Вентилятор", str(fan.get("name") or "—"), float(value), "Win32_Fan", "RPM"))
    return readings


def _sort(readings: list[SensorReading]) -> list[SensorReading]:
    readings.sort(key=lambda r: (_ORDER.index(r.component) if r.component in _ORDER else 99, r.name.lower()))
    return readings


def collect_temperatures() -> list[SensorReading]:
    """Возвращает найденные температуры и обороты (может быть пустым)."""
    readings = _monitor_readings()
    if readings:
        return _sort(readings)
    return _sort(_fallback_readings())
