"""Cost per agent and free-model volume from harness logs: the counting rules.

Each test pins one way the number goes wrong silently: a repeated Claude record
double-counting, a Codex counter reset read as negative work, a half-written
line parsed early, an unknown dollar figure rendered as $0.
"""

import importlib.util
import json
import sqlite3
import tempfile
import unittest
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
NOW = datetime(2026, 10, 22, 20, 0, tzinfo=timezone.utc)


def load(home):
    import os
    os.environ["VP_COST_HOME"] = str(home)
    spec = importlib.util.spec_from_file_location("agent_costs", ROOT / "tools" / "agent_costs.py")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def write_jsonl(path, events, tail=""):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("".join(json.dumps(e) + "\n" for e in events) + tail)


def claude_event(ident, stamp, output=10):
    return {"type": "assistant", "cwd": "/w/lane-a", "timestamp": stamp,
            "message": {"id": ident, "model": "claude-opus-5-5",
                        "usage": {"input_tokens": 1, "cache_read_input_tokens": 100,
                                  "cache_creation_input_tokens": 5, "output_tokens": output}}}


def codex_count(stamp, inp, cached, out):
    return {"type": "event_msg", "timestamp": stamp, "payload": {"type": "token_count", "info": {
        "total_token_usage": {"input_tokens": inp, "cached_input_tokens": cached, "output_tokens": out}}}}


def pi_message(stamp, model, cost):
    return {"type": "message", "timestamp": stamp, "message": {
        "role": "assistant", "provider": "opencode-go", "model": model,
        "usage": {"input": 10, "output": 5, "cacheRead": 0, "cacheWrite": 0, "cost": {"total": cost}}}}


