"""Рекомендованные настройки драйвера NVIDIA для игр.

Параметры хранятся в профиле драйвера (NVAPI), поэтому приложение показывает
рекомендованные значения с выбором вариантов NVIDIA и позволяет скопировать
готовый список для быстрой настройки в NVIDIA App.
"""
from __future__ import annotations

from dataclasses import dataclass

from ..config import load_json, save_json

_ON_OFF = [("on", "Вкл"), ("off", "Выкл")]
_LOW_LATENCY = [("off", "Выкл"), ("on", "Вкл"), ("ultra", "Ультра")]
_POWER = [
    ("max", "Максимальная производительность"),
    ("adaptive", "Адаптивная"),
    ("optimal", "Оптимальная"),
]
_TEX_QUALITY = [
    ("highperf", "Высокая производительность"),
    ("perf", "Производительность"),
    ("quality", "Качество"),
    ("highquality", "Высокое качество"),
]
_NEG_LOD = [("allow", "Разрешить"), ("clamp", "Фиксировать")]
_THREADED = [("on", "Вкл"), ("off", "Выкл"), ("auto", "Авто")]
_VSYNC = [("off", "Выкл"), ("on", "Вкл"), ("app", "Как в приложении")]
_REFRESH = [("highest", "Наивысшая доступная"), ("app", "Как в приложении")]
_SHADER_CACHE = [
    ("unlimited", "Без ограничений"),
    ("10", "10 ГБ"),
    ("5", "5 ГБ"),
    ("1", "1 ГБ"),
]
_MONITOR = [("fixed", "Фиксированная частота"), ("gsync", "G-Sync"), ("ulmb", "ULMB")]
_MAX_FPS = [
    ("off", "Выкл"),
    ("237", "237 (для 240 Гц)"),
    ("141", "141 (для 144 Гц)"),
    ("117", "117 (для 120 Гц)"),
    ("60", "60"),
]
_BG_FPS = [("off", "Выкл"), ("30", "30"), ("60", "60")]
_PRESENT = [("layered", "Layered on DXGI Swapchain"), ("auto", "Авто"), ("disabled", "Выкл")]


@dataclass
class NvidiaSetting:
    key: str
    name: str
    help: str
    options: list[tuple[str, str]]
    value: str


def _settings(values: dict[str, str]) -> list[NvidiaSetting]:
    defs = [
        ("image_scaling", "Масштабирование изображения", "Апскейл драйвера. Лучше выключить — используйте FSR/DLSS в игре.", [("off", "Выкл"), ("on", "Вкл")]),
        ("low_latency", "Режим низкой задержки", "Снижает задержку ввода. «Ультра» — минимальная задержка; в игре NVIDIA Reflex приоритетнее.", _LOW_LATENCY),
        ("power", "Режим управления питанием", "Не даёт GPU сбрасывать частоты во время игры.", _POWER),
        ("tex_quality", "Фильтрация текстур — качество", "Качество анизотропной фильтрации. «Высокая производительность» даёт чуть больше FPS.", _TEX_QUALITY),
        ("neg_lod", "Фильтрация текстур — отрицательный LOD", "«Разрешить» добавляет резкости текстурам, «Фиксировать» убирает шум.", _NEG_LOD),
        ("aniso_sample", "Фильтрация текстур — оптимизация анизотропной выборки", "Ускоряет анизотропную фильтрацию.", _ON_OFF),
        ("trilinear", "Фильтрация текстур — оптимизация трилинейной фильтрации", "Ускоряет трилинейную фильтрацию.", _ON_OFF),
        ("threaded", "Многопоточная оптимизация", "Многопоточная обработка драйвера.", _THREADED),
        ("vsync", "Вертикальная синхронизация", "VSync добавляет задержку ввода — выключайте в соревновательных играх.", _VSYNC),
        ("refresh", "Предпочитаемая частота обновления", "Всегда берёт максимальную частоту монитора.", _REFRESH),
        ("shader_cache", "Размер кэша шейдеров", "Большой кэш уменьшает подгрузки и фризы.", _SHADER_CACHE),
        ("monitor", "Технология монитора", "Режим синхронизации. При G-Sync-мониторе выберите G-Sync.", _MONITOR),
        ("max_fps", "Максимальная частота кадров", "Ограничение FPS. Чуть ниже герцовки снижает задержку; «Выкл» — без лимита.", _MAX_FPS),
        ("bg_fps", "Макс. FPS фоновых приложений", "Ограничение FPS для приложений в фоне.", _BG_FPS),
        ("present", "Метод вывода Vulkan/OpenGL", "Метод представления для Vulkan/OpenGL.", _PRESENT),
    ]
    return [
        NvidiaSetting(key, name, help_text, options, values.get(key, options[0][0]))
        for key, name, help_text, options in defs
    ]


