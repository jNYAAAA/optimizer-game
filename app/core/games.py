"""Оптимизация игр: профили настроек для нескольких игр.

Поддерживаются файлы двух видов:

* VDF-подобные (CS2, Dota 2, Apex Legends) — ``"key" "value"`` внутри блока;
* UE ini (PUBG, Squad, WARDOGS) — секции ``[Section]`` и строки ``Key=Value``.

У WARDOGS файл ``GameUserSettings.ini`` содержит группы масштабируемости
``[ScalabilityGroups]`` (``sg.*``) и настройки игры ``[/Script/WDGame.WDUserSettings]``.

У каждой настройки есть рекомендованное значение, список допустимых вариантов и
пояснение. Перед изменением каждый файл копируется в папку данных приложения.
"""
from __future__ import annotations

import json
import os
import re
import shutil
import stat
from dataclasses import dataclass, field
from pathlib import Path

import psutil

from ..config import app_data_dir

BACKUP_DIRNAME = "game_backup"

_ON_OFF = [("0", "Выкл"), ("1", "Вкл")]

# Уровни групп масштабируемости Unreal Engine (0 — минимум, 3 — максимум).
_UE_QUALITY = [
    ("0", "Минимум (Potato)"),
    ("1", "Низкое"),
    ("2", "Среднее"),
    ("3", "Высокое"),
]

# В WARDOGS у групп качества есть дополнительный уровень 4 («Overkill»).
_UE_QUALITY_MAX = list(_UE_QUALITY) + [("4", "Ультра (Overkill)")]

# Стандартные группы масштабируемости Unreal Engine для игр, у которых формат
# GameUserSettings.ini не отличается от общепринятого.
_UE_PERF_OPTIONS = [
    ("0", "Минимум"),
    ("1", "Низкое"),
    ("2", "Среднее"),
    ("3", "Высокое"),
]


def _ue_settings() -> list[Setting]:
    """Типовой набор графических параметров UE-игры (секция ScalabilityGroups)."""
    specs = [
        (
            "sg.ResolutionQuality", "100.000000", "Масштаб разрешения рендера",
            "Разрешение рендера. 100% — максимум чёткости; снижайте, только если не "
            "хватает FPS (лучше сначала DLSS/FSR в самой игре).",
            [("100.000000", "100%"), ("90.000000", "90%"), ("80.000000", "80%")],
        ),
        ("sg.ViewDistanceQuality", "2", "Дальность прорисовки",
         "Как далеко видны объекты и игроки. Резать в последнюю очередь.", list(_UE_PERF_OPTIONS)),
        ("sg.AntiAliasingQuality", "2", "Сглаживание",
         "Сглаживание краёв. Среднее — разумный компромисс.", list(_UE_PERF_OPTIONS)),
        ("sg.ShadowQuality", "0", "Тени",
         "Качество теней. Низкое даёт заметный прирост FPS.", list(_UE_PERF_OPTIONS)),
        ("sg.GlobalIlluminationQuality", "0", "Глобальное освещение",
         "Один из самых дорогих параметров — минимум даёт ощутимый прирост FPS.",
         list(_UE_PERF_OPTIONS)),
        ("sg.ReflectionQuality", "0", "Отражения",
         "Отражения редко важны в динамичном бою.", list(_UE_PERF_OPTIONS)),
        ("sg.PostProcessQuality", "0", "Постобработка",
         "Эффекты постобработки: свечение, размытие и т.п.", list(_UE_PERF_OPTIONS)),
        ("sg.TextureQuality", "2", "Текстуры",
         "Качество текстур. На мощных GPU почти не влияет на FPS.", list(_UE_PERF_OPTIONS)),
        ("sg.EffectsQuality", "0", "Эффекты",
         "Взрывы, дым и искры — заметная нагрузка в массовых боях.", list(_UE_PERF_OPTIONS)),
        ("sg.FoliageQuality", "0", "Растительность",
         "Трава и листва. Минимум ещё и улучшает видимость противников.",
         list(_UE_PERF_OPTIONS)),
        ("sg.ShadingQuality", "1", "Затенение",
         "Сложность шейдинга. Низкое заметно снижает нагрузку.", list(_UE_PERF_OPTIONS)),
    ]
    return [
        Setting(key, value, label, "ScalabilityGroups", help=help_text, options=list(options))
        for key, value, label, help_text, options in specs
    ]

_GTAV_TEMPLATE = """<?xml version="1.0" encoding="UTF-8"?>
<Settings>
  <version value="27" />
  <configSource>SMC_AUTO</configSource>
  <graphics>
    <Tessellation value="0" />
    <LodScale value="0.000000" />
    <PedLodBias value="0.200000" />
    <VehicleLodBias value="0.000000" />
    <ShadowQuality value="0" />
    <ReflectionQuality value="0" />
    <ReflectionMSAA value="0" />
    <SSAO value="0" />
    <AnisotropicFiltering value="0" />
    <MSAA value="0" />
    <MSAAFragments value="0" />
    <MSAAQuality value="0" />
    <SamplingMode value="0" />
    <TextureQuality value="0" />
    <ParticleQuality value="0" />
    <WaterQuality value="0" />
    <GrassQuality value="0" />
    <ShaderQuality value="0" />
    <Shadow_SoftShadows value="0" />
    <UltraShadows_Enabled value="false" />
    <Shadow_ParticleShadows value="true" />
    <Shadow_Distance value="1.000000" />
    <Shadow_LongShadows value="false" />
    <Shadow_SplitZStart value="0.930000" />
    <Shadow_SplitZEnd value="0.890000" />
    <Shadow_aircraftExpWeight value="0.990000" />
    <Shadow_DisableScreenSizeEffect value="false" />
    <Grass_UpdateRadius value="0.000000" />
    <Grass_UpdateBias value="0.000000" />
    <Grass_Unk value="0.000000" />
    <Grass_Unk2 value="0.000000" />
    <Grass_Unk3 value="0.000000" />
    <Grass_Unk4 value="0.000000" />
    <Grass_Unk5 value="0.000000" />
    <Grass_Unk6 value="0.000000" />
    <Grass_Unk7 value="0.000000" />
    <Grass_Unk8 value="0.000000" />
    <Grass_Unk9 value="0.000000" />
    <Grass_Unk10 value="0.000000" />
    <DoF value="false" />
    <DoF_Unk value="false" />
    <HDStreamingInFlight value="false" />
    <MaxLODScale value="0.000000" />
    <MotionBlurStrength value="0.000000" />
  </graphics>
  <video>
    <AdapterIndex value="0" />
    <OutputIndex value="0" />
    <ScreenWidth value="1920" />
    <ScreenHeight value="1080" />
    <RefreshRate value="60" />
    <Windowed value="0" />
    <VSync value="0" />
    <Stereo value="0" />
    <Convergence value="0.100000" />
    <Separation value="0.000000" />
    <PauseOnFocusLoss value="1" />
    <AspectRatio value="0" />
    <DX_Version value="2" />
  </video>
</Settings>
"""


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
    kind: str  # "vdf" | "ini" | "xml" | "cfg"
    settings: list[Setting]
    locator: str
    create: bool = False
    template: str = ""
    # У игры есть вкладка «Убрать тени» (правка sg.ShadowQuality + защита файла
    # от перезаписи игрой).
    disable_shadows: bool = False

    @property
    def process(self) -> str:
        return {
            "cs2": "cs2.exe",
            "dota2": "dota2.exe",
            "apex": "r5apex.exe",
            "pubg": "tslgame.exe",
            "wardogs": "wardogsclient-win64-shipping.exe",
            "valorant": "valorant-win64-shipping.exe",
            "fortnite": "fortniteclient-win64-shipping.exe",
            "thefinals": "discovery-win64-shipping.exe",
            "marvelrivals": "marvel-win64-shipping.exe",
        }.get(self.key, "")


