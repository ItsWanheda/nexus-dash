# 🔐 NEXUS-DASH Security Model

NEXUS-DASH is a local-first, single-machine observability application. This document records the security assumptions that contributors must preserve.

## 🧱 Trust boundary

The local API is intended to be reachable only from the same machine:
- Bind to `127.0.0.1`; do not bind to `0.0.0.0`.
- Validate the Host header using trusted-host middleware.
- Reject non-loopback client addresses.
- Allow only the known local browser origins.
- Keep credentialed CORS disabled.

The API does not implement user authentication. Loopback is the intended trust boundary, not a substitute for authentication on an exposed service. Never publish the API port through a tunnel, reverse proxy, firewall rule or port-forward.

## 🖥️ Diagnostic terminal

The terminal UI accepts a deliberately small command grammar and dispatches to built-in diagnostic functions. It is not a subprocess shell.

Preserve these constraints:
- No arbitrary executable selection or shell invocation.
- No `shell=True`, command chaining, redirection, script execution or `eval`.
- Bound command length, arguments, probe counts, timeouts and output size.
- Network probes only target hosts supplied by the user.

## 🧩 Process inspection and termination

Process snapshots and historical sampling are bounded and best-effort. Permissions and short-lived processes affect visibility.

Termination is a guarded, user-initiated action:
- Validate PID and process creation time to reduce PID-reuse races.
- Reject protected/system PIDs.
- Restrict eligible targets to the current user.
- Revalidate identity immediately before acting.
- Never connect automatic alerts, anomaly triggers or thresholds to process termination.

## 📡 Hardware and network operations

- Hardware inventory and sensor collection are read-only.
- Fan monitoring never writes fan-control attributes or changes firmware settings.
- SMART health uses bounded read-only queries.
- Socket ownership is not a substitute for measured byte-rate attribution.
- Unsupported platform providers must return explicit capability status rather than fabricated values.

## 🗄️ Local persistence and privacy

SQLite data remains on the machine unless a user explicitly exports it. The aggregate resource table stores numeric metrics and timestamps. Optional feature tables can store process names/PIDs, configured network target labels/ports, measured rates and bounded incident evidence.

Do not add usernames, executable paths, command lines, packet payloads, MAC addresses or socket IP endpoints to persistent history without a separate privacy/security review and clear user-facing controls.

Retention must remain bounded. Clear History must cover every history and incident table introduced by a feature. Export endpoints must cap query sizes and payloads and must not silently include unrelated local identifiers.

## 🤖 Sentinel and external providers

Sentinel talks to the local Ollama service at `127.0.0.1:11434`. It receives only the context explicitly selected by the user. It has no command-execution, process-control or settings-mutation tools, and NEXUS has no cloud inference fallback.

Optional hardware/network providers are local dependencies. Their output is untrusted, best-effort data: validate and bound it before storing or displaying it.

## 🧪 Security review checklist

- [ ] API remains loopback-only with trusted-host and origin enforcement.
- [ ] New routes validate types, bounds and user-controlled strings.
- [ ] No new arbitrary process or shell execution path exists.
- [ ] Process-control operations revalidate identity and remain user-initiated.
- [ ] Persistent data fields, retention and deletion behaviour are documented.
- [ ] Exports are bounded and clearly described.
- [ ] Optional providers fail safely and report unavailable capability.
- [ ] Sentinel context remains local and opt-in.
- [ ] Tests cover rejection paths, permission failures and missing providers.

For vulnerability reporting, follow the root [Security Policy](../../SECURITY.md).
