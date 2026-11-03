"""Read-only, best-effort OS hardware inventory and optional sensor providers."""
from __future__ import annotations

import json
import platform
import re
import subprocess
from functools import lru_cache
from pathlib import Path
from typing import Any

from .windows_gpu import collect_windows_dxgi_inventory, windows_gpu_luid_key


def _read(path: Path, limit: int = 240) -> str | None:
    try:
        value = path.read_text(encoding="utf-8", errors="replace").strip()
    except OSError:
        return None
    return value[:limit] if value else None


def collect_system_inventory() -> dict[str, Any]:
    system = {"manufacturer": None, "model": None, "family": None, "product_version": None}
    board = {"manufacturer": None, "model": None, "version": None}
    bios = {"vendor": None, "version": None, "release_date": None}
    source = "SMBIOS/DMI"
    if platform.system() == "Linux":
        mapping = {
            "sys_vendor": (system, "manufacturer"), "product_name": (system, "model"),
            "product_family": (system, "family"), "product_version": (system, "product_version"),
            "board_vendor": (board, "manufacturer"), "board_name": (board, "model"),
            "board_version": (board, "version"), "bios_vendor": (bios, "vendor"),
            "bios_version": (bios, "version"), "bios_date": (bios, "release_date"),
        }
        root = Path("/sys/class/dmi/id")
        for filename, (target, key) in mapping.items():
            target[key] = _read(root / filename)
    elif platform.system() == "Windows":
        source = "Windows WMI Win32_ComputerSystem / Win32_BaseBoard / Win32_BIOS"
        try:
            import wmi
            cim = wmi.WMI(namespace=r"root\cimv2")
            rows = list(cim.Win32_ComputerSystem())
            if rows:
                system["manufacturer"] = str(getattr(rows[0], "Manufacturer", "") or "")[:240] or None
                system["model"] = str(getattr(rows[0], "Model", "") or "")[:240] or None
                system["family"] = str(getattr(rows[0], "SystemFamily", "") or "")[:240] or None
            rows = list(cim.Win32_BaseBoard())
            if rows:
                board["manufacturer"] = str(getattr(rows[0], "Manufacturer", "") or "")[:240] or None
                board["model"] = str(getattr(rows[0], "Product", "") or "")[:240] or None
                board["version"] = str(getattr(rows[0], "Version", "") or "")[:240] or None
            rows = list(cim.Win32_BIOS())
            if rows:
                bios["vendor"] = str(getattr(rows[0], "Manufacturer", "") or "")[:240] or None
                bios["version"] = str(getattr(rows[0], "SMBIOSBIOSVersion", "") or "")[:240] or None
                bios["release_date"] = str(getattr(rows[0], "ReleaseDate", "") or "")[:240] or None
        except Exception:
            source += " (provider unavailable)"
    elif platform.system() == "Darwin":
        source = "macOS platform identity; conventional baseboard identity is not generally exposed"
        system["model"] = platform.machine()
    return {
        "system": system, "motherboard": board, "bios": bios, "source": source,
        "limitations": "Firmware-reported values may be generic or blank; NEXUS does not guess a motherboard model from a chipset.",
    }



_PCI_VENDOR_FALLBACKS = {
    "1002": "AMD",
    "10de": "NVIDIA",
    "8086": "Intel",
    "106b": "Apple",
    "1022": "AMD",
    "15ad": "VMware",
    "80ee": "Oracle VirtualBox",
    "1234": "QEMU",
    "1af4": "Red Hat Virtio",
    "1414": "Microsoft",
    "1b36": "QEMU",
    "1d0f": "Amazon",
}
_PCI_DATABASES = (
    Path("/usr/share/hwdata/pci.ids"),
    Path("/usr/share/misc/pci.ids"),
    Path("/usr/share/pci.ids"),
    Path("/var/lib/pci.ids"),
)


