"""Best-effort, platform-aware hardware telemetry for NEXUS-DASH.

Every optional sensor is represented explicitly. Missing APIs, drivers, or permissions
produce an Unavailable reading instead of a guessed value.
"""
from __future__ import annotations

import copy
import math
import platform
import threading
import time
from datetime import datetime, timezone
from typing import Any

import psutil

from .hardware_providers import (
    collect_system_inventory,
    collect_gpu_inventory,
    collect_amd_smi_devices,
    collect_lhm_sensors,
    collect_linux_hwmon,
    collect_linux_gpu_metrics,
    collect_windows_gpu_performance_metrics,
)

_NVML_LOCK = threading.Lock()
_NVML_READY = False


def _finite(value: Any) -> float | None:
    if isinstance(value, bool) or value is None:
        return None
    try:
        result = float(value)
    except (TypeError, ValueError, OverflowError):
        return None
    return result if math.isfinite(result) else None


def _reading(value: Any, unit: str, source: str, reason: str | None = None) -> dict[str, Any]:
    number = _finite(value)
    if number is None:
        return {
            "value": None,
            "unit": unit,
            "status": "Unavailable",
            "source": source,
            "reason": reason or "This operating system or hardware provider did not expose the measurement.",
        }
    return {"value": round(number, 2), "unit": unit, "status": "Available", "source": source}


def _unavailable(reason: str, unit: str = "") -> dict[str, Any]:
    return _reading(None, unit, "platform-provider", reason)


def _sensor_data() -> tuple[list[dict[str, Any]], list[dict[str, Any]], list[dict[str, Any]]]:
    cpu_temperatures: list[dict[str, Any]] = []
    board_temperatures: list[dict[str, Any]] = []
    fans: list[dict[str, Any]] = []
    try:
        providers = psutil.sensors_temperatures(fahrenheit=False) or {}
    except (AttributeError, NotImplementedError, OSError, psutil.Error):
        providers = {}
    for chip, entries in providers.items():
        for entry in entries or []:
            current = _finite(getattr(entry, "current", None))
            if current is None:
                continue
            label = str(getattr(entry, "label", "") or chip)[:120]
            chip_name = str(chip)[:100]
            row = {"provider": chip_name, "label": label, "current_c": round(current, 1),
                   "high_c": _finite(getattr(entry, "high", None)),
                   "critical_c": _finite(getattr(entry, "critical", None))}
            target = cpu_temperatures if any(token in (chip_name + " " + label).casefold()
                for token in ("cpu", "coretemp", "k10temp", "zenpower", "package")) else board_temperatures
            target.append(row)
    try:
        fan_providers = psutil.sensors_fans() or {}
    except (AttributeError, NotImplementedError, OSError, psutil.Error):
        fan_providers = {}
    for chip, entries in fan_providers.items():
        for entry in entries or []:
            rpm = _finite(getattr(entry, "current", None))
            if rpm is not None:
                fans.append({"provider": str(chip)[:100],
                             "label": str(getattr(entry, "label", "") or chip)[:120],
                             "rpm": round(rpm, 1)})
    for sensor in collect_lhm_sensors():
        group = (sensor["hardware_type"] + " " + sensor["hardware"]).casefold()
        if sensor["type"] == "Temperature":
            row = {"provider": "LibreHardwareMonitor WMI", "label": sensor["name"],
                   "current_c": round(sensor["value"], 1), "high_c": None, "critical_c": None}
            (cpu_temperatures if "cpu" in group else board_temperatures).append(row)
        elif sensor["type"] == "Fan" and 0 <= sensor["value"] <= 100000:
            fans.append({"provider": "LibreHardwareMonitor WMI", "label": sensor["name"],
                         "rpm": round(sensor["value"], 1)})
    hwmon = collect_linux_hwmon()
    if not board_temperatures:
        board_temperatures.extend(hwmon["temperatures"])
    if not fans:
        fans.extend(hwmon["fans"])
    if platform.system() == "Windows" and not board_temperatures:
        try:
            import wmi
            connection = wmi.WMI(namespace=r"root\wmi")
            for zone in connection.MSAcpi_ThermalZoneTemperature():
                raw = _finite(getattr(zone, "CurrentTemperature", None))
                if raw is None or raw <= 0:
                    continue
                celsius = raw / 10.0 - 273.15
                if -40 <= celsius <= 150:
                    board_temperatures.append({"provider": "Windows ACPI WMI", "label": "ACPI thermal zone",
                                                "current_c": round(celsius, 1), "high_c": None, "critical_c": None})
        except Exception:
            pass
    return cpu_temperatures[:128], board_temperatures[:128], fans[:128]




