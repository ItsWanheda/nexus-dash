"""User-configured continuous DNS/TCP quality probes. No default internet targets."""
from __future__ import annotations

import time
from typing import Any

from network_metrics import diagnose_tcp_connectivity


def sample_targets(targets: list[dict[str, Any]]) -> list[dict[str, Any]]:
    output = []
    for target in targets[:3]:
        host = str(target.get("host") or "").strip()[:253]
        try:
            port = int(target.get("port", 443))
            result = diagnose_tcp_connectivity(host, port, attempts=1)
        except (ValueError, OSError) as exc:
            output.append({
                "sampled_epoch": time.time(), "host_label": host or "invalid target",
                "port": int(target.get("port", 443) or 443), "status": "invalid-target",
                "dns_latency_ms": None, "tcp_latency_ms": None, "jitter_ms": None,
                "packet_loss_percent": 100.0, "success_count": 0, "failure_count": 1,
                "reason": str(exc)[:200],
            })
            continue
        latency = result.get("tcp_latency_ms") or {}
        output.append({
            "sampled_epoch": time.time(), "host_label": host, "port": port,
            "status": result.get("status", "unknown"),
            "dns_latency_ms": result.get("dns_latency_ms"),
            "tcp_latency_ms": latency.get("average"),
            "jitter_ms": latency.get("jitter"),
            "packet_loss_percent": result.get("packet_loss_percent", 100.0),
            "success_count": int(result.get("success_count", 0)),
            "failure_count": int(result.get("failure_count", 1)),
            "reason": result.get("message"),
        })
    return output
