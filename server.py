"""Local-only NEXUS system telemetry API. The terminal is diagnostics-only."""
from __future__ import annotations

import csv
import getpass
import ipaddress
import io
import json
import logging
import math
import os
import platform
import sqlite3
import threading
import time
from datetime import datetime, timezone
from typing import Any

import psutil
from fastapi import FastAPI, HTTPException, Query, Request
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel, Field
from starlette.middleware.trustedhost import TrustedHostMiddleware
from starlette.responses import JSONResponse, Response

from telemetry_store import SAMPLE_FIELDS, WINDOW_SECONDS, TelemetryStore
from diagnostics import DIAGNOSTICS_VERSION, ProcessMemoryTracker, analyse_diagnostics, collect_os_events
from hardware import collect_hardware
from storage_metrics import StorageSampler
from process_intelligence import ProcessIntelligence
from settings_store import SettingsStore

LOGGER = logging.getLogger("nexus")
ALLOWED_ORIGINS = {
    "http://127.0.0.1:5500", "http://localhost:5500",
    "http://127.0.0.1:5501", "http://localhost:5501",
    "http://127.0.0.1:8000", "http://localhost:8000",
}
PROTECTED_PIDS = {0, 1, 2, 3, 4, os.getpid(), os.getppid()}
_NVML_INITIALIZED = False

TELEMETRY_STORE = TelemetryStore()
PROCESS_MEMORY_TRACKER = ProcessMemoryTracker()
STORAGE_SAMPLER = StorageSampler()
SETTINGS_STORE = SettingsStore(TELEMETRY_STORE.directory)
PROCESS_INTELLIGENCE = ProcessIntelligence()
_TIMELINE_THRESHOLDS: dict[str, bool] = {}
_RECORDER_STOP = threading.Event()
_RECORDER_THREAD: threading.Thread | None = None

app = FastAPI(title="NEXUS Local System API", version=DIAGNOSTICS_VERSION,
              docs_url=None, redoc_url=None, openapi_url=None)
app.add_middleware(TrustedHostMiddleware, allowed_hosts=["127.0.0.1", "localhost", "[::1]"])
app.add_middleware(CORSMiddleware, allow_origins=sorted(ALLOWED_ORIGINS),
                   allow_credentials=False, allow_methods=["GET", "POST", "PUT", "DELETE", "OPTIONS"],
                   allow_headers=["Content-Type"], max_age=600)


@app.middleware("http")
async def enforce_local_access(request: Request, call_next):
    client = request.client.host if request.client else ""
    try:
        is_loopback = ipaddress.ip_address(client).is_loopback
    except ValueError:
        is_loopback = False
    if not is_loopback:
        return JSONResponse(status_code=403, content={"detail": "Local connections only."})
    origin = request.headers.get("origin")
    if origin and origin not in ALLOWED_ORIGINS:
        return JSONResponse(status_code=403, content={"detail": "Origin is not allowed."})
    return await call_next(request)


class TerminalRequest(BaseModel):
    command: str = Field(min_length=1, max_length=120)


class ProcessKillRequest(BaseModel):
    pid: int = Field(gt=0)
    create_time: float = Field(gt=0)


class TimelineMarkerRequest(BaseModel):
    title: str = Field(min_length=1, max_length=120)
    note: str = Field(default="", max_length=500)


class SettingsUpdate(BaseModel):
    sampling_interval_seconds: int | None = None
    retention_days: int | None = None
    background_recording: bool | None = None
    process_history_enabled: bool | None = None
    process_history_interval_seconds: int | None = None
    process_exclusions: list[str] | None = None
    privacy_mode: bool | None = None
    start_minimized: bool | None = None


def _format_uptime(seconds: float) -> str:
    total = max(0, int(seconds))
    days, remainder = divmod(total, 86400)
    hours, remainder = divmod(remainder, 3600)
    minutes, seconds = divmod(remainder, 60)
    if days:
        return f"{days}d {hours}h {minutes}m"
    if hours:
        return f"{hours}h {minutes}m"
    if minutes:
        return f"{minutes}m {seconds}s"
    return f"{seconds}s"


