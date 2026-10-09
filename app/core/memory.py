"""Оптимизация оперативной памяти.

Действия:
* обрезка рабочих наборов процессов (``EmptyWorkingSet``);
* очистка списка ожидания (standby list) через ``NtSetSystemInformation`` —
  требует привилегии ``SeProfileSingleProcessPrivilege`` и прав администратора.
"""
from __future__ import annotations

import ctypes
from ctypes import wintypes
from dataclasses import dataclass
from typing import Callable

import psutil

ProgressFn = Callable[[int, str], None] | None

# --- Доступ к процессам -----------------------------------------------------
PROCESS_SET_QUOTA = 0x0100
PROCESS_QUERY_LIMITED_INFORMATION = 0x1000

_kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)
_psapi = ctypes.WinDLL("psapi", use_last_error=True)
_advapi32 = ctypes.WinDLL("advapi32", use_last_error=True)
_ntdll = ctypes.WinDLL("ntdll", use_last_error=True)

_kernel32.OpenProcess.restype = wintypes.HANDLE
_kernel32.OpenProcess.argtypes = [wintypes.DWORD, wintypes.BOOL, wintypes.DWORD]
_kernel32.CloseHandle.argtypes = [wintypes.HANDLE]
_kernel32.GetCurrentProcess.restype = wintypes.HANDLE

_psapi.EmptyWorkingSet.argtypes = [wintypes.HANDLE]
_psapi.EmptyWorkingSet.restype = wintypes.BOOL

_ntdll.NtSetSystemInformation.argtypes = [ctypes.c_ulong, ctypes.c_void_p, ctypes.c_ulong]
_ntdll.NtSetSystemInformation.restype = ctypes.c_long

# Класс SystemMemoryListInformation и команды.
SYSTEM_MEMORY_LIST_INFORMATION = 0x50
MEMORY_PURGE_STANDBY_LIST = 4
MEMORY_PURGE_LOW_PRIORITY_STANDBY_LIST = 5

TOKEN_ADJUST_PRIVILEGES = 0x0020
TOKEN_QUERY = 0x0008
SE_PRIVILEGE_ENABLED = 0x0002


class _LUID(ctypes.Structure):
    _fields_ = [("LowPart", wintypes.DWORD), ("HighPart", wintypes.LONG)]


class _LUID_AND_ATTRIBUTES(ctypes.Structure):
    _fields_ = [("Luid", _LUID), ("Attributes", wintypes.DWORD)]


class _TOKEN_PRIVILEGES(ctypes.Structure):
    _fields_ = [("PrivilegeCount", wintypes.DWORD), ("Privileges", _LUID_AND_ATTRIBUTES * 1)]


_advapi32.OpenProcessToken.argtypes = [
    wintypes.HANDLE,
    wintypes.DWORD,
    ctypes.POINTER(wintypes.HANDLE),
]
_advapi32.OpenProcessToken.restype = wintypes.BOOL
_advapi32.LookupPrivilegeValueW.argtypes = [
    wintypes.LPCWSTR,
    wintypes.LPCWSTR,
    ctypes.POINTER(_LUID),
]
_advapi32.LookupPrivilegeValueW.restype = wintypes.BOOL
_advapi32.AdjustTokenPrivileges.argtypes = [
    wintypes.HANDLE,
    wintypes.BOOL,
    ctypes.c_void_p,
    wintypes.DWORD,
    ctypes.c_void_p,
    ctypes.c_void_p,
]
_advapi32.AdjustTokenPrivileges.restype = wintypes.BOOL


@dataclass
class MemoryStats:
    total: int
    used: int
    available: int
    percent: float

    @classmethod
    def current(cls) -> "MemoryStats":
        vm = psutil.virtual_memory()
        return cls(total=vm.total, used=vm.used, available=vm.available, percent=vm.percent)


@dataclass
class OptimizeResult:
    before: MemoryStats
    after: MemoryStats
    trimmed: int
    trim_total: int
    standby_cleared: bool
    message: str

    @property
    def freed(self) -> int:
        return max(self.after.available - self.before.available, 0)


def _enable_privilege(name: str) -> bool:
    """Включает привилегию текущего процесса."""
    token = wintypes.HANDLE()
    if not _advapi32.OpenProcessToken(
        _kernel32.GetCurrentProcess(), TOKEN_ADJUST_PRIVILEGES | TOKEN_QUERY, ctypes.byref(token)
    ):
        return False
    try:
        luid = _LUID()
        if not _advapi32.LookupPrivilegeValueW(None, name, ctypes.byref(luid)):
            return False
        privileges = _TOKEN_PRIVILEGES()
        privileges.PrivilegeCount = 1
        privileges.Privileges[0].Luid = luid
        privileges.Privileges[0].Attributes = SE_PRIVILEGE_ENABLED
        if not _advapi32.AdjustTokenPrivileges(
            token, False, ctypes.byref(privileges), 0, None, None
        ):
            return False
        # AdjustTokenPrivileges возвращает успех даже без нужного права.
        return ctypes.get_last_error() == 0
    finally:
        _kernel32.CloseHandle(token)


def _empty_working_set(pid: int) -> bool:
    handle = _kernel32.OpenProcess(
        PROCESS_SET_QUOTA | PROCESS_QUERY_LIMITED_INFORMATION, False, pid
    )
    if not handle:
        return False
    try:
        return bool(_psapi.EmptyWorkingSet(handle))
    finally:
        _kernel32.CloseHandle(handle)


def trim_working_sets(progress: ProgressFn = None) -> tuple[int, int]:
    """Обрезает рабочие наборы процессов. Возвращает ``(успешно, всего)``."""
    processes = list(psutil.process_iter(["pid", "name"]))
    total = len(processes)
    success = 0
    for index, proc in enumerate(processes):
        pid = proc.info.get("pid")
        if pid and pid > 0 and _empty_working_set(pid):
            success += 1
        if progress and index % 25 == 0:
            progress(int(index / max(total, 1) * 100), "Обрезка рабочих наборов…")
    return success, total


def clear_standby_list() -> bool:
    """Очищает список ожидания (kein reboot). Нужны права администратора."""
    if not _enable_privilege("SeProfileSingleProcessPrivilege"):
        return False
    command = ctypes.c_ulong(MEMORY_PURGE_STANDBY_LIST)
    status = _ntdll.NtSetSystemInformation(
        SYSTEM_MEMORY_LIST_INFORMATION, ctypes.byref(command), ctypes.sizeof(command)
    )
    return status == 0


def optimize_memory(clear_standby: bool = True, progress: ProgressFn = None) -> OptimizeResult:
    """Комплексная оптимизация памяти с отчётом «до/после»."""
    before = MemoryStats.current()
    if progress:
        progress(5, "Обрезка рабочих наборов процессов…")
    trimmed, total = trim_working_sets(progress)

    standby_cleared = False
    if clear_standby:
        if progress:
            progress(85, "Очистка списка ожидания…")
        standby_cleared = clear_standby_list()

    after = MemoryStats.current()

    messages: list[str] = [f"Обработано процессов: {trimmed} из {total}"]
    if clear_standby:
        messages.append(
            "Список ожидания очищен" if standby_cleared
            else "Список ожидания не очищен"
        )
    if progress:
        progress(100, "Оптимизация памяти завершена")
    return OptimizeResult(
        before=before,
        after=after,
        trimmed=trimmed,
        trim_total=total,
        standby_cleared=standby_cleared,
        message="; ".join(messages),
    )
