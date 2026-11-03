"""Bounded historical analytics and evidence-backed resource scorecards."""
from __future__ import annotations

import math
from collections import Counter, defaultdict
from datetime import datetime, timezone
from typing import Any

PRESSURE_THRESHOLDS = {
    "cpu_percent": 85.0, "ram_percent": 85.0, "disk_percent": 90.0,
    "disk_activity_percent": 90.0, "disk_latency_ms": 50.0,
}


def _number(value: Any) -> float | None:
    if value is None or isinstance(value, bool):
        return None
    try:
        result = float(value)
    except (TypeError, ValueError, OverflowError):
        return None
    return result if math.isfinite(result) else None


def _percentile(values: list[float], percentile: float) -> float | None:
    if not values:
        return None
    ordered = sorted(values)
    position = (len(ordered) - 1) * percentile
    low, high = int(math.floor(position)), int(math.ceil(position))
    if low == high:
        return round(ordered[low], 3)
    fraction = position - low
    return round(ordered[low] * (1 - fraction) + ordered[high] * fraction, 3)


def _describe(values: list[float], threshold: float | None = None) -> dict[str, Any]:
    valid = [value for value in values if math.isfinite(value)]
    if not valid:
        return {"count": 0, "average": None, "minimum": None, "maximum": None,
                "p50": None, "p95": None, "latest": None, "threshold": threshold,
                "above_threshold": 0, "above_threshold_percent": None}
    above = sum(1 for value in valid if threshold is not None and value >= threshold)
    return {
        "count": len(valid), "average": round(sum(valid) / len(valid), 3),
        "minimum": round(min(valid), 3), "maximum": round(max(valid), 3),
        "p50": _percentile(valid, 0.50), "p95": _percentile(valid, 0.95),
        "latest": round(valid[-1], 3), "threshold": threshold, "above_threshold": above,
        "above_threshold_percent": round(above / len(valid) * 100, 2) if threshold is not None else None,
    }


def _network_rates(samples: list[dict[str, Any]]) -> list[dict[str, Any]]:
    output, previous = [], None
    for item in samples:
        sent = _number(item.get("network_sent_bytes"))
        received = _number(item.get("network_recv_bytes"))
        epoch = _number(item.get("sampled_epoch"))
        if previous and sent is not None and received is not None and epoch is not None:
            elapsed = epoch - previous["epoch"]
            if elapsed > 0 and sent >= previous["sent"] and received >= previous["received"]:
                output.append({
                    "epoch": epoch, "sent_bytes_per_sec": (sent - previous["sent"]) / elapsed,
                    "received_bytes_per_sec": (received - previous["received"]) / elapsed,
                })
        if sent is not None and received is not None and epoch is not None:
            previous = {"sent": sent, "received": received, "epoch": epoch}
    return output


def _network_rates_from_interface(points: list[dict[str, Any]]) -> list[dict[str, float]]:
    output = []
    for previous, current in zip(points, points[1:]):
        elapsed = float(current.get("sampled_epoch") or 0) - float(previous.get("sampled_epoch") or 0)
        if elapsed <= 0:
            continue
        pair = {}
        for key, target in (("bytes_sent", "sent_bytes_per_sec"), ("bytes_recv", "received_bytes_per_sec")):
            before, after = _number(previous.get(key)), _number(current.get(key))
            if before is None or after is None or after < before:
                break
            pair[target] = (after - before) / elapsed
        if len(pair) == 2:
            output.append(pair)
    return output


def _counter_deltas(points: list[dict[str, Any]], key: str) -> list[int]:
    output = []
    for previous, current in zip(points, points[1:]):
        before, after = _number(previous.get(key)), _number(current.get(key))
        if before is not None and after is not None and after >= before:
            output.append(int(after - before))
    return output