def _gpu_memory() -> dict[str, Any]:
    global _NVML_INITIALIZED
    try:
        import pynvml  # optional package: nvidia-ml-py
        if not _NVML_INITIALIZED:
            pynvml.nvmlInit()
            _NVML_INITIALIZED = True
        info = pynvml.nvmlDeviceGetMemoryInfo(pynvml.nvmlDeviceGetHandleByIndex(0))
        return {"used_gb": round(info.used / (1024 ** 3), 2),
                "total_gb": round(info.total / (1024 ** 3), 2), "status": "Available"}
    except Exception:
        return {"used_gb": None, "total_gb": None, "status": "Unavailable"}


def _same_user(process: psutil.Process) -> bool:
    try:
        actual = process.username()
        current_user = psutil.Process(os.getpid()).username()
        return actual.casefold() == current_user.casefold()
    except (psutil.Error, OSError):
        return False


def _can_terminate(process: psutil.Process) -> bool:
    return process.pid > 4 and process.pid not in PROTECTED_PIDS and _same_user(process)


def _terminal(stdout: str, stderr: str = "", returncode: int = 0) -> dict[str, Any]:
    return {"stdout": stdout, "stderr": stderr, "returncode": returncode}


@app.get("/api/health")
def health() -> dict[str, Any]:
    return {"status": "ok", "service": "nexus-local-api", "version": DIAGNOSTICS_VERSION,
            "desktop_runtime": os.environ.get("NEXUS_DESKTOP_RUNTIME") == "1"}


def _collect_stats() -> dict[str, Any]:
    """Collect one fresh host snapshot without persisting identifying system fields."""
    try:
        memory = psutil.virtual_memory()
        net = psutil.net_io_counters()
        disk = psutil.disk_usage(os.path.abspath(os.sep))
        boot_time = psutil.boot_time()
        uptime = max(0, time.time() - boot_time)
        storage_snapshot = STORAGE_SAMPLER.collect(include_details=False)
        return {
            "cpu": {"percent": round(psutil.cpu_percent(interval=0.1), 1),
                    "cores": psutil.cpu_count(logical=True) or 0,
                    "physical_cores": psutil.cpu_count(logical=False) or 0},
            "ram": {"used_gb": round(memory.used / (1024 ** 3), 2),
                    "total_gb": round(memory.total / (1024 ** 3), 2), "percent": round(memory.percent, 1)},
            "network": {"sent_mb": round(net.bytes_sent / (1024 ** 2), 2),
                        "recv_mb": round(net.bytes_recv / (1024 ** 2), 2),
                        "sent_bytes": net.bytes_sent, "recv_bytes": net.bytes_recv},
            "disk": {"used_gb": round(disk.used / (1024 ** 3), 2),
                     "total_gb": round(disk.total / (1024 ** 3), 2), "percent": round(disk.percent, 1)},
            "gpu": _gpu_memory(),
            "storage_io": storage_snapshot.get("totals", {}),
            "system": {"hostname": platform.node() or "Unknown", "platform": platform.system(),
                       "platform_release": platform.release(), "architecture": platform.machine(),
                       "python_version": platform.python_version(), "user": getpass.getuser(),
                       "boot_time": datetime.fromtimestamp(boot_time, timezone.utc).isoformat(),
                       "uptime_seconds": round(uptime), "uptime": _format_uptime(uptime)},
            "sampled_at": datetime.now(timezone.utc).isoformat(),
        }
    except (psutil.Error, OSError, ValueError) as exc:
        LOGGER.exception("Unable to collect system metrics")
        raise HTTPException(status_code=503, detail="System metrics are temporarily unavailable.") from exc


