# NEXUS // CORE DASHBOARD

A local-first, cyberpunk-inspired system monitoring dashboard built with **vanilla HTML/CSS/JavaScript** and a **Python FastAPI + psutil backend**. The UI has no JavaScript framework or package-manager build step.

> **Security model:** NEXUS is designed for local use. The API binds to loopback, checks browser origins, disables credentialed CORS, and provides a read-only diagnostic console instead of arbitrary shell execution.

## Features

- **Live host telemetry:** CPU utilisation and core counts, RAM, disk, network transfer totals, and estimated upload/download rates.
- **Session charts:** CPU and memory samples collected while the page is open; no fabricated historical dataset.
- **Process manager:** filter and inspect process snapshots. Termination is limited to current-user processes and protected PIDs are blocked.
- **Read-only diagnostic console:** exact allowlisted commands such as `help`, `status`, `cpu`, `memory`, `uptime`, `hostname`, `platform`, `whoami`, `date`, and `python --version`. User input is never passed to a shell.
- **System profile and session logs:** live OS/runtime information and truthful browser-session events.
- **Responsive UI:** mobile navigation, focus states, dark/light theme preference, and reduced-motion support.
- **Secure defaults and tests:** loopback-only startup, origin checks, bounded inputs, structured API errors, and CI tests.

GPU memory metrics are optional and currently use NVIDIA NVML when the optional `nvidia-ml-py` package and compatible NVIDIA drivers are present. On other hardware, GPU telemetry is marked unavailable rather than displaying invented measurements.

## Stack

| Component | Technology |
| --- | --- |
| Frontend | HTML5, CSS Grid/Flexbox, vanilla JavaScript |
| API | Python 3.10+, FastAPI, Uvicorn |
| Host metrics | psutil |
| Optional GPU adapter | `nvidia-ml-py` (NVIDIA only) |
| Tests | pytest, FastAPI TestClient |

## Setup

### 1. Clone and install

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

Install runtime dependencies:

```bash
python -m pip install -r requirements.txt
```

### 2. Start the API

In terminal 1, run:

```bash
python server.py
```

The API listens on **127.0.0.1:8000**. Verify it at <http://127.0.0.1:8000/api/health>.

### 3. Serve the frontend

In terminal 2, from the repository root:

```bash
python -m http.server 5500 --bind 127.0.0.1
```

Open <http://127.0.0.1:5500>. Do not open `index.html` through a `file://` URL; serve it from the documented local origin so the API origin policy can apply.

### 4. Optional NVIDIA telemetry

For a compatible NVIDIA driver, install:

```bash
python -m pip install nvidia-ml-py
```

The rest of the dashboard works without this optional package.

## API

| Method | Endpoint | Description |
| --- | --- | --- |
| GET | `/api/health` | Local API health |
| GET | `/api/stats` | CPU, RAM, disk, network, GPU and host data |
| GET | `/api/processes?limit=100` | Process snapshot (limit 1–200) |
| POST | `/api/process/kill` | Terminate an eligible process; JSON body: `{"pid": 1234}` |
| POST | `/api/terminal` | Run one allowlisted diagnostic; JSON body: `{"command": "status"}` |

Interactive OpenAPI/Swagger documentation is disabled because this API is intended for local dashboard use rather than public service integration.

## Tests

```bash
python -m pip install -r requirements-dev.txt
python -m pytest -q
```

The GitHub Actions workflow compiles the Python sources and runs the tests on Python 3.10–3.13.

## Security notes

- **Do not expose port 8000 publicly.** Do not bind the API to `0.0.0.0`, add a port-forward, or put it behind a public reverse proxy.
- The backend checks the client loopback address and rejects unapproved browser `Origin` values. Allowed frontend origins are limited to localhost ports 5500 and 5501; the API's own localhost origin is also allowed.
- The terminal accepts exact built-in diagnostic commands only. It does not use `subprocess`, `shell=True`, `eval`, or arbitrary command execution.
- Process termination can cause data loss. Confirm the target process and any unsaved work. Protected PIDs and processes not owned by the current user are rejected; operating-system permissions still apply.
- Run the app as a standard user rather than an administrator/root account for routine monitoring.
- This is **not** an authentication system or a multi-user remote monitoring service. Read [SECURITY.md](SECURITY.md) before changing its networking model.

## Project layout

```text
nexus-dash/
├── .github/workflows/ci.yml
├── src/static/app.js
├── src/style/styles.css
├── tests/test_server.py
├── index.html
├── server.py
├── requirements.txt
├── requirements-dev.txt
├── SECURITY.md
├── CHANGELOG.md
└── README.md
```

## Roadmap

- Add opt-in local persistence for user-selected telemetry history.
- Support platform-specific GPU adapters without reporting unsupported metrics as real data.
- Expand process-permission tests on Windows, Linux and macOS.
- Consider a local desktop packaging option after further security review.

## License

MIT. See [LICENSE](LICENSE).
