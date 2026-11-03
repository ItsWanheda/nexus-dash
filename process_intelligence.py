"""Best-effort, bounded per-process history and inspection.

Process histories are keyed by (PID, creation time) so PID reuse cannot join
unrelated processes. Executable paths and handles are returned only on explicit
inspection; they are never written to the telemetry database.
"""
from __future__ import annotations

import os
import threading
import time
from collections import deque
from datetime import datetime, timezone
from typing import Any

import psutil


class ProcessIntelligence:
    def __init__(self, *, max_processes: int = 200, max_samples: int = 360) -> None:
        self.max_processes = max(10, min(int(max_processes), 500))
        self.max_samples = max(30, min(int(max_samples), 1000))
        self._lock = threading.RLock()
        self._history: dict[tuple[int, float], deque[dict[str, Any]]] = {}
        self._known: dict[int, tuple[float, str]] = {}
        self._primed = False

    @staticmethod
    def _safe(callable_value, default=None):
        try:
            return callable_value()
        except (psutil.Error, OSError, AttributeError, NotImplementedError):
            return default

    @staticmethod
    def _io(process: psutil.Process) -> dict[str, int] | None:
        try:
            counters = process.io_counters()
            return {
                "read_bytes": int(getattr(counters, "read_bytes", 0)),
                "write_bytes": int(getattr(counters, "write_bytes", 0)),
                "read_count": int(getattr(counters, "read_count", 0)),
                "write_count": int(getattr(counters, "write_count", 0)),
            }
        except (psutil.Error, OSError, AttributeError, NotImplementedError):
            return None

    def sample(self, exclusions: list[str] | None = None) -> dict[str, Any]:
        excluded = {str(name).casefold() for name in (exclusions or [])}
        now = time.time()
        observed: dict[int, tuple[float, str]] = {}
        candidates: list[tuple[float, psutil.Process, dict[str, Any]]] = []

        for process in psutil.process_iter(["pid", "name", "create_time", "memory_info", "status"]):
            try:
                info = process.info
                pid = int(info["pid"])
                name = str(info.get("name") or "Unknown")
                if name.casefold() in excluded:
                    continue
                created = float(info.get("create_time") or process.create_time())
                memory = info.get("memory_info")
                rss = int(memory.rss) if memory else 0
                cpu = float(process.cpu_percent(interval=None) or 0.0)
                threads = int(process.num_threads())
                io = self._io(process)
                record = {
                    "timestamp": datetime.fromtimestamp(now, timezone.utc).isoformat(),
                    "epoch": now,
                    "cpu_percent": round(max(0.0, cpu), 2),
                    "rss_mb": round(rss / (1024 ** 2), 2),
                    "threads": threads,
                    "read_bytes": io["read_bytes"] if io else None,
                    "write_bytes": io["write_bytes"] if io else None,
                }
                observed[pid] = (created, name)
                candidates.append((rss, process, record))
            except (psutil.Error, OSError, TypeError, ValueError):
                continue

        candidates.sort(key=lambda item: item[0], reverse=True)
        selected = candidates[: self.max_processes]
        with self._lock:
            started: list[dict[str, Any]] = []
            exited: list[dict[str, Any]] = []
            if self._primed:
                for pid, (created, name) in observed.items():
                    previous = self._known.get(pid)
                    if previous is None or abs(previous[0] - created) > 0.01:
                        started.append({"pid": pid, "name": name, "create_time": created})
                for pid, (created, name) in self._known.items():
                    current = observed.get(pid)
                    if current is None or abs(current[0] - created) > 0.01:
                        exited.append({"pid": pid, "name": name, "create_time": created})
            self._primed = True
            self._known = observed
            active_keys: set[tuple[int, float]] = set()
            for _, process, record in selected:
                key = (int(process.pid), float(observed[int(process.pid)][0]))
                active_keys.add(key)
                history = self._history.setdefault(key, deque(maxlen=self.max_samples))
                history.append(record)
            # Bound stale identity histories as well as active process histories.
            for key in list(self._history):
                if key not in active_keys and len(self._history) > self.max_processes * 2:
                    self._history.pop(key, None)
            return {"started": started[:50], "exited": exited[:50],
                    "tracked_processes": len(active_keys), "sampled_at": datetime.fromtimestamp(now, timezone.utc).isoformat()}

    def inspect(self, pid: int, expected_create_time: float) -> dict[str, Any]:
        try:
            process = psutil.Process(int(pid))
            created = float(process.create_time())
            if abs(created - float(expected_create_time)) > 0.01:
                raise psutil.NoSuchProcess(pid, msg="PID now belongs to a different process.")
            with process.oneshot():
                name = process.name()
                memory = process.memory_info()
                full_memory = self._safe(process.memory_full_info)
                cpu = float(self._safe(lambda: process.cpu_percent(interval=None), 0.0) or 0.0)
                threads = int(self._safe(process.num_threads, 0) or 0)
                status = self._safe(process.status, "unknown")
                ppid = int(self._safe(process.ppid, 0) or 0)
                exe = self._safe(process.exe, None)
                username = self._safe(process.username, None)
                io = self._io(process)
                num_handles = self._safe(lambda: process.num_handles(), None)
                num_fds = self._safe(lambda: process.num_fds(), None)
                parent = self._safe(process.parent, None)
                children = self._safe(lambda: process.children(recursive=False), [])
            now = time.time()
            with self._lock:
                history = list(self._history.get((int(pid), created), []))
            initial_rss = history[0]["rss_mb"] if history else round(memory.rss / (1024 ** 2), 2)
            current_rss = round(memory.rss / (1024 ** 2), 2)
            first_io = history[0] if history else {}
            last_io = history[-1] if history else {}
            elapsed = max(0.001, float(last_io.get("epoch", now)) - float(first_io.get("epoch", now)))
            read_rate = None
            write_rate = None
            if io and first_io.get("read_bytes") is not None and last_io.get("read_bytes") is not None:
                read_rate = round(max(0, io["read_bytes"] - int(first_io["read_bytes"])) / max(1.0, now - float(first_io.get("epoch", now))), 1)
                write_rate = round(max(0, io["write_bytes"] - int(first_io["write_bytes"])) / max(1.0, now - float(first_io.get("epoch", now))), 1)
            parent_info = None
            if parent:
                parent_info = {"pid": parent.pid, "name": self._safe(parent.name, "Unknown")}
            child_info = []
            for child in children or []:
                child_info.append({"pid": child.pid, "name": self._safe(child.name, "Unknown")})
            executable_size = None
            executable_name = os.path.basename(exe) if exe else None
            if exe:
                try:
                    executable_size = os.path.getsize(exe)
                except OSError:
                    pass
            return {
                "pid": int(pid), "create_time": created, "name": name, "status": status,
                "cpu_percent": round(max(0.0, cpu), 2), "rss_mb": current_rss,
                "vms_mb": round(memory.vms / (1024 ** 2), 2),
                "uss_mb": round(full_memory.uss / (1024 ** 2), 2) if full_memory and hasattr(full_memory, "uss") else None,
                "threads": threads, "uptime_seconds": round(max(0.0, now - created), 1),
                "started_at": datetime.fromtimestamp(created, timezone.utc).isoformat(),
                "ppid": ppid, "parent": parent_info, "children": child_info,
                "io": {"read_bytes": io["read_bytes"] if io else None,
                       "write_bytes": io["write_bytes"] if io else None,
                       "read_rate_bytes_per_sec": read_rate, "write_rate_bytes_per_sec": write_rate},
                "handles": {"count": int(num_handles) if num_handles is not None else None,
                            "file_descriptors": int(num_fds) if num_fds is not None else None,
                            "status": "Available" if num_handles is not None or num_fds is not None else "Unsupported"},
                "executable": {"name": executable_name, "path": exe, "size_bytes": executable_size,
                               "status": "Available" if exe else "Unavailable"},
                "owner": username,
                "history": history[-120:],
                "history_status": "Available" if history else "Warming up",
            }
        except psutil.NoSuchProcess as exc:
            raise LookupError("The process no longer exists or its PID was reused.") from exc
        except psutil.AccessDenied as exc:
            raise PermissionError("The operating system denied access to this process.") from exc

    def history(self, pid: int, expected_create_time: float, window_seconds: int = 1800) -> list[dict[str, Any]]:
        cutoff = time.time() - max(60, min(int(window_seconds), 86400))
        key = (int(pid), float(expected_create_time))
        with self._lock:
            return [point for point in self._history.get(key, []) if float(point.get("epoch", 0)) >= cutoff]