def _memory_pressure(percent: float) -> dict[str, Any]:
    if platform.system() == "Linux":
        try:
            with open("/proc/pressure/memory", "r", encoding="ascii") as stream:
                line = next((row for row in stream if row.startswith("some ")), "")
            values = {}
            for part in line.split()[1:]:
                key, separator, value = part.partition("=")
                if separator and key in {"avg10", "avg60", "avg300", "total"}:
                    values[key] = _finite(value)
            if values:
                return {
                    "status": "Available",
                    "source": "Linux PSI /proc/pressure/memory",
                    "some_avg10_percent": values.get("avg10"),
                    "some_avg60_percent": values.get("avg60"),
                    "some_avg300_percent": values.get("avg300"),
                    "level": "high" if (values.get("avg10") or 0) >= 10 else "elevated" if (values.get("avg10") or 0) >= 1 else "normal",
                }
        except (OSError, StopIteration, ValueError):
            pass
    # A pressure band derived from OS-reported utilisation is not a hardware sensor.
    level = "critical" if percent >= 95 else "high" if percent >= 85 else "elevated" if percent >= 70 else "normal"
    return {
        "status": "Estimated",
        "source": "psutil virtual-memory utilisation",
        "level": level,
        "utilisation_percent": round(percent, 1),
        "reason": "No native memory-pressure interface was available; the level is derived from reported RAM utilisation.",
    }


_GPU_METRIC_FIELDS = (
    "utilization_percent", "memory_utilization_percent", "memory_used_gb", "memory_total_gb", "shared_memory_used_gb",
    "temperature_c", "power_w", "graphics_clock_mhz", "memory_clock_mhz", "fan_percent", "fan_rpm",
)
_GPU_CACHE_LOCK = threading.Lock()
_GPU_CACHE: list[dict[str, Any]] | None = None
_GPU_CACHE_AT = 0.0
_GPU_CACHE_TTL_SECONDS = 2.0


def _gpu_inventory_row(item: dict[str, Any], index: int) -> dict[str, Any]:
    vendor = str(item.get("vendor") or "Unknown")[:100]
    name = str(item.get("name") or f"{vendor} graphics adapter")[:160]
    row: dict[str, Any] = {
        "index": index,
        "name": name,
        "vendor": vendor,
        "status": "Inventory only",
        "device_id": item.get("device_id"),
        "vendor_id": item.get("vendor_id"),
        "pci_address": item.get("pci_address"),
        "driver": item.get("driver"),
        "driver_version": item.get("driver_version"),
        "inventory_source": item.get("inventory_source"),
        "pnp_device_id": item.get("pnp_device_id"),
        "subsystem_vendor_id": item.get("subsystem_vendor_id"),
        "subsystem_device_id": item.get("subsystem_device_id"),
        "revision": item.get("revision"),
        "adapter_luid": item.get("adapter_luid"),
        "adapter_type": item.get("adapter_type"),
        "dedicated_video_memory_gb": item.get("dedicated_video_memory_gb"),
        "dedicated_system_memory_gb": item.get("dedicated_system_memory_gb"),
        "shared_system_memory_gb": item.get("shared_system_memory_gb"),
        "video_processor": item.get("video_processor"),
        "driver_date": item.get("driver_date"),
        "current_resolution": item.get("current_resolution"),
        "current_refresh_rate_hz": item.get("current_refresh_rate_hz"),
        "reason": "The display adapter is identified, but the operating system or installed drivers did not expose live sensor values.",
    }
    for field in _GPU_METRIC_FIELDS:
        unit = "%" if field.endswith("percent") else (
            "GiB" if field.endswith("_gb") else (
                "°C" if field == "temperature_c" else (
                    "W" if field == "power_w" else (
                        "MHz" if field.endswith("_mhz") else "RPM" if field == "fan_rpm" else "%"
                    )
                )
            )
        )
        row[field] = _unavailable("No compatible provider exposed this GPU measurement.", unit)
    return row


