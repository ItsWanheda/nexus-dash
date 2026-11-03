# Hardware and Storage Telemetry

NEXUS reports local hardware identity and sensor values on a best-effort basis. Device identification is separate from live telemetry: a GPU can be detected by PCI/WMI identity even when its driver does not expose utilisation, temperature or fan values.

## GPU identification and live metrics

- NVIDIA: live utilisation, memory, temperature, power, clock and fan-percent values use NVML when the compatible driver and optional nvidia-ml-py package are installed.
- AMD: Windows WMI video-controller inventory and Linux PCI inventory identify AMD adapters. On supported Linux AMDGPU/ROCm hosts, optional AMD SMI bindings can expose engine utilisation, VRAM, power, clocks, temperature and fan RPM. AMD SMI is not a universal Windows provider and not all AMD generations/drivers expose every metric.
- Intel: Windows WMI or Linux PCI inventory identifies Intel graphics devices. Live sensor support depends on a separate compatible provider.
- On Linux, NEXUS can look up legacy PCI device identifiers in a locally installed pci.ids database. If a device is recognised but no live metric provider is available, the UI labels it Inventory only instead of omitting it or inventing a value.

Install optional bindings with:

    python -m pip install -r requirements-hardware.txt

The host still needs a compatible vendor driver/runtime. Missing or unsupported readings remain unavailable.

## System, motherboard and BIOS identity

- Linux reads SMBIOS/DMI values from /sys/class/dmi/id.
- Windows reads Win32_ComputerSystem, Win32_BaseBoard and Win32_BIOS through WMI.
- macOS reports the available machine identity but generally does not expose a conventional PC baseboard model.

The API exposes system manufacturer/model/family, board manufacturer/model/version and BIOS vendor/version/release date. It intentionally does not expose board serial numbers or system UUIDs. Firmware may report generic strings such as an OEM-specific baseboard name or leave a field blank. NEXUS shows firmware-reported values and source; it does not infer a retail motherboard model from a chipset.

## Temperature and fan monitoring

- psutil sensor APIs report temperatures/fan RPM where supported.
- Linux also reads kernel hwmon temp*_input and fan*_input values where drivers publish them.
- Windows can read ACPI thermal zones through WMI. For expanded motherboard/GPU/fan sensors, run LibreHardwareMonitor with its WMI sensor provider enabled; NEXUS reads its root\LibreHardwareMonitor namespace.
- AMD SMI and NVIDIA NVML may expose GPU fan/temperature values for supported devices.

Fan monitoring is read-only. NEXUS does not set fan curves, write hwmon control attributes, change BIOS settings or override vendor fan controllers. A missing RPM value is unavailable—not zero RPM.

## Storage endpoint

- GET /api/storage returns mounted-drive capacity, per-device read/write throughput, IOPS, activity and response latency where counters exist, top process I/O, and SMART health where supported.
- Rates are calculated from counter differences divided by elapsed monotonic time. The first sample is marked as warming up.
- Per-process storage I/O remains a live snapshot; persistent process history stores per-process disk byte counters/rates separately when process history is enabled.
- SMART health uses smartctl --json --health with no shell, bounded device count, short timeout and a five-minute cache. Install smartmontools and run NEXUS with read-only device-query permissions. Some USB bridges, RAID controllers, virtual drives and NVMe controllers may not expose all fields.

## Platform capability summary

| Platform | Identification | Optional live sensor providers |
| --- | --- | --- |
| Windows | WMI system/baseboard/BIOS and AMD/NVIDIA/Intel display controller IDs | NVML for NVIDIA; LibreHardwareMonitor WMI for supported temperatures/fans; ACPI thermal zones; optional SMART |
| Linux | SMBIOS/DMI and PCI vendor/device IDs (including local pci.ids name lookup) | AMD SMI on supported AMDGPU/ROCm; NVML for NVIDIA; psutil/kernel hwmon temperatures and fan tachometers; optional SMART |
| macOS | Platform model; conventional baseboard identification is generally unavailable | psutil sensors where exposed; GPU and fan sensor coverage depends on hardware/provider; optional SMART |

A missing sensor is not evidence that hardware is healthy. A generic firmware model string is not proof that the board is unidentified; it may be the exact value the firmware publishes.

## Network Intelligence and per-process attribution

- GET /api/network provides per-interface byte/packet counters, throughput, link state, speed, MTU, duplex, errors and drops.
- GET /api/network/history reads bounded interface history. IP and MAC addresses are excluded from this table.
- GET /api/network/connections reports live socket ownership, protocol, state and ports. This is connection attribution, not byte-rate attribution.
- GET /api/network/processes reports per-process byte rates only when NetHogs is installed on Linux and the opt-in sampler is enabled. This build does not implement Windows ETW/WFP or macOS per-process byte accounting. Unsupported platforms return a capability status, not fabricated rates.

## Privacy

All endpoints remain protected by the local loopback, trusted-host and browser-origin checks. Persistent system telemetry contains aggregate metrics; per-interface samples contain interface name/counters/link metadata; process history contains process name/PID/creation time and CPU/RAM/thread/disk metrics; optional process-network history contains process name/PID/byte rates; optional network-quality history stores the explicitly configured target label/port and DNS/TCP results. Incident captures bundle recent evidence from these sources.

The database does not store usernames, process command lines, executable paths, socket IP addresses, MAC addresses or packet contents. Configured network target labels may be hostnames or IPs, as entered by the user. Use the Settings toggles to disable optional collection, and use Clear History to delete all local history tables and incident captures.
