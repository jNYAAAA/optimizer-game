"""Игровые настройки Windows (питание, HAGS, игровой режим и т. д.).

Значения читаются и записываются в реестр/через powercfg. Часть параметров
требует прав администратора и перезагрузки. Пункт про оптимизации полного
экрана строится для исполняемого файла конкретной игры.
"""
from __future__ import annotations

import os
import re
from dataclasses import dataclass
from pathlib import Path
from typing import Callable

from . import registry
from .games import _library_roots, _steam_roots
from ..utils import run_command

_GUID_RE = re.compile(
    r"[0-9a-fA-F]{8}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{12}"
)
_HIGH = "8c5e7fda-e8bf-4a96-9a85-a6e23a8c635c"
_BALANCED = "381b4222-f694-41f0-9685-ff5bb260df2e"
_ULTIMATE = "e9a42b02-d5df-448d-aa00-03f14749eb61"

_HAGS_KEY = r"SYSTEM\CurrentControlSet\Control\GraphicsDrivers"
_GAMEBAR_KEY = r"Software\Microsoft\GameBar"
_DX_KEY = r"Software\Microsoft\DirectX\UserGpuPreferences"
_LAYERS_KEY = r"Software\Microsoft\Windows NT\CurrentVersion\AppCompatFlags\Layers"

_ON_OFF = [("on", "Вкл"), ("off", "Выкл")]

# Исполняемые файлы игр относительно steamapps\common.
_GAME_EXE = {
    "cs2": ["Counter-Strike Global Offensive/game/bin/win64/cs2.exe"],
    "dota2": ["dota 2 beta/game/bin/win64/dota2.exe"],
    "apex": ["Apex Legends/r5apex.exe"],
    "pubg": ["PUBG/TslGame/Binaries/Win64/TslGame.exe"],
    "squad": ["Squad/SquadGame/Binaries/Win64/SquadGame-Win64-Shipping.exe"],
    "dayz": ["DayZ/DayZ_x64.exe"],
    "gtav": ["Grand Theft Auto V/GTA5.exe"],
    "wardogs": ["Wardogs/Wardogs/Binaries/Win64/WardogsClient-Win64-Shipping.exe"],
    "thefinals": ["The Finals/Discovery/Binaries/Win64/Discovery-Win64-Shipping.exe"],
    "marvelrivals": ["Marvel Rivals/MarvelGame/Binaries/Win64/Marvel-Win64-Shipping.exe"],
    "r6siege": ["Rainbow Six Siege/RainbowSixSiege.exe"],
    "overwatch2": ["Overwatch/Overwatch.exe"],
    "destiny2": ["Destiny 2/destiny2.exe"],
    "tarkov": ["EscapeFromTarkov/EscapeFromTarkov.exe"],
    "rust": ["Rust/RustClient.exe"],
    "rocketleague": ["rocket league/Binaries/Win64/RocketLeague.exe"],
    "seaofthieves": ["Sea of Thieves/Athena/Binaries/Win64/SoTGame-Win64-Shipping.exe"],
}

# Игры вне Steam (Riot / Epic / Battlestate) — типовые пути установки.
_ABSOLUTE_EXE = {
    "valorant": [
        r"C:\Riot Games\VALORANT\live\ShooterGame\Binaries\Win64\VALORANT-Win64-Shipping.exe",
    ],
    "fortnite": [
        r"C:\Program Files\Epic Games\Fortnite\FortniteGame\Binaries\Win64\FortniteClient-Win64-Shipping.exe",
    ],
    "tarkov": [
        r"C:\Battlestate Games\Escape from Tarkov\EscapeFromTarkov.exe",
        r"D:\Battlestate Games\Escape from Tarkov\EscapeFromTarkov.exe",
    ],
}


@dataclass
class WinSetting:
    key: str
    name: str
    help: str
    options: list[tuple[str, str]]
    value: str
    get: Callable[[], str]
    apply: Callable[[str], tuple[bool, str]]
    requires_admin: bool = False
    note: str = ""


def game_exe_path(game_key: str) -> str | None:
    for absolute in _ABSOLUTE_EXE.get(game_key, []):
        candidate = Path(absolute)
        if candidate.is_file():
            return str(candidate)
    rels = _GAME_EXE.get(game_key, [])
    for steam_root in _steam_roots():
        for library in _library_roots(steam_root):
            common = library / "steamapps" / "common"
            for rel in rels:
                candidate = common / rel
                if candidate.is_file():
                    return str(candidate)
    return None


def cs2_exe_path() -> str | None:
    return game_exe_path("cs2")


# ---------------------------------------------------------------------------
# Схема питания
# ---------------------------------------------------------------------------
def _active_scheme() -> str:
    code, output = run_command("powercfg /getactivescheme", timeout=30)
    if code != 0:
        return ""
    match = _GUID_RE.search(output)
    return match.group(0).lower() if match else ""


def _power_get() -> str:
    scheme = _active_scheme()
    if scheme == _HIGH:
        return "high"
    if scheme == _ULTIMATE:
        return "ultimate"
    if scheme == _BALANCED:
        return "balanced"
    return "other"


def _power_apply(value: str) -> tuple[bool, str]:
    if value == "high":
        command = "powercfg /setactive SCHEME_MIN"
    elif value == "balanced":
        command = "powercfg /setactive SCHEME_BALANCED"
    elif value == "ultimate":
        run_command(f"powercfg -duplicatescheme {_ULTIMATE}", timeout=30)
        command = f"powercfg /setactive {_ULTIMATE}"
    else:
        return False, "Неизвестная схема"
    code, output = run_command(command, timeout=30)
    if code == 0:
        return True, "Схема питания изменена"
    return False, output or "Не удалось изменить схему питания"