def _pci_address_key(value: Any) -> str:
    address = str(value or "").strip().casefold()
    # NVML commonly pads the PCI domain to eight hex digits while sysfs/AMD SMI
    # use four; normalise the domain so both providers refer to the same device.
    parts = address.split(":")
    if len(parts) == 3 and len(parts[0]) >= 4:
        domain = parts[0][-4:]
        return f"{domain}:{parts[1]}:{parts[2]}"
    return address


def _normalised_gpu_name(value: Any) -> str:
    return "".join(character for character in str(value or "").casefold() if character.isalnum())


def _gpu_has_live_metrics(device: dict[str, Any]) -> bool:
    return any(
        isinstance(device.get(field), dict) and device[field].get("value") is not None
        for field in _GPU_METRIC_FIELDS
    )


def _find_gpu_match(devices: list[dict[str, Any]], candidate: dict[str, Any]) -> dict[str, Any] | None:
    address = _pci_address_key(candidate.get("pci_address"))
    if address:
        match = next((item for item in devices if _pci_address_key(item.get("pci_address")) == address), None)
        if match:
            return match
    device_id = str(candidate.get("device_id") or "").casefold()
    if device_id:
        matches = [item for item in devices if str(item.get("device_id") or "").casefold() == device_id]
        if len(matches) == 1:
            return matches[0]
    name = _normalised_gpu_name(candidate.get("name"))
    vendor = str(candidate.get("vendor") or "").casefold()
    if name and vendor:
        matches = [
            item for item in devices
            if str(item.get("vendor") or "").casefold() == vendor
            and _normalised_gpu_name(item.get("name")) == name
        ]
        if len(matches) == 1:
            return matches[0]
    return None


def _merge_gpu_provider_devices(
    inventory_devices: list[dict[str, Any]],
    provider_devices: list[dict[str, Any]],
) -> None:
    """Merge live provider readings by physical-device identity, never by vendor alone."""
    for provider_device in provider_devices:
        target = _find_gpu_match(inventory_devices, provider_device)
        if target is None:
            target = _gpu_inventory_row(provider_device, len(inventory_devices))
            inventory_devices.append(target)
        for key in ("name", "vendor", "device_id", "vendor_id", "pci_address", "driver", "driver_version", "inventory_source"):
            value = provider_device.get(key)
            if value not in (None, ""):
                # Prefer a provider's precise model string over a generic OS label.
                if key == "name" or not target.get(key):
                    target[key] = value
        for field in _GPU_METRIC_FIELDS:
            reading = provider_device.get(field)
            if isinstance(reading, dict) and reading.get("value") is not None:
                target[field] = reading
        target["status"] = "Available" if _gpu_has_live_metrics(target) else "Inventory only"
        target["reason"] = None if target["status"] == "Available" else (
            provider_device.get("reason") or target.get("reason")
        )


def _apply_linux_gpu_metrics(devices: list[dict[str, Any]]) -> None:
    if platform.system() != "Linux":
        return
    try:
        metrics_by_address = collect_linux_gpu_metrics(devices)
    except Exception:
        return
    for device in devices:
        metrics = metrics_by_address.get(_pci_address_key(device.get("pci_address")), {})
        for field, metric in metrics.items():
            if field in _GPU_METRIC_FIELDS and isinstance(metric, dict) and metric.get("value") is not None:
                device[field] = _reading(metric["value"], metric.get("unit", ""), metric.get("source", "Linux DRM/sysfs"))
        if _gpu_has_live_metrics(device):
            device["status"] = "Available"
            device["reason"] = None


