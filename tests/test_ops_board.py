"""The operations board is a deterministic projection, never a written summary.

These tests pin the three properties the owner asked for: the board reads
Dunking Sheep and the operations database, a source that cannot be read stays
unavailable instead of becoming a zero, and the board refreshes on a timer
without any model in the loop.
"""

import tempfile
import unittest
from datetime import datetime, timezone
from pathlib import Path
from unittest.mock import patch

import ops_board
import ops_metrics

NOW = datetime(2026, 10, 19, 18, 0, 0, tzinfo=timezone.utc)
EXPECTED_CALLS = {"task_list", "list_dunks", "list_panes", "health"}


class FakeClient:
    """A scripted Dunking Sheep client that records every call."""

    def __init__(self, responses=None, failures=()):
        self.responses = responses or {}
        self.failures = set(failures)
        self.calls = []

    def call(self, name, **kwargs):
        self.calls.append((name, kwargs))
        if name in self.failures:
            raise RuntimeError("daemon unavailable")
        return self.responses.get(name)


def sample_client():
    return FakeClient({
        "task_list": {"scope": "visible", "pane_id": "wV:p4", "tasks": [
            {"id": "t18", "title": "Dashboard overhaul", "status": "in_progress",
             "priority": "high", "scope": "global", "assignees": ["wV:p4"],
             "created_at": NOW.timestamp() - 3600, "updated_at": NOW.timestamp(),
             "lease_expires_at": NOW.timestamp() + 600, "blocked_by": [], "eligible": True,
             "claimable": True, "attempts": 0},
            {"id": "t6", "title": "Advance strict C", "status": "open",
             "priority": "high", "scope": "global", "assignees": [],
             "created_at": NOW.timestamp() - 7200, "updated_at": NOW.timestamp() - 7200,
             "lease_expires_at": None, "blocked_by": ["t99"], "eligible": False,
             "claimable": True, "attempts": 0},
            {"id": "t2", "title": "Switch build", "status": "blocked",
             "priority": "medium", "scope": "global", "assignees": ["crackdown-switch"],
             "created_at": NOW.timestamp() - 900, "updated_at": NOW.timestamp() - 900,
             "lease_expires_at": None, "blocked_by": [], "eligible": False,
             "claimable": False, "attempts": 1},
        ]},
        "task_metrics": {"window": {"seconds": 3600}, "throughput": {"created": 2, "completed": 1},
                         "latency_ms": {"completion": {"count": 1, "avg": 10}}, "by_actor": {}},
        "inbox_stats": {"mailboxes": [
            {"mailbox": "wV:p4", "destination": "webui-dash", "unread": 2, "total": 5,
             "oldest_unread_s": 120},
            {"mailbox": "w9:pH", "destination": "vp of agentry", "unread": 1, "total": 3,
             "oldest_unread_s": 60},
            {"mailbox": "wM:p1", "destination": "wM:p1", "unread": 0, "total": 9,
             "oldest_unread_s": None},
        ]},
        "list_dunks": {"dunks": [
            {"id": "d52", "name": "keep-moving", "target_pane_id": "wR:p3",
             "target_label": "ds4 poolrad", "interval_minutes": 45.0, "running": True,
             "status": "Next: 02:41", "next_send_in_s": 160, "send_count": 2,
             "skip_count": 49, "hold_count": 0},
            {"id": "d60", "name": "stopped", "target_pane_id": "w9:pH", "target_label": "vp",
             "interval_minutes": 30.0, "running": False, "status": "Stopped",
             "next_send_in_s": None, "send_count": 1, "skip_count": 0, "hold_count": 0},
        ]},
        "list_panes": {"panes": [
            {"pane_id": "wR:p3", "agent": "pi", "agent_status": "working",
             "workspace_label": "poolrad-decomp", "tab_label": "ds4 poolrad", "is_self": False},
            {"pane_id": "wV:p4", "agent": "pi", "agent_status": "idle",
             "workspace_label": "vp-of-agentry", "tab_label": "webui-dash", "is_self": True},
        ]},
        "status": {"version": "2.20.0", "uptime_s": 1200, "herdr_available": True,
                   "queued_messages": 0, "inbox_unread": 3, "task_followers": 0,
                   "quarantined_mailboxes": None, "dunkers": 2, "running": 1, "message": None},
        "health": {"ok": True, "problems": [], "repairs": [], "duration_ms": 12,
                   "checks": {"memory": {"ok": True, "sources": 488, "chunks": 262299,
                                         "queue_depth": 0},
                              "stale_leases": {"expired_leases": 0},
                              "wal_bytes": 0, "disk_free_bytes": 10 ** 11}},
    })


