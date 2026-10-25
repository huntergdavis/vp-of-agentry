"""Current desk navigation must never bounce owners into the retired manager."""

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

    def test_root_stays_on_desk_with_or_without_login(self):
        for cookie in (None, self.session_cookie()):
            response = self.redirect_for("/", cookie=cookie)
            self.assertEqual(200, response.status_code)
            self.assertNotIn("location", response.headers)

    def test_legacy_paths_return_to_cos_without_old_manager(self):
        for path in ("/conversation", "/session/default", "/session/default/workspace/w1",
                     "/index.html", "/nonsense"):
            response = self.redirect_for(path, query="x=1")
            self.assertEqual(307, response.status_code)
            self.assertEqual("/dash/cos", response.headers["location"])

    def test_old_board_and_chat_aliases_keep_their_destination(self):
        for name in ("poolrad", "operations", "play", "vp", "cos", "fleet"):
            response = self.redirect_for("/" + name)
            self.assertEqual("/dash/" + name, response.headers["location"])

    def test_current_routes_are_not_redirected(self):
        for path in ("/dash/cos", "/dash/vp", "/dash/fleet", "/api/channels",
                     "/api/messages", "/assets/index-x.js"):
            self.assertEqual(200, self.redirect_for(path).status_code)

    def test_login_defaults_to_cos_even_with_old_manager_configured(self):
        request = build_request("/api/login")
        response = type("Response", (), {"set_cookie": lambda self, *a, **kw: None})()
        with patch.dict(os.environ, {"VP_HERDR_WEBUI_URL": "http://cell:8789/"}):
            for target in (None, "http://cell:8789/session/default"):
                result = server.login(server.Login(password=PASSWORD, next=target), request, response)
                self.assertEqual("/dash/cos", result["next"])

    def test_login_keeps_an_explicit_current_chat_target(self):
        request = build_request("/api/login")
        response = type("Response", (), {"set_cookie": lambda self, *a, **kw: None})()
        result = server.login(server.Login(password=PASSWORD, next="/dash/vp"), request, response)
        self.assertEqual("/dash/vp", result["next"])


if __name__ == "__main__":
    unittest.main()