def _normalise_pci_id(value: str | None) -> str:
    raw = str(value or "").strip().lower().removeprefix("0x")
    return raw.zfill(4) if raw else ""


@lru_cache(maxsize=512)
def _pci_vendor_name(vendor_id: str) -> str:
    """Resolve a PCI vendor name using known aliases or a local pci.ids database."""
    vendor = _normalise_pci_id(vendor_id)
    if not re.fullmatch(r"[0-9a-f]{4}", vendor):
        return "Unknown"
    known = _PCI_VENDOR_FALLBACKS.get(vendor)
    if known:
        return known
    for database in _PCI_DATABASES:
        try:
            for line in database.read_text(encoding="utf-8", errors="replace").splitlines():
                if not line or line.startswith(("#", "\t")):
                    continue
                match = re.match(r"^([0-9a-fA-F]{4})\s+(.+)$", line)
                if match and match.group(1).lower() == vendor:
                    return match.group(2).strip()[:100]
        except OSError:
            continue
    return f"PCI vendor {vendor.upper()}"


@lru_cache(maxsize=512)
def _pci_device_name(vendor_id: str, device_id: str) -> str | None:
    """Resolve a device label from locally installed pci.ids databases."""
    vendor = _normalise_pci_id(vendor_id)
    device = _normalise_pci_id(device_id)
    if not re.fullmatch(r"[0-9a-f]{4}", vendor) or not re.fullmatch(r"[0-9a-f]{4}", device):
        return None
    for database in _PCI_DATABASES:
        try:
            current_vendor = None
            for line in database.read_text(encoding="utf-8", errors="replace").splitlines():
                if not line or line.startswith("#") or line.startswith("\t\t"):
                    continue
                if line.startswith("\t"):
                    match = re.match(r"^\t([0-9a-fA-F]{4})\s+(.+)$", line)
                    if current_vendor == vendor and match and match.group(1).lower() == device:
                        return match.group(2).strip()[:160]
                    continue
                match = re.match(r"^([0-9a-fA-F]{4})\s+(.+)$", line)
                current_vendor = match.group(1).lower() if match else None
        except OSError:
            continue
    return None


def _classify_gpu_vendor(vendor_id: str | None, vendor_text: str = "", name: str = "") -> str:
    """Return a vendor label without assuming that every adapter is NVIDIA/AMD/Intel."""
    code = _normalise_pci_id(vendor_id)
    known = _PCI_VENDOR_FALLBACKS.get(code)
    if known:
        return known
    text = f"{vendor_text} {name}".casefold()
    if any(token in text for token in ("advanced micro", "amd", "radeon", "ati technologies")):
        return "AMD"
    if any(token in text for token in ("nvidia", "geforce", "quadro", "tesla")):
        return "NVIDIA"
    if any(token in text for token in ("intel", "iris", "arc graphics", "uhd graphics")):
        return "Intel"
    if "apple" in text:
        return "Apple"
    if vendor_text.strip():
        return vendor_text.strip()[:100]
    if code and re.fullmatch(r"[0-9a-f]{4}", code):
        return _pci_vendor_name(code)
    return "Unknown"


def _linux_gpu_inventory(root: Path | None = None) -> list[dict[str, Any]]:
    """Enumerate every PCI display-class device, not only three hard-coded vendors."""
    devices_root = root or Path("/sys/bus/pci/devices")
    output: list[dict[str, Any]] = []
    try:
        devices = sorted(devices_root.glob("*"))
    except OSError:
        devices = []
    for device in devices:
        vendor_id = _read(device / "vendor")
        class_id = _read(device / "class")
        if not class_id or not class_id.lower().startswith("0x03"):
            continue
        device_id = _read(device / "device")
        vendor = _classify_gpu_vendor(vendor_id)
        model = _read(device / "product_name") or _read(device / "label")
        if not model and vendor_id and device_id:
            model = _pci_device_name(vendor_id, device_id)
        driver = None
        try:
            driver = (device / "driver").resolve().name
        except OSError:
            pass
        output.append({
            "name": model or f"{vendor} graphics adapter",
            "vendor": vendor,
            "vendor_id": vendor_id,
            "device_id": device_id,
            "subsystem_vendor_id": _read(device / "subsystem_vendor"),
            "subsystem_device_id": _read(device / "subsystem_device"),
            "driver": driver,
            "pci_address": device.name,
            "inventory_status": "Detected",
            "inventory_source": "Linux PCI sysfs",
        })
        if len(output) >= 32:
            break
    return output


