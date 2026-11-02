# SPDX-License-Identifier: GPL-3.0-or-later
"""Resolve an opt-in Turing display by its physical Windows USB connector.

Two identical VID_1A86&PID_5722 displays can exchange COM numbers on wake.
Use native Windows SetupAPI (without spawning PowerShell) to read exactly the
SPDRP_LOCATION_PATHS property shown by Windows device manager.
"""
from __future__ import annotations

import ctypes
import os
import re
from ctypes import wintypes
from dataclasses import dataclass
from typing import Callable

TURING_DEVICE_ID = "VID_1A86&PID_5722"
PORT_PATTERN = re.compile(r"\bCOM\d+\b", re.IGNORECASE)

# GUID_DEVCLASS_PORTS: only enumerate present serial port devices.
_GUID_PORTS = (0x4D36E978, 0xE325, 0x11CE, (0xBF, 0xC1, 0x08, 0x00, 0x2B, 0xE1, 0x03, 0x18))
_DIGCF_PRESENT = 0x00000002
_SPDRP_FRIENDLYNAME = 0x0000000C
_SPDRP_LOCATION_PATHS = 0x00000023
_ERROR_NO_MORE_ITEMS = 259
_ERROR_INSUFFICIENT_BUFFER = 122
_REG_SZ = 1
_REG_MULTI_SZ = 7


class _GUID(ctypes.Structure):
    _fields_ = [
        ("Data1", wintypes.DWORD),
        ("Data2", wintypes.WORD),
        ("Data3", wintypes.WORD),
        ("Data4", ctypes.c_ubyte * 8),
    ]


class _SP_DEVINFO_DATA(ctypes.Structure):
    _fields_ = [
        ("cbSize", wintypes.DWORD),
        ("ClassGuid", _GUID),
        ("DevInst", wintypes.DWORD),
        ("Reserved", ctypes.c_void_p),
    ]


@dataclass(frozen=True)
class UsbDisplayPort:
    com_port: str
    instance_id: str
    locations: tuple[str, ...]


class UsbLocationError(RuntimeError):
    pass


def normalize_location(value: str) -> str:
    """A complete physical location, not a VID/PID, COM or serial number."""
    value = str(value or "").strip()
    if not value or not (
        value.upper().startswith("PCIROOT(")
        or value.upper().startswith("ACPI(")
    ):
        raise ValueError("Expected a complete USB LocationPaths value")
    if "#USB(" not in value.upper():
        raise ValueError("Selected location must include a physical USB port")
    return value.upper()


