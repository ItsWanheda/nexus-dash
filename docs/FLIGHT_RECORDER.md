# System Flight Recorder

The Flight Recorder stores a rolling window of real resource telemetry on the machine that runs the NEXUS API. It is intended for troubleshooting recent spikes, not for indefinite monitoring or forensic collection of process command lines.

## What is recorded

The database contains a UTC timestamp, CPU utilisation, RAM utilisation/capacity, system-volume utilisation/capacity, network byte counters, and optional GPU-memory values. Unsupported GPU values remain null.

The recorder deliberately does not store hostname, OS username, process names, executable paths, command lines, open files, network destinations, or file contents. The process tree is fetched as a live bounded snapshot and is not added to the historical database.

## Sampling and bounds

- The API background recorder samples while the API process is running, even when the browser UI is closed.
- Persistent writes are throttled to approximately one sample every five seconds.
- Old samples are deleted after 24 hours.
- The database is capped at 20,000 samples; the oldest samples are deleted first when the cap is reached.
- History queries are limited to five supported windows and 2,000 returned samples.
- Current values are not backfilled. History begins when this version of NEXUS is running.

## Storage location

Default location:

- Windows: %USERPROFILE%\.nexus-dash\telemetry.sqlite3
- Linux/macOS: ~/.nexus-dash/telemetry.sqlite3

Set NEXUS_DATA_DIR before starting python server.py to choose a different directory. NEXUS attempts to restrict directory and database file permissions on platforms that support POSIX mode bits.

To erase stored telemetry, stop the API first, then remove the database and its companion files (telemetry.sqlite3, telemetry.sqlite3-wal, and telemetry.sqlite3-shm) from that directory. Do not delete the database while the API is running.

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
