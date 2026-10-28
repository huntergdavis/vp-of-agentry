"""An unavailable roster is not evidence of zero lanes."""
import importlib
import json
import subprocess
import unittest
from types import SimpleNamespace
from unittest.mock import patch

server = importlib.import_module("server.app")


class FleetAvailabilityTests(unittest.TestCase):
    def test_pending_counts_use_global_json_option_before_nested_command(self):
        result = SimpleNamespace(returncode=0, stderr="", stdout='''{"pending": [
            {"pane_id": "%2"}, {"pane_id": "%2"}, {"pane_id": "%35"}, {}
        ]}''')
        with patch.object(server.subprocess, "run", return_value=result) as run:
            counts = server._pending_by_pane()
        self.assertEqual({"%2": 2, "%35": 1}, counts)
        run.assert_called_once_with(
            ["dunkingsheep", "--json", "owner", "stats"],
            capture_output=True, text=True, timeout=10,
        )

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


    def fleet_with_pending_result(self, pending_result):
        def run(argv, **kwargs):
            if argv == ["dunkingsheep", "panes", "--json"]:
                return SimpleNamespace(returncode=0, stderr="", stdout=json.dumps({
                    "panes": [{"pane_id": "%35", "agent": "codex", "label": "fixture"}]
                }))
            self.assertEqual(["dunkingsheep", "--json", "owner", "stats"], argv)
            if isinstance(pending_result, Exception):
                raise pending_result
            return pending_result

        with patch.object(server.subprocess, "run", side_effect=run), \
             patch.object(server, "_FLEET_CACHE", {"at": 0, "payload": None}), \
             patch.object(server, "_capability", return_value={}), \
             patch.object(server, "_desk_token", return_value=""), \
             patch.object(server.os.path, "expanduser", return_value="/nonexistent-test-fleet"), \
             patch("fleet_inventory.collect", return_value={"state": "ok", "rows": []}):
            return server.api_fleet()

    def test_failed_pending_read_is_unknown_not_zero_in_fleet(self):
        failures = [
            SimpleNamespace(returncode=1, stderr="refused", stdout='{"pending": []}'),
            subprocess.TimeoutExpired("dunkingsheep", 10),
            OSError("missing executable"),
        ]
        for body in ("", "not json", "{}", "[]", "null", '{"pending": null}',
                     '{"pending": {}}', '{"pending": [null]}',
                     '{"pending": [{"pane_id": []}]}',
                     '{"ok": false, "pending": []}'):
            failures.append(SimpleNamespace(returncode=0, stderr="", stdout=body))
        for result in failures:
            with self.subTest(result=result):
                fleet = self.fleet_with_pending_result(result)
                self.assertEqual("ok", fleet["state"])
                self.assertEqual(1, fleet["count"])
                self.assertIsNone(fleet["rows"][0]["pending"])
                self.assertEqual("unknown", fleet["rows"][0]["pending_state"])

    def test_valid_pending_read_preserves_counts_and_real_zero(self):
        for pending, expected in (([], 0), ([{"pane_id": "%2"}], 0),
                                  ([{"pane_id": "%35"}] * 2, 2)):
            with self.subTest(pending=pending):
                result = SimpleNamespace(returncode=0, stderr="", stdout=json.dumps({"pending": pending}))
                fleet = self.fleet_with_pending_result(result)
                self.assertEqual(expected, fleet["rows"][0]["pending"])
                self.assertEqual("ok", fleet["rows"][0]["pending_state"])