def _record_resource_events(payload: dict[str, Any]) -> None:
    metrics = [
        ("cpu", "CPU utilisation spike", float(payload.get("cpu", {}).get("percent") or 0), 90.0, 85.0),
        ("ram", "System memory pressure", float(payload.get("ram", {}).get("percent") or 0), 90.0, 85.0),
        ("disk", "System volume nearly full", float(payload.get("disk", {}).get("percent") or 0), 95.0, 90.0),
        ("disk-io", "Sustained disk activity", float(payload.get("storage_io", {}).get("activity_percent") or 0), 95.0, 85.0),
    ]
    for key, title, value, threshold, reset_at in metrics:
        active = _TIMELINE_THRESHOLDS.get(key, False)
        if value >= threshold and not active:
            TELEMETRY_STORE.record_event(
                "resource", title, f"Observed {value:.1f}% (signal threshold {threshold:.0f}%).",
                severity="critical" if value >= 98 else "warning",
                metadata={"metric": key, "value": round(value, 1), "threshold": threshold},
            )
            _TIMELINE_THRESHOLDS[key] = True
        elif active and value < reset_at:
            _TIMELINE_THRESHOLDS[key] = False


@app.get("/api/stats")
def get_stats() -> dict[str, Any]:
    payload = _collect_stats()
    try:
        if SETTINGS_STORE.get()["background_recording"]:
            if TELEMETRY_STORE.record(payload):
                _record_resource_events(payload)
    except Exception:
        # A history-storage issue must not make live telemetry unavailable.
        LOGGER.exception("Telemetry sample could not be recorded")
    return payload


def _recorder_loop() -> None:
    cycle = 0
    elapsed = 0
    while not _RECORDER_STOP.is_set():
        try:
            settings = SETTINGS_STORE.get()
            interval = int(settings["sampling_interval_seconds"])
            retention_seconds = int(settings["retention_days"]) * 86400
            effective_interval = max(interval, math.ceil(retention_seconds / TELEMETRY_STORE.max_samples))
            TELEMETRY_STORE.sample_interval_seconds = float(effective_interval)
            TELEMETRY_STORE.retention_seconds = retention_seconds
            if settings["background_recording"]:
                payload = _collect_stats()
                if TELEMETRY_STORE.record(payload):
                    _record_resource_events(payload)
                cycle += interval
                if settings["process_history_enabled"] and cycle >= int(settings["process_history_interval_seconds"]):
                    process_events = PROCESS_INTELLIGENCE.sample(settings.get("process_exclusions", []))
                    for item in process_events["started"]:
                        TELEMETRY_STORE.record_event(
                            "process-start", f"Process started: {item['name']}",
                            f"PID {item['pid']}", metadata={"pid": item["pid"]},
                        )
                    for item in process_events["exited"]:
                        TELEMETRY_STORE.record_event(
                            "process-exit", f"Process exited: {item['name']}",
                            f"PID {item['pid']}", metadata={"pid": item["pid"]},
                        )
                    PROCESS_MEMORY_TRACKER.sample()
                    cycle = 0
            _RECORDER_STOP.wait(interval)
        except Exception:
            LOGGER.exception("Background telemetry sample failed")
            _RECORDER_STOP.wait(5.0)


@app.on_event("startup")
def start_recorder() -> None:
    global _RECORDER_THREAD
    if _RECORDER_THREAD and _RECORDER_THREAD.is_alive():
        return
    _RECORDER_STOP.clear()
    _RECORDER_THREAD = threading.Thread(
        target=_recorder_loop, name="nexus-telemetry-recorder", daemon=True
    )
    _RECORDER_THREAD.start()


@app.on_event("shutdown")
def stop_recorder() -> None:
    _RECORDER_STOP.set()
    if _RECORDER_THREAD and _RECORDER_THREAD.is_alive():
        _RECORDER_THREAD.join(timeout=2.0)



@app.get("/api/diagnostics")
def get_diagnostics(window: str = Query(default="1h")) -> dict[str, Any]:
    """Return bounded, evidence-based resource-pressure and event-correlation findings."""
    if window not in WINDOW_SECONDS:
        raise HTTPException(status_code=400, detail="Unsupported diagnostics window.")
    try:
        samples = TELEMETRY_STORE.get_history(window, 2000)
        PROCESS_MEMORY_TRACKER.sample()
        growth = PROCESS_MEMORY_TRACKER.get_growth(window)
        event_result = collect_os_events(window)
        return analyse_diagnostics(samples, growth, event_result["events"], window=window,
                                   event_source_status=event_result["status"])
    except (OSError, RuntimeError, ValueError, sqlite3.Error):
        LOGGER.exception("Unable to analyse local diagnostics")
        raise HTTPException(status_code=503, detail="Diagnostics are temporarily unavailable.")


