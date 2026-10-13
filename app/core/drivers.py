"""Информация о драйверах, проверка обновлений Windows Update и сайтов производителей.

* ``Get-CimInstance Win32_PnPSignedDriver`` — установленные драйверы и версии;
* ``Microsoft.Update.Session`` — доступные обновления драйверов через Windows Update;
* NVIDIA AjaxDriverService — последняя версия драйвера с официального сайта
  (для AMD/Intel автоматическая проверка недоступна, даётся ссылка на сайт).
"""
from __future__ import annotations

import json
import os
import re
import subprocess
import tempfile
import urllib.request
import xml.etree.ElementTree as ET
from dataclasses import dataclass, field
from datetime import datetime
from urllib.parse import quote, quote_plus

from ..utils import CREATE_NO_WINDOW, as_list, powershell_json, run_powershell

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

_VENDOR_SITES = {
    "AMD": "https://www.amd.com/en/support/download/drivers.html",
    "Intel": "https://www.intel.com/content/www/us/en/download/785597/intel-arc-iris-xe-graphics-windows.html",
}
_NVIDIA_LOOKUP = "https://www.nvidia.com/Download/API/lookupValueSearch.aspx?TypeID=3"
_NVIDIA_DRIVER = (
    "https://gfwsl.geforce.com/services_toolkit/services/com/nvidia/services/"
    "AjaxDriverService.php?func=DriverManualLookup&psid={psid}&pfid={pfid}"
    "&osID=57&languageCode=1033&beta=0&isWHQL=1&dltype=-1&dch=1&upCRD=0&qnf=0"
    "&sort1=0&numberOfResults=1"
)


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


@dataclass
class VendorDriverInfo:
    vendor: str
    device: str
    installed: str
    latest: str
    release_date: str
    url: str
    update_available: bool
    note: str = ""
    download_url: str = ""


@dataclass
class MotherboardDriverInfo:
    manufacturer: str = "—"
    product: str = "—"
    url: str = ""
    search_url: str = ""
    platform: str = ""
    hints: list[str] = field(default_factory=list)


@dataclass
class ProblemDevice:
    name: str = "—"
    status: str = "—"
    device_class: str = "—"
    instance_id: str = "—"
    hardware_id: str = ""

    @property
    def catalog_url(self) -> str:
        return catalog_search_url(self.hardware_id)

    @property
    def search_url(self) -> str:
        """Поиск драйвера в браузере по имени устройства и его Hardware ID."""
        parts = [p for p in (self.name, self.hardware_id) if p and p != "—"]
        return "https://duckduckgo.com/?q=" + quote_plus(" ".join(parts) + " драйвер скачать")


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


# ---------------------------------------------------------------------------
# Установленные драйверы
# ---------------------------------------------------------------------------
def list_drivers() -> list[DriverInfo]:
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


def display_drivers(drivers: list[DriverInfo] | None = None) -> list[DriverInfo]:
    drivers = drivers if drivers is not None else list_drivers()
    return [d for d in drivers if d.device_class.upper() == "DISPLAY"]


# ---------------------------------------------------------------------------
# Windows Update
# ---------------------------------------------------------------------------
def check_driver_updates() -> DriverUpdateResult:
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
            True, [], "Windows Update: обновления драйверов не найдены."
        )
    return DriverUpdateResult(True, updates, f"Windows Update: доступно обновлений — {count}")


# ---------------------------------------------------------------------------
# Онлайн-проверка у производителя
# ---------------------------------------------------------------------------
def _http_get(url: str, timeout: int = 25) -> str:
    request = urllib.request.Request(
        url, headers={"User-Agent": "Mozilla/5.0 (OptimizerGame)"}
    )
    with urllib.request.urlopen(request, timeout=timeout) as response:
        return response.read().decode("utf-8", errors="replace")


def _normalize(name: str) -> str:
    text = name.lower()
    for token in ("nvidia", "geforce", "(tm)", "®", "™", "(r)"):
        text = text.replace(token, "")
    return " ".join(text.split())


def _nvidia_marketing_version(wddm: str) -> str | None:
    """32.0.16.1692 -> 616.92 (маркетинговая версия NVIDIA)."""
    parts = [p for p in wddm.split(".") if p.isdigit()]
    if len(parts) < 4:
        return None
    digits = "".join(parts[-2:])
    if len(digits) < 5:
        return None
    last5 = digits[-5:]
    return f"{last5[:3]}.{last5[3:]}"


