"""Best-effort per-interface network telemetry and on-demand connectivity probes."""
from __future__ import annotations

import ipaddress
import re
import socket
import threading
import time
from collections import Counter
from queue import Queue, Empty
from typing import Any

import psutil


def _safe_delta(current: int | None, previous: int | None) -> int | None:
    if current is None or previous is None or current < previous:
        return None
    return current - previous


def _loopback_interface(name: str, addresses: list[Any]) -> bool:
    if name.casefold() in {"lo", "loopback"}:
        return True
    for address in addresses:
        candidate = str(getattr(address, "address", "") or "").split("%", 1)[0]
        try:
            if ipaddress.ip_address(candidate).is_loopback:
                return True
        except ValueError:
            continue
    return False


class NetworkSampler:
    """Samples interface counters and link state. Interface addresses are never collected."""

    def __init__(self) -> None:
        self._lock = threading.RLock()
        self._previous: dict[str, tuple[float, dict[str, int | None], bool | None]] = {}

    def collect(self) -> dict[str, Any]:
        sampled_epoch = time.time()
        now = time.monotonic()
        try:
            counters = psutil.net_io_counters(pernic=True, nowrap=True) or {}
        except (psutil.Error, OSError, NotImplementedError):
            counters = {}
        try:
            stats = psutil.net_if_stats()
        except (psutil.Error, OSError, NotImplementedError):
            stats = {}
        try:
            addresses = psutil.net_if_addrs()
        except (psutil.Error, OSError, NotImplementedError):
            addresses = {}

        interfaces: list[dict[str, Any]] = []
        transitions: list[dict[str, Any]] = []
        with self._lock:
            for name, item in counters.items():
                nic = stats.get(name)
                current: dict[str, int | None] = {}
                for output, attribute in (
                    ("bytes_sent", "bytes_sent"), ("bytes_recv", "bytes_recv"),
                    ("packets_sent", "packets_sent"), ("packets_recv", "packets_recv"),
                    ("errors_in", "errin"), ("errors_out", "errout"),
                    ("drops_in", "dropin"), ("drops_out", "dropout"),
                ):
                    value = getattr(item, attribute, None)
                    current[output] = max(0, int(value)) if value is not None else None

                is_up = bool(nic.isup) if nic is not None else None
                previous = self._previous.get(name)
                elapsed = max(0.001, now - previous[0]) if previous else None
                deltas: dict[str, int | None] = {}
                if previous:
                    for key in current:
                        deltas[key] = _safe_delta(current[key], previous[1].get(key))
                    if previous[2] is not None and is_up is not None and previous[2] != is_up:
                        transitions.append({
                            "name": name[:128], "is_up": is_up,
                            "kind": "interface-up" if is_up else "interface-down",
                        })
                else:
                    deltas = {key: None for key in current}

                def rate(key: str) -> float | None:
                    delta = deltas.get(key)
                    return round(delta / elapsed, 2) if delta is not None and elapsed else None

                speed = getattr(nic, "speed", None) if nic is not None else None
                mtu = getattr(nic, "mtu", None) if nic is not None else None
                duplex_value = getattr(nic, "duplex", None) if nic is not None else None
                duplex = "unknown"
                if duplex_value == getattr(psutil, "NIC_DUPLEX_FULL", object()):
                    duplex = "full"
                elif duplex_value == getattr(psutil, "NIC_DUPLEX_HALF", object()):
                    duplex = "half"

                interfaces.append({
                    "name": str(name)[:128], "is_up": is_up,
                    "speed_mbps": max(0, int(speed)) if speed is not None and int(speed) >= 0 else None,
                    "mtu": max(0, int(mtu)) if mtu is not None and int(mtu) >= 0 else None,
                    "duplex": duplex, "is_loopback": _loopback_interface(name, addresses.get(name, [])),
                    **current,
                    "sent_bytes_per_sec": rate("bytes_sent"),
                    "received_bytes_per_sec": rate("bytes_recv"),
                    "sent_packets_per_sec": rate("packets_sent"),
                    "received_packets_per_sec": rate("packets_recv"),
                    "errors_in_delta": deltas.get("errors_in"),
                    "errors_out_delta": deltas.get("errors_out"),
                    "drops_in_delta": deltas.get("drops_in"),
                    "drops_out_delta": deltas.get("drops_out"),
                    "delta_status": "Available" if previous and elapsed else "Warming up",
                })
                self._previous[name] = (now, current, is_up)

        interfaces.sort(key=lambda item: (
            not bool(item["is_up"]), bool(item["is_loopback"]), item["name"].casefold()
        ))
        active = [item for item in interfaces if item["is_up"]]
        return {
            "sampled_at": sampled_epoch, "status": "Available" if interfaces else "Unavailable",
            "interface_count": len(interfaces), "active_interface_count": len(active),
            "interfaces": interfaces[:64], "transitions": transitions[:32],
            "capabilities": {
                "per_interface_counters": "Available" if interfaces else "Unavailable",
                "link_state": "Available" if stats else "Unavailable",
                "ip_addresses_collected": False, "network_destinations_persisted": False,
            },
        }


