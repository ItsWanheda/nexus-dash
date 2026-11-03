# NEXUS-DASH

**A local-first system observability and diagnostics platform with a Flight Recorder, process intelligence, Bottleneck Detective, memory-growth tracking, and crash/event correlation.**

NEXUS-DASH 2.0.0 combines a dependency-free vanilla JavaScript interface with a Python FastAPI + psutil backend. It records bounded local telemetry and analyses evidence to investigate performance problems; it does not claim automatic root-cause certainty. It is designed for inspecting one local machine, not as a public or multi-user monitoring service.

![NEXUS preview](src/img/Preview.png)

## Version 2.0.0

This major release adds evidence-based diagnostics. See [CHANGELOG.md](CHANGELOG.md) and [docs/DIAGNOSTICS.md](docs/DIAGNOSTICS.md).

## What it does

### Live system monitoring
- CPU utilisation per core and available frequency/temperature sensors, RAM availability/cache/swap/pressure, system volumes, network counters/rates, uptime, and host profile.
- Hardware view for system manufacturer/model, SMBIOS/DMI motherboard and BIOS identity, CPU/board temperatures, fan RPM, battery and memory-pressure telemetry.
- GPU inventory recognises AMD, NVIDIA and Intel adapters through Windows WMI or Linux PCI identifiers. NVIDIA live telemetry uses NVML; supported Linux AMDGPU/ROCm systems can use AMD SMI. Older or unsupported cards remain visible as **Inventory only** when no live provider is available.
- Windows can read expanded CPU/board/GPU/fan sensors from LibreHardwareMonitor when its WMI provider is running. Linux reads psutil and kernel hwmon values where drivers expose them. Fan monitoring is read-only.
- Storage view for read/write throughput, IOPS, per-device activity/latency where supported, top process I/O, drive capacity, and optional SMART health.
- Unsupported readings are explicitly unavailable; NEXUS does not infer or fabricate sensor values.

### System Flight Recorder
- Local SQLite telemetry history that survives page reloads and browser restarts.
- CPU, RAM, disk-use, network-counter, optional GPU-memory, aggregate disk throughput/IOPS, and supported disk activity/latency samples, recorded at a bounded interval.
- Historical replay windows: 5 minutes, 15 minutes, 1 hour, 6 hours, and 24 hours.
- Resource history charts and JSON/CSV export. JSON session export also includes browser-session events, resource alerts, alert settings, and the latest process snapshot.
- Background recording continues while the local API is running, even when the dashboard tab is not open.

### Process intelligence
- Filterable process snapshot, parent/child process tree, identity-checked process inspection, and guarded termination.
- Persistent per-process CPU, resident memory, thread count and disk read/write counters/rates stored in local SQLite while process history is enabled.
- Process history is keyed by PID plus creation time, so PID reuse does not merge unrelated applications. The recorder samples a bounded top set of processes and honours configured exclusions.
- Process paths, command lines and user names are not written to persistent process history. Process names and PIDs are persisted for historical attribution.
- Termination remains restricted to eligible same-user processes and protected PIDs are rejected.

### Network Intelligence
- Dedicated Network view with per-interface upload/download throughput, packet rates, link state, speed, MTU, duplex, and packet error/drop deltas.
- Locally recorded per-interface history and link transitions, with reset-aware rate calculations.
- Live TCP/UDP socket inventory with process ownership, protocol/state breakdowns and ports. IP addresses stay hidden unless explicitly revealed for the current view; socket rows are not persisted.
- Optional per-process byte-rate attribution through NetHogs on Linux. The provider must be installed, enabled in Settings, and permitted to capture. Windows ETW/WFP and macOS byte-accounting providers are not implemented yet; socket ownership is not presented as bandwidth.
- Optional continuous DNS/TCP quality checks for up to three user-configured host/port targets, at most once per minute while background recording is enabled. Three consecutive unhealthy checks create a timeline event and incident capture.
- On-demand DNS and TCP handshake tests report resolver latency, connect latency, within-probe jitter and failed TCP attempts. Continuous checks report the change between successive latency samples as a latency swing; they do not send HTTP requests or application payloads.

