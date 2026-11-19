'''Traceroute service – runs system traceroute and parses hop latencies.'''
import re
import subprocess
from dataclasses import dataclass
from typing import List, Optional


@dataclass
class HopResult:
    hop: int
    host: Optional[str]
    latency_ms: Optional[float]
    raw: str


def run_traceroute(host: str, max_hops: int = 30, timeout: int = 2) -> List[HopResult]:
    """Execute ``traceroute`` to *host* and return a list of HopResult.
    macOS/Linux ``traceroute`` is used (no ``-I`` or ``-T`` flags).
    ``max_hops`` limits the number of hops; ``timeout`` is per‑probe seconds.
    """
    # macOS ``traceroute`` flag: -m max hops, -w timeout per probe, -n numeric output
    cmd = ["traceroute", "-n", "-m", str(max_hops), "-w", str(timeout), host]
    try:
        proc = subprocess.run(cmd, capture_output=True, text=True, timeout=max_hops * (timeout + 1))
    except FileNotFoundError:
        raise RuntimeError("`traceroute` command not found on this system")
    except subprocess.TimeoutExpired:
        raise RuntimeError("Traceroute timed out")

    if proc.returncode not in (0, 1):  # non‑zero may still have output, but treat as error
        raise RuntimeError(f"Traceroute failed: {proc.stderr.strip()}")

    lines = proc.stdout.splitlines()
    hops: List[HopResult] = []
    hop_re = re.compile(r"^(\d+)\s+(\S+)(?:\s+([\d.]+)\s+ms)?(?:\s+([\d.]+)\s+ms)?(?:\s+([\d.]+)\s+ms)?")
    for line in lines:
        line = line.strip()
        if not line or line.startswith("traceroute"):
            continue
        m = hop_re.match(line)
        if not m:
            continue
        hop_num = int(m.group(1))
        host_ip = m.group(2)
        # gather all latency numbers present
        lat_vals = [float(v) for v in (m.group(3), m.group(4), m.group(5)) if v]
        latency = sum(lat_vals) / len(lat_vals) if lat_vals else None
        # treat "*" as timeout
        if host_ip == "*":
            host_ip = None
            latency = None
        hops.append(HopResult(hop=hop_num, host=host_ip, latency_ms=latency, raw=line))
    return hops
