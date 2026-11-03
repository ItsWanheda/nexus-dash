from nexus_dash.services.hardware import _reading, collect_hardware


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


from nexus_dash.services.hardware_providers import collect_gpu_inventory, collect_system_inventory, collect_linux_hwmon, collect_lhm_sensors


def test_system_inventory_has_sanitised_fields():
    data = collect_system_inventory()
    assert {"system", "motherboard", "bios", "source", "limitations"} <= data.keys()
    assert "serial" not in str(data).casefold()
    assert "uuid" not in str(data).casefold()


def test_gpu_inventory_is_bounded_and_vendor_labelled():
    cards = collect_gpu_inventory()
    assert len(cards) <= 32
    assert all(isinstance(card.get("vendor"), str) and card.get("vendor") for card in cards)


def test_optional_sensor_providers_fail_closed():
    assert isinstance(collect_linux_hwmon(), dict)
    assert isinstance(collect_lhm_sensors(), list)



def test_linux_gpu_inventory_discovers_amd_and_other_pci_vendors(tmp_path, monkeypatch):
    from nexus_dash.services import hardware_providers

    monkeypatch.setattr(hardware_providers.platform, "system", lambda: "Linux")
    monkeypatch.setattr(hardware_providers, "_pci_vendor_name", lambda code: "PCI vendor " + code.upper().replace("0X", ""))
    fixtures = [
        ("0000:03:00.0", "0x1002", "0x747e", "AMD"),
        ("0000:04:00.0", "0x10de", "0x2684", "NVIDIA"),
        ("0000:05:00.0", "0x1abc", "0x1234", "PCI vendor 1ABC"),
    ]
    for address, vendor_id, device_id, _ in fixtures:
        device = tmp_path / address
        device.mkdir()
        (device / "vendor").write_text(vendor_id, encoding="ascii")
        (device / "device").write_text(device_id, encoding="ascii")
        (device / "class").write_text("0x030000", encoding="ascii")

    cards = hardware_providers._linux_gpu_inventory(tmp_path)
    by_address = {card["pci_address"]: card for card in cards}

    assert len(cards) == 3
    assert by_address["0000:03:00.0"]["vendor"] == "AMD"
    assert by_address["0000:04:00.0"]["vendor"] == "NVIDIA"
    assert by_address["0000:05:00.0"]["vendor"] == "PCI vendor 1ABC"


def test_windows_wmi_gpu_inventory_uses_pci_vendor_id_for_amd(monkeypatch):
    import sys
    from types import SimpleNamespace
    from nexus_dash.services import hardware_providers

    row = SimpleNamespace(
        Name="AMD Radeon(TM) RX 7800 XT",
        AdapterCompatibility="Advanced Micro Devices, Inc.",
        PNPDeviceID=r"PCI\VEN_1002&DEV_747E&SUBSYS_00000000",
        DriverVersion="31.0.24027.1012",
    )
    cim = SimpleNamespace(Win32_VideoController=lambda: [row])
    fake_wmi = SimpleNamespace(WMI=lambda **kwargs: cim)
    monkeypatch.setattr(hardware_providers.platform, "system", lambda: "Windows")
    monkeypatch.setitem(sys.modules, "wmi", fake_wmi)

    cards = hardware_providers._windows_wmi_gpu_inventory()

    assert len(cards) == 1
    assert cards[0]["vendor"] == "AMD"
    assert "Radeon" in cards[0]["name"]


def test_gpu_inventory_is_independent_of_nvidia_provider(monkeypatch):
    import sys
    from nexus_dash.services import hardware

    monkeypatch.setattr(hardware.platform, "system", lambda: "Linux")
    monkeypatch.setattr(hardware, "collect_gpu_inventory", lambda: [{
        "name": "AMD Radeon RX 7800 XT",
        "vendor": "AMD",
        "vendor_id": "0x1002",
        "device_id": "0x747e",
        "pci_address": "0000:03:00.0",
        "inventory_source": "test",
    }])
    monkeypatch.setattr(hardware, "collect_linux_gpu_metrics", lambda inventory: {})
    monkeypatch.setattr(hardware, "collect_amd_smi_devices", lambda: [])
    monkeypatch.setattr(hardware, "collect_lhm_sensors", lambda: [])
    monkeypatch.setitem(sys.modules, "pynvml", None)

    devices = hardware._gpu_devices()

    assert len(devices) == 1
    assert devices[0]["vendor"] == "AMD"
    assert devices[0]["name"] == "AMD Radeon RX 7800 XT"
    assert devices[0]["status"] == "Inventory only"