### Advanced Analytics
- Historical CPU, memory, disk and aggregate network summaries for 1-hour, 6-hour, 24-hour, 7-day and 30-day windows.
- Average, minimum, maximum, median, p95, utilisation distributions, threshold frequency, UTC-hour profiles and bucketed trend charts.
- Previous equal-length period comparisons and incident frequency by timeline category/severity.
- Independent CPU, memory, storage and network evidence scorecards. Thermal history is explicitly shown as not recorded; NEXUS does not invent readings or combine metrics into an arbitrary health score.
- Missing samples are not interpolated. Network-interface history is bounded independently and can cover up to 20,000 retained samples per interface in analytics.

### Bottleneck Detective — diagnostics and forensics
- Analyses recorded system telemetry and persistent process samples for CPU/RAM pressure, memory growth, disk throughput/activity/latency, and best-effort OS crash/hang indicators.
- Uses a rolling median/MAD baseline after at least 20 historical baseline samples, with explicit threshold/step-change fallbacks when MAD is zero. Findings are explanations for investigation, not proof of root cause.
- Captures local forensic incidents around resource threshold crossings, adaptive anomalies and sustained configured network-quality failures; users can also capture a snapshot manually.
- Incident evidence is bounded and locally stored. It can include recent resource samples, process names/PIDs and metrics, network-quality target labels/ports, process-network byte rates when available, and timeline events.
- Exports on-demand diagnostic reports and individual incident JSON captures. Review process and target information before sharing.
- OS event collection is best-effort: Windows uses optional pywin32, Linux checks readable system logs, and macOS checks DiagnosticReports metadata.

### NEXUS Sentinel — local AI assistant
- Optional Ollama-backed assistant running at 127.0.0.1:11434; the default model is qwen3.5:4b.
- The model selector shows only models already installed locally. NEXUS never downloads a model, calls a cloud inference API, or gives the model command-execution tools.
- The context toggle controls whether recent local telemetry, adaptive findings, sampled process summaries, network-quality samples and incident metadata are sent to the local model.
- A deterministic built-in diagnostic guide is used when Ollama or the selected model is unavailable. It is a fallback guide, not an LLM; no cloud fallback is attempted.

### Configurable resource alerts
- CPU, RAM, and system-volume threshold percentages.
- Consecutive-sample requirement reduces one-off alert noise.
- Optional browser desktop notifications require a user-initiated permission request.
- Alert preferences are stored in browser local storage; active alert history is session-local.

### Security and accessibility
- Loopback-only API; browser origin allowlist; restrictive CORS; trusted-host validation.
- CMD-like diagnostic terminal with useful, explicit allowlisted commands. It is not a general shell and does not support arbitrary PowerShell/CMD input, command chaining or destructive execution.
- Bounded API input, structured errors, responsive navigation, keyboard focus states, and reduced-motion support.
- No cloud telemetry upload or external analytics. Optional local network-quality targets and local model context are user-controlled.

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

### 4. Optional hardware providers

    python -m pip install -r requirements-hardware.txt

This installs optional NVML, Windows WMI and Linux AMD SMI bindings. Live readings still depend on compatible hardware and drivers. On Windows, run LibreHardwareMonitor with its WMI sensor provider enabled to expose additional fan/temperature data. On Linux, AMD SMI requires a compatible AMDGPU/ROCm driver/runtime. Missing readings remain unavailable.

### 5. Optional local AI assistant

Install Ollama separately, then pull the default model:

    ollama pull qwen3.5:4b

Start the Ollama service if it is not already running, then open NEXUS Sentinel. The model tag currently occupies approximately 3.3–4.0 GB in the Ollama library. Smaller qwen3.5:2b and qwen3.5:0.8b variants are available for systems with tighter memory budgets. NEXUS only lists installed models and never downloads one automatically.

### 6. Windows desktop application

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

