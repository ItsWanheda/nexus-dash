# NEXUS-DASH

**A local-first system observability and diagnostics platform with a Flight Recorder, process intelligence, Bottleneck Detective, memory-growth tracking, and crash/event correlation.**

NEXUS-DASH 2.0.0 combines a dependency-free vanilla JavaScript interface with a Python FastAPI + psutil backend. It records bounded local telemetry and analyses evidence to investigate performance problems; it does not claim automatic root-cause certainty. It is designed for inspecting one local machine, not as a public or multi-user monitoring service.

![NEXUS preview](src/img/Preview.png)

## Version 2.0.0

This major release adds evidence-based diagnostics. See [CHANGELOG.md](CHANGELOG.md) and [docs/DIAGNOSTICS.md](docs/DIAGNOSTICS.md).

## What it does

### Live system monitoring
- CPU utilisation per core and available frequency/temperature sensors, RAM availability/cache/swap/pressure, system volumes, network counters/rates, uptime, and host profile.
- Hardware view for available CPU, NVIDIA GPU, motherboard temperature/fan, and battery telemetry. Voltage, battery health, charge cycles, and unsupported sensors remain explicitly unavailable.
- Optional NVIDIA GPU utilisation, memory, temperature, power, and clock telemetry via NVML when compatible hardware, drivers, and the nvidia-ml-py package are available.
- Storage view for read/write throughput, IOPS, per-device activity/latency where supported, top process I/O, drive capacity, and optional SMART health.
- Unsupported GPU telemetry is explicitly unavailable; the interface does not invent readings.

### System Flight Recorder
- Local SQLite telemetry history that survives page reloads and browser restarts.
- CPU, RAM, disk-use, network-counter, optional GPU-memory, aggregate disk throughput/IOPS, and supported disk activity/latency samples, recorded at a bounded interval.
- Historical replay windows: 5 minutes, 15 minutes, 1 hour, 6 hours, and 24 hours.
- Resource history charts and JSON/CSV export. JSON session export also includes browser-session events, resource alerts, alert settings, and the latest process snapshot.
- Background recording continues while the local API is running, even when the dashboard tab is not open.

### Process intelligence
- Filterable process snapshot with CPU, memory, state, and guarded termination.
- Parent/child process tree for understanding process relationships.
- Tree snapshots are bounded and best-effort; permissions and short-lived processes can limit visibility.
- Termination remains restricted to same-user processes and protected PIDs are rejected.

### Network Intelligence
- Dedicated Network view with per-interface upload/download throughput, packet rates, link state, speed, MTU, duplex, and packet error/drop deltas.
- Locally recorded per-interface history and link transitions, with reset-aware rate calculations.
- Live TCP/UDP socket inventory with process attribution, protocol/state breakdowns and ports. IP addresses stay hidden unless explicitly revealed for the current view; socket rows are not persisted.
- On-demand DNS and TCP handshake tests report resolver latency, connect latency, jitter and failed attempts. The test sends no HTTP request or application payload and does not save the target host.

### Advanced Analytics
- Historical CPU, memory, disk and aggregate network summaries for 1-hour, 6-hour, 24-hour, 7-day and 30-day windows.
- Average, minimum, maximum, median, p95, utilisation distributions, threshold frequency, UTC-hour profiles and bucketed trend charts.
- Previous equal-length period comparisons and incident frequency by timeline category/severity.
- Independent CPU, memory, storage and network evidence scorecards. Thermal history is explicitly shown as not recorded; NEXUS does not invent readings or combine metrics into an arbitrary health score.
- Missing samples are not interpolated. Network-interface history is bounded independently and can cover up to 20,000 retained samples per interface in analytics.

### Bottleneck Detective — diagnostics
- Analyses real Flight Recorder samples for sustained CPU saturation, system-memory pressure, system-volume capacity pressure, and disk I/O activity/latency signals where supported.
- Tracks process resident-memory growth in a bounded in-memory buffer and reports observed growth/rate; this is a lead, not proof of a leak.
- Correlates available OS crash/hang indicators with nearby resource-pressure windows without asserting causation.
- Provides evidence-backed findings with severity, observed values, confidence limits, and practical next steps.
- Exports an on-demand JSON troubleshooting report with bounded telemetry, findings, process-memory candidates, and sanitised event metadata.
- OS event collection is best-effort: Windows uses optional pywin32, Linux checks readable system logs, and macOS checks DiagnosticReports metadata.

