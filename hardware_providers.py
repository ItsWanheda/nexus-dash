"""Read-only, best-effort OS hardware inventory and optional sensor providers."""
from __future__ import annotations

import platform
from pathlib import Path
from typing import Any


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


def collect_gpu_inventory() -> list[dict[str, Any]]:
    output: list[dict[str, Any]] = []
    if platform.system() == "Linux":
        root = Path("/sys/bus/pci/devices")
        vendors = {"0x1002": "AMD", "0x10de": "NVIDIA", "0x8086": "Intel"}
        try:
            devices = sorted(root.glob("*"))
        except OSError:
            devices = []
        for device in devices:
            vendor_id = _read(device / "vendor")
            class_id = _read(device / "class")
            if vendor_id not in vendors or not class_id or not class_id.startswith("0x03"):
                continue
            vendor = vendors[vendor_id]
            product_id = _read(device / "device") or "unknown"
            model = _read(device / "product_name") or _read(device / "label")
            output.append({
                "name": model or f"{vendor} PCI graphics device {product_id}",
                "vendor": vendor, "device_id": product_id, "pci_address": device.name,
                "inventory_status": "Detected",
            })
    elif platform.system() == "Windows":
        try:
            import wmi
            rows = wmi.WMI(namespace=r"root\cimv2").Win32_VideoController()
            for row in list(rows)[:16]:
                name = str(getattr(row, "Name", "") or "Unknown GPU")[:160]
                vendor_text = str(getattr(row, "AdapterCompatibility", "") or "")
                lowered = vendor_text.casefold() + " " + name.casefold()
                vendor = "AMD" if any(token in lowered for token in ("amd", "advanced micro", "radeon")) else (
                    "NVIDIA" if any(token in lowered for token in ("nvidia", "geforce")) else
                    "Intel" if any(token in lowered for token in ("intel", "arc")) else vendor_text[:80] or "Unknown")
                output.append({
                    "name": name, "vendor": vendor,
                    "driver_version": str(getattr(row, "DriverVersion", "") or "")[:80] or None,
                    "device_id": str(getattr(row, "PNPDeviceID", "") or "")[:180] or None,
                    "inventory_status": "Detected",
                })
        except Exception:
            pass
    return output[:16]


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
        for index, handle in enumerate(handles[:16]):
            try:
                asic = amdsmi.amdsmi_get_gpu_asic_info(handle)
                name = str(asic.get("market_name") or asic.get("product_name") or f"AMD GPU {index}")
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
            if kind not in {"Temperature", "Fan", "Load", "Clock", "Power"}:
                continue
            try:
                value = float(sensor.Value)
            except (TypeError, ValueError, AttributeError):
                continue
            result.append({
                "type": kind, "name": str(getattr(sensor, "Name", "") or "")[:120],
                "value": value, "hardware": str(getattr(sensor, "Hardware", "") or "")[:160],
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
