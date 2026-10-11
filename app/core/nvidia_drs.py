"""Применение настроек драйвера NVIDIA в профиль игры через NVAPI (DRS).

Модуль вызывает функции ``NvAPI_DRS_*`` напрямую через ``ctypes``, поэтому
значения попадают в профиль драйвера (как при настройке в панели управления
NVIDIA), а не просто копируются в буфер обмена.

Требуется установленный драйвер NVIDIA с библиотекой ``nvapi64.dll`` и права
администратора (приложение их запрашивает при запуске).
"""
from __future__ import annotations

import ctypes
import os

NVAPI_UNICODE_STRING_MAX = 2048
NVAPI_BINARY_DATA_MAX = 4096

# Идентификаторы функций NVAPI (получаются через nvapi_QueryInterface).
_ID_NVAPI_INITIALIZE = 0x0150E828
_ID_DRS_CREATE_SESSION = 0x0694D52E
_ID_DRS_DESTROY_SESSION = 0xDAD9CFF8
_ID_DRS_LOAD_SETTINGS = 0x375DBD6B
_ID_DRS_SAVE_SETTINGS = 0xFCBC7E14
_ID_DRS_CREATE_PROFILE = 0xCC176068
_ID_DRS_GET_PROFILE_INFO = 0x61CD6FD6
_ID_DRS_FIND_PROFILE_BY_NAME = 0x7E4A9A0B
_ID_DRS_CREATE_APPLICATION = 0x4347A9DE
_ID_DRS_FIND_APPLICATION_BY_NAME = 0xEEE566B2
_ID_DRS_SET_SETTING = 0x8A2CF5F5
_ID_DRS_GET_SETTING = 0xEA99498D


class NvidiaDrsError(RuntimeError):
    """Не удалось выполнить операцию NVAPI."""


# ---------------------------------------------------------------------------
# Структуры NVAPI
# ---------------------------------------------------------------------------
class _NVDRS_BINARY_SETTING(ctypes.Structure):
    _fields_ = [
        ("valueLength", ctypes.c_uint32),
        ("valueData", ctypes.c_ubyte * NVAPI_BINARY_DATA_MAX),
    ]


class _NVDRS_SETTING_UNION(ctypes.Union):
    _fields_ = [
        ("dwordValue", ctypes.c_uint32),
        ("binaryValue", _NVDRS_BINARY_SETTING),
        ("stringValue", ctypes.c_uint16 * NVAPI_UNICODE_STRING_MAX),
    ]


class _NVDRS_SETTING(ctypes.Structure):
    _fields_ = [
        ("version", ctypes.c_uint32),
        ("settingName", ctypes.c_uint16 * NVAPI_UNICODE_STRING_MAX),
        ("settingId", ctypes.c_uint32),
        ("settingType", ctypes.c_int32),
        ("settingLocation", ctypes.c_int32),
        ("isCurrentPredefined", ctypes.c_uint32),
        ("isPredefinedValid", ctypes.c_uint32),
        ("predefinedValue", _NVDRS_SETTING_UNION),
        ("currentValue", _NVDRS_SETTING_UNION),
    ]


class _NVDRS_PROFILE(ctypes.Structure):
    _fields_ = [
        ("version", ctypes.c_uint32),
        ("profileName", ctypes.c_uint16 * NVAPI_UNICODE_STRING_MAX),
        ("gpuSupport", ctypes.c_uint32),
        ("isPredefined", ctypes.c_uint32),
        ("numOfApps", ctypes.c_uint32),
        ("numOfSettings", ctypes.c_uint32),
    ]


class _NVDRS_APPLICATION_V4(ctypes.Structure):
    _fields_ = [
        ("version", ctypes.c_uint32),
        ("isPredefined", ctypes.c_uint32),
        ("appName", ctypes.c_uint16 * NVAPI_UNICODE_STRING_MAX),
        ("userFriendlyName", ctypes.c_uint16 * NVAPI_UNICODE_STRING_MAX),
        ("launcher", ctypes.c_uint16 * NVAPI_UNICODE_STRING_MAX),
        ("fileInFolder", ctypes.c_uint16 * NVAPI_UNICODE_STRING_MAX),
        ("bitvector1", ctypes.c_uint32),
        ("commandLine", ctypes.c_uint16 * NVAPI_UNICODE_STRING_MAX),
    ]


def _make_version(size: int, version: int) -> int:
    return size | (version << 16)


_SETTING_VER = _make_version(ctypes.sizeof(_NVDRS_SETTING), 1)
_PROFILE_VER = _make_version(ctypes.sizeof(_NVDRS_PROFILE), 1)
_APPLICATION_VER = _make_version(ctypes.sizeof(_NVDRS_APPLICATION_V4), 4)

# Тип значения — dword (все настройки, которые мы задаём, целочисленные).
_DWORD_TYPE = 0
_CURRENT_PROFILE_LOCATION = 0

