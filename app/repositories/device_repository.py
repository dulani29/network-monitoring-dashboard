from typing import List, Optional

from ..database import Database
from ..models import Device


class DeviceRepository:
    def __init__(self, db: Database):
        self.db = db

    def list(self, only_enabled: bool = False) -> List[Device]:
        sql = "SELECT * FROM devices"
        if only_enabled:
            sql += " WHERE enabled = 1"
        sql += " ORDER BY name COLLATE NOCASE"
        with self.db.connection() as conn:
            return [Device.from_row(r) for r in conn.execute(sql)]

    def get(self, device_id: int) -> Optional[Device]:
        with self.db.connection() as conn:
            row = conn.execute("SELECT * FROM devices WHERE id = ?", (device_id,)).fetchone()
        return Device.from_row(row) if row else None

    def get_by_host(self, host: str) -> Optional[Device]:
        with self.db.connection() as conn:
            row = conn.execute("SELECT * FROM devices WHERE host = ? COLLATE NOCASE", (host,)).fetchone()
        return Device.from_row(row) if row else None

    def count(self) -> int:
        with self.db.connection() as conn:
            return conn.execute("SELECT COUNT(*) FROM devices").fetchone()[0]

    def create(self, name: str, host: str, device_type: str = "other", enabled: bool = True) -> Device:
        with self.db.connection() as conn:
            cur = conn.execute(
                "INSERT INTO devices (name, host, device_type, enabled) VALUES (?, ?, ?, ?)",
                (name, host, device_type, int(enabled)),
            )
            device_id = cur.lastrowid
        return self.get(device_id)

    def update(self, device_id: int, name: str, host: str, device_type: str, enabled: bool) -> Optional[Device]:
        with self.db.connection() as conn:
            conn.execute(
                "UPDATE devices SET name = ?, host = ?, device_type = ?, enabled = ? WHERE id = ?",
                (name, host, device_type, int(enabled), device_id),
            )
        return self.get(device_id)

    def delete(self, device_id: int) -> bool:
        with self.db.connection() as conn:
            cur = conn.execute("DELETE FROM devices WHERE id = ?", (device_id,))
            return cur.rowcount > 0
