"""CREDITED / REPLACED / rate (owner #1386): computed from commits, never typed in.

Builds a throwaway git repo whose checkpoint commits carry known times, so the
deltas and per-day nets can be checked against the events that made them.
"""

import importlib.util
import json
import os
import subprocess
import tempfile
import unittest
from datetime import datetime, timedelta, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
NOW = datetime(2026, 10, 23, 22, 0, tzinfo=timezone.utc)  # 15:00 in Los Angeles


def load():
    spec = importlib.util.spec_from_file_location("credit_stats", ROOT / "tools" / "credit_stats.py")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


class Repo:
    def __init__(self, path):
        self.path = path
        self.git("init", "-q", "-b", "main")
        (path / "docs/re").mkdir(parents=True)

    def git(self, *args, when=None):
        env = {**os.environ, "GIT_AUTHOR_NAME": "t", "GIT_AUTHOR_EMAIL": "t@t", "GIT_COMMITTER_NAME": "t",
               "GIT_COMMITTER_EMAIL": "t@t"}
        if when:
            env["GIT_AUTHOR_DATE"] = env["GIT_COMMITTER_DATE"] = when.isoformat()
        subprocess.run(["git", "-C", str(self.path), *args], check=True, env=env, capture_output=True)

    def pin(self, strict, kinds, when, subject="Accept"):
        (self.path / "docs/re/function_accounting_checkpoint.json").write_text(
            json.dumps({"strict_full_c_originals": strict, "verified_game_identities": strict + 45}))
        rows = "id,kind,detail\n" + "".join(f"B{i},{k},x\n" for i, k in enumerate(kinds))
        (self.path / "docs/re/credit_evidence_kind.csv").write_text(rows)
        self.git("add", "-A")
        self.git("commit", "-q", "-m", subject, when=when)


class CreditRules(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.repo = Repo(Path(self.tmp.name))
        self.mod = load()

    def tearDown(self):
        self.tmp.cleanup()

    def test_value_kinds_and_deltas_come_from_the_commits(self):
        r = self.repo
        r.pin(2, ["checker", "cites-tool"], NOW - timedelta(days=9))
        r.pin(3, ["checker", "audit", "audit"], NOW - timedelta(days=3), "Publish batch")
        r.pin(5, ["checker", "audit", "audit", "unit-test", "unit-test"], NOW - timedelta(hours=2))
        result = self.mod.collect(r.path, now=NOW)
        credited = result["credited"]
        self.assertEqual(credited["value"]["value"], 5)
        self.assertEqual(credited["delta_24h"]["value"], 2)
        self.assertEqual(credited["delta_7d"]["value"], 3)
        kinds = {k["kind"]: k["count"]["value"] for k in credited["by_kind"]}
        self.assertEqual(kinds, {"checker": 1, "audit": 2, "unit-test": 2, "cites-tool": 0},
                         "a kind that left the table in the window is a real zero")
        self.assertIsNone(credited["kind_mismatch"])
        days = {d["day"]: d["net"] for d in result["rate"]["credited"]}
        self.assertEqual(days["2026-10-23"], 2)
        self.assertEqual(days["2026-10-20"], 1)
        self.assertEqual(result["rate"]["largest_steps"][0]["change"], 2)

    def test_a_day_before_the_first_commit_is_unknown_not_zero(self):
        self.repo.pin(4, ["checker"] * 4, NOW - timedelta(days=2))
        days = self.mod.collect(self.repo.path, now=NOW)["rate"]["credited"]
        self.assertIsNone(days[0]["net"])
        self.assertEqual(self.mod.collect(self.repo.path, now=NOW)["credited"]["kind_mismatch"], None)

    def test_replaced_is_null_with_reason_until_a_lane_writes_the_file(self):
        self.repo.pin(1, ["checker"], NOW - timedelta(days=1))
        result = self.mod.collect(self.repo.path, now=NOW)
        self.assertIsNone(result["replaced"]["value"]["value"])
        self.assertIn("not yet collected", result["replaced"]["value"]["reason"])
        self.assertIsNone(result["rate"]["replaced"])
        self.assertIsNone(result["rate"]["replaced_per_day_7d"]["value"])

    def test_replaced_counts_only_zero_difference_proofs(self):
        self.repo.pin(1, ["checker"], NOW - timedelta(days=1))
        (self.repo.path / "docs/re/replaced_bodies.json").write_text(json.dumps({"schema": "replaced/1", "bodies": [
            {"id": "A", "proven_at": "2026-10-23T18:00:00Z", "evidence": {"kind": "pixels", "differing": 0}},
            {"id": "B", "proven_at": "2026-10-22T18:00:00Z", "evidence": {"kind": "arrivals", "differing": 0}},
            {"id": "C", "proven_at": "2026-10-23T18:00:00Z", "evidence": {"kind": "pixels", "differing": 12}}]}))
        result = self.mod.collect(self.repo.path, now=NOW)
        self.assertEqual(result["replaced"]["value"]["value"], 2)
        self.assertEqual(result["replaced"]["not_counted"]["value"], 1)
        days = {d["day"]: d["net"] for d in result["rate"]["replaced"]}
        self.assertEqual(days["2026-10-23"], 1)
        self.assertEqual(days["2026-10-22"], 1, "the first proof day counts from zero, not from unknown")
        self.assertEqual(days["2026-10-20"], 0, "before any proof, replaced is a known zero")

    def test_a_missing_repo_is_null_with_reason(self):
        result = self.mod.collect(Path(self.tmp.name) / "nope", now=NOW)
        self.assertEqual(result["credited"]["status"], "nulled")
        self.assertTrue(result["credited"]["reason"])
        self.assertEqual(result["rate"]["status"], "nulled")


if __name__ == "__main__":
    unittest.main()
