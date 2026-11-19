"""Business logic: run checks (in parallel), classify status, build dashboard data."""
from concurrent.futures import ThreadPoolExecutor
from typing import List, Optional

from ..models import CheckResult, Device, Status
from ..repositories.device_repository import DeviceRepository
from ..repositories.history_repository import HistoryRepository
from .incident_service import IncidentService
from .ping_service import PingResult, PingService
from config import Config
from .dns_service import resolve as dns_resolve
from .http_service import check as http_check



class MonitorService:
    def __init__(self, devices: DeviceRepository, history: HistoryRepository,
                 ping: PingService, max_workers: int = 16, high_latency_ms: int = 150,
                 incidents: Optional[IncidentService] = None):
        self.devices = devices
        self.history = history
        self.ping = ping
        self.max_workers = max_workers
        self.high_latency_ms = high_latency_ms
        self.incidents = incidents

    # -- classification ---------------------------------------------------
    def classify(self, r: PingResult) -> str:
        if not r.reachable:
            return Status.OFFLINE
        if r.packet_loss > 0 or (r.avg_ms is not None and r.avg_ms > self.high_latency_ms):
            return Status.DEGRADED
        return Status.ONLINE

    # -- checks ---------------------------------------------------------------
    def check_device(self, device: Device) -> CheckResult:
        pr = self.ping.ping(device.host)
        # DNS resolution timing
        dns_res = dns_resolve(device.host)
        # Website health check (using a default URL or per-device attribute if present)
        website_url = getattr(device, "website", None) or Config.DEFAULT_SITE_URL
        http_res = http_check(website_url) if website_url else None
        # Run the check and store it
        result = CheckResult(
            device_id=device.id,
            status=self.classify(pr),
            latency_ms=pr.avg_ms,
            min_ms=pr.min_ms,
            max_ms=pr.max_ms,
            packet_loss=pr.packet_loss,
            error=pr.error,
            dns_ms=dns_res.elapsed_ms,
            website_status=1 if (http_res and http_res.ok) else 0,
        )
        # Persist and capture the actual checked_at timestamp
        persisted = self.history.add(result)
        # Update the result object with the timestamp used for incident tracking
        result.checked_at = persisted.checked_at
        if self.incidents:
            self.incidents.track(result)       # open / close an outage on status change
        return result

    def check_many(self, devices: List[Device]) -> List[CheckResult]:
        if not devices:
            return []
        workers = min(self.max_workers, len(devices))
        with ThreadPoolExecutor(max_workers=workers) as pool:
            return list(pool.map(self.check_device, devices))

    def check_all(self) -> List[CheckResult]:
        return self.check_many(self.devices.list(only_enabled=True))

    # -- dashboard views --------------------------------------------------
    def devices_with_status(self) -> List[dict]:
        latest = self.history.latest_for_all()
        stats = self.history.uptime_stats(hours=24)
        out = []
        for d in self.devices.list():
            row = d.to_dict()
            last = latest.get(d.id)
            row["status"] = last.status if last else Status.UNKNOWN
            row["latency_ms"] = last.latency_ms if last else None
            row["packet_loss"] = last.packet_loss if last else None
            row["last_checked"] = last.checked_at if last else None
            row["error"] = last.error if last else None
            s = stats.get(d.id, {})
            row["uptime_pct"] = s.get("uptime_pct")
            row["avg_latency_ms"] = s.get("avg_latency_ms")
            out.append(row)
        return out

    def summary(self) -> dict:
        rows = self.devices_with_status()
        counts = {Status.ONLINE: 0, Status.DEGRADED: 0, Status.OFFLINE: 0, Status.UNKNOWN: 0}
        latencies = []
        for r in rows:
            counts[r["status"]] += 1
            if r["latency_ms"] is not None:
                latencies.append(r["latency_ms"])
        known = counts[Status.ONLINE] + counts[Status.DEGRADED] + counts[Status.OFFLINE]
        health = round(100.0 * (counts[Status.ONLINE] + counts[Status.DEGRADED]) / known, 1) if known else None
        return {
            "total": len(rows),
            **counts,
            "avg_latency_ms": round(sum(latencies) / len(latencies), 1) if latencies else None,
            "network_health_pct": health,
        }
