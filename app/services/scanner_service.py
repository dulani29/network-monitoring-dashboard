"""Network scanner: finds live devices on a subnet with a ping sweep.

How it works
    1. Every host address in the subnet gets one ICMP echo (the same OS `ping`
       the monitor uses; no shell, no raw sockets, no extra privileges).
    2. Hosts that answer are "live". For each one we try a reverse-DNS lookup
       for a friendly name.
    3. When the sweep ends we read the OS ARP table to attach MAC addresses.

The scan runs as a background job so the browser can show live progress. Only
one scan runs at a time. Devices that block ICMP in their firewall (many
phones do) will not be found - the same limitation the monitor itself has.

Scope is limited by validators.validate_scan_payload (private ranges, <= /22);
this module trusts that its caller has already validated the network.
"""
import ipaddress
import socket
import threading
from concurrent.futures import ThreadPoolExecutor, as_completed
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Callable, Dict, List, Optional

from ..repositories.device_repository import DeviceRepository
from .network_utils import (detect_default_gateway, detect_local_subnet,
                            local_ipv4_addresses, read_arp_table)
from .ping_service import PingService


class ScanBusyError(RuntimeError):
    """A scan is already running."""


@dataclass
class ScanJob:
    id: int
    subnet: str
    total: int
    state: str = "running"            # running | done | cancelled | error
    scanned: int = 0
    found: List[dict] = field(default_factory=list)
    started_at: str = ""
    finished_at: Optional[str] = None
    error: Optional[str] = None


def _now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def _ip_key(entry: dict):
    return ipaddress.IPv4Address(entry["host"])


def reverse_dns(ip: str) -> Optional[str]:
    try:
        name = socket.gethostbyaddr(ip)[0]
    except OSError:                     # herror / gaierror / timeout: no name, that's fine
        return None
    return None if not name or name == ip else name


class ScannerService:
    def __init__(self, devices: DeviceRepository, ping: PingService, max_workers: int = 64,
                 enrich: bool = True,
                 resolve: Callable[[str], Optional[str]] = reverse_dns,
                 arp_table: Callable[[], Dict[str, str]] = read_arp_table,
                 gateway: Callable[[], Optional[str]] = detect_default_gateway,
                 local_ips: Callable[[], set] = local_ipv4_addresses):
        self.devices = devices
        self.ping = ping
        self.max_workers = max(1, max_workers)
        self.enrich = enrich            # hostnames, MACs, gateway/self labels (off in unit tests)
        self._resolve, self._arp, self._gateway, self._local_ips = resolve, arp_table, gateway, local_ips
        self._lock = threading.Lock()
        self._job: Optional[ScanJob] = None
        self._cancel = threading.Event()
        self._thread: Optional[threading.Thread] = None
        self._next_id = 1

    # -- public API ---------------------------------------------------------
    def default_subnet(self) -> Optional[str]:
        return detect_local_subnet()

    def start(self, network: ipaddress.IPv4Network) -> dict:
        with self._lock:
            if self._job and self._job.state == "running":
                raise ScanBusyError("A scan is already running.")
            hosts = [str(h) for h in network.hosts()]
            job = ScanJob(id=self._next_id, subnet=str(network), total=len(hosts), started_at=_now())
            self._next_id += 1
            self._job = job
            self._cancel = threading.Event()
            self._thread = threading.Thread(
                target=self._run, args=(job, hosts, self._cancel), daemon=True, name=f"scan-{job.id}")
            self._thread.start()
        return self.snapshot()

    def cancel(self) -> dict:
        self._cancel.set()
        return self.snapshot()

    def join(self, timeout: Optional[float] = None) -> None:
        """Wait for the running scan to finish (used by tests)."""
        t = self._thread
        if t:
            t.join(timeout)

    def snapshot(self) -> dict:
        """The latest scan as JSON, with each device flagged if it is already monitored."""
        with self._lock:
            job = self._job
            if job is None:
                return {"state": "idle", "devices": []}
            monitored = {d.host.lower() for d in self.devices.list()}
            devices = [dict(d, already_added=d["host"].lower() in monitored)
                       for d in sorted(job.found, key=_ip_key)]
            return {"id": job.id, "state": job.state, "subnet": job.subnet, "total": job.total,
                    "scanned": job.scanned, "started_at": job.started_at,
                    "finished_at": job.finished_at, "error": job.error, "devices": devices}

    # -- worker ---------------------------------------------------------------
    def _run(self, job: ScanJob, hosts: List[str], cancel: threading.Event) -> None:
        try:
            gateway = self._safe(self._gateway) if self.enrich else None
            mine = (self._safe(self._local_ips) or set()) if self.enrich else set()
            workers = min(self.max_workers, max(1, len(hosts)))
            with ThreadPoolExecutor(max_workers=workers) as pool:
                futures = [pool.submit(self._probe, h, cancel, gateway, mine) for h in hosts]
                for fut in as_completed(futures):
                    entry = fut.result()
                    with self._lock:
                        job.scanned += 1
                        if entry:
                            job.found.append(entry)
            if self.enrich and job.found and not cancel.is_set():
                macs = self._safe(self._arp) or {}
                with self._lock:
                    for entry in job.found:
                        entry["mac"] = macs.get(entry["host"])
            state = "cancelled" if cancel.is_set() else "done"
            error = None
        except Exception as exc:        # never leave a job stuck on "running"
            state, error = "error", f"Scan failed: {exc}"
        with self._lock:
            job.state, job.error, job.finished_at = state, error, _now()

    def _probe(self, host: str, cancel: threading.Event, gateway, mine) -> Optional[dict]:
        if cancel.is_set():
            return None
        result = self.ping.ping(host)
        if not result.reachable:
            return None
        hostname = self._safe(self._resolve, host) if self.enrich else None
        is_gateway, is_self = host == gateway, host in mine
        return {
            "host": host,
            "hostname": hostname,
            "mac": None,
            "latency_ms": result.avg_ms,
            "is_gateway": is_gateway,
            "is_self": is_self,
            "suggested_name": self._suggest_name(host, hostname, is_gateway, is_self),
            "suggested_type": "router" if is_gateway else "laptop" if is_self else "other",
        }

    @staticmethod
    def _suggest_name(host, hostname, is_gateway, is_self) -> str:
        if is_gateway:
            return "Router (gateway)"
        if is_self:
            return "This computer"
        if hostname:
            return hostname.split(".")[0][:60] or f"Device {host}"
        return f"Device {host}"

    @staticmethod
    def _safe(fn, *args):
        try:
            return fn(*args)
        except Exception:               # enrichment is best effort; never fail the scan over it
            return None