@app.get("/api/diagnostics/report")
def export_diagnostics_report(window: str = Query(default="1h")) -> Response:
    """Generate an explicitly requested, bounded JSON troubleshooting report."""
    if window not in WINDOW_SECONDS:
        raise HTTPException(status_code=400, detail="Unsupported diagnostics window.")
    try:
        samples = TELEMETRY_STORE.get_history(window, 2000)
        PROCESS_MEMORY_TRACKER.sample()
        growth = PROCESS_MEMORY_TRACKER.get_growth(window)
        event_result = collect_os_events(window)
        analysis = analyse_diagnostics(samples, growth, event_result["events"], window=window,
                                       event_source_status=event_result["status"])
    except (OSError, RuntimeError, ValueError, sqlite3.Error):
        LOGGER.exception("Unable to create diagnostics report")
        raise HTTPException(status_code=503, detail="Diagnostics report is temporarily unavailable.")
    report = {
        "application": "NEXUS-DASH", "version": DIAGNOSTICS_VERSION,
        "report_type": "local-diagnostics", "generated_at": datetime.now(timezone.utc).isoformat(),
        "window": window, "analysis": analysis, "telemetry_samples": samples,
        "process_memory_growth": growth, "os_events": event_result,
        "privacy_notice": "Generated on request. Includes local telemetry and may include process names, PIDs, and sanitized OS event metadata. Review before sharing.",
    }
    suffix = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    return Response(content=json.dumps(report, indent=2, allow_nan=False),
        media_type="application/json; charset=utf-8",
        headers={"Content-Disposition": f'attachment; filename="nexus-diagnostics-{suffix}.json"'})

@app.get("/api/hardware")
def get_hardware() -> dict[str, Any]:
    """Return component-level hardware readings with explicit sensor availability."""
    try:
        return collect_hardware()
    except Exception:
        LOGGER.exception("Unable to collect hardware telemetry")
        raise HTTPException(status_code=503, detail="Hardware telemetry is temporarily unavailable.")


@app.get("/api/storage")
def get_storage() -> dict[str, Any]:
    """Return live disk I/O, per-drive capacity, process activity, and optional SMART data."""
    try:
        return STORAGE_SAMPLER.collect()
    except Exception:
        LOGGER.exception("Unable to collect storage telemetry")
        raise HTTPException(status_code=503, detail="Storage telemetry is temporarily unavailable.")


@app.get("/api/processes")
def get_processes(limit: int = Query(default=100, ge=1, le=200)) -> dict[str, Any]:
    items = []
    for process in psutil.process_iter(["pid", "name", "cpu_percent", "memory_info", "status", "create_time", "ppid", "num_threads"]):
        try:
            info = process.info
            memory = info.get("memory_info")
            items.append({"pid": info["pid"], "name": info.get("name") or "Unknown",
                          "cpu": round(float(info.get("cpu_percent") or 0), 1),
                          "ram_mb": round(memory.rss / (1024 ** 2), 1) if memory else 0,
                          "status": info.get("status") or "unknown", "can_terminate": _can_terminate(process),
                          "create_time": info.get("create_time"), "ppid": info.get("ppid"),
                          "threads": info.get("num_threads")})
        except (psutil.NoSuchProcess, psutil.AccessDenied, psutil.ZombieProcess):
            continue
    items.sort(key=lambda item: (item["cpu"], item["ram_mb"]), reverse=True)
    return {"items": items[:limit], "count": min(len(items), limit),
            "sampled_at": datetime.now(timezone.utc).isoformat()}


@app.get("/api/settings")
def get_settings() -> dict[str, Any]:
    settings = SETTINGS_STORE.get()
    settings["desktop_runtime"] = os.environ.get("NEXUS_DESKTOP_RUNTIME") == "1"
    return settings