def _apply_lhm_gpu_sensors(devices: list[dict[str, Any]], sensors: list[dict[str, Any]]) -> None:
    """Attach LibreHardwareMonitor readings to the matching GPU, regardless of vendor."""
    if not devices:
        return
    for sensor in sensors:
        hardware = str(sensor.get("hardware") or "")
        hardware_type = str(sensor.get("hardware_type") or "").casefold()
        sensor_type = str(sensor.get("type") or "")
        if not (hardware_type.startswith("gpu") or "graphics" in hardware_type or "gpu" in hardware.casefold()):
            continue
        candidates = []
        hardware_name = _normalised_gpu_name(hardware)
        for device in devices:
            device_name = _normalised_gpu_name(device.get("name"))
            if hardware_name and device_name and (hardware_name in device_name or device_name in hardware_name):
                candidates.append(device)
        if not candidates:
            vendor_hint = (
                "AMD" if any(token in hardware_type + hardware.casefold() for token in ("amd", "ati", "radeon")) else
                "NVIDIA" if any(token in hardware_type + hardware.casefold() for token in ("nvidia", "geforce")) else
                "Intel" if any(token in hardware_type + hardware.casefold() for token in ("intel", "arc")) else
                None
            )
            if vendor_hint:
                candidates = [item for item in devices if str(item.get("vendor", "")).casefold() == vendor_hint.casefold()]
        if len(candidates) != 1:
            continue
        device = candidates[0]
        try:
            value = float(sensor.get("value"))
        except (TypeError, ValueError, OverflowError):
            continue
        if not math.isfinite(value):
            continue
        label = str(sensor.get("name") or "").casefold()
        field = None
        unit = str(sensor.get("unit") or "")
        if sensor_type == "Temperature" and -40 <= value <= 200:
            field = "temperature_c"
            unit = "°C"
        elif sensor_type == "Power" and value >= 0:
            field = "power_w"
            unit = "W"
        elif sensor_type == "Fan" and 0 <= value <= 100000:
            field = "fan_rpm"
            unit = "RPM"
        elif sensor_type == "Clock" and value >= 0:
            field = "memory_clock_mhz" if any(token in label for token in ("memory", "vram")) else "graphics_clock_mhz"
            unit = "MHz"
        elif sensor_type == "Load" and 0 <= value <= 100:
            field = "memory_utilization_percent" if "memory" in label else "utilization_percent"
            unit = "%"
        elif sensor_type in {"Data", "SmallData"} and any(token in label for token in ("memory used", "vram used", "memory total", "vram total")):
            if any(token in label for token in ("used", "current")):
                field = "memory_used_gb"
            elif any(token in label for token in ("total", "capacity")):
                field = "memory_total_gb"
            if field:
                factor = 1.0
                unit_text = unit.casefold().replace(" ", "")
                if unit_text in {"mb", "mib"}:
                    factor = 1 / 1024
                elif unit_text in {"kb", "kib"}:
                    factor = 1 / (1024 ** 2)
                elif unit_text in {"b", "byte", "bytes"}:
                    factor = 1 / (1024 ** 3)
                elif unit_text in {"gb", "gib"}:
                    factor = 1.0
                else:
                    field = None  # Never guess an undocumented unit.
                value *= factor
                unit = "GiB"
        if field:
            device[field] = _reading(value, unit, "LibreHardwareMonitor WMI")
            device["status"] = "Available"
            device["reason"] = None