class Fixture(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.home = Path(self.tmp.name)
        self.cache = self.home / "cache.json"
        self.ledger = self.home / "ledger.md"
        self.ledger.write_text(
            "| date | item | model | cost | duration | outcome | corrections |\n"
            "| --- | --- | --- | --- | --- | --- | --- |\n"
            "| 2026-10-21 | a | m:free | $0 | 1 s | **accepted after rework** | 4 |\n"
            "| 2026-10-21 | b | m:free | $0 | 1 s | rejected | 0 |\n")
        self.mod = load(self.home)
        self.mod.LEDGER = self.ledger
        self.mod.OPS_DB = self.home / "absent.sqlite3"

    def tearDown(self):
        self.tmp.cleanup()

    def run_collect(self):
        return self.mod.collect(now=NOW, cache_path=self.cache, panes_command=["false"])

    def row(self, result, harness):
        return next(r for r in result["cost_per_agent"]["rows"] if r["harness"] == harness)


class CountingRules(Fixture):
    def test_claude_counts_each_api_message_once_and_never_claims_dollars(self):
        stamp = "2026-10-22T19:00:00Z"
        write_jsonl(self.home / ".claude/projects/p/s.jsonl",
                    [claude_event("m1", stamp), claude_event("m1", stamp), claude_event("m2", stamp)])
        row = self.row(self.run_collect(), "claude")
        self.assertEqual(row["tokens_24h"]["value"], 2 * 116)
        self.assertIsNone(row["usd_month"]["value"])
        self.assertIn("tokens, not dollars", row["usd_month"]["reason"])

    def test_codex_deltas_the_cumulative_counter_and_a_reset_is_not_negative(self):
        stamp = "2026-10-22T19:00:00Z"
        write_jsonl(self.home / ".codex/sessions/2026/10/22/r.jsonl", [
            {"type": "session_meta", "payload": {"cwd": "/w/codex"}},
            {"type": "turn_context", "payload": {"model": "gpt-x"}},
            codex_count(stamp, 100, 60, 10), codex_count(stamp, 100, 60, 10),  # repeated event
            codex_count(stamp, 150, 80, 20),
            codex_count(stamp, 30, 0, 3)])  # counter reset after compaction
        row = self.row(self.run_collect(), "codex")
        # 100+10, then +50 input +10 out, then the reset's own 30+3.
        self.assertEqual(row["tokens_24h"]["value"], 110 + 60 + 33)

    def test_a_half_written_line_waits_and_the_next_tick_reads_only_the_tail(self):
        path = self.home / ".claude/projects/p/s.jsonl"
        write_jsonl(path, [claude_event("m1", "2026-10-22T19:00:00Z")],
                    tail=json.dumps(claude_event("m2", "2026-10-22T19:00:00Z"))[:40])
        self.assertEqual(self.row(self.run_collect(), "claude")["tokens_24h"]["value"], 116)
        write_jsonl(path, [claude_event("m1", "2026-10-22T19:00:00Z"),
                           claude_event("m2", "2026-10-22T19:00:00Z")])
        self.assertEqual(self.row(self.run_collect(), "claude")["tokens_24h"]["value"], 232)
        state = json.loads(self.cache.read_text())["files"][str(path)]
        self.assertEqual(state["offset"], path.stat().st_size)

    def test_pi_dollars_are_recorded_and_free_runs_are_split_by_model(self):
        sessions = self.home / ".pi/agent/sessions/--w--"
        write_jsonl(sessions / "a.jsonl", [{"type": "session", "cwd": "/w/pi"},
                                           pi_message("2026-10-22T19:00:00Z", "deepseek-v4.1-flash", 0.5)])
        write_jsonl(sessions / "b.jsonl", [{"type": "session", "cwd": "/w/pi"},
                                           pi_message("2026-10-22T19:00:00Z", "cat-jam-free", 0)])
        write_jsonl(sessions / "c.jsonl", [{"type": "session", "cwd": "/w/pi"},
                                           pi_message("2026-10-05T19:00:00Z", "cat-jam-free", 0)])
        result = self.run_collect()
        row = self.row(result, "pi")
        self.assertAlmostEqual(row["usd_month"]["value"], 0.5)
        free = {m["model"]: m for m in result["free_model"]["models"]}
        self.assertEqual(list(free), ["opencode-go/cat-jam-free"], "a paid model is never a free run")
        self.assertEqual(free["opencode-go/cat-jam-free"]["runs_month"]["value"], 2)
        self.assertEqual(free["opencode-go/cat-jam-free"]["runs_24h"]["value"], 1)
        self.assertEqual(free["opencode-go/cat-jam-free"]["runs_no_output_month"]["value"], 0)

    def test_ledger_outcomes_are_counted_and_unreviewed_runs_are_not_accepted(self):
        result = self.run_collect()["free_model"]
        self.assertEqual(result["outcomes_recorded"]["value"], 2)
        (only,) = result["outcomes"]
        self.assertEqual(only["accepted"]["value"], 0)
        self.assertEqual(only["accepted_after_rework"]["value"], 1)
        self.assertEqual(only["rejected"]["value"], 1)

    def test_an_absent_ledger_is_null_with_reason_not_zero(self):
        self.mod.LEDGER = self.home / "nope.md"
        cell = self.run_collect()["free_model"]["outcomes_recorded"]
        self.assertIsNone(cell["value"])
        self.assertIn("nope.md", cell["reason"])

    def test_opencode_messages_are_read_from_its_database(self):
        db = self.home / ".local/share/opencode/opencode.db"
        db.parent.mkdir(parents=True)
        with sqlite3.connect(db) as conn:
            conn.execute("CREATE TABLE message (id TEXT, session_id TEXT, time_created INT, data TEXT)")
            data = {"role": "assistant", "path": {"cwd": "/w/oc"}, "providerID": "opencode",
                    "modelID": "glm-5.3-flash-free", "cost": 0,
                    "tokens": {"input": 7, "output": 3, "cache": {"read": 0, "write": 0}}}
            conn.execute("INSERT INTO message VALUES ('1','s1',?,?)",
                         (int(NOW.timestamp() * 1000) - 60_000, json.dumps(data)))
        result = self.run_collect()
        row = self.row(result, "opencode")
        self.assertEqual(row["tokens_24h"]["value"], 10)
        self.assertEqual(row["usd_month"]["value"], 0.0)
        self.assertEqual(result["free_model"]["runs_24h"]["value"], 1)

    def test_an_absent_harness_root_is_reported_not_silently_empty(self):
        status = self.run_collect()["cost_per_agent"]
        self.assertEqual(status["status"], "partial")
        self.assertIn("absent", status["failed_sources"]["codex"])


if __name__ == "__main__":
    unittest.main()
