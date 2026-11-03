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

NEXUS discovers display adapters independently of their live sensor providers. It does **not** assume the system uses NVIDIA hardware, and it does not stop enumerating a vendor after finding the first card.

| Platform | Inventory source | Additional live telemetry |
| --- | --- | --- |
| Windows | DirectX DXGI adapter enumeration (model, PCI IDs, subsystem, revision, LUID and dedicated/shared memory) merged with WMI driver/display metadata; PCI device-registry fallback | Windows GPU Engine/AdapterMemory counters keyed by DXGI LUID; NVIDIA NVML where supported; LibreHardwareMonitor WMI readings for supported AMD, NVIDIA and Intel devices |
| Linux | All PCI display-class devices from `/sys/bus/pci/devices`; vendor/device names from local `pci.ids` when installed | Generic DRM/sysfs counters (driver-dependent); AMD SMI on supported AMDGPU/ROCm systems; AMD ADLX on supported Windows AMD drivers; NVIDIA NVML |
| macOS | Built-in `system_profiler SPDisplaysDataType -json` inventory | Values exposed by the operating system or a compatible installed provider |

Known PCI vendor identifiers are labelled as AMD, NVIDIA, Intel, Apple, or their respective platform/vendor names. Other valid PCI identifiers are resolved from the local `pci.ids` database when possible; otherwise NEXUS preserves a generic PCI vendor label and still shows the device entry.

GPU **identification** and **live measurements** are separate:
- An identified device remains visible as **Inventory only** when a driver/provider does not expose live readings.
- When available, Linux DRM/sysfs counters can expose GPU busy percentage, VRAM use/capacity, temperature, power, clock and fan readings.
- AMD SMI provides additional readings on supported Linux AMDGPU/ROCm systems. AMD ADLX (optional `amd-adlx` Python binding) provides AMD GPU name/device IDs and supported live metrics on compatible 64-bit Windows systems, including usage, core/VRAM clocks, temperature/hotspot, power, fan and VRAM usage. Both are optional and neither is required for basic AMD device identification.
- NVIDIA NVML provides additional NVIDIA measurements when its driver and Python binding are available.
- On Windows, DXGI supplies the adapter model, PCI vendor/device/subsystem IDs, revision, dedicated/shared memory capacities and adapter LUID. WMI adds driver version/date, video processor and active display mode.
- On supported Windows 10/11 graphics drivers, GPU Engine and GPU AdapterMemory performance counters can expose per-adapter utilisation and dedicated/shared memory use. NEXUS matches these counters by DXGI LUID, not vendor name.
- LibreHardwareMonitor can provide additional per-device load, temperature, power, clock, fan and memory readings across multiple GPU vendors. Matchable sensor names are attached to the corresponding adapter rather than being reported as a separate GPU.
- Multiple adapters from the same vendor are retained. Live readings are merged by PCI address/device identity or an unambiguous model match, never by vendor name alone.

Install optional Python bindings (the Windows AMD ADLX binding is included in the Windows hardware extras and packaged desktop build):

```bash
python -m pip install -r requirements-hardware.txt
```

> ℹ️ Installing an optional Python package does not install a GPU driver, enable an unsupported sensor, or guarantee live values. Device names and capabilities depend on what the operating system and drivers expose. If the GPU is detected but a specific field is unavailable, NEXUS reports that field as unavailable instead of guessing.

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
- For expanded Windows motherboard/GPU/fan sensors, run LibreHardwareMonitor with its WMI sensor provider enabled; NEXUS reads its `root\\LibreHardwareMonitor` namespace and associates supported GPU sensors with detected display adapters.
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
| Windows | DXGI + WMI + PCI device-registry fallback for display adapters; WMI for system/baseboard/BIOS | GPU Engine/AdapterMemory counters keyed by DXGI LUID; NVML for NVIDIA; LibreHardwareMonitor WMI for supported GPU/board sensors; ACPI thermal zones; optional SMART |
| Linux | SMBIOS/DMI and all PCI display-class devices, including local pci.ids vendor/device lookup | DRM/sysfs counters where exposed; AMD SMI on supported AMDGPU/ROCm; NVML for NVIDIA; kernel hwmon temperatures/fans; optional SMART |
| macOS | Built-in system_profiler display-adapter inventory; conventional baseboard identification is generally unavailable | GPU/fan metrics depend on OS/provider exposure; psutil sensors; optional SMART |

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
