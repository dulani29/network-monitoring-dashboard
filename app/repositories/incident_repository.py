from datetime import datetime, timedelta, timezone
from typing import List, Optional

from ..database import Database
from .history_repository import _iso


class IncidentRepository:
    """Persistence for outages (one row per down -> recovered period)."""

    def __init__(self, db: Database):
        self.db = db

    def get_open(self, device_id: int) -> Optional[dict]:
        with self.db.connection() as conn:
            row = conn.execute(
                "SELECT * FROM incidents WHERE device_id = ? AND ended_at IS NULL "
                "ORDER BY id DESC LIMIT 1", (device_id,)).fetchone()
        return dict(row) if row else None

    def open(self, device_id: int, started_at: str, error: Optional[str] = None) -> int:
        with self.db.connection() as conn:
            return conn.execute(
                "INSERT INTO incidents (device_id, started_at, error) VALUES (?, ?, ?)",
                (device_id, started_at, error)).lastrowid

    def close(self, device_id: int, ended_at: str) -> int:
        """Close every open incident of the device; returns how many were closed."""
        with self.db.connection() as conn:
            return conn.execute(
                "UPDATE incidents SET ended_at = ? WHERE device_id = ? AND ended_at IS NULL",
                (ended_at, device_id)).rowcount

    def list(self, device_id: Optional[int] = None, limit: Optional[int] = None) -> List[dict]:
        """Newest first, joined with the device name/host."""
        sql = """SELECT i.*, d.name AS device_name, d.host AS device_host
                 FROM incidents i JOIN devices d ON d.id = i.device_id WHERE 1=1"""
        params: list = []
        if device_id:
            sql += " AND i.device_id = ?"
            params.append(device_id)
        sql += " ORDER BY i.started_at DESC, i.id DESC"
        if limit:
            sql += " LIMIT ?"
            params.append(limit)
        with self.db.connection() as conn:
            return [dict(r) for r in conn.execute(sql, params)]

    def purge_older_than(self, days: int) -> int:
        """Drop *finished* incidents that ended before the retention window."""
        cutoff = _iso(datetime.now(timezone.utc) - timedelta(days=days))
        with self.db.connection() as conn:
            return conn.execute(
                "DELETE FROM incidents WHERE ended_at IS NOT NULL AND ended_at < ?",
                (cutoff,)).rowcount
