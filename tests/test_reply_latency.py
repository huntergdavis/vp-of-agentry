"""Reply-latency leaderboard: timestamps only, silence never drops out of the average."""

import importlib.util
import json
import sqlite3
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
NOW = 1_800_000_000.0


def load():
    spec = importlib.util.spec_from_file_location("reply_latency", ROOT / "tools" / "reply_latency.py")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


class ReplyRules(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.dir = Path(self.tmp.name)
        rows = []
        # fast: six reads at 10 s, by name and by pane id, plus one open message 100 s old (> 3 x 10 s)
        for i in range(5):
            rows.append((f"a{i}", "fast", "fast (w1:p1)", "w1:p1", NOW - 1000, NOW - 990, None, None, None, "read"))
        rows.append(("a5", "w1:p1", None, "w1:p1", NOW - 500, None, NOW - 490, None, None, "acked"))
        rows.append(("a6", "fast", "fast (w1:p1)", "w1:p1", NOW - 100, None, None, None, None, "sent"))
        # stuck: nothing handled, two open; one closed by cancel
        rows.append(("b1", "stuck", "stuck (w1:p2)", None, NOW - 7200, None, None, None, None, "sent"))
        rows.append(("b2", "stuck", "stuck (w1:p2)", None, NOW - 60, None, None, None, None, "queued"))
        rows.append(("b3", "stuck", "stuck (w1:p2)", None, NOW - 60, None, None, NOW, None, "cancelled"))
        # few: one quick read, not enough to rank
        rows.append(("c1", "few", "few (w1:p3)", "w1:p3", NOW - 50, NOW - 49, None, None, None, "read"))
        with sqlite3.connect(self.dir / "inbox.db") as conn:
            conn.execute("CREATE TABLE messages (id TEXT, mailbox TEXT, mailbox_label TEXT, pane_id TEXT, "
                         "created_at REAL, read_at REAL, acked_at REAL, cancelled_at REAL, archived_at REAL, state TEXT)")
            conn.executemany("INSERT INTO messages VALUES (?,?,?,?,?,?,?,?,?,?)", rows)
        self.mod = load()
        panes = json.dumps([{"pane_id": "w1:p1"}, {"pane_id": "w1:p2"}])
        self.result = self.mod.collect(self.dir, now=NOW, runner=lambda argv: panes)
        self.rows = {r["mailbox"]: r for r in self.result["rows"]}

    def tearDown(self):
        self.tmp.cleanup()

    def test_mail_by_name_and_by_pane_id_is_one_agent(self):
        fast = self.rows["w1:p1"]
        self.assertEqual(fast["label"], "fast (w1:p1)")
        self.assertEqual(fast["handled"]["value"], 6)
        self.assertEqual(fast["p50_s"]["value"], 10.0)
        self.assertTrue(fast["ranked"])
        self.assertIn("w1:p2", self.rows, "a pane named only in the label is still that pane")

    def test_silence_is_counted_against_the_agents_own_median(self):
        fast = self.rows["w1:p1"]
        self.assertEqual(fast["silent"]["value"], 1)
        self.assertEqual(fast["oldest_silent"]["id"], "a6")

    def test_an_agent_that_handled_nothing_is_null_not_perfect_and_all_its_open_mail_is_silent(self):
        stuck = self.rows["w1:p2"]
        self.assertIsNone(stuck["p50_s"]["value"])
        self.assertIn("no messages handled", stuck["p50_s"]["reason"])
        self.assertEqual(stuck["unhandled_24h"]["value"], 2, "a cancelled message is not unhandled")
        self.assertEqual(stuck["silent"]["value"], 2)
        self.assertEqual(stuck["oldest_silent"]["id"], "b1")
        self.assertFalse(stuck["ranked"])

    def test_two_fast_replies_do_not_outrank_a_volume_lane(self):
        order = [r["mailbox"] for r in self.result["rows"]]
        self.assertLess(order.index("w1:p1"), order.index("w1:p3"))
        self.assertFalse(self.rows["w1:p3"]["ranked"])
        self.assertFalse(self.rows["w1:p3"]["pane_open"])

    def test_the_panel_says_it_is_deterministic(self):
        self.assertIn("no model involved", self.result["deterministic"])

    def test_absent_store_is_null_with_reason(self):
        result = self.mod.collect(self.dir / "none", now=NOW)
        self.assertEqual(result["status"], "nulled")
        self.assertIn("absent", result["reason"])


if __name__ == "__main__":
    unittest.main()