GAMES: list[GameProfile] = [
    GameProfile(
        key="cs2",
        name="Counter-Strike 2",
        logo="games/cs2-cover.png",
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
                "setting.msaa_samples", "4", "Режим сглаживания множественной выборкой",
                help="Сглаживание краёв геометрии. 4X MSAA — компромисс между качеством и FPS.",
                options=[("0", "CMAA2"), ("2", "2X MSAA"), ("4", "4X MSAA"), ("8", "8X MSAA")],
            ),
            Setting(
                "setting.videocfg_shadow_quality", "0", "Общее качество теней",
                help="Качество теней. Низкое даёт заметный прирост FPS; тени остаются читаемыми.",
                options=[("0", "Низкое"), ("1", "Среднее"), ("2", "Высокое")],
            ),
            Setting(
                "setting.videocfg_dynamic_shadows", "1", "Динамические тени",
                help="Тени от движущихся объектов. «От всего» — со всех объектов, «Только солнце» — "
                "лишь от солнца (быстрее).",
                options=[("1", "От всего"), ("0", "Только солнце")],
            ),
            Setting(
                "setting.videocfg_texture_detail", "0", "Детализация моделей и текстур",
                help="Качество текстур и моделей. На мощных GPU почти не влияет на FPS.",
                options=[("0", "Низкое"), ("1", "Среднее"), ("2", "Высокое")],
            ),
            Setting(
                "setting.r_texturefilteringquality", "5", "Режим фильтрации текстур",
                help="Чёткость текстур под углом. Анизотропная фильтрация почти не стоит FPS.",
                options=[
                    ("0", "Билинейная"),
                    ("1", "Трилинейная"),
                    ("2", "Анизотропная 2x"),
                    ("3", "Анизотропная 4x"),
                    ("4", "Анизотропная 8x"),
                    ("5", "Анизотропная 16x"),
                ],
            ),
            Setting(
                "setting.shaderquality", "0", "Детализация шейдеров",
                help="Сложность шейдеров, отражений и воды.",
                options=[("0", "Низкое"), ("1", "Среднее"), ("2", "Высокое")],
            ),
            Setting(
                "setting.videocfg_particle_detail", "0", "Детализация частиц",
                help="Плотность частиц: дым, огонь, взрывы.",
                options=[("0", "Низкая"), ("1", "Средняя"), ("2", "Высокая")],
            ),
            Setting(
                "setting.videocfg_ao_detail", "0", "Глобальное затенение",
                help="Мягкие тени в углах. Стоит FPS без игровой пользы.",
                options=[("0", "Выкл"), ("1", "Низкое"), ("2", "Среднее"), ("3", "Высокое")],
            ),
            Setting(
                "setting.videocfg_hdr_detail", "0", "Расширенный динамический диапазон",
                help="Диапазон освещения. «Производительность» снижает нагрузку.",
                options=[("0", "Производительность"), ("1", "Качество")],
            ),
            Setting(
                "setting.videocfg_fsr_detail", "0", "FidelityFX Super Resolution",
                help="Апскейл из низкого разрешения: повышает FPS, но добавляет размытие.",
                options=[("0", "Выкл. (наивысшее качество)"), ("1", "Вкл. (производительность)")],
            ),
            Setting(
                "setting.r_low_latency", "0", "NVIDIA Reflex",
                help="Снижает задержку ввода. «Boost» не даёт GPU сбрасывать частоты.",
                options=[("0", "Выкл"), ("1", "Вкл"), ("2", "Вкл + Boost")],
            ),
            Setting(
                "setting.fullscreen", "1", "Полноэкранный режим",
                help="Полноэкранный режим обычно даёт минимальную задержку ввода.",
                options=[("1", "Полноэкранный"), ("0", "Оконный")],
            ),
            Setting(
                "setting.nowindowborder", "0", "Окно без рамки",
                help="При оконном режиме убирает рамку окна (безрамочное окно).",
                options=[("0", "Выкл"), ("1", "Вкл")],
            ),
            Setting(
                "setting.fullscreen_min_on_focus_loss", "1", "Сворачивать при потере фокуса",
                help="Сворачивать игру при переключении в другое окно.",
                options=[("1", "Вкл"), ("0", "Выкл")],
            ),
        ],
    ),
    GameProfile(
        key="dota2",
        name="Dota 2",
        logo="games/dota2-cover.png",
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
        logo="games/apex-cover.png",
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
        logo="games/pubg-cover.png",
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
    GameProfile(
        key="squad",
        name="Squad",
        logo="games/squad-cover.png",
        kind="ini",
        locator="squad",
        settings=[
            Setting(
                "bUseVSync", "False", "Вертикальная синхронизация", "/Script/Squad.SQGameUserSettings",
                help="Привязка кадров к монитору; добавляет задержку.",
                options=[("False", "Выкл"), ("True", "Вкл")],
            ),
            Setting(
                "bUseDynamicResolution", "False", "Динамическое разрешение", "/Script/Squad.SQGameUserSettings",
                help="Автоматически меняет разрешение под нагрузкой.",
                options=[("False", "Выкл"), ("True", "Вкл")],
            ),
            Setting(
                "FrameRateLimit", "240.000000", "Лимит FPS", "/Script/Squad.SQGameUserSettings",
                help="Ограничение частоты кадров.",
                options=[("0.000000", "Без ограничений"), ("144.000000", "144"), ("240.000000", "240")],
            ),
            Setting(
                "ScreenPercentage", "(Value=100)", "Масштаб разрешения", "/Script/Squad.SQGameUserSettings",
                help="Разрешение рендера. 100% — максимальная чёткость.",
                options=[("(Value=100)", "100%"), ("(Value=85)", "85%"), ("(Value=70)", "70%")],
            ),
            Setting(
                "ReflexMode", "Off", "NVIDIA Reflex", "/Script/Squad.SQGameUserSettings",
                help="Снижает задержку ввода.",
                options=[("Off", "Выкл"), ("On", "Вкл"), ("OnPlusBoost", "Вкл + Boost")],
            ),
            Setting(
                "AmbientOcclusion", "(Value=0)", "Ambient Occlusion", "/Script/Squad.SQGameUserSettings",
                help="Контактное затенение. Стоит FPS без игровой пользы.",
                options=[("(Value=0)", "Выкл"), ("(Value=1)", "Вкл")],
            ),
            Setting(
                "sg.ResolutionQuality", "100", "Масштаб разрешения (scalability)", "ScalabilityGroups",
                help="Разрешение рендера в группах качества.",
                options=[("100", "100%"), ("85", "85%"), ("70", "70%")],
            ),
            Setting(
                "sg.ViewDistanceQuality", "2", "Дальность прорисовки", "ScalabilityGroups",
                help="Насколько далеко видны объекты и игроки.",
                options=[("0", "Очень низкое"), ("1", "Низкое"), ("2", "Среднее"), ("3", "Высокое")],
            ),
            Setting(
                "sg.AntiAliasingQuality", "2", "Сглаживание", "ScalabilityGroups",
                help="Сглаживание краёв.",
                options=[("0", "Выкл"), ("1", "Низкое"), ("2", "Среднее"), ("3", "Высокое")],
            ),
            Setting(
                "sg.ShadowQuality", "1", "Тени", "ScalabilityGroups",
                help="Качество теней.",
                options=[("0", "Очень низкое"), ("1", "Низкое"), ("2", "Среднее"), ("3", "Высокое")],
            ),
            Setting(
                "sg.ReflectionQuality", "0", "Отражения", "ScalabilityGroups",
                help="Качество отражений.",
                options=[("0", "Очень низкое"), ("1", "Низкое"), ("2", "Среднее"), ("3", "Высокое")],
            ),
            Setting(
                "sg.TextureQuality", "2", "Текстуры", "ScalabilityGroups",
                help="Качество текстур.",
                options=[("0", "Очень низкое"), ("1", "Низкое"), ("2", "Среднее"), ("3", "Высокое")],
            ),
            Setting(
                "sg.PostProcessQuality", "1", "Постобработка", "ScalabilityGroups",
                help="Эффекты постобработки.",
                options=[("0", "Очень низкое"), ("1", "Низкое"), ("2", "Среднее"), ("3", "Высокое")],
            ),
            Setting(
                "sg.FoliageQuality", "1", "Растительность", "ScalabilityGroups",
                help="Плотность травы и листвы.",
                options=[("0", "Очень низкое"), ("1", "Низкое"), ("2", "Среднее"), ("3", "Высокое")],
            ),
        ],
    ),
    GameProfile(
        key="dayz",
        name="DayZ",
        logo="games/dayz-cover.png",
        kind="cfg",
        locator="dayz",
        settings=[
            Setting(
                "VSync", "0", "Вертикальная синхронизация",
                help="Привязка кадров к монитору; добавляет задержку.",
                options=[("0", "Выкл"), ("1", "Вкл")],
            ),
            Setting(
                "MSAA", "0", "Сглаживание (MSAA)",
                help="Сглаживание краёв геометрии.",
                options=[("0", "Выкл"), ("2", "2x"), ("4", "4x"), ("8", "8x")],
            ),
            Setting(
                "PostFX", "0", "Постобработка",
                help="Размытие, свечение и другие эффекты.",
                options=[("0", "Выкл"), ("1", "Низкое"), ("2", "Среднее"), ("3", "Высокое")],
            ),
            Setting(
                "FXAO", "0", "Ambient Occlusion",
                help="Контактное затенение.",
                options=[("0", "Выкл"), ("1", "Вкл")],
            ),
            Setting(
                "AToC", "0", "AToC",
                help="Сглаживание прозрачности (alpha to coverage).",
                options=[("0", "Выкл"), ("1", "Вкл")],
            ),
            Setting(
                "AnisoFilter", "0", "Анизотропная фильтрация",
                help="Чёткость текстур под углом.",
                options=[("0", "Выкл"), ("1", "Низкое"), ("2", "Среднее"), ("3", "Высокое")],
            ),
            Setting(
                "TerrainDetail", "0", "Детализация ландшафта",
                help="Детализация рельефа и травы.",
                options=[("0", "Низкое"), ("1", "Среднее"), ("2", "Высокое")],
            ),
            Setting(
                "FXAA", "0", "FXAA",
                help="Быстрое сглаживание постобработкой.",
                options=[("0", "Выкл"), ("1", "Вкл")],
            ),
        ],
    ),
    GameProfile(
        key="gtav",
        name="Grand Theft Auto V",
        logo="games/gtav-cover.png",
        kind="xml",
        locator="gtav",
        create=True,
        template=_GTAV_TEMPLATE,
        settings=[
            Setting(
                "TextureQuality", "2", "Качество текстур",
                help="Разрешение текстур. Держите высоким — почти не влияет на FPS.",
                options=[("0", "Низкое"), ("1", "Среднее"), ("2", "Высокое")],
            ),
            Setting(
                "ShaderQuality", "1", "Качество шейдеров",
                help="Сложность шейдеров и освещения.",
                options=[("0", "Низкое"), ("1", "Среднее"), ("2", "Высокое")],
            ),
            Setting(
                "ShadowQuality", "1", "Качество теней",
                help="Качество теней. Низкое/среднее даёт заметный прирост FPS.",
                options=[("0", "Низкое"), ("1", "Среднее"), ("2", "Высокое")],
            ),
            Setting(
                "ReflectionQuality", "0", "Качество отражений",
                help="Отражения на мокрых поверхностях и машинах.",
                options=[("0", "Низкое"), ("1", "Среднее"), ("2", "Высокое")],
            ),
            Setting(
                "ReflectionMSAA", "0", "Сглаживание отражений",
                help="MSAA для отражений.",
                options=[("0", "Выкл"), ("1", "2x"), ("2", "4x"), ("3", "8x")],
            ),
            Setting(
                "SSAO", "0", "Ambient Occlusion",
                help="Контактное затенение в углах.",
                options=[("0", "Выкл"), ("1", "Низкое"), ("2", "Высокое")],
            ),
            Setting(
                "AnisotropicFiltering", "2", "Анизотропная фильтрация",
                help="Чёткость текстур под углом.",
                options=[("0", "x1"), ("1", "x2"), ("2", "x4"), ("3", "x8"), ("4", "x16")],
            ),
            Setting(
                "MSAA", "0", "MSAA",
                help="Сглаживание краёв. Стоит FPS.",
                options=[("0", "Выкл"), ("1", "2x"), ("2", "4x"), ("3", "8x")],
            ),
            Setting(
                "ParticleQuality", "0", "Качество частиц",
                help="Плотность частиц (дым, искры).",
                options=[("0", "Низкое"), ("1", "Среднее"), ("2", "Высокое")],
            ),
            Setting(
                "WaterQuality", "1", "Качество воды",
                help="Детализация воды.",
                options=[("0", "Низкое"), ("1", "Среднее"), ("2", "Высокое")],
            ),
            Setting(
                "GrassQuality", "1", "Качество травы",
                help="Плотность травы.",
                options=[("0", "Низкое"), ("1", "Среднее"), ("2", "Высокое"), ("3", "Очень высокое")],
            ),
            Setting(
                "Tessellation", "1", "Тесселяция",
                help="Детализация рельефа.",
                options=[("0", "Выкл"), ("1", "Низкое"), ("2", "Среднее"), ("3", "Высокое")],
            ),
            Setting(
                "DoF", "false", "Глубина резкости",
                help="Размытие фона. Стоит FPS и мешает обзору.",
                options=[("false", "Выкл"), ("true", "Вкл")],
            ),
            Setting(
                "MotionBlurStrength", "0.000000", "Размытие в движении",
                help="Размытие при движении камеры.",
                options=[("0.000000", "Выкл"), ("0.500000", "50%"), ("1.000000", "100%")],
            ),
            Setting(
                "VSync", "0", "Вертикальная синхронизация",
                help="Привязка кадров к монитору; добавляет задержку.",
                options=[("0", "Выкл"), ("1", "Вкл")],
            ),
        ],
    ),
    GameProfile(
        key="wardogs",
        name="WARDOGS",
        logo="games/wardogs-cover.png",
        kind="ini",
        locator="wardogs",
        disable_shadows=True,
        settings=[
            # --- Группы масштабируемости (секция ScalabilityGroups) ---
            Setting(
                "sg.ResolutionQuality", "100.000000", "Масштаб разрешения рендера",
                "ScalabilityGroups",
                help="Разрешение рендера. 100% — чёткость; ниже — больше FPS, но хуже видимость "
                "на дистанции. Сначала используйте DLSS/FSR, а не этот параметр.",
                options=[("100.000000", "100%"), ("90.000000", "90%"), ("85.000000", "85%"),
                         ("80.000000", "80%"), ("70.000000", "70%")],
            ),
            Setting(
                "sg.ViewDistanceQuality", "2", "Дальность прорисовки", "ScalabilityGroups",
                help="Как далеко видны объекты и игроки. Резать в последнюю очередь — от него "
                "сильнее всего зависит, заметите ли вы противника на открытой местности.",
                options=list(_UE_QUALITY_MAX),
            ),
            Setting(
                "sg.MeshQuality", "1", "Детализация моделей", "ScalabilityGroups",
                help="Геометрия персонажей и мира. Низкое — минимум нагрузки на ЦП/ГП; "
                "среднее даёт более цельные силуэты.",
                options=list(_UE_QUALITY_MAX),
            ),
            Setting(
                "sg.ShadingQuality", "0", "Качество затенения", "ScalabilityGroups",
                help="Сложность шейдинга. «Картошка» заметно снижает нагрузку и почти не "
                "влияет на читаемость картинки в бою.",
                options=list(_UE_QUALITY_MAX),
            ),
            Setting(
                "sg.GlobalIlluminationQuality", "0", "Глобальное освещение", "ScalabilityGroups",
                help="Один из самых дорогих параметров. Выключение даёт ощутимый прирост FPS.",
                options=list(_UE_QUALITY_MAX),
            ),
            Setting(
                "sg.ReflectionQuality", "0", "Отражения", "ScalabilityGroups",
                help="Отражения почти не важны в перестрелках — простая жертва ради FPS.",
                options=list(_UE_QUALITY_MAX),
            ),
            Setting(
                "sg.PostProcessQuality", "0", "Постобработка", "ScalabilityGroups",
                help="Эффекты постобработки. «Картошка» — максимум кадров, картинка становится "
                "проще, но цели читаются.",
                options=list(_UE_QUALITY_MAX),
            ),
            Setting(
                "sg.EffectsQuality", "0", "Эффекты", "ScalabilityGroups",
                help="Взрывы, дым, разрушения. В массовых боях сильно нагружает систему.",
                options=list(_UE_QUALITY_MAX),
            ),
            Setting(
                "sg.ParticleSpawnRateQuality", "0", "Количество частиц", "ScalabilityGroups",
                help="Плотность частиц. Низкое значение помогает удержать FPS у зоны контроля.",
                options=list(_UE_QUALITY_MAX),
            ),
            Setting(
                "sg.FoliageQuality", "0", "Растительность", "ScalabilityGroups",
                help="Трава и листва. Низкое качество ещё и улучшает видимость противников.",
                options=list(_UE_QUALITY_MAX),
            ),
            Setting(
                "sg.LandscapeQuality", "1", "Ландшафт", "ScalabilityGroups",
                help="Детализация рельефа и грунта.",
                options=list(_UE_QUALITY_MAX),
            ),
            Setting(
                "sg.AntiAliasingQuality", "2", "Сглаживание (без DLSS/FSR)", "ScalabilityGroups",
                help="Сглаживание краёв. Если включён DLSS или FSR, влияние невелико.",
                options=list(_UE_QUALITY_MAX),
            ),
            Setting(
                "sg.TextureQuality", "1", "Потоковая передача текстур", "ScalabilityGroups",
                help="Размер пула текстур в памяти (стриминг). Низкое — меньше видеопамяти и "
                "поздних подгрузок; в видео выбрано «Низкое».",
                options=list(_UE_QUALITY_MAX),
            ),
            Setting(
                "sg.WorldTextureQuality", "0", "Текстуры мира", "ScalabilityGroups",
                help="Качество текстур мира. При 8 ГБ VRAM и меньше — низкое.",
                options=list(_UE_QUALITY_MAX),
            ),
            Setting(
                "sg.CharacterTextureQuality", "0", "Текстуры персонажей", "ScalabilityGroups",
                help="Качество текстур персонажей. При нехватке VRAM держите низким; высокое "
                "заметно улучшает различимость силуэтов.",
                options=list(_UE_QUALITY_MAX),
            ),
            Setting(
                "sg.EffectsTextureQuality", "0", "Текстуры эффектов", "ScalabilityGroups",
                help="Текстуры эффектов. Можно держать ниже остальных.",
                options=list(_UE_QUALITY_MAX),
            ),
            Setting(
                "sg.TextureFilteringQuality", "1", "Фильтрация текстур", "ScalabilityGroups",
                help="Чёткость текстур под углом. Низкое — минимум нагрузки; среднее чётче "
                "почти без потери FPS.",
                options=list(_UE_QUALITY_MAX),
            ),
            Setting(
                "sg.MotionBlurQuality", "0", "Размытие в движении", "ScalabilityGroups",
                help="Смазывает картинку при повороте камеры — мешает целиться.",
                options=list(_UE_QUALITY),
            ),
            Setting(
                "sg.DepthOfFieldQuality", "0", "Глубина резкости", "ScalabilityGroups",
                help="Размытие фона. Мешает обзору и стоит FPS.",
                options=list(_UE_QUALITY),
            ),
            Setting(
                "sg.LensFlareQuality", "0", "Блики объектива", "ScalabilityGroups",
                help="Визуальный шум вокруг источников света.",
                options=list(_UE_QUALITY),
            ),
            Setting(
                "sg.BloomQuality", "0", "Свечение (Bloom)", "ScalabilityGroups",
                help="«Мыльный» ореол вокруг ярких объектов.",
                options=list(_UE_QUALITY),
            ),
            # --- Настройки самой игры (секция WDUserSettings) ---
            Setting(
                "UpscalingMethod", "DLSS", "Метод сглаживания (апскейл)",
                "/Script/WDGame.WDUserSettings",
                help="Как в видео — NVIDIA DLSS. Варианты для других видеокарт: FSR 3 (AMD) "
                "и XeSS (Intel), либо TSR/TAA без апскейла. Названия методов зависят от "
                "версии игры — сверяйте с меню.",
                options=[("DLSS", "NVIDIA DLSS"), ("FSR3", "AMD FSR 3"), ("XeSS", "Intel XeSS"),
                         ("TSR", "TSR (без апскейла)"), ("TAA", "TAA")],
            ),
            Setting(
                "NvidiaDLSSMode", "5", "NVIDIA DLSS", "/Script/WDGame.WDUserSettings",
                help="Режим DLSS. В видео выбран «Баланс» — больше кадров, чем «Качество», "
                "при сохранении читаемости целей. 0 — выключить (игра использует TAA).",
                options=[("0", "Выкл (TAA)"), ("4", "Качество"), ("5", "Баланс"),
                         ("6", "Производительность")],
            ),
            Setting(
                "FSR3QualityMode", "1", "AMD FSR 3", "/Script/WDGame.WDUserSettings",
                help="Апскейл для видеокарт AMD и старых NVIDIA. 0 — выключить. "
                "Не используйте «Производительность»: цели вдали станут неразличимы.",
                options=[("0", "Выкл (TAA)"), ("1", "Качество"), ("2", "Баланс"),
                         ("3", "Производительность")],
            ),
            Setting(
                "NvidiaDLSSGMode", "0", "Генерация кадров (Frame Generation)",
                "/Script/WDGame.WDUserSettings",
                help="Не поднимает базовый FPS и добавляет задержку — для соревновательной "
                "игры лучше выключить.",
                options=list(_ON_OFF),
            ),
            Setting(
                "NvidiaReflexMode", "1", "NVIDIA Reflex", "/Script/WDGame.WDUserSettings",
                help="Снижает задержку ввода. «Boost» не даёт GPU сбрасывать частоты.",
                options=[("0", "Выкл"), ("1", "Вкл"), ("2", "Вкл + Boost")],
            ),
            Setting(
                "bUseVSync", "False", "Вертикальная синхронизация",
                "/Script/WDGame.WDUserSettings",
                help="Привязка кадров к частоте монитора — добавляет задержку ввода.",
                options=[("False", "Выкл"), ("True", "Вкл")],
            ),
            Setting(
                "bUseDynamicResolution", "False", "Динамическое разрешение",
                "/Script/WDGame.WDUserSettings",
                help="Игра сама меняет разрешение под нагрузкой — картинка «плывёт».",
                options=[("False", "Выкл"), ("True", "Вкл")],
            ),
            Setting(
                "Brightness", "2.200000", "Яркость", "/Script/WDGame.WDUserSettings",
                help="В видео — 110% (в конфиге 2,200000). Чуть ярче картинка: противников "
                "лучше видно в тенях.",
                options=[("1.800000", "90%"), ("2.000000", "100%"),
                         ("2.200000", "110% (как в видео)"), ("2.400000", "120%")],
            ),
            Setting(
                "Sharpness", "1.200000", "Резкость", "/Script/WDGame.WDUserSettings",
                help="Пост-резкость изображения. В видео — 1,20: картинка чётче, цели на "
                "дистанции читаются лучше.",
                options=[("0.000000", "Выкл"), ("1.200000", "1,20"), ("1.500000", "1,50"),
                         ("2.000000", "2,00")],
            ),
            Setting(
                "FrameRateLimit", "0.000000", "Ограничение FPS",
                "/Script/WDGame.WDUserSettings",
                help="0 — без ограничений. Если фреймтайм неровный, поставьте частоту монитора "
                "или стабильный FPS.",
                options=[("0.000000", "Без ограничений"), ("60.000000", "60"),
                         ("120.000000", "120"), ("141.000000", "141"),
                         ("144.000000", "144"), ("240.000000", "240")],
            ),
            Setting(
                "BackgroundFrameRateLimit", "120.000000", "Лимит FPS в меню",
                "/Script/WDGame.WDUserSettings",
                help="«Main Menu FPS Limit» из видео: в меню и фоне кадры ограничены, чтобы "
                "видеокарта не грелась и не тратила ресурсы впустую.",
                options=[("120.000000", "120"), ("60.000000", "60"),
                         ("30.000000", "30"), ("144.000000", "144")],
            ),
            Setting(
                "FullscreenMode", "1", "Режим экрана", "/Script/WDGame.WDUserSettings",
                help="Полноэкранный режим обычно даёт минимальную задержку ввода.",
                options=[("0", "Полноэкранный"), ("1", "Полноэкранный в окне"),
                         ("2", "Оконный")],
            ),
            Setting(
                "FieldOfView", "95.000000", "Угол обзора (FOV)",
                "/Script/WDGame.WDUserSettings",
                help="95–100 — оптимально для WARDOGS. Слишком большой FOV уменьшает цели "
                "на дистанции.",
                options=[("90.000000", "90"), ("95.000000", "95"), ("100.000000", "100"),
                         ("110.000000", "110"), ("120.000000", "120")],
            ),
            Setting(
                "bUseMotionBlur", "False", "Размытие в движении",
                "/Script/WDGame.WDUserSettings",
                help="Полное отключение эффекта.",
                options=[("False", "Выкл"), ("True", "Вкл")],
            ),
            Setting(
                "bUseDepthOfField", "False", "Глубина резкости",
                "/Script/WDGame.WDUserSettings",
                help="Полное отключение эффекта.",
                options=[("False", "Выкл"), ("True", "Вкл")],
            ),
            Setting(
                "bUseLensFlare", "False", "Блики объектива",
                "/Script/WDGame.WDUserSettings",
                help="Полное отключение эффекта.",
                options=[("False", "Выкл"), ("True", "Вкл")],
            ),
            Setting(
                "bUseBloom", "False", "Свечение (Bloom)",
                "/Script/WDGame.WDUserSettings",
                help="Полное отключение эффекта.",
                options=[("False", "Выкл"), ("True", "Вкл")],
            ),
            Setting(
                "bIsPictureInPictureScopeEnabled", "False", "Отдельный рендеринг в прицеле (PIP)",
                "/Script/WDGame.WDUserSettings",
                help="Картинка в картинке внутри оптики. Отключение даёт заметный прирост FPS.",
                options=[("False", "Выкл"), ("True", "Вкл")],
            ),
            Setting(
                "bTinnitusAudioEnabled", "False", "Звон в ушах после взрывов",
                "/Script/WDGame.WDUserSettings",
                help="Эффект звона мешает слышать окружение после близких взрывов.",
                options=[("False", "Выкл"), ("True", "Вкл")],
            ),
            Setting(
                "bIsSpatialAudioEnabled", "True", "Пространственный 3D-звук",
                "/Script/WDGame.WDUserSettings",
                help="Позволяет определять направление шагов и стрельбы.",
                options=[("True", "Вкл"), ("False", "Выкл")],
            ),
        ],
    ),
    # --- Популярные игры ---
    GameProfile(
        key="valorant",
        name="VALORANT",
        logo="games/valorant-cover.png",
        kind="ini",
        locator="valorant",
        settings=_ue_settings(),
    ),
    GameProfile(
        key="fortnite",
        name="Fortnite",
        logo="games/fortnite-cover.png",
        kind="ini",
        locator="fortnite",
        settings=_ue_settings(),
    ),
    GameProfile(
        key="thefinals",
        name="THE FINALS",
        logo="games/thefinals-cover.png",
        kind="ini",
        locator="thefinals",
        settings=_ue_settings(),
    ),
    GameProfile(
        key="marvelrivals",
        name="Marvel Rivals",
        logo="games/marvelrivals-cover.png",
        kind="ini",
        locator="marvelrivals",
        settings=_ue_settings(),
    ),
    GameProfile(
        key="seaofthieves",
        name="Sea of Thieves",
        logo="games/seaofthieves-cover.png",
        kind="ini",
        locator="seaofthieves",
        settings=_ue_settings(),
    ),
]

