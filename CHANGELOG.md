# Changelog

All notable changes to NEXUS-DASH are recorded here. Unreleased changes are part of the active development branch and are not a published release.

## [2.0.0] - 2026-10-27

### Added — Bottleneck Detective and troubleshooting
- Added evidence-based analysis for sustained CPU saturation, system-memory pressure, and system-volume capacity pressure, including peak/average values, threshold counts, severity, confidence, and next steps.
- Added bounded process RSS growth tracking in memory, keyed by PID plus process creation time to reduce PID-reuse confusion; process identities are not persisted to SQLite.
- Added best-effort OS crash/hang indicators: Windows Application events through optional pywin32, readable Linux system-log indicators, and macOS DiagnosticReports metadata.
- Added temporal correlation between resource-pressure samples and OS events, explicitly avoiding causal claims.
- Added an on-demand JSON troubleshooting report with analysis, bounded telemetry, process-memory growth candidates, event metadata, and privacy notice.
- Added Bottleneck Detective UI, diagnostics API tests, memory-growth tests, and platform source-status reporting.
- Added docs/DIAGNOSTICS.md and updated project, API, security, contribution, and Flight Recorder documentation.
- Bumped application/API version to 2.0.0.

### Added — Telemetry history and process intelligence
- Added a local SQLite System Flight Recorder with a background sampler, five-second write throttling, a 24-hour retention window, and a 20,000-sample cap.
- Added historical replay windows, real CPU/RAM/disk charts, history and JSON/CSV exports, plus a session JSON export containing user-selected session events, alerts, and process snapshot data.
- Added a bounded parent/child process tree while preserving the existing filterable process list and same-user termination safeguards.
- Added configurable CPU, RAM, and system-volume threshold alerts with consecutive-sample controls and optional browser notifications.
- Added tests for bounded SQLite history, write throttling, history endpoints, exports, and process-tree responses.
- Added docs/FLIGHT_RECORDER.md covering data lifecycle, API usage, privacy, retention, exports, and troubleshooting.

### Security and privacy
- Persisted only sanitised resource metrics and timestamps; hostname, username, process names, command lines, and executable paths are excluded from stored telemetry.
- Kept browser notifications opt-in, process snapshots bounded, and all new endpoints behind the existing local-client, origin, and host checks.

### Existing security and UI work
- Removed arbitrary shell execution from the diagnostic console; only exact read-only diagnostics are accepted.
- Added loopback-client enforcement, origin allowlisting, restrictive CORS, trusted-host validation, and structured API errors.
- Restricted process termination to current-user processes and protected PIDs; disabled interactive OpenAPI/Swagger endpoints.
- Preserved the dark/neon-green interface while improving responsive navigation, focus states, reduced-motion handling, live telemetry, and session logs.

## [1.3.0] - 2026-10-27
- Added the System Flight Recorder, bounded history APIs, process tree, exports, and configurable resource alerts.

## [1.1.0] - 2026-06-14
- Added the first psutil-backed system telemetry API, process manager, and diagnostic terminal.

## [1.0.0] - 2026-06-13
- Initial dashboard UI and responsive layout.
