# Security Policy

NEXUS-DASH is a **local system-monitoring tool**. It is not intended to be an internet-facing service, multi-user control plane, or general-purpose remote shell.

## Supported versions

| Version | Status |
| --- | --- |
| Latest main / active development branch | Expected to receive fixes |
| Older snapshots | Upgrade to the latest supported code |

## Deployment constraints

- The bundled server must bind to 127.0.0.1, not 0.0.0.0.
- Never expose port 8000 through a firewall rule, tunnel, reverse proxy, port-forward, or public hosting.
- Browser origins are explicitly allowlisted; credentialed CORS is disabled and non-loopback clients are rejected.
- The diagnostic terminal must remain limited to built-in read-only diagnostics. Do not reintroduce shell=True, arbitrary subprocess commands, command chaining, or eval.
- Process termination can disrupt work. It rejects protected PIDs and processes owned by another user, but permissions and operating-system behaviour still matter.
- Run under a standard user account rather than an administrator/root account for routine monitoring.
- The loopback service does not implement user authentication; its trust boundary is the local machine.

## Diagnostics and report privacy

- Process-memory tracking uses a bounded in-memory buffer and resets when the API restarts; process names and PIDs are not written to the Flight Recorder database.
- OS event collection is read-only and best-effort. Windows event-log access requires optional pywin32; Linux/macOS sources depend on readable local logs or report metadata.
- Diagnostic report export is user-initiated and can contain telemetry, process names/PIDs, and sanitised event metadata. Review reports before sharing.
- Findings are heuristic indicators. Resource pressure does not establish root cause, memory growth does not prove a leak, and timestamp correlation does not establish causation.

## Telemetry privacy and retention

- Historical data is stored locally in SQLite under ~/.nexus-dash/telemetry.sqlite3 or the directory chosen by NEXUS_DATA_DIR.
- The database stores resource values and timestamps only; the recorder intentionally excludes hostname, OS username, process names, executable paths, and command lines.
- Retention is bounded to 24 hours and 20,000 samples. Stored telemetry is not uploaded or sent to a third-party service.
- Export files can include sensitive local resource and process/session information. Save and share them carefully; the JSON session export may contain browser session events and a process snapshot.
- Browser desktop notifications are optional and require an explicit user action. Alert preferences remain in the browser's local storage.

## Reporting a vulnerability

Do not publish working exploits or sensitive host data in a public issue. Use GitHub private vulnerability reporting if enabled, or contact the maintainer at wanheda.work@gmail.com with:
- affected commit/version and environment,
- reproduction steps or proof of concept,
- impact and prerequisites,
- suggested remediation, if known.

Only test against systems you own or have permission to administer. Reports will be acknowledged as soon as practical; this policy does not promise a fixed response SLA.

## Scope

In-scope issues include arbitrary command execution, unintended remote or cross-origin process control, sensitive information disclosure, unsafe defaults that expose the API, privilege escalation caused by this application, and telemetry retention/export defects, unbounded diagnostics collection, unsafe event-log parsing, and sensitive diagnostic reports. Visual defects and unsupported third-party driver behaviour are not security vulnerabilities by themselves.
