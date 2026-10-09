"""Твики реестра и сети.

Каждый твик описывается декларативно (:class:`RegWrite` / :class:`ServiceChange`)
либо кастомными функциями. Перед применением оригинальные значения сохраняются
в ``%APPDATA%\\OptimizerGame\\tweak_backup.json``, поэтому откат восстанавливает
систему в исходное состояние.
"""
from __future__ import annotations

import os
import re
from dataclasses import dataclass, field
from typing import Any, Callable

from ..config import TWEAK_BACKUP_FILE, load_json, save_json
from ..utils import as_list, powershell_json, run_command, run_powershell
from . import registry, services

RISK_LABELS = {"low": "Низкий", "medium": "Средний", "high": "Высокий"}

# Сопоставление терминов Set-Service и CIM StartMode.
_MODE_TO_CIM = {"Automatic": "Auto", "Manual": "Manual", "Disabled": "Disabled", "Boot": "Boot", "System": "System"}


@dataclass
class RegWrite:
    hive: str
    path: str
    name: str
    type: str
    value: Any


@dataclass
class ServiceChange:
    name: str
    start_mode: str  # Automatic | Manual | Disabled


@dataclass
class Tweak:
    key: str
    name: str
    description: str
    category: str
    risk: str = "low"
    requires_admin: bool = False
    writes: list[RegWrite] = field(default_factory=list)
    services: list[ServiceChange] = field(default_factory=list)
    apply_fn: Callable[[], tuple[bool, str]] | None = None
    revert_fn: Callable[[], tuple[bool, str]] | None = None
    is_applied_fn: Callable[[dict[str, str]], bool] | None = None

    @property
    def risk_label(self) -> str:
        return RISK_LABELS.get(self.risk, self.risk)


# ---------------------------------------------------------------------------
# Резервные копии
# ---------------------------------------------------------------------------
def _encode(value: Any) -> Any:
    if isinstance(value, (bytes, bytearray)):
        return {"__bytes__": bytes(value).hex()}
    return {"value": value}


def _decode(encoded: Any) -> Any:
    if isinstance(encoded, dict) and "__bytes__" in encoded:
        return bytes.fromhex(encoded["__bytes__"])
    if isinstance(encoded, dict):
        return encoded.get("value")
    return encoded


def _load_backup() -> dict:
    data = load_json(TWEAK_BACKUP_FILE, {})
    return data if isinstance(data, dict) else {}


def _save_backup(data: dict) -> None:
    save_json(TWEAK_BACKUP_FILE, data)


# ---------------------------------------------------------------------------
# Применение и откат
# ---------------------------------------------------------------------------
def _capture_backup(tweak: Tweak, mode_map: dict[str, str]) -> None:
    backup = _load_backup()
    if tweak.key in backup:
        return
    writes_backup = []
    for write in tweak.writes:
        exists, data_type, value = registry.read_value(write.hive, write.path, write.name)
        writes_backup.append(
            {
                "hive": write.hive,
                "path": write.path,
                "name": write.name,
                "exists": exists,
                "data_type": data_type,
                "data": _encode(value) if exists else None,
            }
        )
    services_backup = [
        {"name": change.name, "start_mode": mode_map.get(change.name)}
        for change in tweak.services
    ]
    backup[tweak.key] = {"writes": writes_backup, "services": services_backup}
    _save_backup(backup)


def apply_tweak(tweak: Tweak, mode_map: dict[str, str] | None = None) -> tuple[bool, str]:
    if tweak.apply_fn is not None:
        return tweak.apply_fn()

    mode_map = mode_map or {}
    _capture_backup(tweak, mode_map)

    errors: list[str] = []
    for write in tweak.writes:
        try:
            registry.write_value(write.hive, write.path, write.name, write.type, write.value)
        except OSError as exc:
            errors.append(f"{write.name}: {exc}")

    for change in tweak.services:
        ok, message = services.set_start_mode(change.name, change.start_mode)
        if not ok:
            errors.append(f"{change.name}: {message}")

    if errors:
        return False, "Частично применено. " + "; ".join(errors)
    return True, "Применено"


def revert_tweak(tweak: Tweak) -> tuple[bool, str]:
    if tweak.revert_fn is not None:
        return tweak.revert_fn()

    backup = _load_backup()
    entry = backup.get(tweak.key)
    if entry is None:
        # Нет резервной копии: удаляем созданные значения (простейший откат).
        for write in tweak.writes:
            registry.delete_value(write.hive, write.path, write.name)
        return True, "Значения сброшены"

    errors: list[str] = []
    for write in entry.get("writes", []):
        try:
            if write.get("exists"):
                registry.write_value(
                    write["hive"],
                    write["path"],
                    write["name"],
                    write["data_type"],
                    _decode(write.get("data")),
                )
            else:
                registry.delete_value(write["hive"], write["path"], write["name"])
        except (OSError, KeyError) as exc:
            errors.append(f"{write.get('name')}: {exc}")

    for svc in entry.get("services", []):
        original = svc.get("start_mode")
        if original and original in _MODE_TO_CIM:
            ok, message = services.set_start_mode(svc["name"], _MODE_TO_CIM[original])
            if not ok:
                errors.append(f"{svc['name']}: {message}")

    backup.pop(tweak.key, None)
    _save_backup(backup)

    if errors:
        return False, "Частично откачено. " + "; ".join(errors)
    return True, "Откачено"


# ---------------------------------------------------------------------------
# Проверка состояния
# ---------------------------------------------------------------------------
def _values_match(write: RegWrite) -> bool:
    exists, _data_type, value = registry.read_value(write.hive, write.path, write.name)
    if not exists:
        return False
    return value == write.value


