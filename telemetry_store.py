"""Bounded local SQLite store for privacy-conscious NEXUS telemetry history."""
from __future__ import annotations

import json
import os
import sqlite3
import threading
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

WINDOW_SECONDS = {
    "5m": 5 * 60,
    "15m": 15 * 60,
    "1h": 60 * 60,
    "6h": 6 * 60 * 60,
    "24h": 24 * 60 * 60,
}
SAMPLE_FIELDS = (
    "timestamp", "cpu_percent", "ram_percent", "ram_used_gb", "ram_total_gb",
    "disk_percent", "disk_used_gb", "disk_total_gb", "network_sent_bytes",
    "network_recv_bytes", "gpu_used_gb", "gpu_total_gb",
)


def _number(value: Any, default: float | int | None = None) -> float | int | None:
    if value is None or isinstance(value, bool):
        return default
    try:
        result = float(value)
    except (TypeError, ValueError, OverflowError):
        return default
    if not (result == result and abs(result) != float("inf")):
        return default
    return result


class TelemetryStore:
    """SQLite recorder with bounded retention, write throttling, and serialised access."""

    def __init__(
        self,
        directory: str | os.PathLike[str] | None = None,
        *,
        retention_seconds: int = 24 * 60 * 60,
        max_samples: int = 20_000,
        sample_interval_seconds: float = 5.0,
    ) -> None:
        if directory is None:
            configured = os.environ.get("NEXUS_DATA_DIR")
            directory = Path(configured).expanduser() if configured else Path.home() / ".nexus-dash"
        self.directory = Path(directory).expanduser()
        self.db_path = self.directory / "telemetry.sqlite3"
        self.retention_seconds = max(60, int(retention_seconds))
        self.max_samples = max(10, int(max_samples))
        self.sample_interval_seconds = max(0.0, float(sample_interval_seconds))
        self._lock = threading.RLock()
        self._initialise()

    def _connect(self) -> sqlite3.Connection:
        connection = sqlite3.connect(str(self.db_path), timeout=3.0)
        connection.row_factory = sqlite3.Row
        connection.execute("PRAGMA busy_timeout = 3000")
        return connection

    def _initialise(self) -> None:
        self.directory.mkdir(mode=0o700, parents=True, exist_ok=True)
        with self._lock, self._connect() as connection:
            connection.execute("PRAGMA journal_mode = WAL")
            connection.execute(
                """CREATE TABLE IF NOT EXISTS telemetry_samples (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    sampled_epoch REAL NOT NULL,
                    payload TEXT NOT NULL
                )"""
            )
            connection.execute(
                "CREATE INDEX IF NOT EXISTS idx_telemetry_samples_epoch "
                "ON telemetry_samples(sampled_epoch)"
            )
            connection.commit()
        try:
            os.chmod(self.directory, 0o700)
            os.chmod(self.db_path, 0o600)
        except OSError:
            # Windows and some filesystems do not support POSIX mode semantics.
            pass

    @staticmethod
    def _to_sample(data: dict[str, Any], now: float) -> dict[str, Any]:
        cpu = data.get("cpu") or {}
        ram = data.get("ram") or {}
        disk = data.get("disk") or {}
        network = data.get("network") or {}
        gpu = data.get("gpu") or {}
        timestamp = data.get("sampled_at")
        if not isinstance(timestamp, str):
            timestamp = datetime.fromtimestamp(now, timezone.utc).isoformat()
        # Deliberately exclude hostname, username, process names, paths and other
        # identifying host details from the persistent telemetry history.
        sample = {
            "timestamp": timestamp,
            "cpu_percent": _number(cpu.get("percent"), 0.0),
            "ram_percent": _number(ram.get("percent"), 0.0),
            "ram_used_gb": _number(ram.get("used_gb"), 0.0),
            "ram_total_gb": _number(ram.get("total_gb"), 0.0),
            "disk_percent": _number(disk.get("percent"), 0.0),
            "disk_used_gb": _number(disk.get("used_gb"), 0.0),
            "disk_total_gb": _number(disk.get("total_gb"), 0.0),
            "network_sent_bytes": int(_number(network.get("sent_bytes"), 0) or 0),
            "network_recv_bytes": int(_number(network.get("recv_bytes"), 0) or 0),
            "gpu_used_gb": _number(gpu.get("used_gb")),
            "gpu_total_gb": _number(gpu.get("total_gb")),
        }
        sample["cpu_percent"] = min(100.0, max(0.0, float(sample["cpu_percent"] or 0)))
        sample["ram_percent"] = min(100.0, max(0.0, float(sample["ram_percent"] or 0)))
        sample["disk_percent"] = min(100.0, max(0.0, float(sample["disk_percent"] or 0)))
        return sample

    def record(self, data: dict[str, Any]) -> bool:
        """Persist a sanitised sample when the configured minimum interval elapsed."""
        now = time.time()
        sample = self._to_sample(data, now)
        payload = json.dumps(sample, separators=(",", ":"), allow_nan=False)
        with self._lock, self._connect() as connection:
            latest = connection.execute(
                "SELECT sampled_epoch FROM telemetry_samples "
                "ORDER BY sampled_epoch DESC LIMIT 1"
            ).fetchone()
            if latest and now - float(latest["sampled_epoch"]) < self.sample_interval_seconds:
                return False
            connection.execute(
                "INSERT INTO telemetry_samples(sampled_epoch, payload) VALUES (?, ?)",
                (now, payload),
            )
            connection.execute(
                "DELETE FROM telemetry_samples WHERE sampled_epoch < ?",
                (now - self.retention_seconds,),
            )
            connection.execute(
                """DELETE FROM telemetry_samples
                   WHERE id IN (
                       SELECT id FROM telemetry_samples
                       ORDER BY sampled_epoch DESC
                       LIMIT -1 OFFSET ?
                   )""",
                (self.max_samples,),
            )
            connection.commit()
        return True

    def get_history(self, window: str = "1h", limit: int = 600) -> list[dict[str, Any]]:
        if window not in WINDOW_SECONDS:
            raise ValueError("Unsupported history window.")
        bounded_limit = max(1, min(int(limit), 2000))
        cutoff = time.time() - WINDOW_SECONDS[window]
        with self._lock, self._connect() as connection:
            rows = connection.execute(
                """SELECT payload FROM telemetry_samples
                   WHERE sampled_epoch >= ?
                   ORDER BY sampled_epoch DESC LIMIT ?""",
                (cutoff, bounded_limit),
            ).fetchall()
        return [json.loads(row["payload"]) for row in reversed(rows)]

    def count(self) -> int:
        with self._lock, self._connect() as connection:
            row = connection.execute("SELECT COUNT(*) AS total FROM telemetry_samples").fetchone()
        return int(row["total"])