def test_gpu_provider_merge_matches_device_not_only_vendor():
    from nexus_dash.services import hardware

    inventory = [
        {"name": "AMD Radeon RX 7800 XT", "vendor": "AMD", "pci_address": "0000:03:00.0"},
        {"name": "AMD Radeon RX 6600", "vendor": "AMD", "pci_address": "0000:04:00.0"},
        {"name": "NVIDIA GeForce RTX 4070", "vendor": "NVIDIA", "pci_address": "0000:05:00.0"},
    ]
    devices = [hardware._gpu_inventory_row(item, index) for index, item in enumerate(inventory)]
    live = {
        "name": "AMD Radeon RX 7800 XT",
        "vendor": "AMD",
        "pci_address": "0000:03:00.0",
        "status": "Available",
        "utilization_percent": hardware._reading(42, "%", "test provider"),
    }

    hardware._merge_gpu_provider_devices(devices, [live])

    assert len(devices) == 3
    assert devices[0]["status"] == "Available"
    assert devices[0]["utilization_percent"]["value"] == 42
    assert devices[1]["status"] == "Inventory only"
    assert devices[1]["name"] == "AMD Radeon RX 6600"
    assert devices[2]["vendor"] == "NVIDIA"


def test_lhm_gpu_readings_attach_to_matching_amd_device():
    from nexus_dash.services import hardware

    device = hardware._gpu_inventory_row({
        "name": "AMD Radeon RX 7800 XT",
        "vendor": "AMD",
    }, 0)
    sensors = [
        {"hardware_type": "GpuAmd", "hardware": "AMD Radeon RX 7800 XT",
         "type": "Load", "name": "GPU Core", "value": 57.0, "unit": "%"},
        {"hardware_type": "GpuAmd", "hardware": "AMD Radeon RX 7800 XT",
         "type": "Temperature", "name": "GPU Temperature", "value": 63.0, "unit": "°C"},
        {"hardware_type": "GpuAmd", "hardware": "AMD Radeon RX 7800 XT",
         "type": "Data", "name": "GPU Memory Used", "value": 2048.0, "unit": "MB"},
    ]

    hardware._apply_lhm_gpu_sensors([device], sensors)

    assert device["status"] == "Available"
    assert device["utilization_percent"]["value"] == 57
    assert device["temperature_c"]["value"] == 63
    assert device["memory_used_gb"]["value"] == 2


def test_gpu_memory_summary_aggregates_all_detected_vendors(monkeypatch):
    from nexus_dash.services import hardware

    devices = [
        {"vendor": "AMD",
         "memory_used_gb": {"value": 2.0},
         "memory_total_gb": {"value": 8.0}},
        {"vendor": "Intel",
         "memory_used_gb": {"value": 1.0},
         "memory_total_gb": {"value": 4.0}},
    ]
    monkeypatch.setattr(hardware, "collect_gpu_devices", lambda: devices)

    summary = hardware.collect_gpu_memory_summary()

    assert summary["status"] == "Available"
    assert summary["used_gb"] == 3.0
    assert summary["total_gb"] == 12.0
    assert summary["device_count"] == 2
    assert summary["vendors"] == ["AMD", "Intel"]



