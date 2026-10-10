"""Оптимизация игр: профили настроек для нескольких игр.

Поддерживаются файлы двух видов:

* VDF-подобные (CS2, Dota 2, Apex Legends) — ``"key" "value"`` внутри блока;
* UE ini (PUBG) — секции ``[Section]`` и строки ``Key=Value``.

Перед изменением каждый файл копируется в папку данных приложения.
"""
from __future__ import annotations

import os
import re
import shutil
from dataclasses import dataclass, field
from pathlib import Path

import psutil

from ..config import app_data_dir

BACKUP_DIRNAME = "game_backup"


@dataclass
class Setting:
    key: str
    value: str
    label: str
    section: str = ""


@dataclass
class GameProfile:
    key: str
    name: str
    logo: str
    kind: str  # "vdf" | "ini"
    settings: list[Setting]
    locator: str  # "steam:730:local/cfg/cs2_video.txt" | "env:..."

    @property
    def process(self) -> str:
        return {"cs2": "cs2.exe", "dota2": "dota2.exe", "apex": "r5apex.exe", "pubg": "tslgame.exe"}.get(self.key, "")


GAMES: list[GameProfile] = [
    GameProfile(
        key="cs2",
        name="Counter-Strike 2",
        logo="cs2.png",
        kind="vdf",
        locator="steam:730:local/cfg/cs2_video.txt",
        settings=[
            Setting("setting.r_player_visibility_mode", "0", "Повышенный контраст — выкл"),
            Setting("setting.mat_vsync", "0", "Вертикальная синхронизация — выкл"),
            Setting("setting.msaa_samples", "4", "Режим сглаживания — 4x MSAA"),
            Setting("setting.videocfg_shadow_quality", "1", "Тени — низкое"),
            Setting("setting.videocfg_texture_detail", "0", "Детализация моделей и текстур — низкое"),
            Setting("setting.shaderquality", "0", "Детализация шейдеров — низкое"),
            Setting("setting.videocfg_particle_detail", "1", "Детализация частиц — низкое"),
            Setting("setting.videocfg_ao_detail", "0", "Глобальное затенение — выкл"),
            Setting("setting.videocfg_hdr_detail", "0", "HDR — производительность"),
            Setting("setting.videocfg_fsr_detail", "0", "FidelityFX Super Resolution — выкл"),
            Setting("setting.r_low_latency", "0", "NVIDIA Reflex — выкл"),
        ],
    ),
    GameProfile(
        key="dota2",
        name="Dota 2",
        logo="dota2.png",
        kind="vdf",
        locator="steam:570:remote/cfg/video.txt",
        settings=[
            Setting("setting.mat_vsync", "0", "Вертикальная синхронизация — выкл"),
            Setting("setting.r_ssao", "0", "SSAO (затенение) — выкл"),
            Setting("setting.r_deferred_height_fog", "0", "Высотный туман — выкл"),
            Setting("setting.cl_globallight_shadow_mode", "0", "Тени глобального света — низкое"),
            Setting("setting.r_deferred_additive_pass", "0", "Доп. проход освещения — выкл"),
            Setting("setting.r_deferred_specular_bloom", "0", "Bloom — выкл"),
            Setting("setting.dota_portrait_animate", "0", "Анимация портретов — выкл"),
            Setting("setting.dota_cheap_water", "1", "Упрощённая вода — вкл"),
            Setting("setting.r_shadow_half_update_rate", "1", "Тени через кадр — вкл"),
            Setting("setting.mat_viewportscale", "1.000000", "Масштаб рендера — 100% (качество)"),
            Setting("setting.mat_picmip", "0", "Детализация текстур — высокое"),
            Setting("setting.r_rootlod", "0", "Детализация моделей — высокое"),
        ],
    ),
    GameProfile(
        key="apex",
        name="Apex Legends",
        logo="apex.png",
        kind="vdf",
        locator="apex",
        settings=[
            Setting("setting.mat_vsync_mode", "0", "Вертикальная синхронизация — выкл"),
            Setting("setting.dvs_enable", "0", "Динамическое разрешение — выкл"),
            Setting("setting.volumetric_lighting", "0", "Объёмное освещение — выкл"),
            Setting("setting.volumetric_fog", "0", "Объёмный туман — выкл"),
            Setting("setting.cl_ragdoll_maxcount", "0", "Тряпичная физика — выкл"),
            Setting("setting.cl_particle_fallback_base", "0", "Детализация частиц — низкое"),
            Setting("setting.r_lod_switch_scale", "1.000000", "Детализация объектов — 100%"),
            Setting("setting.mat_picmip", "0", "Детализация текстур — высокое"),
            Setting("setting.mat_forceaniso", "8", "Анизотропная фильтрация — 8x"),
            Setting("setting.shadow_enable", "1", "Тени — вкл (без потери качества)"),
            Setting("setting.stream_memory", "2000000", "Память стриминга — 2 ГБ"),
        ],
    ),
    GameProfile(
        key="pubg",
        name="PUBG: Battlegrounds",
        logo="pubg.png",
        kind="ini",
        locator="pubg",
        settings=[
            Setting("sg.ResolutionQuality", "100.000000", "Масштаб разрешения — 100%", "ScalabilityGroups"),
            Setting("sg.ViewDistanceQuality", "2", "Дальность прорисовки — высокое", "ScalabilityGroups"),
            Setting("sg.AntiAliasingQuality", "1", "Сглаживание — среднее", "ScalabilityGroups"),
            Setting("sg.ShadowQuality", "0", "Тени — выкл", "ScalabilityGroups"),
            Setting("sg.PostProcessQuality", "0", "Постобработка — выкл", "ScalabilityGroups"),
            Setting("sg.TextureQuality", "2", "Текстуры — высокое", "ScalabilityGroups"),
            Setting("sg.EffectsQuality", "0", "Эффекты — низкое", "ScalabilityGroups"),
            Setting("sg.FoliageQuality", "0", "Растительность — низкое", "ScalabilityGroups"),
            Setting("bMotionBlur", "False", "Размытие в движении — выкл", "/Script/TslGame.TslGameUserSettings"),
            Setting("bSharpen", "False", "Резкость — выкл", "/Script/TslGame.TslGameUserSettings"),
            Setting("InGameFrameRateLimitType", "Unlimited", "Лимит FPS — без ограничений", "/Script/TslGame.TslGameUserSettings"),
            Setting("bUseInGameSmoothedFrameRate", "False", "Сглаживание FPS — выкл", "/Script/TslGame.TslGameUserSettings"),
        ],
    ),
]