_COMMON = {
    "image_scaling": "off",
    "neg_lod": "allow",
    "aniso_sample": "on",
    "trilinear": "on",
    "threaded": "on",
    "vsync": "off",
    "refresh": "highest",
    "shader_cache": "10",
    "monitor": "fixed",
    "bg_fps": "off",
    "present": "layered",
}

# Профили под каждую игру (настроены на высокий FPS).
NVIDIA_PROFILES: dict[str, list[NvidiaSetting]] = {
    "cs2": _settings({**_COMMON, "low_latency": "ultra", "power": "max", "tex_quality": "highperf", "max_fps": "off"}),
    "dota2": _settings({**_COMMON, "low_latency": "on", "power": "max", "tex_quality": "highperf", "max_fps": "off"}),
    "apex": _settings({**_COMMON, "low_latency": "ultra", "power": "max", "tex_quality": "highperf", "max_fps": "off"}),
    "pubg": _settings({**_COMMON, "low_latency": "on", "power": "max", "tex_quality": "highperf", "max_fps": "off"}),
    "squad": _settings({**_COMMON, "low_latency": "on", "power": "max", "tex_quality": "highperf", "max_fps": "141"}),
    "dayz": _settings({**_COMMON, "low_latency": "on", "power": "max", "tex_quality": "highperf", "max_fps": "off"}),
    "gtav": _settings({**_COMMON, "low_latency": "on", "power": "max", "tex_quality": "highperf", "max_fps": "off"}),
}


def profile_for(game_key: str) -> list[NvidiaSetting]:
    return NVIDIA_PROFILES.get(game_key, NVIDIA_PROFILES["cs2"])


# ---------------------------------------------------------------------------
# Готовые профили (переключение одним нажатием)
# ---------------------------------------------------------------------------
PRESETS: list[tuple[str, str, dict[str, str]]] = [
    (
        "fps",
        "МАКС. FPS",
        {
            "image_scaling": "off",
            "low_latency": "ultra",
            "power": "max",
            "tex_quality": "highperf",
            "neg_lod": "allow",
            "aniso_sample": "on",
            "trilinear": "on",
            "threaded": "on",
            "vsync": "off",
            "refresh": "highest",
            "shader_cache": "10",
            "monitor": "fixed",
            "max_fps": "off",
            "bg_fps": "off",
            "present": "layered",
        },
    ),
    (
        "balanced",
        "БАЛАНС",
        {
            "image_scaling": "off",
            "low_latency": "on",
            "power": "max",
            "tex_quality": "quality",
            "neg_lod": "allow",
            "aniso_sample": "on",
            "trilinear": "on",
            "threaded": "on",
            "vsync": "off",
            "refresh": "highest",
            "shader_cache": "5",
            "monitor": "fixed",
            "max_fps": "141",
            "bg_fps": "off",
            "present": "layered",
        },
    ),
    (
        "quality",
        "КАЧЕСТВО",
        {
            "image_scaling": "off",
            "low_latency": "on",
            "power": "max",
            "tex_quality": "highquality",
            "neg_lod": "clamp",
            "aniso_sample": "off",
            "trilinear": "off",
            "threaded": "on",
            "vsync": "off",
            "refresh": "highest",
            "shader_cache": "unlimited",
            "monitor": "gsync",
            "max_fps": "off",
            "bg_fps": "off",
            "present": "layered",
        },
    ),
]

PRESETS_BY_KEY = {key: values for key, _label, values in PRESETS}


def _profile_file(game_key: str) -> str:
    return f"nvidia_{game_key}.json"


def load_saved(game_key: str) -> dict:
    data = load_json(_profile_file(game_key), {})
    return data if isinstance(data, dict) else {}


def save_profile(game_key: str, values: dict) -> None:
    save_json(_profile_file(game_key), values)


