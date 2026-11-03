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
import re
import sqlite3
import threading
import time
from datetime import datetime, timezone
from typing import Any
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen

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
from network_metrics import NetworkSampler, collect_connections, diagnose_tcp_connectivity, build_network_history_points
from analytics import build_analytics_report
from process_network import collect_process_network
from network_quality import sample_targets, assess_quality_sample
from anomaly_detection import detect_anomalies
from local_agent import LocalAgent, DEFAULT_MODEL as DEFAULT_ASSISTANT_MODEL

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
PROCESS_INTELLIGENCE = ProcessIntelligence(max_processes=50)
LOCAL_AGENT = LocalAgent()
NETWORK_SAMPLER = NetworkSampler()
_NETWORK_ERROR_ACTIVE: set[str] = set()
_NETWORK_QUALITY_FAILURES: dict[str, int] = {}
_NETWORK_QUALITY_ALERT_LAST: dict[str, float] = {}
_NETWORK_QUALITY_LAST: float = 0.0
_ANOMALY_LAST_FIRED: dict[str, float] = {}
_PROCESS_NETWORK_LAST: float = 0.0
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
    command: str = Field(min_length=1, max_length=256)


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
    process_network_enabled: bool | None = None
    network_quality_enabled: bool | None = None
    network_quality_targets: list[dict[str, Any]] | None = None
    assistant_model: str | None = None


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


def _capture_incident(title: str, summary: str, severity: str, trigger: str) -> dict[str, Any]:
    evidence = {
        "captured_at": datetime.now(timezone.utc).isoformat(),
        "window_seconds": 600,
        "telemetry": TELEMETRY_STORE.get_history("15m", 300),
        "process_performance": TELEMETRY_STORE.get_recent_process_samples(600, 500),
        "network_quality": TELEMETRY_STORE.get_network_quality("15m", 100),
        "process_network": TELEMETRY_STORE.get_recent_process_network(600, 200),
        "timeline": TELEMETRY_STORE.get_events("15m", 200),
        "privacy": "Local evidence. Process names and PIDs may be included. No executable paths, command lines, IP/MAC addresses or packet contents are captured.",
    }
    incident = TELEMETRY_STORE.create_incident_capture(
        title, summary, severity, trigger, evidence
    )
    TELEMETRY_STORE.record_event(
        "system", f"Incident captured: {title}", summary, severity=severity,
        metadata={"incident_id": incident["id"], "trigger": trigger},
    )
    return incident


def _record_adaptive_anomalies(payload: dict[str, Any]) -> dict[str, Any]:
    report = detect_anomalies(TELEMETRY_STORE.get_history("1h", 300))
    now = time.time()
    findings = []
    for item in report.get("findings", []):
        key = str(item.get("metric"))
        if now - _ANOMALY_LAST_FIRED.get(key, 0.0) < 600:
            continue
        _ANOMALY_LAST_FIRED[key] = now
        findings.append(item)
        TELEMETRY_STORE.record_event(
            "resource", f"Adaptive anomaly: {item['label']}",
            f"Observed {item['current']}{item['unit']} versus baseline median {item['baseline_median']}{item['unit']}; robust z={item['robust_z_score']}.",
            severity=item["severity"],
            metadata={"metric": key, "current": item["current"], "baseline": item["baseline_median"],
                      "robust_z": item["robust_z_score"]},
        )
    if findings:
        _capture_incident(
            "Adaptive resource anomaly",
            "; ".join(f"{item['label']} {item['current']}{item['unit']} (baseline {item['baseline_median']}{item['unit']})" for item in findings),
            "critical" if any(item["severity"] == "critical" for item in findings) else "warning",
            "adaptive-anomaly",
        )
    report["findings"] = findings
    return report


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
            _capture_incident(title, f"Resource threshold crossed: {value:.1f}% (threshold {threshold:.0f}%).",
                              "critical" if value >= 98 else "warning", "resource-threshold")
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


