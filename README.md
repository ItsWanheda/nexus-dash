# NEXUS-DASH

> **A local-first system observability, diagnostics and investigation workspace.**
>
> Monitor a machine, record bounded telemetry, inspect processes and network activity, and investigate performance incidents — without turning the application into a remote monitoring service.

![NEXUS-DASH preview](src/img/Preview.png)

**Version:** 2.0.0 · **Runtime:** Python 3.10+ / FastAPI · **UI:** HTML, CSS and vanilla JavaScript · **Storage:** local SQLite

[Features](#-what-nexus-dash-does) · [Quick start](#-quick-start) · [Documentation](#-documentation) · [Project layout](#-project-layout) · [Security](#-security-at-a-glance) · [Development](#-development-and-validation)

---

## 📚 Contents

- [What NEXUS-DASH does](#-what-nexus-dash-does)
- [Technology](#-technology)
- [Quick start](#-quick-start)
- [Optional integrations](#-optional-integrations)
- [API overview](#-api-overview)
- [Local data, retention and privacy](#-local-data-retention-and-privacy)
- [Documentation](#-documentation)
- [Project layout](#-project-layout)
- [Development and validation](#-development-and-validation)
- [Security at a glance](#-security-at-a-glance)
- [License](#-license)

## 🔎 What NEXUS-DASH does

NEXUS-DASH 2.0.0 combines a dependency-light browser interface with a Python FastAPI and psutil backend. It records bounded local telemetry and presents evidence that helps investigate system behaviour. Findings are investigation leads — **not automatic root-cause diagnoses**.

### 📊 Live system monitoring
- CPU utilisation per core, available frequency and temperature sensors, RAM/cache/swap/pressure, system volumes, network counters and uptime.
- Hardware identity from SMBIOS/DMI or Windows WMI, including system, motherboard and BIOS details where firmware exposes them.
- Vendor-neutral GPU inventory for AMD, NVIDIA, Intel, Apple and other OS-reported display adapters. Optional vendor/platform providers add live readings when available.
- Linux psutil/kernel hwmon readings and optional Windows LibreHardwareMonitor WMI sensors. Fan monitoring is read-only.
- Storage throughput, IOPS, device activity/latency where supported, drive capacity, top-process I/O and optional SMART health.

> ℹ️ **Provider availability varies.** Inventory can be available when live sensor values are not. Unsupported values remain explicitly unavailable; NEXUS does not fabricate readings.

### 🕒 System Flight Recorder
- Local SQLite resource history that survives browser reloads and API restarts.
- Bounded CPU, memory, disk, network and supported GPU/storage samples.
- Historical replay, charts, JSON/CSV exports, configurable retention and a local investigation timeline.
- Background recording continues while the API is running, even when the dashboard tab is closed.

### 🧩 Process intelligence
- Filterable process snapshots, parent/child navigation and detailed process inspection.
- CPU, RSS memory, thread count, uptime and disk I/O history.
- Persistent process history is keyed by PID plus process creation time to avoid mixing reused PIDs.
- Guarded process termination revalidates process identity and rejects protected or other-user processes.

> ⚠️ **Process control is intentionally restricted.** NEXUS never automatically terminates a process because a threshold or alert was triggered.

### 🌐 Network intelligence
- Per-interface throughput, packet rates, link state, speed, MTU, duplex, errors and drops.
- Bounded live TCP/UDP socket inventory with process ownership.
- Optional Linux NetHogs per-process byte-rate attribution.
- User-configured, opt-in DNS/TCP quality checks and on-demand connectivity diagnostics.

> ℹ️ Socket ownership is not bandwidth attribution. Windows ETW/WFP and macOS per-process byte accounting are not implemented in this release; unsupported providers report their limitation.

### 📈 Advanced analytics
- Historical CPU, memory, disk and network summaries across supported time windows.
- Average, minimum, maximum, median, p95, distributions, trend buckets and equal-period comparisons.
- Independent evidence scorecards. Missing samples are not interpolated, and NEXUS does not invent a combined health score.

### 🕵️ Bottleneck Detective and incident forensics
- Sustained resource-pressure analysis, process memory-growth observations and adaptive median/MAD anomaly detection.
- Best-effort correlation with local OS crash/hang indicators.
- Bounded manual and automatic incident captures, evidence inspection and JSON export.

> ⚠️ Correlation is not causation. Memory growth is not proof of a leak, and an anomaly is not proof of malware or hardware failure.

### 🤖 NEXUS Sentinel — local assistant
- Optional Ollama integration at `127.0.0.1:11434`; default model: `qwen3.5:4b`.
- Lists models already installed locally; it does not download models or use cloud inference.
- Optional diagnostic context is sent only to the local Ollama service.
- A deterministic built-in diagnostic guide is available when Ollama or a selected model is unavailable.

### 🔔 Alerts, workspace and desktop
- Configurable resource thresholds, consecutive-sample rules, cooldowns and hysteresis.
- Custom dashboard profiles, widget ordering and sizing, settings import/export and local retention controls.
- Windows-first PyWebView desktop shell with tray integration, opt-in sign-in startup, PyInstaller packaging and an Inno Setup recipe.

## 🧰 Technology

| Layer | Technology |
| --- | --- |
| Frontend | HTML5, CSS and vanilla JavaScript |
| Local API | Python 3.10+, FastAPI, Uvicorn |
| OS telemetry | psutil and optional platform/vendor providers |
| Historical storage | SQLite on the local machine |
| Optional GPU telemetry | AMD ADLX on supported Windows drivers, NVIDIA NVML, supported Linux AMD SMI, Linux DRM/sysfs and Windows LibreHardwareMonitor |
| Desktop packaging | PyWebView, PyInstaller and Inno Setup |
| Tests and CI | pytest, FastAPI TestClient, GitHub Actions |

## 🚀 Quick start

### 1. Clone and create an environment

```bash
git clone https://github.com/ItsWanheda/nexus-dash.git
cd nexus-dash
python -m venv .venv
```

Activate it:

**Windows PowerShell**
```powershell
.\.venv\Scripts\Activate.ps1
```

**Linux / macOS**
```bash
source .venv/bin/activate
```

### 2. Install runtime dependencies

```bash
python -m pip install -r requirements.txt
```

### 3. Start the local API

From the repository root:

```bash
python server.py
```

The API listens on **127.0.0.1:8000**. Health check: <http://127.0.0.1:8000/api/health>.

### 4. Serve the dashboard

Open a second terminal in the repository root:

```bash
python -m http.server 5500 --bind 127.0.0.1
```

Then open <http://127.0.0.1:5500>.

> ⚠️ Do not open `index.html` through a `file://` URL. Serve it from an allowed local origin. Keep both services on loopback.

## 🧩 Optional integrations

### Hardware providers

```bash
python -m pip install -r requirements-hardware.txt
```

This installs optional NVIDIA NVML, Windows WMI, AMD ADLX on compatible 64-bit Windows systems, and Linux AMD SMI bindings. GPU inventory is also read from native OS interfaces (Windows DirectX DXGI + WMI/device registry, Linux PCI sysfs and macOS system_profiler). On Windows, DXGI reports the adapter model, PCI/subsystem identity, revision and dedicated/shared memory capacity; Windows GPU Engine and AdapterMemory counters provide per-adapter utilisation and memory use where the graphics driver exposes them. Live sensor values remain dependent on each device's driver and supported sensor interfaces. Windows LibreHardwareMonitor can provide additional readings across supported GPU vendors; Linux DRM/sysfs exposes generic counters where the active driver publishes them. AMD SMI requires a compatible AMDGPU/ROCm stack.

### SMART storage health

Install the operating-system **smartmontools** package so `smartctl` is available. NEXUS performs bounded, read-only health queries. Device/controller support and permissions vary.

> 💡 Installing the Python hardware extras does not install the external `smartctl` executable.

### NEXUS Sentinel / Ollama

Install Ollama separately, then install the model you want to use:

```bash
ollama pull qwen3.5:4b
```

Start the Ollama service if it is not already running, then open NEXUS Sentinel. Smaller qwen3.5 variants may suit systems with less memory. NEXUS only lists installed models and never downloads one automatically.

### Desktop application and installers

NEXUS-DASH uses a native desktop window with a local-only API and UI. The app selects the platform's supported WebView backend:
- **Windows:** WebView2 / Edge Chromium; the Windows setup executable is built with Inno Setup.
- **Debian / Ubuntu:** GTK 3 + WebKitGTK; use the setup script below to install system dependencies, create an isolated Python environment, and add an application launcher.
- **macOS:** Cocoa / WKWebView; use the setup script below to install the app into your user Library and create a launcher.

#### Windows

For a source checkout:

```powershell
python -m pip install -r requirements-desktop.txt
python desktop_app.py
```

Build the Windows x64 application and installer from PowerShell:

```powershell
./scripts/build_windows.ps1
```

The installer is per-user by default. WebView2 Runtime must be available on the machine.

#### Debian / Ubuntu

Clone the repository, then run:

```bash
git clone https://github.com/ItsWanheda/nexus-dash.git
cd nexus-dash
bash scripts/setup_linux.sh
```

The setup installs GTK/WebKitGTK system packages, creates a user-local virtual environment, installs desktop dependencies, and registers a desktop launcher. It supports Debian/Ubuntu apt-based systems with WebKitGTK 4.1 or 4.0 packages.

#### macOS

Install Python 3.10 or newer, clone the repository, then run:

```bash
git clone https://github.com/ItsWanheda/nexus-dash.git
cd nexus-dash
bash scripts/setup_macos.sh
```

The setup creates a user-local environment and installs a launcher at `~/Applications/NEXUS-DASH.command`. Start it from Terminal with `nexus-dash` or double-click the command file.

> 🔒 The desktop app keeps its API and static UI bound to `127.0.0.1`. It does not expose a LAN listener. Linux and macOS setup scripts install per-user files and do not require running NEXUS-DASH as root.

## 🔌 API overview

Interactive OpenAPI/Swagger endpoints are intentionally disabled. The main local API routes are:

| Method | Endpoint | Purpose |
| --- | --- | --- |
| GET | `/api/health` | API health and version |
| GET | `/api/stats` | Current system snapshot |
| GET | `/api/hardware` | Hardware identity and available sensors |
| GET | `/api/storage` | Drive capacity, I/O and optional SMART |
| GET | `/api/network` | Interface counters and rates |
| GET | `/api/network/connections` | Bounded live TCP/UDP socket inventory |
| GET | `/api/network/history` | Stored interface history |
| GET | `/api/network/diagnostics` | User-triggered DNS/TCP diagnostics |
| GET | `/api/network/processes` | Per-process network rates/capability status |
| GET | `/api/network/quality` | Configured DNS/TCP quality history |
| GET | `/api/analytics` | Historical statistics and scorecards |
| GET | `/api/anomalies` | Adaptive anomaly analysis |
| GET | `/api/incidents` and `/api/incidents/{id}` | Incident list and evidence |
| POST | `/api/incidents/capture` | Manual incident capture |
| GET | `/api/assistant/status` | Local Ollama status and installed models |
| POST | `/api/assistant/chat` | Local assistant request |
| GET | `/api/processes` and `/api/processes/{pid}` | Process list and identity-checked inspection |
| GET | `/api/process-history` | Persistent process performance history |
| GET | `/api/process-compare` | Compare two process identities |
| GET | `/api/process-tree` | Bounded parent/child process tree |
| GET | `/api/timeline` | Local investigation timeline |
| POST | `/api/timeline/markers` | Add a user-authored marker |
| GET/PUT | `/api/settings` | Read/update local settings |
| GET | `/api/diagnostics` and `/api/diagnostics/report` | Evidence-based findings and report |
| GET | `/api/history` and `/api/history/export` | Resource history and JSON/CSV export |
| DELETE | `/api/history` | Clear local history |
| POST | `/api/process/kill` | Request guarded process termination |
| POST | `/api/terminal` | Execute an allowlisted diagnostic command |

All endpoints remain subject to loopback-client, trusted-host and browser-origin checks.

## 🗄️ Local data, retention and privacy

Default database location:

- **Windows:** `%USERPROFILE%\.nexus-dash\telemetry.sqlite3`
- **Linux/macOS:** `~/.nexus-dash/telemetry.sqlite3`

Set `NEXUS_DATA_DIR` before starting the API to choose another local directory.

The aggregate resource table stores numeric system metrics and timestamps. Optional feature tables have separate data:
- Process history: process name, PID, creation time and CPU/RSS/thread/disk metrics.
- Process-network history: process name, PID and measured byte rates when enabled.
- Network-quality history: the explicitly configured target label/port and DNS/TCP measurements.
- Incident captures: bounded evidence assembled from recent local records.

The new history features do not store executable paths, command lines, usernames, packet payloads, MAC addresses or socket IP endpoints. A user-entered network target label may itself contain a hostname or IP address.

Retention is configurable (1, 7 or 30 days) and storage is bounded. Effective sampling cadence may increase for longer retention to remain within the configured sample cap. Review incident and session exports before sharing them.

Use **Settings → Clear History** to remove the local history tables and incident captures. Browser-local alert preferences are separate and can be removed by clearing site data for the local UI origin.

## 📖 Documentation

Start with the [documentation index](docs/README.md).

| Guide | Covers |
| --- | --- |
| [Diagnostics and forensics](docs/guides/DIAGNOSTICS.md) | Thresholds, adaptive detection, incident evidence and OS event sources |
| [Flight Recorder](docs/guides/FLIGHT_RECORDER.md) | SQLite history, sampling, retention, exports and troubleshooting |
| [Hardware and storage](docs/guides/HARDWARE_STORAGE.md) | GPU inventory, sensor providers, SMART and platform limitations |
| [Terminal and Sentinel](docs/guides/TERMINAL_SENTINEL.md) | Diagnostic command grammar and local assistant safety |
| [Project structure](docs/architecture/PROJECT_STRUCTURE.md) | Repository layout and module responsibilities |
| [Security model](docs/architecture/SECURITY_MODEL.md) | Trust boundaries, process safeguards and privacy model |
| [Security policy](SECURITY.md) | Vulnerability reporting and supported security scope |
| [Contributing](CONTRIBUTING.md) | Setup, engineering rules and validation |

## 🗂️ Project layout

```text
nexus-dash/
├── nexus_dash/
│   ├── api/
│   │   └── server.py          # FastAPI app, middleware and route composition
│   ├── desktop/
│   │   └── app.py             # Windows PyWebView and system-tray shell
│   └── services/
│       ├── telemetry_store.py # SQLite history, incidents and retention
│       ├── diagnostics.py     # Evidence-based diagnostics and OS events
│       ├── hardware*.py       # Hardware collection and optional providers
│       ├── storage_metrics.py # Disk activity and optional SMART queries
│       ├── process_*.py       # Process intelligence and network attribution
│       ├── network_*.py       # Interface, connectivity and quality metrics
│       ├── analytics.py       # Historical analytics and scorecards
│       ├── anomaly_detection.py
│       ├── terminal_service.py# Restricted diagnostic command grammar
│       ├── local_agent.py     # Local Ollama assistant integration
│       └── settings_store.py  # Validated local settings
├── src/                      # Browser assets (JS, CSS and images)
├── tests/                    # Backend and API tests
├── docs/                     # Architecture references and feature guides
├── installer/                # Inno Setup installer recipe
├── scripts/                  # Build and maintenance scripts
├── server.py                 # Backward-compatible ASGI/CLI entry point
├── desktop_app.py            # Backward-compatible desktop launcher
├── index.html                # Dashboard document
├── NEXUS-DASH.spec           # PyInstaller build configuration
└── requirements*.txt         # Runtime, development and optional dependencies
```

> 🧭 **Compatibility note:** application code now lives in the `nexus_dash` package. The root `server.py` and `desktop_app.py` files remain as thin compatibility launchers, preserving `python server.py`, `python desktop_app.py`, and the `server:app` ASGI target.

## 🧪 Development and validation

Install development dependencies:

```bash
python -m pip install -r requirements-dev.txt
```

Run the full test suite:

```bash
python -m pytest -q
```

Check frontend syntax:

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

Compile backend and test sources:

```bash
python -m compileall -q nexus_dash tests server.py desktop_app.py
```

CI checks Python 3.10–3.13, frontend JavaScript syntax, Python compilation and pytest. Physical hardware sensor coverage and interactive Windows window/tray behaviour still require manual testing on representative machines.

## 🔐 Security at a glance

- The API is local-only and binds to `127.0.0.1`; do not expose port 8000 to a LAN or the internet.
- Trusted-host, loopback-client and browser-origin checks are enforced; credentialed CORS is disabled.
- The diagnostic terminal is an allowlisted diagnostics interface, **not** CMD, PowerShell or Bash.
- Process termination is guarded and identity-checked; alerts never trigger automatic termination.
- Fan monitoring is read-only.
- Sentinel uses local Ollama only and has no command-execution tools or cloud fallback.
- Telemetry and incident data remain local unless the user explicitly exports or shares it.

Read [SECURITY.md](SECURITY.md) before changing networking, process control, persistence or assistant context behaviour.

## 📄 License

MIT. See [LICENSE](LICENSE).
