from dataclasses import dataclass, asdict
from typing import Optional


class Status:
    ONLINE = "online"
    DEGRADED = "degraded"   # replies, but with packet loss or high latency
    OFFLINE = "offline"
    UNKNOWN = "unknown"     # never checked yet


@dataclass
class CheckResult:
    device_id: int
    status: str
    latency_ms: Optional[float] = None
    min_ms: Optional[float] = None
    max_ms: Optional[float] = None
    packet_loss: float = 0.0
    error: Optional[str] = None
    dns_ms: Optional[float] = None
    website_status: Optional[int] = None
    dns_ms: Optional[float] = None
    website_status: Optional[int] = None
    checked_at: str = ""
    id: Optional[int] = None

    @classmethod
    def from_row(cls, row) -> "CheckResult":
        return cls(
            id=row["id"],
            device_id=row["device_id"],
            status=row["status"],
            latency_ms=row["latency_ms"],
            min_ms=row["min_ms"],
            max_ms=row["max_ms"],
            packet_loss=row["packet_loss"],
            error=row["error"],
            checked_at=row["checked_at"],
        )

    def to_dict(self) -> dict:
        return asdict(self)
