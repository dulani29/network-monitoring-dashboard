"""Incident log: turns the stream of check results into outages.

An *incident* starts with the first OFFLINE check of a device and ends with the
first non-offline check (Degraded counts as "up", the same rule the uptime %
uses). Durations are therefore accurate to the check interval.
"""
import threading
from datetime import datetime, timezone
from typing import List, Optional

from ..models import CheckResult, Status
from ..repositories.device_repository import DeviceRepository
from ..repositories.history_repository import _iso
from ..repositories.incident_repository import IncidentRepository


def parse_iso(value: str) -> datetime:
    dt = datetime.fromisoformat(value.replace("Z", "+00:00"))
    return dt if dt.tzinfo else dt.replace(tzinfo=timezone.utc)


def local_midnight_utc() -> datetime:
    """Start of 'today' in the server's local time zone, as an aware UTC datetime."""
    now = datetime.now().astimezone()
    return now.replace(hour=0, minute=0, second=0, microsecond=0).astimezone(timezone.utc)


class IncidentService:
    def __init__(self, incidents: IncidentRepository, devices: DeviceRepository):
        self.incidents = incidents
        self.devices = devices
        # Checks run in a thread pool; make open/close atomic per call so two
        # overlapping checks of one device can't open the same incident twice.
        self._lock = threading.Lock()

    # -- recording -----------------------------------------------------------
    def track(self, result: CheckResult) -> None:
        with self._lock:
            open_incident = self.incidents.get_open(result.device_id)
            if result.status == Status.OFFLINE:
                if not open_incident:
                    self.incidents.open(result.device_id, result.checked_at, result.error)
            elif open_incident:      # online or degraded -> recovered
                self.incidents.close(result.device_id, result.checked_at)

    def close_for_device(self, device_id: int) -> None:
        """Used when a device is paused: it can no longer recover on its own."""
        with self._lock:
            self.incidents.close(device_id, _iso(datetime.now(timezone.utc)))

    # -- reporting -----------------------------------------------------------
    def report(self, since: Optional[datetime] = None, device_id: Optional[int] = None,
               limit: int = 200) -> dict:
        now = datetime.now(timezone.utc)
        since = since or local_midnight_utc()
        everything = self.incidents.list()          # stats always cover all devices

        def seconds(row) -> float:
            end = parse_iso(row["ended_at"]) if row["ended_at"] else now
            return max(0.0, (end - parse_iso(row["started_at"])).total_seconds())

        def seconds_today(row) -> float:
            start = max(parse_iso(row["started_at"]), since)
            end = parse_iso(row["ended_at"]) if row["ended_at"] else now
            return max(0.0, (min(end, now) - start).total_seconds())

        per_device = {}
        for d in self.devices.list():
            per_device[d.id] = {"device_id": d.id, "device_name": d.name, "device_host": d.host,
                                "downtime_today_seconds": 0, "longest_outage_seconds": 0,
                                "incidents": 0, "ongoing": False}
        longest = None
        today_total = 0.0
        for row in everything:
            dur, today = seconds(row), seconds_today(row)
            row["duration_seconds"] = round(dur)
            row["ongoing"] = row["ended_at"] is None
            today_total += today
            stat = per_device.get(row["device_id"])
            if stat is not None:
                stat["downtime_today_seconds"] += today
                stat["longest_outage_seconds"] = max(stat["longest_outage_seconds"], dur)
                stat["incidents"] += 1
                stat["ongoing"] = stat["ongoing"] or row["ongoing"]
            if longest is None or dur > longest["seconds"]:
                longest = {"seconds": round(dur), "device_name": row["device_name"],
                           "started_at": row["started_at"], "ongoing": row["ongoing"]}

        devices: List[dict] = list(per_device.values())
        for stat in devices:
            stat["downtime_today_seconds"] = round(stat["downtime_today_seconds"])
            stat["longest_outage_seconds"] = round(stat["longest_outage_seconds"])
        devices.sort(key=lambda s: (-s["downtime_today_seconds"], s["device_name"].lower()))

        log = [r for r in everything if not device_id or r["device_id"] == device_id][:limit]
        return {
            "summary": {
                "downtime_today_seconds": round(today_total),
                "longest_outage": longest,
                "incidents_total": len(everything),
                "ongoing": sum(1 for r in everything if r["ongoing"]),
                "since": _iso(since),
            },
            "devices": devices,
            "incidents": log,
        }