def _record_network_events(snapshot: dict[str, Any]) -> None:
    for transition in snapshot.get("transitions", []):
        name = str(transition.get("name") or "interface")[:128]
        is_up = bool(transition.get("is_up"))
        TELEMETRY_STORE.record_event(
            "network", f"Network interface {name} {'connected' if is_up else 'disconnected'}",
            "Link state changed; this is an observation, not a confirmed connectivity failure.",
            severity="info" if is_up else "warning",
            metadata={"interface": name, "is_up": is_up},
        )
    for interface in snapshot.get("interfaces", []):
        name = str(interface.get("name") or "interface")[:128]
        errors = sum(int(interface.get(key) or 0) for key in ("errors_in_delta", "errors_out_delta"))
        drops = sum(int(interface.get(key) or 0) for key in ("drops_in_delta", "drops_out_delta"))
        active = name in _NETWORK_ERROR_ACTIVE
        if errors > 0 or drops > 0:
            if not active:
                TELEMETRY_STORE.record_event(
                    "network", f"Network errors or drops observed on {name}",
                    f"Observed {errors} new errors and {drops} new dropped packets since the last sample.",
                    severity="warning" if errors or drops else "info",
                    metadata={"interface": name, "errors": errors, "drops": drops},
                )
                _NETWORK_ERROR_ACTIVE.add(name)
        else:
            _NETWORK_ERROR_ACTIVE.discard(name)


def _collect_network_snapshot() -> dict[str, Any]:
    snapshot = NETWORK_SAMPLER.collect()
    if snapshot.get("interfaces"):
        TELEMETRY_STORE.record_network_interfaces(
            snapshot["interfaces"], sampled_epoch=snapshot.get("sampled_at")
        )
        _record_network_events(snapshot)
    return snapshot




def _run_network_quality_checks(settings: dict[str, Any]) -> None:
    global _NETWORK_QUALITY_LAST
    if not settings.get("network_quality_enabled"):
        return
    targets = settings.get("network_quality_targets") or []
    if not targets or time.time() - _NETWORK_QUALITY_LAST < 60:
        return
    _NETWORK_QUALITY_LAST = time.time()
    for sample in sample_targets(targets):
        key = f"{sample['host_label']}:{sample['port']}"
        # With one bounded probe per minute, inter-sample latency movement is the
        # long-window stability indicator; the on-demand probe still computes
        # within-session jitter over multiple handshakes.
        previous = TELEMETRY_STORE.get_network_quality("24h", 1000)
        prior = next((item for item in reversed(previous)
                      if item.get("host_label") == sample["host_label"]
                      and int(item.get("port") or 0) == int(sample["port"])
                      and item.get("tcp_latency_ms") is not None), None)
        if sample.get("tcp_latency_ms") is not None and prior:
            sample["jitter_ms"] = round(abs(float(sample["tcp_latency_ms"]) -
                                                float(prior["tcp_latency_ms"])), 2)
        TELEMETRY_STORE.record_network_quality(sample)
        assessment = assess_quality_sample(sample)
        tcp_latency = sample.get("tcp_latency_ms")
        dns_latency = sample.get("dns_latency_ms")
        jitter = sample.get("jitter_ms")
        loss = sample.get("packet_loss_percent")
        is_failure = str(sample.get("status") or "").casefold() != "connected"
        is_unstable = assessment["unhealthy"] and not is_failure
        consecutive = _NETWORK_QUALITY_FAILURES.get(key, 0)
        if is_failure or is_unstable:
            consecutive += 1
            _NETWORK_QUALITY_FAILURES[key] = consecutive
        else:
            _NETWORK_QUALITY_FAILURES[key] = 0
        if consecutive == 3 and time.time() - _NETWORK_QUALITY_ALERT_LAST.get(key, 0.0) >= 1800:
            _NETWORK_QUALITY_ALERT_LAST[key] = time.time()
            if is_failure:
                title = "Persistent DNS or connection interruption"
                detail = f"Three consecutive network checks failed for {key}; last status: {sample['status']}."
            else:
                title = "Persistent network latency or instability"
                detail = (
                    f"Three consecutive checks for {key} exceeded at least one stability indicator: "
                    f"DNS {dns_latency} ms, TCP {tcp_latency} ms, latency swing {jitter} ms, "
                    f"attempt loss {loss}%."
                )
            TELEMETRY_STORE.record_event("network", title, detail, severity="warning",
                                         metadata={"target": key, "consecutive_checks": consecutive,
                                                   "status": sample["status"]})
            _capture_incident(title, detail, "warning", "network-quality")


