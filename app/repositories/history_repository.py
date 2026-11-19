from datetime import datetime, timedelta, timezone
from typing import Dict, List, Optional

from ..database import Database
from ..models import CheckResult


def _iso(dt: datetime) -> str:
    return dt.strftime("%Y-%m-%dT%H:%M:%S.") + f"{dt.microsecond // 1000:03d}Z"


class HistoryRepository:
    def __init__(self, db: Database):
        self.db = db

    def add(self, r: CheckResult) -> CheckResult:
        r.checked_at = r.checked_at or _iso(datetime.now(timezone.utc))
        with self.db.connection() as conn:
            cur = conn.execute(
                """INSERT INTO check_results
                   (device_id, status, latency_ms, min_ms, max_ms, packet_loss, error, dns_ms, website_status, checked_at)
                   VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
                (r.device_id, r.status, r.latency_ms, r.min_ms, r.max_ms,
                 r.packet_loss, r.error, r.dns_ms, r.website_status, r.checked_at),
            )
            r.id = cur.lastrowid
        return r

    def latest_for_all(self) -> Dict[int, CheckResult]:
        sql = """
            SELECT c.* FROM check_results c
            JOIN (SELECT device_id, MAX(id) AS mid FROM check_results GROUP BY device_id) m
              ON c.id = m.mid
        """
        with self.db.connection() as conn:
            return {r["device_id"]: CheckResult.from_row(r) for r in conn.execute(sql)}

    def for_device(self, device_id: int, limit: int = 60) -> List[CheckResult]:
        """Newest-first."""
        with self.db.connection() as conn:
            rows = conn.execute(
                "SELECT * FROM check_results WHERE device_id = ? ORDER BY id DESC LIMIT ?",
                (device_id, limit),
            ).fetchall()
        return [CheckResult.from_row(r) for r in rows]

    def recent(self, limit: int = 100, device_id: Optional[int] = None,
               status: Optional[str] = None) -> List[dict]:
        sql = """SELECT c.*, d.name AS device_name, d.host AS device_host
                 FROM check_results c JOIN devices d ON d.id = c.device_id WHERE 1=1"""
        params: list = []
        if device_id:
            sql += " AND c.device_id = ?"
            params.append(device_id)
        if status:
            sql += " AND c.status = ?"
            params.append(status)
        sql += " ORDER BY c.id DESC LIMIT ?"
        params.append(limit)
        with self.db.connection() as conn:
            return [dict(r) for r in conn.execute(sql, params)]

    def series(self, per_device: int = 40) -> Dict[int, List[dict]]:
        """Last N readings of every device, oldest -> newest (for dashboard charts)."""
        sql = """
            SELECT c.device_id, c.status, c.latency_ms, c.packet_loss, c.checked_at
            FROM check_results c
            WHERE c.id IN (SELECT c2.id FROM check_results c2
                           WHERE c2.device_id = c.device_id ORDER BY c2.id DESC LIMIT ?)
            ORDER BY c.device_id, c.id
        """
        out: Dict[int, List[dict]] = {}
        with self.db.connection() as conn:
            for r in conn.execute(sql, (per_device,)):
                out.setdefault(r["device_id"], []).append({
                    "status": r["status"], "latency_ms": r["latency_ms"],
                    "packet_loss": r["packet_loss"], "checked_at": r["checked_at"]})
        return out

    def uptime_stats(self, hours: int = 24) -> Dict[int, dict]:
        """Per-device uptime % (online+degraded count as 'up') over the window."""
        since = _iso(datetime.now(timezone.utc) - timedelta(hours=hours))
        sql = """
            SELECT device_id,
                   COUNT(*) AS total,
                   SUM(CASE WHEN status != 'offline' THEN 1 ELSE 0 END) AS up,
                   AVG(latency_ms) AS avg_latency
            FROM check_results WHERE checked_at >= ? GROUP BY device_id
        """
        with self.db.connection() as conn:
            rows = conn.execute(sql, (since,)).fetchall()
        return {
            r["device_id"]: {
                "checks": r["total"],
                "uptime_pct": round(100.0 * r["up"] / r["total"], 1) if r["total"] else None,
                "avg_latency_ms": round(r["avg_latency"], 1) if r["avg_latency"] is not None else None,
            }
            for r in rows
        }

    def purge_older_than(self, days: int) -> int:
        cutoff = _iso(datetime.now(timezone.utc) - timedelta(days=days))
        with self.db.connection() as conn:
            return conn.execute("DELETE FROM check_results WHERE checked_at < ?", (cutoff,)).rowcount

    def clear(self, device_id: Optional[int] = None) -> int:
        with self.db.connection() as conn:
            if device_id:
                return conn.execute("DELETE FROM check_results WHERE device_id = ?", (device_id,)).rowcount
            return conn.execute("DELETE FROM check_results").rowcount
