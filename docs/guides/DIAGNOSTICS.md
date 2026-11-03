# 🕵️ Bottleneck Detective, Diagnostics and Forensics

Bottleneck Detective combines system telemetry, persistent process history, adaptive signals and best-effort OS crash/hang indicators. It provides investigation leads; it does not repair the machine or claim that temporal correlation proves root cause.

## 📚 On this page

- [Resource-pressure analysis](#-resource-pressure-analysis)
- [Persistent process history](#-persistent-process-performance-history)
- [Adaptive anomaly detection](#-adaptive-anomaly-detection)
- [Continuous network quality](#-continuous-network-quality)
- [Incident capture](#-incident-capture)
- [Crash and hang sources](#-crash-and-hang-event-sources)
- [API and troubleshooting](#-api-and-troubleshooting)

> ⚠️ **Interpretation warning:** an alert is a signal to investigate, not proof of a faulty component, malware, a memory leak or a root cause.

## 📊 Resource-pressure analysis

The fixed/evidence-based analyzer evaluates recorded CPU utilisation, system RAM pressure, system-volume capacity and supported disk activity/latency.

A sustained finding requires:
- at least three above-threshold samples; and
- at least 25% of valid samples for that metric.

Disk activity and latency are separate measurements. Availability and meaning depend on the operating-system counter/provider.

## 🧩 Persistent process performance history

When process history is enabled, the background recorder observes a bounded set of up to 50 processes, favouring the largest resident-memory footprints. It stores:

| Field | Purpose |
| --- | --- |
| PID + process creation time | Identity key that reduces PID-reuse mixing |
| Process name | Historical attribution |
| CPU percentage, RSS and thread count | Sampled process performance |
| Disk read/write byte counters | Cumulative I/O where the OS exposes it |
| Derived read/write rates | Per-second counter deltas |

History is stored in local SQLite and remains available after a process exits, the inspector closes or the API restarts. Sampling follows the selected interval and retention-aware effective cadence. Process exclusions apply.

Process command lines, executable paths and usernames are not stored in this table. Process names and PIDs are identifying information and remain local while the feature is enabled.

The inspector offers 1-hour, 6-hour, 24-hour, 7-day and 30-day views. PID plus creation time must match the stored identity. A missing sample does not mean the process was idle: it may have been outside the tracked top set, excluded, inaccessible or not running during that interval.

A separate in-memory process-growth observer is useful for short-lived snapshots, but resets when the API process restarts. Persistent SQLite history is the durable trend source.

## 📈 Adaptive anomaly detection

The adaptive detector compares the latest system sample with up to 120 preceding samples and requires at least 20 valid baseline values for a metric. It uses the median and median absolute deviation (MAD):

- When MAD is non-zero, the latest value must exceed a robust z-score of 3.5; metrics with defined absolute thresholds must also cross that threshold.
- When MAD is zero, the detector uses a documented absolute-threshold plus baseline-step rule, or a 3× baseline rule for unbounded throughput metrics.
- A 10-minute per-metric cooldown limits repeated timeline events.

Signals include CPU, RAM, system-volume usage, disk activity, disk latency and disk read/write throughput.

> 💡 **Tip:** allow the recorder to collect at least 20 usable baseline samples before relying on adaptive analysis. A baseline can become misleading after workload, software or operating-mode changes.

Adaptive findings indicate unusual behaviour relative to the recent local baseline. They do not identify malware or prove a cause.

## 🌐 Continuous network quality

This feature is opt-in. Configure up to three host/port targets in Settings and enable continuous network monitoring. While background recording is running, each target is checked no more than once per minute using DNS resolution and a TCP handshake.

- DNS resolution latency and TCP connect latency are persisted.
- The continuous view compares successive TCP latency samples and labels the absolute change **latency swing**. This is not packet-level jitter.
- A failed TCP/DNS check is recorded as a connection-attempt failure. The stored field named `packet_loss_percent` is retained for compatibility; in this mode it represents failed TCP connection attempts, not ICMP packet loss.
- Three consecutive failed or unhealthy checks create a network timeline event and incident capture, with a 30-minute alert cooldown.

The on-demand three-attempt diagnostic can report within-probe TCP handshake jitter. Neither mode sends HTTP requests or application payloads. NEXUS adds no default public endpoint. Configured host labels and ports are stored locally so the user can identify the target that degraded.

## 📦 Incident capture

Captures can be created manually or automatically on system resource threshold crossings, adaptive anomalies and persistent network-quality degradation.

Each capture is bounded to **2 MB**, and the database retains at most **250 captures**. An evidence bundle can include:
- recent system resource samples (up to 15 minutes),
- persistent process performance samples (up to 10 minutes),
- recent network-quality and per-process network-rate samples,
- recent investigation timeline events,
- capture timestamp, trigger, title, severity and short summary.

Captures are stored locally in SQLite. They can include process names/PIDs and configured network target labels/ports. They do not contain executable paths, command lines, usernames, socket IP addresses, MAC addresses or packet payloads.

> ⚠️ Review individual incident JSON exports before sharing. Local evidence may still reveal application names, process identifiers and network targets.

NEXUS does not automatically upload reports.

## 🧾 Crash and hang event sources

Event collection is read-only and best-effort.

| Platform | Source | Limitations |
| --- | --- | --- |
| Windows | Application fault, Windows Error Reporting, application hang and .NET event IDs through optional pywin32 | Permissions and optional package availability can limit results |
| Linux | Readable syslog, messages, kern.log and apport.log files | Distribution paths and permissions vary; journald is not queried |
| macOS | Metadata for recent .crash, .hang and .ips files in DiagnosticReports directories | Report bodies are not parsed; directories may be unavailable |

No readable event does not prove that no crash occurred. Event correlation is temporal only.

## 🔌 API and troubleshooting

| Endpoint | Purpose |
| --- | --- |
| `GET /api/diagnostics?window=1h` | Evidence-based diagnostics and adaptive findings |
| `GET /api/anomalies?window=1h` | Adaptive baseline analysis |
| `GET /api/process-history?pid=…&create_time=…&window=24h` | Persistent process history |
| `GET /api/network/quality?window=24h` | Configured DNS/TCP monitoring history |
| `GET /api/incidents` and `GET /api/incidents/{id}` | Incident list and evidence |
| `POST /api/incidents/capture` | Manual incident capture |
| `GET /api/diagnostics/report?window=1h` | Explicitly requested JSON report |

### Common issues

| Symptom | What to check |
| --- | --- |
| Insufficient anomaly baseline | Keep the recorder running until at least 20 usable samples exist for the metric |
| No process history | Enable process history, keep background recording active and review exclusions |
| No network history | Enable network quality, configure at least one host/port and keep background recording active |
| No per-process byte attribution | Install NetHogs on Linux and check permissions; Windows ETW/WFP and macOS providers are not available in this build |
| No incident capture | Check whether the selected threshold or three-consecutive-network-check condition occurred; manual capture is also available |
| No OS events | Check platform support, optional dependencies, readable logs and permissions |

**Safety note:** diagnostics are observational. No process is killed, service restarted, fan curve changed or application configuration changed automatically.
