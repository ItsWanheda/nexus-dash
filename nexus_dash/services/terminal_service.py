"""Safe, useful, CMD-like local diagnostics without a general shell."""
from __future__ import annotations

import getpass
import os
import platform
import shlex
import shutil
import socket
import subprocess
import time
from typing import Any

import psutil

from .network_metrics import collect_connections, diagnose_tcp_connectivity, _normalize_host

MAX_OUTPUT = 12_000
MAX_PROCESSES = 50


def _bytes(value: int | float) -> str:
    amount = max(0.0, float(value))
    for unit in ("B", "KiB", "MiB", "GiB", "TiB"):
        if amount < 1024 or unit == "TiB":
            return f"{amount:.1f} {unit}"
        amount /= 1024
    return f"{amount:.1f} TiB"


def _duration(seconds: float) -> str:
    total = max(0, int(seconds))
    days, rest = divmod(total, 86400)
    hours, rest = divmod(rest, 3600)
    minutes, seconds = divmod(rest, 60)
    parts = []
    if days:
        parts.append(f"{days}d")
    if hours or days:
        parts.append(f"{hours}h")
    parts.extend((f"{minutes}m", f"{seconds}s"))
    return " ".join(parts)


def _result(stdout: str = "", *, stderr: str = "", returncode: int = 0) -> dict[str, Any]:
    return {"stdout": str(stdout)[:MAX_OUTPUT], "stderr": str(stderr)[:2000], "returncode": int(returncode)}


def _cpu() -> str:
    frequency = psutil.cpu_freq()
    return (
        f"Utilisation: {psutil.cpu_percent(interval=0.1):.1f}%\n"
        f"Logical cores: {psutil.cpu_count(logical=True) or 0}\n"
        f"Physical cores: {psutil.cpu_count(logical=False) or 0}\n"
        f"Frequency: {getattr(frequency, 'current', None) or 'Unavailable'} MHz"
    )


def _memory() -> str:
    mem = psutil.virtual_memory()
    swap = psutil.swap_memory()
    return (
        f"Physical memory: {_bytes(mem.used)} / {_bytes(mem.total)} ({mem.percent:.1f}%)\n"
        f"Available: {_bytes(mem.available)}\n"
        f"Swap/pagefile: {_bytes(swap.used)} / {_bytes(swap.total)} ({swap.percent:.1f}%)"
    )


def _processes(limit: int = 20, sort: str = "cpu") -> str:
    rows = []
    for process in psutil.process_iter(["pid", "name", "memory_info", "status"]):
        try:
            info = process.info
            memory = info.get("memory_info")
            rows.append({
                "pid": int(info["pid"]),
                "name": str(info.get("name") or "Unknown")[:80],
                "cpu": max(0.0, float(process.cpu_percent(interval=None) or 0)),
                "rss": int(memory.rss) if memory else 0,
                "status": str(info.get("status") or "unknown"),
            })
        except (psutil.Error, OSError, TypeError, ValueError):
            continue
    key = {"cpu": lambda row: row["cpu"], "memory": lambda row: row["rss"], "name": lambda row: row["name"].casefold()}[sort]
    rows.sort(key=key, reverse=(sort != "name"))
    lines = [f"{'PID':>8}  {'CPU %':>7}  {'RAM':>10}  {'STATE':<12}  PROCESS"]
    for row in rows[:limit]:
        lines.append(f"{row['pid']:>8}  {row['cpu']:>7.1f}  {_bytes(row['rss']):>10}  {row['status']:<12}  {row['name']}")
    return "\n".join(lines) + f"\n\nShowing {min(limit, len(rows))} of {len(rows)} accessible processes."


def _drives() -> str:
    lines = ["DEVICE / MOUNT                       FILESYSTEM      USED / TOTAL        FREE"]
    try:
        partitions = psutil.disk_partitions(all=False)
    except (psutil.Error, OSError):
        partitions = []
    seen = set()
    for part in partitions[:64]:
        mount = str(part.mountpoint)
        if mount in seen:
            continue
        seen.add(mount)
        try:
            usage = psutil.disk_usage(mount)
            lines.append(f"{mount[:36]:<36} {str(part.fstype)[:12]:<12} {_bytes(usage.used):>10} / {_bytes(usage.total):<10} {_bytes(usage.free):>10}")
        except (psutil.Error, OSError):
            lines.append(f"{mount[:36]:<36} unavailable")
    return "\n".join(lines) if len(lines) > 1 else "No accessible mounted volumes were reported."


