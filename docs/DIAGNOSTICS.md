# Bottleneck Detective, Persistent Diagnostics and Forensics

Bottleneck Detective combines system telemetry, persistent process history, adaptive signals and best-effort OS crash/hang indicators. It provides investigation leads; it does not repair the machine or claim that temporal correlation proves root cause.

## Resource-pressure analysis

The fixed/evidence-based analyzer evaluates recorded CPU utilisation, system RAM pressure, system-volume capacity and supported disk activity/latency. A sustained finding requires at least three above-threshold samples and at least 25% of valid samples for that metric. Disk activity and latency are separate measurements; their availability and meaning depend on the underlying OS counter/provider.

## Persistent process performance history

When process history is enabled, the background recorder observes a bounded set of up to 50 processes, favouring the largest resident-memory footprints. It stores:
- PID and process creation time (the identity key, to prevent PID-reuse mixing).
- Process name, sampled CPU percentage, RSS memory and thread count.
- Cumulative disk read/write byte counters and derived per-second rates when the OS exposes them.

The history is stored in the local SQLite database and remains available after a process exits, after the inspector closes, and after the API restarts. Sampling follows the selected interval and retention-aware effective cadence. Process exclusions apply. Process command lines, executable paths and usernames are not stored in this table. Names/PIDs are identifying information and are retained locally while this feature is enabled.

The inspector offers 1-hour, 6-hour, 24-hour, 7-day and 30-day views. PID plus creation time must match the stored identity. A missing sample does not mean the process was idle; it may have been outside the tracked top set, excluded, inaccessible, or not running during the sampling interval.

A separate in-memory process-growth observer remains useful for short-lived process snapshots, but its history resets with the API process. Persistent SQLite history is the durable trend source.

## Adaptive anomaly detection

The adaptive detector compares the latest system sample with up to 120 preceding samples, and requires at least 20 valid baseline values for a metric. It uses the median and median absolute deviation (MAD):
- When MAD is non-zero, the latest value must exceed a robust z-score of 3.5; metrics with defined absolute thresholds must also cross that threshold.
- When MAD is zero, it uses a documented absolute-threshold plus baseline-step rule (or a 3x baseline rule for unbounded throughput metrics).

Signals include CPU, RAM, system-volume usage, disk activity, disk latency and disk read/write throughput. A 10-minute per-metric cooldown limits repeated timeline events. Adaptive findings indicate unusual behaviour relative to the recent local baseline; they do not identify malware or a confirmed cause. A baseline may be misleading after workload changes, software updates or a machine operating-mode change.

## Continuous network quality

This feature is opt-in. Configure up to three host/port targets in Settings and enable continuous network monitoring. While background recording is running, each target is checked no more than once per minute using DNS resolution and a TCP handshake:
- DNS resolution latency and TCP connect latency are persisted.
- The continuous view compares successive TCP latency samples and labels the absolute change latency swing. This is not packet-level jitter.
- A failed TCP/DNS check is recorded as a connection-attempt failure. The stored field is named packet_loss_percent for compatibility, but in this mode it represents failed TCP connection attempts, not ICMP packet loss.
- Three consecutive failed or unhealthy checks create a network timeline event and incident capture, with a 30-minute alert cooldown.

The on-demand three-attempt diagnostic can report within-probe TCP handshake jitter. Neither mode sends HTTP requests or application payloads. Targets are explicitly user-configured; NEXUS adds no default public endpoint. The configured host label and port are stored locally so the user can identify which target degraded.

## Incident capture

Incident captures can be created manually or automatically on system resource threshold crossings, adaptive anomalies and persistent network-quality degradation. Each capture is bounded to 2 MB and the database retains at most 250 captures. The evidence bundle can include:
- Recent system resource samples (up to the last 15 minutes).
- Persistent process performance samples (up to the last 10 minutes).
- Recent network-quality and per-process network-rate samples.
- Recent investigation timeline events.
- A capture timestamp, trigger, title, severity and short summary.

Captures are stored locally in SQLite. They can include process names/PIDs and the configured network target label/port. They do not contain executable paths, command lines, usernames, socket IP addresses, MAC addresses or packet payloads. NEXUS does not automatically upload reports. Review individual incident JSON exports before sharing.

## Crash and hang event sources

Event collection is read-only and best-effort.

| Platform | Source | Limitations |
| --- | --- | --- |
| Windows | Application fault, Windows Error Reporting, application hang and .NET event IDs through optional pywin32 | Permissions and optional package availability can limit results. |
| Linux | Readable syslog, messages, kern.log and apport.log files | Distribution paths and permissions vary; journald is not queried in this build. |
| macOS | Metadata for recent .crash, .hang and .ips files in DiagnosticReports directories | Report bodies are not parsed; directories may be unavailable. |

No readable event does not prove that no crash occurred. Event correlation is temporal only.

## API

- GET /api/diagnostics?window=1h — evidence-based diagnostics and adaptive findings.
- GET /api/anomalies?window=1h — adaptive baseline analysis.
- GET /api/process-history?pid=…&create_time=…&window=24h — persistent process history.
- GET /api/network/quality?window=24h — configured DNS/TCP monitoring history.
- GET /api/incidents and GET /api/incidents/{id} — incident list and evidence.
- POST /api/incidents/capture — manual incident capture.
- GET /api/diagnostics/report?window=1h — explicitly requested JSON troubleshooting report.

## Troubleshooting

- Insufficient anomaly baseline: keep the recorder running until at least 20 usable samples exist for the metric.
- No process history: enable process history, leave background recording active, and check process exclusions. Only a bounded top set is sampled.
- No network history: enable network quality, enter at least one host/port, and ensure background recording remains enabled.
- No byte attribution: install NetHogs on Linux and check local permissions. Windows ETW/WFP and macOS providers are not available in this build.
- No incident capture: check whether the selected trigger threshold or three-consecutive-network-check condition has occurred; manual capture is also available.
- No OS events: verify platform support, optional dependencies, log access and permissions.

Diagnostics are observational. No process is killed, service restarted, fan curve changed, or application configuration changed automatically.