GAMES_BY_KEY = {game.key: game for game in GAMES}


# ---------------------------------------------------------------------------
# Пресеты настроек самой игры (аналог профилей в панели NVIDIA)
# ---------------------------------------------------------------------------
GAME_PRESETS: list[tuple[str, str]] = [
    ("perf", "МАКС. ПРОИЗВОДИТЕЛЬНОСТЬ"),
    ("balanced", "БАЛАНС"),
    ("quality", "КАЧЕСТВО"),
]

# Значения пресетов «БАЛАНС» и «КАЧЕСТВО» изменить относительно рекомендованных.
# Формат: game_key -> setting_key -> (значение_баланса, значение_качества).
# Пустая строка — оставить рекомендованное значение.
_PRESET_OVERRIDES: dict[str, dict[str, tuple[str, str]]] = {
    "cs2": {
        "setting.msaa_samples": ("2", "8"),
        "setting.videocfg_shadow_quality": ("1", "2"),
        "setting.videocfg_texture_detail": ("1", "2"),
        "setting.r_texturefilteringquality": ("3", "5"),
        "setting.shaderquality": ("1", "2"),
        "setting.videocfg_particle_detail": ("1", "2"),
        "setting.videocfg_ao_detail": ("1", "3"),
        "setting.videocfg_hdr_detail": ("", "1"),
    },
    "dota2": {
        "setting.r_ssao": ("", "1"),
        "setting.r_deferred_height_fog": ("", "1"),
        "setting.cl_globallight_shadow_mode": ("1", "2"),
        "setting.r_deferred_additive_pass": ("", "1"),
        "setting.r_deferred_specular_bloom": ("", "1"),
        "setting.dota_portrait_animate": ("", "1"),
        "setting.dota_cheap_water": ("", "0"),
        "setting.r_shadow_half_update_rate": ("", "0"),
    },
    "apex": {
        "setting.volumetric_lighting": ("", "1"),
        "setting.volumetric_fog": ("", "1"),
        "setting.cl_ragdoll_maxcount": ("2", "4"),
        "setting.cl_particle_fallback_base": ("1", "2"),
        "setting.mat_forceaniso": ("", "16"),
        "setting.stream_memory": ("", "4000000"),
    },
    "pubg": {
        "sg.ViewDistanceQuality": ("", "3"),
        "sg.AntiAliasingQuality": ("2", "3"),
        "sg.ShadowQuality": ("2", "3"),
        "sg.PostProcessQuality": ("2", "3"),
        "sg.TextureQuality": ("", "3"),
        "sg.EffectsQuality": ("2", "3"),
        "sg.FoliageQuality": ("2", "3"),
    },
    "squad": {
        "AmbientOcclusion": ("", "(Value=1)"),
        "sg.ViewDistanceQuality": ("", "3"),
        "sg.AntiAliasingQuality": ("", "3"),
        "sg.ShadowQuality": ("2", "3"),
        "sg.ReflectionQuality": ("2", "3"),
        "sg.TextureQuality": ("", "3"),
        "sg.PostProcessQuality": ("2", "3"),
        "sg.FoliageQuality": ("2", "3"),
    },
    "dayz": {
        "MSAA": ("2", "4"),
        "PostFX": ("1", "2"),
        "FXAO": ("", "1"),
        "AToC": ("", "1"),
        "AnisoFilter": ("2", "3"),
        "TerrainDetail": ("1", "2"),
        "FXAA": ("", "1"),
    },
    "gtav": {
        "ShaderQuality": ("", "2"),
        "ShadowQuality": ("", "2"),
        "ReflectionQuality": ("1", "2"),
        "ReflectionMSAA": ("1", "3"),
        "SSAO": ("", "2"),
        "AnisotropicFiltering": ("", "4"),
        "MSAA": ("1", "2"),
        "ParticleQuality": ("1", "2"),
        "WaterQuality": ("", "2"),
        "GrassQuality": ("", "3"),
        "Tessellation": ("2", "3"),
    },
    "wardogs": {
        "sg.ViewDistanceQuality": ("3", "3"),
        "sg.MeshQuality": ("3", "3"),
        "sg.ShadingQuality": ("2", "3"),
        "sg.GlobalIlluminationQuality": ("1", "2"),
        "sg.ReflectionQuality": ("1", "2"),
        "sg.PostProcessQuality": ("2", "3"),
        "sg.EffectsQuality": ("1", "3"),
        "sg.ParticleSpawnRateQuality": ("1", "3"),
        "sg.FoliageQuality": ("1", "2"),
        "sg.LandscapeQuality": ("2", "3"),
        "sg.AntiAliasingQuality": ("3", "3"),
        "sg.TextureQuality": ("3", "3"),
        "sg.WorldTextureQuality": ("3", "3"),
        "sg.CharacterTextureQuality": ("3", "3"),
        "sg.EffectsTextureQuality": ("2", "3"),
        "sg.TextureFilteringQuality": ("3", "3"),
        "sg.BloomQuality": ("1", "2"),
        "sg.LensFlareQuality": ("1", "2"),
        "sg.DepthOfFieldQuality": ("1", "1"),
        "NvidiaDLSSMode": ("5", "4"),
    },
}