def _interface_summary(rows: list[dict[str, Any]]) -> dict[str, Any]:
    grouped: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for row in rows:
        grouped[str(row.get("interface_name") or "Unknown")].append(row)
    summaries = []
    sent_total = received_total = error_total = drop_total = 0
    weighted_up_seconds = observed_seconds = 0.0
    for name, points in grouped.items():
        points.sort(key=lambda item: float(item.get("sampled_epoch") or 0))
        first, last = points[0], points[-1]
        sent_first, sent_last = _number(first.get("bytes_sent")), _number(last.get("bytes_sent"))
        recv_first, recv_last = _number(first.get("bytes_recv")), _number(last.get("bytes_recv"))
        sent = max(0, sent_last - sent_first) if sent_first is not None and sent_last is not None and sent_last >= sent_first else 0
        received = max(0, recv_last - recv_first) if recv_first is not None and recv_last is not None and recv_last >= recv_first else 0
        sent_total += sent
        received_total += received
        rates = _network_rates_from_interface(points)
        errors = sum(_counter_deltas(points, "errors_in")) + sum(_counter_deltas(points, "errors_out"))
        drops = sum(_counter_deltas(points, "drops_in")) + sum(_counter_deltas(points, "drops_out"))
        error_total += errors
        drop_total += drops
        up_points = [item for item in points if item.get("is_up") is not None]
        up_percent = sum(1 for item in up_points if item["is_up"]) / len(up_points) * 100 if up_points else None
        duration = max(0.0, float(last.get("sampled_epoch") or 0) - float(first.get("sampled_epoch") or 0))
        observed_seconds += duration if not bool(last.get("is_loopback")) else 0
        if up_percent is not None and not bool(last.get("is_loopback")):
            weighted_up_seconds += duration * up_percent / 100
        summaries.append({
            "name": name, "sample_count": len(points), "sent_bytes": sent, "received_bytes": received,
            "average_upload_bytes_per_sec": _describe([p["sent_bytes_per_sec"] for p in rates])["average"],
            "peak_upload_bytes_per_sec": _describe([p["sent_bytes_per_sec"] for p in rates])["maximum"],
            "average_download_bytes_per_sec": _describe([p["received_bytes_per_sec"] for p in rates])["average"],
            "peak_download_bytes_per_sec": _describe([p["received_bytes_per_sec"] for p in rates])["maximum"],
            "error_delta_count": errors, "drop_delta_count": drops,
            "link_up_percent": round(up_percent, 2) if up_percent is not None else None,
            "speed_mbps": last.get("speed_mbps"), "loopback": bool(last.get("is_loopback")),
        })
    summaries.sort(key=lambda item: item["sent_bytes"] + item["received_bytes"], reverse=True)
    return {
        "interfaces": summaries[:32], "sent_bytes": sent_total, "received_bytes": received_total,
        "error_delta_count": error_total, "drop_delta_count": drop_total,
        "link_up_percent": round(weighted_up_seconds / observed_seconds * 100, 2) if observed_seconds > 0 else None,
        "sample_count": len(rows),
    }


