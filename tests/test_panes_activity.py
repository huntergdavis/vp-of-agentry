"""Read-only pane snapshots: auth, bounded work, isolation and recovery."""

import asyncio
from concurrent.futures import ThreadPoolExecutor
import importlib
import json
import threading
import unittest
from unittest.mock import Mock, patch

from fastapi import HTTPException, Response

server = importlib.import_module("server.app")


class PanesActivityTests(unittest.TestCase):
    def setUp(self):
        self.cache = patch.object(server, "PANES_ACTIVITY_CACHE", {"expires": 0, "data": None})
        self.cache.start()
        self.addCleanup(self.cache.stop)
        self.panes = [
            {"pane_id": "w1:p1", "agent": "codex", "agent_status": "working",
             "tab_label": "Code", "workspace_label": "Project"},
            {"pane_id": "w1:p2", "agent_status": "idle", "tab_label": "Shell"},
        ]
        self.client = Mock()
        self.client.call.side_effect = self.socket_call
        self.flock = patch.object(server, "_flock", return_value=self.client).start()
        self.addCleanup(patch.stopall)

    def socket_call(self, command, **args):
        if command == "list_panes":
            return {"panes": self.panes}
        self.assertEqual(command, "read_pane", "snapshot must never mutate a pane")
        return {"text": "\n".join(f"line {i}" for i in range(60)), "agent_status": "blocked"}

    def snapshot(self):
        response = Response()
        result = server.panes_activity(response, "owner")
        self.assertEqual(response.headers["cache-control"], "no-store")
        return result

    def test_includes_terminals_with_labels_and_bounded_output(self):
        result = self.snapshot()
        self.assertEqual(len(result["panes"]), 2)
        row, shell = result["panes"]
        self.assertEqual((row["pane_id"], row["name"], row["tab_label"], row["workspace"], row["agent"]),
                         ("w1:p1", "Code", "Code", "Project", "codex"))
        self.assertEqual(row["status"], "waiting")
        self.assertIsNone(shell["agent"])
        self.assertEqual(len(row["text"].splitlines()), 40)
        self.assertTrue(row["text"].startswith("line 20"))
        self.client.call.assert_any_call("read_pane", target="w1:p2", lines=40)

    def test_snapshot_cache_expiry_removes_closed_panes(self):
        with patch.object(server.time, "monotonic", return_value=100):
            self.snapshot()
            self.snapshot()
        self.assertEqual(self.client.call.call_count, 3)
        self.panes = []
        with patch.object(server.time, "monotonic", return_value=105):
            self.assertEqual(self.snapshot()["panes"], [])
        self.assertEqual(self.client.call.call_count, 4)

    def test_concurrent_browsers_share_one_refresh(self):
        entered, release = threading.Event(), threading.Event()
        def blocked(command, **args):
            if command == "list_panes":
                entered.set()
                self.assertTrue(release.wait(3))
            return self.socket_call(command, **args)
        self.client.call.side_effect = blocked
        with ThreadPoolExecutor(max_workers=6) as callers:
            futures = [callers.submit(self.snapshot) for _ in range(6)]
            self.assertTrue(entered.wait(3))
            release.set()
            self.assertTrue(all(future.result()["panes"] for future in futures))
        self.assertEqual(self.client.call.call_count, 3)

    def test_pane_failure_is_local_generic_and_cached(self):
        def failed(command, **args):
            if args.get("target") == "w1:p2":
                raise RuntimeError("sensitive upstream exception")
            return self.socket_call(command, **args)
        self.client.call.side_effect = failed
        result = self.snapshot()
        self.assertIsNone(result["panes"][0]["error"])
        self.assertEqual(result["panes"][1]["error"], "Pane output unavailable")
        self.assertNotIn("sensitive", json.dumps(result))
        self.snapshot()
        self.assertEqual(self.client.call.call_count, 3)

    def test_daemon_failure_is_cached_and_recovers(self):
        self.flock.side_effect = RuntimeError("sensitive daemon exception")
        for _ in range(2):
            with self.assertRaises(HTTPException) as error:
                self.snapshot()
            self.assertEqual(error.exception.status_code, 503)
            self.assertEqual(error.exception.detail, "Herdr panes unavailable")
        self.assertEqual(self.flock.call_count, 1)
        self.flock.side_effect = None
        server.PANES_ACTIVITY_CACHE["expires"] = 0
        self.assertEqual(len(self.snapshot()["panes"]), 2)

    def test_single_pane_activity_keeps_existing_contract(self):
        with patch.object(server, "_panes", return_value=self.panes):
            result = server.activity("pane-w1-p1", "owner")
        self.assertEqual(result["channel"], "pane-w1-p1")
        self.assertEqual(result["status"], "waiting")
        self.client.call.assert_called_once_with("read_pane", target="w1:p1", lines=80)

    def test_oversized_output_and_missing_status(self):
        def oversized(command, **args):
            return {"panes": self.panes} if command == "list_panes" else {"text": "x" * 100000}
        self.client.call.side_effect = oversized
        row = self.snapshot()["panes"][0]
        self.assertEqual(len(row["text"]), 32000)
        self.assertEqual(row["status"], "working")

    def test_http_auth_before_socket_access_and_cross_origin_denial(self):
        async def request(headers):
            sent = []
            async def receive():
                return {"type": "http.request", "body": b"", "more_body": False}
            async def send(message):
                sent.append(message)
            await server.app({"type": "http", "asgi": {"version": "3.0"}, "http_version": "1.1",
                              "method": "GET", "scheme": "http", "path": "/api/panes/activity",
                              "raw_path": b"/api/panes/activity", "query_string": b"",
                              "server": ("localhost", 80), "client": ("127.0.0.1", 1234),
                              "headers": [(b"host", b"localhost"), *headers]}, receive, send)
            return sent[0]["status"]
        with patch.object(server, "_auth_record", return_value={"token": "synthetic-test-token"}):
            self.assertEqual(asyncio.run(request([])), 401)
            self.flock.assert_not_called()
            auth = [(b"authorization", b"Bearer synthetic-test-token")]
            self.assertEqual(asyncio.run(request(auth + [(b"origin", b"http://elsewhere")])), 403)
            self.flock.assert_not_called()
            self.assertEqual(asyncio.run(request(auth)), 200)


if __name__ == "__main__":
    unittest.main()
