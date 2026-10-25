"""The embedded Poolrad dashboard stays behind owner auth and serves only public reports."""

import importlib
import json
import re
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from fastapi import HTTPException, Request

server = importlib.import_module("server.app")
REAL_DASHBOARD = Path(__file__).resolve().parents[1] / "integrations" / "poolrad-dashboard"


class PoolradDashboardTests(unittest.TestCase):
    def setUp(self):
        temporary = tempfile.TemporaryDirectory()
        self.addCleanup(temporary.cleanup)
        root = Path(temporary.name)
        dashboard = root / "tools" / "dashboard"
        reports = dashboard / "state" / "reports"
        reports.mkdir(parents=True)
        (dashboard / "dashboard.html").write_text("<h1>Poolrad dashboard</h1>")
        (reports / "SLOT_A_FIRST_EGA_ROW64.md").write_text("public evidence")
        (reports / "private.md").write_text("private data")
        for name, value in (("DB", root / "messages.sqlite3"), ("AUTH", root / "auth.json"),
                            ("CREDENTIALS", root / "owner-credentials"), ("DASHBOARD_DIR", dashboard)):
            override = patch.object(server, name, value)
            override.start()
            self.addCleanup(override.stop)
        server._initialize()
        self.token = server._auth_record()["token"]

    def authenticate(self, token=""):
        headers = [(b"host", b"localhost")]
        if token:
            headers.append((b"authorization", f"Bearer {token}".encode()))
        request = Request({"type": "http", "scheme": "http", "server": ("localhost", 80),
                           "client": ("127.0.0.1", 1234), "path": "/", "headers": headers})
        return server.require_auth(request)

    def assert_route_requires_auth(self, path, method):
        route = next(route for route in server.app.routes if route.path == path and method in route.methods)
        self.assertIn(server.require_auth, [dependency.call for dependency in route.dependant.dependencies])

    def test_page_and_reports_require_auth_and_allow_only_cited_reports(self):
        page = "/api/poolrad-dashboard/dashboard.html"
        report = "/api/poolrad-dashboard/state/reports/SLOT_A_FIRST_EGA_ROW64.md"
        self.assert_route_requires_auth(page, "GET")
        self.assert_route_requires_auth("/api/poolrad-dashboard/state/reports/{filename}", "GET")
        with self.assertRaises(HTTPException) as denied:
            self.authenticate()
        self.assertEqual(401, denied.exception.status_code)
        identity = self.authenticate(self.token)
        self.assertEqual("api", identity)
        self.assertEqual("<h1>Poolrad dashboard</h1>", Path(server.poolrad_dashboard_page(identity).path).read_text())
        self.assertEqual("public evidence", Path(server.poolrad_dashboard_report(
            "SLOT_A_FIRST_EGA_ROW64.md", identity).path).read_text())
        with self.assertRaises(HTTPException) as blocked:
            server.poolrad_dashboard_report("private.md", identity)
        self.assertEqual(404, blocked.exception.status_code)

    def test_refresh_renders_locally_after_auth(self):
        script = server.DASHBOARD_DIR / "dashboard.py"
        script.write_text("from pathlib import Path\nPath(__file__).with_name('dashboard.html').write_text('refreshed')\n")
        self.assert_route_requires_auth("/api/poolrad-dashboard/refresh", "POST")
        identity = self.authenticate(self.token)
        import ops_metrics

        with patch.object(ops_metrics, "published_accounting", return_value={
                "commit_oid": "b" * 40, "strict_full_c": 225,
                "verified_game_identities": 273, "ceiling": 815,
                "bound_kind": "upper_bound", "source_signature": "sig",
                "evidence_ref": "docs/re/FUNCTION_CEILING_CENSUS.md"}), \
             patch.object(ops_metrics, "record_accounting", lambda *args, **kwargs: None):
            result = server.refresh_poolrad_dashboard(identity)
        self.assertTrue(result["refreshed"])
        self.assertEqual("b" * 40, result["published_checkpoint"])
        self.assertEqual("refreshed", Path(server.poolrad_dashboard_page(identity).path).read_text())

    def test_progress_route_requires_auth(self):
        self.assert_route_requires_auth("/api/poolrad-dashboard/progress", "GET")
        with self.assertRaises(HTTPException) as denied:
            server.poolrad_dashboard_progress(self.authenticate())
        self.assertEqual(401, denied.exception.status_code)