def _bucket_series(samples: list[dict[str, Any]], network_rates: list[dict[str, Any]], bucket_seconds: int) -> list[dict[str, Any]]:
    buckets: dict[int, dict[str, list[float]]] = defaultdict(lambda: defaultdict(list))
    for item in samples:
        epoch = _number(item.get("sampled_epoch"))
        if epoch is None:
            continue
        bucket = int(epoch // bucket_seconds * bucket_seconds)
        for source, target in (
            ("cpu_percent", "cpu"), ("ram_percent", "ram"), ("disk_percent", "disk"),
            ("disk_read_bytes_per_sec", "disk_read"), ("disk_write_bytes_per_sec", "disk_write"),
            ("disk_latency_ms", "disk_latency"),
        ):
            value = _number(item.get(source))
            if value is not None:
                buckets[bucket][target].append(value)
    for item in network_rates:
        bucket = int(float(item["epoch"]) // bucket_seconds * bucket_seconds)
        buckets[bucket]["network_upload"].append(float(item["sent_bytes_per_sec"]))
        buckets[bucket]["network_download"].append(float(item["received_bytes_per_sec"]))
    output = []
    for bucket in sorted(buckets):
        point: dict[str, Any] = {"timestamp": datetime.fromtimestamp(bucket, timezone.utc).isoformat(), "epoch": bucket}
        for key, values in buckets[bucket].items():
            point[key + "_average"] = round(sum(values) / len(values), 3)
            point[key + "_peak"] = round(max(values), 3)
        output.append(point)
    return output[-500:]


def _hourly_profile(samples: list[dict[str, Any]]) -> list[dict[str, Any]]:
    buckets: dict[int, dict[str, list[float]]] = defaultdict(lambda: defaultdict(list))
    for item in samples:
        epoch = _number(item.get("sampled_epoch"))
        if epoch is None:
            continue
        hour = datetime.fromtimestamp(epoch, timezone.utc).hour
        for source, target in (("cpu_percent", "cpu"), ("ram_percent", "ram"), ("disk_percent", "disk")):
            value = _number(item.get(source))
            if value is not None:
                buckets[hour][target].append(value)
    output = []
    for hour in range(24):
        metrics = buckets[hour]
        output.append({
            "hour_utc": hour,
            **{name + "_average": round(sum(values) / len(values), 2) if values else None
               for name, values in metrics.items()},
            "sample_count": max((len(values) for values in metrics.values()), default=0),
        })
    return output


def _distribution(values: list[float]) -> list[dict[str, Any]]:
    output = []
    total = len(values)
    for lower, upper in ((0, 25), (25, 50), (50, 75), (75, 90), (90, 101)):
        count = sum(1 for value in values if lower <= value < upper)
        output.append({
            "range": f"{lower}-{min(100, upper)}%", "lower": lower,
            "upper": min(100, upper), "count": count,
            "percent": round(count / total * 100, 2) if total else 0.0,
        })
    return output


def _scorecard(key: str, title: str, summary: dict[str, Any], threshold: float | None, minimum_samples: int = 3) -> dict[str, Any]:
    count = int(summary.get("count") or 0)
    above = int(summary.get("above_threshold") or 0)
    ratio = summary.get("above_threshold_percent")
    if count < minimum_samples or threshold is None:
        status = "insufficient-data"
    elif above == 0:
        status = "no-sustained-pressure"
    elif ratio is not None and ratio >= 50:
        status = "sustained-pressure"
    else:
        status = "intermittent-pressure"
    return {
        "key": key, "title": title, "status": status, "samples": count, "threshold": threshold,
        "samples_above_threshold": above, "above_threshold_percent": ratio,
        "average": summary.get("average"), "p95": summary.get("p95"), "maximum": summary.get("maximum"),
    }


def _compare(current: dict[str, Any], previous: dict[str, Any]) -> dict[str, Any]:
    before, after = previous.get("average"), current.get("average")
    difference = None if after is None or before is None else round(after - before, 3)
    percent = None if difference is None or before in (None, 0) else round(difference / abs(before) * 100, 2)
    return {"current": after, "previous": before, "change": difference, "change_percent": percent}


def build_analytics_report(
    current_samples: list[dict[str, Any]],
    previous_samples: list[dict[str, Any]],
    network_rows: list[dict[str, Any]],
    events: list[dict[str, Any]],
    *,
    window: str,
    bucket_seconds: int,
) -> dict[str, Any]:
    metrics = [
        ("cpu_percent", "CPU utilisation", 85.0), ("ram_percent", "Memory utilisation", 85.0),
        ("disk_percent", "System volume capacity", 90.0), ("disk_activity_percent", "Disk activity", 90.0),
        ("disk_latency_ms", "Disk response latency", 50.0),
        ("disk_read_bytes_per_sec", "Disk read throughput", None),
        ("disk_write_bytes_per_sec", "Disk write throughput", None),
        ("disk_read_iops", "Disk read IOPS", None), ("disk_write_iops", "Disk write IOPS", None),
    ]
    current_metrics, previous_metrics = {}, {}
    for key, _title, threshold in metrics:
        current_metrics[key] = _describe([v for item in current_samples if (v := _number(item.get(key))) is not None], threshold)
        previous_metrics[key] = _describe([v for item in previous_samples if (v := _number(item.get(key))) is not None], threshold)

    network_rates = _network_rates(current_samples)
    network = _interface_summary(network_rows)
    network_current = {
        "upload": _describe([item["sent_bytes_per_sec"] for item in network_rates]),
        "download": _describe([item["received_bytes_per_sec"] for item in network_rates]),
        "interfaces": network["interfaces"], "sent_bytes": network["sent_bytes"],
        "received_bytes": network["received_bytes"], "error_delta_count": network["error_delta_count"],
        "drop_delta_count": network["drop_delta_count"], "link_up_percent": network["link_up_percent"],
        "sample_count": network["sample_count"],
    }

    cpu, memory = current_metrics["cpu_percent"], current_metrics["ram_percent"]
    activity_metric = current_metrics["disk_activity_percent"]
    latency_metric = current_metrics["disk_latency_ms"]
    storage_count = max(int(activity_metric["count"]), int(latency_metric["count"]))
    storage_above = max(int(activity_metric["above_threshold"]), int(latency_metric["above_threshold"]))
    storage_ratio = max(
        float(activity_metric["above_threshold_percent"] or 0),
        float(latency_metric["above_threshold_percent"] or 0),
    )
    if storage_count < 3:
        storage_status = "insufficient-data"
    elif storage_above == 0:
        storage_status = "no-sustained-pressure"
    elif storage_ratio >= 50:
        storage_status = "sustained-pressure"
    else:
        storage_status = "intermittent-pressure"
    network_errors = network_current["error_delta_count"] + network_current["drop_delta_count"]
    non_loopback_rows = [row for row in network_rows if not bool(row.get("is_loopback"))]
    network_card = {
        "key": "network", "title": "Network stability",
        "status": "insufficient-data" if len(non_loopback_rows) < 3 else
                  ("intermittent-pressure" if network_errors else "no-observed-errors"),
        "samples": len(non_loopback_rows), "errors": network_current["error_delta_count"],
        "drops": network_current["drop_delta_count"], "link_up_percent": network_current["link_up_percent"],
    }
    categories = Counter(str(event.get("category") or "system") for event in events)
    severities = Counter(str(event.get("severity") or "info") for event in events)
    cpu_values = [v for item in current_samples if (v := _number(item.get("cpu_percent"))) is not None]
    memory_values = [v for item in current_samples if (v := _number(item.get("ram_percent"))) is not None]
    return {
        "window": window, "generated_at": datetime.now(timezone.utc).isoformat(),
        "sample_count": len(current_samples), "previous_sample_count": len(previous_samples),
        "coverage": {
            "status": "available" if len(current_samples) >= 3 else "insufficient-data",
            "first_sample": current_samples[0].get("timestamp") if current_samples else None,
            "last_sample": current_samples[-1].get("timestamp") if current_samples else None,
            "expected_sample_count": None,
            "note": "Only locally recorded samples are included. Missing periods are not interpolated.",
        },
        "metrics": current_metrics, "network": network_current,
        "scorecards": [
            _scorecard("cpu", "CPU pressure", cpu, 85.0),
            _scorecard("memory", "Memory pressure", memory, 85.0),
            {
                "key": "storage", "title": "Storage performance", "status": storage_status,
                "samples": storage_count, "activity": activity_metric, "latency": latency_metric,
                "samples_above_threshold": storage_above, "above_threshold_percent": storage_ratio,
            },
            network_card,
            {"key": "thermal", "title": "Thermal conditions", "status": "not-recorded",
             "samples": 0, "note": "Temperature readings are currently live-only; historical thermal sampling is not enabled."},
        ],
        "distribution": {"cpu": _distribution(cpu_values), "memory": _distribution(memory_values)},
        "hourly_profile_utc": _hourly_profile(current_samples),
        "trend": _bucket_series(current_samples, network_rates, max(60, int(bucket_seconds))),
        "incidents": {
            "total": len(events), "by_category": dict(categories),
            "by_severity": dict(severities), "recent": events[-20:],
        },
        "comparison": {
            key: _compare(current_metrics[key], previous_metrics[key]) for key, _title, _threshold in metrics
        } if previous_samples else {},
        "limitations": [
            "Analytics are descriptive and do not establish root cause.",
            "Network process attribution is a live socket snapshot; per-process network byte counters are not persisted.",
            "Thermal readings are live-only and are not included in historical analytics.",
            "Missing metrics are not interpreted as zero or healthy.",
        ],
    }
