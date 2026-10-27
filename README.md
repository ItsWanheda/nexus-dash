# NEXUS-DASH

**A local-first system observability dashboard with a rolling Flight Recorder, process intelligence, historical charts, and configurable resource alerts.**

NEXUS-DASH combines a dependency-free vanilla JavaScript interface with a Python FastAPI + psutil backend. It is designed for inspecting one local machine, not as a public or multi-user monitoring service.

![NEXUS preview](src/img/Preview.png)

## What it does

### Live system monitoring
- CPU utilisation, logical/physical core counts, RAM use, system-volume use, network counters/rates, uptime, and host profile.
- Optional NVIDIA GPU memory via NVML when compatible hardware, drivers, and the nvidia-ml-py package are available.
- Unsupported GPU telemetry is explicitly unavailable; the interface does not invent readings.

### System Flight Recorder
- Local SQLite telemetry history that survives page reloads and browser restarts.
- CPU, RAM, disk-use, network-counter, and available GPU-memory samples, recorded at a bounded interval.
- Historical replay windows: 5 minutes, 15 minutes, 1 hour, 6 hours, and 24 hours.
- Resource history charts and JSON/CSV export. JSON session export also includes browser-session events, resource alerts, alert settings, and the latest process snapshot.
- Background recording continues while the local API is running, even when the dashboard tab is not open.

### Process intelligence
- Filterable process snapshot with CPU, memory, state, and guarded termination.
- Parent/child process tree for understanding process relationships.
- Tree snapshots are bounded and best-effort; permissions and short-lived processes can limit visibility.
- Termination remains restricted to same-user processes and protected PIDs are rejected.

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

## API reference

| Method | Endpoint | Purpose |
| --- | --- | --- |
| GET | /api/health | Local API health/version |
| GET | /api/stats | Current CPU, RAM, disk, network, GPU, and host snapshot |
| GET | /api/processes?limit=100 | Filterable process snapshot (limit 1–200) |
| GET | /api/process-tree?limit=500 | Bounded parent/child tree (limit 1–1000) |
| GET | /api/history?window=1h&limit=600 | Historical samples; windows: 5m, 15m, 1h, 6h, 24h |
| GET | /api/history/export?format=json&window=24h&limit=2000 | Download historical samples as JSON or CSV |
| POST | /api/process/kill | Request termination of an eligible PID; body: {"pid": 1234} |
| POST | /api/terminal | Run an exact allowlisted diagnostic; body: {"command": "status"} |

Interactive OpenAPI/Swagger endpoints are intentionally disabled.

## Local history, retention, and privacy

By default, telemetry is stored in:

- **Windows:** %USERPROFILE%\.nexus-dash\telemetry.sqlite3
- **Linux/macOS:** ~/.nexus-dash/telemetry.sqlite3

Set NEXUS_DATA_DIR before starting the API to choose a different local data directory. The recorder creates a private directory where filesystem permissions support it. It keeps at most 24 hours and 20,000 samples, whichever limit is reached first, and rate-limits persistent writes to approximately one sample every five seconds.

Persistent samples contain resource metrics and a UTC timestamp. Hostname, OS username, executable paths, command lines, and process names are not written to the telemetry database. Process snapshots and browser event logs are collected separately for the live UI and are only included in an export when the user explicitly requests a session JSON export.

To clear history, stop NEXUS and remove the telemetry.sqlite3, telemetry.sqlite3-wal, and telemetry.sqlite3-shm files from the data directory. Browser-local alert preferences can be removed by clearing site data for the local UI origin. See docs/FLIGHT_RECORDER.md for details.

## Tests

    python -m pip install -r requirements-dev.txt
    python -m pytest -q
    node --check src/static/flight-recorder.js
    node --check src/static/app.js
    python -m compileall -q server.py telemetry_store.py tests

CI validates Python 3.10–3.13, frontend JavaScript syntax, Python compilation, and the test suite. Local manual checks across Windows, Linux, and macOS are still recommended for process visibility and permission-dependent behaviour.

## Project layout

    nexus-dash/
    ├── .github/workflows/ci.yml
    ├── docs/FLIGHT_RECORDER.md
    ├── src/static/app.js
    ├── src/static/flight-recorder.js
    ├── src/style/styles.css
    ├── tests/
    ├── index.html
    ├── server.py
    ├── telemetry_store.py
    ├── requirements.txt
    ├── requirements-dev.txt
    ├── SECURITY.md
    ├── CHANGELOG.md
    └── README.md

## Security

Read SECURITY.md before changing the networking model or process-control behaviour. Keep the API bound to loopback and run it as a standard user. Never expose port 8000 to the internet or a LAN.

## License

MIT. See LICENSE.
