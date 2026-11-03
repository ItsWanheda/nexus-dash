"""Robust, explainable local anomaly detection using rolling median/MAD baselines."""
from __future__ import annotations

import math
from statistics import median
from typing import Any

METRICS = {
    "cpu_percent": {"label": "CPU utilisation", "unit": "%", "absolute": 85.0},
    "ram_percent": {"label": "Memory utilisation", "unit": "%", "absolute": 85.0},
    "disk_percent": {"label": "System volume capacity", "unit": "%", "absolute": 95.0},
    "disk_activity_percent": {"label": "Disk activity", "unit": "%", "absolute": 90.0},
    "disk_latency_ms": {"label": "Disk latency", "unit": "ms", "absolute": 50.0},
    "disk_read_bytes_per_sec": {"label": "Disk read throughput", "unit": "B/s", "absolute": None},
    "disk_write_bytes_per_sec": {"label": "Disk write throughput", "unit": "B/s", "absolute": None},
}


def _finite(value: Any) -> float | None:
    if value is None or isinstance(value, bool):
        return None
    try:
        number = float(value)
    except (TypeError, ValueError, OverflowError):
        return None
    return number if math.isfinite(number) else None


def detect_anomalies(samples: list[dict[str, Any]], *, min_baseline: int = 20, max_baseline: int = 120) -> dict[str, Any]:
    """Compare the latest point with prior samples only; no labels or ML model required."""
    if not samples:
        return {"status": "insufficient-data", "sample_count": 0, "findings": [], "method": "rolling median/MAD"}
    latest = samples[-1]
    baseline = samples[-(max_baseline + 1):-1]
    findings = []
    evaluated = 0
    for key, spec in METRICS.items():
        values = [value for item in baseline if (value := _finite(item.get(key))) is not None]
        current = _finite(latest.get(key))
        if current is None or len(values) < min_baseline:
            continue
        evaluated += 1
        center = median(values)
        deviations = [abs(value - center) for value in values]
        mad = median(deviations)
        absolute = spec["absolute"]
        robust_z = None
        method = "median/MAD"
        anomalous = False
        if mad > 0:
            robust_z = 0.6745 * (current - center) / mad
            anomalous = robust_z >= 3.5 and (absolute is None or current >= absolute)
        elif absolute is not None:
            # When historical samples are identical, require a genuine threshold breach
            # and a clear step-change above the baseline rather than dividing by zero.
            anomalous = current >= absolute and current > center + max(5.0, abs(center) * 0.25)
            method = "absolute threshold + baseline step (MAD=0)"
        else:
            anomalous = center > 0 and current >= center * 3.0
            method = "3x baseline (MAD=0)"
        if anomalous:
            ratio = round(current / center, 2) if center > 0 else None
            severity = "critical" if absolute is not None and current >= absolute + 10 else "warning"
            findings.append({
                "metric": key, "label": spec["label"], "current": round(current, 3),
                "baseline_median": round(center, 3), "baseline_mad": round(mad, 3),
                "robust_z_score": round(robust_z, 2) if robust_z is not None else None,
                "ratio_to_baseline": ratio, "unit": spec["unit"],
                "threshold": absolute, "severity": severity, "method": method,
                "interpretation": "The latest value is unusually high relative to the machine's recent recorded baseline. This is a signal to investigate, not proof of root cause.",
            })
    return {
        "status": "anomalies-detected" if findings else "normal" if evaluated else "insufficient-data",
        "sample_count": len(samples), "baseline_samples": len(baseline),
        "evaluated_metrics": evaluated, "method": "rolling median/MAD with documented absolute-threshold fallback",
        "findings": findings,
    }