GAMES_BY_KEY = {game.key: game for game in GAMES}


@dataclass
class GameSettingsResult:
    ok: bool
    message: str
    files: list[str] = field(default_factory=list)
    backup_dir: str = ""


# ---------------------------------------------------------------------------
# Поиск файлов
# ---------------------------------------------------------------------------
def _steam_roots() -> list[Path]:
    roots: list[Path] = []
    try:
        import winreg

        for hive, subkey, value in (
            (winreg.HKEY_CURRENT_USER, r"Software\Valve\Steam", "SteamPath"),
            (winreg.HKEY_LOCAL_MACHINE, r"SOFTWARE\WOW6432Node\Valve\Steam", "InstallPath"),
            (winreg.HKEY_LOCAL_MACHINE, r"SOFTWARE\Valve\Steam", "InstallPath"),
        ):
            try:
                with winreg.OpenKey(hive, subkey) as key:
                    path = winreg.QueryValueEx(key, value)[0]
                    if path:
                        roots.append(Path(str(path)))
            except OSError:
                continue
    except Exception:  # noqa: BLE001
        pass
    for candidate in (
        r"C:\Program Files (x86)\Steam",
        r"C:\Program Files\Steam",
        r"D:\Steam",
        r"E:\Steam",
        r"F:\Steam",
    ):
        roots.append(Path(candidate))

    unique: list[Path] = []
    for root in roots:
        try:
            resolved = root.resolve()
        except OSError:
            continue
        if resolved not in unique and root.is_dir():
            unique.append(resolved)
    return unique


def _library_roots(steam_root: Path) -> list[Path]:
    roots = [steam_root]
    vdf = steam_root / "steamapps" / "libraryfolders.vdf"
    try:
        text = vdf.read_text(encoding="utf-8", errors="replace")
    except OSError:
        return roots
    for match in re.finditer(r'"path"\s*"([^"]+)"', text):
        path = Path(match.group(1).replace("\\\\", "\\"))
        if path.is_dir() and path not in roots:
            roots.append(path)
    return roots


