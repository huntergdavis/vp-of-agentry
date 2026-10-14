"""The embedded Poolrad dashboard stays behind owner auth and serves only public reports."""

import importlib
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from fastapi import HTTPException, Request

server = importlib.import_module("server.app")


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
        self.assertEqual({"refreshed": True}, server.refresh_poolrad_dashboard(identity))
        self.assertEqual("refreshed", Path(server.poolrad_dashboard_page(identity).path).read_text())


if __name__ == "__main__":
    unittest.main()
