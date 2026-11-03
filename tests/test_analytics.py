from analytics import build_analytics_report


def test_analytics_calculates_percentiles_scorecards_comparison_and_incidents():
    samples = [{
        "timestamp": f"2026-11-01T0{index}:00:00+00:00",
        "sampled_epoch": 1793510000 + index * 60,
        "cpu_percent": value, "ram_percent": 35 + value / 2, "disk_percent": 50,
        "disk_activity_percent": 10, "disk_latency_ms": 2,
        "network_sent_bytes": index * 1000, "network_recv_bytes": index * 2000,
    } for index, value in enumerate((10, 20, 30, 40, 90))]
    previous = [{"sampled_epoch": 1793509000, "cpu_percent": 5, "ram_percent": 10, "disk_percent": 50}]
    report = build_analytics_report(
        samples, previous, [], [{"category": "marker", "severity": "info", "title": "test"}],
        window="24h", bucket_seconds=300,
    )
    assert report["metrics"]["cpu_percent"]["average"] == 38
    assert report["metrics"]["cpu_percent"]["maximum"] == 90
    assert report["metrics"]["cpu_percent"]["p95"] is not None
    assert report["scorecards"][0]["status"] == "intermittent-pressure"
    assert report["comparison"]["cpu_percent"]["previous"] == 5
    assert report["incidents"]["by_category"]["marker"] == 1
    assert len(report["distribution"]["cpu"]) == 5


def test_analytics_reports_missing_thermal_data_without_fabricating_it():
    report = build_analytics_report([], [], [], [], window="1h", bucket_seconds=60)
    thermal = next(item for item in report["scorecards"] if item["key"] == "thermal")
    assert thermal["status"] == "not-recorded"
    assert report["coverage"]["status"] == "insufficient-data"