def _version_tuple(version: str) -> tuple[int, ...]:
    parts = []
    for chunk in version.replace(",", ".").split("."):
        chunk = "".join(ch for ch in chunk if ch.isdigit())
        parts.append(int(chunk) if chunk else 0)
    return tuple(parts)


def _format_date(value: str) -> str:
    text = (value or "").strip()
    if not text:
        return ""
    for fmt in ("%a %b %d, %Y", "%Y-%m-%d"):
        try:
            return datetime.strptime(text, fmt).strftime("%d.%m.%Y")
        except ValueError:
            continue
    return text


def _nvidia_lookup(device_name: str) -> tuple[str, str] | None:
    try:
        root = ET.fromstring(_http_get(_NVIDIA_LOOKUP, timeout=25))
    except Exception:  # noqa: BLE001
        return None

    target = _normalize(device_name)
    fallback: tuple[str, str] | None = None
    for node in root.iter("LookupValue"):
        name = (node.findtext("Name") or "").strip()
        value = (node.findtext("Value") or "").strip()
        parent = node.get("ParentID") or ""
        if not name or not value or not parent:
            continue
        normalized = _normalize(name)
        if normalized == target:
            return (parent, value)
        if fallback is None and (target in normalized or normalized in target):
            fallback = (parent, value)
    return fallback


def _nvidia_latest(psid: str, pfid: str) -> dict | None:
    data = json.loads(_http_get(_NVIDIA_DRIVER.format(psid=psid, pfid=pfid), timeout=25))
    items = data.get("IDS") or []
    if not items:
        return None
    info = items[0].get("downloadInfo") or {}
    if not info.get("Version"):
        return None
    return info


def latest_nvidia_driver(device_name: str, installed_wddm: str) -> VendorDriverInfo:
    installed = _nvidia_marketing_version(installed_wddm) or installed_wddm
    lookup = _nvidia_lookup(device_name)
    if not lookup:
        return VendorDriverInfo(
            "NVIDIA", device_name, installed, "—", "", "", False,
            "не удалось сопоставить модель с сайтом NVIDIA",
        )
    psid, pfid = lookup
    try:
        info = _nvidia_latest(psid, pfid)
    except Exception as exc:  # noqa: BLE001
        return VendorDriverInfo(
            "NVIDIA", device_name, installed, "—", "", "", False,
            f"ошибка запроса к NVIDIA: {exc}",
        )
    if not info:
        return VendorDriverInfo(
            "NVIDIA", device_name, installed, "—", "", "", False,
            "NVIDIA не вернула данные о драйвере",
        )
    latest = str(info.get("Version") or "")
    update = _version_tuple(latest) > _version_tuple(installed)
    return VendorDriverInfo(
        vendor="NVIDIA",
        device=device_name,
        installed=installed,
        latest=latest,
        release_date=_format_date(str(info.get("ReleaseDateTime") or "")),
        url=str(info.get("DetailsURL") or ""),
        update_available=update,
        note="" if update else "установлена последняя версия",
        download_url=str(info.get("DownloadURL") or ""),
    )


def check_gpu_drivers(displays: list[DriverInfo]) -> list[VendorDriverInfo]:
    """Проверяет видеодрайверы на сайтах производителей (где это возможно)."""
    results: list[VendorDriverInfo] = []
    for driver in displays:
        name = driver.name
        low = name.lower()
        if "nvidia" in low:
            results.append(latest_nvidia_driver(name, driver.version))
        elif "amd" in low or "radeon" in low:
            results.append(
                VendorDriverInfo(
                    "AMD", name, driver.version, "—", "", _VENDOR_SITES["AMD"], False,
                    "автопроверка недоступна — откройте сайт AMD",
                )
            )
        elif "intel" in low:
            results.append(
                VendorDriverInfo(
                    "Intel", name, driver.version, "—", "", _VENDOR_SITES["Intel"], False,
                    "автопроверка недоступна — откройте сайт Intel",
                )
            )
        else:
            results.append(
                VendorDriverInfo("—", name, driver.version, "—", "", "", False, "")
            )
    return results


