from telemetry_store import TelemetryStore


def sample(cpu=22.5, ram=41.0):
    return {
        "sampled_at": "2026-10-27T12:00:00+00:00",
        "cpu": {"percent": cpu, "cores": 8},
        "ram": {"percent": ram, "used_gb": 6.5, "total_gb": 16},
        "disk": {"percent": 55, "used_gb": 200, "total_gb": 500},
        "network": {"sent_bytes": 1234, "recv_bytes": 5678},
        "gpu": {"status": "Unavailable", "used_gb": None, "total_gb": None},
        "storage_io": {"read_bytes_per_sec": 1024, "write_bytes_per_sec": 2048, "read_iops": 4, "write_iops": 5, "activity_percent": 42, "latency_ms": 3.5},
        "system": {"hostname": "must-not-be-stored", "user": "also-must-not-be-stored"},
    }


def test_history_records_sanitised_resource_samples(tmp_path):
    store = TelemetryStore(tmp_path / "history", sample_interval_seconds=0)
    assert store.record(sample())
    history = store.get_history("1h", 10)
    assert len(history) == 1
    point = history[0]
    assert point["cpu_percent"] == 22.5
    assert point["ram_percent"] == 41.0
    assert point["network_sent_bytes"] == 1234
    assert "hostname" not in point
    assert "user" not in point
    assert store.count() == 1


def test_history_write_interval_throttles_duplicate_samples(tmp_path):
    store = TelemetryStore(tmp_path / "throttled", sample_interval_seconds=60)
    assert store.record(sample())
    assert not store.record(sample(cpu=99))
    assert store.count() == 1
    assert store.get_history("1h", 10)[0]["cpu_percent"] == 22.5


def test_history_is_capped_to_configured_maximum(tmp_path):
    store = TelemetryStore(
        tmp_path / "bounded", sample_interval_seconds=0, max_samples=10,
        retention_seconds=24 * 60 * 60,
    )
    for value in range(15):
        store.record(sample(cpu=value))
    history = store.get_history("24h", 100)
    assert store.count() == 10
    assert len(history) == 10
    assert history[-1]["cpu_percent"] == 14.0


def test_history_rejects_unknown_window(tmp_path):
    store = TelemetryStore(tmp_path / "invalid-window")
    try:
        store.get_history("forever", 20)
        assert False, "Expected unsupported window to raise ValueError"
    except ValueError:
        pass



def test_timeline_event_storage_is_bounded_and_sanitised(tmp_path):
    store = TelemetryStore(tmp_path / "events")
    event = store.record_event(
        "marker", "Started IDE", "Build started",
        metadata={"pid": 123, "path": "C:/private/app.exe", "bad": object()},
    )
    assert event["title"] == "Started IDE"
    assert "path" in event["metadata"]
    assert store.get_events("24h", 10)[0]["title"] == "Started IDE"
    try:
        store.get_events("forever", 10)
        assert False, "Expected unsupported window to raise ValueError"
    except ValueError:
        pass



def test_clear_history_deletes_samples_and_events(tmp_path):
    store = TelemetryStore(tmp_path / "clear")
    data = {
        "cpu": {"percent": 10}, "ram": {"percent": 20}, "disk": {"percent": 30},
        "network": {"sent_bytes": 0, "recv_bytes": 0}, "gpu": {}, "storage_io": {},
    }
    assert store.record(data)
    store.record_event("marker", "test marker")
    store.clear_history()
    assert store.count() == 0
    assert store.get_events("24h", 20) == []



def test_network_interface_history_stores_only_counters_and_link_metadata(tmp_path):
    store = TelemetryStore(tmp_path / "network-history", sample_interval_seconds=0)
    interfaces = [{
        "name": "Ethernet", "is_up": True, "is_loopback": False, "speed_mbps": 1000, "mtu": 1500,
        "duplex": "full", "bytes_sent": 1000, "bytes_recv": 2000, "packets_sent": 10,
        "packets_recv": 20, "errors_in": 0, "errors_out": 0, "drops_in": 0, "drops_out": 0,
        "local_address": "192.0.2.10", "mac": "aa:bb:cc:dd:ee:ff",
    }]
    assert store.record_network_interfaces(interfaces)
    rows = store.get_network_history("24h", interface="Ethernet", limit_per_interface=20)
    assert len(rows) == 1
    assert rows[0]["interface_name"] == "Ethernet"
    assert "local_address" not in rows[0]
    assert "mac" not in rows[0]


def test_analytics_history_supports_30_day_window_and_previous_period(tmp_path):
    store = TelemetryStore(tmp_path / "analytics-history", sample_interval_seconds=0)
    data = {
        "cpu": {"percent": 15}, "ram": {"percent": 20, "used_gb": 2, "total_gb": 8},
        "disk": {"percent": 30, "used_gb": 30, "total_gb": 100},
        "network": {"sent_bytes": 100, "recv_bytes": 200}, "gpu": {}, "storage_io": {},
    }
    store.record(data)
    report = store.get_analytics_history("30d", compare_previous=True)
    assert report["window"] == "30d"
    assert len(report["current"]) == 1
    assert report["previous"] == []
