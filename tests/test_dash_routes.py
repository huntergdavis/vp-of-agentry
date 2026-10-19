"""The standalone dashboard routes and the login return target.

The herdr web UI frames these routes, so they must render on their own and
must never serve dashboard content to a caller without an owner session.
"""

import importlib
import os
import secrets
import tempfile
import time
import unittest
from pathlib import Path
from unittest.mock import patch

from starlette.requests import Request

server = importlib.import_module("server.app")
PASSWORD = "test-owner-password"


def build_request(path="/dash/poolrad", host="cell", cookie=None, query=""):
    headers = [(b"host", f"{host}:8787".encode())]
    if cookie:
        headers.append((b"cookie", f"vp_session={cookie}".encode()))
    return Request({"type": "http", "scheme": "http", "server": (host, 8787),
                     "client": ("127.0.0.1", 1234), "path": path, "query_string": query.encode(),
                     "headers": headers})


class DashRouteTests(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory()
        self.addCleanup(self.temporary.cleanup)
        root = Path(self.temporary.name)
        for name, value in (("DB", root / "messages.sqlite3"), ("AUTH", root / "auth.json"),
                            ("CREDENTIALS", root / "owner-credentials")):
            override = patch.object(server, name, value)
            override.start()
            self.addCleanup(override.stop)
        with patch.dict(os.environ, {"VP_PASSWORD": PASSWORD}):
            server._initialize()
        self.token = server._auth_record()["token"]

    def session_cookie(self):
        cookie = secrets.token_urlsafe(32)
        with server._db() as conn:
            conn.execute("INSERT INTO sessions(token_hash,expires_at) VALUES(?,?)",
                         (server._session_key(cookie), time.time() + 3600))
        return cookie

    def test_a_dashboard_route_without_a_session_goes_to_the_login(self):
        response = server.dash_route("poolrad", build_request())
        self.assertEqual(302, response.status_code)
        self.assertEqual("/?next=%2Fdash%2Fpoolrad", response.headers["location"])

    def test_a_dashboard_route_with_a_session_serves_the_bundle(self):
        cookie = self.session_cookie()
        response = server.dash_route("operations", build_request(cookie=cookie))
        self.assertEqual(200, response.status_code)
        self.assertEqual("text/html", response.media_type)
        self.assertEqual("no-store", response.headers["cache-control"])

    def test_the_dash_root_and_trailing_slashes_redirect(self):
        self.assertEqual("/dash/poolrad", server.dash_root().headers["location"])
        response = server.dash_route("play/", build_request(cookie=self.session_cookie()))
        self.assertEqual(307, response.status_code)
        self.assertEqual("/dash/play", response.headers["location"])

    def test_the_old_paths_are_retired_to_the_shell(self):
        # Owner #956: the herdr web UI is the front door, so the old aliases
        # are answered by the redirect middleware, not by these routes.
        # tests/test_retired_desk.py covers that behaviour.
        self.assertFalse(hasattr(server, "legacy_poolrad_route"))
        self.assertTrue(server.DESK_KEPT_PREFIXES)

    def test_the_return_target_is_limited_to_this_host(self):
        request = build_request()
        self.assertEqual("/dash/poolrad", server._safe_next("/dash/poolrad", request))
        self.assertEqual("http://cell:8787/dash/vp", server._safe_next("http://cell:8787/dash/vp", request))
        self.assertIsNone(server._safe_next("http://evil.example/", request))
        self.assertIsNone(server._safe_next("http://cell:9999/dash/vp", request))
        self.assertIsNone(server._safe_next("//evil.example/", request))
        self.assertIsNone(server._safe_next("", request))
        self.assertIsNone(server._safe_next(None, request))

    def test_the_herdr_web_ui_port_is_allowed_as_a_return_target(self):
        with patch.dict(os.environ, {"VP_HERDR_WEBUI_URL": "http://cell:8789/"}):
            request = build_request()
            self.assertEqual("http://cell:8789/", server._safe_next("http://cell:8789/", request))
            self.assertIsNone(server._safe_next("http://cell:8790/", request))

    def test_the_allowed_return_port_follows_the_configured_web_ui_url(self):
        # The frame address and the allowed return port come from one variable,
        # so they cannot drift apart: move the proxy and both move together.
        with patch.dict(os.environ, {"VP_HERDR_WEBUI_URL": "http://cell:8791/"}):
            request = build_request()
            self.assertEqual("http://cell:8791/", server._safe_next("http://cell:8791/", request))
            self.assertIsNone(server._safe_next("http://cell:8789/", request))

    def test_login_returns_the_safe_target_only(self):
        request = build_request()
        response = type("Response", (), {"set_cookie": lambda self, *args, **kwargs: None})()
        with patch.dict(os.environ, {"VP_HERDR_WEBUI_URL": "http://cell:8789/"}):
            good = server.login(server.Login(password=PASSWORD, next="http://cell:8789/dash/vp"),
                                request, response)
            refused = server.login(server.Login(password=PASSWORD, next="http://evil.example/"),
                                   request, response)
        self.assertEqual("http://cell:8789/dash/vp", good["next"])
        # A refused target falls back to the herdr web UI, never to an outside
        # site and never to a dead end (owner #956 retired the desk UI).
        self.assertEqual("http://cell:8789/", refused["next"])


if __name__ == "__main__":
    unittest.main()
