"""Очистка временных файлов, кэшей и корзины.

Каждый источник описан :class:`CleanTarget`. Сканирование считает размер и
количество файлов, очистка удаляет содержимое. Занятые файлы пропускаются.
"""
from __future__ import annotations

import glob
import os
import shutil
from dataclasses import dataclass, field
from pathlib import Path
from typing import Callable, Iterable

from ..utils import powershell_json, run_powershell

ProgressFn = Callable[[int, str], None] | None


@dataclass
class CleanTarget:
    key: str
    name: str
    description: str
    patterns: list[str] = field(default_factory=list)
    kind: str = "files"  # files | recyclebin | prefetch
    requires_admin: bool = False


@dataclass
class ScanResult:
    key: str
    size_bytes: int = 0
    file_count: int = 0
    accessible: bool = True


@dataclass
class CleanResult:
    freed_bytes: int = 0
    deleted: int = 0
    skipped: int = 0
    per_target: dict[str, int] = field(default_factory=dict)


def _env(name: str, default: str = "") -> str:
    return os.environ.get(name, default) or default


def default_targets() -> list[CleanTarget]:
    """Список источников для очистки."""
    temp = _env("TEMP", _env("TMP"))
    local = _env("LOCALAPPDATA")
    roaming = _env("APPDATA")
    windir = _env("SystemRoot", r"C:\Windows")

    def user_data(*parts: str) -> str:
        return os.path.join(local, *parts)

    targets: list[CleanTarget] = [
        CleanTarget(
            key="user_temp",
            name="Временные файлы пользователя",
            description="Содержимое %TEMP% текущего пользователя.",
            patterns=[os.path.join(temp, "*")] if temp else [],
        ),
        CleanTarget(
            key="system_temp",
            name="Системные временные файлы",
            description="Содержимое C:\\Windows\\Temp.",
            patterns=[os.path.join(windir, "Temp", "*")],
            requires_admin=True,
        ),
        CleanTarget(
            key="windows_update",
            name="Кэш Центра обновления Windows",
            description="Загруженные пакеты обновлений, которые уже установлены.",
            patterns=[os.path.join(windir, "SoftwareDistribution", "Download", "*")],
            requires_admin=True,
        ),
        CleanTarget(
            key="prefetch",
            name="Prefetch",
            description="Данные предзагрузки приложений (пересоздаются автоматически).",
            patterns=[os.path.join(windir, "Prefetch", "*")],
            kind="prefetch",
            requires_admin=True,
        ),
        CleanTarget(
            key="crash_dumps",
            name="Аварийные дампы",
            description="Дампы падений приложений.",
            patterns=[os.path.join(local, "CrashDumps", "*")],
        ),
        CleanTarget(
            key="thumbnails",
            name="Кэш эскизов",
            description="Миниатюры изображений и видео проводника.",
            patterns=[
                os.path.join(local, "Microsoft", "Windows", "Explorer", "thumbcache_*.db"),
                os.path.join(local, "Microsoft", "Windows", "Explorer", "iconcache_*.db"),
            ],
        ),
        CleanTarget(
            key="browser_chrome",
            name="Кэш Google Chrome",
            description="Веб-кэш, кэш кода и графики.",
            patterns=[
                os.path.join(local, "Google", "Chrome", "User Data", "*", "Cache", "*"),
                os.path.join(local, "Google", "Chrome", "User Data", "*", "Code Cache", "*"),
                os.path.join(local, "Google", "Chrome", "User Data", "*", "GPUCache", "*"),
            ],
        ),
        CleanTarget(
            key="browser_edge",
            name="Кэш Microsoft Edge",
            description="Веб-кэш, кэш кода и графики.",
            patterns=[
                os.path.join(local, "Microsoft", "Edge", "User Data", "*", "Cache", "*"),
                os.path.join(local, "Microsoft", "Edge", "User Data", "*", "Code Cache", "*"),
                os.path.join(local, "Microsoft", "Edge", "User Data", "*", "GPUCache", "*"),
            ],
        ),
        CleanTarget(
            key="browser_brave",
            name="Кэш Brave",
            description="Веб-кэш браузера Brave.",
            patterns=[
                os.path.join(local, "BraveSoftware", "Brave-Browser", "User Data", "*", "Cache", "*"),
                os.path.join(local, "BraveSoftware", "Brave-Browser", "User Data", "*", "Code Cache", "*"),
            ],
        ),
        CleanTarget(
            key="browser_firefox",
            name="Кэш Mozilla Firefox",
            description="Дисковый кэш профилей Firefox.",
            patterns=[
                os.path.join(local, "Mozilla", "Firefox", "Profiles", "*", "cache2", "*"),
            ],
        ),
        CleanTarget(
            key="recyclebin",
            name="Корзина",
            description="Удаляет файлы из корзины без возможности восстановления.",
            kind="recyclebin",
        ),
    ]

    if roaming:
        targets.append(
            CleanTarget(
                key="roaming_temp",
                name="Кэш приложений (Roaming)",
                description="Временные файлы в %APPDATA%\\Temp.",
                patterns=[os.path.join(roaming, "Temp", "*")],
            )
        )
    return targets