def _apply_windows_gpu_metrics(devices: list[dict[str, Any]]) -> None:
    if platform.system() != "Windows":
        return
    try:
        metrics = collect_windows_gpu_performance_metrics()
    except Exception:
        return
    for device in devices:
        row = metrics.get(str(device.get("adapter_luid") or "").casefold(), {})
        value = row.get("utilization_percent")
        if value is not None and 0 <= value <= 100:
            device["utilization_percent"] = _reading(value, "%", "Windows GPU Engine counters")
        shared_used = row.get("shared_memory_used_gb")
        if shared_used is not None and shared_used >= 0:
            device["shared_memory_used_gb"] = _reading(shared_used, "GiB", "Windows GPU AdapterMemory counters")
        used = row.get("memory_used_gb")
        if used is not None and used >= 0:
            device["memory_used_gb"] = _reading(used, "GiB", "Windows GPU AdapterMemory counters")
            total = device.get("dedicated_video_memory_gb")
            if isinstance(total, (int, float)) and total > 0:
                device["memory_total_gb"] = _reading(total, "GiB", "Windows DirectX DXGI")
                device["memory_utilization_percent"] = _reading(
                    min(100.0, used / total * 100), "%", "Windows GPU AdapterMemory counters"
                )
        if _gpu_has_live_metrics(device):
            device["status"], device["reason"] = "Available", None


def _gpu_devices() -> list[dict[str, Any]]:
    """Detect all OS-visible display adapters and merge optional live telemetry."""
    global _NVML_READY
    inventory = collect_gpu_inventory()
    devices = [_gpu_inventory_row(item, index) for index, item in enumerate(inventory[:32])]
    _apply_linux_gpu_metrics(devices)
    _apply_windows_gpu_metrics(devices)

    vendor_devices: list[dict[str, Any]] = []
    try:
        import pynvml

        with _NVML_LOCK:
            if not _NVML_READY:
                pynvml.nvmlInit()
                _NVML_READY = True
        count = min(max(int(pynvml.nvmlDeviceGetCount()), 0), 32)

        def query(call):
            try:
                return call()
            except Exception:
                return None

        for index in range(count):
            try:
                handle = pynvml.nvmlDeviceGetHandleByIndex(index)
                raw_name = pynvml.nvmlDeviceGetName(handle)
                name = raw_name.decode("utf-8", "replace") if isinstance(raw_name, bytes) else str(raw_name)
                utilization = query(lambda: pynvml.nvmlDeviceGetUtilizationRates(handle))
                memory = query(lambda: pynvml.nvmlDeviceGetMemoryInfo(handle))
                power_mw = query(lambda: pynvml.nvmlDeviceGetPowerUsage(handle))
                pci_info = query(lambda: pynvml.nvmlDeviceGetPciInfo(handle))
                pci_address = getattr(pci_info, "busId", None) if pci_info else None
                if isinstance(pci_address, bytes):
                    pci_address = pci_address.decode("ascii", "replace")
                vendor_devices.append({
                    "index": index,
                    "name": name[:160],
                    "vendor": "NVIDIA",
                    "pci_address": str(pci_address or "").lower() or None,
                    "status": "Available",
                    "inventory_source": "NVIDIA NVML",
                    "utilization_percent": _reading(getattr(utilization, "gpu", None), "%", "NVIDIA NVML"),
                    "memory_utilization_percent": _reading(getattr(utilization, "memory", None), "%", "NVIDIA NVML"),
                    "memory_used_gb": _reading(memory.used / (1024 ** 3) if memory else None, "GiB", "NVIDIA NVML"),
                    "memory_total_gb": _reading(memory.total / (1024 ** 3) if memory else None, "GiB", "NVIDIA NVML"),
                    "temperature_c": _reading(query(lambda: pynvml.nvmlDeviceGetTemperature(handle, pynvml.NVML_TEMPERATURE_GPU)), "°C", "NVIDIA NVML"),
                    "power_w": _reading(power_mw / 1000 if power_mw is not None else None, "W", "NVIDIA NVML"),
                    "graphics_clock_mhz": _reading(query(lambda: pynvml.nvmlDeviceGetClockInfo(handle, pynvml.NVML_CLOCK_GRAPHICS)), "MHz", "NVIDIA NVML"),
                    "memory_clock_mhz": _reading(query(lambda: pynvml.nvmlDeviceGetClockInfo(handle, pynvml.NVML_CLOCK_MEM)), "MHz", "NVIDIA NVML"),
                    "fan_percent": _reading(query(lambda: pynvml.nvmlDeviceGetFanSpeed(handle)), "%", "NVIDIA NVML"),
                })
            except Exception as exc:
                vendor_devices.append({
                    "index": index, "name": f"NVIDIA GPU {index}", "vendor": "NVIDIA",
                    "status": "Inventory only", "reason": str(exc)[:240],
                })
    except Exception:
        pass

    try:
        vendor_devices.extend(collect_amd_smi_devices())
    except Exception:
        pass
    _merge_gpu_provider_devices(devices, vendor_devices)

    try:
        lhm_sensors = collect_lhm_sensors()
    except Exception:
        lhm_sensors = []
    _apply_lhm_gpu_sensors(devices, lhm_sensors)

    for index, device in enumerate(devices[:32]):
        device["index"] = index
        if _gpu_has_live_metrics(device):
            device["status"] = "Available"
            device["reason"] = None
        elif device.get("status") != "Unavailable":
            device["status"] = "Inventory only"
            device["reason"] = device.get("reason") or (
                "The GPU is detected, but no supported live sensor provider exposed measurements for this device."
            )
    return devices[:32]