def _interfaces() -> str:
    try:
        counters = psutil.net_io_counters(pernic=True) or {}
        states = psutil.net_if_stats() or {}
    except (psutil.Error, OSError):
        return "Network interface counters are unavailable."
    lines = ["INTERFACE                         STATE   SPEED       SENT             RECEIVED"]
    for name, counter in list(counters.items())[:64]:
        state = states.get(name)
        status = "UP" if state and state.isup else "DOWN" if state else "UNKNOWN"
        speed = f"{state.speed} Mbps" if state and state.speed > 0 else "—"
        lines.append(f"{name[:32]:<34} {status:<7} {speed:<11} {_bytes(counter.bytes_sent):>12}  {_bytes(counter.bytes_recv):>12}")
    return "\n".join(lines) if len(lines) > 1 else "No network interfaces were reported."


def _network() -> str:
    counters = psutil.net_io_counters()
    connections = collect_connections(limit=10, include_addresses=False)
    return (
        f"Aggregate sent: {_bytes(counters.bytes_sent)}\n"
        f"Aggregate received: {_bytes(counters.bytes_recv)}\n"
        f"Live sockets: {connections.get('count', 0)} ({connections.get('status', 'Unavailable')})"
    )


def _connections(limit: int) -> str:
    snapshot = collect_connections(limit=limit, include_addresses=False)
    lines = [f"Socket inventory: {snapshot['status']} · {snapshot['count']} total",
             "PID      PROCESS                         PROTO  STATE          LOCAL → REMOTE PORT"]
    for row in snapshot.get("connections", []):
        lines.append(f"{str(row.get('pid') or '—'):<8} {str(row.get('process') or 'Unknown')[:30]:<30} {row.get('protocol', '?'):<6} {row.get('state', '?'):<14} {str(row.get('local_port') or '—')} → {str(row.get('remote_port') or '—')}")
    if snapshot.get("reason"):
        lines.append(snapshot["reason"])
    lines.append("IP addresses are hidden in this terminal view.")
    return "\n".join(lines)


def _process_detail(pid: int) -> str:
    process = psutil.Process(pid)
    with process.oneshot():
        memory = process.memory_info()
        created = process.create_time()
        try:
            io = process.io_counters()
        except (psutil.Error, OSError, AttributeError):
            io = None
        return "\n".join((
            f"Name: {process.name()}",
            f"PID / parent: {process.pid} / {process.ppid()}",
            f"Status: {process.status()}",
            f"CPU: {process.cpu_percent(interval=None):.1f}%",
            f"RSS / VMS: {_bytes(memory.rss)} / {_bytes(memory.vms)}",
            f"Threads: {process.num_threads()}",
            f"Started: {time.strftime('%Y-%m-%d %H:%M:%S', time.localtime(created))}",
            f"Uptime: {_duration(time.time() - created)}",
            f"Disk read/write: {_bytes(io.read_bytes)} / {_bytes(io.write_bytes)}" if io else "Disk I/O: unavailable",
        ))


def _dns(host: str) -> str:
    target = _normalize_host(host)
    started = time.perf_counter()
    try:
        results = socket.getaddrinfo(target, None, type=socket.SOCK_STREAM)
    except OSError as exc:
        return f"DNS lookup failed for {target}: {exc}"
    elapsed = (time.perf_counter() - started) * 1000
    addresses = sorted({row[4][0] for row in results})
    return f"Host: {target}\nResolved addresses: {', '.join(addresses[:16])}\nLookup time: {elapsed:.1f} ms"


