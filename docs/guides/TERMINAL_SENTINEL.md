# 🖥️ NEXUS Diagnostic Terminal and Sentinel

This guide covers two local troubleshooting features: the allowlisted Diagnostic Terminal and the optional Ollama-backed NEXUS Sentinel assistant.

## 📚 On this page

- [Diagnostic Terminal](#-diagnostic-terminal)
- [Command reference](#-command-reference)
- [Hardware capability notes](#-hardware-capability-notes)
- [NEXUS Sentinel](#-nexus-sentinel)
- [Optional machine context](#-optional-machine-context)
- [Safety model](#-safety-model)

## 🧰 Diagnostic Terminal

The terminal workspace looks CMD-like, but it is deliberately **not a general shell**. It parses an explicit command grammar and calls local read-only diagnostic functions.

It does not start cmd.exe, PowerShell, Bash or arbitrary executables. Shell operators, command chaining, script execution and destructive commands are rejected.

### Command reference

| Command | What it does |
| --- | --- |
| `help` | Show the command reference |
| `status` / `sysinfo` | Show host, OS, architecture, CPU, RAM and uptime |
| `cpu` | Sample CPU utilisation, core counts and exposed frequency |
| `memory` | Show physical memory and swap/pagefile use |
| `disk` / `drives` | List accessible mounted volumes and capacity |
| `processes [limit] [sort=cpu\|memory\|name]` | List accessible processes, bounded to 50 rows |
| `process <pid>` | Inspect parent, state, CPU, RSS/VMS, threads, start time, uptime and disk I/O counters |
| `network` | Show aggregate sent/received counters and live socket count |
| `interfaces` | Show per-interface link state, speed and byte counters |
| `connections [limit]` | Show live TCP/UDP process ownership and ports; IP addresses are hidden |
| `dns <hostname>` | Resolve a hostname and measure resolver time |
| `tcp <hostname> <port>` | Perform one bounded TCP handshake check; no application payload is sent |
| `ping <hostname> [count]` | Use the OS ping utility for 1–4 ICMP probes, with a five-second timeout |
| `hardware` | Show system/baseboard identity and detected GPU inventory |
| `date`, `hostname`, `whoami`, `uptime` | Show local host/session information |
| `python --version` | Show the Python runtime version |

### Examples

```text
status
processes 15 sort=memory
process 1234
interfaces
dns example.com
tcp example.com 443
ping example.com 3
hardware
```

Commands run as the current local OS user. Permissions can limit process, socket, hardware and sensor visibility. The terminal caps output and arguments. Network probes contact only hosts entered by the user.

> ⚠️ Keep the API bound to loopback. Do not treat the terminal UI as a remote administration interface.

## 🧩 Hardware capability notes

GPU inventory, motherboard identity and sensor access are separate capabilities:
- The OS or PCI inventory can identify an older GPU even if no driver exposes current load/temperature.
- Board model strings come from SMBIOS/DMI or WMI. OEM firmware may publish generic or blank values; NEXUS does not guess.
- Linux fan readings require a kernel hwmon driver to publish fan tachometers.
- Windows expanded sensors require LibreHardwareMonitor to be running and publishing its WMI namespace.

NEXUS reads sensors; it does not control fan curves.

## 🤖 NEXUS Sentinel

NEXUS Sentinel is an optional local troubleshooting assistant. Its default model is `qwen3.5:4b`, served by Ollama at `127.0.0.1:11434`.

1. Install Ollama separately.
2. Pull the model once:

   ```bash
   ollama pull qwen3.5:4b
   ```

3. Start the Ollama service if it is not already running.
4. Open NEXUS Sentinel and select an installed model.

NEXUS lists models already installed in Ollama. It does not download models, call remote inference APIs or silently fall back to a cloud provider. Smaller qwen3.5 variants are alternatives for systems with less memory.

## 🧾 Optional machine context

The **Include current NEXUS evidence** toggle controls whether a chat request contains recent system metrics, adaptive findings, recent sampled process summaries, network-quality samples and recent incident metadata.

The context is sent to the local Ollama process, not a hosted inference endpoint.

> 🔏 **Privacy tip:** review the selected context before discussing sensitive machine activity. Local does not mean that every process name or target label is non-sensitive.

## 🛡️ Safety model

Sentinel has no command tools or process-control tools. It cannot run terminal commands, terminate processes, change settings, alter fan control or restart services. It can explain what a recommended diagnostic command does and ask the user to run it.

Diagnostic output and event text are untrusted evidence. The assistant should distinguish observations from hypotheses and explain when data is missing.

When Ollama is unavailable or the selected model is not installed, NEXUS shows its deterministic built-in diagnostic guide. This fallback is not an LLM and does not download or install a model.