def preset_value(game_key: str, setting: Setting, preset: str) -> str:
    """Значение настройки для выбранного пресета игры."""
    override = _PRESET_OVERRIDES.get(game_key, {}).get(setting.key)
    if override is not None:
        balanced, quality = override
        if preset == "balanced" and balanced:
            return balanced
        if preset == "quality" and quality:
            return quality
    return setting.value


@dataclass
class GameSettingsResult:
    ok: bool
    message: str
    files: list[str] = field(default_factory=list)
    backup_dir: str = ""


# ---------------------------------------------------------------------------
# «Убрать тени»: sg.ShadowQuality=4 + защита файла от перезаписи игрой
# ---------------------------------------------------------------------------
SHADOW_KEY = "sg.ShadowQuality"
SHADOW_DISABLED_VALUE = "4"


@dataclass
class ShadowStatus:
    ok: bool
    message: str
    files: list[str] = field(default_factory=list)
    value: str = ""
    readonly: bool = False


def _is_readonly(path: Path) -> bool:
    try:
        return not (path.stat().st_mode & stat.S_IWRITE)
    except OSError:
        return False


def _set_readonly(path: Path, readonly: bool) -> None:
    """Ставит/снимает атрибут «только чтение» (защита от записи игрой)."""
    mode = path.stat().st_mode
    path.chmod(mode & ~stat.S_IWRITE if readonly else mode | stat.S_IWRITE)