# ---------------------------------------------------------------------------
# Установка обновлений
# ---------------------------------------------------------------------------
_INSTALL_WU_SCRIPT = r"""
$ErrorActionPreference = 'Stop'
$session = New-Object -ComObject Microsoft.Update.Session
$searcher = $session.CreateUpdateSearcher()
$result = $searcher.Search("IsInstalled=0 and Type='Driver'")
if ($result.Updates.Count -eq 0) { 'NONE'; exit 0 }
$coll = New-Object -ComObject Microsoft.Update.UpdateColl
foreach ($u in $result.Updates) { [void]$coll.Add($u) }
$downloader = $session.CreateUpdateDownloader()
$downloader.Updates = $coll
[void]$downloader.Download()
$installer = $session.CreateUpdateInstaller()
$installer.Updates = $coll
$r = $installer.Install()
[ordered]@{
    resultCode     = [int]$r.ResultCode
    rebootRequired = [bool]$r.RebootRequired
    count          = [int]$coll.Count
} | ConvertTo-Json -Compress
"""


def install_windows_driver_updates(progress=None) -> tuple[bool, str]:
    """Скачивает и устанавливает доступные драйверы через Windows Update."""
    if progress:
        progress(5, "Поиск и загрузка обновлений Windows…")
    proc = run_powershell(_INSTALL_WU_SCRIPT, timeout=2400)
    text = (proc.stdout or "").strip().lstrip("\ufeff")

    if text.startswith("NONE") or (not text and proc.returncode == 0):
        return False, "Обновления драйверов Windows Update не найдены."

    try:
        data = json.loads(text)
    except ValueError:
        message = (proc.stderr or text or "Не удалось установить обновления.").strip()
        return False, message

    try:
        code = int(data.get("resultCode", -1))
    except (TypeError, ValueError):
        code = -1
    reboot = bool(data.get("rebootRequired"))

    if code in (2, 3):
        message = "Обновления драйверов установлены."
        if code == 3:
            message += " Часть — с ошибками."
        if reboot:
            message += " Требуется перезагрузка."
        return True, message
    return False, f"Установка не удалась (код {code})."


def _download_file(url: str, dest: str, progress=None) -> None:
    request = urllib.request.Request(
        url, headers={"User-Agent": "Mozilla/5.0 (OptimizerGame)"}
    )
    with urllib.request.urlopen(request, timeout=60) as response:
        total = int(response.headers.get("Content-Length") or 0)
        downloaded = 0
        with open(dest, "wb") as handle:
            while True:
                chunk = response.read(1024 * 512)
                if not chunk:
                    break
                handle.write(chunk)
                downloaded += len(chunk)
                if progress and total:
                    percent = min(int(downloaded / total * 90), 90)
                    progress(percent, f"Загрузка драйвера… {downloaded * 100 // total}%")


def install_nvidia_driver(download_url: str, progress=None) -> tuple[bool, str]:
    """Скачивает установщик NVIDIA и запускает тихую установку."""
    if not download_url:
        return False, "Не удалось получить ссылку на драйвер NVIDIA."

    dest = os.path.join(tempfile.gettempdir(), "optimizer_nvidia_driver.exe")
    if progress:
        progress(1, "Загрузка драйвера NVIDIA…")
    try:
        _download_file(download_url, dest, progress)
    except Exception as exc:  # noqa: BLE001
        return False, f"Ошибка загрузки драйвера: {exc}"

    if progress:
        progress(92, "Установка драйвера NVIDIA (может занять несколько минут)…")
    try:
        proc = subprocess.run(
            [dest, "-s", "-noreboot"],
            timeout=2400,
            creationflags=CREATE_NO_WINDOW,
        )
    except subprocess.TimeoutExpired:
        return False, "Установка драйвера заняла слишком много времени."
    except Exception as exc:  # noqa: BLE001
        return False, f"Не удалось запустить установщик: {exc}"
    finally:
        try:
            os.remove(dest)
        except OSError:
            pass

    if proc.returncode == 0:
        return True, "Драйвер NVIDIA установлен. Может потребоваться перезагрузка."
    return False, f"Установщик NVIDIA завершился с кодом {proc.returncode}."


# ---------------------------------------------------------------------------
# Материнская плата и устройства без драйверов
# ---------------------------------------------------------------------------
_BASEBOARD_SCRIPT = r"""
$ErrorActionPreference = 'SilentlyContinue'
$b = Get-CimInstance Win32_BaseBoard | Select-Object -First 1
$c = Get-CimInstance Win32_Processor | Select-Object -First 1
[ordered]@{
    manufacturer = "$($b.Manufacturer)"
    product      = "$($b.Product)"
    cpu          = "$($c.Manufacturer)"
    cpuName      = "$($c.Name)"
} | ConvertTo-Json -Compress
"""

