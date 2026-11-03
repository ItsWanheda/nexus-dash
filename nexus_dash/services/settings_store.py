"""Validated per-user NEXUS configuration stored beside the local telemetry DB."""
from __future__ import annotations

import json
import math
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
    "process_network_enabled": False,
    "network_quality_enabled": False,
    "network_quality_targets": [],
    "assistant_model": "qwen3.5:4b",
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
            retention_seconds = int(result["retention_days"]) * 86400
            effective_interval = max(int(result["sampling_interval_seconds"]), math.ceil(retention_seconds / 20_000))
            result["effective_sampling_interval_seconds"] = effective_interval
            result["data_directory"] = str(self.directory)
            result["database_path"] = str(self.directory / "telemetry.sqlite3")
            result["retention_note"] = (
                f"Up to {result['retention_days']} days within 20,000 samples; "
                f"effective recorder cadence is at least {effective_interval} seconds."
            )
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
            for key in ("background_recording", "process_history_enabled", "privacy_mode", "start_minimized",
                        "process_network_enabled", "network_quality_enabled"):
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
            targets = next_values["network_quality_targets"]
            if not isinstance(targets, list) or len(targets) > 3:
                raise ValueError("Configure at most three network-quality targets.")
            cleaned_targets = []
            for target in targets:
                if not isinstance(target, dict):
                    raise ValueError("Each network-quality target must contain a host and port.")
                host = str(target.get("host") or "").strip().rstrip(".")
                try:
                    port = int(target.get("port", 443))
                except (TypeError, ValueError) as exc:
                    raise ValueError("Network-quality port must be an integer.") from exc
                if not host or len(host) > 253 or any(char in host for char in "/\\?#@% \t\r\n") or not 1 <= port <= 65535:
                    raise ValueError("Network-quality targets must be hostnames or IP addresses with ports 1–65535.")
                cleaned_targets.append({"host": host, "port": port})
            next_values["network_quality_targets"] = cleaned_targets
            model = str(next_values["assistant_model"] or "qwen3.5:4b").strip()
            if not model or len(model) > 120 or any(char in model for char in "/\\?#@% \t\r\n"):
                raise ValueError("Assistant model must be an installed local Ollama model name.")
            next_values["assistant_model"] = model
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
