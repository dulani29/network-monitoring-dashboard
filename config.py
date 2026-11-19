"""Central application configuration.

Values can be overridden with environment variables, e.g.
    NETMON_PORT=8080 python run.py
"""
import os
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent


def _env_int(name: str, default: int) -> int:
    try:
        return int(os.environ.get(name, default))
    except ValueError:
        return default


class Config:
    # --- Web server -------------------------------------------------------
    HOST = os.environ.get("NETMON_HOST", "127.0.0.1")
    PORT = _env_int("NETMON_PORT", 5050)
    DEBUG = os.environ.get("NETMON_DEBUG", "0") == "1"

    # --- Database ---------------------------------------------------------
    DATABASE_PATH = os.environ.get("NETMON_DB", str(BASE_DIR / "data" / "netmon.db"))

    # --- Ping behaviour ---------------------------------------------------
    PING_COUNT = _env_int("NETMON_PING_COUNT", 3)          # packets per check
    PING_TIMEOUT = _env_int("NETMON_PING_TIMEOUT", 2)      # seconds per packet
    MAX_WORKERS = _env_int("NETMON_MAX_WORKERS", 16)       # parallel checks

    # --- Network scanner --------------------------------------------------
    SCAN_WORKERS = _env_int("NETMON_SCAN_WORKERS", 64)         # parallel pings during a scan
    SCAN_PING_TIMEOUT = _env_int("NETMON_SCAN_TIMEOUT", 1)     # seconds to wait for each host
    SCAN_ENRICH = True                                         # hostnames, MACs, gateway label

    # --- Status thresholds ------------------------------------------------
    HIGH_LATENCY_MS = _env_int("NETMON_HIGH_LATENCY_MS", 150)  # above = degraded

    # --- Auto monitoring --------------------------------------------------
    AUTO_MONITOR_DEFAULT = os.environ.get("NETMON_AUTO", "0") == "1"
    AUTO_INTERVAL_DEFAULT = _env_int("NETMON_INTERVAL", 30)    # seconds
    MIN_INTERVAL = 5
    HISTORY_RETENTION_DAYS = _env_int("NETMON_RETENTION_DAYS", 7)

    # --- Misc -------------------------------------------------------------
    SEED_DEFAULT_DEVICES = os.environ.get("NETMON_SEED", "1") == "1"
    DEFAULT_SITE_URL = os.environ.get("NETMON_SITE_URL", "http://example.com")



class TestConfig(Config):
    TESTING = True
    DATABASE_PATH = ":memory:"
    SEED_DEFAULT_DEVICES = False
    AUTO_MONITOR_DEFAULT = False
    SCAN_ENRICH = False            # tests must not touch DNS / ARP / routing tables
