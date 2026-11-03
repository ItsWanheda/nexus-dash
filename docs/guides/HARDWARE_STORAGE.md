# 🧩 Hardware and Storage Telemetry

NEXUS reports local hardware identity and sensor values on a best-effort basis. Device identification is separate from live telemetry: a GPU can be detected by PCI/WMI identity even when its driver does not expose utilisation, temperature or fan values.

## 📚 On this page

- [GPU identification and live metrics](#-gpu-identification-and-live-metrics)
- [System and motherboard identity](#-system-motherboard-and-bios-identity)
- [Temperature and fan monitoring](#-temperature-and-fan-monitoring)
- [Storage metrics and SMART](#-storage-metrics-and-smart)
- [Platform capabilities](#-platform-capability-summary)
- [Network metrics and privacy](#-network-intelligence-and-per-process-attribution)

## 🎮 GPU identification and live metrics

| Vendor | Inventory source | Optional live metrics |
| --- | --- | --- |
| NVIDIA | Windows WMI / Linux PCI identifiers | NVML: utilisation, memory, temperature, power, clocks and fan values where supported |
| AMD | Windows WMI / Linux PCI identifiers | AMD SMI on supported Linux AMDGPU/ROCm systems: engine, VRAM, power, clocks, temperature and fan RPM where exposed |
| Intel | Windows WMI / Linux PCI identifiers | Separate compatible provider required for live sensor support |

On Linux, NEXUS can look up legacy PCI device identifiers in a locally installed `pci.ids` database. If a device is recognised but no live metric provider is available, the UI labels it **Inventory only** instead of omitting it or inventing a value.

Install optional Python bindings:

```bash
python -m pip install -r requirements-hardware.txt
```

The host still needs a compatible vendor driver/runtime. Missing or unsupported readings remain unavailable.

## 🖥️ System, motherboard and BIOS identity

- **Linux:** SMBIOS/DMI values from `/sys/class/dmi/id`.
- **Windows:** `Win32_ComputerSystem`, `Win32_BaseBoard` and `Win32_BIOS` through WMI.
- **macOS:** available machine identity; conventional PC baseboard identification is generally unavailable.

The API exposes system manufacturer/model/family, board manufacturer/model/version and BIOS vendor/version/release date. It intentionally does not expose board serial numbers or system UUIDs.

Firmware may report generic strings or leave fields blank. NEXUS shows firmware-reported values and their source; it does not infer a retail motherboard model from a chipset.

## 🌡️ Temperature and fan monitoring

- psutil sensor APIs report temperatures/fan RPM where supported.
- Linux also reads kernel hwmon `temp*_input` and `fan*_input` values where drivers publish them.
- Windows can read ACPI thermal zones through WMI.
- For expanded Windows motherboard/GPU/fan sensors, run LibreHardwareMonitor with its WMI sensor provider enabled; NEXUS reads its `root\\LibreHardwareMonitor` namespace.
- AMD SMI and NVIDIA NVML may expose GPU fan/temperature values for supported devices.

> ⚠️ **Read-only:** NEXUS does not set fan curves, write hwmon control attributes, change BIOS settings or override vendor fan controllers. A missing RPM value is unavailable — not zero RPM.

## 💽 Storage metrics and SMART

`GET /api/storage` returns mounted-drive capacity, per-device read/write throughput, IOPS, activity and response latency where counters exist, top process I/O, and SMART health where supported.

- Rates are calculated from counter differences divided by elapsed monotonic time.
- The first sample is marked as warming up.
- Per-process storage I/O is a live snapshot; persistent process history stores per-process disk byte counters/rates separately when enabled.
- SMART health uses `smartctl --json --health` with no shell, a bounded device count, a short timeout and a five-minute cache.

Install the operating-system smartmontools package so `smartctl` is available. Run NEXUS with read-only device-query permissions. Some USB bridges, RAID controllers, virtual drives and NVMe controllers may not expose every field.

## 🧭 Platform capability summary

| Platform | Identification | Optional live sensor providers |
| --- | --- | --- |
| Windows | WMI system/baseboard/BIOS and AMD/NVIDIA/Intel display controller IDs | NVML for NVIDIA; LibreHardwareMonitor WMI for supported temperatures/fans; ACPI thermal zones; optional SMART |
| Linux | SMBIOS/DMI and PCI vendor/device IDs, including local pci.ids lookup | AMD SMI on supported AMDGPU/ROCm; NVML for NVIDIA; psutil/kernel hwmon temperatures and fan tachometers; optional SMART |
| macOS | Platform model; conventional baseboard identification is generally unavailable | psutil sensors where exposed; GPU/fan coverage depends on hardware/provider; optional SMART |

A missing sensor is not evidence that hardware is healthy. A generic firmware model string may be the exact value the firmware publishes.

## 🌐 Network intelligence and per-process attribution

- `GET /api/network` provides per-interface byte/packet counters, throughput, link state, speed, MTU, duplex, errors and drops.
- `GET /api/network/history` reads bounded interface history. IP and MAC addresses are excluded from this table.
- `GET /api/network/connections` reports live socket ownership, protocol, state and ports. This is connection attribution, not byte-rate attribution.
- `GET /api/network/processes` reports per-process byte rates only when NetHogs is installed on Linux and the opt-in sampler is enabled.

This release does not implement Windows ETW/WFP or macOS per-process byte accounting. Unsupported platforms return a capability status, not fabricated rates.

## 🔏 Privacy

All endpoints remain protected by local loopback, trusted-host and browser-origin checks.

Persistent data is separated by feature:
- aggregate system metrics and timestamps,
- interface names/counters/link metadata,
- process name/PID/creation time and CPU/RAM/thread/disk metrics,
- optional process-network name/PID/byte rates,
- optional configured network target label/port and DNS/TCP results,
- bounded incident captures containing recent evidence.

The database does not store usernames, process command lines, executable paths, socket IP addresses, MAC addresses or packet contents in these feature histories. Configured network target labels may contain hostnames or IP addresses, as entered by the user.

Use Settings to disable optional collection and **Clear History** to delete local history tables and incident captures.
