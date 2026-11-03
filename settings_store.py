"""Validated per-user NEXUS configuration stored beside the local telemetry DB."""
from __future__ import annotations

import json
import os
import threading
from pathlib import Path
from typing import Any


DEFAULT_SETTINGS: dict[str, Any] = {
    "sampling_interval_seconds": 5,
    "retention_days": 1,
    "background_recording": True,
    "process_history_enabled": True,
    "process_history_interval_seconds": 15,
    "process_exclusions": [],
    "privacy_mode": True,
    "start_minimized": False,
}


class SettingsStore:
    def __init__(self, directory: str | os.PathLike[str]) -> None:
        self.directory = Path(directory).expanduser()
        self.path = self.directory / "settings.json"
        self._lock = threading.RLock()
        self.directory.mkdir(mode=0o700, parents=True, exist_ok=True)

    def get(self) -> dict[str, Any]:
        with self._lock:
            try:
                saved = json.loads(self.path.read_text(encoding="utf-8"))
            except (OSError, ValueError, TypeError):
                saved = {}
            result = dict(DEFAULT_SETTINGS)
            if isinstance(saved, dict):
                for key in DEFAULT_SETTINGS:
                    if key in saved:
                        result[key] = saved[key]
            result["data_directory"] = str(self.directory)
            result["database_path"] = str(self.directory / "telemetry.sqlite3")
            result["retention_note"] = "Retention applies to raw samples; long windows are retained up to the configured limit."
            return result

    def update(self, changes: dict[str, Any]) -> dict[str, Any]:
        unknown = set(changes) - set(DEFAULT_SETTINGS)
        if unknown:
            raise ValueError("Unsupported settings: " + ", ".join(sorted(unknown)))
        with self._lock:
            current = {key: self.get()[key] for key in DEFAULT_SETTINGS}
            next_values = dict(current)
            next_values.update(changes)
            if next_values["sampling_interval_seconds"] not in {5, 10, 15, 30}:
                raise ValueError("Sampling interval must be 5, 10, 15, or 30 seconds.")
            if next_values["retention_days"] not in {1, 7, 30}:
                raise ValueError("Retention must be 1, 7, or 30 days.")
            if next_values["process_history_interval_seconds"] not in {5, 10, 15, 30}:
                raise ValueError("Process history interval must be 5, 10, 15, or 30 seconds.")
            for key in ("background_recording", "process_history_enabled", "privacy_mode", "start_minimized"):
                if not isinstance(next_values[key], bool):
                    raise ValueError(key + " must be a boolean.")
            exclusions = next_values["process_exclusions"]
            if not isinstance(exclusions, list) or len(exclusions) > 50:
                raise ValueError("Process exclusions must be a list of at most 50 executable names.")
            cleaned = []
            for name in exclusions:
                if not isinstance(name, str) or not name.strip() or len(name.strip()) > 100:
                    raise ValueError("Each excluded process name must contain 1–100 characters.")
                cleaned.append(name.strip()[:100])
            next_values["process_exclusions"] = list(dict.fromkeys(cleaned))
            temporary = self.path.with_suffix(".json.tmp")
            temporary.write_text(json.dumps(next_values, indent=2, allow_nan=False), encoding="utf-8")
            try:
                os.chmod(temporary, 0o600)
            except OSError:
                pass
            temporary.replace(self.path)
            try:
                os.chmod(self.path, 0o600)
            except OSError:
                pass
        return self.get()
