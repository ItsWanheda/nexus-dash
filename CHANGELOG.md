# Changelog

All notable changes to NEXUS-DASH are recorded here.

## [Unreleased]

### Security
- Removed arbitrary shell execution from the terminal; only exact read-only diagnostics are accepted.
- Added loopback-client enforcement, browser-origin allowlisting, restrictive CORS, and trusted-host validation.
- Restricted process termination to current-user processes and protected PIDs; added bounded request validation and wait behaviour.
- Disabled automatically exposed OpenAPI/Swagger endpoints and stopped returning raw internal exceptions.

### Added
- Added API health endpoint and CPU, RAM, disk, network byte-counter, uptime, and system profile telemetry.
- Added optional NVIDIA NVML memory metrics with an explicit unavailable state when drivers or NVML are absent.
- Added API regression tests and a GitHub Actions CI workflow for Python 3.10–3.13.
- Added process search, session-only CPU/RAM charts, theme preference, session logs, and accessible responsive navigation.

### Changed
- Reworked the interface while retaining the black/neon-green cyberpunk visual identity.
- Replaced fabricated activity/chart values with real samples and browser-session events.
- Updated setup instructions, runtime dependencies, and the security policy to document the local-only trust boundary.

## [1.1.0] - 2026-06-14
- Added the first psutil-backed real hardware monitoring API, process manager, and terminal view.

## [1.0.0] - 2026-06-13
- Initial cyberpunk dashboard UI and responsive layout.
