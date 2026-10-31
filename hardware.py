"""Best-effort, platform-aware hardware telemetry for NEXUS-DASH.

Every optional sensor is represented explicitly. Missing APIs, drivers, or permissions
produce an Unavailable reading instead of a guessed value.
"""
from __future__ import annotations

import math
import platform
import threading
from datetime import datetime, timezone
from typing import Any

import psutil

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
        chip_name = str(chip)[:100]
        for entry in entries or []:
            current = _finite(getattr(entry, "current", None))
            if current is None:
                continue
            label = str(getattr(entry, "label", "") or chip_name)[:120]
            item = {
                "provider": chip_name,
                "label": label,
                "current_c": round(current, 1),
                "high_c": _finite(getattr(entry, "high", None)),
                "critical_c": _finite(getattr(entry, "critical", None)),
            }
            target = cpu_temperatures if any(
                token in (chip_name + " " + label).casefold()
                for token in ("cpu", "coretemp", "k10temp", "zenpower", "package")
            ) else board_temperatures
            target.append(item)
    try:
        provider_fans = psutil.sensors_fans() or {}
    except (AttributeError, NotImplementedError, OSError, psutil.Error):
        provider_fans = {}
    for chip, entries in provider_fans.items():
        for entry in entries or []:
            rpm = _finite(getattr(entry, "current", None))
            if rpm is not None:
                fans.append({
                    "provider": str(chip)[:100],
                    "label": str(getattr(entry, "label", "") or chip)[:120],
                    "rpm": round(rpm, 1),
                })
    if platform.system() == "Windows" and not board_temperatures:
        try:
            import wmi  # optional: requirements-hardware.txt
            connection = wmi.WMI(namespace=r"root\wmi")
            for zone in connection.MSAcpi_ThermalZoneTemperature():
                raw = _finite(getattr(zone, "CurrentTemperature", None))
                if raw is None or raw <= 0:
                    continue
                celsius = raw / 10.0 - 273.15
                if -40 <= celsius <= 150:
                    board_temperatures.append({
                        "provider": "Windows ACPI WMI",
                        "label": "ACPI thermal zone",
                        "current_c": round(celsius, 1),
                        "high_c": None,
                        "critical_c": None,
                    })
        except Exception:
            # WMI thermal zones are optional and often absent on modern systems.
            pass
    return cpu_temperatures, board_temperatures, fans


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


def _gpu_devices() -> list[dict[str, Any]]:
    global _NVML_READY
    try:
        import pynvml
    except ImportError:
        return []
    try:
        with _NVML_LOCK:
            if not _NVML_READY:
                pynvml.nvmlInit()
                _NVML_READY = True
        count = int(pynvml.nvmlDeviceGetCount())
    except Exception:
        return []
    devices: list[dict[str, Any]] = []
    for index in range(min(max(count, 0), 16)):
        try:
            handle = pynvml.nvmlDeviceGetHandleByIndex(index)
            raw_name = pynvml.nvmlDeviceGetName(handle)
            name = raw_name.decode("utf-8", "replace") if isinstance(raw_name, bytes) else str(raw_name)
            try:
                utilization = pynvml.nvmlDeviceGetUtilizationRates(handle)
                gpu_util = _reading(getattr(utilization, "gpu", None), "%", "NVIDIA NVML")
                memory_util = _reading(getattr(utilization, "memory", None), "%", "NVIDIA NVML")
            except Exception:
                gpu_util = _unavailable("NVML utilisation counters are unavailable.", "%")
                memory_util = _unavailable("NVML utilisation counters are unavailable.", "%")
            try:
                memory = pynvml.nvmlDeviceGetMemoryInfo(handle)
                used = memory.used / (1024 ** 3)
                total = memory.total / (1024 ** 3)
            except Exception:
                used = total = None
            try:
                temperature = pynvml.nvmlDeviceGetTemperature(handle, pynvml.NVML_TEMPERATURE_GPU)
            except Exception:
                temperature = None
            try:
                power = pynvml.nvmlDeviceGetPowerUsage(handle) / 1000.0
            except Exception:
                power = None
            try:
                graphics_clock = pynvml.nvmlDeviceGetClockInfo(handle, pynvml.NVML_CLOCK_GRAPHICS)
            except Exception:
                graphics_clock = None
            try:
                memory_clock = pynvml.nvmlDeviceGetClockInfo(handle, pynvml.NVML_CLOCK_MEM)
            except Exception:
                memory_clock = None
            try:
                fan = pynvml.nvmlDeviceGetFanSpeed(handle)
            except Exception:
                fan = None
            devices.append({
                "index": index,
                "name": name[:160],
                "vendor": "NVIDIA",
                "utilization_percent": gpu_util,
                "memory_utilization_percent": memory_util,
                "memory_used_gb": _reading(used, "GiB", "NVIDIA NVML"),
                "memory_total_gb": _reading(total, "GiB", "NVIDIA NVML"),
                "temperature_c": _reading(temperature, "°C", "NVIDIA NVML"),
                "power_w": _reading(power, "W", "NVIDIA NVML"),
                "graphics_clock_mhz": _reading(graphics_clock, "MHz", "NVIDIA NVML"),
                "memory_clock_mhz": _reading(memory_clock, "MHz", "NVIDIA NVML"),
                "fan_percent": _reading(fan, "%", "NVIDIA NVML"),
                "status": "Available",
            })
        except Exception:
            devices.append({
                "index": index,
                "name": f"NVIDIA GPU {index}",
                "vendor": "NVIDIA",
                "status": "Unavailable",
                "reason": "The NVML device could not be queried.",
            })
    return devices


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
    gpu = _gpu_devices()
    cpu_temperature_status = "Available" if cpu_temperatures else "Unavailable"
    board_temperature_status = "Available" if board_temperatures else "Unavailable"
    fan_status = "Available" if fans else "Unavailable"
    return {
        "sampled_at": now,
        "platform": {"system": platform.system(), "release": platform.release(), "machine": platform.machine()},
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
            "status": "Available" if gpu else "Unavailable",
            "devices": gpu,
            "reason": None if gpu else "NVIDIA NVML is unavailable, no supported NVIDIA device was found, or its driver could not be queried.",
        },
        "memory": ram,
        "motherboard": {
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
            "nvidia_nvml": "Available" if gpu else "Unavailable",
            "windows_wmi": "Optional; install requirements-hardware.txt for ACPI thermal-zone support on Windows.",
        },
    }