def collect_connections(*, limit: int = 200, include_addresses: bool = False) -> dict[str, Any]:
    """Return a bounded live socket snapshot. Endpoint IPs are hidden unless explicitly requested."""
    bounded_limit = max(1, min(int(limit), 500))
    try:
        connections = psutil.net_connections(kind="inet")
    except psutil.AccessDenied:
        return {
            "status": "Limited", "reason": "The operating system denied access to some or all connection tables.",
            "count": 0, "visible_count": 0, "connections": [], "by_state": {}, "by_protocol": {},
            "by_process": [], "addresses_visible": bool(include_addresses),
        }
    except (psutil.Error, OSError, NotImplementedError):
        return {
            "status": "Unavailable", "reason": "Connection enumeration is not supported by this OS/provider.",
            "count": 0, "visible_count": 0, "connections": [], "by_state": {}, "by_protocol": {},
            "by_process": [], "addresses_visible": bool(include_addresses),
        }

    names: dict[int, str] = {}
    rows: list[dict[str, Any]] = []
    state_counts: Counter[str] = Counter()
    protocol_counts: Counter[str] = Counter()
    process_counts: Counter[str] = Counter()
    for connection in connections:
        pid = int(connection.pid) if connection.pid is not None else None
        if pid is not None and pid not in names:
            try:
                names[pid] = psutil.Process(pid).name()
            except (psutil.Error, OSError):
                names[pid] = "Unknown"
        process_name = names.get(pid, "System") if pid is not None else "System"
        protocol = "TCP" if connection.type == socket.SOCK_STREAM else "UDP"
        state = str(connection.status or "NONE").upper()
        state_counts[state] += 1
        protocol_counts[protocol] += 1
        process_counts[process_name] += 1
        local, remote = connection.laddr, connection.raddr
        row: dict[str, Any] = {
            "pid": pid, "process": process_name, "protocol": protocol, "state": state,
            "local_port": int(local.port) if local else None,
            "remote_port": int(remote.port) if remote else None,
        }
        if include_addresses:
            row["local_address"] = str(local.ip) if local else None
            row["remote_address"] = str(remote.ip) if remote else None
        rows.append(row)

    rows.sort(key=lambda row: (
        row["state"] != "ESTABLISHED", row["process"].casefold(),
        row["remote_port"] or 0, row["pid"] or 0
    ))
    return {
        "status": "Available", "reason": None, "count": len(connections),
        "visible_count": min(len(rows), bounded_limit), "connections": rows[:bounded_limit],
        "by_state": dict(state_counts), "by_protocol": dict(protocol_counts),
        "by_process": [{"process": name, "count": count} for name, count in process_counts.most_common(15)],
        "addresses_visible": bool(include_addresses),
    }


def _normalize_host(host: str) -> str:
    candidate = str(host or "").strip().rstrip(".")
    if not candidate or len(candidate) > 253 or any(ch in candidate for ch in "/\\?#@% \t\r\n"):
        raise ValueError("Enter a hostname or IP address only, without a URL or path.")
    try:
        ipaddress.ip_address(candidate)
        return candidate
    except ValueError:
        try:
            ascii_host = candidate.encode("idna").decode("ascii").lower()
        except UnicodeError as exc:
            raise ValueError("The host name is not valid IDNA.") from exc
        labels = ascii_host.split(".")
        if not labels or any(
            not re.fullmatch(r"[a-z0-9](?:[a-z0-9-]{0,61}[a-z0-9])?", label)
            for label in labels
        ):
            raise ValueError("Enter a valid DNS host name or IP address.")
        return ascii_host