def _windows_wmi_gpu_inventory() -> list[dict[str, Any]]:
    output: list[dict[str, Any]] = []
    try:
        import wmi
        rows = wmi.WMI(namespace=r"root\cimv2").Win32_VideoController()
        for row in list(rows)[:32]:
            name = str(getattr(row, "Name", "") or "Display adapter")[:160]
            vendor_text = str(getattr(row, "AdapterCompatibility", "") or "")
            pnp_id = str(getattr(row, "PNPDeviceID", "") or "")[:240]
            ven = re.search(r"VEN_([0-9A-Fa-f]{4})", pnp_id)
            dev = re.search(r"DEV_([0-9A-Fa-f]{4})", pnp_id)
            sub = re.search(r"SUBSYS_([0-9A-Fa-f]{8})", pnp_id)
            rev = re.search(r"REV_([0-9A-Fa-f]{4})", pnp_id)
            vendor_code, device_code = ven.group(1).lower() if ven else "", dev.group(1).lower() if dev else ""
            vendor = _classify_gpu_vendor(vendor_code, vendor_text, name)
            if (not name or "basic display adapter" in name.casefold()
                    or name.casefold() in {"unknown gpu", "display adapter"}) and vendor_code and device_code:
                name = _pci_device_name(vendor_code, device_code) or name
            subsystem = sub.group(1).lower() if sub else ""
            output.append({
                "name": name, "vendor": vendor, "vendor_id": vendor_code or None,
                "device_id": device_code or None, "pnp_device_id": pnp_id or None,
                "subsystem_device_id": subsystem[:4] or None,
                "subsystem_vendor_id": subsystem[4:] or None,
                "revision": rev.group(1).lower() if rev else None,
                "driver_version": str(getattr(row, "DriverVersion", "") or "")[:80] or None,
                "driver_date": str(getattr(row, "DriverDate", "") or "")[:80] or None,
                "video_processor": str(getattr(row, "VideoProcessor", "") or "")[:160] or None,
                "current_resolution": (
                    f"{int(getattr(row, 'CurrentHorizontalResolution', 0) or 0)}x"
                    f"{int(getattr(row, 'CurrentVerticalResolution', 0) or 0)}"
                    if getattr(row, "CurrentHorizontalResolution", None)
                    and getattr(row, "CurrentVerticalResolution", None) else None
                ),
                "current_refresh_rate_hz": int(getattr(row, "CurrentRefreshRate", 0) or 0) or None,
                "inventory_status": "Detected", "inventory_source": "Windows WMI",
            })
    except Exception:
        pass
    return output


def _merge_windows_gpu_inventory(dxgi_devices, wmi_devices):
    """Merge precise DXGI identity/memory with WMI driver and display metadata."""
    merged = [dict(item) for item in dxgi_devices]
    for item in wmi_devices:
        vendor, device = str(item.get("vendor_id") or "").casefold(), str(item.get("device_id") or "").casefold()
        matches = [row for row in merged if vendor and device
            and str(row.get("vendor_id") or "").casefold() == vendor
            and str(row.get("device_id") or "").casefold() == device]
        sv, sd = str(item.get("subsystem_vendor_id") or "").casefold(), str(item.get("subsystem_device_id") or "").casefold()
        exact = [row for row in matches if sv and sd
            and str(row.get("subsystem_vendor_id") or "").casefold() == sv
            and str(row.get("subsystem_device_id") or "").casefold() == sd]
        if exact:
            matches = exact
        target = matches[0] if len(matches) == 1 else None
        if target is None:
            merged.append(dict(item))
            continue
        for key, value in item.items():
            if value in (None, ""):
                continue
            if key == "name":
                if not any(word in str(value).casefold() for word in ("basic display", "unknown gpu", "display adapter")):
                    target[key] = value
            elif not target.get(key):
                target[key] = value
    return merged[:32]


