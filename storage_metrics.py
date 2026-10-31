"""Disk I/O, per-process activity, drive capacity, and optional SMART telemetry."""
from __future__ import annotations

import json
import math
import platform
import shutil
import subprocess
import threading
import time
from datetime import datetime, timezone
from typing import Any

import psutil


def _number(value: Any) -> float | None:
    if isinstance(value, bool) or value is None:
        return None
    try:
        result = float(value)
    except (TypeError, ValueError, OverflowError):
        return None
    return result if math.isfinite(result) else None


def counter_rate(before: Any, after: Any, elapsed: float) -> float | None:
    """Return a non-negative counter rate, or None until two valid samples exist."""
    first, last = _number(before), _number(after)
    if first is None or last is None or elapsed <= 0:
        return None
    return round(max(0.0, last - first) / elapsed, 2)


def _counter_value(counter: Any, key: str) -> float | None:
    return _number(getattr(counter, key, None))


class StorageSampler:
    """Thread-safe delta sampler. Process names/PIDs remain live-only and are never persisted."""

    def __init__(self, *, smart_ttl_seconds: float = 300.0, smart_timeout_seconds: float = 1.2):
        self._lock = threading.RLock()
        self._previous_total: Any = None
        self._previous_total_at: float | None = None
        self._previous_devices: dict[str, tuple[Any, float]] = {}
        self._previous_processes: dict[str, tuple[dict[str, float], float, int, str]] = {}
        self._smart_cache: dict[str, tuple[float, dict[str, Any]]] = {}
        self._smart_ttl_seconds = max(60.0, float(smart_ttl_seconds))
        self._smart_timeout_seconds = max(0.2, min(3.0, float(smart_timeout_seconds)))
        self._smartctl = shutil.which("smartctl")

    @staticmethod
    def _rates(before: Any, after: Any, elapsed: float) -> dict[str, float | None]:
        names = ("read_bytes", "write_bytes", "read_count", "write_count", "read_time", "write_time", "busy_time")
        deltas: dict[str, float | None] = {}
        for name in names:
            first = _counter_value(before, name) if before is not None else None
            last = _counter_value(after, name) if after is not None else None
            deltas[name] = None if first is None or last is None else max(0.0, last - first)
        return {
            "read_bytes_per_sec": round(deltas["read_bytes"] / elapsed, 2) if deltas["read_bytes"] is not None and elapsed > 0 else None,
            "write_bytes_per_sec": round(deltas["write_bytes"] / elapsed, 2) if deltas["write_bytes"] is not None and elapsed > 0 else None,
            "read_iops": round(deltas["read_count"] / elapsed, 2) if deltas["read_count"] is not None and elapsed > 0 else None,
            "write_iops": round(deltas["write_count"] / elapsed, 2) if deltas["write_count"] is not None and elapsed > 0 else None,
            "activity_percent": round(min(100.0, deltas["busy_time"] / (elapsed * 1000.0) * 100.0), 1) if deltas["busy_time"] is not None and elapsed > 0 else None,
            "latency_ms": round((deltas["read_time"] + deltas["write_time"]) / (deltas["read_count"] + deltas["write_count"]), 2)
                if deltas["read_time"] is not None and deltas["write_time"] is not None
                and deltas["read_count"] is not None and deltas["write_count"] is not None
                and deltas["read_count"] + deltas["write_count"] > 0 else None,
        }

    def _smart_device_arg(self, device: str) -> str:
        system = platform.system()
        if system == "Windows" and "physicaldrive" in device.casefold():
            return "\\\\.\\" + device
        if system == "Darwin" and device.startswith("disk"):
            return "/dev/" + device
        if system == "Linux" and not device.startswith("/"):
            return "/dev/" + device
        return device

    def _smart_health(self, device: str, now: float) -> dict[str, Any]:
        cached = self._smart_cache.get(device)
        if cached and now - cached[0] < self._smart_ttl_seconds:
            return dict(cached[1])
        if not self._smartctl:
            result = {
                "status": "Unavailable",
                "health": None,
                "temperature_c": None,
                "reason": "smartctl is not installed. Install smartmontools and grant read access to the drive.",
            }
        else:
            try:
                completed = subprocess.run(
                    [self._smartctl, "--json", "--health", self._smart_device_arg(device)],
                    stdin=subprocess.DEVNULL,
                    capture_output=True,
                    text=True,
                    timeout=self._smart_timeout_seconds,
                    check=False,
                    shell=False,
                    creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0),
                )
                payload = json.loads(completed.stdout or "{}")
                smart = payload.get("smart_status") if isinstance(payload, dict) else None
                passed = smart.get("passed") if isinstance(smart, dict) else None
                temperature = None
                if isinstance(payload, dict):
                    raw_temp = payload.get("temperature")
                    if isinstance(raw_temp, dict):
                        temperature = _number(raw_temp.get("current"))
                    nvme = payload.get("nvme_smart_health_information_log")
                    if temperature is None and isinstance(nvme, dict):
                        temperature = _number(nvme.get("temperature"))
                if isinstance(passed, bool):
                    result = {
                        "status": "Available",
                        "health": "Passing" if passed else "Failing",
                        "temperature_c": temperature,
                        "reason": None,
                    }
                else:
                    result = {
                        "status": "Unavailable",
                        "health": None,
                        "temperature_c": temperature,
                        "reason": "SMART health data was not returned. The device may not support SMART or access may be restricted.",
                    }
            except (OSError, subprocess.SubprocessError, ValueError, json.JSONDecodeError):
                result = {
                    "status": "Unavailable",
                    "health": None,
                    "temperature_c": None,
                    "reason": "SMART query timed out, failed, or returned unreadable data.",
                }
        self._smart_cache[device] = (now, result)
        return dict(result)

    @staticmethod
    def _drives() -> list[dict[str, Any]]:
        drives: list[dict[str, Any]] = []
        seen: set[tuple[str, str]] = set()
        try:
            partitions = psutil.disk_partitions(all=False)
        except (psutil.Error, OSError, AttributeError):
            partitions = []
        for partition in partitions[:128]:
            device = str(getattr(partition, "device", "") or "")[:260]
            mountpoint = str(getattr(partition, "mountpoint", "") or "")[:260]
            key = (device, mountpoint)
            if not mountpoint or key in seen:
                continue
            seen.add(key)
            try:
                usage = psutil.disk_usage(mountpoint)
                drives.append({
                    "device": device or "Unavailable",
                    "mountpoint": mountpoint,
                    "filesystem": str(getattr(partition, "fstype", "") or "Unknown")[:80],
                    "total_gb": round(usage.total / (1024 ** 3), 2),
                    "used_gb": round(usage.used / (1024 ** 3), 2),
                    "free_gb": round(usage.free / (1024 ** 3), 2),
                    "percent": round(usage.percent, 1),
                    "status": "Available",
                })
            except (psutil.Error, OSError, PermissionError):
                drives.append({
                    "device": device or "Unavailable",
                    "mountpoint": mountpoint,
                    "filesystem": str(getattr(partition, "fstype", "") or "Unknown")[:80],
                    "total_gb": None,
                    "used_gb": None,
                    "free_gb": None,
                    "percent": None,
                    "status": "Unavailable",
                    "reason": "The operating system denied access to this mount point.",
                })
        return drives

    def _process_activity(self, now: float, elapsed: float | None) -> list[dict[str, Any]]:
        current: dict[str, tuple[dict[str, float], int, str]] = {}
        try:
            processes = psutil.process_iter(["pid", "name", "create_time"])
        except (psutil.Error, OSError):
            return []
        for process in processes:
            try:
                info = process.info
                pid = int(info.get("pid") or 0)
                created = _number(info.get("create_time"))
                counters = process.io_counters()
                if pid <= 0 or created is None or counters is None:
                    continue
                identity = f"{pid}:{created:.3f}"
                values = {
                    "read_bytes": _counter_value(counters, "read_bytes") or 0.0,
                    "write_bytes": _counter_value(counters, "write_bytes") or 0.0,
                    "read_count": _counter_value(counters, "read_count") or 0.0,
                    "write_count": _counter_value(counters, "write_count") or 0.0,
                }
                current[identity] = (values, pid, str(info.get("name") or "Unknown")[:120])
            except (psutil.Error, OSError, AttributeError, TypeError, ValueError):
                continue
        activity = []
        interval = elapsed or 0.0
        if interval > 0:
            for identity, (values, pid, name) in current.items():
                previous = self._previous_processes.get(identity)
                if not previous:
                    continue
                old, old_at, _, _ = previous
                delta_t = max(0.0, now - old_at)
                if delta_t <= 0:
                    continue
                read_rate = max(0.0, values["read_bytes"] - old["read_bytes"]) / delta_t
                write_rate = max(0.0, values["write_bytes"] - old["write_bytes"]) / delta_t
                read_iops = max(0.0, values["read_count"] - old["read_count"]) / delta_t
                write_iops = max(0.0, values["write_count"] - old["write_count"]) / delta_t
                total_rate = read_rate + write_rate
                if total_rate > 0 or read_iops + write_iops > 0:
                    activity.append({
                        "pid": pid,
                        "name": name,
                        "read_bytes_per_sec": round(read_rate, 2),
                        "write_bytes_per_sec": round(write_rate, 2),
                        "read_iops": round(read_iops, 2),
                        "write_iops": round(write_iops, 2),
                        "total_bytes_per_sec": round(total_rate, 2),
                    })
        self._previous_processes = {
            identity: (values, now, pid, name)
            for identity, (values, pid, name) in current.items()
        }
        activity.sort(key=lambda item: item["total_bytes_per_sec"], reverse=True)
        return activity[:10]

    def collect(self) -> dict[str, Any]:
        with self._lock:
            now = time.monotonic()
            sampled_at = datetime.now(timezone.utc).isoformat()
            try:
                total = psutil.disk_io_counters()
                per_disk = psutil.disk_io_counters(perdisk=True) or {}
            except (psutil.Error, OSError, AttributeError):
                total, per_disk = None, {}
            elapsed = now - self._previous_total_at if self._previous_total_at is not None else None
            rates = self._rates(self._previous_total, total, elapsed or 0.0)
            status = "Available" if total is not None and elapsed and elapsed > 0 else "Warming up" if total is not None else "Unavailable"
            self._previous_total = total
            self._previous_total_at = now
            devices = []
            for device_index, (name, counters) in enumerate(sorted(per_disk.items(), key=lambda item: str(item[0]).casefold())[:64]):
                previous = self._previous_devices.get(str(name))
                device_elapsed = now - previous[1] if previous else 0.0
                device_rates = self._rates(previous[0] if previous else None, counters, device_elapsed)
                smart = self._smart_health(str(name), now) if device_index < 2 else {
                    "status": "Unavailable", "health": None, "temperature_c": None,
                    "reason": "SMART queries are capped at two devices per snapshot to keep local API requests bounded.",
                }
                devices.append({
                    "device": str(name)[:160],
                    **device_rates,
                    "smart": smart,
                    "temperature_c": smart.get("temperature_c"),
                    "status": "Available" if previous and device_elapsed > 0 else "Warming up",
                })
                self._previous_devices[str(name)] = (counters, now)
            process_elapsed = elapsed
            top_processes = self._process_activity(now, process_elapsed)
            drives = self._drives()
            return {
                "sampled_at": sampled_at,
                "status": status,
                "drives": drives,
                "devices": devices,
                "totals": {
                    "read_bytes_per_sec": rates["read_bytes_per_sec"],
                    "write_bytes_per_sec": rates["write_bytes_per_sec"],
                    "read_mb_per_sec": round(rates["read_bytes_per_sec"] / (1024 ** 2), 3) if rates["read_bytes_per_sec"] is not None else None,
                    "write_mb_per_sec": round(rates["write_bytes_per_sec"] / (1024 ** 2), 3) if rates["write_bytes_per_sec"] is not None else None,
                    "read_iops": rates["read_iops"],
                    "write_iops": rates["write_iops"],
                    "activity_percent": rates["activity_percent"],
                    "latency_ms": rates["latency_ms"],
                    "status": status,
                },
                "top_processes": top_processes,
                "capabilities": {
                    "psutil_disk_io": "Available" if total is not None else "Unavailable",
                    "disk_activity_percent": "Available" if rates["activity_percent"] is not None else "Unavailable",
                    "disk_latency": "Available" if rates["latency_ms"] is not None else "Unavailable",
                    "smart": "Available" if self._smartctl else "Unavailable",
                    "process_io": "Best effort; operating-system permissions may hide process counters.",
                },
            }