# ---------------------------------------------------------------------------
# HAGS
# ---------------------------------------------------------------------------
def _hags_get() -> str:
    exists, _type, value = registry.read_value("HKLM", _HAGS_KEY, "HwSchMode")
    if not exists:
        return "off"
    try:
        return "on" if int(value) == 2 else "off"
    except (TypeError, ValueError):
        return "off"


def _hags_apply(value: str) -> tuple[bool, str]:
    try:
        registry.write_value("HKLM", _HAGS_KEY, "HwSchMode", "REG_DWORD", 2 if value == "on" else 1)
    except OSError as exc:
        return False, f"Не удалось записать (нужны права администратора): {exc}"
    return True, "Применено. Требуется перезагрузка."


# ---------------------------------------------------------------------------
# Игровой режим
# ---------------------------------------------------------------------------
def _game_mode_get() -> str:
    exists, _type, value = registry.read_value("HKCU", _GAMEBAR_KEY, "AutoGameModeEnabled")
    if not exists:
        return "off"
    try:
        return "on" if int(value) == 1 else "off"
    except (TypeError, ValueError):
        return "off"


def _game_mode_apply(value: str) -> tuple[bool, str]:
    data = 1 if value == "on" else 0
    registry.write_value("HKCU", _GAMEBAR_KEY, "AutoGameModeEnabled", "REG_DWORD", data)
    registry.write_value("HKCU", _GAMEBAR_KEY, "AllowAutoGameMode", "REG_DWORD", data)
    return True, "Игровой режим изменён"


# ---------------------------------------------------------------------------
# Оптимизация для оконных игр
# ---------------------------------------------------------------------------
def _windowed_get() -> str:
    exists, _type, value = registry.read_value("HKCU", _DX_KEY, "DirectXUserGlobalSettings")
    if exists and "SwapEffectUpgradeEnable=1" in str(value):
        return "on"
    return "off"


def _windowed_apply(value: str) -> tuple[bool, str]:
    exists, _type, current = registry.read_value("HKCU", _DX_KEY, "DirectXUserGlobalSettings")
    text = str(current) if exists else ""
    flag = "SwapEffectUpgradeEnable=1;" if value == "on" else "SwapEffectUpgradeEnable=0;"
    if "SwapEffectUpgradeEnable=" in text:
        text = re.sub(r"SwapEffectUpgradeEnable=\d+;", flag, text)
    else:
        text = flag + text
    registry.write_value("HKCU", _DX_KEY, "DirectXUserGlobalSettings", "REG_SZ", text)
    return True, "Применено. Перезапустите игру."


# ---------------------------------------------------------------------------
# Полноэкранные оптимизации для exe конкретной игры
# ---------------------------------------------------------------------------
def _fsopt_setting(game_key: str) -> WinSetting:
    exe = game_exe_path(game_key)
    exe_name = os.path.basename(exe) if exe else "игры"

    def get() -> str:
        if not exe:
            return "off"
        exists, _type, value = registry.read_value("HKCU", _LAYERS_KEY, exe)
        if exists and "DISABLEDXMAXIMIZEDWINDOWEDMODE" in str(value):
            return "on"
        return "off"

    def apply(value: str) -> tuple[bool, str]:
        if not exe:
            return False, "Исполняемый файл игры не найден"
        if value == "on":
            registry.write_value(
                "HKCU", _LAYERS_KEY, exe, "REG_SZ", "~ DISABLEDXMAXIMIZEDWINDOWEDMODE"
            )
            return True, f"Оптимизации полного экрана отключены для {exe_name}"
        registry.delete_value("HKCU", _LAYERS_KEY, exe)
        return True, f"Оптимизации полного экрана включены для {exe_name}"

    return WinSetting(
        key="fsopt",
        name=f"Отключить оптимизации полного экрана для {exe_name}",
        help="Помогает при проблемах с alt-tab и полноэкранным режимом.",
        options=list(_ON_OFF),
        value="off",
        get=get,
        apply=apply,
    )


def win_settings_for(game_key: str = "cs2") -> list[WinSetting]:
    return [
        WinSetting(
            key="power_plan",
            name="Схема управления питанием",
            help="Высокая/максимальная производительность не даёт ПК сбрасывать частоты. "
            "На ноутбуке — только от сети.",
            options=[
                ("ultimate", "Максимальная производительность"),
                ("high", "Высокая производительность"),
                ("balanced", "Сбалансированная"),
            ],
            value="high",
            get=_power_get,
            apply=_power_apply,
        ),
        WinSetting(
            key="hags",
            name="Планирование GPU с аппаратным ускорением (HAGS)",
            help="Позволяет GPU управлять своей памятью напрямую, снижает задержку. "
            "Требуется перезагрузка.",
            options=list(_ON_OFF),
            value="on",
            get=_hags_get,
            apply=_hags_apply,
            requires_admin=True,
        ),
        WinSetting(
            key="game_mode",
            name="Игровой режим",
            help="Даёт игре приоритет процессора/графики и откладывает обновления.",
            options=list(_ON_OFF),
            value="on",
            get=_game_mode_get,
            apply=_game_mode_apply,
        ),
        WinSetting(
            key="windowed_opt",
            name="Оптимизация для оконных игр",
            help="Снижает задержку в оконном/безрамочном режиме и включает Auto HDR/VRR.",
            options=list(_ON_OFF),
            value="off",
            get=_windowed_get,
            apply=_windowed_apply,
        ),
        _fsopt_setting(game_key),
    ]
