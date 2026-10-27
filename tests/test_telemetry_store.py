from telemetry_store import TelemetryStore


def sample(cpu=22.5, ram=41.0):
    return {
        "sampled_at": "2026-10-27T12:00:00+00:00",
        "cpu": {"percent": cpu, "cores": 8},
        "ram": {"percent": ram, "used_gb": 6.5, "total_gb": 16},
        "disk": {"percent": 55, "used_gb": 200, "total_gb": 500},
        "network": {"sent_bytes": 1234, "recv_bytes": 5678},
        "gpu": {"status": "Unavailable", "used_gb": None, "total_gb": None},
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
