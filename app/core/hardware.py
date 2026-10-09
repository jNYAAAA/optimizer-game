"""Сбор характеристик ПК.

Основной источник — PowerShell CIM-запросы (``Get-CimInstance``), которые дают
модель материнской платы, скорость и тип модулей памяти, медиа-тип дисков и т. д.
Часть данных (загрузка CPU, использование разделов) берётся из ``psutil``.

Если PowerShell недоступен или вернул ошибку, используется резервный путь на
``psutil`` + ``platform``.
"""
from __future__ import annotations

import platform
import time
from dataclasses import dataclass, field
from datetime import datetime
from typing import Any

import psutil

from ..utils import as_list, powershell_json

# ---------------------------------------------------------------------------
# Справочники SMBIOS
# ---------------------------------------------------------------------------
_SMBIOS_MEMORY_TYPES = {
    0x01: "Other",
    0x02: "DRAM",
    0x0F: "SDRAM",
    0x11: "SDRAM",
    0x12: "DDR",
    0x13: "DDR2",
    0x18: "DDR3",
    0x1A: "DDR4",
    0x1E: "LPDDR4",
    0x22: "DDR5",
    0x23: "LPDDR5",
}

_MEMORY_TYPES = {
    20: "DDR",
    21: "DDR2",
    24: "DDR3",
    26: "DDR4",
}

_FORM_FACTORS = {
    8: "DIMM",
    9: "SODIMM",
    12: "SODIMM",
    13: "SRIMM",
    16: "FB-DIMM",
}


def _memory_type_name(smbios_type: Any, memory_type: Any) -> str:
    for candidate in (smbios_type, memory_type):
        try:
            key = int(candidate)
        except (TypeError, ValueError):
            continue
        if key in _SMBIOS_MEMORY_TYPES:
            return _SMBIOS_MEMORY_TYPES[key]
        if key in _MEMORY_TYPES:
            return _MEMORY_TYPES[key]
    return "—"


def _form_factor_name(value: Any) -> str:
    try:
        return _FORM_FACTORS.get(int(value), "—")
    except (TypeError, ValueError):
        return "—"


def _to_int(value: Any, default: int = 0) -> int:
    try:
        if value is None:
            return default
        return int(value)
    except (TypeError, ValueError):
        return default


def _clean(value: Any, default: str = "—") -> str:
    if value is None:
        return default
    text = str(value).strip()
    return text or default


def _format_datetime(value: Any) -> str:
    if not value:
        return "—"
    text = str(value).strip()
    # PS отдаёт вид "20240115120000.000000+180"
    head = text.split(".")[0]
    for fmt in ("%Y%m%d%H%M%S",):
        try:
            return datetime.strptime(head, fmt).strftime("%d.%m.%Y %H:%M")
        except ValueError:
            pass
    try:
        parsed = datetime.fromisoformat(text)
        return parsed.strftime("%d.%m.%Y %H:%M")
    except ValueError:
        return text


# ---------------------------------------------------------------------------
# Модели данных
# ---------------------------------------------------------------------------
@dataclass
class CpuInfo:
    name: str = "—"
    vendor: str = "—"
    cores: int = 0
    threads: int = 0
    max_clock_mhz: int = 0
    socket: str = "—"
    l2_cache_bytes: int = 0
    l3_cache_bytes: int = 0
    arch: str = "—"


@dataclass
class MemoryModule:
    manufacturer: str = "—"
    capacity_bytes: int = 0
    speed_mhz: int = 0
    configured_mhz: int = 0
    part_number: str = "—"
    slot: str = "—"
    memory_type: str = "—"
    form_factor: str = "—"


@dataclass
class RamInfo:
    total_bytes: int = 0
    modules: list[MemoryModule] = field(default_factory=list)


@dataclass
class GpuInfo:
    name: str = "—"
    vram_bytes: int = 0
    driver_version: str = "—"
    driver_date: str = "—"
    video_processor: str = "—"
    status: str = "—"
    resolution: str = "—"
    refresh_rate: int = 0


@dataclass
class DiskInfo:
    friendly_name: str = "—"
    media_type: str = "—"
    bus_type: str = "—"
    size_bytes: int = 0
    health: str = "—"
    serial: str = "—"


@dataclass
class PartitionInfo:
    device: str = "—"
    mountpoint: str = "—"
    fstype: str = "—"
    total: int = 0
    used: int = 0
    free: int = 0
    percent: float = 0.0


