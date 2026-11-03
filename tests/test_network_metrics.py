from network_metrics import NetworkSampler, _normalize_host, build_network_history_points, diagnose_tcp_connectivity


def test_network_sampler_returns_interface_capabilities_without_addresses():
    snapshot = NetworkSampler().collect()
    assert "interfaces" in snapshot
    assert snapshot["capabilities"]["ip_addresses_collected"] is False
    for interface in snapshot["interfaces"]:
        assert {"name", "bytes_sent", "sent_bytes_per_sec"} <= interface.keys()
        assert "local_address" not in interface


def test_network_history_derives_rates_and_handles_counter_reset():
    rows = [
        {"interface_name": "eth0", "sampled_epoch": 10, "bytes_sent": 1000, "bytes_recv": 1000,
         "packets_sent": 10, "packets_recv": 10, "errors_in": 0, "errors_out": 0, "drops_in": 0, "drops_out": 0},
        {"interface_name": "eth0", "sampled_epoch": 12, "bytes_sent": 3000, "bytes_recv": 5000,
         "packets_sent": 20, "packets_recv": 30, "errors_in": 1, "errors_out": 0, "drops_in": 0, "drops_out": 0},
        {"interface_name": "eth0", "sampled_epoch": 14, "bytes_sent": 10, "bytes_recv": 20,
         "packets_sent": 2, "packets_recv": 3, "errors_in": 0, "errors_out": 0, "drops_in": 0, "drops_out": 0},
    ]
    points = build_network_history_points(rows)
    assert points[1]["sent_bytes_per_sec"] == 1000
    assert points[1]["received_bytes_per_sec"] == 2000
    assert points[1]["errors_in_delta"] == 1
    assert points[2]["sent_bytes_per_sec"] is None


def test_network_host_validation_rejects_urls_and_paths():
    assert _normalize_host("example.com") == "example.com"
    assert _normalize_host("127.0.0.1") == "127.0.0.1"
    for invalid in ("https://example.com", "example.com/path", "name with spaces", "example.com:443"):
        try:
            _normalize_host(invalid)
            assert False, "Expected invalid host to be rejected"
        except ValueError:
            pass


def test_network_connectivity_probe_is_bounded_and_reports_attempts(monkeypatch):
    import network_metrics
    monkeypatch.setattr(network_metrics.socket, "getaddrinfo", lambda *args, **kwargs: [
        (network_metrics.socket.AF_INET, network_metrics.socket.SOCK_STREAM, 0, "", ("127.0.0.1", 9))
    ])
    result = diagnose_tcp_connectivity("127.0.0.1", 9, attempts=1)
    assert result["status"] in {"connected", "tcp-failed"}
    assert result["success_count"] + result["failure_count"] == 1
    assert result["resolved_address_count"] == 1



def test_network_history_rates_are_calculated_independently_per_interface():
    rows = [
        {"interface_name": "eth0", "sampled_epoch": 10, "bytes_sent": 100, "bytes_recv": 100,
         "packets_sent": 1, "packets_recv": 1},
        {"interface_name": "wlan0", "sampled_epoch": 11, "bytes_sent": 1000, "bytes_recv": 1000,
         "packets_sent": 10, "packets_recv": 10},
        {"interface_name": "eth0", "sampled_epoch": 12, "bytes_sent": 300, "bytes_recv": 500,
         "packets_sent": 3, "packets_recv": 5},
        {"interface_name": "wlan0", "sampled_epoch": 13, "bytes_sent": 1600, "bytes_recv": 2000,
         "packets_sent": 16, "packets_recv": 20},
    ]
    points = build_network_history_points(rows)
    assert points[2]["sent_bytes_per_sec"] == 100
    assert points[2]["received_bytes_per_sec"] == 200
    assert points[3]["sent_bytes_per_sec"] == 300
    assert points[3]["received_bytes_per_sec"] == 500