def test_linux_gpu_metrics_reads_generic_drm_and_hwmon_counters(tmp_path, monkeypatch):
    from nexus_dash.services import hardware_providers

    monkeypatch.setattr(hardware_providers.platform, "system", lambda: "Linux")
    address = "0000:03:00.0"
    device = tmp_path / address
    hwmon = device / "hwmon" / "hwmon0"
    hwmon.mkdir(parents=True)
    values = {
        "gpu_busy_percent": "37",
        "mem_info_vram_used": str(2 * 1024**3),
        "mem_info_vram_total": str(8 * 1024**3),
    }
    for name, value in values.items():
        (device / name).write_text(value, encoding="ascii")
    for name, value in {
        "temp1_input": "64000",
        "power1_average": "125000000",
        "freq1_input": "2250000000",
        "fan1_input": "1200",
    }.items():
        (hwmon / name).write_text(value, encoding="ascii")

    metrics = hardware_providers.collect_linux_gpu_metrics(
        [{"pci_address": address}],
        sysfs_root=tmp_path,
    )[address]

    assert metrics["utilization_percent"]["value"] == 37
    assert metrics["memory_used_gb"]["value"] == 2
    assert metrics["memory_total_gb"]["value"] == 8
    assert metrics["temperature_c"]["value"] == 64
    assert metrics["power_w"]["value"] == 125
    assert metrics["graphics_clock_mhz"]["value"] == 2250
    assert metrics["fan_rpm"]["value"] == 1200


def test_pci_address_matching_normalises_nvml_domain_padding():
    from nexus_dash.services.hardware import _pci_address_key

    assert _pci_address_key("00000000:65:00.0") == "0000:65:00.0"
    assert _pci_address_key("0000:65:00.0") == "0000:65:00.0"


def test_windows_gpu_luid_normalization():
    from nexus_dash.services.windows_gpu import windows_gpu_luid_key

    assert windows_gpu_luid_key("luid_0x00000000_0x0000abcd_phys_0_eng_0") == "00000000:0000abcd"
    assert windows_gpu_luid_key("00000000:0000ABCD") == "00000000:0000abcd"
    assert windows_gpu_luid_key("not-a-luid") is None


def test_windows_dxgi_inventory_is_safe_off_windows(monkeypatch):
    from nexus_dash.services import windows_gpu

    monkeypatch.setattr(windows_gpu.platform, "system", lambda: "Linux")
    assert windows_gpu.collect_windows_dxgi_inventory() == []


def test_windows_dxgi_and_wmi_inventory_merge_exact_adapter_identity():
    from nexus_dash.services.hardware_providers import _merge_windows_gpu_inventory

    dxgi = [{
        "name": "AMD Radeon Graphics",
        "vendor_id": "1002", "device_id": "747e",
        "subsystem_vendor_id": "1462", "subsystem_device_id": "0b36",
        "adapter_luid": "00000000:0000abcd",
        "dedicated_video_memory_gb": 16.0,
    }]
    wmi = [{
        "name": "AMD Radeon RX 7800 XT",
        "vendor_id": "1002", "device_id": "747e",
        "subsystem_vendor_id": "1462", "subsystem_device_id": "0b36",
        "driver_version": "32.0.1", "video_processor": "AMD Radeon RX 7800 XT",
    }]

    result = _merge_windows_gpu_inventory(dxgi, wmi)

    assert len(result) == 1
    assert result[0]["name"] == "AMD Radeon RX 7800 XT"
    assert result[0]["adapter_luid"] == "00000000:0000abcd"
    assert result[0]["dedicated_video_memory_gb"] == 16.0
    assert result[0]["driver_version"] == "32.0.1"


