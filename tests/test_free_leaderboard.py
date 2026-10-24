"""Free-model leaderboard (owner #1426): output ranks, runs do not; lines stay honest-but-missing."""

import importlib.util
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent


def load():
    spec = importlib.util.spec_from_file_location("free_leaderboard", ROOT / "tools" / "free_leaderboard.py")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def run_dir(root, body, model, verdict):
    d = root / body
    d.mkdir(parents=True)
    (d / "verdict.txt").write_text(f"body: {body}\nmodel: {model}\nbytes gate: exit 0\n   {verdict}\n")
    (d / "run.log").write_text(f"worker {body} on {model} at 2026-10-23 11:31:43 PDT\n")


class LeaderboardRules(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        base = Path(self.tmp.name)
        self.runs, self.bake = base / "free_runs", base / "bakeoff"
        many = "openrouter/a/many-runs:free"
        for i in range(6):
            run_dir(self.runs, f"B{i}", many, "BYTES DIFFER: first difference at +0")
        run_dir(self.runs, "B9", many, "BYTES MATCH: 16 bytes at 1 are byte-identical to GAME.OVR.")
        (self.bake / "20261023-180922").mkdir(parents=True)
        (self.bake / "20261023-180922" / "results.tsv").write_text(
            "opencode-go/sharp\tB1\tVERIFIED (   BYTES MATCH: 143 bytes at 5 are byte-identical to GAME.OVR.)\t98s\n"
            "opencode-go/sharp\tB1\tVERIFIED (   BYTES MATCH: 143 bytes at 5 are byte-identical to GAME.OVR.)\t90s\n"
            "openrouter/x/pro\tB2\tEMPTY\t258s\n"
            f"{many}\tB3\tNO DUMP\t10s\n")
        self.mod = load()

    def tearDown(self):
        self.tmp.cleanup()

    def collect(self):
        return self.mod.collect(free_runs=self.runs, bakeoff=self.bake)

    def test_verified_output_outranks_run_count_and_repeats_count_once(self):
        rows = self.collect()["rows"]
        self.assertEqual(rows[0]["model"], "opencode-go/sharp")
        self.assertEqual(rows[0]["verified_decodes"]["value"], 1, "the same body verified twice is one decode")
        self.assertEqual(rows[0]["verified_bytes"]["value"], 143)
        many = next(r for r in rows if r["model"].endswith("many-runs:free"))
        self.assertEqual((many["runs"]["value"], many["wrong_bytes"]["value"], many["no_dump"]["value"]), (8, 6, 1))

    def test_tiers_are_free_subscription_or_metered(self):
        tiers = {r["model"]: r["tier"] for r in self.collect()["rows"]}
        self.assertEqual(tiers, {"opencode-go/sharp": "subscription", "openrouter/a/many-runs:free": "free",
                                 "openrouter/x/pro": "metered"})

    def test_lines_are_null_with_reason_never_zero(self):
        for row in self.collect()["rows"]:
            for key in ("accepted_lines", "assisted_lines"):
                self.assertIsNone(row[key]["value"])
                self.assertIn("no per-line attribution", row[key]["reason"])

    def test_the_honest_line_ships_with_the_data(self):
        self.assertIn("it is not a credit", self.collect()["truth"])

    def test_no_sources_is_null_with_reason(self):
        empty = Path(self.tmp.name) / "none"
        result = self.mod.collect(free_runs=empty, bakeoff=empty)
        self.assertEqual(result["status"], "nulled")
        self.assertIn("absent", result["reason"])


if __name__ == "__main__":
    unittest.main()
