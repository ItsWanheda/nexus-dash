"""Bounded local SQLite store for privacy-conscious NEXUS telemetry history."""
from __future__ import annotations

import json
import os
import sqlite3
import threading
import time
from contextlib import closing
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

WINDOW_SECONDS = {
    "5m": 5 * 60,
    "15m": 15 * 60,
    "1h": 60 * 60,
    "6h": 6 * 60 * 60,
    "24h": 24 * 60 * 60,
    "7d": 7 * 24 * 60 * 60,
    "30d": 30 * 24 * 60 * 60,
}
SAMPLE_FIELDS = (
    "timestamp", "cpu_percent", "ram_percent", "ram_used_gb", "ram_total_gb",
    "disk_percent", "disk_used_gb", "disk_total_gb", "network_sent_bytes",
    "network_recv_bytes", "gpu_used_gb", "gpu_total_gb", "disk_read_bytes_per_sec",
    "disk_write_bytes_per_sec", "disk_read_iops", "disk_write_iops", "disk_activity_percent", "disk_latency_ms",
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
        with self._lock, closing(self._connect()) as connection:
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
            connection.execute(
                """CREATE TABLE IF NOT EXISTS timeline_events (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    created_epoch REAL NOT NULL,
                    payload TEXT NOT NULL
                )"""
            )
            connection.execute(
                "CREATE INDEX IF NOT EXISTS idx_timeline_events_epoch "
                "ON timeline_events(created_epoch)"
            )
            connection.execute(
                """CREATE TABLE IF NOT EXISTS network_interface_samples (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    sampled_epoch REAL NOT NULL,
                    interface_name TEXT NOT NULL,
                    bytes_sent INTEGER,
                    bytes_recv INTEGER,
                    packets_sent INTEGER,
                    packets_recv INTEGER,
                    errors_in INTEGER,
                    errors_out INTEGER,
                    drops_in INTEGER,
                    drops_out INTEGER,
                    is_up INTEGER,
                    speed_mbps REAL,
                    mtu INTEGER,
                    duplex TEXT,
                    is_loopback INTEGER
                )"""
            )
            connection.execute(
                "CREATE INDEX IF NOT EXISTS idx_network_samples_time "
                "ON network_interface_samples(sampled_epoch)"
            )
            connection.execute(
                "CREATE INDEX IF NOT EXISTS idx_network_samples_name_time "
                "ON network_interface_samples(interface_name, sampled_epoch)"
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
        storage_io = data.get("storage_io") or {}
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
            "disk_read_bytes_per_sec": _number(storage_io.get("read_bytes_per_sec")),
            "disk_write_bytes_per_sec": _number(storage_io.get("write_bytes_per_sec")),
            "disk_read_iops": _number(storage_io.get("read_iops")),
            "disk_write_iops": _number(storage_io.get("write_iops")),
            "disk_activity_percent": _number(storage_io.get("activity_percent")),
            "disk_latency_ms": _number(storage_io.get("latency_ms")),
        }
        sample["cpu_percent"] = min(100.0, max(0.0, float(sample["cpu_percent"] or 0)))
        sample["ram_percent"] = min(100.0, max(0.0, float(sample["ram_percent"] or 0)))
        sample["disk_percent"] = min(100.0, max(0.0, float(sample["disk_percent"] or 0)))
        if sample["disk_activity_percent"] is not None:
            sample["disk_activity_percent"] = min(100.0, max(0.0, float(sample["disk_activity_percent"])))
        return sample

    def record(self, data: dict[str, Any]) -> bool:
        """Persist a sanitised sample when the configured minimum interval elapsed."""
        now = time.time()
        sample = self._to_sample(data, now)
        payload = json.dumps(sample, separators=(",", ":"), allow_nan=False)
        with self._lock, closing(self._connect()) as connection:
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
        with self._lock, closing(self._connect()) as connection:
            rows = connection.execute(
                """SELECT payload FROM telemetry_samples
                   WHERE sampled_epoch >= ?
                   ORDER BY sampled_epoch DESC LIMIT ?""",
                (cutoff, bounded_limit),
            ).fetchall()
        return [json.loads(row["payload"]) for row in reversed(rows)]

    def count(self) -> int:
        with self._lock, closing(self._connect()) as connection:
            row = connection.execute("SELECT COUNT(*) AS total FROM telemetry_samples").fetchone()
        return int(row["total"])

    def clear_history(self) -> None:
        """Delete all stored telemetry samples and timeline events."""
        with self._lock, closing(self._connect()) as connection:
            connection.execute("DELETE FROM telemetry_samples")
            connection.execute("DELETE FROM timeline_events")
            connection.execute("DELETE FROM network_interface_samples")
            connection.commit()


    def record_event(
        self,
        category: str,
        title: str,
        detail: str = "",
        *,
        severity: str = "info",
        metadata: dict[str, Any] | None = None,
        created_at: float | None = None,
    ) -> dict[str, Any]:
        """Persist a bounded event without storing command lines or executable paths."""
        allowed_categories = {"resource", "process-start", "process-exit", "marker", "system", "network"}
        allowed_severities = {"info", "warning", "critical"}
        category_value = category if category in allowed_categories else "system"
        severity_value = severity if severity in allowed_severities else "info"
        now = float(created_at if created_at is not None else time.time())
        safe_metadata: dict[str, Any] = {}
        for key, value in list((metadata or {}).items())[:12]:
            if not isinstance(key, str) or len(key) > 40:
                continue
            if isinstance(value, (str, int, float, bool)) or value is None:
                safe_metadata[key] = str(value)[:160] if isinstance(value, str) else value
        event = {
            "timestamp": datetime.fromtimestamp(now, timezone.utc).isoformat(),
            "category": category_value,
            "severity": severity_value,
            "title": str(title)[:120],
            "detail": str(detail)[:500],
            "metadata": safe_metadata,
        }
        payload = json.dumps(event, separators=(",", ":"), allow_nan=False)
        with self._lock, closing(self._connect()) as connection:
            connection.execute(
                "INSERT INTO timeline_events(created_epoch, payload) VALUES (?, ?)",
                (now, payload),
            )
            connection.execute(
                "DELETE FROM timeline_events WHERE created_epoch < ?",
                (now - self.retention_seconds,),
            )
            connection.execute(
                """DELETE FROM timeline_events WHERE id IN (
                    SELECT id FROM timeline_events ORDER BY created_epoch DESC
                    LIMIT -1 OFFSET 10000
                )"""
            )
            connection.commit()
        return event

    def get_events(self, window: str = "24h", limit: int = 500) -> list[dict[str, Any]]:
        if window not in WINDOW_SECONDS:
            raise ValueError("Unsupported timeline window.")
        bounded_limit = max(1, min(int(limit), 2000))
        cutoff = time.time() - WINDOW_SECONDS[window]
        with self._lock, closing(self._connect()) as connection:
            rows = connection.execute(
                """SELECT payload FROM timeline_events
                   WHERE created_epoch >= ?
                   ORDER BY created_epoch DESC LIMIT ?""",
                (cutoff, bounded_limit),
            ).fetchall()
        return [json.loads(row["payload"]) for row in reversed(rows)]


    def record_network_interfaces(
        self,
        interfaces: list[dict[str, Any]],
        *,
        sampled_epoch: float | None = None,
    ) -> bool:
        """Persist interface counters and link state only; never store IP/MAC addresses."""
        if not isinstance(interfaces, list) or not interfaces:
            return False
        now = float(sampled_epoch if sampled_epoch is not None else time.time())
        prepared: list[tuple[Any, ...]] = []
        for item in interfaces[:64]:
            if not isinstance(item, dict):
                continue
            name = item.get("name")
            if not isinstance(name, str):
                continue
            safe_name = "".join(ch for ch in name.strip()[:128] if ch.isprintable())
            if not safe_name:
                continue

            def safe_int(key: str) -> int | None:
                value = _number(item.get(key))
                return max(0, int(value)) if value is not None else None

            speed = _number(item.get("speed_mbps"))
            mtu = safe_int("mtu")
            duplex = item.get("duplex")
            if duplex not in {"full", "half", "unknown"}:
                duplex = "unknown"
            is_up = item.get("is_up")
            is_loopback = item.get("is_loopback")
            prepared.append((
                now, safe_name, safe_int("bytes_sent"), safe_int("bytes_recv"),
                safe_int("packets_sent"), safe_int("packets_recv"),
                safe_int("errors_in"), safe_int("errors_out"),
                safe_int("drops_in"), safe_int("drops_out"),
                int(bool(is_up)) if is_up is not None else None,
                max(0.0, float(speed)) if speed is not None else None,
                mtu, duplex, int(bool(is_loopback)),
            ))
        if not prepared:
            return False
        max_rows = self.max_samples * 16
        with self._lock, closing(self._connect()) as connection:
            latest = connection.execute(
                "SELECT MAX(sampled_epoch) AS latest FROM network_interface_samples"
            ).fetchone()
            if latest and latest["latest"] is not None and now - float(latest["latest"]) < self.sample_interval_seconds:
                return False
            connection.executemany(
                """INSERT INTO network_interface_samples(
                    sampled_epoch, interface_name, bytes_sent, bytes_recv,
                    packets_sent, packets_recv, errors_in, errors_out,
                    drops_in, drops_out, is_up, speed_mbps, mtu, duplex, is_loopback
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
                prepared,
            )
            connection.execute(
                "DELETE FROM network_interface_samples WHERE sampled_epoch < ?",
                (now - self.retention_seconds,),
            )
            connection.execute(
                """DELETE FROM network_interface_samples WHERE id IN (
                    SELECT id FROM network_interface_samples
                    ORDER BY sampled_epoch DESC LIMIT -1 OFFSET ?
                )""",
                (max_rows,),
            )
            connection.commit()
        return True

    def get_network_history(
        self,
        window: str = "24h",
        *,
        interface: str | None = None,
        limit_per_interface: int = 2000,
    ) -> list[dict[str, Any]]:
        if window not in WINDOW_SECONDS:
            raise ValueError("Unsupported network history window.")
        cutoff = time.time() - WINDOW_SECONDS[window]
        bounded_limit = max(1, min(int(limit_per_interface), 2000))
        with self._lock, closing(self._connect()) as connection:
            if interface is not None:
                rows = connection.execute(
                    """SELECT sampled_epoch, interface_name, bytes_sent, bytes_recv,
                              packets_sent, packets_recv, errors_in, errors_out,
                              drops_in, drops_out, is_up, speed_mbps, mtu, duplex, is_loopback
                       FROM (
                         SELECT sampled_epoch, interface_name, bytes_sent, bytes_recv,
                                packets_sent, packets_recv, errors_in, errors_out,
                                drops_in, drops_out, is_up, speed_mbps, mtu, duplex, is_loopback
                         FROM network_interface_samples
                         WHERE sampled_epoch >= ? AND interface_name = ?
                         ORDER BY sampled_epoch DESC LIMIT ?
                       )
                       ORDER BY sampled_epoch ASC""",
                    (cutoff, interface[:128], bounded_limit),
                ).fetchall()
            else:
                rows = connection.execute(
                    """SELECT sampled_epoch, interface_name, bytes_sent, bytes_recv,
                              packets_sent, packets_recv, errors_in, errors_out,
                              drops_in, drops_out, is_up, speed_mbps, mtu, duplex, is_loopback
                       FROM (
                         SELECT sampled_epoch, interface_name, bytes_sent, bytes_recv,
                                packets_sent, packets_recv, errors_in, errors_out,
                                drops_in, drops_out, is_up, speed_mbps, mtu, duplex, is_loopback,
                                ROW_NUMBER() OVER (
                                  PARTITION BY interface_name ORDER BY sampled_epoch DESC
                                ) AS row_number
                         FROM network_interface_samples WHERE sampled_epoch >= ?
                       )
                       WHERE row_number <= ?
                       ORDER BY sampled_epoch ASC""",
                    (cutoff, bounded_limit),
                ).fetchall()
        return [dict(row) for row in rows]

    def get_analytics_history(
        self,
        window: str = "24h",
        *,
        compare_previous: bool = False,
    ) -> dict[str, Any]:
        """Return bounded stored samples for analytics, with an optional prior equal-length window."""
        if window not in WINDOW_SECONDS:
            raise ValueError("Unsupported analytics window.")
        duration = WINDOW_SECONDS[window]
        now = time.time()
        current_start = now - duration
        query_start = current_start - duration if compare_previous else current_start
        limit = min(self.max_samples * (2 if compare_previous else 1), 40_000)
        with self._lock, closing(self._connect()) as connection:
            rows = connection.execute(
                """SELECT sampled_epoch, payload FROM telemetry_samples
                   WHERE sampled_epoch >= ?
                   ORDER BY sampled_epoch ASC LIMIT ?""",
                (query_start, limit),
            ).fetchall()
        current: list[dict[str, Any]] = []
        previous: list[dict[str, Any]] = []
        for row in rows:
            item = json.loads(row["payload"])
            item["sampled_epoch"] = float(row["sampled_epoch"])
            if compare_previous and float(row["sampled_epoch"]) < current_start:
                previous.append(item)
            else:
                current.append(item)
        return {
            "window": window,
            "duration_seconds": duration,
            "current_start": current_start,
            "previous_start": query_start if compare_previous else None,
            "current": current,
            "previous": previous,
        }