def format_profile(settings: list[NvidiaSetting], values: dict[str, str]) -> str:
    """Текстовый список выбранных значений (для копирования в NVIDIA App)."""
    lines = []
    for setting in settings:
        value = values.get(setting.key, setting.value)
        label = dict(setting.options).get(value, value)
        lines.append(f"{setting.name}: {label}")
    return "\n".join(lines)


# ---------------------------------------------------------------------------
# Применение к драйверу NVIDIA (NVAPI / DRS)
# ---------------------------------------------------------------------------
# Ключ интерфейса -> (идентификатор настройки драйвера, {значение: dword}).
_DRS_SETTINGS: dict[str, tuple[int, dict[str, int]]] = {
    "image_scaling": (0x10444444, {"off": 0x00000000, "on": 0x00000001}),
    "low_latency": (0x0005F543, {"off": 0x00000000, "on": 0x00000001, "ultra": 0x00000002}),
    "power": (0x1057EB71, {"adaptive": 0x00000000, "max": 0x00000001, "optimal": 0x00000005}),
    "tex_quality": (
        0x00CE2691,
        {
            "quality": 0x00000000,
            "perf": 0x0000000A,
            "highperf": 0x00000014,
            "highquality": 0xFFFFFFF6,
        },
    ),
    "neg_lod": (0x0019BB68, {"allow": 0x00000000, "clamp": 0x00000001}),
    "aniso_sample": (0x00E73211, {"off": 0x00000000, "on": 0x00000001}),
    # У настройки драйвера инвертированные значения: «Вкл» = 0, «Выкл» = 1.
    "trilinear": (0x002ECAF2, {"on": 0x00000000, "off": 0x00000001}),
    "threaded": (0x20C1221E, {"auto": 0x00000000, "on": 0x00000001, "off": 0x00000002}),
    "vsync": (0x00A879CF, {"off": 0x08416747, "on": 0x47814940, "app": 0x60925292}),
    "refresh": (0x0064B541, {"highest": 0x00000001, "app": 0x00000000}),
    "shader_cache": (
        0x00AC8497,
        {"off": 0x00000000, "1": 0x00000400, "5": 0x00001400, "10": 0x00002800,
         "unlimited": 0xFFFFFFFF},
    ),
    "max_fps": (
        0x10835002,
        {"off": 0, "237": 237, "141": 141, "117": 117, "60": 60},
    ),
    "bg_fps": (0x10835005, {"off": 0, "30": 30, "60": 60}),
    "present": (0x20D690F8, {"layered": 0x00000001, "auto": 0x00000002, "disabled": 0x00000000}),
}

# Настройки, которые нельзя задать в профиле игры (управляются глобально) —
# выводим понятные названия вместо технических ключей.
_UNSUPPORTED_NAMES = {
    "monitor": "Технология монитора (настраивается в разделе «Настройка G-SYNC»)",
}


def drs_pairs(values: dict[str, str]) -> tuple[list[tuple[int, int]], list[str]]:
    """Преобразует выбранные значения в пары (id настройки драйвера, dword)."""
    pairs: list[tuple[int, int]] = []
    unsupported: list[str] = []
    for key, raw in values.items():
        mapping = _DRS_SETTINGS.get(key)
        if mapping is None:
            unsupported.append(_UNSUPPORTED_NAMES.get(key, key))
            continue
        if raw in mapping[1]:
            pairs.append((mapping[0], mapping[1][raw]))
    return pairs, unsupported


def apply_to_driver(game_key: str, values: dict[str, str]) -> tuple[bool, str]:
    """Записывает выбранные значения в профиль драйвера NVIDIA для игры."""
    from . import nvidia_drs
    from .games import GAMES_BY_KEY
    from .win_settings import game_exe_path

    exe = game_exe_path(game_key)
    if not exe:
        return False, (
            "Исполняемый файл игры не найден — профиль драйвера создаётся для "
            "конкретной игры. Установите игру и повторите."
        )
    pairs, unsupported = drs_pairs(values)
    if not pairs:
        return False, "Нет настроек, которые можно применить к драйверу."

    profile = GAMES_BY_KEY.get(game_key)
    friendly = profile.name if profile is not None else game_key
    ok, messages = nvidia_drs.apply_profile(exe, friendly, pairs)
    text = " ".join(messages)
    if unsupported:
        text += " Настраивается вручную: " + "; ".join(unsupported) + "."
    return ok, text.strip()
