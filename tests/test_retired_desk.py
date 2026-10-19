"""The old desk UI is retired: :8787 keeps only what the shell needs.

Owner #956: the herdr web UI on :8789 is the front door. :8787 keeps the
four standalone dashboards, their assets, the API and the login page; every
other path is a permanent redirect to the shell, and no redirect can bounce
back to the desk.
"""

import asyncio
import importlib
import os
import secrets
import tempfile
import time
import unittest
from pathlib import Path
from unittest.mock import patch

from starlette.requests import Request
from starlette.responses import Response

server = importlib.import_module("server.app")
PASSWORD = "test-owner-password"


def build_request(path="/", host="cell", cookie=None, query=""):
    headers = [(b"host", f"{host}:8787".encode())]
    if cookie:
        headers.append((b"cookie", f"vp_session={cookie}".encode()))
    return Request({"type": "http", "scheme": "http", "server": (host, 8787),
                    "client": ("127.0.0.1", 1234), "path": path, "query_string": query.encode(),
                    "headers": headers})


async def passthrough(request):
    return Response("served by the desk", status_code=200)


class RetiredDeskTests(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory()
        self.addCleanup(self.temporary.cleanup)
        root = Path(self.temporary.name)
        for name, value in (("DB", root / "messages.sqlite3"), ("AUTH", root / "auth.json"),
                            ("CREDENTIALS", root / "owner-credentials")):
            override = patch.object(server, name, value)
            override.start()
            self.addCleanup(override.stop)
        with patch.dict(os.environ, {"VP_PASSWORD": PASSWORD,
                                     "VP_HERDR_WEBUI_URL": "http://192.168.0.209:8789/"}):
            server._initialize()

    def session_cookie(self):
        cookie = secrets.token_urlsafe(32)
        with server._db() as conn:
            conn.execute("INSERT INTO sessions(token_hash,expires_at) VALUES(?,?)",
                         (server._session_key(cookie), time.time() + 3600))
        return cookie

    def redirect_for(self, path, host="cell", cookie=None, query=""):
        request = build_request(path, host=host, cookie=cookie, query=query)
        return asyncio.run(server.retire_the_desk_ui(request, passthrough))

    def test_the_root_serves_the_login_page_without_a_session(self):
        response = self.redirect_for("/")
        self.assertEqual(200, response.status_code)

    def test_the_root_redirects_to_the_shell_when_signed_in(self):
        response = self.redirect_for("/", cookie=self.session_cookie())
        self.assertEqual(308, response.status_code)
        self.assertEqual("http://cell:8789/", response.headers["location"])

    def test_every_retired_path_redirects_to_the_shell(self):
        for path in ("/conversation", "/search", "/activity", "/editor", "/roster",
                     "/poolrad", "/operations", "/play", "/vp", "/nonsense",
                     "/api-unknown", "/dashboards"):
            response = self.redirect_for(path)
            self.assertEqual(308, response.status_code, f"{path} did not redirect")
            self.assertEqual("http://cell:8789/", response.headers["location"], path)

    def test_paths_the_shell_owns_keep_their_path_and_query(self):
        for path in ("/session", "/session/default", "/session/default/workspace/w1",
                     "/session/default/workspace/w1/tab/t1/pane/p1"):
            response = self.redirect_for(path, query="x=1")
            self.assertEqual(308, response.status_code)
            self.assertEqual(f"http://cell:8789{path}?x=1", response.headers["location"])

    def test_the_target_follows_the_host_the_owner_used(self):
        for host in ("cell", "localhost", "192.168.0.209"):
            response = self.redirect_for("/conversation", host=host)
            self.assertEqual(f"http://{host}:8789/", response.headers["location"])

    def test_what_the_shell_needs_is_still_served_here(self):
        for path in ("/dash", "/dash/poolrad", "/dash/operations", "/dash/play", "/dash/vp",
                     "/api", "/api/health", "/api/login", "/api/ops-board", "/assets/index-x.js"):
            response = self.redirect_for(path)
            self.assertEqual(200, response.status_code, f"{path} was redirected away")

    def test_no_redirect_can_bounce_back_to_the_desk(self):
        for path in ("/", "/conversation", "/session/default", "/nonsense", "/poolrad"):
            response = self.redirect_for(path, cookie=self.session_cookie())
            if response.status_code == 308:
                location = response.headers["location"]
                self.assertIn(":8789/", location)
                self.assertNotIn(":8787", location)

    def test_signing_in_without_a_target_lands_on_the_shell(self):
        request = build_request("/")
        response = type("Response", (), {"set_cookie": lambda self, *args, **kwargs: None})()
        with patch.dict(os.environ, {"VP_HERDR_WEBUI_URL": "http://192.168.0.209:8789/"}):
            result = server.login(server.Login(password=PASSWORD), request, response)
        self.assertEqual("http://cell:8789/", result["next"])

    def test_signing_in_keeps_an_accepted_return_target(self):
        request = build_request("/")
        response = type("Response", (), {"set_cookie": lambda self, *args, **kwargs: None})()
        with patch.dict(os.environ, {"VP_HERDR_WEBUI_URL": "http://192.168.0.209:8789/"}):
            result = server.login(server.Login(password=PASSWORD, next="/dash/vp"), request, response)
        self.assertEqual("/dash/vp", result["next"])


if __name__ == "__main__":
    unittest.main()