_PROBLEM_SCRIPT = r"""
$ErrorActionPreference = 'SilentlyContinue'
$items = Get-PnpDevice | Where-Object { $_.Present -eq $true -and $_.Status -ne 'OK' } | ForEach-Object {
    $hw = ''
    if ($_.HardwareID) { $hw = "$($_.HardwareID[0])" }
    [ordered]@{
        name        = "$($_.FriendlyName)"
        status      = "$($_.Status)"
        deviceClass = "$($_.Class)"
        instanceId  = "$($_.InstanceID)"
        hardwareId  = $hw
    }
}
$items | ConvertTo-Json -Depth 3 -Compress
"""


def catalog_search_url(hardware_id: str) -> str:
    """Ссылка на поиск драйвера в каталоге обновлений Microsoft."""
    query = (hardware_id or "").strip()
    return "https://www.catalog.update.microsoft.com/Search.aspx?q=" + quote_plus(query)


_AMD_CHIPSETS = (
    "A620", "B650", "X670", "X870", "B840", "B850", "TRX", "WRX",
    "A520", "B550", "X570", "B450", "X470",
)
_INTEL_CHIPSETS = (
    "H610", "B660", "B760", "B860", "H770", "Z690", "Z790", "Z890",
    "H610E", "W680", "W790",
)


def _mobo_slug(product: str) -> str:
    text = re.sub(r"\(rev[^)]*\)", "", product or "", flags=re.IGNORECASE)
    text = re.sub(r"\(.*?\)", "", text)
    return re.sub(r"\s+", " ", text).strip()


def _platform_from_product(product: str, cpu_manufacturer: str = "") -> str:
    text = (product or "").upper()
    if any(chip in text for chip in _AMD_CHIPSETS):
        return "AMD"
    if any(chip in text for chip in _INTEL_CHIPSETS):
        return "Intel"
    low = (cpu_manufacturer or "").lower()
    if "amd" in low:
        return "AMD"
    if "intel" in low:
        return "Intel"
    return ""


def _search_url(manufacturer: str, product: str) -> str:
    query = quote_plus(f"{manufacturer} {product} драйверы скачать")
    return f"https://duckduckgo.com/?q={query}"


def _vendor_url(manufacturer: str, product: str, platform: str) -> str:
    """Прямая ссылка на страницу драйверов платы у производителя."""
    m = (manufacturer or "").lower()
    slug = _mobo_slug(product)
    dash = slug.replace(" ", "-")
    if "gigabyte" in m:
        return f"https://www.gigabyte.com/Motherboard/{dash}/support#support-dl-driver"
    if "msi" in m or "micro-star" in m:
        return f"https://www.msi.com/Motherboard/{dash}/support#driver"
    if "asrock" in m:
        segment = f"{platform}/" if platform else ""
        return f"https://www.asrock.com/mb/{segment}{quote(slug)}/index.asp#Download"
    if "asus" in m:
        return "https://www.asus.com/support/download-center/"
    if "biostar" in m:
        return "https://www.biostar.com.tw/app/en/mb/introduction.php?S_ID=" + quote_plus(slug)
    if "ecs" in m or "elitegroup" in m:
        return "https://www.ecs.com.tw/en/Product/Motherboard"
    return _search_url(manufacturer, product)


def _driver_hints(platform: str, drivers: list[DriverInfo]) -> list[str]:
    """Какие драйверы платы обычно нужно скачать, по установленным устройствам."""
    hints: list[str] = []

    def add(text: str) -> None:
        if text and text not in hints:
            hints.append(text)

    if platform == "AMD":
        add("Чипсет AMD")
    elif platform == "Intel":
        add("Чипсет Intel")
    else:
        add("Чипсет")

    audio_vendor = ""
    lan_vendor = ""
    wifi_vendor = ""
    has_audio = has_lan = has_wifi = has_bt = has_igpu = has_raid = False

    def vendor_of(name: str, options: tuple[str, ...]) -> str:
        for option in options:
            if option.lower() in name:
                return option
        return ""

    for driver in drivers:
        device_class = driver.device_class.upper()
        name = driver.name.lower()
        if device_class == "MEDIA" and "nvidia" not in name:
            has_audio = True
            audio_vendor = audio_vendor or vendor_of(name, ("Realtek", "Conexant", "Creative"))
        elif device_class == "NET":
            if any(k in name for k in ("wi-fi", "wifi", "wireless", "802.11")):
                has_wifi = True
                wifi_vendor = wifi_vendor or vendor_of(name, ("MediaTek", "Intel", "Realtek", "AMD"))
            elif any(k in name for k in ("ethernet", "lan", "gbe", "gigabit")):
                has_lan = True
                lan_vendor = lan_vendor or vendor_of(name, ("Realtek", "Intel", "Killer", "Marvell"))
        elif device_class == "BLUETOOTH":
            has_bt = True
        elif device_class == "DISPLAY" and any(k in name for k in ("radeon", "amd", "intel", "uhd", "iris")):
            has_igpu = True
        elif device_class in ("SCSIADAPTER", "HDC") and "raid" in name:
            has_raid = True

    if has_audio:
        add(f"Аудио ({audio_vendor})" if audio_vendor else "Аудио")
    if has_lan:
        add(f"Сеть LAN ({lan_vendor})" if lan_vendor else "Сеть LAN")
    if has_wifi:
        add(f"Wi-Fi ({wifi_vendor})" if wifi_vendor else "Wi-Fi")
    if has_bt:
        add("Bluetooth")
    if has_igpu:
        add("Встроенная графика")
    if has_raid:
        add("SATA/RAID контроллер")
    return hints


