# 🧭 Python Architecture and Project Structure

NEXUS-DASH keeps its Python implementation in the `nexus_dash` package. The package separates HTTP composition, desktop integration, and reusable monitoring services while keeping the browser application and distribution assets at the repository root.

## 🗺️ Repository map

```text
nexus-dash/
├── nexus_dash/
│   ├── __init__.py
│   ├── api/
│   │   ├── __init__.py
│   │   └── server.py              # FastAPI app, middleware and route composition
│   ├── desktop/
│   │   ├── __init__.py
│   │   └── app.py                 # PyWebView, tray and desktop lifecycle
│   └── services/
│       ├── __init__.py
│       ├── analytics.py           # Historical analytics, comparisons and scorecards
│       ├── anomaly_detection.py   # Adaptive baseline and anomaly signals
│       ├── diagnostics.py         # Evidence-based diagnostics and OS event reads
│       ├── hardware.py             # Hardware collection orchestration
│       ├── hardware_providers.py  # Optional OS/vendor hardware providers
│       ├── local_agent.py         # Local Ollama assistant integration
│       ├── network_metrics.py     # Interface counters, sockets and connectivity
│       ├── network_quality.py     # Configured DNS/TCP quality sampling
│       ├── process_intelligence.py# Process identity, inspection and history
│       ├── process_network.py     # Optional per-process network attribution
│       ├── settings_store.py      # Validated local settings
│       ├── storage_metrics.py     # Disk activity and optional SMART queries
│       ├── telemetry_store.py     # SQLite history, incidents and retention
│       └── terminal_service.py   # Restricted diagnostic command grammar
├── tests/                         # Unit, API, persistence and provider tests
├── src/                           # Browser JavaScript, styles and images
├── docs/                          # Architecture references and feature guides
├── installer/                     # Inno Setup installer definition
├── scripts/                       # Windows build automation
├── server.py                      # Legacy ASGI/CLI compatibility launcher
├── desktop_app.py                 # Legacy desktop compatibility launcher
├── index.html                     # Browser application shell
├── NEXUS-DASH.spec                # PyInstaller configuration
└── requirements*.txt              # Runtime, development and optional dependencies
```

## 🧱 Runtime layers

### 1. API composition — `nexus_dash/api/server.py`

The FastAPI application is the composition root. It wires service objects together, defines request/response models and routes, and applies the local-access, trusted-host and browser-origin safeguards.

Keep API-specific concerns here:
- HTTP validation, status codes and response contracts.
- Route-to-service orchestration.
- Middleware and application lifecycle.
- API-level limits and security boundaries.

Move reusable collection, persistence or analysis logic into a service module rather than adding more domain logic to the API file.

### 2. Desktop integration — `nexus_dash/desktop/app.py`

The desktop layer owns the Windows PyWebView and tray lifecycle, local static server, API startup and shutdown, and optional Windows startup registration.

It imports the API and settings services only when the desktop runtime is launched. Optional GUI dependencies remain lazy imports so importing the desktop module does not require PyWebView, pystray or Pillow.

### 3. Service layer — `nexus_dash/services/`

| Module | Responsibility |
|---|---|
| `telemetry_store.py` | SQLite schema, persistence, retention, incidents and historical queries |
| `settings_store.py` | Validated settings and local configuration persistence |
| `diagnostics.py` | Evidence-based findings, process-memory observation and OS event metadata |
| `hardware.py` | Unified hardware snapshot and component status |
| `hardware_providers.py` | Optional platform and vendor inventory/sensor providers |
| `storage_metrics.py` | Disk throughput, I/O activity, drive metadata and optional SMART data |
| `process_intelligence.py` | Process identity, inspection, resource samples and history |
| `process_network.py` | Optional per-process network attribution |
| `network_metrics.py` | Interface metrics, connection inventory and bounded connectivity probes |
| `network_quality.py` | Configured DNS/TCP target sampling and quality assessment |
| `analytics.py` | Historical distributions, trends, comparisons and scorecards |
| `anomaly_detection.py` | Adaptive baseline analysis and anomaly signals |
| `terminal_service.py` | Explicit allowlisted diagnostic command parser |
| `local_agent.py` | Local Ollama connectivity and assistant fallback behaviour |

Service modules should be independently testable and should not import FastAPI, desktop GUI packages or the browser layer unless a clear boundary requires it.

### 4. Browser interface and assets

The HTML document defines the dashboard shell. Vanilla JavaScript modules live under `src/static/`, styles live under `src/style/`, and preview assets live under `src/img/`. The frontend is served locally and does not require a package-manager build step.

### 5. Packaging and automation

- `server.py` preserves the historical `python server.py` command and `server:app` ASGI import target.
- `desktop_app.py` preserves the historical desktop launch command used by users and the Windows build.
- `NEXUS-DASH.spec` packages the desktop launcher and local UI assets.
- `scripts/build_windows.ps1` orchestrates PyInstaller and Inno Setup.
- `.github/workflows/ci.yml` compiles package and launcher sources and runs the test suite across supported Python versions.

## 🔁 Compatibility launchers

The root launchers are intentionally small. They delegate to the package implementation rather than duplicating application logic.

The `server.py` compatibility shim aliases the imported module to `nexus_dash.api.server`. This preserves the historical ASGI target and keeps module-level access consistent for integrations that still import `server`.

The `desktop_app.py` shim delegates to `nexus_dash.desktop.app` and preserves the existing CLI flags. Keep these files as launch/compatibility layers; new functionality belongs inside `nexus_dash/`.

## 🧩 Import conventions

Use package-qualified imports for application entry points and tests:

```python
from nexus_dash.services.telemetry_store import TelemetryStore
from nexus_dash.services.network_metrics import NetworkSampler
from nexus_dash.api.server import app
```

Inside `nexus_dash/services/`, use relative imports for sibling services:

```python
from .network_metrics import diagnose_tcp_connectivity
```

Avoid:
- Importing all services eagerly from a package `__init__.py`.
- Loading optional hardware/GUI providers at module import time.
- Creating circular imports between the API and service layer.
- Reintroducing top-level copies of service implementations.

## ✅ Validation after Python changes

Run from the repository root:

```bash
python -m compileall -q nexus_dash tests server.py desktop_app.py
python -m pytest -q
```

For changes involving the desktop runtime, also run the Windows packaging workflow and manually smoke-test the window/tray lifecycle on a supported Windows machine.

> ⚠️ A successful import or unit-test run does not prove that a frozen desktop build can locate its HTML/JavaScript assets or load platform-specific optional providers. Validate the packaged artifact separately.

## 🛡️ Design constraints to preserve

- The API must remain bound to loopback; do not expose it to a LAN or the public internet.
- Preserve trusted-host, local-client and browser-origin checks.
- Keep the diagnostic terminal an allowlisted diagnostics interface, not a general shell.
- Never terminate a process automatically in response to thresholds or anomaly scores.
- Revalidate process identity before a user-requested termination.
- Keep hardware and vendor providers optional, bounded and explicit about unavailable readings.
- Keep telemetry local and preserve the existing SQLite retention controls.
