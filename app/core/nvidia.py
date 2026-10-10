"""Рекомендованные настройки драйвера NVIDIA для игр.

Параметры хранятся в профиле драйвера (NVAPI), поэтому приложение показывает
рекомендованные значения с выбором вариантов NVIDIA и позволяет скопировать
готовый список для быстрой настройки в NVIDIA App.
"""
from __future__ import annotations

from dataclasses import dataclass

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


def format_profile(settings: list[NvidiaSetting], values: dict[str, str]) -> str:
    """Текстовый список выбранных значений (для копирования в NVIDIA App)."""
    lines = []
    for setting in settings:
        value = values.get(setting.key, setting.value)
        label = dict(setting.options).get(value, value)
        lines.append(f"{setting.name}: {label}")
    return "\n".join(lines)
