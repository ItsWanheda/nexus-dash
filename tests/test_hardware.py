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


from hardware_providers import collect_gpu_inventory, collect_system_inventory, collect_linux_hwmon, collect_lhm_sensors


def test_system_inventory_has_sanitised_fields():
    data = collect_system_inventory()
    assert {"system", "motherboard", "bios", "source", "limitations"} <= data.keys()
    assert "serial" not in str(data).casefold()
    assert "uuid" not in str(data).casefold()


def test_gpu_inventory_is_bounded_and_vendor_labelled():
    cards = collect_gpu_inventory()
    assert len(cards) <= 16
    assert all(card.get("vendor") in {"AMD", "NVIDIA", "Intel", "Unknown"} for card in cards)


def test_optional_sensor_providers_fail_closed():
    assert isinstance(collect_linux_hwmon(), dict)
    assert isinstance(collect_lhm_sensors(), list)