def _run_process_network_sampling(settings: dict[str, Any]) -> None:
    global _PROCESS_NETWORK_LAST
    if not settings.get("process_network_enabled") or time.time() - _PROCESS_NETWORK_LAST < 15:
        return
    _PROCESS_NETWORK_LAST = time.time()
    result = collect_process_network()
    if result.get("items"):
        TELEMETRY_STORE.record_process_network(result["items"])


def _recorder_loop() -> None:
    cycle = 0
    process_network_cycle = 0
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
                    try:
                        _record_adaptive_anomalies(payload)
                    except Exception:
                        LOGGER.exception("Adaptive anomaly detection failed")
                try:
                    _collect_network_snapshot()
                except Exception:
                    LOGGER.exception("Background network sample failed")
                try:
                    _run_network_quality_checks(settings)
                except Exception:
                    LOGGER.exception("Network quality sampling failed")
                try:
                    _run_process_network_sampling(settings)
                except Exception:
                    LOGGER.exception("Per-process network sampling failed")
                cycle += interval
                process_network_cycle += interval
                retention_seconds = int(settings["retention_days"]) * 86400
                effective_process_interval = max(
                    int(settings["process_history_interval_seconds"]),
                    math.ceil(retention_seconds * PROCESS_INTELLIGENCE.max_processes / 1_200_000),
                )
                if settings["process_history_enabled"] and cycle >= effective_process_interval:
                    process_events = PROCESS_INTELLIGENCE.sample(settings.get("process_exclusions", []))
                    TELEMETRY_STORE.record_process_samples(process_events.get("samples", []), max_rows=1_200_000)
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
        analysis = analyse_diagnostics(samples, growth, event_result["events"], window=window,
                                       event_source_status=event_result["status"])
        analysis["adaptive_anomalies"] = detect_anomalies(samples)
        analysis["incidents"] = TELEMETRY_STORE.get_incidents(50)
        return analysis
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
        "adaptive_anomalies": detect_anomalies(samples),
        "incident_captures": TELEMETRY_STORE.get_incidents(100),
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


@app.get("/api/network")
def get_network() -> dict[str, Any]:
    """Return per-interface counters, rates, link state, and error/drop deltas."""
    try:
        return _collect_network_snapshot()
    except Exception:
        LOGGER.exception("Unable to collect per-interface network telemetry")
        raise HTTPException(status_code=503, detail="Network telemetry is temporarily unavailable.")


@app.get("/api/network/connections")
def get_network_connections(
    limit: int = Query(default=200, ge=1, le=500),
    include_addresses: bool = Query(default=False),
) -> dict[str, Any]:
    """Return a bounded live socket table. IP addresses require explicit opt-in."""
    try:
        return collect_connections(limit=limit, include_addresses=include_addresses)
    except Exception:
        LOGGER.exception("Unable to enumerate network connections")
        raise HTTPException(status_code=503, detail="Network connection data is temporarily unavailable.")




@app.get("/api/network/processes")
def get_process_network(window: str = Query(default="24h"), limit: int = Query(default=500, ge=1, le=2000)) -> dict[str, Any]:
    if window not in WINDOW_SECONDS:
        raise HTTPException(status_code=400, detail="Unsupported process-network window.")
    settings = SETTINGS_STORE.get()
    if not settings.get("process_network_enabled"):
        return {"status": "disabled", "provider": None, "items": [],
                "reason": "Enable process network attribution in Settings. A compatible OS provider is required."}
    try:
        live = collect_process_network()
        if live.get("items"):
            TELEMETRY_STORE.record_process_network(live["items"])
        history = TELEMETRY_STORE.get_process_network_history(window, limit)
        return {**live, "history": history, "history_count": len(history)}
    except (OSError, RuntimeError, sqlite3.Error):
        LOGGER.exception("Process network accounting failed")
        raise HTTPException(status_code=503, detail="Process network data is temporarily unavailable.")


