"""The collector's guards: a broken source is null+reason, never a zero.

Negative test: run the collector against an EMPTY config dir into a temp output.
Every database-backed cell must be nulled with a reason, warnings must be
non-empty, and the production snapshot must not be touched. This is the guard's
proof - a guard that has never been seen to fail is a guard we are assuming.
"""

import importlib.util
import json
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
COLLECTOR = ROOT / "tools" / "ops_snapshot.py"


def load_collector():
    spec = importlib.util.spec_from_file_location("ops_snapshot", COLLECTOR)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


class GuardTests(unittest.TestCase):
    def test_guard_names_a_missing_table_not_a_zero(self):
        module = load_collector()
        stale = Path("/home/hunter/workspace/dunkingsheep/tasks.db")
        if not stale.exists():
            self.skipTest("stale fixture DB absent")
        reason = module.guard(stale, table="tasks", min_rows=1)
        self.assertIn("absent", reason)

    def test_empty_config_dir_nulls_the_db_cells_and_warns(self):
        with tempfile.TemporaryDirectory() as temporary:
            empty = Path(temporary) / "empty"
            empty.mkdir()
            out = Path(temporary) / "snap.json"
            production = ROOT / "data" / "ops-snapshot.json"
            before = production.stat().st_mtime if production.exists() else None
            proc = subprocess.run(
                [sys.executable, str(COLLECTOR), "--dunk-dir", str(empty), "--out", str(out)],
                capture_output=True, text=True, timeout=240)
            self.assertEqual(0, proc.returncode, proc.stderr)
            self.assertNotIn(str(production), proc.stdout,
                             "--out must be honoured; the production path must not be written")
            self.assertTrue(out.exists())
            snapshot = json.loads(out.read_text())
            for source in ("tasks", "metrics"):
                self.assertEqual("nulled", snapshot["sources"][source]["status"], source)
                self.assertTrue(snapshot["sources"][source]["reason"], source)
            self.assertTrue(snapshot["warnings"], "a broken source must produce a warning")
            self.assertTrue(any("absent" in item["reason"] for item in snapshot["warnings"]))
            if before is not None:
                self.assertEqual(before, production.stat().st_mtime,
                                 "the production snapshot was rewritten by a test run")


class ContextSectionTests(unittest.TestCase):
    """The digest section: rendered from the file, counted, and nulled honestly."""

    def test_context_section_carries_the_digest_and_per_article_counts(self):
        module = load_collector()
        live = Path.home() / ".config" / "dunkingsheep" / "context"
        if not live.is_dir():
            self.skipTest("no live context store on this host")
        context = module.collect_context()
        self.assertEqual("ok", context["status"], context.get("reason"))
        self.assertTrue(context["digest"].startswith("## Ground truths ("),
                        "the digest must be included verbatim")
        self.assertIsInstance(context["articles"]["value"], int)
        self.assertTrue(context["articles"]["as_of"], "every number carries an as_of")
        self.assertTrue(context["entries"], "per-article rows are what makes 'never read' visible")
        for entry in context["entries"]:
            self.assertIn("reads", entry)
            self.assertIn("injected", entry)
            self.assertIn(entry["store"], ("global", "project"))

    def test_an_absent_store_is_nulled_with_a_reason_not_zero_articles(self):
        module = load_collector()
        with tempfile.TemporaryDirectory() as temporary:
            context = module.collect_context(project_dir=temporary)
            if context["status"] == "ok":
                self.skipTest("a project store exists in the temp dir")
            self.assertIsNone(context["articles"]["value"],
                              "an absent store is not '0 articles'")
            self.assertTrue(context["articles"]["reason"])
            self.assertIsNone(context["digest"])


if __name__ == "__main__":
    unittest.main()
