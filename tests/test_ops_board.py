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
EXPECTED_CALLS = {"task_list", "task_metrics", "inbox_stats", "list_dunks",
                  "list_panes", "status", "health"}


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
        self.conn = ops_metrics.connect(Path(self.temporary.name) / "ops.sqlite3")
        self.addCleanup(self.conn.close)

    def record_accounting(self, strict=225, identities=273, ceiling=815):
        ops_metrics.record_accounting(self.conn, {
            "commit_oid": "a" * 40, "strict_full_c": strict,
            "verified_game_identities": identities, "ceiling": ceiling,
            "bound_kind": "upper_bound", "source_signature": "sig",
            "evidence_ref": "docs/re/FUNCTION_CEILING_CENSUS.md",
        }, observed_at=ops_metrics.iso(NOW))

    def test_board_reads_dunkingsheep_and_the_operations_database(self):
        self.record_accounting()
        client = sample_client()
        board = ops_board.build(client, self.conn, now=NOW)
        self.assertEqual(EXPECTED_CALLS, {name for name, _ in client.calls})
        self.assertEqual({name: "ok" for name in
                          ("tasks", "task_metrics", "inbox", "dunks", "panes",
                           "daemon", "health", "ops_db")}, board["sources"])
        self.assertTrue(board["no_model"])
        self.assertEqual(3, board["tasks"]["depth"])
        self.assertEqual({"open": 1, "in_progress": 1, "blocked": 1}, board["tasks"]["counts"])
        self.assertEqual([{"assignee": "crackdown-switch", "count": 1},
                          {"assignee": "wV:p4", "count": 1}], board["tasks"]["by_assignee"])
        self.assertEqual(3, board["inbox"]["unread_total"])
        self.assertEqual(120, board["inbox"]["oldest_unread_s"])
        self.assertEqual(2, board["dunks"]["total"])
        self.assertEqual(1, board["dunks"]["running"])
        self.assertEqual(2, board["panes"]["total"])
        self.assertEqual(1, board["panes"]["working"])
        self.assertEqual("2.20.0", board["daemon"]["version"])
        self.assertEqual(27.6, board["poolrad"]["strict_percent"])
        self.assertEqual(33.4, board["poolrad"]["identity_percent"])
        self.assertEqual(590, board["poolrad"]["remaining"])
        self.assertEqual(27.6, board["headline"]["strict_percent"])
        self.assertEqual(3, board["headline"]["task_depth"])
        self.assertEqual(3, board["headline"]["inbox_unread"])

    def test_a_missing_source_stays_unavailable_and_never_becomes_zero(self):
        client = sample_client()
        client.failures = {"inbox_stats", "list_dunks"}
        board = ops_board.build(client, self.conn, now=NOW)
        self.assertEqual("unavailable", board["sources"]["inbox"])
        self.assertEqual("unavailable", board["sources"]["dunks"])
        self.assertIsNone(board["headline"]["inbox_unread"])
        self.assertIsNone(board["headline"]["dunks_running"])
        self.assertNotIn(0, [board["headline"]["inbox_unread"], board["headline"]["dunks_running"]])
        # The other sources keep their values.
        self.assertEqual("ok", board["sources"]["tasks"])
        self.assertEqual(3, board["headline"]["task_depth"])

    def test_the_board_reports_no_reviewed_accounting_as_unavailable(self):
        board = ops_board.build(sample_client(), self.conn, now=NOW)
        self.assertEqual("unavailable", board["poolrad"]["state"])
        self.assertIsNone(board["headline"]["strict_percent"])

    def test_task_ages_and_leases_are_measured_from_the_record(self):
        board = ops_board.build(sample_client(), self.conn, now=NOW)
        items = {item["id"]: item for item in board["tasks"]["items"]}
        self.assertEqual(3600, items["t18"]["age_s"])
        self.assertEqual(600, items["t18"]["lease_expires_in_s"])
        self.assertIsNone(items["t6"]["lease_expires_in_s"])
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