@dataclass
class OsInfo:
    caption: str = "—"
    version: str = "—"
    build: str = "—"
    arch: str = "—"
    install_date: str = "—"
    last_boot: str = "—"
    serial: str = "—"
    user: str = "—"
    computer_name: str = "—"


@dataclass
class MotherboardInfo:
    manufacturer: str = "—"
    product: str = "—"
    version: str = "—"
    serial: str = "—"
    bios_vendor: str = "—"
    bios_version: str = "—"
    bios_date: str = "—"


@dataclass
class SystemInfo:
    cpu: CpuInfo = field(default_factory=CpuInfo)
    ram: RamInfo = field(default_factory=RamInfo)
    gpus: list[GpuInfo] = field(default_factory=list)
    disks: list[DiskInfo] = field(default_factory=list)
    partitions: list[PartitionInfo] = field(default_factory=list)
    os_info: OsInfo = field(default_factory=OsInfo)
    motherboard: MotherboardInfo = field(default_factory=MotherboardInfo)
    source: str = "powershell"
    error: str | None = None


# ---------------------------------------------------------------------------
# PowerShell-скрипт
# ---------------------------------------------------------------------------
_SPEC_SCRIPT = r"""
$ErrorActionPreference = 'SilentlyContinue'
$cs   = Get-CimInstance Win32_ComputerSystem
$os   = Get-CimInstance Win32_OperatingSystem
$cpu  = Get-CimInstance Win32_Processor | Select-Object -First 1
$bb   = Get-CimInstance Win32_BaseBoard | Select-Object -First 1
$bios = Get-CimInstance Win32_BIOS | Select-Object -First 1
$mem  = @(Get-CimInstance Win32_PhysicalMemory)
$gpu  = @(Get-CimInstance Win32_VideoController)

# Точный объём VRAM из реестра (Win32_VideoController.AdapterRAM ограничен 4 ГБ)
$vram = @{}
$cls = 'HKLM:\SYSTEM\CurrentControlSet\Control\Class\{4d36e968-e325-11ce-bfc1-08002be10318}'
Get-ChildItem $cls -ErrorAction SilentlyContinue | ForEach-Object {
    $p = Get-ItemProperty $_.PSPath -ErrorAction SilentlyContinue
    if ($p.DriverDesc) {
        $size = $p.'HardwareInformation.qwMemorySize'
        if (-not $size) { $size = $p.'HardwareInformation.MemorySize' }
        if ($size) { $vram[$p.DriverDesc] = [Int64]$size }
    }
}

$phys = @()
try { $phys = @(Get-PhysicalDisk) } catch {}

$memMods = foreach ($m in $mem) {
    [ordered]@{
        manufacturer = "$($m.Manufacturer)"
        capacity     = [Int64]$m.Capacity
        speed        = [int]$m.Speed
        configured   = [int]$m.ConfiguredClockSpeed
        part         = "$($m.PartNumber)"
        slot         = "$($m.DeviceLocator)"
        smbiosType   = [int]$m.SMBIOSMemoryType
        memoryType   = [int]$m.MemoryType
        formFactor   = [int]$m.FormFactor
    }
}

$gpus = foreach ($g in $gpu) {
    [ordered]@{
        name           = "$($g.Name)"
        adapterRam     = [Int64]$g.AdapterRAM
        vram           = [Int64]($vram[$g.Name])
        driverVersion  = "$($g.DriverVersion)"
        driverDate     = $g.DriverDate.ToString('yyyy-MM-dd')
        videoProcessor = "$($g.VideoProcessor)"
        status         = "$($g.Status)"
        currentH       = [int]$g.CurrentHorizontalResolution
        currentV       = [int]$g.CurrentVerticalResolution
        refresh        = [int]$g.CurrentRefreshRate
    }
}

$disks = foreach ($d in $phys) {
    [ordered]@{
        friendlyName = "$($d.FriendlyName)"
        mediaType    = "$($d.MediaType)"
        busType      = "$($d.BusType)"
        size         = [Int64]$d.Size
        health       = "$($d.HealthStatus)"
        serial       = "$($d.SerialNumber)"
    }
}

$result = [ordered]@{
    computerName = "$($cs.Name)"
    totalRam     = [Int64]$cs.TotalPhysicalMemory
    os = [ordered]@{
        caption  = "$($os.Caption)"
        version  = "$($os.Version)"
        build    = "$($os.BuildNumber)"
        arch     = "$($os.OSArchitecture)"
        install  = $os.InstallDate.ToString('yyyy-MM-dd HH:mm')
        lastBoot = $os.LastBootUpTime.ToString('yyyy-MM-dd HH:mm')
        serial   = "$($os.SerialNumber)"
        user     = "$($cs.UserName)"
    }
    cpu = [ordered]@{
        name     = "$($cpu.Name)"
        vendor   = "$($cpu.Manufacturer)"
        cores    = [int]$cpu.NumberOfCores
        threads  = [int]$cpu.NumberOfLogicalProcessors
        maxClock = [int]$cpu.MaxClockSpeed
        socket   = "$($cpu.SocketDesignation)"
        l2       = [int]$cpu.L2CacheSize
        l3       = [int]$cpu.L3CacheSize
        arch     = "$($cpu.AddressWidth)"
    }
    motherboard = [ordered]@{
        manufacturer = "$($bb.Manufacturer)"
        product      = "$($bb.Product)"
        version      = "$($bb.Version)"
        serial       = "$($bb.SerialNumber)"
        biosVendor   = "$($bios.Manufacturer)"
        biosVersion  = "$($bios.SMBIOSBIOSVersion)"
        biosDate     = $bios.ReleaseDate.ToString('yyyy-MM-dd')
    }
    memoryModules = @($memMods)
    gpus          = @($gpus)
    disks         = @($disks)
}

$result | ConvertTo-Json -Depth 6 -Compress
"""