_STATUS_NAMES = {
    0: "OK",
    -5: "неверный аргумент",
    -9: "несовместимая версия структуры",
    -104: "не поддерживается",
    -108: "устройство занято",
    -158: "изменение запрещено",
    -160: "настройка не найдена",
    -163: "профиль не найден",
    -164: "имя профиля уже занято",
    -167: "исполняемый файл уже используется",
    -175: "доступ запрещён",
}


def _status(code: int) -> str:
    name = _STATUS_NAMES.get(code)
    if name:
        return f"{name} ({code})"
    return f"код {code}"


def _set_wstring(target, text: str) -> None:
    buffer = ctypes.create_unicode_buffer(text)
    ctypes.memmove(target, buffer, ctypes.sizeof(ctypes.c_uint16) * (len(text) + 1))


_loaded = False
_library = None  # type: ignore[assignment]


def _ensure_library() -> bool:
    global _loaded, _library
    if _loaded:
        return _library is not None
    _loaded = True
    if os.name != "nt":
        return False
    try:
        library = ctypes.WinDLL("nvapi64.dll")
    except OSError:
        return False
    library.nvapi_QueryInterface.restype = ctypes.c_void_p
    library.nvapi_QueryInterface.argtypes = [ctypes.c_uint32]
    if not library.nvapi_QueryInterface(_ID_NVAPI_INITIALIZE):
        return False
    _library = library
    return True


def _func(func_id: int, *argtypes):
    address = _library.nvapi_QueryInterface(func_id)
    if not address:
        return None
    return ctypes.CFUNCTYPE(ctypes.c_int, *argtypes)(address)