def _is_applied(tweak: Tweak, mode_map: dict[str, str]) -> bool:
    if tweak.is_applied_fn is not None:
        return tweak.is_applied_fn(mode_map)
    if not tweak.writes and not tweak.services:
        return False
    for write in tweak.writes:
        if not _values_match(write):
            return False
    for change in tweak.services:
        current = mode_map.get(change.name)
        if current and current != _MODE_TO_CIM.get(change.start_mode, change.start_mode):
            return False
    return True


def evaluate_applied(tweaks: list[Tweak]) -> dict[str, bool]:
    need_services = any(t.services for t in tweaks)
    mode_map: dict[str, str] = {}
    if need_services:
        try:
            mode_map = {s.name: s.start_mode for s in services.list_services()}
        except Exception:  # noqa: BLE001
            mode_map = {}
    return {tweak.key: _is_applied(tweak, mode_map) for tweak in tweaks}


# ---------------------------------------------------------------------------
# Кастомные твики
# ---------------------------------------------------------------------------
_NET_INTERFACES = r"SYSTEM\CurrentControlSet\Services\Tcpip\Parameters\Interfaces"


def _interface_keys() -> list[str]:
    return [f"{_NET_INTERFACES}\\{guid}" for guid in registry.list_subkeys("HKLM", _NET_INTERFACES)]


def _nagle_apply() -> tuple[bool, str]:
    interfaces = _interface_keys()
    if not interfaces:
        return False, "Сетевые интерфейсы не найдены"
    for path in interfaces:
        registry.write_value("HKLM", path, "TcpAckFrequency", "REG_DWORD", 1)
        registry.write_value("HKLM", path, "TCPNoDelay", "REG_DWORD", 1)
    return True, f"Применено к интерфейсам: {len(interfaces)}"


def _nagle_revert() -> tuple[bool, str]:
    for path in _interface_keys():
        registry.delete_value("HKLM", path, "TcpAckFrequency")
        registry.delete_value("HKLM", path, "TCPNoDelay")
    return True, "Откачено"


def _nagle_applied(_mode_map: dict[str, str]) -> bool:
    interfaces = _interface_keys()
    if not interfaces:
        return False
    return all(
        registry.read_value("HKLM", path, "TcpAckFrequency")[0]
        and registry.read_value("HKLM", path, "TCPNoDelay")[0]
        for path in interfaces
    )


_HIBER_FILE = os.path.join(os.environ.get("SystemDrive", "C:") + "\\", "hiberfil.sys")


def _hibernation_apply() -> tuple[bool, str]:
    code, output = run_command("powercfg /h off", timeout=60)
    if code == 0:
        return True, "Гибернация отключена"
    return False, output or "Не удалось отключить гибернацию"


def _hibernation_revert() -> tuple[bool, str]:
    code, output = run_command("powercfg /h on", timeout=60)
    if code == 0:
        return True, "Гибернация включена"
    return False, output or "Не удалось включить гибернацию"


def _hibernation_applied(_mode_map: dict[str, str]) -> bool:
    return not os.path.exists(_HIBER_FILE)


# ---------------------------------------------------------------------------
# Задачи планировщика (телеметрия)
# ---------------------------------------------------------------------------
_TELEMETRY_TASKS = [
    "Microsoft\\Windows\\Application Experience\\Microsoft Compatibility Appraiser",
    "Microsoft\\Windows\\Application Experience\\ProgramDataUpdater",
    "Microsoft\\Windows\\Customer Experience Improvement Program\\Consolidator",
    "Microsoft\\Windows\\Customer Experience Improvement Program\\UsbCeip",
    "Microsoft\\Windows\\Feedback\\Siuf\\DmClient",
    "Microsoft\\Windows\\Feedback\\Siuf\\DmClientOnScenarioDownload",
]


def _task_parts(full_name: str) -> tuple[str, str]:
    parts = full_name.split("\\")
    return "\\" + "\\".join(parts[:-1]) + "\\", parts[-1]


def _telemetry_tasks_apply() -> tuple[bool, str]:
    changed = 0
    for name in _TELEMETRY_TASKS:
        code, _output = run_command(f'schtasks /Change /TN "{name}" /Disable', timeout=30)
        if code == 0:
            changed += 1
    if changed:
        return True, f"Отключено задач: {changed} из {len(_TELEMETRY_TASKS)}"
    return False, "Не удалось изменить задачи"


def _telemetry_tasks_revert() -> tuple[bool, str]:
    changed = 0
    for name in _TELEMETRY_TASKS:
        code, _output = run_command(f'schtasks /Change /TN "{name}" /Enable', timeout=30)
        if code == 0:
            changed += 1
    if changed:
        return True, f"Включено задач: {changed} из {len(_TELEMETRY_TASKS)}"
    return False, "Не удалось изменить задачи"


def _telemetry_tasks_applied(_mode_map: dict[str, str]) -> bool:
    commands = []
    for name in _TELEMETRY_TASKS:
        path, leaf = _task_parts(name)
        commands.append(
            f"$t = Get-ScheduledTask -TaskPath '{path}' -TaskName '{leaf}' -ErrorAction SilentlyContinue; "
            "if ($t) { $s += $t.State }"
        )
    script = "$s = @(); " + " ".join(commands) + "; $s | ConvertTo-Json -Compress"
    try:
        data = powershell_json(script, timeout=60)
    except Exception:  # noqa: BLE001
        return False
    states = [str(item) for item in as_list(data)]
    if not states:
        return False
    return all(state == "Disabled" for state in states)


# ---------------------------------------------------------------------------
# NTFS (fsutil) и схема питания
# ---------------------------------------------------------------------------
_GUID_RE = re.compile(
    r"[0-9a-fA-F]{8}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{12}"
)
_HIGH_PERFORMANCE_SCHEME = "8c5e7fda-e8bf-4a96-9a85-a6e23a8c635c"
_BALANCED_SCHEME = "381b4222-f694-41f0-9685-ff5bb260df2e"
_POWER_BACKUP_FILE = "power_scheme_backup.json"