def collect_windows_gpu_performance_metrics() -> dict[str, dict[str, Any]]:
    """Read GPU Engine and AdapterMemory counters keyed by physical DXGI LUID."""
    if platform.system() != "Windows":
        return {}
    try:
        import wmi
        cim = wmi.WMI(namespace=r"root\cimv2")
    except Exception:
        return {}
    output: dict[str, dict[str, Any]] = {}
    try:
        for row in list(cim.Win32_PerfFormattedData_GPUPerformanceCounters_GPUEngine())[:512]:
            key = windows_gpu_luid_key(str(getattr(row, "Name", "") or ""))
            try:
                value = float(getattr(row, "UtilizationPercentage", None))
            except (TypeError, ValueError, OverflowError):
                continue
            if key and 0 <= value <= 1000:
                target = output.setdefault(key, {})
                target["utilization_percent"] = max(value, target.get("utilization_percent", 0.0))
    except Exception:
        pass
    try:
        for row in list(cim.Win32_PerfFormattedData_GPUPerformanceCounters_GPUAdapterMemory())[:128]:
            key = windows_gpu_luid_key(str(getattr(row, "Name", "") or ""))
            if not key:
                continue
            target = output.setdefault(key, {})
            for prop, field in (("DedicatedUsage", "memory_used_gb"), ("SharedUsage", "shared_memory_used_gb")):
                try:
                    target[field] = max(0.0, float(getattr(row, prop, 0) or 0)) / (1024 ** 3)
                except (TypeError, ValueError, OverflowError):
                    pass
    except Exception:
        pass
    return output


def _windows_registry_gpu_inventory() -> list[dict[str, Any]]:
    """Fallback display-adapter inventory using the built-in Windows device registry."""
    output: list[dict[str, Any]] = []
    try:
        import winreg
        access = winreg.KEY_READ | getattr(winreg, "KEY_WOW64_64KEY", 0)
        display_guid = "{4d36e968-e325-11ce-bfc1-08002be10318}"
        with winreg.OpenKey(
            winreg.HKEY_LOCAL_MACHINE,
            r"SYSTEM\CurrentControlSet\Enum\PCI",
            0,
            access,
        ) as root:
            for vendor_index in range(512):
                try:
                    vendor_key_name = winreg.EnumKey(root, vendor_index)
                except OSError:
                    break
                vendor_match = re.search(r"VEN_([0-9A-Fa-f]{4})", vendor_key_name)
                device_match = re.search(r"DEV_([0-9A-Fa-f]{4})", vendor_key_name)
                if not vendor_match:
                    continue
                vendor_code = vendor_match.group(1).lower()
                device_code = device_match.group(1).lower() if device_match else ""
                try:
                    vendor_key = winreg.OpenKey(root, vendor_key_name, 0, access)
                except OSError:
                    continue
                with vendor_key:
                    for instance_index in range(64):
                        try:
                            instance_name = winreg.EnumKey(vendor_key, instance_index)
                        except OSError:
                            break
                        try:
                            instance_key = winreg.OpenKey(vendor_key, instance_name, 0, access)
                        except OSError:
                            continue
                        with instance_key:
                            def query_value(value_name: str):
                                try:
                                    return winreg.QueryValueEx(instance_key, value_name)[0]
                                except OSError:
                                    return None
                            class_guid = str(query_value("ClassGUID") or "").casefold()
                            hardware_ids = query_value("HardwareID") or []
                            compatible_ids = query_value("CompatibleIDs") or []
                            id_text = " ".join(str(value) for value in (*hardware_ids, *compatible_ids)).casefold()
                            is_display = class_guid == display_guid or bool(re.search(r"cc_03", id_text))
                            if not is_display:
                                continue
                            friendly = str(query_value("FriendlyName") or "").strip()
                            description = str(query_value("DeviceDesc") or "").strip()
                            name = friendly or (description if description and not description.startswith("@") else "")
                            vendor = _classify_gpu_vendor(vendor_code, "", name)
                            output.append({
                                "name": name[:160] or f"{vendor} graphics adapter",
                                "vendor": vendor,
                                "vendor_id": vendor_code,
                                "device_id": f"PCI\\{vendor_key_name}\\{instance_name}"[:240],
                                "inventory_status": "Detected",
                                "inventory_source": "Windows device registry",
                            })
                            if len(output) >= 32:
                                return output
    except Exception:
        pass
    return output