### Configurable resource alerts
- CPU, RAM, and system-volume threshold percentages.
- Consecutive-sample requirement reduces one-off alert noise.
- Optional browser desktop notifications require a user-initiated permission request.
- Alert preferences are stored in browser local storage; active alert history is session-local.

### Security and accessibility
- Loopback-only API; browser origin allowlist; restrictive CORS; trusted-host validation.
- Read-only diagnostic console with exact built-in commands instead of shell execution.
- Bounded API input, structured errors, responsive navigation, keyboard focus states, and reduced-motion support.
- No front-end framework, package-manager build step, external analytics, or telemetry upload.

## Stack

| Layer | Technology |
| --- | --- |
| Frontend | HTML5, CSS, vanilla JavaScript |
| Local API | Python 3.10+, FastAPI, Uvicorn |
| OS telemetry | psutil |
| Historical storage | SQLite, local filesystem only |
| Optional GPU | nvidia-ml-py / NVIDIA NVML |
| Tests | pytest, FastAPI TestClient, GitHub Actions |

## Quick start

### 1. Clone and install

    git clone https://github.com/ItsWanheda/nexus-dash.git
    cd nexus-dash
    python -m venv .venv

Activate the environment:

**Windows PowerShell**

    .\.venv\Scripts\Activate.ps1

**Linux / macOS**

    source .venv/bin/activate

Install runtime dependencies:

    python -m pip install -r requirements.txt

### 2. Run the API

From the repository root:

    python server.py

The API binds to **127.0.0.1:8000**. Health check: <http://127.0.0.1:8000/api/health>.

### 3. Serve the UI

Open a second terminal in the repository root:

    python -m http.server 5500 --bind 127.0.0.1

Open <http://127.0.0.1:5500>. Do not open index.html through a file:// URL; the UI should be served from an allowed local origin.

### 4. Optional NVIDIA GPU metrics

    python -m pip install nvidia-ml-py

The dashboard remains usable without this optional dependency.

### 5. Windows desktop application

For a source checkout:

    python -m pip install -r requirements-desktop.txt
    python desktop_app.py

NEXUS opens in a PyWebView/Edge WebView2 window, keeps the local UI and API on 127.0.0.1, and adds a system-tray menu with Open and Quit. Closing the window hides it to the tray. Start minimized is controlled by Settings or the explicit `--minimized` argument.

Windows sign-in startup is opt-in:

    python desktop_app.py --register-startup
    python desktop_app.py --remove-startup

Build the Windows x64 app and installer from PowerShell:

    ./scripts/build_windows.ps1

The Windows Desktop Build workflow packages and uploads an installer and portable artifact. This first desktop target is Windows; Linux and macOS continue to use the browser-based local-server workflow. WebView2 must be available on Windows.

### 6. Optional hardware providers and SMART

    python -m pip install -r requirements-hardware.txt

This adds NVIDIA NVML bindings and the optional Windows WMI provider. SMART health also requires the operating-system smartmontools package (`smartctl`) and appropriate read permissions. Unsupported sensor values remain unavailable.

## API reference

| Method | Endpoint | Purpose |
| --- | --- | --- |
| GET | /api/health | Local API health/version |
| GET | /api/stats | Current CPU, RAM, disk, network, GPU, storage counters, and host snapshot |
| GET | /api/hardware | Detailed CPU/core, GPU, memory, motherboard, and battery telemetry |
| GET | /api/storage | Per-drive capacity and I/O, top process activity, and optional SMART health |
| GET | /api/network | Per-interface counters, throughput, link state, errors and drops |
| GET | /api/network/connections?limit=150&include_addresses=false | Bounded live TCP/UDP socket inventory |
| GET | /api/network/history?window=24h | Locally stored interface counter history |
| GET | /api/network/diagnostics?host=example.com&port=443 | User-triggered DNS and TCP handshake diagnostics |
| GET | /api/analytics?window=24h&compare_previous=true | Historical statistics, trends, distributions and scorecards |
| GET | /api/processes?limit=100 | Filterable process snapshot (limit 1–200) |
| GET | /api/processes/{pid}?create_time=... | Identity-checked detailed process inspection |
| GET | /api/process-history?pid=...&create_time=...&window=30m | Process CPU/RAM history |
| GET | /api/process-compare?... | Compare two identity-checked process snapshots |
| GET | /api/timeline?window=24h | Local investigation timeline |
| POST | /api/timeline/markers | Add a user incident marker |
| GET/PUT | /api/settings | Read and update local settings |
| GET | /api/updates/check | Manually check latest published GitHub release |
| DELETE | /api/history | Delete local telemetry and timeline history |
| GET | /api/process-tree?limit=500 | Bounded parent/child tree (limit 1–1000) |
| GET | /api/diagnostics?window=1h | Evidence-based findings and event correlation |
| GET | /api/diagnostics/report?window=1h | On-demand JSON troubleshooting report |
| GET | /api/history?window=1h&limit=600 | Historical samples; windows: 5m, 15m, 1h, 6h, 24h |
| GET | /api/history/export?format=json&window=24h&limit=2000 | Download historical samples as JSON or CSV |
| POST | /api/process/kill | Request termination of an eligible PID; body includes pid and create_time identity |
| POST | /api/terminal | Run an exact allowlisted diagnostic; body: {"command": "status"} |