# ---------------------------------------------------------------------------
# Корзина
# ---------------------------------------------------------------------------
_RECYCLE_SIZE_SCRIPT = r"""
$ErrorActionPreference='SilentlyContinue'
$shell = New-Object -ComObject Shell.Application
$bin = $shell.Namespace(0xA)
$size = 0; $count = 0
foreach ($item in $bin.Items()) {
    try { $size += [Int64]$item.Size; $count++ } catch {}
}
[ordered]@{ size = [Int64]$size; count = [int]$count } | ConvertTo-Json -Compress
"""


def recycle_bin_info() -> ScanResult:
    try:
        data = powershell_json(_RECYCLE_SIZE_SCRIPT, timeout=30) or {}
        return ScanResult(
            key="recyclebin",
            size_bytes=int(data.get("size") or 0),
            file_count=int(data.get("count") or 0),
        )
    except Exception:  # noqa: BLE001
        return ScanResult(key="recyclebin", accessible=False)


def empty_recycle_bin() -> CleanResult:
    info = recycle_bin_info()
    proc = run_powershell("Clear-RecycleBin -Force -ErrorAction SilentlyContinue; 'OK'", timeout=180)
    ok = proc.returncode == 0
    return CleanResult(
        freed_bytes=info.size_bytes if ok else 0,
        deleted=info.file_count if ok else 0,
        per_target={"recyclebin": info.size_bytes if ok else 0},
    )


# ---------------------------------------------------------------------------
# Сканирование
# ---------------------------------------------------------------------------
def _iter_matches(pattern: str) -> Iterable[str]:
    for match in glob.glob(pattern):
        yield match


def _measure(path: str) -> tuple[int, int]:
    """Возвращает ``(размер, количество файлов)`` для пути."""
    try:
        if os.path.islink(path):
            return 0, 0
        if os.path.isfile(path):
            return os.stat(path, follow_symlinks=False).st_size, 1
    except OSError:
        return 0, 0

    size = 0
    count = 0
    for root, _dirs, files in os.walk(path, followlinks=False):
        for name in files:
            full = os.path.join(root, name)
            try:
                if os.path.islink(full):
                    continue
                size += os.stat(full, follow_symlinks=False).st_size
                count += 1
            except OSError:
                continue
    return size, count


def scan_target(target: CleanTarget) -> ScanResult:
    if target.kind == "recyclebin":
        return recycle_bin_info()

    result = ScanResult(key=target.key)
    seen: set[str] = set()
    for pattern in target.patterns:
        for match in _iter_matches(pattern):
            if match in seen:
                continue
            seen.add(match)
            size, count = _measure(match)
            result.size_bytes += size
            result.file_count += count
    return result


def scan_targets(targets: Iterable[CleanTarget], progress: ProgressFn = None) -> dict[str, ScanResult]:
    target_list = list(targets)
    results: dict[str, ScanResult] = {}
    total = max(len(target_list), 1)
    for index, target in enumerate(target_list):
        if progress:
            progress(int(index / total * 100), f"Сканирование: {target.name}")
        results[target.key] = scan_target(target)
    if progress:
        progress(100, "Сканирование завершено")
    return results


# ---------------------------------------------------------------------------
# Очистка
# ---------------------------------------------------------------------------
def _remove(path: str) -> tuple[int, int, int]:
    """Удаляет путь. Возвращает ``(освобождено, удалено, пропущено)``."""
    size, count = _measure(path)
    try:
        if os.path.islink(path) or os.path.isfile(path):
            os.remove(path)
        else:
            shutil.rmtree(path, ignore_errors=False)
    except OSError:
        return 0, 0, max(count, 1)
    return size, count, 0


def clean_target(target: CleanTarget, progress: ProgressFn = None) -> CleanResult:
    if target.kind == "recyclebin":
        return empty_recycle_bin()

    result = CleanResult()
    seen: set[str] = set()
    for pattern in target.patterns:
        for match in _iter_matches(pattern):
            if match in seen:
                continue
            seen.add(match)
            freed, deleted, skipped = _remove(match)
            result.freed_bytes += freed
            result.deleted += deleted
            result.skipped += skipped
    if progress:
        progress(100, f"{target.name}: освобождено")
    return result


def clean_targets(
    targets: Iterable[CleanTarget],
    keys: Iterable[str] | None = None,
    progress: ProgressFn = None,
) -> CleanResult:
    """Очищает выбранные источники (``keys=None`` — все)."""
    selected = [t for t in targets if keys is None or t.key in set(keys)]
    aggregate = CleanResult()
    total = max(len(selected), 1)
    for index, target in enumerate(selected):
        if progress:
            progress(int(index / total * 100), f"Очистка: {target.name}")
        partial = clean_target(target)
        aggregate.freed_bytes += partial.freed_bytes
        aggregate.deleted += partial.deleted
        aggregate.skipped += partial.skipped
        if partial.freed_bytes:
            aggregate.per_target[target.key] = partial.freed_bytes
    if progress:
        progress(100, "Очистка завершена")
    return aggregate
