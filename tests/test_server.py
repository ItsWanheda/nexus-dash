from fastapi.testclient import TestClient

from server import app

client = TestClient(app, base_url="http://127.0.0.1", client=("127.0.0.1", 54321))


def test_health_endpoint_reports_service():
    response = client.get("/api/health")
    assert response.status_code == 200
    assert response.json()["status"] == "ok"


def test_stats_contains_metric_groups():
    response = client.get("/api/stats")
    assert response.status_code == 200
    payload = response.json()
    assert {"cpu", "ram", "network", "disk", "gpu", "system", "sampled_at"} <= payload.keys()
    assert 0 <= payload["cpu"]["percent"] <= 100
    assert 0 <= payload["ram"]["percent"] <= 100
    assert payload["network"]["sent_bytes"] >= 0
    assert payload["system"]["hostname"]


def test_process_snapshot_is_bounded():
    response = client.get("/api/processes?limit=5")
    assert response.status_code == 200
    payload = response.json()
    assert len(payload["items"]) <= 5
    assert payload["count"] <= 5


def test_terminal_help_only_describes_diagnostics():
    response = client.post("/api/terminal", json={"command": "help"})
    assert response.status_code == 200
    assert "uptime" in response.json()["stdout"]
    assert "does not execute arbitrary shell" in response.json()["stdout"]


def test_terminal_rejects_arbitrary_shell_command():
    response = client.post("/api/terminal", json={"command": "echo hello"})
    assert response.status_code == 400
    assert "not allowed" in response.json()["detail"].lower()


def test_terminal_rejects_shell_operators():
    assert client.post("/api/terminal", json={"command": "uptime; whoami"}).status_code == 400


def test_terminal_rejects_oversized_input():
    assert client.post("/api/terminal", json={"command": "x" * 121}).status_code == 422


def test_unapproved_browser_origin_is_rejected():
    response = client.get("/api/health", headers={"Origin": "https://untrusted.example"})
    assert response.status_code == 403



def test_history_endpoint_uses_supported_windows_and_rejects_unknown():
    response = client.get("/api/history?window=1h&limit=10")
    assert response.status_code == 200
    payload = response.json()
    assert payload["window"] == "1h"
    assert payload["storage"] == "local-sqlite"
    assert payload["count"] == len(payload["samples"])
    assert client.get("/api/history?window=forever").status_code == 400


def test_history_export_supports_csv_and_json():
    csv_response = client.get("/api/history/export?format=csv&window=24h&limit=20")
    assert csv_response.status_code == 200
    assert "text/csv" in csv_response.headers["content-type"]
    assert "cpu_percent" in csv_response.text
    json_response = client.get("/api/history/export?format=json&window=24h&limit=20")
    assert json_response.status_code == 200
    assert json_response.json()["sample_count"] == len(json_response.json()["samples"])
    assert client.get("/api/history/export?format=exe").status_code == 400


def test_process_tree_is_bounded_and_has_expected_shape():
    response = client.get("/api/process-tree?limit=10")
    assert response.status_code == 200
    payload = response.json()
    assert payload["count"] <= 10
    assert isinstance(payload["items"], list)
    assert isinstance(payload["truncated"], bool)
    def visit(nodes):
        for node in nodes:
            assert {"pid", "ppid", "name", "cpu", "ram_mb", "status", "can_terminate", "children"} <= node.keys()
            visit(node["children"])
    visit(payload["items"])



def test_diagnostics_endpoint_returns_evidence_based_report():
    response = client.get("/api/diagnostics?window=1h")
    assert response.status_code == 200
    payload = response.json()
    assert payload["version"] == "2.0.0"
    assert payload["window"] == "1h"
    assert isinstance(payload["findings"], list)
    assert isinstance(payload["memory_growth"], list)
    assert "limitations" in payload


def test_diagnostics_rejects_unsupported_window():
    assert client.get("/api/diagnostics?window=forever").status_code == 400
    assert client.get("/api/diagnostics/report?window=forever").status_code == 400


def test_diagnostics_report_is_json_download():
    response = client.get("/api/diagnostics/report?window=15m")
    assert response.status_code == 200
    assert "application/json" in response.headers["content-type"]
    assert "attachment;" in response.headers["content-disposition"]
    payload = response.json()
    assert payload["report_type"] == "local-diagnostics"
    assert payload["analysis"]["window"] == "15m"
    assert "privacy_notice" in payload



def test_hardware_endpoint_reports_explicit_component_statuses():
    response = client.get("/api/hardware")
    assert response.status_code == 200
    payload = response.json()
    assert {"cpu", "gpu", "memory", "motherboard", "battery"} <= payload.keys()
    assert payload["cpu"]["voltage_v"]["status"] == "Unavailable"


def test_storage_endpoint_returns_bounded_drive_and_io_data():
    response = client.get("/api/storage")
    assert response.status_code == 200
    payload = response.json()
    assert {"sampled_at", "status", "drives", "devices", "totals", "top_processes", "capabilities"} <= payload.keys()
    assert isinstance(payload["drives"], list)
    assert isinstance(payload["devices"], list)
    assert len(payload["top_processes"]) <= 10
    assert {"read_bytes_per_sec", "write_bytes_per_sec", "read_iops", "write_iops"} <= payload["totals"].keys()


def test_storage_endpoint_rejects_untrusted_origin():
    response = client.get("/api/storage", headers={"Origin": "https://untrusted.example"})
    assert response.status_code == 403



def test_process_detail_and_history_are_bound_to_process_creation_time():
    import os
    import time
    process = __import__("psutil").Process(os.getpid())
    created = process.create_time()
    detail = client.get(f"/api/processes/{os.getpid()}?create_time={created}")
    assert detail.status_code == 200
    payload = detail.json()
    assert {"create_time", "threads", "uptime_seconds", "io", "handles", "executable", "history"} <= payload.keys()
    stale = client.get(f"/api/processes/{os.getpid()}?create_time={created - 100}")
    assert stale.status_code == 404


def test_process_history_rejects_unsupported_windows():
    import os
    import psutil
    created = psutil.Process(os.getpid()).create_time()
    assert client.get(f"/api/process-history?pid={os.getpid()}&create_time={created}&window=forever").status_code == 400


def test_settings_are_validated_and_persisted():
    response = client.get("/api/settings")
    assert response.status_code == 200
    assert response.json()["retention_days"] in {1, 7, 30}
    updated = client.put("/api/settings", json={"sampling_interval_seconds": 10, "retention_days": 7})
    assert updated.status_code == 200
    assert updated.json()["sampling_interval_seconds"] == 10
    invalid = client.put("/api/settings", json={"sampling_interval_seconds": 2})
    assert invalid.status_code == 400


def test_timeline_records_resource_events_and_user_markers():
    marker = client.post("/api/timeline/markers", json={"title": "Started game", "note": "Testing frame pacing"})
    assert marker.status_code == 200
    result = client.get("/api/timeline?window=24h&limit=20")
    assert result.status_code == 200
    assert any(item["title"] == "Started game" for item in result.json()["events"])
    assert client.get("/api/timeline?window=forever").status_code == 400


def test_process_termination_requires_process_identity():
    import os
    import psutil
    created = psutil.Process(os.getpid()).create_time()
    response = client.post("/api/process/kill", json={"pid": os.getpid(), "create_time": created + 50})
    assert response.status_code in {403, 409}