@app.get("/api/network/quality")
def get_network_quality(window: str = Query(default="24h"), limit: int = Query(default=1000, ge=1, le=2000)) -> dict[str, Any]:
    if window not in WINDOW_SECONDS:
        raise HTTPException(status_code=400, detail="Unsupported network quality window.")
    try:
        samples = TELEMETRY_STORE.get_network_quality(window, limit)
        return {"status": "enabled" if SETTINGS_STORE.get().get("network_quality_enabled") else "disabled",
                "targets": SETTINGS_STORE.get().get("network_quality_targets", []),
                "count": len(samples), "samples": samples}
    except (OSError, RuntimeError, sqlite3.Error):
        LOGGER.exception("Unable to read network quality history")
        raise HTTPException(status_code=503, detail="Network quality history is temporarily unavailable.")


@app.get("/api/anomalies")
def get_anomalies(window: str = Query(default="1h")) -> dict[str, Any]:
    if window not in WINDOW_SECONDS:
        raise HTTPException(status_code=400, detail="Unsupported anomaly analysis window.")
    try:
        report = detect_anomalies(TELEMETRY_STORE.get_history(window, 2000))
        report["window"] = window
        return report
    except (OSError, RuntimeError, sqlite3.Error):
        LOGGER.exception("Anomaly analysis failed")
        raise HTTPException(status_code=503, detail="Anomaly analysis is temporarily unavailable.")


class AssistantRequest(BaseModel):
    message: str = Field(min_length=1, max_length=2000)
    model: str | None = Field(default=None, max_length=120)
    history: list[dict[str, str]] = Field(default_factory=list, max_length=8)
    include_context: bool = True


class IncidentCaptureRequest(BaseModel):
    title: str = Field(min_length=1, max_length=120)
    note: str = Field(default="", max_length=500)
    severity: str = Field(default="info", pattern="^(info|warning|critical)$")




def _assistant_context() -> dict[str, Any]:
    stats = _collect_stats()
    samples = TELEMETRY_STORE.get_history("15m", 120)
    diagnostics = detect_anomalies(TELEMETRY_STORE.get_history("1h", 300))
    process_samples = TELEMETRY_STORE.get_recent_process_samples(300, 100)
    process_latest: dict[tuple[int, float], dict[str, Any]] = {}
    for item in process_samples:
        process_latest[(int(item["pid"]), float(item["create_time"]))] = item
    top_processes = sorted(
        process_latest.values(), key=lambda item: float(item.get("rss_mb") or 0), reverse=True
    )[:12]
    incidents = TELEMETRY_STORE.get_incidents(10)
    quality = TELEMETRY_STORE.get_network_quality("1h", 30)
    return {
        "captured_at": datetime.now(timezone.utc).isoformat(),
        "current_metrics": {
            "cpu_percent": stats.get("cpu", {}).get("percent"),
            "ram_percent": stats.get("ram", {}).get("percent"),
            "disk_percent": stats.get("disk", {}).get("percent"),
        },
        "recent_telemetry": samples[-30:],
        "diagnostics": diagnostics,
        "top_processes": [
            {key: item.get(key) for key in ("pid", "process_name", "cpu_percent", "rss_mb", "threads",
                                              "read_bytes_per_sec", "write_bytes_per_sec")}
            for item in top_processes
        ],
        "network_quality_recent": quality[-10:],
        "recent_incidents": incidents,
        "limits": "No command lines, executable paths, passwords, tokens, remote addresses or packet content are included.",
    }


@app.get("/api/assistant/status")
def get_assistant_status() -> dict[str, Any]:
    settings = SETTINGS_STORE.get()
    status = LOCAL_AGENT.status()
    status["configured_model"] = settings.get("assistant_model", DEFAULT_ASSISTANT_MODEL)
    status["agent"] = "NEXUS Sentinel"
    return status


@app.get("/api/assistant/models")
def get_assistant_models() -> dict[str, Any]:
    return LOCAL_AGENT.status()


@app.post("/api/assistant/chat")
def assistant_chat(payload: AssistantRequest) -> dict[str, Any]:
    settings = SETTINGS_STORE.get()
    model = payload.model or settings.get("assistant_model", DEFAULT_ASSISTANT_MODEL)
    history = []
    for item in payload.history[:8]:
        if isinstance(item, dict) and item.get("role") in {"user", "assistant"}:
            history.append({"role": item["role"], "content": str(item.get("content") or "")[:2000]})
    try:
        context = _assistant_context() if payload.include_context else None
        result = LOCAL_AGENT.chat(payload.message.strip(), model=model, history=history, context=context)
        return result
    except (OSError, RuntimeError, ValueError, sqlite3.Error):
        LOGGER.exception("NEXUS Sentinel request failed")
        raise HTTPException(status_code=503, detail="NEXUS Sentinel could not assemble its local context.")
