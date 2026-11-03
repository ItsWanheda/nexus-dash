from __future__ import annotations

from anomaly_detection import detect_anomalies
from local_agent import LocalAgent, OllamaUnavailable, DEFAULT_MODEL
from network_quality import assess_quality_sample, sample_targets
from process_network import collect_process_network, parse_nethogs_trace
from settings_store import SettingsStore


def test_nethogs_trace_parser_returns_process_rates_without_executable_paths():
    rows = parse_nethogs_trace(
        "/usr/bin/browser/1234/1000 12.5 8.25\n"
        "/usr/lib/video-player/2345/1000 0.0 1.5\n"
        "Refreshing: 1\n"
    )
    assert len(rows) == 2
    assert rows[0] == {
        "pid": 1234,
        "process_name": "browser",
        "upload_bytes_per_sec": 12800.0,
        "download_bytes_per_sec": 8448.0,
        "provider": "NetHogs",
    }
    assert "/usr/bin" not in str(rows)


def test_process_network_provider_reports_unsupported_windows_without_faking_rates(monkeypatch):
    import process_network
    monkeypatch.setattr(process_network.platform, "system", lambda: "Windows")
    result = collect_process_network()
    assert result["status"] == "unsupported"
    assert result["items"] == []
    assert "ETW/WFP" in result["reason"]


def test_adaptive_anomaly_detector_uses_recorded_baseline_and_absolute_guard():
    samples = [
        {"cpu_percent": 32, "ram_percent": 48, "disk_percent": 55}
        for _ in range(25)
    ]
    samples.append({"cpu_percent": 99, "ram_percent": 48, "disk_percent": 55})
    result = detect_anomalies(samples)
    assert result["status"] == "anomalies-detected"
    assert any(item["metric"] == "cpu_percent" for item in result["findings"])
    assert result["findings"][0]["baseline_median"] == 32


def test_adaptive_anomaly_detector_does_not_flag_without_baseline():
    result = detect_anomalies([{"cpu_percent": 99}])
    assert result["status"] == "insufficient-data"
    assert result["findings"] == []


def test_network_quality_flags_persistent_latency_and_dns_failures():
    slow = assess_quality_sample({
        "status": "connected", "dns_latency_ms": 270, "tcp_latency_ms": 310,
        "jitter_ms": 60, "packet_loss_percent": 0,
    })
    assert slow["unhealthy"] is True
    assert "high_dns_latency" in slow["reasons"]
    assert "high_latency_swing" in slow["reasons"]

    failed = assess_quality_sample({"status": "dns-failed"})
    assert failed["unhealthy"] is True
    assert failed["reasons"] == ["dns_or_tcp_failure"]

    healthy = assess_quality_sample({
        "status": "connected", "dns_latency_ms": 25, "tcp_latency_ms": 40,
        "jitter_ms": 7, "packet_loss_percent": 0,
    })
    assert healthy["unhealthy"] is False


def test_sample_targets_reports_real_tcp_and_dns_metrics(monkeypatch):
    import network_quality
    monkeypatch.setattr(network_quality, "diagnose_tcp_connectivity", lambda host, port, attempts: {
        "status": "connected", "dns_latency_ms": 11.5,
        "tcp_latency_ms": {"average": 30.0, "jitter": 4.0},
        "packet_loss_percent": 0.0, "success_count": 1, "failure_count": 0,
        "message": "Connected",
    })
    samples = sample_targets([{"host": "example.test", "port": 443}])
    assert len(samples) == 1
    assert samples[0]["status"] == "connected"
    assert samples[0]["dns_latency_ms"] == 11.5
    assert samples[0]["tcp_latency_ms"] == 30.0


def test_settings_validate_opt_in_network_targets_and_assistant_model(tmp_path):
    store = SettingsStore(tmp_path)
    saved = store.update({
        "network_quality_enabled": True,
        "network_quality_targets": [{"host": "example.test", "port": 443}],
        "process_network_enabled": True,
        "assistant_model": DEFAULT_MODEL,
    })
    assert saved["network_quality_enabled"] is True
    assert saved["network_quality_targets"] == [{"host": "example.test", "port": 443}]
    assert saved["process_network_enabled"] is True
    assert saved["assistant_model"] == DEFAULT_MODEL
    try:
        store.update({"network_quality_targets": [{"host": "https://example.test", "port": 443}]})
        assert False, "URL schemes must not be accepted as probe targets"
    except ValueError:
        pass
    try:
        store.update({"assistant_model": "../external/model"})
        assert False, "Local model setting must not accept path syntax"
    except ValueError:
        pass


def test_sentinel_uses_deterministic_local_fallback_when_ollama_is_offline(monkeypatch):
    agent = LocalAgent()
    def offline():
        raise OllamaUnavailable("Ollama is offline.")
    monkeypatch.setattr(agent, "models", offline)
    response = agent.chat(
        "Why is the machine slow?",
        context={"current_metrics": {"cpu_percent": 93, "ram_percent": 52}},
    )
    assert response["status"] == "fallback"
    assert response["mode"] == "built-in-guide"
    assert "CPU: 93%" in response["content"]
    assert "no cloud fallback" not in response["content"].casefold()
    assert response["context_included"] is True