@app.put("/api/settings")
def update_settings(payload: SettingsUpdate) -> dict[str, Any]:
    try:
        updated = SETTINGS_STORE.update(payload.model_dump(exclude_none=True))
        retention_seconds = int(updated["retention_days"]) * 86400
        effective_interval = max(int(updated["sampling_interval_seconds"]),
                                 math.ceil(retention_seconds / TELEMETRY_STORE.max_samples))
        TELEMETRY_STORE.sample_interval_seconds = float(effective_interval)
        TELEMETRY_STORE.retention_seconds = retention_seconds
        return updated
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@app.get("/api/timeline")
def get_timeline(
    window: str = Query(default="24h"),
    limit: int = Query(default=500, ge=1, le=2000),
) -> dict[str, Any]:
    if window not in WINDOW_SECONDS:
        raise HTTPException(status_code=400, detail="Unsupported timeline window.")
    try:
        events = TELEMETRY_STORE.get_events(window, limit)
    except (OSError, RuntimeError, ValueError, sqlite3.Error):
        LOGGER.exception("Unable to read investigation timeline")
        raise HTTPException(status_code=503, detail="Timeline is temporarily unavailable.")
    return {"window": window, "count": len(events), "events": events, "storage": "local-sqlite"}


@app.post("/api/timeline/markers")
def create_timeline_marker(payload: TimelineMarkerRequest) -> dict[str, Any]:
    try:
        event = TELEMETRY_STORE.record_event(
            "marker", payload.title.strip(), payload.note.strip(),
            severity="info", metadata={"source": "user"},
        )
        return {"status": "created", "event": event}
    except (OSError, sqlite3.Error, ValueError):
        LOGGER.exception("Unable to save timeline marker")
        raise HTTPException(status_code=503, detail="Timeline marker could not be saved.")


@app.get("/api/processes/{pid}")
def get_process_detail(pid: int, create_time: float = Query(gt=0)) -> dict[str, Any]:
    try:
        return PROCESS_INTELLIGENCE.inspect(pid, create_time)
    except LookupError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except PermissionError as exc:
        raise HTTPException(status_code=403, detail=str(exc)) from exc


@app.get("/api/process-history")
def get_process_history(
    pid: int = Query(gt=0),
    create_time: float = Query(gt=0),
    window: str = Query(default="30m"),
) -> dict[str, Any]:
    windows = {"5m": 300, "15m": 900, "30m": 1800, "1h": 3600, "6h": 21600, "24h": 86400}
    if window not in windows:
        raise HTTPException(status_code=400, detail="Unsupported process-history window.")
    try:
        process = psutil.Process(pid)
        if abs(float(process.create_time()) - create_time) > 0.01:
            raise HTTPException(status_code=404, detail="The process no longer exists or its PID was reused.")
        history = PROCESS_INTELLIGENCE.history(pid, create_time, windows[window])
        return {"pid": pid, "create_time": create_time, "window": window, "samples": history,
                "count": len(history), "status": "Available" if history else "Warming up"}
    except psutil.NoSuchProcess as exc:
        raise HTTPException(status_code=404, detail="The process no longer exists.") from exc
    except psutil.AccessDenied as exc:
        raise HTTPException(status_code=403, detail="The operating system denied access to this process.") from exc


@app.get("/api/process-compare")
def compare_processes(
    pid_a: int = Query(gt=0), create_time_a: float = Query(gt=0),
    pid_b: int = Query(gt=0), create_time_b: float = Query(gt=0),
) -> dict[str, Any]:
    try:
        return {"processes": [
            PROCESS_INTELLIGENCE.inspect(pid_a, create_time_a),
            PROCESS_INTELLIGENCE.inspect(pid_b, create_time_b),
        ]}
    except LookupError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except PermissionError as exc:
        raise HTTPException(status_code=403, detail=str(exc)) from exc


@app.get("/api/history")
def get_history(
    window: str = Query(default="1h"),
    limit: int = Query(default=600, ge=1, le=2000),
) -> dict[str, Any]:
    """Return actual locally recorded samples for a bounded historical window."""
    if window not in WINDOW_SECONDS:
        raise HTTPException(status_code=400, detail="Unsupported history window.")
    try:
        samples = TELEMETRY_STORE.get_history(window, limit)
    except (OSError, RuntimeError, ValueError, sqlite3.Error):
        LOGGER.exception("Unable to read telemetry history")
        raise HTTPException(status_code=503, detail="Telemetry history is temporarily unavailable.")
    return {"window": window, "count": len(samples), "samples": samples, "storage": "local-sqlite"}


