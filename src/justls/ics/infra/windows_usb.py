"""Read-only Windows PnP inventory, independent of camera SDK sessions."""
from __future__ import annotations

import ctypes
import os
from ctypes import wintypes


def zwo_camera_count() -> int:
    if os.name != "nt":
        raise NotImplementedError("OS camera hotplug monitoring is available on Windows only")

    class GUID(ctypes.Structure):
        _fields_ = [("Data1", wintypes.DWORD), ("Data2", wintypes.WORD),
                    ("Data3", wintypes.WORD), ("Data4", ctypes.c_ubyte * 8)]

    class DeviceInfo(ctypes.Structure):
        _fields_ = [("cbSize", wintypes.DWORD), ("ClassGuid", GUID),
                    ("DevInst", wintypes.DWORD), ("Reserved", ctypes.c_size_t)]

    api = ctypes.WinDLL("setupapi", use_last_error=True)
    api.SetupDiGetClassDevsW.argtypes = [ctypes.c_void_p, wintypes.LPCWSTR, wintypes.HWND, wintypes.DWORD]
    api.SetupDiGetClassDevsW.restype = wintypes.HANDLE
    api.SetupDiEnumDeviceInfo.argtypes = [wintypes.HANDLE, wintypes.DWORD, ctypes.POINTER(DeviceInfo)]
    api.SetupDiEnumDeviceInfo.restype = wintypes.BOOL
    api.SetupDiGetDeviceInstanceIdW.argtypes = [wintypes.HANDLE, ctypes.POINTER(DeviceInfo),
                                             wintypes.LPWSTR, wintypes.DWORD, ctypes.POINTER(wintypes.DWORD)]
    api.SetupDiGetDeviceInstanceIdW.restype = wintypes.BOOL
    api.SetupDiDestroyDeviceInfoList.argtypes = [wintypes.HANDLE]
    api.SetupDiDestroyDeviceInfoList.restype = wintypes.BOOL
    handle = api.SetupDiGetClassDevsW(None, "USB", None, 0x02 | 0x04)
    if handle == ctypes.c_void_p(-1).value:
        raise ctypes.WinError(ctypes.get_last_error())
    count = 0
    try:
        index = 0
        while True:
            device = DeviceInfo()
            device.cbSize = ctypes.sizeof(DeviceInfo)
            if not api.SetupDiEnumDeviceInfo(handle, index, ctypes.byref(device)):
                if ctypes.get_last_error() == 259:  # ERROR_NO_MORE_ITEMS
                    break
                raise ctypes.WinError(ctypes.get_last_error())
            value = ctypes.create_unicode_buffer(1024)
            if not api.SetupDiGetDeviceInstanceIdW(handle, ctypes.byref(device), value, len(value), None):
                raise ctypes.WinError(ctypes.get_last_error())
            identity = value.value.upper()
            if identity.startswith("USB\\VID_03C3&PID_") and "&MI_" not in identity:
                count += 1
            index += 1
    finally:
        api.SetupDiDestroyDeviceInfoList(handle)
    return count
