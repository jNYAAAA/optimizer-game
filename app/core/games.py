"""Оптимизация игр: профили настроек для нескольких игр.

Поддерживаются файлы двух видов:

* VDF-подобные (CS2, Dota 2, Apex Legends) — ``"key" "value"`` внутри блока;
* UE ini (PUBG) — секции ``[Section]`` и строки ``Key=Value``.

У каждой настройки есть рекомендованное значение, список допустимых вариантов и
пояснение. Перед изменением каждый файл копируется в папку данных приложения.
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

_ON_OFF = [("0", "Выкл"), ("1", "Вкл")]


@dataclass
class Setting:
    key: str
    value: str
    label: str
    section: str = ""
    help: str = ""
    options: list[tuple[str, str]] = field(default_factory=list)


@dataclass
class GameProfile:
    key: str
    name: str
    logo: str
    kind: str  # "vdf" | "ini"
    settings: list[Setting]
    locator: str

    @property
    def process(self) -> str:
        return {
            "cs2": "cs2.exe",
            "dota2": "dota2.exe",
            "apex": "r5apex.exe",
            "pubg": "tslgame.exe",
        }.get(self.key, "")


GAMES: list[GameProfile] = [
    GameProfile(
        key="cs2",
        name="Counter-Strike 2",
        logo="games/cs2-logo.png",
        kind="vdf",
        locator="steam:730:local/cfg/cs2_video.txt",
        settings=[
            Setting(
                "setting.r_player_visibility_mode", "0", "Повышенный контраст",
                help="Подсвечивает контраст игроков. Выключение убирает лишнюю обработку.",
                options=[("0", "Выкл"), ("1", "Вкл")],
            ),
            Setting(
                "setting.mat_vsync", "0", "Вертикальная синхронизация",
                help="Привязка кадров к частоте монитора. Включение добавляет задержку ввода.",
                options=[("0", "Выкл"), ("1", "Вкл"), ("2", "Адаптивная")],
            ),
            Setting(
                "setting.msaa_samples", "4", "Режим сглаживания (MSAA)",
                help="Сглаживание краёв геометрии. 4x — компромисс между качеством и FPS.",
                options=[("0", "Выкл"), ("2", "2x"), ("4", "4x"), ("8", "8x")],
            ),
            Setting(
                "setting.videocfg_shadow_quality", "1", "Тени",
                help="Качество теней. Низкое даёт заметный прирост FPS; тени остаются читаемыми.",
                options=[("1", "Низкое"), ("2", "Среднее"), ("3", "Высокое")],
            ),
            Setting(
                "setting.videocfg_texture_detail", "0", "Детализация моделей и текстур",
                help="Качество текстур и моделей. На мощных GPU почти не влияет на FPS.",
                options=[("0", "Низкое"), ("1", "Среднее"), ("2", "Высокое")],
            ),
            Setting(
                "setting.shaderquality", "0", "Детализация шейдеров",
                help="Сложность шейдеров, отражений и воды.",
                options=[("0", "Низкое"), ("1", "Среднее"), ("2", "Высокое")],
            ),
            Setting(
                "setting.videocfg_particle_detail", "1", "Детализация частиц",
                help="Плотность частиц: дым, огонь, взрывы.",
                options=[("1", "Низкое"), ("2", "Среднее"), ("3", "Высокое")],
            ),
            Setting(
                "setting.videocfg_ao_detail", "0", "Глобальное затенение",
                help="Мягкие тени в углах. Стоит FPS без игровой пользы.",
                options=[("0", "Выкл"), ("1", "Низкое"), ("2", "Среднее"), ("3", "Высокое")],
            ),
            Setting(
                "setting.videocfg_hdr_detail", "0", "HDR",
                help="Диапазон освещения. «Производительность» снижает нагрузку.",
                options=[("0", "Производительность"), ("1", "Качество")],
            ),
            Setting(
                "setting.videocfg_fsr_detail", "0", "FidelityFX Super Resolution",
                help="Апскейл из низкого разрешения: повышает FPS, но добавляет размытие.",
                options=[("0", "Выкл"), ("1", "Вкл")],
            ),
            Setting(
                "setting.r_low_latency", "0", "NVIDIA Reflex",
                help="Снижает задержку ввода. «Boost» не даёт GPU сбрасывать частоты.",
                options=[("0", "Выкл"), ("1", "Вкл"), ("2", "Вкл + Boost")],
            ),
        ],
    ),
    GameProfile(
        key="dota2",
        name="Dota 2",
        logo="games/dota2-logo.png",
        kind="vdf",
        locator="steam:570:remote/cfg/video.txt",
        settings=[
            Setting(
                "setting.mat_vsync", "0", "Вертикальная синхронизация",
                help="Привязка кадров к частоте монитора; добавляет задержку.",
                options=[("0", "Выкл"), ("1", "Вкл"), ("2", "Адаптивная")],
            ),
            Setting("setting.r_ssao", "0", "SSAO (затенение)", help="Мягкие контактные тени.", options=list(_ON_OFF)),
            Setting("setting.r_deferred_height_fog", "0", "Высотный туман", help="Дымка по высоте — стоит FPS.", options=list(_ON_OFF)),
            Setting(
                "setting.cl_globallight_shadow_mode", "0", "Тени глобального света",
                help="Качество теней от солнца.",
                options=[("0", "Низкое"), ("1", "Среднее"), ("2", "Высокое")],
            ),
            Setting("setting.r_deferred_additive_pass", "0", "Доп. проход освещения", help="Дополнительный проход света.", options=list(_ON_OFF)),
            Setting("setting.r_deferred_specular_bloom", "0", "Bloom (свечение)", help="Свечение ярких участков.", options=list(_ON_OFF)),
            Setting("setting.dota_portrait_animate", "0", "Анимация портретов", help="Анимированные портреты героев в HUD.", options=list(_ON_OFF)),
            Setting("setting.dota_cheap_water", "1", "Упрощённая вода", help="Упрощённый рендер воды.", options=list(_ON_OFF)),
            Setting("setting.r_shadow_half_update_rate", "1", "Тени через кадр", help="Обновляет тени вдвое реже.", options=list(_ON_OFF)),
            Setting(
                "setting.mat_viewportscale", "1.000000", "Масштаб рендера",
                help="Разрешение рендера. 100% — максимальная чёткость.",
                options=[("0.700000", "70%"), ("0.850000", "85%"), ("1.000000", "100%")],
            ),
            Setting(
                "setting.mat_picmip", "0", "Детализация текстур",
                help="Разрешение текстур.",
                options=[("0", "Высокое"), ("1", "Среднее"), ("2", "Низкое")],
            ),
            Setting(
                "setting.r_rootlod", "0", "Детализация моделей",
                help="Уровень детализации моделей.",
                options=[("0", "Высокое"), ("1", "Среднее"), ("2", "Низкое")],
            ),
        ],
    ),
    GameProfile(
        key="apex",
        name="Apex Legends",
        logo="games/apex-logo.png",
        kind="vdf",
        locator="apex",
        settings=[
            Setting(
                "setting.mat_vsync_mode", "0", "Вертикальная синхронизация",
                help="Привязка кадров к монитору; добавляет задержку.",
                options=[("0", "Выкл"), ("1", "Вкл"), ("2", "Адаптивная")],
            ),
            Setting("setting.dvs_enable", "0", "Динамическое разрешение", help="Автоматически меняет разрешение под нагрузкой.", options=list(_ON_OFF)),
            Setting("setting.volumetric_lighting", "0", "Объёмное освещение", help="Объёмные световые лучи — тяжёлые для GPU.", options=list(_ON_OFF)),
            Setting("setting.volumetric_fog", "0", "Объёмный туман", help="Объёмный туман — заметная нагрузка.", options=list(_ON_OFF)),
            Setting(
                "setting.cl_ragdoll_maxcount", "0", "Тряпичная физика",
                help="Количество физических тел погибших.",
                options=[("0", "Выкл"), ("2", "2"), ("4", "4"), ("8", "8")],
            ),
            Setting(
                "setting.cl_particle_fallback_base", "0", "Детализация частиц",
                help="Плотность частиц и эффектов.",
                options=[("0", "Низкое"), ("1", "Среднее"), ("2", "Высокое")],
            ),
            Setting(
                "setting.r_lod_switch_scale", "1.000000", "Детализация объектов",
                help="Дальность и детализация моделей.",
                options=[("0.500000", "50%"), ("0.750000", "75%"), ("1.000000", "100%")],
            ),
            Setting(
                "setting.mat_picmip", "0", "Детализация текстур",
                help="Разрешение текстур.",
                options=[("0", "Высокое"), ("1", "Среднее"), ("2", "Низкое")],
            ),
            Setting(
                "setting.mat_forceaniso", "8", "Анизотропная фильтрация",
                help="Чёткость текстур под углом.",
                options=[("1", "Выкл"), ("2", "2x"), ("4", "4x"), ("8", "8x"), ("16", "16x")],
            ),
            Setting("setting.shadow_enable", "1", "Тени", help="Динамические тени.", options=list(_ON_OFF)),
            Setting(
                "setting.stream_memory", "2000000", "Память стриминга",
                help="Бюджет видеопамяти под текстуры.",
                options=[("1000000", "1 ГБ"), ("2000000", "2 ГБ"), ("4000000", "4 ГБ")],
            ),
        ],
    ),
    GameProfile(
        key="pubg",
        name="PUBG: Battlegrounds",
        logo="games/pubg-logo.png",
        kind="ini",
        locator="pubg",
        settings=[
            Setting(
                "sg.ResolutionQuality", "100.000000", "Масштаб разрешения", "ScalabilityGroups",
                help="Разрешение рендера. 100% — максимальная чёткость.",
                options=[("100.000000", "100%"), ("90.000000", "90%"), ("80.000000", "80%")],
            ),
            Setting(
                "sg.ViewDistanceQuality", "2", "Дальность прорисовки", "ScalabilityGroups",
                help="Насколько далеко видны объекты и игроки.",
                options=[("0", "Очень низкое"), ("1", "Низкое"), ("2", "Среднее"), ("3", "Высокое")],
            ),
            Setting(
                "sg.AntiAliasingQuality", "1", "Сглаживание", "ScalabilityGroups",
                help="Сглаживание краёв.",
                options=[("0", "Выкл"), ("1", "Низкое"), ("2", "Среднее"), ("3", "Высокое")],
            ),
            Setting(
                "sg.ShadowQuality", "0", "Тени", "ScalabilityGroups",
                help="Качество теней.",
                options=[("0", "Очень низкое"), ("1", "Низкое"), ("2", "Среднее"), ("3", "Высокое")],
            ),
            Setting(
                "sg.PostProcessQuality", "0", "Постобработка", "ScalabilityGroups",
                help="Эффекты постобработки.",
                options=[("0", "Очень низкое"), ("1", "Низкое"), ("2", "Среднее"), ("3", "Высокое")],
            ),
            Setting(
                "sg.TextureQuality", "2", "Текстуры", "ScalabilityGroups",
                help="Качество текстур.",
                options=[("0", "Очень низкое"), ("1", "Низкое"), ("2", "Среднее"), ("3", "Высокое")],
            ),
            Setting(
                "sg.EffectsQuality", "0", "Эффекты", "ScalabilityGroups",
                help="Качество эффектов (взрывы, дым).",
                options=[("0", "Очень низкое"), ("1", "Низкое"), ("2", "Среднее"), ("3", "Высокое")],
            ),
            Setting(
                "sg.FoliageQuality", "0", "Растительность", "ScalabilityGroups",
                help="Плотность травы и листвы.",
                options=[("0", "Очень низкое"), ("1", "Низкое"), ("2", "Среднее"), ("3", "Высокое")],
            ),
            Setting(
                "bMotionBlur", "False", "Размытие в движении", "/Script/TslGame.TslGameUserSettings",
                help="Размытие при повороте камеры.",
                options=[("False", "Выкл"), ("True", "Вкл")],
            ),
            Setting(
                "bSharpen", "False", "Резкость", "/Script/TslGame.TslGameUserSettings",
                help="Пост-резкость изображения.",
                options=[("False", "Выкл"), ("True", "Вкл")],
            ),
            Setting(
                "InGameFrameRateLimitType", "Unlimited", "Лимит FPS", "/Script/TslGame.TslGameUserSettings",
                help="Ограничение частоты кадров в игре.",
                options=[("Unlimited", "Без ограничений"), ("Custom", "Пользовательский")],
            ),
            Setting(
                "bUseInGameSmoothedFrameRate", "False", "Сглаживание FPS", "/Script/TslGame.TslGameUserSettings",
                help="Сглаживает колебания частоты кадров.",
                options=[("False", "Выкл"), ("True", "Вкл")],
            ),
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


def _apply_text(profile: GameProfile, text: str, items: list[tuple[Setting, str]]) -> str:
    for setting, value in items:
        if profile.kind == "ini":
            text = _set_ini_value(text, setting.section, setting.key, value)
        else:
            text = _set_vdf_value(text, setting.key, value)
    return text


def _backup_name(profile: GameProfile, path: Path) -> str:
    try:
        account = path.parents[3].name
    except IndexError:
        account = "local"
    return f"{profile.key}_{account}_{path.name}"


def apply_setting_values(
    profile: GameProfile, items: list[tuple[Setting, str]], progress=None
) -> GameSettingsResult:
    """Применяет набор (настройка, значение) ко всем профилям игры."""
    if not items:
        return GameSettingsResult(False, "Нет настроек для применения.")
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
            path.write_text(_apply_text(profile, text, items), encoding="utf-8")
            changed.append(str(path))
        except OSError:
            continue

    if progress:
        progress(100, "Готово")
    if not changed:
        return GameSettingsResult(False, "Не удалось изменить файлы настроек.")
    return GameSettingsResult(
        True,
        f"Применено настроек: {len(items)} · профилей: {len(changed)}.",
        changed,
        str(backup_dir),
    )


def apply_game_settings(profile: GameProfile, progress=None) -> GameSettingsResult:
    items = [(setting, setting.value) for setting in profile.settings]
    return apply_setting_values(profile, items, progress)