@app.delete("/api/history")
def delete_history() -> dict[str, str]:
    try:
        TELEMETRY_STORE.clear_history()
        return {"status": "deleted", "scope": "telemetry-and-timeline"}
    except (OSError, sqlite3.Error):
        LOGGER.exception("Unable to delete local telemetry history")
        raise HTTPException(status_code=503, detail="Local telemetry history could not be deleted.")


@app.get("/api/history/export")
def export_history(
    export_format: str = Query(default="json", alias="format"),
    window: str = Query(default="24h"),
    limit: int = Query(default=2000, ge=1, le=2000),
) -> Response:
    """Export bounded historical resource samples as JSON or CSV."""
    if window not in WINDOW_SECONDS:
        raise HTTPException(status_code=400, detail="Unsupported history window.")
    if export_format not in {"json", "csv"}:
        raise HTTPException(status_code=400, detail="Export format must be json or csv.")
    try:
        samples = TELEMETRY_STORE.get_history(window, limit)
    except (OSError, RuntimeError, ValueError, sqlite3.Error):
        LOGGER.exception("Unable to export telemetry history")
        raise HTTPException(status_code=503, detail="Telemetry history is temporarily unavailable.")
    suffix = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    filename = f"nexus-telemetry-{suffix}.{export_format}"
    headers = {"Content-Disposition": f'attachment; filename="{filename}"'}
    if export_format == "json":
        body = json.dumps(
            {"exported_at": datetime.now(timezone.utc).isoformat(),
             "window": window, "sample_count": len(samples), "samples": samples},
            indent=2, allow_nan=False,
        )
        return Response(content=body, media_type="application/json; charset=utf-8", headers=headers)
    output = io.StringIO(newline="")
    writer = csv.DictWriter(output, fieldnames=SAMPLE_FIELDS, extrasaction="ignore")
    writer.writeheader()
    writer.writerows(samples)
    return Response(content=output.getvalue(), media_type="text/csv; charset=utf-8", headers=headers)


@app.get("/api/process-tree")
def get_process_tree(limit: int = Query(default=500, ge=1, le=1000)) -> dict[str, Any]:
    """Return a bounded parent/child snapshot. No process path or command line is collected."""
    nodes: dict[int, dict[str, Any]] = {}
    truncated = False
    fields = ["pid", "ppid", "name", "cpu_percent", "memory_info", "status", "create_time", "num_threads"]
    for process in psutil.process_iter(fields):
        if len(nodes) >= limit:
            truncated = True
            break
        try:
            info = process.info
            pid = int(info["pid"])
            memory = info.get("memory_info")
            nodes[pid] = {
                "pid": pid,
                "ppid": int(info.get("ppid") or 0),
                "name": info.get("name") or "Unknown",
                "cpu": round(float(info.get("cpu_percent") or 0), 1),
                "ram_mb": round(memory.rss / (1024 ** 2), 1) if memory else 0.0,
                "status": info.get("status") or "unknown",
                "can_terminate": _can_terminate(process),
                "create_time": info.get("create_time"),
                "threads": info.get("num_threads"),
                "children": [],
            }
        except (psutil.NoSuchProcess, psutil.AccessDenied, psutil.ZombieProcess, TypeError, ValueError):
            continue
    roots: list[dict[str, Any]] = []
    for node in nodes.values():
        parent = nodes.get(node["ppid"])
        if parent and parent["pid"] != node["pid"]:
            parent["children"].append(node)
        else:
            roots.append(node)

    def sort_children(node: dict[str, Any]) -> None:
        node["children"].sort(key=lambda child: (child["name"].casefold(), child["pid"]))
        for child in node["children"]:
            sort_children(child)

    for root in roots:
        sort_children(root)
    roots.sort(key=lambda node: (node["name"].casefold(), node["pid"]))
    return {
        "items": roots, "count": len(nodes), "truncated": truncated,
        "sampled_at": datetime.now(timezone.utc).isoformat(),
    }