def shadow_status(profile: GameProfile) -> ShadowStatus:
    """Текущее значение sg.ShadowQuality и состояние защиты файла."""
    files = find_game_files(profile)
    if not files:
        return ShadowStatus(
            False,
            f"Файл GameUserSettings.ini не найден — запустите {profile.name} хотя бы раз.",
        )
    path = files[0]
    value = ""
    try:
        for line in path.read_text(encoding="utf-8", errors="replace").splitlines():
            stripped = line.strip()
            if stripped.lower().startswith(SHADOW_KEY.lower() + "="):
                value = stripped.split("=", 1)[1].strip()
                break
    except OSError as exc:
        return ShadowStatus(False, f"Не удалось прочитать файл: {exc}")
    return ShadowStatus(
        True, "", [str(p) for p in files], value, _is_readonly(path)
    )


def remove_shadows(profile: GameProfile, progress=None) -> GameSettingsResult:
    """Ставит sg.ShadowQuality=4 и запрещает игре перезаписывать файл."""
    if profile.key in running_game_keys():
        return GameSettingsResult(False, f"Закройте {profile.name} и повторите.")
    files = find_game_files(profile)
    if not files:
        return GameSettingsResult(
            False, f"Файл настроек {profile.name} не найден — запустите игру хотя бы раз."
        )

    # Снимаем защиту, если она уже стоит, — иначе файл не перезаписать.
    for path in files:
        if _is_readonly(path):
            try:
                _set_readonly(path, False)
            except OSError:
                continue

    setting = Setting(SHADOW_KEY, SHADOW_DISABLED_VALUE, "Тени", "ScalabilityGroups")
    result = apply_setting_values(profile, [(setting, SHADOW_DISABLED_VALUE)], progress)
    if not result.ok:
        return result

    protected: list[str] = []
    for name in result.files:
        path = Path(name)
        try:
            _set_readonly(path, True)
            protected.append(str(path))
        except OSError:
            continue
    if not protected:
        return GameSettingsResult(
            False, "Значение записано, но защиту «только чтение» поставить не удалось."
        )
    if progress:
        progress(100, "Готово")
    return GameSettingsResult(
        True,
        f"Тени убраны ({SHADOW_KEY}={SHADOW_DISABLED_VALUE}), файл защищён от сброса игрой "
        f"({len(protected)}).",
        protected,
        result.backup_dir,
    )


