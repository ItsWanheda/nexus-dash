# 🧭 Project Structure and Module Responsibilities

This document explains where NEXUS-DASH code lives, why the current layout is intentionally hybrid, and how to make future structural changes safely.

## 🗺️ Repository map

```text
nexus-dash/
├── .github/
│   ├── ISSUE_TEMPLATE/          # Bug reports and feature requests
│   └── workflows/               # Python CI and Windows desktop packaging
├── docs/
│   ├── architecture/            # Architecture and security references
│   └── guides/                  # Feature and operator guides
├── src/
│   ├── img/                     # UI preview and image assets
│   ├── static/                  # Browser JavaScript modules
│   └── style/                   # CSS
├── tests/                       # Backend, API and provider tests
├── installer/                   # Inno Setup installer definition
├── scripts/                     # Windows build automation
├── server.py                    # FastAPI entry point and route composition
├── desktop_app.py               # Windows PyWebView/tray entry point
├── telemetry_store.py           # SQLite schema, persistence and retention
├── diagnostics.py               # Evidence-based diagnostics and OS event reads
├── hardware.py                  # Hardware collection orchestration
├── hardware_providers.py        # Optional vendor/OS hardware providers
├── storage_metrics.py           # Storage sampling and SMART queries
├── process_intelligence.py      # Process inspection and history helpers
├── process_network.py           # Optional per-process network attribution
├── network_metrics.py           # Interface metrics, sockets and connectivity checks
├── network_quality.py           # Configured continuous DNS/TCP quality sampling
├── analytics.py                 # Historical summaries and scorecards
├── anomaly_detection.py        # Adaptive median/MAD anomaly analysis
├── terminal_service.py         # Restricted diagnostic command parser
├── local_agent.py                # Local Ollama assistant integration
├── settings_store.py           # Validated local settings
├── index.html                    # Browser application shell
├── NEXUS-DASH.spec               # PyInstaller configuration
├── requirements*.txt             # Runtime, development and optional dependencies
├── README.md                     # Project overview and setup
├── CHANGELOG.md                  # Release history
├── CONTRIBUTING.md               # Contributor workflow
├── SECURITY.md                   # Vulnerability policy
└── LICENSE                       # MIT license
```

## 🧩 Runtime layers

### Browser interface — `index.html` and `src/`
The HTML document defines the dashboard shell. JavaScript modules under `src/static/` implement the UI and call the local API. Styles are maintained in `src/style/`; preview assets are under `src/img/`.

The frontend is vanilla JavaScript and does not require a package-manager build step.

### Local API — `server.py`
The API entry point composes FastAPI routes and application services. It also establishes the loopback, trusted-host and origin checks. Keep route validation and security middleware changes reviewable and covered by API tests.

### Backend service modules
- `telemetry_store.py`: SQLite persistence, retention and local history access.
- `diagnostics.py`: evidence-based findings, process-memory observation and OS event metadata.
- `hardware.py` / `hardware_providers.py`: hardware inventory and optional provider integrations.
- `storage_metrics.py`: storage counters, per-device metrics and optional SMART queries.
- `process_intelligence.py`: process identity, inspection and persistent performance history.
- `process_network.py`: optional per-process network byte-rate provider.
- `network_metrics.py` / `network_quality.py`: interface/socket/connectivity metrics and configured quality checks.
- `analytics.py` / `anomaly_detection.py`: historical summaries and adaptive signals.
- `terminal_service.py`: explicit diagnostics grammar; it is not a general shell.
- `local_agent.py`: local Ollama integration without command-execution tools.
- `settings_store.py`: validated settings persisted locally.

### Desktop packaging
`desktop_app.py` starts the local API and static UI inside the Windows desktop shell. `NEXUS-DASH.spec` defines PyInstaller inputs. The Inno Setup recipe is under `installer/`, and the PowerShell build entry point is under `scripts/`.

### Tests and automation
`tests/` contains automated backend and API tests. `.github/workflows/ci.yml` validates Python versions, JavaScript syntax, compilation and pytest. The Windows workflow builds desktop artifacts.

## 🧱 Why the backend modules remain at the root

This layout is intentionally not a conventional `src/nexus_dash/` Python package yet:

1. `server.py` imports backend modules directly from the repository root.
2. `desktop_app.py` imports the API and settings modules using the same import layout.
3. The PyInstaller spec collects the root entry points and their dependencies.
4. CI compile commands and tests currently target those modules directly.

Moving them without a complete import, test, packaging and runtime migration would create avoidable release risk. The current organization therefore groups documentation, browser assets, tests, build scripts and installer resources while preserving stable Python entry points.

## 🔧 Safe rules for future moves

Before moving a module or asset:

- Search all imports, dynamic imports, file paths and test fixtures that refer to it.
- Update PyInstaller `pathex`, `datas`, hidden imports and installer paths where required.
- Update CI compile/test commands and workflow path filters.
- Check desktop and browser static-file serving paths.
- Preserve compatibility or add an intentional migration layer when external scripts may import the old path.
- Move files and update references in one atomic commit.
- Run the full test suite and build the Windows artifact after structural changes.

> ⚠️ A successful Python import check alone does not prove the packaged desktop application can find its UI assets or optional providers.