def _locate(profile: GameProfile) -> list[Path]:
    locator = profile.locator
    if locator.startswith("steam:"):
        _, appid, rel = locator.split(":", 2)
        files: list[Path] = []
        for steam_root in _steam_roots():
            for library in _library_roots(steam_root):
                userdata = library / "userdata"
                if not userdata.is_dir():
                    continue
                for prof in userdata.iterdir():
                    candidate = prof / appid / rel
                    if candidate.is_file():
                        files.append(candidate)
        return files
    if locator == "apex":
        base = Path(os.environ.get("USERPROFILE", "")) / "Saved Games" / "Respawn" / "Apex" / "local"
        candidate = base / "videoconfig.txt"
        return [candidate] if candidate.is_file() else []
    if locator == "pubg":
        base = Path(os.environ.get("LOCALAPPDATA", "")) / "TslGame" / "Saved" / "Config" / "WindowsNoEditor"
        candidate = base / "GameUserSettings.ini"
        return [candidate] if candidate.is_file() else []
    return []


def find_game_files(profile: GameProfile) -> list[Path]:
    return _locate(profile)


def running_game_keys() -> set[str]:
    keys: set[str] = set()
    for proc in psutil.process_iter(["name"]):
        name = (proc.info.get("name") or "").lower()
        for game in GAMES:
            if name == game.process:
                keys.add(game.key)
    return keys


# ---------------------------------------------------------------------------
# Изменение файлов
# ---------------------------------------------------------------------------
def _set_vdf_value(text: str, key: str, value: str) -> str:
    pattern = re.compile(r'^(\s*)"' + re.escape(key) + r'"\s*"[^"]*"', re.MULTILINE)
    if pattern.search(text):
        return pattern.sub(lambda m: f'{m.group(1)}"{key}"\t\t"{value}"', text, count=1)
    index = text.rfind("}")
    if index == -1:
        return text
    return text[:index] + f'\t"{key}"\t\t"{value}"\n' + text[index:]


def _set_ini_value(text: str, section: str, key: str, value: str) -> str:
    lines = text.splitlines()
    section_header = f"[{section}]"
    start = None
    for i, line in enumerate(lines):
        if line.strip().lower() == section_header.lower():
            start = i
            break
    if start is None:
        lines.append(section_header)
        lines.append(f"{key}={value}")
        return "\n".join(lines) + "\n"
    end = len(lines)
    for i in range(start + 1, len(lines)):
        if lines[i].strip().startswith("["):
            end = i
            break
    for i in range(start + 1, end):
        if lines[i].split("=", 1)[0].strip().lower() == key.lower():
            lines[i] = f"{key}={value}"
            return "\n".join(lines) + "\n"
    lines.insert(end, f"{key}={value}")
    return "\n".join(lines) + "\n"


def _apply_text(profile: GameProfile, text: str) -> str:
    for setting in profile.settings:
        if profile.kind == "ini":
            text = _set_ini_value(text, setting.section, setting.key, setting.value)
        else:
            text = _set_vdf_value(text, setting.key, setting.value)
    return text


def _backup_name(profile: GameProfile, path: Path) -> str:
    try:
        account = path.parents[3].name
    except IndexError:
        account = "local"
    return f"{profile.key}_{account}_{path.name}"


def apply_game_settings(profile: GameProfile, progress=None) -> GameSettingsResult:
    if profile.key in running_game_keys():
        return GameSettingsResult(False, f"Закройте {profile.name} и повторите.")

    files = find_game_files(profile)
    if not files:
        return GameSettingsResult(False, f"Файлы настроек {profile.name} не найдены.")

    backup_dir = app_data_dir() / BACKUP_DIRNAME
    backup_dir.mkdir(parents=True, exist_ok=True)

    changed: list[str] = []
    total = max(len(files), 1)
    for index, path in enumerate(files):
        if progress:
            progress(int(index / total * 100), f"Применение: {profile.name}…")
        try:
            text = path.read_text(encoding="utf-8", errors="replace")
        except OSError:
            continue
        try:
            shutil.copy2(path, backup_dir / _backup_name(profile, path))
        except OSError:
            pass
        try:
            path.write_text(_apply_text(profile, text), encoding="utf-8")
            changed.append(str(path))
        except OSError:
            continue

    if progress:
        progress(100, "Готово")
    if not changed:
        return GameSettingsResult(False, "Не удалось изменить файлы настроек.")
    return GameSettingsResult(
        True,
        f"Настройки {profile.name} применены для {len(changed)} профиля(ей).",
        changed,
        str(backup_dir),
    )