def _fsutil_set(setting: str, value: int, success: str, failure: str) -> tuple[bool, str]:
    code, output = run_command(f"fsutil behavior set {setting} {value}", timeout=30)
    if code == 0:
        return True, success
    return False, output or failure


def _fsutil_is(setting: str) -> bool:
    code, output = run_command(f"fsutil behavior query {setting}", timeout=30)
    if code != 0:
        return False
    return "= 1" in output


def _active_power_scheme() -> str | None:
    code, output = run_command("powercfg /getactivescheme", timeout=30)
    if code != 0:
        return None
    match = _GUID_RE.search(output)
    return match.group(0) if match else None


def _power_high_apply() -> tuple[bool, str]:
    current = _active_power_scheme()
    if current:
        save_json(_POWER_BACKUP_FILE, {"previous": current})
    code, output = run_command("powercfg /setactive SCHEME_MIN", timeout=30)
    if code == 0:
        return True, "Включена схема «Высокая производительность»"
    return False, output or "Не удалось изменить схему питания"


def _power_high_revert() -> tuple[bool, str]:
    data = load_json(_POWER_BACKUP_FILE, {})
    previous = data.get("previous") or _BALANCED_SCHEME
    code, output = run_command(f"powercfg /setactive {previous}", timeout=30)
    if code == 0:
        return True, "Исходная схема питания восстановлена"
    return False, output or "Не удалось восстановить схему питания"


def _power_high_applied(_mode_map: dict[str, str]) -> bool:
    current = _active_power_scheme()
    return bool(current) and current.lower() == _HIGH_PERFORMANCE_SCHEME


# ---------------------------------------------------------------------------
# Протоколы: SMBv1, NetBIOS, переходные технологии IPv6
# ---------------------------------------------------------------------------
_NETBT_INTERFACES = r"SYSTEM\CurrentControlSet\Services\NetBT\Parameters\Interfaces"


def _optional_feature_state(name: str) -> str:
    try:
        proc = run_powershell(
            f"(Get-WindowsOptionalFeature -Online -FeatureName {name}).State", timeout=120
        )
    except Exception:  # noqa: BLE001
        return ""
    return (proc.stdout or "").strip()


def _feature_cmd(feature: str, verb: str, done: str, failed: str) -> tuple[bool, str]:
    proc = run_powershell(
        f"{verb}-WindowsOptionalFeature -Online -FeatureName {feature} -NoRestart "
        "-ErrorAction Stop; 'OK'",
        timeout=300,
    )
    if proc.returncode == 0:
        return True, done
    return False, (proc.stderr or proc.stdout or "").strip() or failed


def _smb1_apply() -> tuple[bool, str]:
    return _feature_cmd(
        "SMB1Protocol", "Disable", "SMBv1 отключён (может потребоваться перезагрузка)", "Не удалось отключить SMBv1"
    )


def _smb1_revert() -> tuple[bool, str]:
    return _feature_cmd(
        "SMB1Protocol", "Enable", "SMBv1 включён (может потребоваться перезагрузка)", "Не удалось включить SMBv1"
    )


def _smb1_applied(_mode_map: dict[str, str]) -> bool:
    return _optional_feature_state("SMB1Protocol") == "Disabled"


def _netbios_keys() -> list[str]:
    return [f"{_NETBT_INTERFACES}\\{guid}" for guid in registry.list_subkeys("HKLM", _NETBT_INTERFACES)]


def _netbios_apply() -> tuple[bool, str]:
    keys = _netbios_keys()
    if not keys:
        return False, "Интерфейсы NetBIOS не найдены"
    for path in keys:
        registry.write_value("HKLM", path, "NetbiosOptions", "REG_DWORD", 2)
    return True, f"NetBIOS отключён на интерфейсах: {len(keys)}"


def _netbios_revert() -> tuple[bool, str]:
    for path in _netbios_keys():
        registry.delete_value("HKLM", path, "NetbiosOptions")
    return True, "NetBIOS включён"


def _netbios_applied(_mode_map: dict[str, str]) -> bool:
    keys = _netbios_keys()
    if not keys:
        return False
    return all(registry.read_value("HKLM", path, "NetbiosOptions")[0] for path in keys)


def _ipv6_transition_apply() -> tuple[bool, str]:
    commands = [
        "netsh interface teredo set state disabled",
        "netsh interface 6to4 set state disabled",
        "netsh interface isatap set state disabled",
    ]
    ok = True
    for command in commands:
        code, _output = run_command(command, timeout=30)
        ok = ok and code == 0
    if ok:
        return True, "Переходные технологии IPv6 отключены"
    return False, "Не удалось применить часть команд"


def _ipv6_transition_revert() -> tuple[bool, str]:
    for command in (
        "netsh interface teredo set state default",
        "netsh interface 6to4 set state default",
        "netsh interface isatap set state default",
    ):
        run_command(command, timeout=30)
    return True, "Переходные технологии IPv6 включены"


def _ipv6_transition_applied(_mode_map: dict[str, str]) -> bool:
    code, output = run_command("netsh interface teredo show state", timeout=30)
    return code == 0 and "disabled" in output.lower()