def restore_shadows(profile: GameProfile, progress=None) -> GameSettingsResult:
    """Снимает защиту файла и возвращает исходные настройки из резервной копии."""
    if profile.key in running_game_keys():
        return GameSettingsResult(False, f"Закройте {profile.name} и повторите.")
    files = find_game_files(profile)
    for path in files:
        if _is_readonly(path):
            try:
                _set_readonly(path, False)
            except OSError:
                continue
    result = restore_game_settings(profile, progress)
    if result.ok:
        return result
    message = result.message
    if any(_is_readonly(path) for path in files):
        return result
    return GameSettingsResult(False, f"{message} Защита «только чтение» снята.")


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


# Папки UE-игр в %LOCALAPPDATA% и варианты подпапки конфигурации.
_UE_FOLDERS: dict[str, list[tuple[str, str]]] = {
    "valorant": [("VALORANT", "Windows"), ("VALORANT", "WindowsClient")],
    "fortnite": [("FortniteGame", "WindowsClient"), ("FortniteGame", "Windows")],
    "thefinals": [("Discovery", "WindowsClient"), ("Discovery", "Windows")],
    "marvelrivals": [("Marvel", "WindowsClient"), ("Marvel", "Windows")],
    "seaofthieves": [("Athena", "WindowsClient"), ("Athena", "Windows")],
}