@app.post("/api/process/kill")
def kill_process(payload: ProcessKillRequest) -> dict[str, Any]:
    if payload.pid <= 4 or payload.pid in PROTECTED_PIDS:
        raise HTTPException(status_code=403, detail="This process is protected.")
    try:
        process = psutil.Process(payload.pid)
        actual_create_time = float(process.create_time())
        if abs(actual_create_time - payload.create_time) > 0.01:
            raise HTTPException(status_code=409, detail="The selected PID now belongs to a different process.")
        if not _same_user(process):
            raise HTTPException(status_code=403, detail="Only processes owned by the current user may be terminated.")
        process.terminate()
        try:
            process.wait(timeout=3)
        except psutil.TimeoutExpired as exc:
            raise HTTPException(status_code=409, detail="Process did not exit within three seconds; it was not force-killed.") from exc
        return {"status": "terminated", "pid": payload.pid}
    except psutil.NoSuchProcess as exc:
        raise HTTPException(status_code=404, detail="Process no longer exists.") from exc
    except psutil.AccessDenied as exc:
        raise HTTPException(status_code=403, detail="The operating system denied this operation.") from exc
    except psutil.ZombieProcess as exc:
        raise HTTPException(status_code=409, detail="Process is already a zombie.") from exc


@app.post("/api/terminal")
def run_terminal_command(payload: TerminalRequest) -> dict[str, Any]:
    """Allow exact read-only diagnostics only; never invoke a shell."""
    command = payload.command.strip()
    normalized = " ".join(command.split()).casefold()
    if not normalized:
        raise HTTPException(status_code=400, detail="Enter a diagnostic command.")
    if any(char in command for char in (";", "|", "&", ">", "<", "$", "\u0000", "\n", "\r")):
        raise HTTPException(status_code=400, detail="Shell operators and multi-line commands are not supported.")

    if normalized == "help":
        return _terminal("Available read-only diagnostics:\n"
                         "  help             Show this help\n  date             Show local date and time\n"
                         "  hostname         Show hostname\n  whoami           Show current OS user\n"
                         "  uptime           Show system uptime\n  platform         Show OS and Python details\n"
                         "  cpu              Show CPU usage and core counts\n  memory           Show RAM usage\n"
                         "  python --version Show Python version\n  status           Show a compact system summary\n"
                         "This console does not execute arbitrary shell commands.")
    if normalized == "date":
        return _terminal(datetime.now().astimezone().isoformat(timespec="seconds"))
    if normalized == "hostname":
        return _terminal(platform.node() or "Unknown")
    if normalized == "whoami":
        return _terminal(getpass.getuser())
    if normalized == "uptime":
        return _terminal(_format_uptime(time.time() - psutil.boot_time()))
    if normalized == "platform":
        return _terminal(f"{platform.system()} {platform.release()} ({platform.machine()})\nPython {platform.python_version()}")
    if normalized == "cpu":
        return _terminal(f"CPU usage: {psutil.cpu_percent(interval=0.1):.1f}%\n"
                         f"Logical cores: {psutil.cpu_count(logical=True) or 0}\n"
                         f"Physical cores: {psutil.cpu_count(logical=False) or 0}")
    if normalized == "memory":
        memory = psutil.virtual_memory()
        return _terminal(f"RAM: {memory.used / (1024 ** 3):.2f} / {memory.total / (1024 ** 3):.2f} GiB ({memory.percent:.1f}%)")
    if normalized == "python --version":
        return _terminal(f"Python {platform.python_version()}")
    if normalized == "status":
        memory = psutil.virtual_memory()
        return _terminal(f"Host: {platform.node() or 'Unknown'}\nOS: {platform.system()} {platform.release()}\n"
                         f"CPU: {psutil.cpu_percent(interval=0.1):.1f}%\nRAM: {memory.percent:.1f}%\n"
                         f"Uptime: {_format_uptime(time.time() - psutil.boot_time())}")
    raise HTTPException(status_code=400, detail="Command not allowed. Type 'help' for supported read-only diagnostics.")


if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="127.0.0.1", port=8000, reload=False, access_log=False, server_header=False)
