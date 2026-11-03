"""Optional per-process traffic accounting. No packet payload is retained."""
from __future__ import annotations

import platform
import re
import shutil
import subprocess
from typing import Any


_ROW = re.compile(r"^(?P<identity>.+?)/(?P<pid>[1-9][0-9]*)/(?P<uid>[0-9]+)\s+(?P<sent>[0-9]+(?:\.[0-9]+)?)\s+(?P<received>[0-9]+(?:\.[0-9]+)?)\s*$")


def parse_nethogs_trace(text: str) -> list[dict[str, Any]]:
    """Parse NetHogs trace rows (default kB/s view); command line and user ID are discarded."""
    output = []
    for line in str(text or "").splitlines():
        match = _ROW.match(line.strip())
        if not match:
            continue
        identity = match.group("identity")
        name = identity.replace("\\", "/").rsplit("/", 1)[-1][:120] or "Unknown"
        try:
            output.append({
                "pid": int(match.group("pid")),
                "process_name": name,
                "upload_bytes_per_sec": max(0.0, float(match.group("sent")) * 1024.0),
                "download_bytes_per_sec": max(0.0, float(match.group("received")) * 1024.0),
                "provider": "NetHogs",
            })
        except (ValueError, OverflowError):
            continue
    return output[:200]


def collect_process_network() -> dict[str, Any]:
    """Run one bounded Linux NetHogs sample if installed; other OSes report honest limits."""
    system = platform.system()
    if system != "Linux":
        return {
            "status": "unsupported",
            "provider": None,
            "items": [],
            "reason": "Per-process byte-rate attribution requires an OS accounting provider. NetHogs is the supported provider in this build on Linux; Windows ETW/WFP and macOS providers are not yet implemented.",
        }
    executable = shutil.which("nethogs")
    if not executable:
        return {"status": "not-installed", "provider": "NetHogs", "items": [],
                "reason": "Install NetHogs to enable Linux per-process bandwidth accounting."}
    try:
        result = subprocess.run(
            [executable, "-t", "-c", "1", "-d", "1"],
            capture_output=True, text=True, timeout=5, check=False, shell=False,
        )
    except subprocess.TimeoutExpired:
        return {"status": "timeout", "provider": "NetHogs", "items": [],
                "reason": "NetHogs did not complete its bounded one-sample capture within five seconds."}
    except OSError as exc:
        return {"status": "unavailable", "provider": "NetHogs", "items": [], "reason": str(exc)[:240]}
    if result.returncode != 0:
        detail = (result.stderr or result.stdout or "NetHogs exited unsuccessfully.").strip()[:240]
        return {"status": "permission-denied" if "permission" in detail.casefold() or "root" in detail.casefold() else "unavailable",
                "provider": "NetHogs", "items": [], "reason": detail}
    items = parse_nethogs_trace(result.stdout)
    return {"status": "available" if items else "warming-up", "provider": "NetHogs",
            "items": items, "reason": None if items else "NetHogs returned no parseable process-rate rows in this sample."}