def _ue_config_paths(game_key: str) -> list[Path]:
    base = Path(os.environ.get("LOCALAPPDATA", ""))
    found: list[Path] = []
    for folder, variant in _UE_FOLDERS.get(game_key, []):
        candidate = base / folder / "Saved" / "Config" / variant / "GameUserSettings.ini"
        if candidate.is_file():
            found.append(candidate)
    return found


def _locate(profile: GameProfile) -> list[Path]:
    locator = profile.locator
    if locator in _UE_FOLDERS:
        return _ue_config_paths(locator)
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
    if locator == "squad":
        base = Path(os.environ.get("LOCALAPPDATA", "")) / "SquadGame" / "Saved" / "Config" / "Windows"
        candidate = base / "GameUserSettings.ini"
        return [candidate] if candidate.is_file() else []
    if locator == "dayz":
        candidate = Path(os.environ.get("USERPROFILE", "")) / "Documents" / "DayZ" / "DayZ.cfg"
        return [candidate] if candidate.is_file() else []
    if locator == "wardogs":
        base = (
            Path(os.environ.get("LOCALAPPDATA", ""))
            / "Wardogs" / "Saved" / "Config" / "WindowsClient"
        )
        candidate = base / "GameUserSettings.ini"
        return [candidate] if candidate.is_file() else []
    if locator == "gtav":
        candidate = (
            Path(os.environ.get("USERPROFILE", ""))
            / "Documents" / "Rockstar Games" / "GTA V" / "settings.xml"
        )
        if profile.create:
            return [candidate]
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