def execute_terminal_command(command: str) -> dict[str, Any]:
    """Parse an explicit command grammar. No shell, chaining, or arbitrary executable."""
    value = str(command or "").strip()
    if not value or len(value) > 256:
        return _result(stderr="Enter a command between 1 and 256 characters.", returncode=2)
    if any(char in value for char in (";", "|", "&", ">", "<", "$", chr(96), "\x00", "\n", "\r")):
        return _result(stderr="Shell operators and multi-line commands are not supported.", returncode=2)
    try:
        parts = shlex.split(value, posix=True)
    except ValueError as exc:
        return _result(stderr=f"Command syntax error: {exc}", returncode=2)
    if not parts:
        return _result(stderr="Enter a command.", returncode=2)
    name, args = parts[0].casefold(), parts[1:]
    try:
        if name in {"help", "?"} and not args:
            return _result(
                "NEXUS Diagnostic Terminal — safe local commands\n"
                "  help | ?                         Command reference\n"
                "  status | sysinfo                 Host, CPU, memory and uptime\n"
                "  cpu | memory                     Live CPU and RAM readings\n"
                "  disk | drives                    Mounted volumes and capacity\n"
                "  processes [limit] [sort=cpu|memory|name]\n"
                "  process <pid>                    Inspect one process\n"
                "  network | interfaces             Aggregate / per-interface totals\n"
                "  connections [limit]              Live TCP/UDP sockets\n"
                "  dns <hostname>                   Resolve a host and time lookup\n"
                "  tcp <hostname> <port>            Test a TCP handshake\n"
                "  ping <hostname> [count]          Send 1–4 ICMP probes\n"
                "  hardware                         Detected board and GPU inventory\n"
                "  python --version                 Python runtime\n"
                "  date | hostname | whoami | uptime\n"
                "Examples: processes 15 sort=memory · process 1234 · tcp example.com 443\n"
                "NEXUS does not execute arbitrary shell commands. No unrestricted shell, command chaining, or destructive commands are supported."
            )
        if name in {"date", "time"} and not args:
            return _result(time.strftime("%Y-%m-%d %H:%M:%S %Z", time.localtime()))
        if name == "hostname" and not args:
            return _result(platform.node() or "Unknown")
        if name == "whoami" and not args:
            return _result(getpass.getuser())
        if name == "uptime" and not args:
            return _result(_duration(time.time() - psutil.boot_time()))
        if name in {"platform", "sysinfo", "status"} and not args:
            return _result(f"Host: {platform.node() or 'Unknown'}\nOS: {platform.system()} {platform.release()}\nArchitecture: {platform.machine()}\nPython: {platform.python_version()}\nCPU: {psutil.cpu_percent(interval=0.1):.1f}% · RAM: {psutil.virtual_memory().percent:.1f}%\nUptime: {_duration(time.time() - psutil.boot_time())}")
        if name == "cpu" and not args:
            return _result(_cpu())
        if name == "memory" and not args:
            return _result(_memory())
        if name in {"disk", "drives"} and not args:
            return _result(_drives())
        if name in {"network", "interfaces"} and not args:
            return _result(_network() if name == "network" else _interfaces())
        if name in {"processes", "ps", "top"}:
            limit, sort = 20, "cpu"
            for arg in args:
                if arg.isdigit():
                    limit = max(1, min(int(arg), MAX_PROCESSES))
                elif arg.startswith("sort=") and arg[5:].casefold() in {"cpu", "memory", "name"}:
                    sort = arg[5:].casefold()
                else:
                    raise ValueError("Usage: processes [limit] [sort=cpu|memory|name]")
            return _result(_processes(limit, sort))
        if name == "process" and len(args) == 1 and args[0].isdigit() and int(args[0]) > 0:
            return _result(_process_detail(int(args[0])))
        if name in {"connections", "netstat"}:
            if len(args) > 1 or (args and not args[0].isdigit()):
                raise ValueError("Usage: connections [limit]")
            return _result(_connections(max(1, min(int(args[0]), 100)) if args else 50))
        if name == "dns" and len(args) == 1:
            return _result(_dns(args[0]))
        if name == "tcp" and len(args) == 2 and args[1].isdigit():
            return _result(json.dumps(diagnose_tcp_connectivity(args[0], int(args[1]), attempts=1), indent=2))
        if name == "ping" and 1 <= len(args) <= 2:
            host = _normalize_host(args[0])
            count = int(args[1]) if len(args) == 2 and args[1].isdigit() else 1
            if count < 1 or count > 4 or (len(args) == 2 and not args[1].isdigit()):
                raise ValueError("Usage: ping <hostname> [count 1–4]")
            executable = shutil.which("ping")
            if not executable:
                raise ValueError("The OS ping utility is not installed or not on PATH.")
            flags = ["-n", str(count)] if os.name == "nt" else ["-c", str(count)]
            completed = subprocess.run([executable, *flags, host], capture_output=True, text=True,
                                        timeout=5, check=False, shell=False)
            return _result(completed.stdout or completed.stderr, returncode=completed.returncode)
        if name == "python" and args == ["--version"]:
            return _result(f"Python {platform.python_version()}")
        if name == "hardware" and not args:
            try:
                from .hardware import collect_hardware
                payload = collect_hardware()
                board = payload.get("motherboard", {}).get("identity", {})
                system = payload.get("system", {})
                cards = payload.get("gpu", {}).get("devices", [])
                lines = [f"System: {system.get('manufacturer') or 'Unknown'} {system.get('model') or 'Unknown'}",
                         f"Motherboard: {board.get('manufacturer') or 'Unknown'} {board.get('model') or 'Unknown'}"]
                lines.extend(f"GPU {card.get('index', '?')}: {card.get('name', 'Unknown')} [{card.get('vendor', 'Unknown')}]"
                             for card in cards)
                return _result("\n".join(lines))
            except Exception as exc:
                return _result("Hardware inventory unavailable.", stderr=str(exc), returncode=1)
    except psutil.NoSuchProcess:
        return _result(stderr="That process is no longer running.", returncode=1)
    except psutil.AccessDenied:
        return _result(stderr="The operating system denied access.", returncode=1)
    except (ValueError, OSError, subprocess.TimeoutExpired) as exc:
        return _result(stderr=str(exc)[:1000], returncode=1)
    return _result(stderr="Command not allowed or invalid. Type 'help' for supported commands.", returncode=2)