class _Session:
    """Сессия DRS: загрузка профилей, изменение и сохранение."""

    def __init__(self) -> None:
        self._handle = ctypes.c_void_p()

    def __enter__(self) -> "_Session":
        if not _ensure_library():
            raise NvidiaDrsError(
                "NVAPI недоступен: не найден nvapi64.dll (нужна видеокарта NVIDIA и драйвер)."
            )
        initialize = _func(_ID_NVAPI_INITIALIZE)
        if initialize is None or initialize() != 0:
            raise NvidiaDrsError("Не удалось инициализировать NVAPI.")

        create = _func(_ID_DRS_CREATE_SESSION, ctypes.POINTER(ctypes.c_void_p))
        code = create(ctypes.byref(self._handle))
        if code != 0:
            raise NvidiaDrsError(f"Не удалось создать сессию драйвера: {_status(code)}")

        load = _func(_ID_DRS_LOAD_SETTINGS, ctypes.c_void_p)
        code = load(self._handle)
        if code != 0:
            self.close()
            raise NvidiaDrsError(f"Не удалось прочитать профили драйвера: {_status(code)}")
        return self

    def __exit__(self, *_exc) -> None:
        self.close()

    def close(self) -> None:
        if not self._handle:
            return
        destroy = _func(_ID_DRS_DESTROY_SESSION, ctypes.c_void_p)
        if destroy is not None:
            destroy(self._handle)
        self._handle = ctypes.c_void_p()

    # -- профили -----------------------------------------------------------
    def _find_profile(self, name: str):
        find = _func(
            _ID_DRS_FIND_PROFILE_BY_NAME,
            ctypes.c_void_p,
            ctypes.c_void_p,
            ctypes.POINTER(ctypes.c_void_p),
        )
        buffer = ctypes.create_unicode_buffer(name, NVAPI_UNICODE_STRING_MAX)
        handle = ctypes.c_void_p()
        code = find(self._handle, ctypes.cast(buffer, ctypes.c_void_p), ctypes.byref(handle))
        return handle if code == 0 else None

    def _profile_is_predefined(self, handle) -> bool:
        get_info = _func(
            _ID_DRS_GET_PROFILE_INFO,
            ctypes.c_void_p,
            ctypes.c_void_p,
            ctypes.POINTER(_NVDRS_PROFILE),
        )
        info = _NVDRS_PROFILE()
        info.version = _PROFILE_VER
        if get_info(self._handle, handle, ctypes.byref(info)) != 0:
            return True
        return bool(info.isPredefined)

    def _create_profile(self, name: str):
        create = _func(
            _ID_DRS_CREATE_PROFILE,
            ctypes.c_void_p,
            ctypes.POINTER(_NVDRS_PROFILE),
            ctypes.POINTER(ctypes.c_void_p),
        )
        profile = _NVDRS_PROFILE()
        profile.version = _PROFILE_VER
        profile.gpuSupport = 1  # GeForce
        _set_wstring(profile.profileName, name)
        handle = ctypes.c_void_p()
        code = create(self._handle, ctypes.byref(profile), ctypes.byref(handle))
        return handle if code == 0 else None

    def _add_application(self, profile, app_name: str, friendly_name: str) -> int:
        create = _func(
            _ID_DRS_CREATE_APPLICATION,
            ctypes.c_void_p,
            ctypes.c_void_p,
            ctypes.POINTER(_NVDRS_APPLICATION_V4),
        )
        app = _NVDRS_APPLICATION_V4()
        app.version = _APPLICATION_VER
        _set_wstring(app.appName, app_name)
        _set_wstring(app.userFriendlyName, friendly_name)
        return create(self._handle, profile, ctypes.byref(app))

    def find_application(self, app_name: str):
        find = _func(
            _ID_DRS_FIND_APPLICATION_BY_NAME,
            ctypes.c_void_p,
            ctypes.c_void_p,
            ctypes.POINTER(ctypes.c_void_p),
            ctypes.POINTER(_NVDRS_APPLICATION_V4),
        )
        buffer = ctypes.create_unicode_buffer(app_name, NVAPI_UNICODE_STRING_MAX)
        handle = ctypes.c_void_p()
        app = _NVDRS_APPLICATION_V4()
        app.version = _APPLICATION_VER
        code = find(
            self._handle,
            ctypes.cast(buffer, ctypes.c_void_p),
            ctypes.byref(handle),
            ctypes.byref(app),
        )
        return handle if code == 0 else None

    def resolve_profile(self, app_name: str, friendly_name: str, messages: list[str]):
        """Профиль игры: существующий или только что созданный."""
        existing = self.find_application(app_name)
        if existing is not None:
            return existing

        base = os.path.basename(app_name) or app_name
        candidate = self._find_profile(base)
        if candidate is not None and not self._profile_is_predefined(candidate):
            if self._add_application(candidate, app_name, friendly_name) == 0:
                return candidate

        for name in (base, f"{base} (Optimizer Game)"):
            profile = self._create_profile(name)
            if profile is None:
                continue
            if self._add_application(profile, app_name, friendly_name) == 0:
                messages.append(f"Создан профиль драйвера «{name}».")
                return profile
        raise NvidiaDrsError("Не удалось создать профиль драйвера для игры.")

    # -- настройки ---------------------------------------------------------
    def set_setting(self, profile, setting_id: int, value: int) -> int:
        set_setting = _func(
            _ID_DRS_SET_SETTING,
            ctypes.c_void_p,
            ctypes.c_void_p,
            ctypes.POINTER(_NVDRS_SETTING),
            ctypes.c_uint32,
            ctypes.c_uint32,
        )
        setting = _NVDRS_SETTING()
        setting.version = _SETTING_VER
        setting.settingId = setting_id
        setting.settingType = _DWORD_TYPE
        setting.settingLocation = _CURRENT_PROFILE_LOCATION
        setting.currentValue.dwordValue = value & 0xFFFFFFFF
        return set_setting(self._handle, profile, ctypes.byref(setting), 0, 0)

    def get_setting(self, profile, setting_id: int):
        get_setting = _func(
            _ID_DRS_GET_SETTING,
            ctypes.c_void_p,
            ctypes.c_void_p,
            ctypes.c_uint32,
            ctypes.POINTER(_NVDRS_SETTING),
            ctypes.POINTER(ctypes.c_uint32),
        )
        setting = _NVDRS_SETTING()
        setting.version = _SETTING_VER
        scratch = ctypes.c_uint32(0)
        code = get_setting(
            self._handle, profile, setting_id, ctypes.byref(setting), ctypes.byref(scratch)
        )
        if code != 0:
            return None
        return setting.currentValue.dwordValue

    def save(self) -> int:
        save = _func(_ID_DRS_SAVE_SETTINGS, ctypes.c_void_p)
        return save(self._handle)


def available() -> bool:
    """Есть ли доступный драйвер NVIDIA."""
    return _ensure_library()


def apply_profile(
    app_name: str, friendly_name: str, settings: list[tuple[int, int]]
) -> tuple[bool, list[str]]:
    """Записывает настройки в профиль драйвера для указанного .exe.

    ``settings`` — список пар (идентификатор настройки, значение dword).
    Возвращает (успех, сообщения для журнала).
    """
    if not settings:
        return False, ["Нет настроек для применения."]
    messages: list[str] = []
    try:
        with _Session() as session:
            profile = session.resolve_profile(app_name, friendly_name, messages)
            applied = 0
            failed: list[int] = []
            for setting_id, value in settings:
                code = session.set_setting(profile, setting_id, value)
                if code == 0:
                    applied += 1
                else:
                    failed.append(setting_id)
            code = session.save()
            if code != 0:
                messages.append(f"Не удалось сохранить профиль: {_status(code)}.")
                return False, messages
            if failed:
                bad = ", ".join(f"0x{sid:08X}" for sid in failed)
                messages.append(f"Не применены настройки: {bad}.")
            messages.insert(0, f"В профиль драйвера записано настроек: {applied} из {len(settings)}.")
            return applied == len(settings), messages
    except NvidiaDrsError as exc:
        return False, [str(exc)]
