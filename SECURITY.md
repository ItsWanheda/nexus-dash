# 🔐 Security Policy

NEXUS-DASH is a **local system-observability and diagnostics application**. It is designed to inspect one machine. It is not an internet-facing service, multi-user control plane, remote administration server or general-purpose shell.

> ⚠️ **Do not expose the NEXUS API.** Keep port 8000 bound to loopback. Do not publish it through a firewall rule, tunnel, reverse proxy, port-forward or public hosting service.

## Supported versions

| Version | Security support |
| --- | --- |
| Latest active development version | Expected to receive fixes |
| Older snapshots | Upgrade to the latest supported code |

## 🛡️ Security boundaries

- **Network:** the API binds to `127.0.0.1`, validates trusted hosts and loopback clients, and accepts only explicitly allowed browser origins. Credentialed CORS is disabled.
- **Authentication:** the local API does not implement user authentication. Its trust boundary is the local machine and local user session; this is not a remote-access security model.
- **Diagnostic terminal:** commands are parsed through an explicit allowlist. NEXUS does not launch CMD, PowerShell, Bash, arbitrary executables or user-supplied scripts.
- **Process control:** termination is a user-requested action. The backend checks PID plus process creation time, rejects protected PIDs and restricts eligible targets to the current user. OS permissions and races still apply.
- **Hardware:** fan monitoring and SMART health checks are read-only. NEXUS does not set fan curves or change device configuration.
- **Local assistant:** Sentinel communicates with the local Ollama service at `127.0.0.1:11434`. It has no command-execution or process-control tools and no cloud fallback.

Run NEXUS as a standard user for routine monitoring. Elevated privileges can expose more system information, but also increase the impact of a defect.

## 🗃️ Telemetry, privacy and retention

Data is stored in local SQLite under `~/.nexus-dash/telemetry.sqlite3` by default, or under the directory configured by `NEXUS_DATA_DIR`.

Different feature tables have different data:
- **Aggregate resource history:** timestamps and numeric system metrics.
- **Process performance history:** process name, PID, process creation time, CPU, RSS memory, thread count and disk I/O counters/rates. Sampling is bounded and can be disabled in Settings.
- **Per-process network history:** process name, PID and measured byte rates when the optional provider and setting are enabled.
- **Network-quality history:** user-configured target label/port and DNS/TCP measurements when continuous checks are enabled.
- **Timeline and incident captures:** bounded local events and evidence assembled from the feature tables above.

The application does not persist executable paths, process command lines, OS usernames, packet payloads, MAC addresses or socket IP endpoints in these new history features. A user-entered network target label can itself contain a hostname or IP address. Process names and PIDs are identifying information and should be treated accordingly.

Retention is configurable (1, 7 or 30 days) and storage is bounded by feature-specific caps. Longer retention can increase the effective sampling interval to stay within those caps. Incident captures are bounded to 2 MB each and the store retains at most 250 captures.

No telemetry is automatically uploaded to a NEXUS cloud service. When the user enables Sentinel context, selected local evidence is sent to the local Ollama process. User-triggered exports can contain sensitive operational information; inspect them before sharing.

Use **Settings → Clear History** to remove local history tables and incident captures. Browser-local alert preferences are separate from the SQLite database.

## 🔎 Diagnostics and interpretation

- OS event collection is read-only and best-effort. Windows may use optional pywin32; Linux and macOS sources depend on readable local logs or report metadata.
- A missing event does not prove that no crash occurred.
- Resource pressure does not establish root cause.
- Memory growth does not prove a memory leak.
- Anomaly detection does not identify malware.
- Timestamp correlation does not establish causation.

See [Diagnostics and forensics](docs/guides/DIAGNOSTICS.md) and [Flight Recorder](docs/guides/FLIGHT_RECORDER.md) for collection details and limitations.

## 🐛 Reporting a vulnerability

Please do not publish working exploits, credentials, private database files or sensitive host data in a public issue.

Use GitHub private vulnerability reporting if enabled, or contact the maintainer at **wanheda.work@gmail.com**. Include:
- affected commit/version and operating system,
- concise reproduction steps or proof of concept,
- impact, prerequisites and realistic attack scenario,
- relevant logs with secrets and personal data removed,
- suggested remediation, if known.

Only test against systems you own or have explicit permission to administer. Reports will be acknowledged as soon as practical; no fixed response SLA is promised.

## 🎯 Scope

In-scope security issues include:
- arbitrary command execution or terminal allowlist bypass,
- unintended remote or cross-origin API access,
- unauthorized or unsafe process control,
- privilege escalation caused by NEXUS,
- exposure of sensitive local telemetry or assistant context,
- unsafe defaults that expose the API beyond loopback,
- retention, export or incident-capture defects that disclose private data,
- unbounded diagnostics collection or unsafe parsing of local event data.

Visual defects and unsupported behaviour in third-party drivers/providers are not security vulnerabilities by themselves.
