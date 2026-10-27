"""Local-only NEXUS system telemetry API. The terminal is diagnostics-only."""
from __future__ import annotations

import getpass
import ipaddress
import logging
import os
import platform
import time
from datetime import datetime, timezone
from typing import Any

import psutil
from fastapi import FastAPI, HTTPException, Query, Request
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel, Field
from starlette.middleware.trustedhost import TrustedHostMiddleware
from starlette.responses import JSONResponse

LOGGER = logging.getLogger("nexus")
ALLOWED_ORIGINS = {
    "http://127.0.0.1:5500", "http://localhost:5500",
    "http://127.0.0.1:5501", "http://localhost:5501",
    "http://127.0.0.1:8000", "http://localhost:8000",
}
PROTECTED_PIDS = {0, 1, 2, 3, 4, os.getpid(), os.getppid()}
_NVML_INITIALIZED = False

app = FastAPI(title="NEXUS Local System API", version="1.2.0",
              docs_url=None, redoc_url=None, openapi_url=None)
app.add_middleware(TrustedHostMiddleware, allowed_hosts=["127.0.0.1", "localhost", "[::1]"])
app.add_middleware(CORSMiddleware, allow_origins=sorted(ALLOWED_ORIGINS),
                   allow_credentials=False, allow_methods=["GET", "POST", "OPTIONS"],
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
def health() -> dict[str, str]:
    return {"status": "ok", "service": "nexus-local-api", "version": "1.2.0"}


@app.get("/api/stats")
def get_stats() -> dict[str, Any]:
    try:
        memory = psutil.virtual_memory()
        net = psutil.net_io_counters()
        disk = psutil.disk_usage(os.path.abspath(os.sep))
        boot_time = psutil.boot_time()
        uptime = max(0, time.time() - boot_time)
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


@app.get("/api/processes")
def get_processes(limit: int = Query(default=100, ge=1, le=200)) -> dict[str, Any]:
    items = []
    for process in psutil.process_iter(["pid", "name", "cpu_percent", "memory_info", "status"]):
        try:
            info = process.info
            memory = info.get("memory_info")
            items.append({"pid": info["pid"], "name": info.get("name") or "Unknown",
                          "cpu": round(float(info.get("cpu_percent") or 0), 1),
                          "ram_mb": round(memory.rss / (1024 ** 2), 1) if memory else 0,
                          "status": info.get("status") or "unknown", "can_terminate": _can_terminate(process)})
        except (psutil.NoSuchProcess, psutil.AccessDenied, psutil.ZombieProcess):
            continue
    items.sort(key=lambda item: (item["cpu"], item["ram_mb"]), reverse=True)
    return {"items": items[:limit], "count": min(len(items), limit),
            "sampled_at": datetime.now(timezone.utc).isoformat()}


@app.post("/api/process/kill")
def kill_process(payload: ProcessKillRequest) -> dict[str, Any]:
    if payload.pid <= 4 or payload.pid in PROTECTED_PIDS:
        raise HTTPException(status_code=403, detail="This process is protected.")
    try:
        process = psutil.Process(payload.pid)
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
