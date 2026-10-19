"""The Herdr web UI frame must follow the host the owner signed in on.

The proxy in front of herdr-webui validates the desk's own session cookie, and
that cookie is bound to one hostname. A frame pointed at a different host
would not carry it and would answer 401.
"""

import importlib
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from fastapi import HTTPException, Request

server = importlib.import_module("server.app")


class HerdrWebUiTests(unittest.TestCase):
    def setUp(self):
        temporary = tempfile.TemporaryDirectory()
        self.addCleanup(temporary.cleanup)
        root = Path(temporary.name)
        for name, value in (("DB", root / "messages.sqlite3"), ("AUTH", root / "auth.json"),
                            ("CREDENTIALS", root / "owner-credentials")):
            override = patch.object(server, name, value)
            override.start()
            self.addCleanup(override.stop)
        server._initialize()
        self.token = server._auth_record()["token"]

    def request_for(self, host: str):
        return Request({"type": "http", "scheme": "http", "server": (host, 8787),
                        "client": ("127.0.0.1", 1234), "path": "/api/herdr-webui",
                        "headers": [(b"host", f"{host}:8787".encode()),
                                    (b"authorization", f"Bearer {self.token}".encode())]})

    def test_the_frame_follows_the_host_the_owner_used(self):
        with patch.dict("os.environ", {"VP_HERDR_WEBUI_URL": "http://192.168.0.209:8789/",
                                       "VP_HERDR_WEBUI_LABEL": "Herdr web UI"}):
            for host, expected in (("192.168.0.209", "http://192.168.0.209:8789/"),
                                   ("cell", "http://cell:8789/"),
                                   ("localhost", "http://localhost:8789/")):
                request = self.request_for(host)
                result = server.herdr_webui(request, server.require_auth(request))
                self.assertTrue(result["available"])
                self.assertEqual(expected, result["url"])
                self.assertEqual("Herdr web UI", result["label"])

    def test_an_unconfigured_host_reports_unavailable(self):
        with patch.dict("os.environ", {"VP_HERDR_WEBUI_URL": ""}):
            request = self.request_for("cell")
            result = server.herdr_webui(request, server.require_auth(request))
            self.assertFalse(result["available"])
            self.assertEqual("", result["url"])

    def test_the_route_requires_auth(self):
        route = next(route for route in server.app.routes
                     if route.path == "/api/herdr-webui" and "GET" in route.methods)
        self.assertIn(server.require_auth, [dependency.call for dependency in route.dependant.dependencies])
        with self.assertRaises(HTTPException) as denied:
            request = Request({"type": "http", "scheme": "http", "server": ("localhost", 80),
                                "client": ("127.0.0.1", 1234), "path": "/api/herdr-webui",
                                "headers": [(b"host", b"localhost")]})
            server.require_auth(request)
        self.assertEqual(401, denied.exception.status_code)

    def test_a_malformed_url_is_left_alone(self):
        for configured in ("not a url", "://broken", "http://host:notaport/"):
            self.assertEqual(configured, server._host_agnostic_url(configured, "cell"))


if __name__ == "__main__":
    unittest.main()