def _set_cfg_value(text: str, key: str, value: str) -> str:
    pattern = re.compile(r'^(\s*' + re.escape(key) + r'\s*=\s*)[^;\r\n]*;', re.MULTILINE)
    if pattern.search(text):
        return pattern.sub(lambda m: f"{m.group(1)}{value};", text, count=1)
    return text.rstrip() + f"\n{key}={value};\n"


def _set_xml_value(text: str, key: str, value: str) -> str:
    pattern = re.compile(r'(<' + re.escape(key) + r'\s+value=")[^"]*(")', re.IGNORECASE)
    if pattern.search(text):
        return pattern.sub(lambda m: f"{m.group(1)}{value}{m.group(2)}", text, count=1)
    return text


def _apply_text(profile: GameProfile, text: str, items: list[tuple[Setting, str]]) -> str:
    for setting, value in items:
        if profile.kind == "ini":
            text = _set_ini_value(text, setting.section, setting.key, value)
        elif profile.kind == "xml":
            text = _set_xml_value(text, setting.key, value)
        elif profile.kind == "cfg":
            text = _set_cfg_value(text, setting.key, value)
        else:
            text = _set_vdf_value(text, setting.key, value)
    return text


def _backup_name(profile: GameProfile, path: Path) -> str:
    try:
        account = path.parents[3].name
    except IndexError:
        account = "local"
    return f"{profile.key}_{account}_{path.name}"


def _manifest_path(profile: GameProfile) -> Path:
    return app_data_dir() / BACKUP_DIRNAME / f"{profile.key}_manifest.json"


def _read_manifest(profile: GameProfile) -> dict:
    path = _manifest_path(profile)
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
        return data if isinstance(data, dict) else {}
    except (OSError, ValueError):
        return {}


def _write_manifest(profile: GameProfile, manifest: dict) -> None:
    path = _manifest_path(profile)
    path.parent.mkdir(parents=True, exist_ok=True)
    try:
        path.write_text(json.dumps(manifest, ensure_ascii=False, indent=2), encoding="utf-8")
    except OSError:
        pass


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
    manifest = _read_manifest(profile)

    changed: list[str] = []
    total = max(len(files), 1)
    for index, path in enumerate(files):
        if progress:
            progress(int(index / total * 100), f"Применение: {profile.name}…")
        if not path.exists():
            if not profile.create:
                continue
            try:
                path.parent.mkdir(parents=True, exist_ok=True)
                path.write_text(profile.template, encoding="utf-8")
            except OSError:
                continue
        try:
            text = path.read_text(encoding="utf-8", errors="replace")
        except OSError:
            continue
        backup_file = backup_dir / _backup_name(profile, path)
        if not backup_file.exists():
            try:
                shutil.copy2(path, backup_file)
                manifest[str(path)] = str(backup_file)
            except OSError:
                pass
        # Файл может быть защищён приёмом «Убрать тени» (только чтение) —
        # на время записи снимаем защиту и возвращаем её обратно.
        readonly = _is_readonly(path)
        if readonly:
            try:
                _set_readonly(path, False)
            except OSError:
                readonly = False
        try:
            path.write_text(_apply_text(profile, text, items), encoding="utf-8")
            changed.append(str(path))
        except OSError:
            continue
        finally:
            if readonly:
                try:
                    _set_readonly(path, True)
                except OSError:
                    pass

    _write_manifest(profile, manifest)

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


def restore_game_settings(profile: GameProfile, progress=None) -> GameSettingsResult:
    """Возвращает исходные файлы настроек игры из резервной копии."""
    if profile.key in running_game_keys():
        return GameSettingsResult(False, f"Закройте {profile.name} и повторите.")

    manifest = _read_manifest(profile)
    if not manifest:
        return GameSettingsResult(False, f"Резервные копии {profile.name} не найдены.")

    restored: list[str] = []
    total = max(len(manifest), 1)
    for index, (original, backup) in enumerate(manifest.items()):
        if progress:
            progress(int(index / total * 100), f"Откат: {profile.name}…")
        backup_path = Path(backup)
        original_path = Path(original)
        if not backup_path.is_file():
            continue
        readonly = _is_readonly(original_path)
        if readonly:
            try:
                _set_readonly(original_path, False)
            except OSError:
                readonly = False
        try:
            original_path.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(backup_path, original_path)
            restored.append(str(original_path))
        except OSError:
            continue
        finally:
            if readonly and original_path.exists():
                try:
                    _set_readonly(original_path, True)
                except OSError:
                    pass

    # Удаляем использованные копии и манифест, чтобы следующее применение
    # снова сохранило исходное состояние.
    for _original, backup in manifest.items():
        try:
            Path(backup).unlink(missing_ok=True)
        except OSError:
            pass
    try:
        _manifest_path(profile).unlink(missing_ok=True)
    except OSError:
        pass

    if progress:
        progress(100, "Готово")
    if not restored:
        return GameSettingsResult(False, "Не удалось восстановить файлы.")
    return GameSettingsResult(
        True,
        f"Настройки {profile.name} возвращены к исходным ({len(restored)} файлов).",
        restored,
        str(app_data_dir() / BACKUP_DIRNAME),
    )


def apply_game_settings(profile: GameProfile, progress=None) -> GameSettingsResult:
    items = [(setting, setting.value) for setting in profile.settings]
    return apply_setting_values(profile, items, progress)