### 7. Optional SMART storage health

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
| GET | /api/network/processes?window=24h | Per-process bandwidth samples/capability status (NetHogs on Linux) |
| GET | /api/network/quality?window=24h | Continuous DNS/TCP quality history for configured targets |
| GET | /api/anomalies?window=1h | Adaptive baseline analysis |
| GET | /api/incidents | List local forensic captures |
| GET | /api/incidents/{id} | Read one bounded incident evidence bundle |
| POST | /api/incidents/capture | Manually capture current local evidence |
| GET | /api/assistant/status | Local Ollama status and installed models |
| POST | /api/assistant/chat | Ask NEXUS Sentinel; optionally include local telemetry context |
| GET | /api/analytics?window=24h&compare_previous=true | Historical statistics, trends, distributions and scorecards |
| GET | /api/processes?limit=100 | Filterable process snapshot (limit 1–200) |
| GET | /api/processes/{pid}?create_time=... | Identity-checked detailed process inspection |
| GET | /api/process-history?pid=...&create_time=...&window=24h | Persistent CPU/RAM/thread/disk I/O history, keyed by PID + creation time |
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
| POST | /api/terminal | Run an allowlisted diagnostic; body: {"command": "processes 15 sort=memory"} |

Interactive OpenAPI/Swagger endpoints are intentionally disabled.

## Local history, retention, and privacy

By default, telemetry is stored in:

- **Windows:** %USERPROFILE%\.nexus-dash\telemetry.sqlite3
- **Linux/macOS:** ~/.nexus-dash/telemetry.sqlite3

Set NEXUS_DATA_DIR before starting the API to choose a different local data directory. The recorder creates a private directory where filesystem permissions support it. It keeps up to 1, 7, or 30 days within a 20,000-sample cap. Longer retention automatically increases the effective recording cadence (at least 130 seconds for 30 days), rather than silently truncating the selected period.

The aggregate resource Flight Recorder table stores numeric system metrics only. When enabled, a separate process-history table stores process name, PID, process creation time, CPU, RSS memory, threads and disk I/O counters/rates. When per-process network attribution is enabled, process name, PID and measured byte rates are stored. Continuous network-quality monitoring stores the configured target label/port and DNS/TCP timing results. Incident captures can bundle recent samples and timeline events from these tables. None of these tables stores executable paths, command lines, user names, packet payloads, MAC addresses or socket IP endpoints. User-configured target labels can contain a hostname or IP address and are retained in local network-quality history until cleared/deleted.

Process and network collection are controlled by Settings; process history is enabled by default in the standard settings. The Ollama context toggle is user-controlled too. Telemetry included in an assistant request is sent to the local Ollama process only, not to a hosted inference endpoint. Review incident exports before sharing.

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
    node --check src/static/assistant.js
    node --check src/static/app.js
    python -m compileall -q server.py telemetry_store.py diagnostics.py hardware.py hardware_providers.py storage_metrics.py process_intelligence.py settings_store.py desktop_app.py network_metrics.py analytics.py terminal_service.py process_network.py network_quality.py anomaly_detection.py local_agent.py tests

CI validates Python 3.10–3.13, frontend JavaScript syntax, Python compilation, and the test suite. Local manual checks across Windows, Linux, and macOS are still recommended for process visibility and permission-dependent behaviour.

## Project layout

    nexus-dash/
    ├── .github/workflows/ci.yml
    ├── docs/FLIGHT_RECORDER.md
    ├── docs/DIAGNOSTICS.md
    ├── docs/HARDWARE_STORAGE.md
    ├── docs/TERMINAL_SENTINEL.md
    ├── src/static/diagnostics.js
    ├── src/static/hardware.js
    ├── src/static/storage.js
    ├── src/static/network-analytics.js
    ├── src/static/assistant.js
    ├── diagnostics.py
    ├── terminal_service.py
    ├── hardware_providers.py
    ├── process_network.py
    ├── network_quality.py
    ├── anomaly_detection.py
    ├── local_agent.py
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