def motherboard_driver_info(drivers: list[DriverInfo] | None = None) -> MotherboardDriverInfo:
    """Производитель/модель материнской платы, ссылка на драйверы и список нужных.

    ``drivers`` — уже прочитанный список драйверов (для подсказок по устройствам).
    """
    try:
        data = powershell_json(_BASEBOARD_SCRIPT, timeout=30) or {}
    except Exception:  # noqa: BLE001
        data = {}
    if not isinstance(data, dict):
        data = {}
    manufacturer = str(data.get("manufacturer") or "—").strip() or "—"
    product = str(data.get("product") or "—").strip() or "—"
    cpu = str(data.get("cpu") or "")
    platform = _platform_from_product(product, cpu)
    hints = _driver_hints(platform, drivers or [])
    return MotherboardDriverInfo(
        manufacturer=manufacturer,
        product=product,
        url=_vendor_url(manufacturer, product, platform),
        search_url=_search_url(manufacturer, product),
        platform=platform,
        hints=hints,
    )


# Виртуальные и служебные устройства: у них статус с ошибкой — обычное дело,
# и «драйверы» для них искать не нужно.
_VIRTUAL_NAME_HINTS = (
    "virtual adapter",
    "virtual wifi",
    "wi-fi direct",
    "wireless virtual",
    "wan miniport",
    "kernel debug",
    "teredo",
    "6to4",
    "isatap",
    "virtual switch",
    "remote ndis",
    "ndis virtual",
)
_VIRTUAL_HWID_HINTS = ("vwifimp", "ms_agile", "ms_ndisuio", "root\\kdnic")
_BENIGN_CLASSES = {"SOFTWAREDEVICE"}


def _is_benign_problem(device: ProblemDevice) -> bool:
    """Виртуальное/служебное устройство, для которого драйвер не требуется."""
    name = device.name.lower()
    hwid = (device.hardware_id or "").lower()
    device_class = (device.device_class or "").upper()

    if device_class in _BENIGN_CLASSES:
        return True
    if any(hint in name for hint in _VIRTUAL_NAME_HINTS):
        return True
    if any(hint in hwid for hint in _VIRTUAL_HWID_HINTS):
        return True
    if hwid.startswith("{") or hwid.startswith("root\\"):
        return True
    return False


def _read_problem_devices() -> list[ProblemDevice]:
    try:
        data = powershell_json(_PROBLEM_SCRIPT, timeout=60)
    except Exception:  # noqa: BLE001
        return []
    devices: list[ProblemDevice] = []
    for entry in as_list(data):
        if not isinstance(entry, dict):
            continue
        name = str(entry.get("name") or "").strip()
        if not name:
            continue
        devices.append(
            ProblemDevice(
                name=name,
                status=str(entry.get("status") or "—"),
                device_class=str(entry.get("deviceClass") or "—"),
                instance_id=str(entry.get("instanceId") or "—"),
                hardware_id=str(entry.get("hardwareId") or ""),
            )
        )
    return devices


def problem_devices() -> list[ProblemDevice]:
    """Устройства без драйвера, без виртуальных и служебных."""
    return [d for d in _read_problem_devices() if not _is_benign_problem(d)]


def problem_devices_split() -> tuple[list[ProblemDevice], int]:
    """Список устройств без драйвера и сколько виртуальных/служебных скрыто."""
    raw = _read_problem_devices()
    visible = [d for d in raw if not _is_benign_problem(d)]
    return visible, len(raw) - len(visible)
