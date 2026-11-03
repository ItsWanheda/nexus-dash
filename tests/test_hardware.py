from hardware import _reading, collect_hardware


def test_missing_hardware_measurement_is_explicitly_unavailable():
    result = _reading(None, "°C", "test-provider", "sensor not exposed")
    assert result["value"] is None
    assert result["status"] == "Unavailable"
    assert result["reason"] == "sensor not exposed"


def test_hardware_snapshot_has_stable_component_groups():
    result = collect_hardware()
    assert {"sampled_at", "platform", "cpu", "gpu", "memory", "motherboard", "battery", "capabilities"} <= result.keys()
    assert {"cores", "temperatures", "voltage_v", "frequency_mhz"} <= result["cpu"].keys()
    assert {"temperatures", "fans"} <= result["motherboard"].keys()
    assert result["cpu"]["voltage_v"]["status"] == "Unavailable"
    assert isinstance(result["gpu"]["devices"], list)
    assert result["battery"]["charge_cycles"]["status"] == "Unavailable"
