"""Owner sessions survive process restarts and can be revoked."""

import importlib
import sqlite3
import tempfile
import time
import unittest
from http.cookies import SimpleCookie
from pathlib import Path
from unittest.mock import patch

from fastapi import HTTPException, Request, Response

server = importlib.import_module("server.app")


def request(cookie=""):
    headers = [(b"host", b"localhost")]
    if cookie:
        headers.append((b"cookie", f"vp_session={cookie}".encode()))
    return Request({"type": "http", "scheme": "http", "server": ("localhost", 80),
                    "client": ("127.0.0.1", 1234), "path": "/", "headers": headers})


class SessionTests(unittest.TestCase):
    def setUp(self):
        temporary = tempfile.TemporaryDirectory()
        self.addCleanup(temporary.cleanup)
        root = Path(temporary.name)
        for attr, value in (("DB", root / "messages.sqlite3"), ("AUTH", root / "auth.json"),
                            ("CREDENTIALS", root / "owner-credentials")):
            p = patch.object(server, attr, value)
            p.start()
            self.addCleanup(p.stop)
        server.LOGIN_ATTEMPTS.clear()
        server._initialize()
        self.password = server.CREDENTIALS.read_text().splitlines()[0].removeprefix("Password: ")

    def login(self, password=None):
        response = Response()
        server.login(server.Login(password=password or self.password), request(), response)
        cookies = SimpleCookie()
        cookies.load(response.headers["set-cookie"])
        self.assertEqual("604800", cookies["vp_session"]["max-age"])
        self.assertTrue(cookies["vp_session"]["httponly"])
        return cookies["vp_session"].value

    def assert_denied(self, cookie):
        with self.assertRaises(HTTPException) as error:
            server.require_auth(request(cookie))
        self.assertEqual(401, error.exception.status_code)

    def test_persists_seven_days_and_expires(self):
        cookie = self.login()
        self.assertEqual("owner", server.require_auth(request(cookie)))
        self.assertEqual(1, sqlite3.connect(server.DB).execute("SELECT count(*) FROM sessions").fetchone()[0])
        # Reopening SQLite simulates the next worker process; no process-local session data is used.
        server._initialize()
        self.assertEqual("owner", server.require_auth(request(cookie)))
        with sqlite3.connect(server.DB) as conn:
            conn.execute("UPDATE sessions SET expires_at=?", (time.time() - 1,))
        self.assert_denied(cookie)

    def test_logout_and_password_change_revoke_other_sessions(self):
        current, other = self.login(), self.login()
        new_password = "new-local-owner-password"
        server.change_password(server.PasswordChange(current_password=self.password, new_password=new_password),
                               request(current), "owner")
        self.assertEqual("owner", server.require_auth(request(current)))
        self.assert_denied(other)
        self.assert_denied(self.login_attempt_old_password())
        replacement = self.login(new_password)
        self.assertEqual("owner", server.require_auth(request(replacement)))
        server.logout(request(current), Response(), "owner")
        self.assert_denied(current)
        self.assertEqual("owner", server.require_auth(request(replacement)))

    def login_attempt_old_password(self):
        with self.assertRaises(HTTPException) as error:
            self.login(self.password)
        self.assertEqual(401, error.exception.status_code)
        return "invalid-session"

    def test_manual_credential_edit_revokes_sessions(self):
        cookie = self.login()
        server.CREDENTIALS.write_text("Password: replacement-local-secret\n")
        now = time.time() + 10
        import os
        os.utime(server.CREDENTIALS, (now, now))
        self.login("replacement-local-secret")
        self.assert_denied(cookie)


if __name__ == "__main__":
    unittest.main()
