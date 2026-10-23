"""Dunks, inbox and delivery numbers (owner #1358): the ways they go quietly wrong.

A coalesced CLI answer read as "no dunks", a frozen countdown shown as live, a
stall hidden because only finished sends have a duration, a message to a dead
pane shown as merely "typing".
"""

import importlib.util
import json
import sqlite3
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
NOW = 1_800_000_000.0


def load():
    spec = importlib.util.spec_from_file_location("delivery_stats", ROOT / "tools" / "delivery_stats.py")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    module.time.sleep = lambda s: None
    return module


DUNK = {"id": "d1", "name": "", "target_pane_id": "w1:p1", "target_tab": "lane", "target_agent": "pi",
        "interval_minutes": 60.0, "running": True, "only_when": "idle", "hold_while_typing": True,
        "skip_if_unconsumed": False, "send_count": 3, "total_skips": 0, "hold_count": 2,
        "last_sent_at": NOW - 4000, "next_send_at": NOW - 600, "text": "check in"}


class Fixture(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.dir = Path(self.tmp.name)
        self.mod = load()
        (self.dir / "dunks.json").write_text(json.dumps({"dunkers": [DUNK], "outbox": [
            {"id": "m9", "pane_id": "w1:gone", "target_label": "old", "created_at": NOW - 7200, "text": "hi"}]}))
        with sqlite3.connect(self.dir / "inbox.db") as conn:
            conn.execute("CREATE TABLE messages (id TEXT, mailbox TEXT, mailbox_label TEXT, state TEXT, "
                         "created_at REAL, read_at REAL, cancelled_at REAL, archived_at REAL, notify_state TEXT)")
            conn.executemany("INSERT INTO messages VALUES (?,?,?,?,?,?,?,?,?)", [
                ("i1", "lane", "lane (w1:p1)", "sent", NOW - 7200, None, None, None, "sent"),
                ("i2", "lane", "lane (w1:p1)", "queued", NOW - 60, None, None, None, "queued"),
                ("i3", "lane", "lane (w1:p1)", "read", NOW - 30, NOW - 10, None, None, "sent"),
                ("i4", "vp", "vp", "cancelled", NOW - 30, None, NOW, None, None)])
        with sqlite3.connect(self.dir / "metrics.db") as conn:
            conn.execute("CREATE TABLE events (at REAL, kind TEXT, mailbox TEXT, reason TEXT, duration_ms INT)")
            conn.executemany("INSERT INTO events VALUES (?,?,?,?,?)",
                             [(NOW - 100, "message.sent", "lane", None, ms) for ms in (1000, 2000, 3000, 4000, 900_000)]
                             + [(NOW - 100, "message.held", "lane", "draft", None),
                                (NOW - 90_000, "message.sent", "lane", None, 99_000_000)])

    def tearDown(self):
        self.tmp.cleanup()

    def runner(self, answers):
        calls = []

        def run(argv):
            calls.append(argv[-1])
            queue = answers[argv[-1]]
            return queue.pop(0) if len(queue) > 1 else queue[0]
        run.calls = calls
        return run


class DeliveryRules(Fixture):
    def test_a_coalesced_answer_is_retried_not_read_as_empty(self):
        run = self.runner({"list": [json.dumps({"coalesced": True, "interval_s": 2}),
                                    json.dumps({"dunks": [dict(DUNK, status="Held (typing)")]})],
                           "messages": ["{}"], "panes": ["[]"]})
        dunks = self.mod.collect(self.dir, now=NOW, runner=run)["dunks"]
        self.assertEqual(run.calls.count("list"), 2)
        self.assertIn("daemon", dunks["source"])
        self.assertEqual(dunks["rows"][0]["state"], "Held (typing)")
        self.assertEqual(dunks["rows"][0]["overdue_min"], 10)

    def test_a_countdown_is_not_frozen_onto_the_page(self):
        run = self.runner({"list": [json.dumps({"dunks": [dict(DUNK, status="Next: 78:04", next_send_at=NOW + 60)]})],
                           "messages": ["{}"], "panes": ["[]"]})
        row = self.mod.collect(self.dir, now=NOW, runner=run)["dunks"]["rows"][0]
        self.assertEqual(row["state"], "scheduled")
        self.assertIsNotNone(row["next_send_at"])

    def test_without_the_daemon_the_store_answers_and_says_so(self):
        run = self.runner({"list": ["not json"], "messages": ["not json"], "panes": ["not json"]})
        result = self.mod.collect(self.dir, now=NOW, runner=run)
        self.assertIn("daemon view unavailable", result["dunks"]["source"])
        self.assertEqual(result["dunks"]["rows"][0]["state"], "overdue 10 min (held 2x)")
        self.assertEqual(result["delivery_health"]["status"], "partial")
        self.assertIn("unknown", result["delivery_health"]["held"][0]["reason"])

    def test_inbox_counts_unread_and_the_oldest(self):
        run = self.runner({"list": ["[]"], "messages": ["{}"], "panes": ["[]"]})
        inbox = self.mod.collect(self.dir, now=NOW, runner=run)["inbox"]
        self.assertEqual(inbox["total"]["unread"]["value"], 2, "read and cancelled are not unread")
        self.assertEqual(inbox["total"]["oldest_unread_h"]["value"], 2.0)
        self.assertEqual(inbox["total"]["notice"], {"sent": 2, "queued": 1, "none": 1})

    def test_percentiles_cover_24h_and_a_stall_still_in_the_queue_is_shown(self):
        queue = {"queued": [{"message_id": "m1", "pane_id": "w1:p1", "target_label": "lane",
                             "message": "queued: someone is typing in lane", "holds": 4, "waiting_s": 30000}]}
        run = self.runner({"list": ["[]"], "messages": [json.dumps(queue)],
                           "panes": [json.dumps([{"pane_id": "w1:p1"}])]})
        result = self.mod.collect(self.dir, now=NOW, runner=run)
        latency = result["delivery_latency"]
        self.assertEqual(latency["all"]["n"]["value"], 5, "the 25-hour-old send is outside the window")
        self.assertEqual(latency["all"]["p50_s"]["value"], 3.0)
        self.assertEqual(latency["all"]["max_s"]["value"], 900.0)
        self.assertEqual(latency["still_waiting"]["n"]["value"], 1)
        self.assertEqual(latency["still_waiting"]["oldest_s"]["value"], 30000)
        self.assertEqual(result["delivery_health"]["held"][0]["reason"], "typing")

    def test_a_held_message_to_a_vanished_pane_is_a_dead_pane(self):
        queue = {"queued": [{"message_id": "m1", "pane_id": "w1:gone", "target_label": "x",
                             "message": "queued: someone is typing in x", "waiting_s": 10}]}
        run = self.runner({"list": ["[]"], "messages": [json.dumps(queue)],
                           "panes": [json.dumps({"panes": [{"pane_id": "w1:p1"}]})]})
        held = self.mod.collect(self.dir, now=NOW, runner=run)["delivery_health"]["held"]
        self.assertEqual(held[0]["reason"], "dead pane")

    def test_absent_stores_are_null_with_reason_not_zero(self):
        empty = self.dir / "empty"
        empty.mkdir()
        run = self.runner({"list": ["x"], "messages": ["x"], "panes": ["x"]})
        result = self.mod.collect(empty, now=NOW, runner=run)
        for name in ("dunks", "inbox", "delivery_latency", "delivery_health"):
            self.assertEqual(result[name]["status"], "nulled", name)
            self.assertTrue(result[name]["reason"], name)


if __name__ == "__main__":
    unittest.main()
