"""Параметры запуска игр (Steam).

Steam хранит строку параметров запуска для каждой игры в файле
``userdata/<аккаунт>/config/localconfig.vdf``. Модуль находит этот файл,
аккуратно меняет только значение ``LaunchOptions`` нужной игры и перед
изменением сохраняет копию, чтобы параметры можно было вернуть.

Важно: перед записью Steam должен быть закрыт — иначе при выходе он
перезапишет конфигурацию своим состоянием в памяти.
"""
from __future__ import annotations

import re
import shutil
from dataclasses import dataclass, field
from pathlib import Path

import psutil

from ..config import app_data_dir, load_json, save_json
from .games import _steam_roots

BACKUP_DIRNAME = "steam_backup"
_MANIFEST = "launch_options.json"

# Идентификаторы игр в Steam.
STEAM_APPIDS: dict[str, int] = {
    "cs2": 730,
    "dota2": 570,
    "apex": 1172470,
    "pubg": 578080,
    "squad": 393380,
    "dayz": 221100,
    "gtav": 271590,
    "wardogs": 1867240,
    "thefinals": 2073850,
    "marvelrivals": 2767030,
    "seaofthieves": 1172620,
}

# Готовые (проверенные) параметры запуска. Для остальных игр строка пустая —
# параметры вводятся вручную.
RECOMMENDED: dict[str, str] = {
    "cs2": "-novid -nojoy -high +fps_max 0",
    "dota2": "-novid -high",
    "apex": "-novid -high",
    "pubg": "-high -USEALLAVAILABLECORES -malloc=system",
    "squad": "-high -USEALLAVAILABLECORES -nosplash",
    "dayz": "-high -nosplash -noPause",
    "gtav": "-high",
    "wardogs": (
        "-dx12 -USEALLAVAILABLECORES -high -nosplash -malloc=system -nogpucrashdebugging"
    ),
    # Игры на Unreal Engine понимают эти флаги: все ядра ЦП, высокий приоритет
    # процесса и отключение заставки при запуске.
    "thefinals": "-USEALLAVAILABLECORES -high -nosplash",
    "marvelrivals": "-USEALLAVAILABLECORES -high -nosplash",
    "seaofthieves": "-USEALLAVAILABLECORES -high -nosplash",
}

RECOMMENDED_HELP = (
    "-dx12 — рендер DirectX 12 (в UE5 он и так по умолчанию); "
    "-USEALLAVAILABLECORES — разрешить все ядра ЦП; "
    "-high — повышенный приоритет процесса; "
    "-nosplash — не показывать логотипы при запуске; "
    "-malloc=system — системный аллокатор памяти (иногда убирает микрофризы); "
    "-nogpucrashdebugging — отключить отладочный сбор данных о сбоях GPU: меньше накладных "
    "расходов и лишних сообщений об ошибках драйвера."
)


@dataclass
class LaunchOptionsResult:
    ok: bool
    message: str
    files: list[str] = field(default_factory=list)


# ---------------------------------------------------------------------------
# Поиск конфигурации Steam
# ---------------------------------------------------------------------------
def steam_running() -> bool:
    for proc in psutil.process_iter(["name"]):
        if (proc.info.get("name") or "").lower() == "steam.exe":
            return True
    return False


def find_configs() -> list[Path]:
    """Файлы ``localconfig.vdf`` всех аккаунтов Steam."""
    found: list[Path] = []
    for steam_root in _steam_roots():
        userdata = steam_root / "userdata"
        if not userdata.is_dir():
            continue
        try:
            accounts = list(userdata.iterdir())
        except OSError:
            continue
        for account in accounts:
            config = account / "config" / "localconfig.vdf"
            if config.is_file() and config not in found:
                found.append(config)
    return found


# ---------------------------------------------------------------------------
# Разбор VDF
# ---------------------------------------------------------------------------
def _skip_string(text: str, index: int) -> int:
    """Пропускает строку в кавычках; ``index`` указывает на открывающую."""
    i = index + 1
    length = len(text)
    while i < length:
        if text[i] == "\\":
            i += 2
            continue
        if text[i] == '"':
            return i + 1
        i += 1
    return length


