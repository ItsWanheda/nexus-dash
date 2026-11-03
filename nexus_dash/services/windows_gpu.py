"""Native Windows DXGI GPU inventory and adapter identity helpers."""
from __future__ import annotations
import ctypes
import platform
import re
import uuid
from typing import Any


def _guid(value: str):
    class GUID(ctypes.Structure):
        _fields_ = [("Data1", ctypes.c_uint32), ("Data2", ctypes.c_uint16),
                    ("Data3", ctypes.c_uint16), ("Data4", ctypes.c_ubyte * 8)]
    parsed = uuid.UUID(value)
    return GUID(parsed.time_low, parsed.time_mid, parsed.time_hi_version,
                (ctypes.c_ubyte * 8).from_buffer_copy(parsed.bytes[8:]))


class _LUID(ctypes.Structure):
    _fields_ = [("LowPart", ctypes.c_uint32), ("HighPart", ctypes.c_int32)]


class _DESC1(ctypes.Structure):
    _fields_ = [
        ("Description", ctypes.c_wchar * 128), ("VendorId", ctypes.c_uint32),
        ("DeviceId", ctypes.c_uint32), ("SubSysId", ctypes.c_uint32),
        ("Revision", ctypes.c_uint32), ("DedicatedVideoMemory", ctypes.c_size_t),
        ("DedicatedSystemMemory", ctypes.c_size_t), ("SharedSystemMemory", ctypes.c_size_t),
        ("AdapterLuid", _LUID), ("Flags", ctypes.c_uint32),
    ]


def _method(pointer, index: int, restype, argtypes):
    table = ctypes.cast(pointer, ctypes.POINTER(ctypes.POINTER(ctypes.c_void_p))).contents
    return ctypes.WINFUNCTYPE(restype, *argtypes)(table[index])


def _release(pointer):
    if pointer and pointer.value:
        try:
            _method(pointer, 2, ctypes.c_ulong, [ctypes.c_void_p])(pointer)
        except Exception:
            pass


def collect_windows_dxgi_inventory() -> list[dict[str, Any]]:
    """Enumerate display adapters and read hardware identity/memory from DXGI."""
    if platform.system() != "Windows":
        return []
    factory, output = ctypes.c_void_p(), []
    try:
        dll = ctypes.WinDLL("dxgi.dll")
        create = dll.CreateDXGIFactory1
        create.argtypes = [ctypes.c_void_p, ctypes.POINTER(ctypes.c_void_p)]
        create.restype = ctypes.c_long
        iid = _guid("770aae78-f26f-4dba-a829-253c83d1b387")
        if create(ctypes.byref(iid), ctypes.byref(factory)) < 0 or not factory.value:
            return []
        enum = _method(factory, 13, ctypes.c_long,
            [ctypes.c_void_p, ctypes.c_uint, ctypes.POINTER(ctypes.c_void_p)])
        for index in range(32):
            adapter = ctypes.c_void_p()
            result = enum(factory, index, ctypes.byref(adapter))
            if (result & 0xffffffff) == 0x887a0002:
                break
            if result < 0 or not adapter.value:
                continue
            try:
                desc = _DESC1()
                get_desc = _method(adapter, 10, ctypes.c_long,
                    [ctypes.c_void_p, ctypes.POINTER(_DESC1)])
                if get_desc(adapter, ctypes.byref(desc)) < 0:
                    continue
                subsystem = f"{desc.SubSysId:08x}"
                high, low = desc.AdapterLuid.HighPart & 0xffffffff, desc.AdapterLuid.LowPart
                output.append({
                    "name": str(desc.Description or "").strip()[:160] or "Windows graphics adapter",
                    "vendor_id": f"{desc.VendorId:04x}" if desc.VendorId <= 0xffff else None,
                    "device_id": f"{desc.DeviceId:04x}" if desc.DeviceId <= 0xffff else None,
                    "subsystem_vendor_id": subsystem[4:] if desc.SubSysId else None,
                    "subsystem_device_id": subsystem[:4] if desc.SubSysId else None,
                    "revision": f"{desc.Revision:02x}" if desc.Revision else None,
                    "dedicated_video_memory_gb": desc.DedicatedVideoMemory / (1024 ** 3),
                    "dedicated_system_memory_gb": desc.DedicatedSystemMemory / (1024 ** 3),
                    "shared_system_memory_gb": desc.SharedSystemMemory / (1024 ** 3),
                    "adapter_luid": f"{high:08x}:{low:08x}",
                    "adapter_type": "Software" if desc.Flags & 0x2 else "Hardware",
                    "inventory_status": "Detected", "inventory_source": "Windows DirectX DXGI",
                })
            finally:
                _release(adapter)
    except (AttributeError, OSError, TypeError, ValueError):
        return output
    finally:
        _release(factory)
    return output


def windows_gpu_luid_key(value: str) -> str | None:
    """Normalize a GPU performance-counter LUID or a canonical DXGI LUID."""
    text = str(value or "").casefold()
    match = re.search(r"luid[_:=]0x([0-9a-f]+)[_:]0x([0-9a-f]+)", text)
    if match:
        return f"{int(match.group(1), 16) & 0xffffffff:08x}:{int(match.group(2), 16) & 0xffffffff:08x}"
    match = re.fullmatch(r"([0-9a-f]{1,8}):([0-9a-f]{1,8})", text)
    if match:
        return f"{int(match.group(1), 16):08x}:{int(match.group(2), 16):08x}"
    return None
