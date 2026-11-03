# 🤝 Contributing to NEXUS-DASH

Thank you for helping improve NEXUS-DASH. Contributions should make diagnostics more reliable while preserving the project's local-first design, security boundaries and accessible dark/neon-green interface.

## 📚 Before you start

1. Read the [README](README.md) to understand the application and supported workflows.
2. Review the [project structure](docs/architecture/PROJECT_STRUCTURE.md) before moving files or changing imports.
3. Read the [security model](docs/architecture/SECURITY_MODEL.md) and [Security Policy](SECURITY.md) before changing network, process-control, persistence or assistant behaviour.
4. Search existing issues and pull requests before starting duplicate work.

## 🛠️ Development setup

```bash
git clone https://github.com/ItsWanheda/nexus-dash.git
cd nexus-dash
python -m venv .venv
```

Activate the environment:

**Windows PowerShell**
```powershell
.\.venv\Scripts\Activate.ps1
```

**Linux / macOS**
```bash
source .venv/bin/activate
```

Install development dependencies:

```bash
python -m pip install -r requirements-dev.txt
```

Run the API and static UI in separate terminals:

```bash
python server.py
python -m http.server 5500 --bind 127.0.0.1
```

Open <http://127.0.0.1:5500>. Do not use a `file://` URL; the UI must be served from an allowed local origin.

## 🧱 Engineering principles

### Security is a feature
- Keep the API loopback-only and preserve trusted-host, client-IP and origin checks.
- Do not add public network access, credentialed CORS, arbitrary shell execution, command chaining, `eval`, or unrestricted subprocess calls.
- Keep diagnostic commands explicitly allowlisted and bounded.
- Process termination must remain opt-in, identity-checked and restricted to eligible same-user processes. Never terminate processes automatically from thresholds or alerts.
- Fan and SMART operations must remain read-only.

### Evidence over assumptions
- Treat hardware counters, sensors and OS event sources as best-effort.
- Mark unsupported or missing values unavailable; never substitute fabricated zeros.
- Findings must expose evidence, thresholds and limitations. Correlation is not causation; observed memory growth is not proof of a leak.
- Do not describe socket ownership as per-process bandwidth.

### Privacy and resource bounds
- Keep telemetry local and retention bounded.
- Do not persist usernames, executable paths, command lines, packet contents, MAC addresses or socket IP endpoints without a separately reviewed design.
- Explain clearly when feature-specific tables retain process names/PIDs or user-configured network target labels.
- Bound API inputs, process snapshots, sampling work, database rows, incident payloads and export sizes.

### Maintainable UI and architecture
- Keep the frontend dependency-free unless a new dependency has a clear, documented benefit.
- Preserve keyboard focus, reduced-motion support and responsive layouts.
- Keep backend entry points and imports compatible with the desktop build unless a migration updates every dependent path and is validated.
- Update the documentation index and relevant guides when paths or behaviour change.

## ✅ Validation

Run the full test suite:

```bash
python -m pytest -q
```

Check all frontend modules:

```bash
node --check src/static/app.js
node --check src/static/flight-recorder.js
node --check src/static/diagnostics.js
node --check src/static/hardware.js
node --check src/static/storage.js
node --check src/static/nexus-enhancements.js
node --check src/static/network-analytics.js
node --check src/static/assistant.js
```

Compile Python modules and tests:

```bash
python -m compileall -q server.py telemetry_store.py diagnostics.py hardware.py hardware_providers.py storage_metrics.py process_intelligence.py settings_store.py desktop_app.py network_metrics.py analytics.py terminal_service.py process_network.py network_quality.py anomaly_detection.py local_agent.py tests
```

For relevant changes, also verify:
- [ ] Linux/macOS local-server startup where supported.
- [ ] Windows desktop packaging and a manual window/tray smoke test.
- [ ] Missing hardware providers and permission-denied paths.
- [ ] Mobile and desktop UI layouts, keyboard navigation and reduced motion.
- [ ] SQLite retention, Clear History and export behaviour.
- [ ] Loopback, origin and process identity safeguards.

## 📝 Pull request checklist

- [ ] Describe the problem, approach and user-visible impact.
- [ ] Explain security and privacy implications.
- [ ] Add or update tests for changed behaviour.
- [ ] Update README, CHANGELOG and relevant guides.
- [ ] Check all relative documentation links after moving files.
- [ ] Confirm no secrets, local databases, exports, build outputs or generated artifacts are committed.
- [ ] Keep the diff focused and avoid unrelated refactors.

## 💬 Commit message convention

Use concise, imperative Conventional Commit messages:

```text
feat: add bounded process history
fix: reject stale process identities
docs: clarify local telemetry retention
refactor: isolate network sampling helpers
test: cover missing hardware providers
build: harden Windows packaging workflow
```

Prefer one logical change per commit. Include a scope when it adds clarity, and explain non-obvious decisions in the commit body.