def collect_gpu_devices() -> list[dict[str, Any]]:
    """Return a short-lived cached GPU snapshot shared by dashboard/API polling."""
    global _GPU_CACHE, _GPU_CACHE_AT
    now = time.monotonic()
    with _GPU_CACHE_LOCK:
        if _GPU_CACHE is not None and now - _GPU_CACHE_AT < _GPU_CACHE_TTL_SECONDS:
            return copy.deepcopy(_GPU_CACHE)
        _GPU_CACHE = _gpu_devices()
        _GPU_CACHE_AT = now
        return copy.deepcopy(_GPU_CACHE)


def collect_gpu_memory_summary() -> dict[str, Any]:
    """Aggregate GPU memory metrics across detected adapters and all installed vendors."""
    devices = collect_gpu_devices()
    vendors = sorted({str(item.get("vendor") or "Unknown") for item in devices if item.get("vendor")})
    readings = []
    for device in devices:
        used = (device.get("memory_used_gb") or {}).get("value")
        total = (device.get("memory_total_gb") or {}).get("value")
        if isinstance(used, (int, float)) and isinstance(total, (int, float)) and total > 0:
            readings.append((float(used), float(total)))
    if readings:
        return {
            "used_gb": round(sum(item[0] for item in readings), 2),
            "total_gb": round(sum(item[1] for item in readings), 2),
            "status": "Available",
            "device_count": len(devices),
            "memory_device_count": len(readings),
            "vendors": vendors,
        }
    return {
        "used_gb": None,
        "total_gb": None,
        "status": "Inventory only" if devices else "Unavailable",
        "device_count": len(devices),
        "memory_device_count": 0,
        "vendors": vendors,
        "reason": (
            "GPU device(s) were detected, but no compatible memory telemetry provider is available."
            if devices else "No display adapters were reported by the available operating-system inventory providers."
        ),
    }



def _battery() -> dict[str, Any]:
    try:
        battery = psutil.sensors_battery()
    except (AttributeError, NotImplementedError, OSError, psutil.Error):
        battery = None
    if battery is None:
        return {
            "status": "Unavailable",
            "reason": "No battery telemetry is exposed by this device or operating system.",
            "percentage": _unavailable("Battery sensor not present.", "%"),
            "charging": _unavailable("Battery charging state is unavailable."),
            "seconds_remaining": _unavailable("Battery estimate is unavailable.", "s"),
            "health_percent": _unavailable("Battery health is not exposed by psutil.", "%"),
            "charge_cycles": _unavailable("Charge cycles are not exposed by psutil."),
        }
    seconds = _finite(battery.secsleft)
    if seconds is not None and seconds < 0:
        seconds = None
    return {
        "status": "Available",
        "percentage": _reading(battery.percent, "%", "psutil"),
        "charging": {"value": bool(battery.power_plugged), "unit": "", "status": "Available", "source": "psutil"},
        "seconds_remaining": _reading(seconds, "s", "psutil", "The operating system did not provide an estimate."),
        "health_percent": _unavailable("Battery health requires a vendor or platform-specific provider.", "%"),
        "charge_cycles": _unavailable("Charge cycles require a vendor or platform-specific provider."),
    }


