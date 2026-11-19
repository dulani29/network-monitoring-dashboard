import ipaddress
import threading
import unittest
from unittest.mock import patch

from app import create_app
from app.services.network_utils import parse_arp_output
from app.services.ping_service import PingResult
from app.services.scanner_service import ScannerService, ScanBusyError
from app.services.validators import ValidationError, validate_scan_payload
from config import TestConfig

LIVE = {"192.168.1.1", "192.168.1.20", "192.168.1.77"}


def fake_ping(self, host):
    if host in LIVE:
        return PingResult(True, 1, 1, 0.0, 2.0, 2.0, 2.0)
    return PingResult(False, 1, 0, 100.0, error="No reply")


class FakeDevices:
    def __init__(self, hosts=()):
        self.hosts = hosts

    def list(self):
        return [type("D", (), {"host": h})() for h in self.hosts]


class FakePing:
    def ping(self, host):
        return fake_ping(None, host)


class ScanValidationTests(unittest.TestCase):
    def ok(self, subnet, **kw):
        return validate_scan_payload({"subnet": subnet, "authorized": True, **kw})

    def fails(self, payload, field):
        with self.assertRaises(ValidationError) as cm:
            validate_scan_payload(payload)
        self.assertIn(field, cm.exception.errors)

    def test_accepts_private_subnets(self):
        self.assertEqual(str(self.ok("192.168.1.0/24")), "192.168.1.0/24")
        self.assertEqual(str(self.ok("10.1.2.0/23")), "10.1.2.0/23")
        self.assertEqual(str(self.ok("172.20.0.0/22")), "172.20.0.0/22")

    def test_host_address_is_normalised_to_its_network(self):
        self.assertEqual(str(self.ok("192.168.1.57/24")), "192.168.1.0/24")

    def test_rejects_public_and_special_ranges(self):
        for bad in ("8.8.8.0/24", "1.1.1.0/24", "127.0.0.0/24", "169.254.0.0/24", "172.32.0.0/24"):
            self.fails({"subnet": bad, "authorized": True}, "subnet")

    def test_rejects_too_big_or_malformed(self):
        for bad in ("10.0.0.0/8", "192.168.0.0/16", "192.168.1.0/21", "192.168.1.1/32",
                    "192.168.1.0", "", "nonsense/24", "fd00::/64", "192.168.1.0/24; rm -rf /"):
            self.fails({"subnet": bad, "authorized": True}, "subnet")

    def test_requires_explicit_authorisation(self):
        self.fails({"subnet": "192.168.1.0/24"}, "authorized")
        self.fails({"subnet": "192.168.1.0/24", "authorized": "yes"}, "authorized")
        self.fails({"subnet": "192.168.1.0/24", "authorized": False}, "authorized")


class ArpParsingTests(unittest.TestCase):
    def test_linux_ip_neigh(self):
        out = ("192.168.1.1 dev eth0 lladdr AA:BB:CC:DD:EE:FF REACHABLE\n"
               "192.168.1.9 dev eth0  FAILED\n"
               "fe80::1 dev eth0 lladdr aa:bb:cc:dd:ee:01 router STALE\n")
        self.assertEqual(parse_arp_output(out), {"192.168.1.1": "aa:bb:cc:dd:ee:ff"})

    def test_macos_unpadded_octets(self):
        out = "? (192.168.1.20) at 0:1a:2b:3c:4:5 on en0 ifscope [ethernet]\n? (192.168.1.99) at (incomplete) on en0\n"
        self.assertEqual(parse_arp_output(out), {"192.168.1.20": "00:1a:2b:3c:04:05"})

    def test_windows_dashes_and_headers(self):
        out = ("Interface: 192.168.1.5 --- 0x4\n  Internet Address      Physical Address      Type\n"
               "  192.168.1.1           aa-bb-cc-dd-ee-ff     dynamic\n"
               "  192.168.1.255         ff-ff-ff-ff-ff-ff     static\n")
        self.assertEqual(parse_arp_output(out), {"192.168.1.1": "aa:bb:cc:dd:ee:ff"})


