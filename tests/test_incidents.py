import unittest
from datetime import datetime, timezone
from unittest.mock import patch

from app import create_app
from app.models import CheckResult, Status
from app.services.ping_service import PingResult
from config import TestConfig

UP = PingResult(True, 3, 3, 0.0, 1.0, 2.0, 3.0)
DOWN = PingResult(False, 3, 0, 100.0, error="No reply")
LOSSY = PingResult(True, 3, 2, 33.3, 10.0, 12.0, 14.0)


def at(h, m=0, s=0):
    return f"2026-11-19T{h:02d}:{m:02d}:{s:02d}.000Z"


def utc(h, m=0, s=0):
    return datetime(2026, 11, 19, h, m, s, tzinfo=timezone.utc)


class IncidentServiceTests(unittest.TestCase):
    def setUp(self):
        self.app = create_app(TestConfig)
        ctx = self.app.extensions["netmon"]
        self.svc = ctx["incidents"]
        self.dev = ctx["devices"].create("Router", "10.0.0.1", "router")
        self.other = ctx["devices"].create("NAS", "10.0.0.2", "server")

    def check(self, device, status, when):
        self.svc.track(CheckResult(device_id=device.id, status=status, checked_at=when,
                                   error="No reply" if status == Status.OFFLINE else None))

    def test_down_then_recovered_records_duration(self):
        self.check(self.dev, Status.ONLINE, at(9, 0))
        self.check(self.dev, Status.OFFLINE, at(10, 0))
        self.check(self.dev, Status.OFFLINE, at(10, 5))          # still the same outage
        self.check(self.dev, Status.ONLINE, at(10, 30))
        rep = self.svc.report(since=utc(0))
        self.assertEqual(len(rep["incidents"]), 1)
        inc = rep["incidents"][0]
        self.assertEqual((inc["started_at"], inc["ended_at"]), (at(10, 0), at(10, 30)))
        self.assertEqual(inc["duration_seconds"], 30 * 60)
        self.assertFalse(inc["ongoing"])
        self.assertEqual(rep["summary"]["ongoing"], 0)

    def test_degraded_counts_as_recovery(self):
        self.check(self.dev, Status.OFFLINE, at(10, 0))
        self.check(self.dev, Status.DEGRADED, at(10, 1))
        self.assertFalse(self.svc.report(since=utc(0))["incidents"][0]["ongoing"])

    def test_no_incident_while_online(self):
        for m in range(3):
            self.check(self.dev, Status.ONLINE, at(9, m))
        self.assertEqual(self.svc.report(since=utc(0))["incidents"], [])

    def test_ongoing_outage_has_no_end(self):
        self.check(self.dev, Status.OFFLINE, at(10, 0))
        rep = self.svc.report(since=utc(0))
        self.assertTrue(rep["incidents"][0]["ongoing"])
        self.assertIsNone(rep["incidents"][0]["ended_at"])
        self.assertEqual(rep["summary"]["ongoing"], 1)

    def test_downtime_today_and_longest_outage(self):
        # Router: 20 min + 5 min today.  NAS: 1 h but yesterday-ish (before `since`) -> only the tail counts.
        self.check(self.dev, Status.OFFLINE, at(10, 0)); self.check(self.dev, Status.ONLINE, at(10, 20))
        self.check(self.dev, Status.OFFLINE, at(12, 0)); self.check(self.dev, Status.ONLINE, at(12, 5))
        self.check(self.other, Status.OFFLINE, at(8, 0)); self.check(self.other, Status.ONLINE, at(9, 0))
        rep = self.svc.report(since=utc(8, 30))                  # "today" starts at 08:30
        by_name = {d["device_name"]: d for d in rep["devices"]}
        self.assertEqual(by_name["Router"]["downtime_today_seconds"], 25 * 60)
        self.assertEqual(by_name["Router"]["longest_outage_seconds"], 20 * 60)
        self.assertEqual(by_name["Router"]["incidents"], 2)
        self.assertEqual(by_name["NAS"]["downtime_today_seconds"], 30 * 60)   # 08:30 -> 09:00
        self.assertEqual(by_name["NAS"]["longest_outage_seconds"], 60 * 60)   # whole outage
        s = rep["summary"]
        self.assertEqual(s["downtime_today_seconds"], 55 * 60)
        self.assertEqual(s["longest_outage"]["seconds"], 60 * 60)
        self.assertEqual(s["longest_outage"]["device_name"], "NAS")

    def test_empty_report(self):
        rep = self.svc.report(since=utc(0))
        self.assertEqual(rep["summary"]["downtime_today_seconds"], 0)
        self.assertIsNone(rep["summary"]["longest_outage"])
        self.assertEqual(len(rep["devices"]), 2)

    def test_device_filter_and_newest_first(self):
        self.check(self.dev, Status.OFFLINE, at(9)); self.check(self.dev, Status.ONLINE, at(9, 1))
        self.check(self.other, Status.OFFLINE, at(10)); self.check(self.other, Status.ONLINE, at(10, 1))
        rep = self.svc.report(since=utc(0))
        self.assertEqual([i["device_name"] for i in rep["incidents"]], ["NAS", "Router"])
        only = self.svc.report(since=utc(0), device_id=self.dev.id)
        self.assertEqual([i["device_name"] for i in only["incidents"]], ["Router"])
        self.assertEqual(only["summary"]["incidents_total"], 2)   # stats stay global

    def test_pausing_a_device_closes_its_outage(self):
        self.check(self.dev, Status.OFFLINE, at(10))
        self.svc.close_for_device(self.dev.id)
        self.assertFalse(self.svc.report(since=utc(0))["incidents"][0]["ongoing"])


