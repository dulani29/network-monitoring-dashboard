"""Runs the operating-system `ping` command and parses the result.

Works on macOS, Linux and Windows. No shell is used (argument list only)."""
import platform
import re
import subprocess
from dataclasses import dataclass
from typing import List, Optional

# Matches "time=14.8 ms", "time<1ms", "time=1ms"
_TIME_RE = re.compile(r"time[=<]\s*([\d.]+)\s*ms", re.IGNORECASE)


@dataclass
class PingResult:
    reachable: bool
    sent: int
    received: int
    packet_loss: float
    min_ms: Optional[float] = None
    avg_ms: Optional[float] = None
    max_ms: Optional[float] = None
    error: Optional[str] = None


class PingService:
    def __init__(self, count: int = 3, timeout: int = 2):
        self.count = max(1, count)
        self.timeout = max(1, timeout)
        self.system = platform.system().lower()

    # -- command construction ---------------------------------------------
    def build_command(self, host: str) -> List[str]:
        if self.system == "windows":
            return ["ping", "-n", str(self.count), "-w", str(self.timeout * 1000), host]
        if self.system == "darwin":      # macOS: -W expects timeout in milliseconds
            return ["ping", "-c", str(self.count), "-W", str(self.timeout * 1000), host]

        return ["ping", "-c", str(self.count), "-W", str(self.timeout), host]   # Linux

    # -- parsing ------------------------------------------------------------
    @staticmethod
    def parse_output(output: str, sent: int) -> PingResult:
        times = [float(t) for t in _TIME_RE.findall(output)]
        received = min(len(times), sent)
        loss = round(100.0 * (sent - received) / sent, 1) if sent else 100.0
        if not times:
            return PingResult(False, sent, 0, 100.0, error="No reply (timeout or unreachable)")
        return PingResult(
            reachable=True,
            sent=sent,
            received=received,
            packet_loss=loss,
            min_ms=round(min(times), 2),
            avg_ms=round(sum(times) / len(times), 2),
            max_ms=round(max(times), 2),
        )

    # -- public API -----------------------------------------------------------
    def ping(self, host: str) -> PingResult:
        cmd = self.build_command(host)
        hard_timeout = self.count * (self.timeout + 1) + 3
        try:
            proc = subprocess.run(
                cmd, capture_output=True, text=True, timeout=hard_timeout, shell=False
            )
        except FileNotFoundError:
            return PingResult(False, self.count, 0, 100.0,
                              error="`ping` command not found on this system")
        except subprocess.TimeoutExpired:
            return PingResult(False, self.count, 0, 100.0, error="Ping timed out")
        except OSError as exc:
            return PingResult(False, self.count, 0, 100.0, error=f"OS error: {exc}")

        output = (proc.stdout or "") + (proc.stderr or "")
        result = self.parse_output(output, self.count)
        if not result.reachable and proc.returncode not in (0, 1, 2):
            result.error = (proc.stderr or "").strip().splitlines()[-1:] and \
                (proc.stderr or "").strip().splitlines()[-1] or result.error
        return result