def _macos_gpu_inventory() -> list[dict[str, Any]]:
    """Use macOS's built-in display inventory without invoking a shell."""
    try:
        result = subprocess.run(
            ["/usr/sbin/system_profiler", "SPDisplaysDataType", "-json"],
            capture_output=True,
            text=True,
            timeout=8,
            check=False,
        )
        if result.returncode != 0 or len(result.stdout) > 1_500_000:
            return []
        payload = json.loads(result.stdout or "{}")
    except (OSError, subprocess.SubprocessError, ValueError, TypeError):
        return []
    output: list[dict[str, Any]] = []
    rows = payload.get("SPDisplaysDataType", [])
    if not isinstance(rows, list):
        return output
    for row in rows[:32]:
        if not isinstance(row, dict):
            continue
        name = str(row.get("sppci_model") or row.get("_name") or row.get("spdisplays_chipset_model") or "Display adapter")[:160]
        vendor_text = str(row.get("spdisplays_vendor") or "")
        vendor = _classify_gpu_vendor(None, vendor_text, name)
        output.append({
            "name": name,
            "vendor": vendor,
            "device_id": str(row.get("spdisplays_device-id") or "")[:80] or None,
            "inventory_status": "Detected",
            "inventory_source": "macOS system_profiler",
        })
    return output


def collect_gpu_inventory() -> list[dict[str, Any]]:
    """Discover GPU/display devices using native OS inventory, regardless of vendor."""
    system = platform.system()
    if system == "Linux":
        devices = _linux_gpu_inventory()
    elif system == "Windows":
        devices = _merge_windows_gpu_inventory(
            collect_windows_dxgi_inventory(), _windows_wmi_gpu_inventory()
        )
        fallback = _windows_registry_gpu_inventory()
        for item in fallback:
            raw_id = str(item.get("device_id") or "").casefold()
            vendor = str(item.get("vendor_id") or "").casefold()
            dev = re.search(r"DEV_([0-9a-f]{4})", raw_id)
            device = dev.group(1) if dev else ""
            duplicate = any(
                vendor and device
                and str(existing.get("vendor_id") or "").casefold() == vendor
                and str(existing.get("device_id") or "").casefold() == device
                for existing in devices
            )
            if not duplicate:
                devices.append(item)
            if len(devices) >= 32:
                break
    elif system == "Darwin":
        devices = _macos_gpu_inventory()
    else:
        devices = []
    return devices[:32]