def _platform_adapter() -> dict[str, str]:
    system = platform.system()
    if system == "Windows":
        return {
            "name": "Windows psutil + optional WMI",
            "details": "CPU, memory, battery and disk counters use psutil. Optional WMI can expose ACPI thermal zones; vendor sensor drivers may be required for CPU/fan readings.",
        }
    if system == "Linux":
        return {
            "name": "Linux psutil + kernel sensor interfaces",
            "details": "psutil reads CPU, memory, battery and hardware-monitor sensors. Memory pressure uses /proc/pressure/memory when readable.",
        }
    if system == "Darwin":
        return {
            "name": "macOS psutil adapter",
            "details": "CPU, memory, battery and disk counters use psutil. Temperature/fan visibility depends on the hardware and drivers; no privileged sensor command is invoked.",
        }
    return {"name": "psutil generic adapter", "details": "Only measurements exposed by psutil and installed optional providers are returned."}


def collect_hardware() -> dict[str, Any]:
    """Collect a bounded hardware snapshot. Optional sensor failures never fail the endpoint."""
    now = datetime.now(timezone.utc).isoformat()
    cpu_temperatures, board_temperatures, fans = _sensor_data()
    try:
        overall_cpu = psutil.cpu_percent(interval=0.1)
        per_core_cpu = psutil.cpu_percent(interval=0.1, percpu=True)
    except (psutil.Error, OSError):
        overall_cpu, per_core_cpu = None, []
    try:
        frequencies = psutil.cpu_freq(percpu=True) or []
        if not frequencies:
            single = psutil.cpu_freq()
            frequencies = [single] if single else []
    except (AttributeError, NotImplementedError, psutil.Error, OSError):
        frequencies = []
    core_count = psutil.cpu_count(logical=True) or 0
    cores = []
    for index in range(max(core_count, len(per_core_cpu), len(frequencies))):
        frequency = frequencies[index] if index < len(frequencies) else None
        percent = per_core_cpu[index] if index < len(per_core_cpu) else None
        cores.append({
            "core": index,
            "utilization_percent": _reading(percent, "%", "psutil.cpu_percent(percpu=True)"),
            "frequency_mhz": _reading(getattr(frequency, "current", None), "MHz", "psutil.cpu_freq(percpu=True)"),
        })
    try:
        memory = psutil.virtual_memory()
    except (psutil.Error, OSError):
        memory = None
    try:
        swap = psutil.swap_memory()
    except (psutil.Error, OSError):
        swap = None
    if memory:
        ram = {
            "total_gb": _reading(memory.total / (1024 ** 3), "GiB", "psutil.virtual_memory"),
            "used_gb": _reading(memory.used / (1024 ** 3), "GiB", "psutil.virtual_memory"),
            "available_gb": _reading(memory.available / (1024 ** 3), "GiB", "psutil.virtual_memory"),
            "percent": _reading(memory.percent, "%", "psutil.virtual_memory"),
            "cached_gb": _reading(getattr(memory, "cached", None) / (1024 ** 3) if getattr(memory, "cached", None) is not None else None, "GiB", "psutil.virtual_memory"),
            "buffers_gb": _reading(getattr(memory, "buffers", None) / (1024 ** 3) if getattr(memory, "buffers", None) is not None else None, "GiB", "psutil.virtual_memory"),
            "shared_gb": _reading(getattr(memory, "shared", None) / (1024 ** 3) if getattr(memory, "shared", None) is not None else None, "GiB", "psutil.virtual_memory"),
            "pressure": _memory_pressure(float(memory.percent)),
        }
    else:
        ram = {"status": "Unavailable", "reason": "psutil could not read system memory."}
    if swap:
        ram["swap"] = {
            "total_gb": _reading(swap.total / (1024 ** 3), "GiB", "psutil.swap_memory"),
            "used_gb": _reading(swap.used / (1024 ** 3), "GiB", "psutil.swap_memory"),
            "free_gb": _reading(swap.free / (1024 ** 3), "GiB", "psutil.swap_memory"),
            "percent": _reading(swap.percent, "%", "psutil.swap_memory"),
            "in_bytes": _reading(swap.sin, "bytes", "psutil.swap_memory"),
            "out_bytes": _reading(swap.sout, "bytes", "psutil.swap_memory"),
        }
    else:
        ram["swap"] = {"status": "Unavailable", "reason": "Swap/pagefile counters are unavailable."}
    try:
        average_frequency = psutil.cpu_freq()
    except (AttributeError, NotImplementedError, psutil.Error, OSError):
        average_frequency = None
    gpu = collect_gpu_devices()
    cpu_temperature_status = "Available" if cpu_temperatures else "Unavailable"
    board_temperature_status = "Available" if board_temperatures else "Unavailable"
    fan_status = "Available" if fans else "Unavailable"
    inventory = collect_system_inventory()
    return {
        "sampled_at": now,
        "platform": {"system": platform.system(), "release": platform.release(), "machine": platform.machine()},
        "system": inventory["system"],
        "platform_adapter": _platform_adapter(),
        "cpu": {
            "model": platform.processor() or "Unavailable",
            "logical_cores": core_count,
            "physical_cores": psutil.cpu_count(logical=False) or 0,
            "utilization_percent": _reading(overall_cpu, "%", "psutil.cpu_percent"),
            "frequency_mhz": _reading(getattr(average_frequency, "current", None), "MHz", "psutil.cpu_freq"),
            "cores": cores,
            "temperatures": {
                "status": cpu_temperature_status,
                "unit": "°C",
                "sensors": cpu_temperatures,
                "reason": None if cpu_temperatures else "No CPU temperature sensors were exposed. On some systems a vendor sensor provider is required.",
            },
            "voltage_v": _unavailable("CPU voltage is not exposed by psutil or a supported provider."),
        },
        "gpu": {
            "status": "Available" if any(item.get("status") == "Available" for item in gpu) else "Inventory only" if gpu else "Unavailable",
            "devices": gpu,
            "detected_vendors": sorted({str(item.get("vendor") or "Unknown") for item in gpu}),
            "reason": None if gpu else "No display adapter was reported by the available operating-system inventory providers. Check OS device enumeration and install the optional platform providers when required.",
        },
        "memory": ram,
        "motherboard": {
            "identity": inventory["motherboard"],
            "bios": inventory["bios"],
            "identity_source": inventory["source"],
            "temperatures": {
                "status": board_temperature_status,
                "unit": "°C",
                "sensors": board_temperatures,
                "reason": None if board_temperatures else "No motherboard/ACPI temperature sensors were exposed.",
            },
            "fans": {
                "status": fan_status,
                "unit": "RPM",
                "sensors": fans,
                "reason": None if fans else "No fan tachometer readings were exposed by the operating system.",
            },
        },
        "battery": _battery(),
        "capabilities": {
            "psutil_sensors": "Available" if cpu_temperatures or board_temperatures or fans else "Unavailable",
            "nvidia_nvml": "Available" if any(item.get("vendor") == "NVIDIA" and item.get("status") == "Available" for item in gpu) else "Unavailable",
            "amd_smi": "Available" if any(item.get("vendor") == "AMD" and item.get("status") == "Available" for item in gpu) else "Unavailable (AMD GPU inventory may still be detected)",
            "gpu_inventory": "Available" if gpu else "Unavailable",
            "gpu_live_telemetry": "Available" if any(item.get("status") == "Available" for item in gpu) else "Unavailable",
            "smbios_identity": "Available" if inventory["motherboard"].get("model") or inventory["system"].get("model") else "Unavailable",
            "libre_hardware_monitor": "Available" if collect_lhm_sensors() else "Not running or unavailable",
            "windows_wmi": "Optional; install requirements-hardware.txt for ACPI thermal-zone support on Windows.",
        },
    }