def _read_windows_ports() -> list[UsbDisplayPort]:
    """Enumerate present Ports using SetupAPI; never open a serial connection."""
    setup = ctypes.WinDLL("setupapi", use_last_error=True)
    hdev = ctypes.c_void_p
    data_ptr = ctypes.POINTER(_SP_DEVINFO_DATA)
    get_devs = setup.SetupDiGetClassDevsW
    get_devs.argtypes = [ctypes.POINTER(_GUID), wintypes.LPCWSTR, wintypes.HWND, wintypes.DWORD]
    get_devs.restype = hdev
    enum = setup.SetupDiEnumDeviceInfo
    enum.argtypes = [hdev, wintypes.DWORD, data_ptr]
    enum.restype = wintypes.BOOL
    get_id = setup.SetupDiGetDeviceInstanceIdW
    get_id.argtypes = [hdev, data_ptr, wintypes.LPWSTR, wintypes.DWORD, ctypes.POINTER(wintypes.DWORD)]
    get_id.restype = wintypes.BOOL
    get_prop = setup.SetupDiGetDeviceRegistryPropertyW
    get_prop.argtypes = [
        hdev, data_ptr, wintypes.DWORD, ctypes.POINTER(wintypes.DWORD),
        ctypes.POINTER(ctypes.c_ubyte), wintypes.DWORD, ctypes.POINTER(wintypes.DWORD),
    ]
    get_prop.restype = wintypes.BOOL
    destroy = setup.SetupDiDestroyDeviceInfoList
    destroy.argtypes = [hdev]
    destroy.restype = wintypes.BOOL

    def property_strings(handle, item, property_id, expected_type):
        # Most location lists are under 1 KiB. Allow up to 64 KiB for devices
        # with long paths; a missing property never becomes a guessed location.
        capacity = 1024
        for _ in range(3):
            buf = (ctypes.c_ubyte * capacity)()
            typ = wintypes.DWORD()
            required = wintypes.DWORD()
            if get_prop(handle, ctypes.byref(item), property_id, ctypes.byref(typ),
                        buf, capacity, ctypes.byref(required)):
                if typ.value != expected_type or required.value > capacity:
                    raise UsbLocationError("Unexpected Windows device property type/size")
                raw = bytes(buf[:required.value])
                return tuple(s for s in raw.decode("utf-16-le").split("\0") if s)
            error = ctypes.get_last_error()
            if error != _ERROR_INSUFFICIENT_BUFFER:
                return ()
            capacity = max(capacity * 2, required.value)
            if capacity > 65536:
                break
        raise UsbLocationError("Windows USB location property is too large")

    fields = _GUID(_GUID_PORTS[0], _GUID_PORTS[1], _GUID_PORTS[2],
                   (ctypes.c_ubyte * 8)(*_GUID_PORTS[3]))
    handle = get_devs(ctypes.byref(fields), None, None, _DIGCF_PRESENT)
    if handle == ctypes.c_void_p(-1).value or handle is None:
        raise UsbLocationError(f"Cannot enumerate serial ports (Windows error {ctypes.get_last_error()})")
    found = []
    try:
        index = 0
        while True:
            item = _SP_DEVINFO_DATA()
            item.cbSize = ctypes.sizeof(item)
            if not enum(handle, index, ctypes.byref(item)):
                error = ctypes.get_last_error()
                if error == _ERROR_NO_MORE_ITEMS:
                    return found
                raise UsbLocationError(f"Cannot enumerate serial port #{index} (Windows error {error})")
            index += 1
            ident = ctypes.create_unicode_buffer(1024)
            needed = wintypes.DWORD()
            if not get_id(handle, ctypes.byref(item), ident, len(ident), ctypes.byref(needed)):
                # Fail closed if the device is unidentifiable.
                continue
            instance = ident.value
            if TURING_DEVICE_ID not in instance.upper():
                continue
            names = property_strings(handle, item, _SPDRP_FRIENDLYNAME, _REG_SZ)
            match = PORT_PATTERN.search(names[0]) if names else None
            if not match:
                continue
            locations = property_strings(handle, item, _SPDRP_LOCATION_PATHS, _REG_MULTI_SZ)
            if not locations:
                continue
            found.append(UsbDisplayPort(
                com_port=match.group(0).upper(),
                instance_id=instance,
                locations=tuple(x.upper() for x in locations),
            ))
    finally:
        destroy(handle)


def list_turing_displays() -> list[UsbDisplayPort]:
    if os.name != "nt":
        raise UsbLocationError("USB physical-port binding is supported on Windows only")
    try:
        return _read_windows_ports()
    except (OSError, UnicodeError) as exc:
        raise UsbLocationError(f"Cannot query Windows USB devices: {exc}") from exc



def resolve_com_port(physical_path: str, *, scan=None) -> str:
    """Resolve by physical connector; scan injection supports deterministic tests."""
    try:
        wanted = normalize_location(physical_path)
    except ValueError as exc:
        raise UsbLocationError(str(exc)) from exc
    if scan is None:
        ports = list_turing_displays()
    else:
        ports = []
        for item in scan():
            if not isinstance(item, dict):
                continue
            ident = str(item.get("InstanceId") or "")
            if TURING_DEVICE_ID not in ident.upper():
                continue
            match = PORT_PATTERN.search(str(item.get("FriendlyName") or ""))
            paths = item.get("LocationPaths") or []
            if isinstance(paths, str):
                paths = [paths]
            if match and paths:
                ports.append(UsbDisplayPort(match.group(0).upper(), ident,
                                            tuple(str(path).upper() for path in paths)))
    matches = {p.com_port for p in ports if wanted in p.locations}
    if len(matches) != 1:
        raise UsbLocationError(
            f"Bound Turing at {wanted} is "
            + ("not present" if not matches else "ambiguous")
            + "; refusing unrelated COM"
        )
    return next(iter(matches))