class IncidentApiTests(unittest.TestCase):
    def setUp(self):
        self.app = create_app(TestConfig)
        self.client = self.app.test_client()
        self.reply = UP
        p = patch("app.services.ping_service.PingService.ping", lambda s, host: self.reply)
        p.start()
        self.addCleanup(p.stop)

    def test_full_cycle_through_the_api(self):
        did = self.client.post("/api/devices", json={"name": "Srv", "host": "10.0.0.5"}).get_json()["id"]
        check = lambda: self.client.post(f"/api/devices/{did}/check")
        check()                                         # online
        self.reply = DOWN; check(); check()             # goes down (one incident, not two)
        data = self.client.get("/api/incidents").get_json()
        self.assertEqual(len(data["incidents"]), 1)
        self.assertTrue(data["incidents"][0]["ongoing"])
        self.assertEqual(data["incidents"][0]["error"], "No reply")
        self.reply = LOSSY; check()                     # replies again (degraded) -> recovered
        data = self.client.get("/api/incidents").get_json()
        self.assertFalse(data["incidents"][0]["ongoing"])
        self.assertEqual(data["summary"]["ongoing"], 0)
        self.assertIsNotNone(data["summary"]["longest_outage"])
        self.assertEqual(data["devices"][0]["incidents"], 1)

    def test_pausing_device_via_api_closes_incident(self):
        did = self.client.post("/api/devices", json={"name": "Srv", "host": "10.0.0.5"}).get_json()["id"]
        self.reply = DOWN
        self.client.post(f"/api/devices/{did}/check")
        self.client.put(f"/api/devices/{did}", json={"name": "Srv", "host": "10.0.0.5", "enabled": False})
        self.assertFalse(self.client.get("/api/incidents").get_json()["incidents"][0]["ongoing"])

    def test_deleting_device_removes_its_incidents(self):
        did = self.client.post("/api/devices", json={"name": "Srv", "host": "10.0.0.5"}).get_json()["id"]
        self.reply = DOWN
        self.client.post(f"/api/devices/{did}/check")
        self.client.delete(f"/api/devices/{did}")
        self.assertEqual(self.client.get("/api/incidents").get_json()["incidents"], [])

    def test_bad_since_is_rejected(self):
        self.assertEqual(self.client.get("/api/incidents?since=yesterday").status_code, 422)

    def test_since_param_is_used(self):
        did = self.client.post("/api/devices", json={"name": "Srv", "host": "10.0.0.5"}).get_json()["id"]
        self.reply = DOWN
        self.client.post(f"/api/devices/{did}/check")
        future = "2999-01-01T00:00:00Z"                  # "today" starts in the future -> nothing counted
        data = self.client.get(f"/api/incidents?since={future}").get_json()
        self.assertEqual(data["summary"]["downtime_today_seconds"], 0)


if __name__ == "__main__":
    unittest.main()
