'''DNS resolution timing service.'''
import socket
import time
from dataclasses import dataclass
from typing import Optional


@dataclass
class DnsResult:
    hostname: str
    ip: Optional[str]
    elapsed_ms: float
    reachable: bool
    error: Optional[str] = None


def resolve(hostname: str) -> DnsResult:
    """Resolve *hostname* to an IP address and time the operation.
    Returns a DnsResult with timing in milliseconds.
    """
    start = time.perf_counter()
    try:
        _, _, ipaddrs = socket.gethostbyname_ex(hostname)
        elapsed = (time.perf_counter() - start) * 1000.0
        ip = ipaddrs[0] if ipaddrs else None
        return DnsResult(
            hostname=hostname,
            ip=ip,
            elapsed_ms=round(elapsed, 2),
            reachable=bool(ip),
        )
    except socket.gaierror as exc:
        elapsed = (time.perf_counter() - start) * 1000.0
        return DnsResult(
            hostname=hostname,
            ip=None,
            elapsed_ms=round(elapsed, 2),
            reachable=False,
            error=str(exc),
        )