def collect_linux_gpu_metrics(
    inventory: list[dict[str, Any]] | None = None,
    *,
    sysfs_root: Path | None = None,
) -> dict[str, dict[str, dict[str, Any]]]:
    """Read generic Linux DRM/sysfs counters when the active driver exposes them."""
    if platform.system() != "Linux":
        return {}
    cards = inventory if inventory is not None else collect_gpu_inventory()
    output: dict[str, dict[str, dict[str, Any]]] = {}

    def read_number(path: Path) -> float | None:
        raw = _read(path, 64)
        if raw is None:
            return None
        try:
            value = float(raw)
            return value if value == value and abs(value) != float("inf") else None
        except (TypeError, ValueError, OverflowError):
            return None

    for card in cards[:32]:
        address = str(card.get("pci_address") or "")
        if not address:
            continue
        device = (sysfs_root or Path("/sys/bus/pci/devices")) / address
        metrics: dict[str, dict[str, Any]] = {}

        def add(field: str, value: float | None, unit: str, source: str = "Linux DRM/sysfs") -> None:
            if value is not None:
                metrics[field] = {"value": value, "unit": unit, "source": source}

        busy = read_number(device / "gpu_busy_percent")
        if busy is not None and 0 <= busy <= 100:
            add("utilization_percent", busy, "%")
        used = read_number(device / "mem_info_vram_used")
        total = read_number(device / "mem_info_vram_total")
        if used is not None and used >= 0:
            add("memory_used_gb", used / (1024 ** 3), "GiB")
        if total is not None and total > 0:
            add("memory_total_gb", total / (1024 ** 3), "GiB")
        if used is not None and total is not None and total > 0:
            add("memory_utilization_percent", min(100.0, max(0.0, used / total * 100)), "%")

        try:
            hwmon_paths = sorted((device / "hwmon").glob("hwmon*"))
        except OSError:
            hwmon_paths = []
        for hwmon in hwmon_paths[:8]:
            if "temperature_c" not in metrics:
                for temp_path in sorted(hwmon.glob("temp*_input"))[:16]:
                    raw = read_number(temp_path)
                    if raw is not None:
                        value = raw / 1000.0
                        if -40 <= value <= 200:
                            add("temperature_c", value, "°C")
                            break
            if "power_w" not in metrics:
                for power_path in (hwmon / "power1_average", hwmon / "power1_input"):
                    raw = read_number(power_path)
                    if raw is not None and raw >= 0:
                        add("power_w", raw / 1_000_000.0, "W")
                        break
            if "graphics_clock_mhz" not in metrics:
                raw = read_number(hwmon / "freq1_input")
                if raw is not None and raw >= 0:
                    add("graphics_clock_mhz", raw / 1_000_000.0, "MHz")
            if "fan_rpm" not in metrics:
                raw = read_number(hwmon / "fan1_input")
                if raw is not None and 0 <= raw <= 100000:
                    add("fan_rpm", raw, "RPM")
        if metrics:
            output[address.casefold()] = metrics
    return output



