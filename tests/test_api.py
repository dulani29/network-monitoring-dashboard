import unittest
from unittest.mock import patch

from app import create_app
from app.services.ping_service import PingResult
from config import TestConfig


def fake_ping(self, host):
    if host == "10.0.0.99":
        return PingResult(False, 3, 0, 100.0, error="No reply")
    if host == "10.0.0.50":
        return PingResult(True, 3, 2, 33.3, 10.0, 12.0, 14.0)
    return PingResult(True, 3, 3, 0.0, 1.0, 2.0, 3.0)


class ApiTests(unittest.TestCase):
    def setUp(self):
        self.app = create_app(TestConfig)
        self.client = self.app.test_client()
        p = patch("app.services.ping_service.PingService.ping", fake_ping)
        p.start()
        self.addCleanup(p.stop)

    def add(self, name, host, **kw):
        return self.client.post("/api/devices", json={"name": name, "host": host, **kw})

    def test_crud(self):
        r = self.add("Router", "192.168.1.1", device_type="router")
        self.assertEqual(r.status_code, 201)
        did = r.get_json()["id"]
        self.assertEqual(self.add("Dup", "192.168.1.1").status_code, 409)
        self.assertEqual(self.client.put(f"/api/devices/{did}", json={"name": "R2", "host": "192.168.1.1"}).status_code, 200)
        self.assertEqual(self.client.delete(f"/api/devices/{did}").status_code, 204)
        self.assertEqual(self.client.delete(f"/api/devices/{did}").status_code, 404)

    def test_validation(self):
        r = self.add("", "bad host!")
        self.assertEqual(r.status_code, 422)
        self.assertIn("host", r.get_json()["fields"])

    def test_status_classification_and_summary(self):
        self.add("Up", "10.0.0.1"); self.add("Lossy", "10.0.0.50"); self.add("Down", "10.0.0.99")
        res = self.client.post("/api/check-all").get_json()
        self.assertEqual(res["checked"], 3)
        s = self.client.get("/api/summary").get_json()
        self.assertEqual((s["online"], s["degraded"], s["offline"]), (1, 1, 1))
        devs = {d["name"]: d for d in self.client.get("/api/devices").get_json()}
        self.assertEqual(devs["Down"]["status"], "offline")
        self.assertEqual(devs["Up"]["uptime_pct"], 100.0)

    def test_history_and_csv(self):
        did = self.add("Up", "10.0.0.1").get_json()["id"]
        self.client.post(f"/api/devices/{did}/check")
        self.client.post(f"/api/devices/{did}/check")
        self.assertEqual(len(self.client.get(f"/api/devices/{did}/history").get_json()), 2)
        csv_resp = self.client.get("/api/export/history.csv")
        self.assertEqual(csv_resp.mimetype, "text/csv")
        self.assertEqual(len(csv_resp.get_data(as_text=True).strip().splitlines()), 3)

    def test_series_endpoint(self):
        did = self.add("Up", "10.0.0.1").get_json()["id"]
        for _ in range(3):
            self.client.post(f"/api/devices/{did}/check")
        data = self.client.get("/api/history/series?limit=2").get_json()
        self.assertEqual(len(data[str(did)]), 2)

    def test_auto_monitor_settings(self):
        r = self.client.post("/api/monitor/auto", json={"enabled": True, "interval": 1}).get_json()
        self.assertTrue(r["enabled"])
        self.assertEqual(r["interval"], 5)   # clamped to min interval

    def test_dashboard_page(self):
        self.assertEqual(self.client.get("/").status_code, 200)


if __name__ == "__main__":
    unittest.main()