class OpsBoardTests(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory()
        self.addCleanup(self.temporary.cleanup)
        budget = patch("ops_budget.read_usage", return_value=[])
        budget.start()
        self.addCleanup(budget.stop)
        self.conn = ops_metrics.connect(Path(self.temporary.name) / "ops.sqlite3")
        self.addCleanup(self.conn.close)

    def test_compact_sections_read_only_actionable_sources(self):
        client = sample_client()
        board = ops_board.build(client, self.conn, now=NOW)
        self.assertEqual(EXPECTED_CALLS, {name for name, _ in client.calls})
        self.assertEqual({"generated_at", "interval_s", "no_model", "brief", "attention", "reference", "budget"}, set(board))
        self.assertTrue(board["no_model"])
        self.assertEqual(1, board["brief"]["tasks"]["open"])
        self.assertEqual(1, board["brief"]["lanes"]["working"])
        for source in board["brief"].values():
            self.assertEqual("ok", source["state"])
            self.assertEqual(ops_board._iso(NOW), source["generated_at"])
            self.assertTrue(source["source"])

    def test_missing_sources_remain_unavailable_not_zero(self):
        client = sample_client()
        client.failures = {"task_list", "list_panes"}
        board = ops_board.build(client, self.conn, now=NOW)
        self.assertIsNone(board["brief"]["tasks"]["open"])
        self.assertIsNone(board["brief"]["lanes"]["idle"])
        self.assertEqual("unavailable", board["brief"]["tasks"]["state"])
        self.assertEqual({"tasks", "panes", "host"}, {a["source"] for a in board["attention"]["alarms"]})

    def test_unknown_lanes_are_not_idle_and_shells_are_excluded(self):
        client = sample_client()
        client.responses["list_panes"]["panes"] += [
            {"pane_id": "%unknown", "agent": "codex", "agent_status": "unknown"},
            {"pane_id": "%shell", "agent": "", "agent_status": "idle"},
        ]
        lanes = ops_board.build(client, self.conn, now=NOW)["brief"]["lanes"]
        self.assertEqual((1, 1, 1), (lanes["working"], lanes["idle"], lanes["unknown"]))

    def test_lane_provenance_survives_projection_to_operations(self):
        client = sample_client()
        pane = client.responses["list_panes"]["panes"][0]
        pane.update(agent_status="working", agent_status_source="codex declared turns",
                    agent_status_reason=None, agent_status_inferred=True)
        rows = ops_board.build(client, self.conn, now=NOW)["reference"]["lanes"]["items"]
        row = next(row for row in rows if row["pane_id"] == pane["pane_id"])
        for key in ("agent_status", "agent_status_source", "agent_status_reason", "agent_status_inferred"):
            self.assertEqual(pane[key], row[key])

    def test_only_explicit_owner_tasks_require_owner(self):
        client = sample_client()
        client.responses["task_list"]["tasks"][0]["assignees"] = ["owner"]
        board = ops_board.build(client, self.conn, now=NOW)
        self.assertEqual(1, board["brief"]["tasks"]["owner"])
        self.assertEqual(["t18"], [t["id"] for t in board["attention"]["owner"]["items"]])
        # A blocked agent task is not silently reclassified as an owner decision.
        self.assertNotIn("t2", [t["id"] for t in board["attention"]["owner"]["items"]])

    def test_health_and_running_schedule_failures_are_visible(self):
        client = sample_client()
        client.responses["health"]["problems"] = ["dispatcher stale"]
        client.responses["list_dunks"]["dunks"][0]["last_error"] = "send failed"
        board = ops_board.build(client, self.conn, now=NOW)
        text = " ".join(a["text"] for a in board["attention"]["alarms"])
        self.assertIn("dispatcher stale", text)
        self.assertIn("send failed", text)

    def test_task_reference_keeps_ages_and_dependencies(self):
        board = ops_board.build(sample_client(), self.conn, now=NOW)
        items = {item["id"]: item for item in board["reference"]["tasks"]["items"]}
        self.assertEqual(3600, items["t18"]["age_s"])
        self.assertEqual(600, items["t18"]["lease_expires_in_s"])
        self.assertEqual(["t99"], items["t6"]["blocked_by"])

    def test_cache_serves_the_snapshot_and_keeps_it_when_a_refresh_fails(self):
        cache = ops_board.BoardCache(interval_s=30)
        with patch.object(ops_board.BoardCache, "_build",
                          return_value={"generated_at": ops_board._iso(NOW), "headline": {}}):
            first = cache.refresh()
        self.assertEqual({"generated_at": ops_board._iso(NOW), "headline": {}}, first)
        with patch.object(ops_board.BoardCache, "_build", side_effect=RuntimeError("boom")):
            stale = cache.snapshot(max_age_s=0)
        self.assertEqual("RuntimeError", stale["refresh_error"])
        self.assertEqual({}, stale["headline"])

    def test_budget_snapshot_updates_on_each_board_cycle(self):
        import threading
        import ops_budget
        ready = threading.Event()
        calls = []
        cache = ops_board.BoardCache(interval_s=0.01)

        def usage():
            calls.append(1)
            return [dict(provider="codex", status="ok", meaning="percent_used",
                         measured_at=NOW.timestamp(), windows=[dict(name="weekly", percent_used=len(calls))])]

        def build(_cache):
            conn = ops_metrics.connect(Path(self.temporary.name) / "timer.sqlite3")
            try:
                result = ops_board.build(sample_client(), conn, now=NOW)
                if len(calls) >= 2:
                    ready.set()
                return result
            finally:
                conn.close()

        with patch.object(ops_budget, "read_usage", side_effect=usage), patch.object(ops_board.BoardCache, "_build", build):
            cache.start()
            try:
                self.assertTrue(ready.wait(3), "budget collector did not run on successive cycles")
            finally:
                cache.stop()
        self.assertGreaterEqual(len(calls), 2)
        self.assertEqual(len(calls), cache._snapshot["budget"]["providers"][0]["windows"][0]["percent_used"])

    def test_the_timer_refreshes_without_any_model_call(self):
        cache = ops_board.BoardCache(interval_s=10)
        builds = []

        def build(self):
            builds.append(1)
            return {"generated_at": ops_board._iso(NOW), "headline": {"task_depth": len(builds)}}

        with patch.object(ops_board.BoardCache, "_build", build):
            cache.start()
            cache.stop()
        self.assertTrue(cache._thread is None)


if __name__ == "__main__":
    unittest.main()
