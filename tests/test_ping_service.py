import unittest
from unittest.mock import patch, MagicMock

from app.services.ping_service import PingService
from app.services.validators import is_valid_host

LINUX_OK = """PING 8.8.8.8 (8.8.8.8) 56(84) bytes of data.
64 bytes from 8.8.8.8: icmp_seq=1 ttl=118 time=15.2 ms
64 bytes from 8.8.8.8: icmp_seq=2 ttl=118 time=14.8 ms
64 bytes from 8.8.8.8: icmp_seq=3 ttl=118 time=16.0 ms
"""
PARTIAL = """64 bytes from 10.0.0.2: icmp_seq=0 ttl=64 time=2.0 ms
Request timeout for icmp_seq 1
"""
WINDOWS = "Reply from 192.168.1.1: bytes=32 time<1ms TTL=64\nReply from 192.168.1.1: bytes=32 time=3ms TTL=64\n"


class PingParsingTests(unittest.TestCase):
    def test_all_replies(self):
        r = PingService.parse_output(LINUX_OK, 3)
        self.assertTrue(r.reachable)
        self.assertEqual(r.packet_loss, 0.0)
        self.assertAlmostEqual(r.avg_ms, 15.33, places=1)
        self.assertEqual(r.min_ms, 14.8)

    def test_partial_loss(self):
        r = PingService.parse_output(PARTIAL, 2)
        self.assertTrue(r.reachable)
        self.assertEqual(r.packet_loss, 50.0)

    def test_windows_format(self):
        r = PingService.parse_output(WINDOWS, 2)
        self.assertTrue(r.reachable)
        self.assertEqual(r.max_ms, 3.0)

    def test_no_reply(self):
        r = PingService.parse_output("Request timeout", 3)
        self.assertFalse(r.reachable)
        self.assertEqual(r.packet_loss, 100.0)

    def test_ping_missing_binary(self):
        with patch("subprocess.run", side_effect=FileNotFoundError):
            r = PingService().ping("8.8.8.8")
        self.assertFalse(r.reachable)
        self.assertIn("not found", r.error)

    def test_ping_runs_without_shell(self):
        proc = MagicMock(stdout=LINUX_OK, stderr="", returncode=0)
        with patch("subprocess.run", return_value=proc) as run:
            PingService().ping("8.8.8.8")
        self.assertFalse(run.call_args.kwargs["shell"])
        self.assertIsInstance(run.call_args.args[0], list)


class ValidatorTests(unittest.TestCase):
    def test_valid(self):
        for h in ("192.168.1.1", "::1", "router.local", "my-server"):
            self.assertTrue(is_valid_host(h), h)

    def test_invalid(self):
        for h in ("", "-c 100", "8.8.8.8; rm -rf /", "a b", "bad_host!", "$(id)"):
            self.assertFalse(is_valid_host(h), h)


if __name__ == "__main__":
    unittest.main()
