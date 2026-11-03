# Hardware and Storage Telemetry

NEXUS collects local hardware readings on a best-effort basis. The backend reports the source and availability of optional measurements; an unsupported or inaccessible sensor is returned as `Unavailable`, never as a guessed value.

## Hardware endpoint

- `GET /api/hardware` returns CPU, per-core load/frequency, exposed CPU and motherboard temperature/fan sensors, memory/cache/swap data, memory-pressure information, NVIDIA GPU telemetry, and battery readings.
- CPU voltage, battery health, and charge cycles remain unavailable unless a supported provider exposes them.
- CPU per-core utilisation and frequency are based on psutil. Temperature and fan values use psutil sensor APIs; Windows can optionally query ACPI thermal zones through WMI.
- NVIDIA metrics require a compatible NVIDIA driver and the optional `nvidia-ml-py` package. Other GPU vendors are not queried by NVML.

## Storage endpoint

- `GET /api/storage` returns mounted-drive capacity, per-device read/write throughput, IOPS, activity and response latency where counters exist, top process I/O, and SMART health where supported.
- Rates are calculated from counter differences divided by elapsed monotonic time. The first sample is marked as warming up.
- Per-process I/O is a live snapshot only. Process names, PIDs, mount paths, device IDs, SMART output, and hardware identifiers are not stored in SQLite.
- SMART health uses `smartctl --json --health` with no shell, bounded device count, a short timeout, and a five-minute cache. Install smartmontools and run NEXUS with permissions that allow read-only device health queries. Some USB bridges, RAID controllers, virtual drives, and NVMe controllers may not expose all SMART fields.

## Optional providers

Install optional packages only for capabilities needed on the local machine:

    python -m pip install -r requirements-hardware.txt

This installs NVIDIA NVML bindings and the optional Windows WMI provider. SMART additionally requires the operating-system smartmontools package and a `smartctl` executable on PATH.

## Platform limitations

| Platform | Available baseline | Optional / unavailable examples |
| --- | --- | --- |
| Windows | psutil CPU, RAM, swap, battery, disk I/O, process I/O | WMI ACPI temperatures; NVML for NVIDIA; SMART depends on smartctl and device permissions. Per-device activity/latency may be unavailable. |
| Linux | psutil CPU, RAM, swap, battery, disk I/O, sensors where kernel drivers expose them; memory PSI when readable | NVML for NVIDIA; SMART depends on smartctl and device permissions. |
| macOS | psutil CPU, RAM, swap, battery, disk I/O, process I/O | Sensor exposure varies; NVML support is hardware/driver dependent; SMART depends on smartctl and device permissions. |

A missing counter or sensor is not evidence that the hardware is healthy. Activity and latency are not comparable across every driver or storage controller. Bottleneck Detective reports sustained patterns for investigation and does not assert that a disk caused an application slowdown.

## Privacy and local security

All new routes are protected by the existing loopback, trusted-host, and browser-origin checks. The API remains bound to `127.0.0.1`. Hardware and storage snapshots are not sent to a remote service. Persistent history includes aggregate numeric resource/disk-I/O metrics, per-interface numeric counters and link metadata, interface names, and timestamps. IP addresses, MAC addresses, DNS targets, remote endpoints, and packet contents are not persisted.


## Network Intelligence

- GET /api/network provides per-interface byte/packet counters, upload/download rates, link state, speed, MTU, duplex, errors and drop deltas. Initial rates warm up until two readings are available.
- GET /api/network/history?window=24h&interface=Ethernet returns bounded local interface history. The store retains counters and link metadata only; it does not store IP or MAC addresses. Rate calculations are chronological and reset-aware.
- GET /api/network/connections?limit=150&include_addresses=false returns a bounded live socket view with protocol, state, PID/process attribution and ports. IP addresses are hidden by default; explicitly reveal them only for the current view. OS permissions may limit the socket table.
- GET /api/network/diagnostics?host=example.com&port=443&attempts=3 performs a bounded DNS lookup and TCP handshake probe. It reports DNS time, connect latency, jitter and failed attempts. No HTTP request or application payload is sent, and the host is not saved in history.

No destination IP, DNS destination, MAC address, packet content, or per-process network traffic volume is persisted. Socket attribution is a live process-name association, not a historical per-process byte counter.
