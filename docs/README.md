# 📚 NEXUS-DASH Documentation

Welcome to the NEXUS-DASH documentation hub. Start with the guide that matches the task you want to perform.

## 🚀 Getting started

- **Install and launch:** follow [Quick start in the main README](../README.md#-quick-start).
- **Understand the repository:** read [Project structure](architecture/PROJECT_STRUCTURE.md).
- **Understand the trust boundary:** read [Security model](architecture/SECURITY_MODEL.md) and the root [Security Policy](../SECURITY.md).

## 📖 Feature guides

| Guide | Best for |
| --- | --- |
| [Diagnostics and forensics](guides/DIAGNOSTICS.md) | Understanding thresholds, adaptive anomalies, incident captures and OS event sources |
| [System Flight Recorder](guides/FLIGHT_RECORDER.md) | Understanding SQLite sampling, retention, exports, alerts and clearing history |
| [Hardware and storage](guides/HARDWARE_STORAGE.md) | GPU inventory, sensors, platform support, disk I/O and SMART |
| [Diagnostic Terminal and Sentinel](guides/TERMINAL_SENTINEL.md) | Using safe diagnostic commands and the local assistant |

## 🧭 Architecture references

| Reference | Contents |
| --- | --- |
| [Project structure](architecture/PROJECT_STRUCTURE.md) | Directory map, module responsibilities and safe organization rules |
| [Security model](architecture/SECURITY_MODEL.md) | Loopback boundary, process safeguards, local data and optional integrations |

## 🧑‍💻 Contributor resources

- [Contributing guide](../CONTRIBUTING.md) — environment setup, engineering principles and validation.
- [Changelog](../CHANGELOG.md) — user-visible changes by release.
- [Security policy](../SECURITY.md) — vulnerability reporting and security scope.
- [Code of Conduct](../CODE_OF_CONDUCT.md) — community expectations.

> 💡 **Documentation rule:** when code behaviour, configuration, API routes, storage fields or supported platforms change, update the relevant guide and this index in the same pull request. Keep examples aligned with the implementation.
