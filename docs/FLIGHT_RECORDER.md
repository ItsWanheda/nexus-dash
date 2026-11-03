# System Flight Recorder

The Flight Recorder stores a rolling window of real resource telemetry on the machine that runs the NEXUS API. It is intended for troubleshooting recent spikes, not for indefinite monitoring or forensic collection of process command lines.

## What is recorded

The database contains a UTC timestamp, CPU utilisation, RAM utilisation/capacity, system-volume utilisation/capacity, network byte counters, and optional GPU-memory values. Unsupported GPU values remain null.

The aggregate system telemetry table deliberately excludes hostname, OS username, process names, executable paths and command lines. Separate feature tables now exist: process performance history stores process name, PID, creation time and numeric CPU/RAM/thread/disk I/O metrics; network-quality history stores explicitly configured target labels/ports and DNS/TCP measurements; process-network history stores process name/PID and measured byte rates when its provider is enabled. Incident captures bundle recent local evidence from these sources. None stores executable paths, command lines, usernames, socket IP addresses, MAC addresses or packet contents.

## Sampling and bounds

- The API background recorder samples while the API process is running, even when the browser UI is closed.
- Persistent writes are throttled to approximately one sample every five seconds.
- Old samples are deleted after 24 hours.
- Aggregate telemetry is capped at 20,000 samples. Network-interface, process, quality and incident tables have independent row bounds and retention handling.
- History queries are limited to five supported windows and 2,000 returned samples.
- Current values are not backfilled. History begins when this version of NEXUS is running.

## Storage location

Default location:

- Windows: %USERPROFILE%\.nexus-dash\telemetry.sqlite3
- Linux/macOS: ~/.nexus-dash/telemetry.sqlite3

Set NEXUS_DATA_DIR before starting python server.py to choose a different directory. NEXUS attempts to restrict directory and database file permissions on platforms that support POSIX mode bits.

To erase stored telemetry, use Settings → Clear History (which clears aggregate telemetry, interface samples, process history, network-quality history, per-process network samples, timeline events and incident captures). Alternatively stop the API first, then remove the database and companion files (telemetry.sqlite3, telemetry.sqlite3-wal and telemetry.sqlite3-shm). Do not delete the database while the API is running.

## API examples

    GET /api/history?window=1h&limit=600
    GET /api/history?window=24h&limit=2000
    GET /api/history/export?format=json&window=24h&limit=2000
    GET /api/history/export?format=csv&window=24h&limit=2000
    GET /api/process-tree?limit=500

Supported windows: 5m, 15m, 1h, 6h, and 24h. The same loopback-client and browser-origin checks used by the existing API apply to these routes.

## Exports

- **JSON session export from the UI:** up to 24 hours of history, browser-session event log, current browser-session alert history and settings, and the last process snapshot known to the page.
- **CSV export from the UI:** historical resource samples only, making it easier to import trends into a spreadsheet.
- **API export routes:** historical resource samples only.

Exports are user-initiated because process snapshots and browser logs can reveal information about local usage. Review the contents before sharing an export.

## Alert rules

CPU, RAM, and system-volume alert thresholds are configured in the browser UI and saved in local storage for that origin. An alert fires after the selected number of consecutive samples meet or exceed a threshold. A 60-second per-metric cooldown reduces repeated notifications. Alert history stays in the current browser session and is included in session JSON exports.

Desktop notifications are optional. NEXUS requests browser permission only after the user presses Enable desktop notifications. Denying notification permission does not disable the in-app alert list.

## Troubleshooting

- **No history yet:** leave the API running for at least one recording interval, then refresh the Flight Recorder. The recorder does not invent/backfill samples.
- **History endpoint returns 503:** check whether the data directory is writable and whether the database can be opened. The API logs the storage error; live /api/stats telemetry is designed to remain available if a write fails.
- **History chart is sparse:** the recorder is capped at about one sample per five seconds, and the chart displays a bounded subset of points.
- **Process tree is incomplete:** operating-system permissions, short-lived processes, and the configured process limit may hide entries. This is a snapshot, not a complete OS audit.
- **Notifications do not appear:** check browser permission settings for the local UI origin. Alerts continue to appear in the interface.


## Diagnostics in version 2.0.0

Bottleneck Detective analyses recorded samples and correlates resource-pressure timestamps with best-effort local crash/hang indicators. Process-memory growth tracking is separate from the SQLite recorder and remains in memory only. Read DIAGNOSTICS.md for thresholds, platform sources, limitations, and report privacy.


## Disk I/O history

The Flight Recorder also records aggregate disk read/write throughput, read/write IOPS, and the maximum reported activity/latency values when the operating system exposes those counters. The history remains bounded by the same 24-hour and 20,000-sample limits. Missing platform counters are stored as null and are not drawn as zero. Per-process I/O, process names, PIDs, drive mount paths, SMART output, and device identifiers are not written to SQLite.

The Storage view obtains a fresh live snapshot and replays historical aggregate rates from the Flight Recorder. Counter rates require at least two samples; the first reading is marked as warming up.


## Extended historical windows and analytics

The recorder and timeline accept 7-day and 30-day windows, subject to the configured retention policy and bounded SQLite sample cap. The Advanced Analytics view calculates average, minimum, maximum, p50, p95, threshold frequency, utilisation distributions, UTC-hour profiles, bucketed trends, incident frequency and equal-length previous-window comparisons. Missing intervals are not interpolated.

Per-interface network counters are stored in a separate bounded table. Each interface is sampled independently and latest history is returned chronologically so rates are calculated correctly. The analytics endpoint can inspect up to 20,000 retained samples per interface. IP/MAC addresses and socket destinations are never stored.


## Persistent process history, network quality and incident evidence

The process sampler stores up to 50 process records per sampling cycle when enabled. A record is keyed by PID plus process creation time and contains process name, CPU percentage, RSS memory, thread count, cumulative disk read/write counters and rates derived from successive counters. Exclusions apply. This table is separate from aggregate resource telemetry and is not the complete list of all processes.

Continuous network-quality checks are opt-in and use up to three user-configured host/port targets. Target labels/ports and DNS/TCP timing results are stored locally. The sampler runs no more than once per minute while background recording is active.

Per-process network history is opt-in and depends on a supported provider. On Linux, NetHogs is used when installed and accessible. On Windows/macOS, this release reports that a per-process byte-accounting provider is not supported; it does not treat socket ownership as network byte rate.

Incident evidence is saved separately in a bounded table. The local store keeps at most 250 captures, with each evidence payload capped at 2 MB. Manual capture and automatic trigger capture are available. Clear History deletes all of these tables along with aggregate resource history.