def collect_amd_adlx_devices() -> list[dict[str, Any]]:
    """Read AMD Windows GPU identity and supported live metrics through AMD's ADLX SDK."""
    if platform.system() != "Windows":
        return []
    try:
        from adlx import ADLX
    except ImportError:
        return []
    helper = None
    initialized = False
    output: list[dict[str, Any]] = []

    def read_metric(metrics, method_name: str):
        try:
            value = getattr(metrics, method_name)()
            if value is None:
                return None
            number = float(value)
            return number if number == number and abs(number) != float("inf") else None
        except (AttributeError, TypeError, ValueError, OverflowError, RuntimeError):
            return None

    def pci_id(value):
        try:
            number = int(value, 0) if isinstance(value, str) else int(value)
            return f"{number:04x}" if 0 <= number <= 0xffff else None
        except (TypeError, ValueError, OverflowError):
            return None

    try:
        helper = ADLX.ADLXHelper()
        result = helper.Initialize()
        if result != ADLX.ADLX_RESULT.ADLX_OK:
            return []
        initialized = True
        system = helper.GetSystemServices()
        monitoring = system.GetPerformanceMonitoringServices()
        for index, gpu in enumerate(list(system.GetGPUs())[:32]):
            name = str(gpu.Name() or f"AMD GPU {index}")[:160]
            vendor_id = pci_id(gpu.VendorId())
            device_id = pci_id(gpu.DeviceId())
            metrics = monitoring.GetCurrentGPUMetrics(gpu)
            if metrics is None:
                output.append({
                    "name": name, "vendor": "AMD", "vendor_id": vendor_id,
                    "device_id": device_id, "inventory_source": "AMD ADLX",
                })
                continue
            row: dict[str, Any] = {
                "name": name, "vendor": "AMD", "vendor_id": vendor_id,
                "device_id": device_id, "inventory_source": "AMD ADLX",
                "utilization_percent": read_metric(metrics, "GPUUsage"),
                "temperature_c": read_metric(metrics, "GPUTemperature"),
                "hotspot_temperature_c": read_metric(metrics, "GPUHotspotTemperature"),
                "power_w": read_metric(metrics, "GPUPower"),
                "graphics_clock_mhz": read_metric(metrics, "GPUClockSpeed"),
                "memory_clock_mhz": read_metric(metrics, "GPUVRAMClockSpeed"),
                "fan_percent": read_metric(metrics, "GPUFanSpeed"),
            }
            # ADLX documents GPUVRAM in MB. Convert only when the SDK returns a value.
            vram_mb = read_metric(metrics, "GPUVRAM")
            if vram_mb is not None and vram_mb >= 0:
                row["memory_used_gb"] = vram_mb / 1024.0
            shared_mb = read_metric(metrics, "GPUSharedMemory")
            if shared_mb is not None and shared_mb >= 0:
                row["shared_memory_used_gb"] = shared_mb / 1024.0
            output.append(row)
    except Exception:
        return output
    finally:
        if initialized and helper is not None:
            try:
                helper.Terminate()
            except Exception:
                pass
    return output


def collect_amd_smi_devices() -> list[dict[str, Any]]:
    """AMD SMI live metrics on supported Linux AMDGPU/ROCm hosts."""
    if platform.system() != "Linux":
        return []
    try:
        import amdsmi
    except ImportError:
        return []
    output: list[dict[str, Any]] = []
    initialized = False
    try:
        amdsmi.amdsmi_init()
        initialized = True
        handles = amdsmi.amdsmi_get_processor_handles()
        for index, handle in enumerate(handles[:32]):
            try:
                asic = amdsmi.amdsmi_get_gpu_asic_info(handle)
                name = str(asic.get("market_name") or asic.get("product_name") or f"AMD GPU {index}")
                try:
                    pci_address = str(amdsmi.amdsmi_get_gpu_device_bdf(handle) or "").lower() or None
                except Exception:
                    pci_address = None
                vram = amdsmi.amdsmi_get_gpu_vram_usage(handle)
                activity = amdsmi.amdsmi_get_gpu_activity(handle)
                power = amdsmi.amdsmi_get_power_info(handle)
                try:
                    metrics = amdsmi.amdsmi_get_gpu_metrics_info(handle) or {}
                except Exception:
                    metrics = {}
                def reading(value: Any, unit: str) -> dict[str, Any]:
                    try:
                        number = float(value)
                        if number != number or abs(number) == float("inf"):
                            raise ValueError
                        return {"value": round(number, 2), "unit": unit, "status": "Available", "source": "AMD SMI"}
                    except (TypeError, ValueError, OverflowError):
                        return {"value": None, "unit": unit, "status": "Unavailable", "source": "AMD SMI",
                                "reason": "The AMD driver did not expose this sensor."}
                used = float(vram["vram_used"]) if vram.get("vram_used") is not None else None
                total = float(vram["vram_total"]) if vram.get("vram_total") is not None else None
                temperature = next((metrics.get(key) for key in (
                    "temperature_edge", "temperature_hotspot", "temperature_mem"
                ) if metrics.get(key) not in (None, "N/A")), None)
                try:
                    fan_rpm = amdsmi.amdsmi_get_gpu_fan_rpms(handle, 0)
                except Exception:
                    fan_rpm = None
                output.append({
                    "index": index, "name": name[:160], "vendor": "AMD", "status": "Available",
                    "pci_address": pci_address, "inventory_source": "AMD SMI",
                    "utilization_percent": reading(activity.get("gfx_activity"), "%"),
                    "memory_utilization_percent": reading(activity.get("umc_activity"), "%"),
                    "memory_used_gb": reading(used / (1024 ** 3) if used is not None else None, "GiB"),
                    "memory_total_gb": reading(total / (1024 ** 3) if total is not None else None, "GiB"),
                    "temperature_c": reading(temperature, "°C"),
                    "power_w": reading(power.get("current_socket_power"), "W"),
                    "graphics_clock_mhz": reading(metrics.get("current_gfxclk"), "MHz"),
                    "memory_clock_mhz": reading(metrics.get("current_uclk"), "MHz"),
                    "fan_rpm": reading(fan_rpm, "RPM"),
                })
            except Exception as exc:
                output.append({"index": index, "name": f"AMD GPU {index}", "vendor": "AMD",
                               "status": "Inventory only", "reason": str(exc)[:240]})
    except Exception:
        return []
    finally:
        if initialized:
            try:
                amdsmi.amdsmi_shut_down()
            except Exception:
                pass
    return output