def _brace_end(text: str, open_index: int) -> int | None:
    """Позиция парной закрывающей скобки для ``{`` в ``open_index``."""
    depth = 0
    i = open_index
    length = len(text)
    while i < length:
        char = text[i]
        if char == '"':
            i = _skip_string(text, i)
            continue
        if char == "{":
            depth += 1
        elif char == "}":
            depth -= 1
            if depth == 0:
                return i
        i += 1
    return None


def _find_block(text: str, key: str, start: int = 0):
    """Ищет блок ``"key" { ... }`` начиная с позиции ``start``.

    Возвращает (начало ключа, позиция ``{``, позиция ``}``) или ``None``.
    """
    pattern = re.compile(r'"' + re.escape(key) + r'"\s*\{')
    for match in pattern.finditer(text, start):
        open_index = text.find("{", match.start())
        if open_index == -1:
            continue
        end_index = _brace_end(text, open_index)
        if end_index is not None:
            return match.start(), open_index, end_index
    return None


def _apps_block(text: str):
    """Диапазон блока ``apps`` внутри UserLocalConfigStore/Software/Valve/Steam."""
    position = 0
    span = None
    for key in ("UserLocalConfigStore", "Software", "Valve", "Steam", "apps"):
        span = _find_block(text, key, position)
        if span is None:
            return None
        position = span[1] + 1
    return span


def _app_block(text: str, appid: int):
    """Диапазон блока настроек конкретной игры внутри ``apps``."""
    apps = _apps_block(text)
    if apps is None:
        return None
    span = _find_block(text, str(appid), apps[1] + 1)
    if span is None or span[2] > apps[2]:
        return None
    return span


_LAUNCH_RE = re.compile(r'"LaunchOptions"\s*"((?:[^"\\]|\\.)*)"')


def _unescape(value: str) -> str:
    return value.replace('\\"', '"').replace("\\\\", "\\")


def _escape(value: str) -> str:
    return value.replace("\\", "\\\\").replace('"', '\\"')


def read_launch_options(text: str, appid: int) -> str | None:
    """Строка параметров запуска игры или ``None``, если игра не найдена."""
    block = _app_block(text, appid)
    if block is None:
        return None
    segment = text[block[1] + 1 : block[2]]
    match = _LAUNCH_RE.search(segment)
    return _unescape(match.group(1)) if match else ""


def write_launch_options(text: str, appid: int, value: str) -> str:
    """Возвращает текст конфигурации с новым значением ``LaunchOptions``."""
    block = _app_block(text, appid)
    if block is None:
        apps = _apps_block(text)
        if apps is None:
            return text
        indent = "\t" * 4
        inserted = (
            f'\n{indent}"{appid}"\n{indent}{{\n'
            f'{indent}\t"LaunchOptions"\t\t"{_escape(value)}"\n'
            f"{indent}}}\n"
        )
        return text[: apps[2]] + inserted + text[apps[2]:]

    open_index, close_index = block[1], block[2]
    segment = text[open_index + 1 : close_index]
    match = _LAUNCH_RE.search(segment)
    if match:
        start = open_index + 1 + match.start(1)
        end = open_index + 1 + match.end(1)
        return text[:start] + _escape(value) + text[end:]
    indent = "\t" * 5
    line = f'\n{indent}"LaunchOptions"\t\t"{_escape(value)}"'
    return text[:close_index] + line + text[close_index:]


# ---------------------------------------------------------------------------
# Чтение и запись
# ---------------------------------------------------------------------------
def current_launch_options(game_key: str) -> tuple[str | None, list[str]]:
    """Текущие параметры запуска и найденные файлы конфигурации Steam."""
    appid = STEAM_APPIDS.get(game_key)
    if appid is None:
        return None, []
    files = find_configs()
    value: str | None = None
    for path in files:
        try:
            text = path.read_text(encoding="utf-8", errors="replace")
        except OSError:
            continue
        found = read_launch_options(text, appid)
        if found:
            value = found
        elif value is None and found is not None:
            value = ""
    return value, files