@app.get("/api/incidents")
def list_incidents(limit: int = Query(default=100, ge=1, le=250)) -> dict[str, Any]:
    return {"incidents": TELEMETRY_STORE.get_incidents(limit)}


@app.get("/api/incidents/{incident_id}")
def read_incident(incident_id: int) -> dict[str, Any]:
    incident = TELEMETRY_STORE.get_incident(incident_id)
    if incident is None:
        raise HTTPException(status_code=404, detail="Incident capture was not found.")
    return incident


@app.post("/api/incidents/capture")
def capture_incident(payload: IncidentCaptureRequest) -> dict[str, Any]:
    try:
        incident = _capture_incident(payload.title.strip(), payload.note.strip() or "User requested a forensic snapshot.",
                                     payload.severity, "manual")
        return {"status": "captured", "incident": incident}
    except (OSError, ValueError, sqlite3.Error):
        LOGGER.exception("Manual incident capture failed")
        raise HTTPException(status_code=503, detail="Incident capture could not be saved.")


@app.get("/api/network/history")
def get_network_history(
    window: str = Query(default="24h"),
    interface: str | None = Query(default=None, min_length=1, max_length=128),
    limit: int = Query(default=600, ge=1, le=2000),
) -> dict[str, Any]:
    if window not in WINDOW_SECONDS:
        raise HTTPException(status_code=400, detail="Unsupported network history window.")
    try:
        rows = TELEMETRY_STORE.get_network_history(
            window, interface=interface, limit_per_interface=limit
        )
        points = build_network_history_points(rows)
        return {"window": window, "interface": interface, "count": len(points),
                "samples": points, "storage": "local-sqlite"}
    except (OSError, RuntimeError, ValueError, sqlite3.Error):
        LOGGER.exception("Unable to read network interface history")
        raise HTTPException(status_code=503, detail="Network history is temporarily unavailable.")


@app.get("/api/network/diagnostics")
def network_diagnostics(
    host: str = Query(min_length=1, max_length=253),
    port: int = Query(default=443, ge=1, le=65535),
    attempts: int = Query(default=3, ge=1, le=3),
) -> dict[str, Any]:
    """Run a user-requested DNS + TCP handshake probe. No application payload is sent."""
    try:
        return diagnose_tcp_connectivity(host, port, attempts=attempts)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


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




@app.get("/api/updates/check")
def check_for_updates() -> dict[str, Any]:
    """Manually check the latest published GitHub release; no code is downloaded or installed."""
    current = DIAGNOSTICS_VERSION
    request = Request(
        "https://api.github.com/repos/ItsWanheda/nexus-dash/releases/latest",
        headers={"Accept": "application/vnd.github+json", "User-Agent": "NEXUS-DASH-update-check"},
    )
    try:
        with urlopen(request, timeout=4) as response:
            release = json.loads(response.read(512_000).decode("utf-8"))
    except HTTPError as exc:
        if exc.code == 404:
            return {"status": "no-release", "current_version": current, "update_available": False,
                    "message": "No published GitHub release is available yet."}
        return {"status": "unavailable", "current_version": current,
                "update_available": False, "message": "GitHub release information is temporarily unavailable."}
    except (OSError, URLError, TimeoutError, ValueError):
        return {"status": "unavailable", "current_version": current,
                "update_available": False, "message": "Could not reach GitHub to check for a published release."}

    tag = str(release.get("tag_name") or "").strip()
    latest = tag[1:] if tag.lower().startswith("v") else tag
    if not latest or not re.fullmatch(r"\d+(?:\.\d+){1,3}(?:[-+][0-9A-Za-z.-]+)?", latest):
        return {"status": "unavailable", "current_version": current,
                "update_available": False, "message": "The latest release tag is not a supported version format."}
    def version_parts(value: str) -> tuple[int, ...]:
        match = re.match(r"^(\d+(?:\.\d+){1,3})", value)
        return tuple(int(part) for part in match.group(1).split(".")) if match else (0,)
    current_parts, latest_parts = version_parts(current), version_parts(latest)
    width = max(len(current_parts), len(latest_parts))
    available = latest_parts + (0,) * (width - len(latest_parts)) > current_parts + (0,) * (width - len(current_parts))
    release_url = str(release.get("html_url") or "")
    if not release_url.startswith("https://github.com/ItsWanheda/nexus-dash/releases/"):
        release_url = ""
    return {
        "status": "update-available" if available else "up-to-date",
        "current_version": current, "latest_version": latest, "update_available": available,
        "release_url": release_url, "published_at": release.get("published_at"),
        "message": "A newer release is available." if available else "NEXUS-DASH is up to date with the latest published release.",
    }


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


