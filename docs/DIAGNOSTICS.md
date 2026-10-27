# Bottleneck Detective — Diagnostics in NEXUS-DASH 2.0.0

Bottleneck Detective turns available telemetry into bounded troubleshooting leads. It is not an automated repair system and does not claim that correlation proves root cause.

## Resource pressure

The analyzer reviews recorded samples for:
- CPU saturation: samples at or above 85%.
- System-memory pressure: RAM use at or above 85%.
- System-volume capacity pressure: occupied disk capacity at or above 90%.

A sustained finding requires at least three above-threshold samples and at least 25% of valid samples for that metric. A single crossing is a limited observation, not a sustained bottleneck. Severity depends on observed values and repetition, not an inferred cause.

Disk capacity is not disk I/O latency. This release does not claim to diagnose queue depth, storage latency, thermal throttling, or a specific application's CPU contention from counters it does not collect.

## Process memory-growth tracking

The API samples resident set size (RSS) for accessible processes approximately every 15 seconds while running. The tracker:
- keys observations by PID plus process creation time to reduce PID-reuse errors;
- retains at most 720 snapshots in process memory;
- requires at least three observations over at least 20 seconds;
- reports growth of at least 32 MiB and ranks up to 25 candidates;
- resets when the API process restarts.

Process names, PIDs, and RSS observations are not persisted in SQLite. They live in a bounded in-memory tracker and may appear in a user-requested diagnostic report. A growing RSS trend may reflect workload accumulation or caching; it does not prove a leak.

## Crash and hang event sources

Event collection is read-only and best-effort. NEXUS does not invoke a shell to collect events.

| Platform | Source | Limitations |
| --- | --- | --- |
| Windows | Application event IDs for application faults, Windows Error Reporting, application hangs, and .NET failures | Requires optional pywin32; access may be denied |
| Linux | Readable syslog, messages, kern.log, and apport.log files | Distribution paths and permissions vary; journald is not queried |
| macOS | Metadata for recent .crash, .hang, and .ips files in DiagnosticReports directories | Report bodies are not parsed; directories may be unavailable |

If no source is readable, a source status is returned. No readable events does not mean no crash occurred. Windows events use numeric IDs and generic summaries rather than raw event messages.

## Event correlation model

An event is marked correlated if its timestamp is within ten minutes of a sample above a resource-pressure threshold. The report explicitly labels this temporal correlation only. It does not establish whether pressure caused the event, the event caused pressure, or a third factor caused both.

## API

- GET /api/diagnostics?window=1h — analysis response.
- GET /api/diagnostics/report?window=1h — explicitly requested JSON report attachment.

Supported windows: 5m, 15m, 1h, 6h, and 24h. History results are limited to 2,000 samples and process-growth output to 25 candidates.

## Report contents and privacy

The report contains analysis metadata and findings, bounded telemetry samples, process-memory growth candidates from the current API lifetime, sanitised OS event metadata, source status, and a privacy notice. Reports are generated on request and are not uploaded. They may reveal local usage patterns, process names, PIDs, and event timing. Review before sharing. Files named nexus-diagnostics-*.json are ignored by Git.

## Troubleshooting

- No findings: the heuristics did not detect a signal in available samples; this is not a guarantee that the machine is healthy.
- Insufficient telemetry: keep the API running until more samples are recorded; history is not fabricated.
- No memory-growth candidates: process tracking requires repeated observations; short-lived processes may be missed.
- OS source unavailable: check platform support, optional dependencies, log access, and local permissions.
- Too many findings: shorten the window and compare evidence against workload; do not make changes based solely on the report.

Diagnostics are observational. No process is killed, configuration changed, or application restarted automatically.