def _partitions_from_psutil() -> list[PartitionInfo]:
    result: list[PartitionInfo] = []
    for part in psutil.disk_partitions(all=False):
        try:
            usage = psutil.disk_usage(part.mountpoint)
        except OSError:
            continue
        result.append(
            PartitionInfo(
                device=part.device,
                mountpoint=part.mountpoint,
                fstype=part.fstype or "—",
                total=usage.total,
                used=usage.used,
                free=usage.free,
                percent=usage.percent,
            )
        )
    return result


def _fallback_system_info(error: str | None = None) -> SystemInfo:
    vm = psutil.virtual_memory()
    freq = psutil.cpu_freq()
    cpu_name = platform.processor() or platform.machine() or "—"
    return SystemInfo(
        cpu=CpuInfo(
            name=cpu_name,
            vendor=platform.machine() or "—",
            cores=psutil.cpu_count(logical=False) or 0,
            threads=psutil.cpu_count(logical=True) or 0,
            max_clock_mhz=int(freq.max) if freq and freq.max else 0,
            arch=platform.architecture()[0],
        ),
        ram=RamInfo(total_bytes=vm.total, modules=[]),
        gpus=[],
        disks=[],
        partitions=_partitions_from_psutil(),
        os_info=OsInfo(
            caption=f"{platform.system()} {platform.release()}",
            version=platform.version(),
            build=platform.version(),
            arch=platform.architecture()[0],
            computer_name=platform.node(),
            user=platform.node(),
        ),
        source="fallback",
        error=error,
    )