def _inspect_process(pid: int, create_time: float) -> dict[str, Any]:
    result = PROCESS_INTELLIGENCE.inspect(pid, create_time)
    if SETTINGS_STORE.get()["privacy_mode"]:
        result["owner"] = None
        result["executable"]["path"] = None
        result["executable"]["status"] = "Redacted by privacy mode"
    return result


@app.get("/api/processes/{pid}")
def get_process_detail(pid: int, create_time: float = Query(gt=0)) -> dict[str, Any]:
    try:
        return _inspect_process(pid, create_time)
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
    windows = {"5m": 300, "15m": 900, "30m": 1800, "1h": 3600, "6h": 21600,
               "24h": 86400, "7d": 604800, "30d": 2592000}
    if window not in windows:
        raise HTTPException(status_code=400, detail="Unsupported process-history window.")
    try:
        history = TELEMETRY_STORE.get_process_history(pid, create_time, windows[window], limit=2000)
        if not history:
            history = PROCESS_INTELLIGENCE.history(pid, create_time, windows[window])
        return {"pid": pid, "create_time": create_time, "window": window, "samples": history,
                "count": len(history), "status": "Available" if history else "Warming up",
                "storage": "local-sqlite" if history else "in-memory-or-empty"}
    except (OSError, sqlite3.Error, ValueError):
        LOGGER.exception("Unable to read persistent process history")
        raise HTTPException(status_code=503, detail="Process history is temporarily unavailable.")


@app.get("/api/process-compare")
def compare_processes(
    pid_a: int = Query(gt=0), create_time_a: float = Query(gt=0),
    pid_b: int = Query(gt=0), create_time_b: float = Query(gt=0),
) -> dict[str, Any]:
    try:
        return {"processes": [
            _inspect_process(pid_a, create_time_a),
            _inspect_process(pid_b, create_time_b),
        ]}
    except LookupError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except PermissionError as exc:
        raise HTTPException(status_code=403, detail=str(exc)) from exc


@app.get("/api/analytics")
def get_analytics(
    window: str = Query(default="24h"),
    compare_previous: bool = Query(default=False),
    bucket_seconds: int | None = Query(default=None, ge=60, le=86400),
) -> dict[str, Any]:
    if window not in WINDOW_SECONDS:
        raise HTTPException(status_code=400, detail="Unsupported analytics window.")
    default_buckets = {
        "5m": 60, "15m": 60, "1h": 300, "6h": 900,
        "24h": 3600, "7d": 21600, "30d": 86400,
    }
    try:
        history = TELEMETRY_STORE.get_analytics_history(window, compare_previous=compare_previous)
        network_rows = TELEMETRY_STORE.get_network_history(window, limit_per_interface=20_000)
        events = TELEMETRY_STORE.get_events(window, limit=2000)
        return build_analytics_report(
            history["current"], history["previous"], network_rows, events,
            window=window, bucket_seconds=bucket_seconds or default_buckets[window],
        )
    except (OSError, RuntimeError, ValueError, sqlite3.Error):
        LOGGER.exception("Unable to build historical analytics")
        raise HTTPException(status_code=503, detail="Historical analytics are temporarily unavailable.")


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
    from terminal_service import execute_terminal_command
    result = execute_terminal_command(payload.command)
    if result["returncode"] == 2:
        raise HTTPException(status_code=400, detail=result["stderr"] or "Command not allowed.")
    return result


if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="127.0.0.1", port=8000, reload=False, access_log=False, server_header=False)