Interactive OpenAPI/Swagger endpoints are intentionally disabled.

## Local history, retention, and privacy

By default, telemetry is stored in:

- **Windows:** %USERPROFILE%\.nexus-dash\telemetry.sqlite3
- **Linux/macOS:** ~/.nexus-dash/telemetry.sqlite3

Set NEXUS_DATA_DIR before starting the API to choose a different local data directory. The recorder creates a private directory where filesystem permissions support it. It keeps up to 1, 7, or 30 days within a 20,000-sample cap. Longer retention automatically increases the effective recording cadence (at least 130 seconds for 30 days), rather than silently truncating the selected period.

Persistent samples contain resource metrics and a UTC timestamp. Hostname, OS username, executable paths, command lines, and process names are not written to the telemetry database. Process snapshots and browser event logs are collected separately for the live UI and are only included in an export when the user explicitly requests a session JSON export.

To clear history, stop NEXUS and remove the telemetry.sqlite3, telemetry.sqlite3-wal, and telemetry.sqlite3-shm files from the data directory. Browser-local alert preferences can be removed by clearing site data for the local UI origin. See docs/FLIGHT_RECORDER.md for recorder details, docs/DIAGNOSTICS.md for diagnostic thresholds, and docs/HARDWARE_STORAGE.md for hardware providers, platform limitations, SMART support, and storage counter semantics.

## Tests

    python -m pip install -r requirements-dev.txt
    python -m pytest -q
    node --check src/static/flight-recorder.js
    node --check src/static/diagnostics.js
    node --check src/static/hardware.js
    node --check src/static/storage.js
    node --check src/static/nexus-enhancements.js
    node --check src/static/network-analytics.js
    node --check src/static/app.js
    python -m compileall -q server.py telemetry_store.py diagnostics.py hardware.py storage_metrics.py process_intelligence.py settings_store.py desktop_app.py network_metrics.py analytics.py tests

CI validates Python 3.10–3.13, frontend JavaScript syntax, Python compilation, and the test suite. Local manual checks across Windows, Linux, and macOS are still recommended for process visibility and permission-dependent behaviour.

## Project layout

    nexus-dash/
    ├── .github/workflows/ci.yml
    ├── docs/FLIGHT_RECORDER.md
    ├── docs/DIAGNOSTICS.md
    ├── docs/HARDWARE_STORAGE.md
    ├── src/static/diagnostics.js
    ├── src/static/hardware.js
    ├── src/static/storage.js
    ├── src/static/network-analytics.js
    ├── diagnostics.py
    ├── hardware.py
    ├── network_metrics.py
    ├── analytics.py
    ├── process_intelligence.py
    ├── network_metrics.py
    ├── analytics.py
    ├── settings_store.py
    ├── desktop_app.py
    ├── NEXUS-DASH.spec
    ├── requirements-desktop.txt
    ├── installer/NEXUS-DASH.iss
    ├── scripts/build_windows.ps1
    ├── storage_metrics.py
    ├── src/static/app.js
    ├── src/static/flight-recorder.js
    ├── src/style/styles.css
    ├── tests/
    ├── index.html
    ├── server.py
    ├── telemetry_store.py
    ├── requirements.txt
    ├── requirements-hardware.txt
    ├── requirements-dev.txt
    ├── SECURITY.md
    ├── CHANGELOG.md
    └── README.md

## Security

Read SECURITY.md before changing the networking model or process-control behaviour. Keep the API bound to loopback and run it as a standard user. Never expose port 8000 to the internet or a LAN.

## License

MIT. See LICENSE.