def _backup_name(appid: int, path: Path) -> str:
    return f"localconfig_{appid}_{path.parent.parent.name}.vdf"


def apply_launch_options(game_key: str, options: str, progress=None) -> LaunchOptionsResult:
    """Записывает строку параметров запуска игры в конфигурацию Steam."""
    appid = STEAM_APPIDS.get(game_key)
    if appid is None:
        return LaunchOptionsResult(False, "Для этой игры неизвестен идентификатор Steam.")
    if steam_running():
        return LaunchOptionsResult(False, "Закройте Steam и повторите — иначе изменения будут потеряны.")

    files = find_configs()
    if not files:
        return LaunchOptionsResult(False, "Файл конфигурации Steam (localconfig.vdf) не найден.")

    options = options.strip()
    backup_dir = app_data_dir() / BACKUP_DIRNAME
    backup_dir.mkdir(parents=True, exist_ok=True)
    manifest = load_json(_MANIFEST, {})
    if not isinstance(manifest, dict):
        manifest = {}

    changed: list[str] = []
    total = max(len(files), 1)
    for index, path in enumerate(files):
        if progress:
            progress(int(index / total * 100), "Запись параметров запуска…")
        try:
            text = path.read_text(encoding="utf-8", errors="replace")
        except OSError:
            continue
        previous = read_launch_options(text, appid)
        if previous is None:
            continue
        updated = write_launch_options(text, appid, options)
        if updated == text:
            continue
        entry = manifest.get(str(path))
        if not isinstance(entry, dict):
            backup_file = backup_dir / _backup_name(appid, path)
            try:
                shutil.copy2(path, backup_file)
                manifest[str(path)] = {
                    "appid": appid,
                    "backup": str(backup_file),
                    "previous": previous,
                }
            except OSError:
                pass
        try:
            path.write_text(updated, encoding="utf-8")
        except OSError:
            continue
        changed.append(str(path))

    save_json(_MANIFEST, manifest)

    if progress:
        progress(100, "Готово")
    if not changed:
        return LaunchOptionsResult(
            False,
            "Игра не найдена в конфигурации Steam. Запустите Steam с этой игрой хотя бы раз.",
        )
    text = "Параметры запуска записаны." if options else "Параметры запуска очищены."
    return LaunchOptionsResult(True, f"{text} Файлов: {len(changed)}.", changed)


def restore_launch_options(game_key: str, progress=None) -> LaunchOptionsResult:
    """Возвращает параметры запуска из резервной копии."""
    appid = STEAM_APPIDS.get(game_key)
    if appid is None:
        return LaunchOptionsResult(False, "Для этой игры неизвестен идентификатор Steam.")
    if steam_running():
        return LaunchOptionsResult(False, "Закройте Steam и повторите.")

    manifest = load_json(_MANIFEST, {})
    if not isinstance(manifest, dict):
        manifest = {}
    entries = {
        path: entry
        for path, entry in manifest.items()
        if isinstance(entry, dict) and entry.get("appid") == appid
    }
    if not entries:
        return LaunchOptionsResult(False, "Резервные копии параметров запуска не найдены.")

    restored: list[str] = []
    total = max(len(entries), 1)
    for index, (original, entry) in enumerate(entries.items()):
        if progress:
            progress(int(index / total * 100), "Возврат параметров запуска…")
        backup_path = Path(str(entry.get("backup", "")))
        if not backup_path.is_file():
            continue
        try:
            shutil.copy2(backup_path, Path(original))
            restored.append(original)
        except OSError:
            continue
        try:
            backup_path.unlink(missing_ok=True)
        except OSError:
            pass
        manifest.pop(original, None)

    save_json(_MANIFEST, manifest)

    if progress:
        progress(100, "Готово")
    if not restored:
        return LaunchOptionsResult(False, "Не удалось восстановить параметры запуска.")
    return LaunchOptionsResult(
        True, f"Параметры запуска возвращены ({len(restored)} файлов).", restored
    )
