"""Tiny SQLite wrapper. A new connection is opened per operation, which keeps
it safe to use from Flask request threads *and* the background scheduler."""
import sqlite3
import threading
from contextlib import contextmanager

SCHEMA = """
CREATE TABLE IF NOT EXISTS devices (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    name        TEXT NOT NULL,
    host        TEXT NOT NULL UNIQUE,
    device_type TEXT NOT NULL DEFAULT 'other',
    enabled     INTEGER NOT NULL DEFAULT 1,
    created_at  TEXT NOT NULL DEFAULT (datetime('now'))
);

CREATE TABLE IF NOT EXISTS check_results (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    device_id   INTEGER NOT NULL REFERENCES devices(id) ON DELETE CASCADE,
    status      TEXT NOT NULL,               -- online | degraded | offline
    latency_ms  REAL,                        -- average RTT, NULL when offline
    min_ms      REAL,
    max_ms      REAL,
    packet_loss REAL NOT NULL DEFAULT 0,     -- percent
    error       TEXT,
    dns_ms      REAL,
    website_status INTEGER,
    checked_at  TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%fZ','now'))
);
CREATE INDEX IF NOT EXISTS idx_results_device_time
    ON check_results(device_id, checked_at DESC);

-- One row per outage: opened on the first failed check, closed on the first
-- successful one. ended_at is NULL while the device is still down.
CREATE TABLE IF NOT EXISTS incidents (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    device_id   INTEGER NOT NULL REFERENCES devices(id) ON DELETE CASCADE,
    started_at  TEXT NOT NULL,
    ended_at    TEXT,
    error       TEXT
);
CREATE INDEX IF NOT EXISTS idx_incidents_device_time
    ON incidents(device_id, started_at DESC);
CREATE INDEX IF NOT EXISTS idx_incidents_open
    ON incidents(device_id) WHERE ended_at IS NULL;

CREATE TABLE IF NOT EXISTS settings (
    key   TEXT PRIMARY KEY,
    value TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS users (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    username TEXT UNIQUE NOT NULL,
    password_hash TEXT NOT NULL,
    created_at TEXT NOT NULL DEFAULT (datetime('now'))
);
"""


class Database:
    def __init__(self, path: str):
        self.path = path
        self._memory = path == ":memory:"
        self._lock = threading.RLock()
        self._shared = None
        if self._memory:
            # One shared connection so the in-memory DB survives (tests).
            self._shared = sqlite3.connect(":memory:", check_same_thread=False)
            self._shared.row_factory = sqlite3.Row

    def _open(self) -> sqlite3.Connection:
        if self._memory:
            return self._shared
        conn = sqlite3.connect(self.path, timeout=10)
        conn.row_factory = sqlite3.Row
        conn.execute("PRAGMA foreign_keys = ON")
        conn.execute("PRAGMA journal_mode = WAL")
        return conn

    @contextmanager
    def connection(self):
        with self._lock:
            conn = self._open()
            try:
                yield conn
                conn.commit()
            except Exception:
                conn.rollback()
                raise
            finally:
                if not self._memory:
                    conn.close()

    def init_schema(self) -> None:
        with self.connection() as conn:
            conn.executescript(SCHEMA)
            conn.execute("PRAGMA foreign_keys = ON")
            # Ensure new columns exist for older DB files
            try:
                conn.execute("ALTER TABLE check_results ADD COLUMN dns_ms REAL")
            except Exception:
                pass
            try:
                conn.execute("ALTER TABLE check_results ADD COLUMN website_status INTEGER")
            except Exception:
                pass

