"""Оптимизация игр: применение настроек Counter-Strike 2.

CS2 хранит настройки видео в ``cs2_video.txt`` внутри профиля Steam:
``<Steam>\\userdata\\<id>\\730\\local\\cfg\\cs2_video.txt``. Перед изменением
файлы копируются в папку данных приложения, чтобы можно было откатиться.
"""
from __future__ import annotations

import re
import shutil
from dataclasses import dataclass, field
from pathlib import Path

import psutil

from ..config import app_data_dir

CS2_APPID = "730"
BACKUP_DIRNAME = "cs2_backup"

# Ключ в cs2_video.txt -> (значение, описание)
CS2_SETTINGS: list[tuple[str, str, str]] = [
    ("setting.r_player_visibility_mode", "0", "Повышенный контраст — выкл"),
    ("setting.mat_vsync", "0", "Вертикальная синхронизация — выкл"),
    ("setting.msaa_samples", "4", "Режим сглаживания — 4x MSAA"),
    ("setting.videocfg_shadow_quality", "1", "Тени — низкое"),
    ("setting.videocfg_texture_detail", "0", "Детализация моделей и текстур — низкое"),
    ("setting.shaderquality", "0", "Детализация шейдеров — низкое"),
    ("setting.videocfg_particle_detail", "1", "Детализация частиц — низкое"),
    ("setting.videocfg_ao_detail", "0", "Глобальное затенение — выкл"),
    ("setting.videocfg_hdr_detail", "0", "HDR — производительность"),
    ("setting.videocfg_fsr_detail", "0", "FidelityFX Super Resolution — выкл"),
    ("setting.r_low_latency", "0", "NVIDIA Reflex — выкл"),
]


@dataclass
class GameSettingsResult:
    ok: bool
    message: str
    files: list[str] = field(default_factory=list)
    backup_dir: str = ""


def is_cs2_running() -> bool:
    for proc in psutil.process_iter(["name"]):
        name = (proc.info.get("name") or "").lower()
        if name in ("cs2.exe", "cs2"):
            return True
    return False


def _steam_roots() -> list[Path]:
    roots: list[Path] = []
    try:
        import winreg

        lookups = [
            (winreg.HKEY_CURRENT_USER, r"Software\Valve\Steam", "SteamPath"),
            (winreg.HKEY_LOCAL_MACHINE, r"SOFTWARE\WOW6432Node\Valve\Steam", "InstallPath"),
            (winreg.HKEY_LOCAL_MACHINE, r"SOFTWARE\Valve\Steam", "InstallPath"),
        ]
        for hive, subkey, value in lookups:
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


def find_cs2_video_files() -> list[Path]:
    """Все cs2_video.txt во всех библиотеках Steam."""
    files: list[Path] = []
    seen: set[Path] = set()
    for steam_root in _steam_roots():
        for library in _library_roots(steam_root):
            userdata = library / "userdata"
            if not userdata.is_dir():
                continue
            for profile in userdata.iterdir():
                video = profile / CS2_APPID / "local" / "cfg" / "cs2_video.txt"
                if video.is_file() and video not in seen:
                    seen.add(video)
                    files.append(video)
    return files


def _set_value(text: str, key: str, value: str) -> str:
    pattern = re.compile(r'^(\s*)"' + re.escape(key) + r'"\s*"[^"]*"', re.MULTILINE)
    if pattern.search(text):
        return pattern.sub(lambda m: f'{m.group(1)}"{key}"\t\t"{value}"', text, count=1)
    index = text.rfind("}")
    if index == -1:
        return text
    return text[:index] + f'\t"{key}"\t\t"{value}"\n' + text[index:]


def apply_cs2_settings(progress=None) -> GameSettingsResult:
    if is_cs2_running():
        return GameSettingsResult(False, "Закройте Counter-Strike 2 и повторите.")

    files = find_cs2_video_files()
    if not files:
        return GameSettingsResult(
            False, "Не найдены файлы настроек CS2 (cs2_video.txt)."
        )

    backup_dir = app_data_dir() / BACKUP_DIRNAME
    backup_dir.mkdir(parents=True, exist_ok=True)

    changed: list[str] = []
    total = max(len(files), 1)
    for index, path in enumerate(files):
        if progress:
            progress(int(index / total * 100), f"Применение настроек ({path.parents[3].name})…")
        try:
            text = path.read_text(encoding="utf-8", errors="replace")
        except OSError:
            continue
        try:
            shutil.copy2(path, backup_dir / f"{path.parents[3].name}_cs2_video.txt")
        except OSError:
            pass
        for key, value, _label in CS2_SETTINGS:
            text = _set_value(text, key, value)
        try:
            path.write_text(text, encoding="utf-8")
            changed.append(str(path))
        except OSError:
            continue

    if progress:
        progress(100, "Готово")
    if not changed:
        return GameSettingsResult(False, "Не удалось изменить файлы настроек.")
    return GameSettingsResult(
        True,
        f"Настройки применены для {len(changed)} профиля(ей).",
        changed,
        str(backup_dir),
    )
