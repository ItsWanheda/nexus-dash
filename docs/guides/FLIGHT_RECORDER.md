# 🕒 System Flight Recorder

The Flight Recorder stores a rolling window of real resource telemetry on the machine running the NEXUS API. It is designed to investigate recent behaviour — not to provide indefinite monitoring or collect process command lines.

## 📚 On this page

- [What is recorded](#-what-is-recorded)
- [Sampling and bounds](#-sampling-and-bounds)
- [Storage location and deletion](#-storage-location-and-deletion)
- [API examples](#-api-examples)
- [Exports and alerts](#-exports-and-alerts)
- [Extended analytics](#-extended-history-and-analytics)
- [Troubleshooting](#-troubleshooting)

## 📋 What is recorded

The aggregate resource table contains a UTC timestamp, CPU utilisation, RAM utilisation/capacity, system-volume utilisation/capacity, network byte counters and optional GPU-memory values. Unsupported GPU values remain null.

Separate feature tables are used for:
- **Process performance:** process name, PID, creation time and numeric CPU/RAM/thread/disk I/O metrics.
- **Network quality:** explicitly configured target labels/ports and DNS/TCP measurements.
- **Per-process network:** process name/PID and measured byte rates when its provider is enabled.
- **Incidents and timeline:** bounded evidence and local investigation events.

The aggregate system telemetry table deliberately excludes hostname, OS username, process names, executable paths and command lines. The additional feature tables have their own documented fields; process names/PIDs and configured target labels are retained locally when those features are enabled.

## ⏱️ Sampling and bounds

- The API background recorder samples while the API process is running, even when the browser UI is closed.
- Aggregate persistent writes are throttled to approximately one sample every five seconds.
- Retention is configurable: 1, 7 or 30 days.
- Aggregate telemetry is capped at 20,000 samples. Network-interface, process, quality and incident tables have independent row bounds and retention handling.
- History queries support bounded windows and at most 2,000 returned samples.
- Current values are not backfilled. History begins when this version of NEXUS is running.

Longer retention may increase the effective sampling interval so the selected period fits within the sample cap.

## 📁 Storage location and deletion

Default location:

| Platform | Database |
| --- | --- |
| Windows | `%USERPROFILE%\.nexus-dash\telemetry.sqlite3` |
| Linux/macOS | `~/.nexus-dash/telemetry.sqlite3` |

Set `NEXUS_DATA_DIR` before starting `python server.py` to choose a different directory. NEXUS attempts to restrict directory and database file permissions on platforms that support POSIX mode bits.

Use **Settings → Clear History** to clear aggregate telemetry, interface samples, process history, network-quality history, per-process network samples, timeline events and incident captures.

Alternatively, stop the API first, then remove:
- `telemetry.sqlite3`
- `telemetry.sqlite3-wal`
- `telemetry.sqlite3-shm`

> ⚠️ Do not delete or replace the database while the API is running. Browser-local alert preferences are stored separately from SQLite.

## 🔌 API examples

```http
GET /api/history?window=1h&limit=600
GET /api/history?window=24h&limit=2000
GET /api/history/export?format=json&window=24h&limit=2000
GET /api/history/export?format=csv&window=24h&limit=2000
GET /api/process-tree?limit=500
```

Supported aggregate history windows: `5m`, `15m`, `1h`, `6h` and `24h`. The same loopback-client and browser-origin checks used by the API apply to these routes.

## 📤 Exports and alerts

- **JSON session export from the UI:** up to 24 hours of history, browser-session event log, current browser-session alert history and settings, and the last process snapshot known to the page.
- **CSV export from the UI:** historical resource samples only, for spreadsheet analysis.
- **API export routes:** historical resource samples only.

Exports are user-initiated because process snapshots and browser logs can reveal information about local usage. Review the contents before sharing.

### Alert rules

CPU, RAM and system-volume alert thresholds are configured in the browser UI and saved in local storage for that origin. An alert fires after the selected number of consecutive samples meet or exceed a threshold. A 60-second per-metric cooldown reduces repeated notifications.

Alert history stays in the current browser session and is included in session JSON exports. Desktop notifications are optional; NEXUS requests browser permission only after the user presses **Enable desktop notifications**. Denying permission does not disable the in-app alert list.

## 💽 Disk I/O history

The Flight Recorder also records aggregate disk read/write throughput, read/write IOPS and maximum reported activity/latency values when the operating system exposes those counters. Missing platform counters are stored as null, not zero.

Per-process I/O, process names, PIDs, drive mount paths, SMART output and device identifiers are not written to the aggregate resource table. The Storage view obtains a fresh live snapshot and replays historical aggregate rates. Counter rates require at least two samples; the first reading is marked as warming up.

## 📈 Extended history and analytics

The recorder and timeline accept 7-day and 30-day windows, subject to configured retention and the bounded SQLite sample cap.

Advanced Analytics calculates average, minimum, maximum, p50, p95, threshold frequency, utilisation distributions, UTC-hour profiles, bucketed trends, incident frequency and equal-length previous-window comparisons. Missing intervals are not interpolated.

Per-interface network counters are stored in a separate bounded table. Each interface is sampled independently; history is returned chronologically so rates are calculated correctly. Analytics can inspect up to 20,000 retained samples per interface. IP/MAC addresses and socket destinations are not stored.

## 🧩 Persistent process and network history

The process sampler stores up to 50 process records per sampling cycle when enabled. A record is keyed by PID plus process creation time and contains process name, CPU percentage, RSS memory, thread count, cumulative disk read/write counters and rates derived from successive counters. Exclusions apply. This table is separate from aggregate resource telemetry and is not a complete process audit.

Continuous network-quality checks are opt-in and use up to three user-configured host/port targets. Target labels/ports and DNS/TCP timing results are stored locally. The sampler runs no more than once per minute while background recording is active.

Per-process network history is opt-in and depends on a supported provider. On Linux, NetHogs is used when installed and accessible. On Windows/macOS, this release reports that per-process byte-accounting is unsupported; it does not treat socket ownership as a byte rate.

Incident evidence is saved separately in a bounded table. The store retains at most 250 captures, with each payload capped at 2 MB. Manual and automatic capture are available. Clear History deletes these tables along with aggregate resource history.

## 🧰 Troubleshooting

| Symptom | Suggested check |
| --- | --- |
| No history yet | Leave the API running for at least one recording interval; samples are not backfilled |
| History endpoint returns 503 | Check whether the data directory is writable and the database can be opened; inspect API logs |
| History chart is sparse | Sampling is throttled and the chart displays a bounded subset of points |
| Process tree is incomplete | Permissions, short-lived processes and configured limits affect visibility |
| Notifications do not appear | Check browser permission settings for the local UI origin; in-app alerts should still appear |

For diagnostic thresholds, event sources and incident evidence, see [Diagnostics and forensics](DIAGNOSTICS.md).