def diagnose_tcp_connectivity(host: str, port: int = 443, *, attempts: int = 3) -> dict[str, Any]:
    """Measure resolver and TCP handshake latency without sending application data."""
    target = _normalize_host(host)
    if not 1 <= int(port) <= 65535:
        raise ValueError("Port must be between 1 and 65535.")
    attempt_count = max(1, min(int(attempts), 3))
    results: Queue[tuple[bool, Any, float]] = Queue(maxsize=1)

    def resolve() -> None:
        started = time.perf_counter()
        try:
            values = socket.getaddrinfo(target, int(port), type=socket.SOCK_STREAM)
            results.put((True, values, (time.perf_counter() - started) * 1000))
        except OSError:
            results.put((False, None, (time.perf_counter() - started) * 1000))

    threading.Thread(target=resolve, name="nexus-dns-probe", daemon=True).start()
    try:
        resolved, addresses, dns_ms = results.get(timeout=2.0)
    except Empty:
        return {
            "status": "dns-timeout", "host": target, "port": int(port), "dns_latency_ms": None,
            "resolved_address_count": 0, "attempts": [], "success_count": 0,
            "failure_count": attempt_count, "message": "The system resolver did not respond within two seconds.",
        }
    if not resolved or not addresses:
        return {
            "status": "dns-failed", "host": target, "port": int(port),
            "dns_latency_ms": round(dns_ms, 2), "resolved_address_count": 0,
            "attempts": [], "success_count": 0, "failure_count": attempt_count,
            "message": "The system resolver could not resolve this host.",
        }

    endpoints, seen = [], set()
    for family, socktype, proto, _canonname, sockaddr in addresses:
        key = (family, socktype, proto, sockaddr)
        if key not in seen:
            seen.add(key)
            endpoints.append((family, socktype, proto, sockaddr))
    attempts_out, successful = [], []
    for index in range(attempt_count):
        family, socktype, proto, sockaddr = endpoints[index % len(endpoints)]
        started = time.perf_counter()
        sock = socket.socket(family, socktype, proto)
        sock.settimeout(0.8)
        try:
            sock.connect(sockaddr)
            latency = (time.perf_counter() - started) * 1000
            successful.append(latency)
            attempts_out.append({"status": "connected", "latency_ms": round(latency, 2)})
        except socket.timeout:
            attempts_out.append({"status": "timeout", "latency_ms": None})
        except OSError as exc:
            category = "refused" if getattr(exc, "errno", None) in {111, 61, 10061} else "unreachable"
            attempts_out.append({"status": category, "latency_ms": None})
        finally:
            sock.close()

    average = sum(successful) / len(successful) if successful else None
    jitter = None
    if len(successful) > 1:
        jitter = sum(abs(successful[i] - successful[i - 1]) for i in range(1, len(successful))) / (len(successful) - 1)
    return {
        "status": "connected" if successful else "tcp-failed",
        "host": target, "port": int(port), "dns_latency_ms": round(dns_ms, 2),
        "resolved_address_count": len(endpoints), "attempts": attempts_out,
        "success_count": len(successful), "failure_count": attempt_count - len(successful),
        "packet_loss_percent": round((attempt_count - len(successful)) / attempt_count * 100, 1),
        "tcp_latency_ms": {
            "min": round(min(successful), 2) if successful else None,
            "average": round(average, 2) if average is not None else None,
            "max": round(max(successful), 2) if successful else None,
            "jitter": round(jitter, 2) if jitter is not None else None,
        },
        "message": "TCP handshakes completed; no application payload was sent." if successful else "DNS succeeded, but TCP connections did not complete.",
    }


def build_network_history_points(rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Turn stored counters into rate and error-delta points; counter resets become null."""
    previous: dict[str, dict[str, Any]] = {}
    output: list[dict[str, Any]] = []
    for row in rows:
        point = dict(row)
        name = str(row.get("interface_name") or "")
        prior = previous.get(name)
        if prior:
            elapsed = float(row["sampled_epoch"]) - float(prior["sampled_epoch"])
            for source, target in (
                ("bytes_sent", "sent_bytes_per_sec"), ("bytes_recv", "received_bytes_per_sec"),
                ("packets_sent", "sent_packets_per_sec"), ("packets_recv", "received_packets_per_sec"),
                ("errors_in", "errors_in_delta"), ("errors_out", "errors_out_delta"),
                ("drops_in", "drops_in_delta"), ("drops_out", "drops_out_delta"),
            ):
                delta = _safe_delta(row.get(source), prior.get(source))
                point[target] = (
                    round(delta / elapsed, 2)
                    if source.startswith(("bytes_", "packets_")) and delta is not None and elapsed > 0
                    else delta
                )
        else:
            for target in ("sent_bytes_per_sec", "received_bytes_per_sec", "sent_packets_per_sec",
                           "received_packets_per_sec", "errors_in_delta", "errors_out_delta",
                           "drops_in_delta", "drops_out_delta"):
                point[target] = None
        output.append(point)
        previous[name] = row
    return output
