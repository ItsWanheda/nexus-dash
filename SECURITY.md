# Security Policy

NEXUS-DASH is a **local system-monitoring tool**. It is not intended to be an internet-facing service, multi-user control plane, or general-purpose remote shell.

## Supported versions

| Version | Status |
| --- | --- |
| Latest main / active development branch | Expected to receive fixes |
| Older snapshots | Upgrade to the latest supported code |

## Deployment constraints

- The bundled server must bind to **127.0.0.1**, not `0.0.0.0`.
- Never expose port 8000 through a firewall rule, tunnel, reverse proxy, port-forward, or public hosting.
- Browser origins are explicitly allowlisted; credentialed CORS is disabled and non-loopback clients are rejected.
- The diagnostic terminal must remain limited to built-in read-only diagnostics. Do not reintroduce `shell=True`, arbitrary subprocess commands, command chaining, or `eval`.
- The process manager can terminate same-user processes. It rejects protected PIDs and processes owned by another user, but termination is inherently disruptive and may lose data.
- Run under a standard user account rather than an administrator/root account for routine monitoring.
- The loopback service does not implement user authentication; its trust boundary is the local machine.

## Reporting a vulnerability

Do not publish working exploits or sensitive host data in a public issue. Use GitHub private vulnerability reporting if enabled, or contact the maintainer at **wanheda.work@gmail.com** with:

- affected commit/version and environment,
- reproduction steps or proof of concept,
- impact and prerequisites,
- suggested remediation, if known.

Only test against systems you own or have permission to administer. Reports will be acknowledged as soon as practical; this policy does not promise a fixed response SLA.

## Scope

In-scope issues include arbitrary command execution, unintended remote or cross-origin process control, sensitive information disclosure, unsafe defaults that expose the API, and privilege escalation caused by this application. Visual defects and unsupported third-party driver behaviour are not security vulnerabilities by themselves.
