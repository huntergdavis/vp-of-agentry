"""An unavailable roster is not evidence of zero lanes."""
import importlib
import subprocess
import unittest
from types import SimpleNamespace
from unittest.mock import patch

server = importlib.import_module("server.app")


class FleetAvailabilityTests(unittest.TestCase):
    def setUp(self):
        p = patch.object(server, "_FLEET_CACHE", {"at": 0, "payload": None})
        p.start()
        self.addCleanup(p.stop)

    def test_cli_refusal_is_visible_and_cached(self):
        result = SimpleNamespace(returncode=1, stdout="", stderr="identity refused")
        with patch.object(server.subprocess, "run", return_value=result) as run:
            first = server.api_fleet()
            second = server.api_fleet()
        self.assertEqual("unavailable", first["state"])
        self.assertEqual("identity refused", first["error"])
        self.assertIsNone(first["count"])
        self.assertTrue(first["generated_at"])
        self.assertIs(first, second)
        self.assertEqual(1, run.call_count)

    def test_timeout_is_unavailable(self):
        with patch.object(server.subprocess, "run", side_effect=subprocess.TimeoutExpired("dunkingsheep", 15)):
            result = server.api_fleet()
        self.assertEqual("unavailable", result["state"])
        self.assertIn("timed out", result["error"])

    def test_malformed_success_is_not_empty(self):
        for body in ("not json", "{}", "[]", '{"panes": null}', '{"panes": [null]}'):
            with self.subTest(body=body), patch.object(server, "_FLEET_CACHE", {"at": 0, "payload": None}):
                with patch.object(server.subprocess, "run", return_value=SimpleNamespace(returncode=0, stdout=body, stderr="")):
                    result = server.api_fleet()
                self.assertEqual("unavailable", result["state"])
                self.assertIsNone(result["count"])

    def test_real_empty_roster_is_a_success(self):
        with patch.object(server.subprocess, "run", return_value=SimpleNamespace(returncode=0, stdout='{"panes":[]}', stderr="")), \
             patch.object(server, "_pending_by_pane", return_value={}), \
             patch.object(server.os.path, "expanduser", return_value="/nonexistent-test-fleet"):
            result = server.api_fleet()
        self.assertEqual("ok", result["state"])
        self.assertEqual(0, result["count"])
        self.assertEqual([], result["rows"])