# ---------------------------------------------------------------------------
# Набор твиков
# ---------------------------------------------------------------------------
def build_tweaks() -> list[Tweak]:
    return [
        Tweak(
            key="telemetry",
            name="Отключить телеметрию",
            description="Запрещает сбор диагностических данных и отключает службы телеметрии.",
            category="Конфиденциальность",
            risk="low",
            requires_admin=True,
            writes=[
                RegWrite(
                    "HKLM",
                    r"SOFTWARE\Policies\Microsoft\Windows\DataCollection",
                    "AllowTelemetry",
                    "REG_DWORD",
                    0,
                ),
                RegWrite(
                    "HKLM",
                    r"SOFTWARE\Microsoft\Windows\CurrentVersion\Policies\DataCollection",
                    "AllowTelemetry",
                    "REG_DWORD",
                    0,
                ),
            ],
            services=[
                ServiceChange("DiagTrack", "Disabled"),
                ServiceChange("dmwappushservice", "Disabled"),
            ],
        ),
        Tweak(
            key="visual_effects",
            name="Максимальное быстродействие",
            description="Отключает анимации и визуальные эффекты Windows.",
            category="Интерфейс",
            risk="low",
            writes=[
                RegWrite(
                    "HKCU",
                    r"Software\Microsoft\Windows\CurrentVersion\Explorer\VisualEffects",
                    "VisualFXSetting",
                    "REG_DWORD",
                    2,
                )
            ],
        ),
        Tweak(
            key="menu_show_delay",
            name="Ускорить появление меню",
            description="Убирает задержку при раскрытии меню.",
            category="Интерфейс",
            risk="low",
            writes=[
                RegWrite("HKCU", r"Control Panel\Desktop", "MenuShowDelay", "REG_SZ", "0")
            ],
        ),
        Tweak(
            key="startup_delay",
            name="Ускорить запуск приложений",
            description="Отключает искусственную задержку стартовых приложений Explorer.",
            category="Интерфейс",
            risk="low",
            writes=[
                RegWrite(
                    "HKCU",
                    r"Software\Microsoft\Windows\CurrentVersion\Explorer\Serialize",
                    "StartupDelayInMSec",
                    "REG_DWORD",
                    0,
                )
            ],
        ),
        Tweak(
            key="network_throttling",
            name="Отключить сетевой троттлинг",
            description="Отключает ограничение пропускной способности сети для мультимедиа.",
            category="Сеть",
            risk="medium",
            requires_admin=True,
            writes=[
                RegWrite(
                    "HKLM",
                    r"SOFTWARE\Microsoft\Windows NT\CurrentVersion\Multimedia\SystemProfile",
                    "NetworkThrottlingIndex",
                    "REG_DWORD",
                    0xFFFFFFFF,
                ),
                RegWrite(
                    "HKLM",
                    r"SOFTWARE\Microsoft\Windows NT\CurrentVersion\Multimedia\SystemProfile",
                    "SystemResponsiveness",
                    "REG_DWORD",
                    10,
                ),
            ],
        ),
        Tweak(
            key="nagle",
            name="Отключить алгоритм Нейгла",
            description="Снижает задержку в сетевых играх (TcpAckFrequency и TCPNoDelay).",
            category="Сеть",
            risk="medium",
            requires_admin=True,
            apply_fn=_nagle_apply,
            revert_fn=_nagle_revert,
            is_applied_fn=_nagle_applied,
        ),
        Tweak(
            key="hibernation",
            name="Отключить гибернацию",
            description="Освобождает hiberfil.sys и место на системном диске.",
            category="Система",
            risk="medium",
            requires_admin=True,
            apply_fn=_hibernation_apply,
            revert_fn=_hibernation_revert,
            is_applied_fn=_hibernation_applied,
        ),
        Tweak(
            key="game_bar",
            name="Отключить Xbox Game Bar",
            description="Отключает игровую панель, запись клипов (Game DVR) и игровой режим.",
            category="Игры",
            risk="low",
            writes=[
                RegWrite(
                    "HKCU",
                    r"Software\Microsoft\Windows\CurrentVersion\GameDVR",
                    "AppCaptureEnabled",
                    "REG_DWORD",
                    0,
                ),
                RegWrite("HKCU", r"System\GameConfigStore", "GameDVR_Enabled", "REG_DWORD", 0),
                RegWrite("HKCU", r"Software\Microsoft\GameBar", "AutoGameModeEnabled", "REG_DWORD", 0),
                RegWrite("HKCU", r"Software\Microsoft\GameBar", "ShowStartupPanel", "REG_DWORD", 0),
            ],
        ),
        Tweak(
            key="cortana",
            name="Отключить Cortana и поиск Bing",
            description="Запрещает Cortana и подмешивание веб-результатов Bing в поиск.",
            category="Конфиденциальность",
            risk="low",
            requires_admin=True,
            writes=[
                RegWrite(
                    "HKLM",
                    r"SOFTWARE\Policies\Microsoft\Windows\Windows Search",
                    "AllowCortana",
                    "REG_DWORD",
                    0,
                ),
                RegWrite(
                    "HKCU",
                    r"Software\Microsoft\Windows\CurrentVersion\Search",
                    "BingSearchEnabled",
                    "REG_DWORD",
                    0,
                ),
                RegWrite(
                    "HKCU",
                    r"Software\Microsoft\Windows\CurrentVersion\Search",
                    "CortanaConsent",
                    "REG_DWORD",
                    0,
                ),
            ],
        ),
        Tweak(
            key="widgets",
            name="Отключить виджеты",
            description="Убирает панель «Новости и интересы» (виджеты).",
            category="Интерфейс",
            risk="low",
            requires_admin=True,
            writes=[
                RegWrite(
                    "HKLM",
                    r"SOFTWARE\Policies\Microsoft\Dsh",
                    "AllowNewsAndInterests",
                    "REG_DWORD",
                    0,
                ),
            ],
        ),
        Tweak(
            key="taskbar_chat",
            name="Скрыть кнопку чата (Teams)",
            description="Убирает значок чата с панели задач.",
            category="Интерфейс",
            risk="low",
            writes=[
                RegWrite(
                    "HKCU",
                    r"Software\Microsoft\Windows\CurrentVersion\Explorer\Advanced",
                    "TaskbarMn",
                    "REG_DWORD",
                    0,
                ),
            ],
        ),
        Tweak(
            key="show_extensions",
            name="Показывать расширения файлов",
            description="Включает отображение расширений в проводнике.",
            category="Проводник",
            risk="low",
            writes=[
                RegWrite(
                    "HKCU",
                    r"Software\Microsoft\Windows\CurrentVersion\Explorer\Advanced",
                    "HideFileExt",
                    "REG_DWORD",
                    0,
                ),
            ],
        ),
        Tweak(
            key="advertising_id",
            name="Отключить рекламный идентификатор",
            description="Запрещает приложениям использовать идентификатор для рекламы.",
            category="Конфиденциальность",
            risk="low",
            writes=[
                RegWrite(
                    "HKCU",
                    r"Software\Microsoft\Windows\CurrentVersion\AdvertisingInfo",
                    "Enabled",
                    "REG_DWORD",
                    0,
                ),
            ],
        ),
        Tweak(
            key="suggestions",
            name="Отключить советы и предложения",
            description="Убирает рекомендованные приложения и подсказки в меню «Пуск».",
            category="Конфиденциальность",
            risk="low",
            writes=[
                RegWrite(
                    "HKCU",
                    r"Software\Microsoft\Windows\CurrentVersion\ContentDeliveryManager",
                    "SoftLandingEnabled",
                    "REG_DWORD",
                    0,
                ),
                RegWrite(
                    "HKCU",
                    r"Software\Microsoft\Windows\CurrentVersion\ContentDeliveryManager",
                    "SubscribedContent-338388Enabled",
                    "REG_DWORD",
                    0,
                ),
                RegWrite(
                    "HKCU",
                    r"Software\Microsoft\Windows\CurrentVersion\ContentDeliveryManager",
                    "SubscribedContent-338389Enabled",
                    "REG_DWORD",
                    0,
                ),
                RegWrite(
                    "HKCU",
                    r"Software\Microsoft\Windows\CurrentVersion\ContentDeliveryManager",
                    "SystemPaneSuggestionsEnabled",
                    "REG_DWORD",
                    0,
                ),
                RegWrite(
                    "HKCU",
                    r"Software\Microsoft\Windows\CurrentVersion\ContentDeliveryManager",
                    "SilentInstalledAppsEnabled",
                    "REG_DWORD",
                    0,
                ),
            ],
        ),
        Tweak(
            key="feedback",
            name="Отключить запросы отзывов",
            description="Windows перестанет предлагать оставить отзыв.",
            category="Конфиденциальность",
            risk="low",
            writes=[
                RegWrite(
                    "HKCU",
                    r"Software\Microsoft\Siuf\Rules",
                    "NumberOfSIUFInPeriod",
                    "REG_DWORD",
                    0,
                ),
            ],
        ),
        Tweak(
            key="transparency",
            name="Отключить прозрачность",
            description="Убирает эффекты прозрачности интерфейса Windows.",
            category="Интерфейс",
            risk="low",
            writes=[
                RegWrite(
                    "HKCU",
                    r"Software\Microsoft\Windows\CurrentVersion\Themes\Personalize",
                    "EnableTransparency",
                    "REG_DWORD",
                    0,
                ),
            ],
        ),
        Tweak(
            key="dark_mode",
            name="Тёмная тема Windows",
            description="Включает тёмное оформление системы и приложений.",
            category="Интерфейс",
            risk="low",
            writes=[
                RegWrite(
                    "HKCU",
                    r"Software\Microsoft\Windows\CurrentVersion\Themes\Personalize",
                    "AppsUseLightTheme",
                    "REG_DWORD",
                    0,
                ),
                RegWrite(
                    "HKCU",
                    r"Software\Microsoft\Windows\CurrentVersion\Themes\Personalize",
                    "SystemUsesLightTheme",
                    "REG_DWORD",
                    0,
                ),
            ],
        ),
        Tweak(
            key="mouse_accel",
            name="Отключить ускорение мыши",
            description="Отключает «повышенную точность» указателя — ровнее прицел в играх.",
            category="Игры",
            risk="low",
            writes=[
                RegWrite("HKCU", r"Control Panel\Mouse", "MouseSpeed", "REG_SZ", "0"),
                RegWrite("HKCU", r"Control Panel\Mouse", "MouseThreshold1", "REG_SZ", "0"),
                RegWrite("HKCU", r"Control Panel\Mouse", "MouseThreshold2", "REG_SZ", "0"),
            ],
        ),
        Tweak(
            key="power_throttling",
            name="Отключить энерготроттлинг",
            description="Запрещает Windows ограничивать производительность фоновых задач.",
            category="Система",
            risk="medium",
            requires_admin=True,
            writes=[
                RegWrite(
                    "HKLM",
                    r"SYSTEM\CurrentControlSet\Control\Power\PowerThrottling",
                    "PowerThrottlingOff",
                    "REG_DWORD",
                    1,
                ),
            ],
        ),
        Tweak(
            key="fast_shutdown",
            name="Ускорить завершение работы",
            description="Сокращает время ожидания служб при выключении.",
            category="Система",
            risk="medium",
            requires_admin=True,
            writes=[
                RegWrite(
                    "HKLM",
                    r"SYSTEM\CurrentControlSet\Control",
                    "WaitToKillServiceTimeout",
                    "REG_SZ",
                    "2000",
                ),
            ],
        ),
        Tweak(
            key="xbox_services",
            name="Отключить службы Xbox",
            description="Отключает фоновые службы Xbox Live.",
            category="Игры",
            risk="low",
            requires_admin=True,
            services=[
                ServiceChange("XblAuthManager", "Disabled"),
                ServiceChange("XblGameSave", "Disabled"),
                ServiceChange("XboxNetApiSvc", "Disabled"),
            ],
        ),
        Tweak(
            key="wer_service",
            name="Отключить отчёты об ошибках",
            description="Отключает службу Windows Error Reporting.",
            category="Службы",
            risk="low",
            requires_admin=True,
            services=[ServiceChange("WerSvc", "Disabled")],
        ),
        Tweak(
            key="sysmain",
            name="Отключить SysMain (SuperFetch)",
            description="Отключает предзагрузку приложений. Полезно на SSD.",
            category="Службы",
            risk="medium",
            requires_admin=True,
            services=[ServiceChange("SysMain", "Disabled")],
        ),
        Tweak(
            key="wsearch",
            name="Отключить индексацию поиска",
            description="Отключает службу Windows Search. Поиск в «Пуск» станет медленнее.",
            category="Службы",
            risk="medium",
            requires_admin=True,
            services=[ServiceChange("WSearch", "Disabled")],
        ),
        Tweak(
            key="telemetry_tasks",
            name="Отключить задачи телеметрии",
            description="Отключает запланированные задачи сбора диагностических данных.",
            category="Конфиденциальность",
            risk="low",
            requires_admin=True,
            apply_fn=_telemetry_tasks_apply,
            revert_fn=_telemetry_tasks_revert,
            is_applied_fn=_telemetry_tasks_applied,
        ),
        Tweak(
            key="background_apps",
            name="Отключить фоновые приложения",
            description="Запрещает приложениям из Store работать в фоне.",
            category="Производительность",
            risk="low",
            writes=[
                RegWrite(
                    "HKCU",
                    r"Software\Microsoft\Windows\CurrentVersion\BackgroundAccessApplications",
                    "GlobalUserDisabled",
                    "REG_DWORD",
                    1,
                ),
                RegWrite(
                    "HKCU",
                    r"Software\Microsoft\Windows\CurrentVersion\Search",
                    "BackgroundAppGlobalToggle",
                    "REG_DWORD",
                    0,
                ),
            ],
        ),
        Tweak(
            key="activity_history",
            name="Отключить историю действий",
            description="Выключает журнал активности и передачу его в облако.",
            category="Конфиденциальность",
            risk="low",
            requires_admin=True,
            writes=[
                RegWrite("HKLM", r"SOFTWARE\Policies\Microsoft\Windows\System", "EnableActivityFeed", "REG_DWORD", 0),
                RegWrite("HKLM", r"SOFTWARE\Policies\Microsoft\Windows\System", "PublishUserActivities", "REG_DWORD", 0),
                RegWrite("HKLM", r"SOFTWARE\Policies\Microsoft\Windows\System", "UploadUserActivities", "REG_DWORD", 0),
            ],
        ),
        Tweak(
            key="tailored_experiences",
            name="Отключить персонализацию рекламы",
            description="Запрещает использование диагностических данных для персонализации.",
            category="Конфиденциальность",
            risk="low",
            writes=[
                RegWrite(
                    "HKCU",
                    r"Software\Microsoft\Windows\CurrentVersion\Privacy",
                    "TailoredExperiencesWithDiagnosticDataEnabled",
                    "REG_DWORD",
                    0,
                ),
            ],
        ),
        Tweak(
            key="lock_screen_spotlight",
            name="Убрать рекламу с экрана блокировки",
            description="Отключает подсказки и «Windows Spotlight» на экране блокировки.",
            category="Конфиденциальность",
            risk="low",
            writes=[
                RegWrite(
                    "HKCU",
                    r"Software\Microsoft\Windows\CurrentVersion\ContentDeliveryManager",
                    "RotatingLockScreenOverlayEnabled",
                    "REG_DWORD",
                    0,
                ),
                RegWrite(
                    "HKCU",
                    r"Software\Microsoft\Windows\CurrentVersion\ContentDeliveryManager",
                    "SubscribedContent-338387Enabled",
                    "REG_DWORD",
                    0,
                ),
            ],
        ),
        Tweak(
            key="start_recommendations",
            name="Убрать рекомендованное в «Пуск»",
            description="Скрывает недавние файлы, программы и рекомендации в меню «Пуск».",
            category="Интерфейс",
            risk="low",
            writes=[
                RegWrite("HKCU", r"Software\Microsoft\Windows\CurrentVersion\Explorer\Advanced", "Start_TrackProgs", "REG_DWORD", 0),
                RegWrite("HKCU", r"Software\Microsoft\Windows\CurrentVersion\Explorer\Advanced", "Start_TrackDocs", "REG_DWORD", 0),
                RegWrite("HKCU", r"Software\Microsoft\Windows\CurrentVersion\Explorer\Advanced", "Start_IrisRecommendations", "REG_DWORD", 0),
            ],
        ),
        Tweak(
            key="search_highlights",
            name="Отключить подсветку поиска",
            description="Убирает динамические подсказки в поле поиска.",
            category="Интерфейс",
            risk="low",
            writes=[
                RegWrite(
                    "HKCU",
                    r"Software\Microsoft\Windows\CurrentVersion\SearchSettings",
                    "IsDynamicSearchBoxEnabled",
                    "REG_DWORD",
                    0,
                ),
            ],
        ),
        Tweak(
            key="copilot",
            name="Отключить Copilot",
            description="Выключает ИИ-помощник Windows Copilot.",
            category="Интерфейс",
            risk="low",
            writes=[
                RegWrite(
                    "HKCU",
                    r"Software\Policies\Microsoft\Windows\WindowsCopilot",
                    "TurnOffWindowsCopilot",
                    "REG_DWORD",
                    1,
                ),
            ],
        ),
        Tweak(
            key="recall",
            name="Отключить Windows Recall",
            description="Запрещает функцию Recall сохранять снимки экрана.",
            category="Конфиденциальность",
            risk="low",
            requires_admin=True,
            writes=[
                RegWrite(
                    "HKLM",
                    r"SOFTWARE\Policies\Microsoft\Windows\WindowsAI",
                    "DisableAIDataAnalysis",
                    "REG_DWORD",
                    1,
                ),
            ],
        ),
        Tweak(
            key="fast_startup",
            name="Отключить быстрый запуск",
            description="Выключает гибридную загрузку (hiberboot) — чище выключение и перезагрузка.",
            category="Система",
            risk="medium",
            requires_admin=True,
            writes=[
                RegWrite(
                    "HKLM",
                    r"SYSTEM\CurrentControlSet\Control\Session Manager\Power",
                    "HiberbootEnabled",
                    "REG_DWORD",
                    0,
                ),
            ],
        ),
        Tweak(
            key="delivery_p2p",
            name="Отключить P2P-раздачу обновлений",
            description="Запрещает отдавать обновления Windows другим компьютерам.",
            category="Сеть",
            risk="low",
            requires_admin=True,
            writes=[
                RegWrite(
                    "HKLM",
                    r"SOFTWARE\Microsoft\Windows\CurrentVersion\DeliveryOptimization\Config",
                    "DODownloadMode",
                    "REG_DWORD",
                    0,
                ),
            ],
        ),
        Tweak(
            key="qos_bandwidth",
            name="Снять резерв сети (QoS)",
            description="Освобождает зарезервированные под QoS 20% пропускной способности.",
            category="Сеть",
            risk="low",
            requires_admin=True,
            writes=[
                RegWrite(
                    "HKLM",
                    r"SOFTWARE\Policies\Microsoft\Windows\Psched",
                    "NonBestEffortLimit",
                    "REG_DWORD",
                    0,
                ),
            ],
        ),
        Tweak(
            key="llmnr",
            name="Отключить LLMNR",
            description="Выключает мультикаст-разрешение имён — меньше сетевого шума и рисков.",
            category="Сеть",
            risk="medium",
            requires_admin=True,
            writes=[
                RegWrite(
                    "HKLM",
                    r"SOFTWARE\Policies\Microsoft\Windows NT\DNSClient",
                    "EnableMulticast",
                    "REG_DWORD",
                    0,
                ),
            ],
        ),
        Tweak(
            key="maintenance",
            name="Отключить автозапуск обслуживания",
            description="Выключает автоматическое обслуживание Windows по расписанию.",
            category="Производительность",
            risk="medium",
            requires_admin=True,
            writes=[
                RegWrite(
                    "HKLM",
                    r"SOFTWARE\Microsoft\Windows NT\CurrentVersion\Schedule\Maintenance",
                    "MaintenanceDisabled",
                    "REG_DWORD",
                    1,
                ),
            ],
        ),
        Tweak(
            key="hide_meet_now",
            name="Скрыть кнопку «Собраться»",
            description="Убирает значок Meet Now с панели задач.",
            category="Интерфейс",
            risk="low",
            requires_admin=True,
            writes=[
                RegWrite(
                    "HKLM",
                    r"SOFTWARE\Microsoft\Windows\CurrentVersion\Policies\Explorer",
                    "HideSCAMeetNow",
                    "REG_DWORD",
                    1,
                ),
            ],
        ),
        Tweak(
            key="snap_assist",
            name="Отключить Snap Assist",
            description="Выключает подсказки при прикреплении окон к краям.",
            category="Интерфейс",
            risk="low",
            writes=[
                RegWrite(
                    "HKCU",
                    r"Software\Microsoft\Windows\CurrentVersion\Explorer\Advanced",
                    "SnapAssist",
                    "REG_DWORD",
                    0,
                ),
            ],
        ),
        Tweak(
            key="rare_services",
            name="Отключить редко используемые службы",
            description="Отключает факс, удалённый реестр, карты, RetailDemo, уведомления принтеров.",
            category="Службы",
            risk="low",
            requires_admin=True,
            services=[
                ServiceChange("Fax", "Disabled"),
                ServiceChange("RemoteRegistry", "Disabled"),
                ServiceChange("MapsBroker", "Disabled"),
                ServiceChange("RetailDemo", "Disabled"),
                ServiceChange("PrintNotify", "Disabled"),
                ServiceChange("WMPNetworkSvc", "Disabled"),
            ],
        ),
        Tweak(
            key="ntfs_last_access",
            name="Отключить запись времени доступа (NTFS)",
            description="Ускоряет работу диска за счёт отказа от метки последнего доступа.",
            category="Производительность",
            risk="low",
            requires_admin=True,
            apply_fn=lambda: _fsutil_set(
                "disablelastaccess", 1, "Запись времени доступа отключена", "Не удалось изменить"
            ),
            revert_fn=lambda: _fsutil_set(
                "disablelastaccess", 0, "Запись времени доступа включена", "Не удалось изменить"
            ),
            is_applied_fn=lambda _m: _fsutil_is("disablelastaccess"),
        ),
        Tweak(
            key="ntfs_8dot3",
            name="Отключить имена 8.3 (NTFS)",
            description="Убирает генерацию коротких имён DOS — меньше нагрузки на диск.",
            category="Производительность",
            risk="low",
            requires_admin=True,
            apply_fn=lambda: _fsutil_set(
                "disable8dot3", 1, "Короткие имена отключены", "Не удалось изменить"
            ),
            revert_fn=lambda: _fsutil_set(
                "disable8dot3", 0, "Короткие имена включены", "Не удалось изменить"
            ),
            is_applied_fn=lambda _m: _fsutil_is("disable8dot3"),
        ),
        Tweak(
            key="high_performance_power",
            name="Схема «Высокая производительность»",
            description="Переключает питание на максимальную производительность (запоминает прежнюю схему).",
            category="Производительность",
            risk="medium",
            requires_admin=True,
            apply_fn=_power_high_apply,
            revert_fn=_power_high_revert,
            is_applied_fn=_power_high_applied,
        ),
        Tweak(
            key="smb1",
            name="Отключить SMBv1",
            description="Убирает устаревший и небезопасный протокол SMB версии 1.",
            category="Протоколы",
            risk="medium",
            requires_admin=True,
            apply_fn=_smb1_apply,
            revert_fn=_smb1_revert,
            is_applied_fn=_smb1_applied,
        ),
        Tweak(
            key="smb_server",
            name="Отключить сервер SMB (общий доступ)",
            description="Выключает службу «Сервер» (LanmanServer) — доступ к вашим папкам по сети.",
            category="Протоколы",
            risk="medium",
            requires_admin=True,
            services=[ServiceChange("LanmanServer", "Disabled")],
        ),
        Tweak(
            key="smb_client",
            name="Отключить клиент SMB",
            description="Выключает службу «Рабочая станция» (LanmanWorkstation). Сетевые папки станут недоступны.",
            category="Протоколы",
            risk="high",
            requires_admin=True,
            services=[ServiceChange("LanmanWorkstation", "Disabled")],
        ),
        Tweak(
            key="netbios_helper",
            name="Отключить службу NetBIOS (TCP/IP Helper)",
            description="Выключает lmhosts — устаревшее разрешение имён NetBIOS.",
            category="Протоколы",
            risk="low",
            requires_admin=True,
            services=[ServiceChange("lmhosts", "Disabled")],
        ),
        Tweak(
            key="netbios_over_tcpip",
            name="Отключить NetBIOS over TCP/IP",
            description="Отключает NetBIOS на всех сетевых интерфейсах — меньше сетевого шума и рисков.",
            category="Протоколы",
            risk="medium",
            requires_admin=True,
            apply_fn=_netbios_apply,
            revert_fn=_netbios_revert,
            is_applied_fn=_netbios_applied,
        ),
        Tweak(
            key="ipv6_transition",
            name="Отключить переходные технологии IPv6",
            description="Выключает Teredo, 6to4 и ISATAP — не нужны при обычном IPv4/IPv6.",
            category="Протоколы",
            risk="low",
            requires_admin=True,
            apply_fn=_ipv6_transition_apply,
            revert_fn=_ipv6_transition_revert,
            is_applied_fn=_ipv6_transition_applied,
        ),
        Tweak(
            key="print_spooler",
            name="Отключить диспетчер печати",
            description="Выключает службу Print Spooler (Spooler). Печать станет недоступна.",
            category="Службы",
            risk="medium",
            requires_admin=True,
            services=[ServiceChange("Spooler", "Disabled")],
        ),
        Tweak(
            key="remote_desktop",
            name="Отключить удалённый рабочий стол",
            description="Выключает TermService — входящие подключения RDP.",
            category="Службы",
            risk="medium",
            requires_admin=True,
            services=[ServiceChange("TermService", "Disabled")],
        ),
        Tweak(
            key="winrm",
            name="Отключить WinRM",
            description="Выключает удалённое управление Windows (Windows Remote Management).",
            category="Службы",
            risk="medium",
            requires_admin=True,
            services=[ServiceChange("WinRM", "Disabled")],
        ),
        Tweak(
            key="ics",
            name="Отключить общий доступ к подключению (ICS)",
            description="Выключает службу SharedAccess — раздачу интернета другим устройствам.",
            category="Службы",
            risk="low",
            requires_admin=True,
            services=[ServiceChange("SharedAccess", "Disabled")],
        ),
        Tweak(
            key="secondary_logon",
            name="Отключить вторичный вход",
            description="Выключает службу seclogon (запуск от другого пользователя).",
            category="Службы",
            risk="low",
            requires_admin=True,
            services=[ServiceChange("seclogon", "Disabled")],
        ),
        Tweak(
            key="tablet_input",
            name="Отключить службу планшета и рукописного ввода",
            description="Выключает TabletInputService — нужно только при сенсорном экране/перьях.",
            category="Службы",
            risk="low",
            requires_admin=True,
            services=[ServiceChange("TabletInputService", "Disabled")],
        ),
        Tweak(
            key="bluetooth",
            name="Отключить службы Bluetooth",
            description="Выключает bthserv — если Bluetooth не используется.",
            category="Службы",
            risk="medium",
            requires_admin=True,
            services=[ServiceChange("bthserv", "Disabled")],
        ),
        Tweak(
            key="biometric",
            name="Отключить биометрию (Windows Hello)",
            description="Выключает WbioSrvc — службу распознавания отпечатков и лица.",
            category="Службы",
            risk="medium",
            requires_admin=True,
            services=[ServiceChange("WbioSrvc", "Disabled")],
        ),
        Tweak(
            key="alljoyn",
            name="Отключить AllJoyn Router",
            description="Выключает AJRouter — маршрутизацию устройств Интернета вещей.",
            category="Службы",
            risk="low",
            requires_admin=True,
            services=[ServiceChange("AJRouter", "Disabled")],
        ),
        Tweak(
            key="prefetch",
            name="Отключить Prefetch/SuperFetch (реестр)",
            description="Убирает предзагрузку приложений на уровне ядра. Полезно на SSD.",
            category="Производительность",
            risk="medium",
            requires_admin=True,
            writes=[
                RegWrite(
                    "HKLM",
                    r"SYSTEM\CurrentControlSet\Control\Session Manager\Memory Management\PrefetchParameters",
                    "EnablePrefetcher",
                    "REG_DWORD",
                    0,
                ),
                RegWrite(
                    "HKLM",
                    r"SYSTEM\CurrentControlSet\Control\Session Manager\Memory Management\PrefetchParameters",
                    "EnableSuperfetch",
                    "REG_DWORD",
                    0,
                ),
            ],
        ),
        Tweak(
            key="priority_separation",
            name="Приоритет активных программ",
            description="Настраивает планировщик на отзывчивость активного приложения.",
            category="Производительность",
            risk="medium",
            requires_admin=True,
            writes=[
                RegWrite(
                    "HKLM",
                    r"SYSTEM\CurrentControlSet\Control\PriorityControl",
                    "Win32PrioritySeparation",
                    "REG_DWORD",
                    38,
                ),
            ],
        ),
    ]
