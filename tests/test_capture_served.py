"""Real Chromium controls for the served-capture tool; only temporary loopback APIs.

Run through the shared heavy wrapper with VP_CAPTURE_BROWSER_TEST=1. Playwright
and Chromium are separate test prerequisites; no desk credential or service used.
"""
import hashlib
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile
from threading import Thread
import unittest

ROOT = Path(__file__).resolve().parents[1]
PASSWORD = "synthetic-capture-password-marker"
SESSION = "synthetic-session-marker"


@unittest.skipUnless(os.environ.get("VP_CAPTURE_BROWSER_TEST") == "1",
                     "Set VP_CAPTURE_BROWSER_TEST=1 under the heavy wrapper")
class ServedCaptureTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.credentials = self.root / "credentials"
        self.credentials.write_text("Password: " + PASSWORD + "\n")
        self.requests = []
        self.script_bodies = []
        self.documents = 0
        self.mode = "normal"
        owner = self

        class Handler(BaseHTTPRequestHandler):
            def log_message(self, *args):
                pass

            def reply(self, status, body=b"", content_type="text/html", headers=None):
                self.send_response(status)
                self.send_header("Content-Type", content_type)
                self.send_header("Content-Length", str(len(body)))
                for name, value in (headers or {}).items():
                    self.send_header(name, value)
                self.end_headers()
                self.wfile.write(body)

            def do_POST(self):
                owner.requests.append(("POST", self.path))
                data = self.rfile.read(int(self.headers.get("Content-Length", 0)))
                if self.path != "/api/login":
                    self.reply(500)
                elif owner.mode == "auth_redirect":
                    self.reply(302, headers={"Location": "/must-not-follow"})
                elif json.loads(data).get("password") != PASSWORD:
                    self.reply(401)
                else:
                    self.reply(200, b'{"ok":true}', "application/json",
                               {"Set-Cookie": "vp_session=" + SESSION + "; HttpOnly; Path=/"})

            def do_GET(self):
                owner.requests.append(("GET", self.path))
                if self.path == "/favicon.ico":
                    self.reply(204)
                    return
                if SESSION not in self.headers.get("Cookie", ""):
                    self.reply(401)
                    return
                if self.path == "/dash/cos":
                    owner.documents += 1
                    suffix = str(owner.documents) if owner.mode == "bundle_filename_drift" else "fixture"
                    script = "/assets/index-" + suffix + ".js?private=" + PASSWORD
                    html = ('<!doctype html><title>Isolated desk</title>'
                            '<script type="module" src="' + script + '"></script>')
                    self.reply(200, html.encode())
                elif self.path.startswith("/assets/index-"):
                    if owner.mode in ("script_redirect", "redirect_chain"):
                        location = "/redirect-hop" if owner.mode == "redirect_chain" else owner.redirect_url
                        self.reply(302, headers={"Location": location})
                        return
                    if owner.mode == "missing_bundle":
                        self.reply(404)
                        return
                    script = "document.body.innerHTML='<nav class=\"dash-nav\">Fixture desk</nav>';"
                    if owner.mode in ("post", "put", "telemetry"):
                        path = "/api/viewport" if owner.mode == "telemetry" else "/api/write"
                        method = "PUT" if owner.mode == "put" else "POST"
                        script += f"fetch('{path}',{{method:'{method}'}}).catch(()=>{{}});"
                    if owner.mode == "dialog":
                        script += "document.body.insertAdjacentHTML('beforeend','<dialog open>Appearance</dialog>');"
                    if owner.mode == "foreign":
                        script += "fetch('http://127.0.0.1:1/private?token=synthetic-session-marker').catch(()=>{});"
                    if owner.mode == "javascript_error":
                        script += "throw new Error('synthetic-capture-password-marker');"
                    if owner.mode in ("bundle_drift", "bundle_filename_drift"):
                        script += "// response " + str(len(owner.script_bodies))
                    body = script.encode()
                    owner.script_bodies.append(body)
                    self.reply(200, body, "application/javascript")
                elif self.path == "/redirect-hop":
                    self.reply(302, headers={"Location": owner.redirect_url})
                else:
                    self.reply(404)

        self.server = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
        thread = Thread(target=self.server.serve_forever, daemon=True)
        thread.start()
        self.addCleanup(self.server.server_close)
        self.addCleanup(self.server.shutdown)

    def run_capture(self, mode="normal"):
        self.mode = mode
        out = self.root / mode
        result = subprocess.run([
            sys.executable, str(ROOT / "tools/capture_served.py"),
            "--url", f"http://127.0.0.1:{self.server.server_port}",
            "--credentials-path", str(self.credentials), "--output", str(out),
            "--settle-ms", "50", "--timeout-ms", "5000",
        ], capture_output=True, text=True, timeout=45)
        evidence = json.loads((out / "evidence.json").read_text())
        all_text = result.stdout + result.stderr + (out / "evidence.json").read_text()
        for secret in (PASSWORD, SESSION, str(self.credentials)):
            self.assertNotIn(secret, all_text)
        if os.environ.get("VP_CAPTURE_TEST_ARTIFACTS"):
            shutil.copytree(out, Path(os.environ["VP_CAPTURE_TEST_ARTIFACTS"]) / mode)
        return result, evidence, out

    def test_actual_response_hashes_two_viewports_and_one_login(self):
        result, evidence, out = self.run_capture()
        self.assertEqual(0, result.returncode, result.stdout + result.stderr)
        self.assertTrue(evidence["passed"])
        self.assertEqual([(1440, 900), (390, 844)],
                         [(r["viewport"]["width"], r["viewport"]["height"]) for r in evidence["cases"]])
        self.assertEqual([("POST", "/api/login")], [r for r in self.requests if r[0] != "GET"])
        for record, body in zip(evidence["cases"], self.script_bodies):
            self.assertTrue(record["dialog_closed"])
            self.assertEqual(200, record["http_status"])
            self.assertEqual("index-fixture.js", record["bundles"][0]["name"])
            self.assertEqual(hashlib.sha256(body).hexdigest(), record["bundles"][0]["sha256"])
            self.assertEqual(hashlib.sha256((out / record["screenshot"]).read_bytes()).hexdigest(),
                             record["screenshot_sha256"])

    def assert_refused(self, mode, code):
        result, evidence, out = self.run_capture(mode)
        self.assertEqual(1, result.returncode, result.stdout + result.stderr)
        self.assertFalse(evidence["passed"])
        self.assertIn(code, [r["code"] for r in evidence["failures"]])
        self.assertEqual([], list(out.glob("*.png")))
        self.assertEqual([("POST", "/api/login")], [r for r in self.requests if r[0] != "GET"])
        return evidence

    def test_post_attempt_never_reaches_server(self):
        self.assert_refused("post", "request_policy_violation")

    def test_put_attempt_never_reaches_server(self):
        self.assert_refused("put", "request_policy_violation")

    def test_viewport_telemetry_is_not_silently_allowed(self):
        self.assert_refused("telemetry", "request_policy_violation")

    def test_open_dialog_refuses_screenshots(self):
        self.assert_refused("dialog", "dialog_present")

    def test_foreign_origin_refused_without_url_in_receipt(self):
        self.assert_refused("foreign", "request_policy_violation")

    def test_missing_bundle_cannot_pass(self):
        self.assert_refused("missing_bundle", "page_or_bundle_failure")

    def test_page_error_redacted(self):
        self.assert_refused("javascript_error", "page_or_bundle_failure")

    def test_changed_bundle_between_viewports_invalidates_all_captures(self):
        self.assert_refused("bundle_drift", "bundle_changed_during_capture")

    def test_changed_bundle_filename_and_bytes_invalidates_all_captures(self):
        evidence = self.assert_refused("bundle_filename_drift", "bundle_changed_during_capture")
        self.assertEqual([["index-1.js"], ["index-2.js"]],
                         [[b["name"] for b in row["bundles"]] for row in evidence["cases"]])

    def check_redirect(self, mode):
        external_requests = []

        class External(BaseHTTPRequestHandler):
            def log_message(self, *args):
                pass

            def do_GET(self):
                external_requests.append(self.path)
                self.send_response(200)
                self.send_header("Content-Type", "application/javascript")
                self.end_headers()
                self.wfile.write(b"document.body.innerHTML='<nav class=\"dash-nav\">Foreign script</nav>';")

        server = ThreadingHTTPServer(("127.0.0.1", 0), External)
        Thread(target=server.serve_forever, daemon=True).start()
        try:
            self.redirect_url = f"http://127.0.0.1:{server.server_port}/redirected.js"
            evidence = self.assert_refused(mode, "request_policy_violation")
            self.assertEqual([], external_requests, "Redirect left the allowed origin before refusal")
            self.assertNotIn(("GET", "/redirect-hop"), self.requests)
            self.assertIn({"reason": "redirect"}, evidence["violations"])
            if os.environ.get("VP_CAPTURE_TEST_ARTIFACTS"):
                path = Path(os.environ["VP_CAPTURE_TEST_ARTIFACTS"]) / mode / "server-observations.json"
                path.write_text(json.dumps(dict(external_requests=external_requests,
                    redirect_hop_requests=sum(path == "/redirect-hop" for _, path in self.requests))))
        finally:
            server.shutdown()
            server.server_close()

    def test_cross_origin_script_redirect_never_leaves_origin(self):
        self.check_redirect("script_redirect")

    def test_same_origin_hop_cannot_hide_foreign_redirect(self):
        self.check_redirect("redirect_chain")

    def test_login_redirect_not_followed(self):
        self.assert_refused("auth_redirect", "authentication_http_status")
        self.assertEqual([("POST", "/api/login")], self.requests)


if __name__ == "__main__":
    unittest.main()