def test_windows_gpu_performance_counters_group_by_luid(monkeypatch):
    import sys
    from types import SimpleNamespace
    from nexus_dash.services import hardware_providers

    engine_rows = [
        SimpleNamespace(Name="pid_10_luid_0x00000000_0x0000abcd_phys_0_eng_0", UtilizationPercentage=31),
        SimpleNamespace(Name="pid_11_luid_0x00000000_0x0000abcd_phys_0_eng_1", UtilizationPercentage=72),
    ]
    memory_rows = [
        SimpleNamespace(Name="luid_0x00000000_0x0000abcd_phys_0", DedicatedUsage=2 * 1024**3, SharedUsage=256 * 1024**2),
    ]
    cim = SimpleNamespace(
        Win32_PerfFormattedData_GPUPerformanceCounters_GPUEngine=lambda: engine_rows,
        Win32_PerfFormattedData_GPUPerformanceCounters_GPUAdapterMemory=lambda: memory_rows,
    )
    monkeypatch.setattr(hardware_providers.platform, "system", lambda: "Windows")
    monkeypatch.setitem(sys.modules, "wmi", SimpleNamespace(WMI=lambda **kwargs: cim))

    metrics = hardware_providers.collect_windows_gpu_performance_metrics()
    assert metrics["00000000:0000abcd"]["utilization_percent"] == 72
    assert metrics["00000000:0000abcd"]["memory_used_gb"] == 2
    assert metrics["00000000:0000abcd"]["shared_memory_used_gb"] == 0.25


def test_windows_gpu_inventory_row_keeps_dxgi_identity_and_memory():
    from nexus_dash.services.hardware import _gpu_inventory_row

    row = _gpu_inventory_row({
        "name": "AMD Radeon RX 7800 XT", "vendor": "AMD",
        "vendor_id": "1002", "device_id": "747e",
        "subsystem_vendor_id": "1462", "subsystem_device_id": "0b36",
        "adapter_luid": "00000000:0000abcd",
        "dedicated_video_memory_gb": 16.0, "shared_system_memory_gb": 8.0,
        "driver_version": "32.0.1",
    }, 0)

    assert row["vendor_id"] == "1002"
    assert row["device_id"] == "747e"
    assert row["subsystem_vendor_id"] == "1462"
    assert row["adapter_luid"] == "00000000:0000abcd"
    assert row["dedicated_video_memory_gb"] == 16.0
    assert row["shared_system_memory_gb"] == 8.0
    assert row["shared_memory_used_gb"]["status"] == "Unavailable"


def test_amd_adlx_provider_reads_identity_and_supported_metrics(monkeypatch):
    import sys
    from types import SimpleNamespace
    from nexus_dash.services import hardware_providers

    class FakeGpu:
        def Name(self): return "AMD Radeon RX 7800 XT"
        def VendorId(self): return 0x1002
        def DeviceId(self): return 0x747e

    class FakeMetrics:
        def GPUUsage(self): return 64
        def GPUTemperature(self): return 61
        def GPUHotspotTemperature(self): return 78
        def GPUPower(self): return 210
        def GPUClockSpeed(self): return 2450
        def GPUVRAMClockSpeed(self): return 2400
        def GPUFanSpeed(self): return 42
        def GPUVRAM(self): return 4096
        def GPUSharedMemory(self): return 128

    class FakeHelper:
        terminated = False
        def Initialize(self): return 0
        def GetSystemServices(self):
            return SimpleNamespace(
                GetPerformanceMonitoringServices=lambda: SimpleNamespace(
                    GetCurrentGPUMetrics=lambda gpu: FakeMetrics()
                ),
                GetGPUs=lambda: [FakeGpu()],
            )
        def Terminate(self): self.terminated = True

    helper = FakeHelper()
    fake_adlx = SimpleNamespace(
        ADLX=SimpleNamespace(
            ADLXHelper=lambda: helper,
            ADLX_RESULT=SimpleNamespace(ADLX_OK=0),
        )
    )
    monkeypatch.setattr(hardware_providers.platform, "system", lambda: "Windows")
    monkeypatch.setitem(sys.modules, "adlx", fake_adlx)

    devices = hardware_providers.collect_amd_adlx_devices()

    assert len(devices) == 1
    assert devices[0]["vendor"] == "AMD"
    assert devices[0]["vendor_id"] == "1002"
    assert devices[0]["device_id"] == "747e"
    assert devices[0]["utilization_percent"] == 64
    assert devices[0]["temperature_c"] == 61
    assert devices[0]["hotspot_temperature_c"] == 78
    assert devices[0]["memory_used_gb"] == 4
    assert devices[0]["shared_memory_used_gb"] == 0.125
    assert helper.terminated is True