def _parse_system_info(data: dict) -> SystemInfo:
    cpu_raw = data.get("cpu") or {}
    os_raw = data.get("os") or {}
    board_raw = data.get("motherboard") or {}

    cpu = CpuInfo(
        name=_clean(cpu_raw.get("name")),
        vendor=_clean(cpu_raw.get("vendor")),
        cores=_to_int(cpu_raw.get("cores")),
        threads=_to_int(cpu_raw.get("threads")),
        max_clock_mhz=_to_int(cpu_raw.get("maxClock")),
        socket=_clean(cpu_raw.get("socket")),
        l2_cache_bytes=_to_int(cpu_raw.get("l2")) * 1024,
        l3_cache_bytes=_to_int(cpu_raw.get("l3")) * 1024,
        arch=_clean(cpu_raw.get("arch")),
    )

    modules: list[MemoryModule] = []
    for mod in as_list(data.get("memoryModules")):
        modules.append(
            MemoryModule(
                manufacturer=_clean(mod.get("manufacturer")),
                capacity_bytes=_to_int(mod.get("capacity")),
                speed_mhz=_to_int(mod.get("speed")),
                configured_mhz=_to_int(mod.get("configured")),
                part_number=_clean(mod.get("part")),
                slot=_clean(mod.get("slot")),
                memory_type=_memory_type_name(mod.get("smbiosType"), mod.get("memoryType")),
                form_factor=_form_factor_name(mod.get("formFactor")),
            )
        )

    total_ram = _to_int(data.get("totalRam"))
    if total_ram <= 0:
        total_ram = psutil.virtual_memory().total
    ram = RamInfo(total_bytes=total_ram, modules=modules)

    gpus: list[GpuInfo] = []
    for gpu in as_list(data.get("gpus")):
        vram = _to_int(gpu.get("vram")) or _to_int(gpu.get("adapterRam"))
        width = _to_int(gpu.get("currentH"))
        height = _to_int(gpu.get("currentV"))
        resolution = f"{width}×{height}" if width and height else "—"
        gpus.append(
            GpuInfo(
                name=_clean(gpu.get("name")),
                vram_bytes=vram,
                driver_version=_clean(gpu.get("driverVersion")),
                driver_date=_format_datetime(gpu.get("driverDate")),
                video_processor=_clean(gpu.get("videoProcessor")),
                status=_clean(gpu.get("status")),
                resolution=resolution,
                refresh_rate=_to_int(gpu.get("refresh")),
            )
        )

    disks: list[DiskInfo] = []
    for disk in as_list(data.get("disks")):
        disks.append(
            DiskInfo(
                friendly_name=_clean(disk.get("friendlyName")),
                media_type=_clean(disk.get("mediaType")),
                bus_type=_clean(disk.get("busType")),
                size_bytes=_to_int(disk.get("size")),
                health=_clean(disk.get("health")),
                serial=_clean(disk.get("serial")),
            )
        )

    os_info = OsInfo(
        caption=_clean(os_raw.get("caption")),
        version=_clean(os_raw.get("version")),
        build=_clean(os_raw.get("build")),
        arch=_clean(os_raw.get("arch")),
        install_date=_format_datetime(os_raw.get("install")),
        last_boot=_format_datetime(os_raw.get("lastBoot")),
        serial=_clean(os_raw.get("serial")),
        user=_clean(os_raw.get("user")),
        computer_name=_clean(data.get("computerName"), platform.node()),
    )

    motherboard = MotherboardInfo(
        manufacturer=_clean(board_raw.get("manufacturer")),
        product=_clean(board_raw.get("product")),
        version=_clean(board_raw.get("version")),
        serial=_clean(board_raw.get("serial")),
        bios_vendor=_clean(board_raw.get("biosVendor")),
        bios_version=_clean(board_raw.get("biosVersion")),
        bios_date=_format_datetime(board_raw.get("biosDate")),
    )

    return SystemInfo(
        cpu=cpu,
        ram=ram,
        gpus=gpus,
        disks=disks,
        partitions=_partitions_from_psutil(),
        os_info=os_info,
        motherboard=motherboard,
        source="powershell",
    )


def collect_system_info(progress=None) -> SystemInfo:
    """Собирает полную информацию о системе.

    ``progress`` — необязательный колбэк ``progress(percent, message)``.
    """
    if progress:
        progress(5, "Опрос оборудования через PowerShell…")
    try:
        data = powershell_json(_SPEC_SCRIPT, timeout=90)
    except Exception as exc:  # noqa: BLE001 - любая ошибка => резервный путь
        if progress:
            progress(100, "Не удалось опросить WMI, используется резервный режим")
        return _fallback_system_info(str(exc))

    if not isinstance(data, dict):
        if progress:
            progress(100, "Пустой ответ WMI, используется резервный режим")
        return _fallback_system_info("Пустой ответ PowerShell")

    if progress:
        progress(90, "Разбор данных…")
    info = _parse_system_info(data)
    if progress:
        progress(100, "Готово")
    return info


def live_stats() -> dict[str, Any]:
    """Быстрые «живые» показатели для дашборда (без тяжёлых запросов)."""
    vm = psutil.virtual_memory()
    freq = psutil.cpu_freq()
    return {
        "cpu_percent": psutil.cpu_percent(interval=None),
        "cpu_freq_current": int(freq.current) if freq else 0,
        "ram_percent": vm.percent,
        "ram_used": vm.used,
        "ram_total": vm.total,
        "ram_available": vm.available,
        "uptime_seconds": int(time.time() - psutil.boot_time()),
    }