class ReplacementSourceTests(unittest.TestCase):
    def test_count_uses_exact_checkpoint_and_preserves_source(self):
        from types import SimpleNamespace
        rows = {"schema": "replaced/1", "truth": "recorded source evidence", "bodies": [
            {"id": "a", "proven_at": "2026-10-20", "evidence": "report"},
            {"id": "b", "proven_at": "2026-10-21", "evidence": "report"},
        ]}
        with patch.object(server.subprocess, "run", return_value=SimpleNamespace(stdout=json.dumps(rows))) as run:
            data = server._replacement_count("a" * 40)
        self.assertEqual(2, data["count"])
        self.assertEqual("ok", data["state"])
        self.assertEqual("a" * 40 + ":docs/re/replaced_bodies.json", run.call_args.args[0][-1])
        self.assertEqual("a" * 40, data["commit"])

    def test_missing_or_ambiguous_record_is_unknown_not_zero(self):
        import subprocess
        from types import SimpleNamespace
        with patch.object(server.subprocess, "run", side_effect=subprocess.CalledProcessError(128, "git")):
            self.assertIsNone(server._replacement_count("b" * 40)["count"])
        rows = {"schema": "replaced/1", "bodies": [
            {"id": "a", "proven_at": "date", "evidence": "report"},
            {"id": "a", "proven_at": "date", "evidence": "report"},
        ]}
        with patch.object(server.subprocess, "run", return_value=SimpleNamespace(stdout=json.dumps(rows))):
            self.assertEqual("unavailable", server._replacement_count("b" * 40)["state"])



class CompactPoolradProgressTests(unittest.TestCase):
    """The owner view carries two percentages and one evidence line, nothing else."""

    def setUp(self):
        self.module = self._load(REAL_DASHBOARD / "dashboard.py")
        self.accounting = {
            "status": "reviewed", "strict_full_c": 225, "verified_identities": 273,
            "ceiling": 815, "bound_kind": "upper_bound",
            "accounting_source": "docs/re/function_accounting_checkpoint.json",
            "evidence_doc": "docs/re/FUNCTION_CEILING_CENSUS.md",
        }

    @staticmethod
    def _load(script):
        import importlib.util

        spec = importlib.util.spec_from_file_location("vp_dashboard_under_test", script)
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)
        return module

    def test_percentages_and_one_evidence_line(self):
        with patch.object(self.module, "cited_evidence", return_value=[
            {"label": "EGA first-view row 64", "source": "docs/re/SLOT_A_FIRST_EGA_ROW64.md",
             "scope": "one row", "matched": 320, "compared": 320, "status": "reported in source",
             "method": "published scoped report"}]):
            view = self.module.compact_view(REPO := Path("/tmp"), self.accounting,
                                             commit="0123456789abcdef", source="published main")
        self.assertEqual(27.6, view["strict_percent"])
        self.assertEqual(33.4, view["identity_percent"])
        self.assertEqual(225, view["strict_full_c"])
        self.assertEqual(273, view["identities"])
        self.assertEqual(815, view["ceiling"])
        self.assertEqual(590, view["remaining"])
        self.assertEqual("published main", view["source"])
        self.assertEqual(0, view["evidence_line"].count("\n"))
        self.assertIn("01234567", view["evidence_line"])
        self.assertIn("320/320 px", view["evidence_line"])
        self.assertIn("not whole-game completion", view["evidence_line"])

    def test_an_unreviewed_checkpoint_never_reports_a_percentage(self):
        accounting = dict(self.accounting, status="pending", ceiling=None)
        with patch.object(self.module, "cited_evidence", return_value=[]):
            view = self.module.compact_view(Path("/tmp"), accounting, commit="0" * 40, source="checkout")
        self.assertIsNone(view["strict_percent"])
        self.assertIsNone(view["identity_percent"])
        self.assertIn("unavailable", view["evidence_line"])

    def test_the_rendered_page_has_no_wall_of_text(self):
        with patch.object(self.module, "cited_evidence", return_value=[]), \
             patch.object(self.module, "head", return_value="0" * 40), \
             patch.object(self.module, "function_progress", return_value=self.accounting), \
             patch.object(self.module, "queue", return_value=([], {})), \
             patch.object(self.module, "read_json", return_value=None), \
             patch.object(self.module, "write_json", lambda *args, **kwargs: None), \
             patch.object(self.module.Path, "mkdir", lambda *args, **kwargs: None):
            with tempfile.TemporaryDirectory() as temporary:
                with patch.object(self.module, "STATE", Path(temporary)):
                    with patch.object(self.module, "HERE", Path(temporary)):
                        page = self.module.render(Path(temporary)).read_text()
        body = page.split("<body", 1)[-1]
        self.assertIn("27.6%", body)
        self.assertIn("33.4%", body)
        self.assertIn("225 / 815 upper bound", body)
        self.assertIn("273 / 815 upper bound", body)
        # One evidence line, no essay.
        self.assertEqual(2, len(re.findall(r"<p ", body)))
        self.assertNotIn("Primary goal", body)
        self.assertNotIn("Next C-body gate", body)


if __name__ == "__main__":
    unittest.main()
