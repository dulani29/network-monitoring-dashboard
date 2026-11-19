"""Background auto-monitoring loop (a daemon thread)."""
import threading
from typing import Optional

from ..repositories.history_repository import HistoryRepository
from ..repositories.incident_repository import IncidentRepository
from ..repositories.settings_repository import SettingsRepository
from .monitor_service import MonitorService


class MonitorScheduler:
    def __init__(self, monitor: MonitorService, history: HistoryRepository,
                 settings: SettingsRepository, retention_days: int = 7,
                 default_enabled: bool = False, default_interval: int = 30,
                 min_interval: int = 5, incidents: Optional[IncidentRepository] = None):
        self.monitor = monitor
        self.incidents = incidents
        self.history = history
        self.settings = settings
        self.retention_days = retention_days
        self.min_interval = min_interval
        self._wake = threading.Event()
        self._stop = threading.Event()
        self._thread: Optional[threading.Thread] = None
        self._lock = threading.Lock()
        self._running_check = False

        self._enabled = self.settings.get("auto_enabled", "1" if default_enabled else "0") == "1"
        self._interval = max(min_interval, int(self.settings.get("auto_interval", default_interval)))

    # -- state ------------------------------------------------------------
    def status(self) -> dict:
        return {"enabled": self._enabled, "interval": self._interval,
                "min_interval": self.min_interval, "checking": self._running_check}

    def configure(self, enabled: Optional[bool] = None, interval: Optional[int] = None) -> dict:
        if interval is not None:
            self._interval = max(self.min_interval, int(interval))
            self.settings.set("auto_interval", self._interval)
        if enabled is not None:
            self._enabled = bool(enabled)
            self.settings.set("auto_enabled", "1" if self._enabled else "0")
        self._wake.set()
        return self.status()

    # -- thread -----------------------------------------------------------
    def start(self) -> None:
        if self._thread and self._thread.is_alive():
            return
        self._stop.clear()
        self._thread = threading.Thread(target=self._loop, name="netmon-scheduler", daemon=True)
        self._thread.start()

    def stop(self) -> None:
        self._stop.set()
        self._wake.set()

    def _loop(self) -> None:
        cycles = 0
        while not self._stop.is_set():
            if self._enabled:
                self._running_check = True
                try:
                    self.monitor.check_all()
                    cycles += 1
                    if cycles % 20 == 0:
                        self.history.purge_older_than(self.retention_days)
                        if self.incidents:
                            self.incidents.purge_older_than(self.retention_days)
                except Exception as exc:   # never let the loop die
                    print(f"[scheduler] check failed: {exc}")
                finally:
                    self._running_check = False
            self._wake.wait(timeout=self._interval if self._enabled else 1.0)
            self._wake.clear()