class ScannerServiceTests(unittest.TestCase):
    def make(self, existing=(), **kw):
        defaults = dict(enrich=True,
                        resolve=lambda ip: {"192.168.1.20": "johns-iphone.lan"}.get(ip),
                        arp_table=lambda: {"192.168.1.20": "aa:bb:cc:00:00:20"},
                        gateway=lambda: "192.168.1.1",
                        local_ips=lambda: {"192.168.1.77"})
        defaults.update(kw)
        return ScannerService(FakeDevices(existing), FakePing(), max_workers=8, **defaults)

    def scan(self, svc, cidr="192.168.1.0/24"):
        svc.start(ipaddress.ip_network(cidr))
        svc.join(10)
        return svc.snapshot()

    def test_finds_live_hosts_sorted_and_enriched(self):
        snap = self.scan(self.make())
        self.assertEqual(snap["state"], "done")
        self.assertEqual((snap["total"], snap["scanned"]), (254, 254))
        by_ip = {d["host"]: d for d in snap["devices"]}
        self.assertEqual([d["host"] for d in snap["devices"]], ["192.168.1.1", "192.168.1.20", "192.168.1.77"])
        self.assertEqual(by_ip["192.168.1.1"]["suggested_type"], "router")
        self.assertEqual(by_ip["192.168.1.1"]["suggested_name"], "Router (gateway)")
        self.assertEqual(by_ip["192.168.1.20"]["suggested_name"], "johns-iphone")
        self.assertEqual(by_ip["192.168.1.20"]["mac"], "aa:bb:cc:00:00:20")
        self.assertEqual(by_ip["192.168.1.77"]["suggested_name"], "This computer")
        self.assertIsNone(by_ip["192.168.1.1"]["mac"])

    def test_only_scans_host_addresses(self):
        seen = []
        class Recorder:
            def ping(self, host):
                seen.append(host)
                return fake_ping(None, host)
        svc = ScannerService(FakeDevices(), Recorder(), enrich=False)
        svc.start(ipaddress.ip_network("192.168.1.0/30"))
        svc.join(5)
        self.assertEqual(sorted(seen), ["192.168.1.1", "192.168.1.2"])    # no .0 network / .3 broadcast

    def test_flags_devices_already_monitored(self):
        snap = self.scan(self.make(existing=["192.168.1.20"]))
        flags = {d["host"]: d["already_added"] for d in snap["devices"]}
        self.assertEqual(flags, {"192.168.1.1": False, "192.168.1.20": True, "192.168.1.77": False})

    def test_enrichment_failures_do_not_break_the_scan(self):
        def boom(*a):
            raise RuntimeError("dns down")
        snap = self.scan(self.make(resolve=boom, arp_table=boom, gateway=boom, local_ips=boom))
        self.assertEqual(snap["state"], "done")
        self.assertEqual(len(snap["devices"]), 3)
        self.assertEqual(snap["devices"][0]["suggested_name"], "Device 192.168.1.1")

    def test_second_scan_while_running_is_refused(self):
        gate = threading.Event()
        class Slow:
            def ping(self, host):
                gate.wait(5)
                return fake_ping(None, host)
        svc = ScannerService(FakeDevices(), Slow(), max_workers=4, enrich=False)
        svc.start(ipaddress.ip_network("192.168.1.0/29"))
        self.assertEqual(svc.snapshot()["state"], "running")
        with self.assertRaises(ScanBusyError):
            svc.start(ipaddress.ip_network("192.168.1.0/29"))
        gate.set()
        svc.join(5)
        svc.start(ipaddress.ip_network("192.168.1.0/29"))      # free again once finished
        svc.join(5)

    def test_cancel_stops_early(self):
        started, gate = threading.Event(), threading.Event()
        class Blocking:
            def ping(self, host):
                started.set()
                gate.wait(5)
                return fake_ping(None, host)
        svc = ScannerService(FakeDevices(), Blocking(), max_workers=2, enrich=False)
        svc.start(ipaddress.ip_network("192.168.1.0/24"))
        started.wait(5)
        svc.cancel()
        gate.set()
        svc.join(10)
        snap = svc.snapshot()
        self.assertEqual(snap["state"], "cancelled")
        self.assertLess(len(snap["devices"]), 3 + 1)

    def test_idle_before_any_scan(self):
        self.assertEqual(self.make().snapshot(), {"state": "idle", "devices": []})


class ScanApiTests(unittest.TestCase):
    def setUp(self):
        self.app = create_app(TestConfig)
        self.client = self.app.test_client()
        for target in ("app.services.ping_service.PingService.ping",):
            p = patch(target, fake_ping)
            p.start()
            self.addCleanup(p.stop)
        self.scanner = self.app.extensions["netmon"]["scanner"]

    def start(self, **body):
        body.setdefault("subnet", "192.168.1.0/24")
        body.setdefault("authorized", True)
        return self.client.post("/api/scan", json=body)

    def test_scan_then_add_found_device(self):
        self.assertEqual(self.client.get("/api/scan").get_json()["state"], "idle")
        r = self.start()
        self.assertEqual(r.status_code, 202)
        self.scanner.join(10)
        snap = self.client.get("/api/scan").get_json()
        self.assertEqual(snap["state"], "done")
        found = {d["host"] for d in snap["devices"]}
        self.assertEqual(found, LIVE)

        pick = snap["devices"][1]
        add = self.client.post("/api/devices", json={
            "name": pick["suggested_name"], "host": pick["host"], "device_type": pick["suggested_type"]})
        self.assertEqual(add.status_code, 201)
        after = {d["host"]: d["already_added"] for d in self.client.get("/api/scan").get_json()["devices"]}
        self.assertTrue(after[pick["host"]])
        self.assertEqual(sum(after.values()), 1)

    def test_rejects_unauthorised_and_public_scans(self):
        r = self.start(authorized=False)
        self.assertEqual(r.status_code, 422)
        self.assertIn("authorized", r.get_json()["fields"])
        r = self.start(subnet="8.8.8.0/24")
        self.assertEqual(r.status_code, 422)
        self.assertIn("subnet", r.get_json()["fields"])
        self.assertEqual(self.client.get("/api/scan").get_json()["state"], "idle")   # nothing started

    def test_default_subnet_endpoint(self):
        with patch("app.services.scanner_service.detect_local_subnet", return_value="192.168.7.0/24"):
            self.assertEqual(self.client.get("/api/scan/default").get_json(), {"subnet": "192.168.7.0/24"})

    def test_busy_returns_409(self):
        gate = threading.Event()
        def slow(self_, host):
            gate.wait(5)
            return fake_ping(None, host)
        with patch("app.services.ping_service.PingService.ping", slow):
            self.assertEqual(self.start(subnet="192.168.1.0/29").status_code, 202)
            self.assertEqual(self.start(subnet="192.168.1.0/29").status_code, 409)
            gate.set()
            self.scanner.join(10)

    def test_cancel_endpoint(self):
        self.start()
        self.assertEqual(self.client.post("/api/scan/cancel").status_code, 200)
        self.scanner.join(10)
        self.assertIn(self.client.get("/api/scan").get_json()["state"], ("cancelled", "done"))


if __name__ == "__main__":
    unittest.main()