def collect_lhm_sensors() -> list[dict[str, Any]]:
    """Read LibreHardwareMonitor WMI sensors when its Windows provider is active."""
    if platform.system() != "Windows":
        return []
    try:
        import wmi
        provider = wmi.WMI(namespace=r"root\LibreHardwareMonitor")
        result = []
        for sensor in list(provider.Sensor())[:512]:
            kind = str(getattr(sensor, "SensorType", "") or "")
            if kind not in {"Temperature", "Fan", "Load", "Clock", "Power", "Data", "SmallData"}:
                continue
            try:
                value = float(sensor.Value)
            except (TypeError, ValueError, AttributeError):
                continue
            result.append({
                "type": kind, "name": str(getattr(sensor, "Name", "") or "")[:120],
                "value": value, "unit": str(getattr(sensor, "Unit", "") or "")[:24],
                "hardware": str(getattr(sensor, "Hardware", "") or "")[:160],
                "hardware_type": str(getattr(sensor, "HardwareType", "") or "")[:80],
            })
        return result
    except Exception:
        return []


def collect_linux_hwmon() -> dict[str, list[dict[str, Any]]]:
    """Read Linux kernel hwmon input attributes only; never write fan control files."""
    result: dict[str, list[dict[str, Any]]] = {"temperatures": [], "fans": []}
    if platform.system() != "Linux":
        return result
    for chip in Path("/sys/class/hwmon").glob("hwmon*"):
        chip_name = _read(chip / "name") or chip.name
        for input_path in chip.glob("temp*_input"):
            raw = _read(input_path)
            try:
                current = float(raw) / 1000 if raw is not None else None
            except ValueError:
                current = None
            if current is None or not -40 <= current <= 200:
                continue
            stem = input_path.name[:-6]
            label = _read(chip / f"{stem}_label") or stem
            result["temperatures"].append({
                "provider": f"Linux hwmon/{chip_name}", "label": label,
                "current_c": round(current, 1), "high_c": None, "critical_c": None,
            })
        for input_path in chip.glob("fan*_input"):
            raw = _read(input_path)
            try:
                rpm = float(raw) if raw is not None else None
            except ValueError:
                rpm = None
            if rpm is None or not 0 <= rpm <= 100000:
                continue
            stem = input_path.name[:-6]
            label = _read(chip / f"{stem}_label") or stem
            result["fans"].append({
                "provider": f"Linux hwmon/{chip_name}", "label": label, "rpm": round(rpm, 1),
            })
    return {"temperatures": result["temperatures"][:128], "fans": result["fans"][:128]}
