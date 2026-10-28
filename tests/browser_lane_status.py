"""Render the built Operations board with synthetic activity; no live services."""
import functools
import http.server
from pathlib import Path
import threading

from playwright.sync_api import sync_playwright

ROOT = Path(__file__).resolve().parents[1]


class StaticApp(http.server.SimpleHTTPRequestHandler):
    def do_GET(self):
        if self.path.startswith("/dash/"):
            self.path = "/index.html"
        super().do_GET()

    def log_message(self, *_args):
        pass


def main():
    def source(**extra):
        return dict(state="ok", source="synthetic fixture", generated_at="2026-10-27T00:00:00Z", **extra)

    lanes = [
        dict(pane_id="%missing", tab_label="Silent Codex", agent="codex", agent_status=None),
        dict(pane_id="%declared", tab_label="Declared OpenCode", agent="opencode", agent_status="working",
             agent_status_source="opencode declared turns", agent_status_inferred=True),
        dict(pane_id="%expired", tab_label="Expired turn", agent="codex", agent_status=None,
             agent_status_reason="turn expired without an end", agent_status_inferred=True),
        dict(pane_id="%backend", tab_label="Backend state", agent="claude", agent_status="idle",
             agent_status_source="terminal backend", agent_status_inferred=False),
    ]
    board = dict(generated_at="2026-10-27T00:00:00Z", no_model=True,
                 brief=dict(tasks=source(open=0, owner=0), lanes=source(working=1, idle=1, unknown=2)),
                 attention=dict(alarms=[], owner=source(items=[])), budget=None,
                 reference=dict(tasks=source(items=[]), lanes=source(items=lanes), schedules=source(items=[])))
    server = http.server.ThreadingHTTPServer(
        ("127.0.0.1", 0), functools.partial(StaticApp, directory=str(ROOT / "web/dist")))
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    try:
        chrome = sorted((Path.home() / ".cache/ms-playwright").glob("chromium-*/chrome-linux64/chrome"))[-1]
        with sync_playwright() as p:
            browser = p.chromium.launch(executable_path=str(chrome), args=["--no-sandbox"])
            try:
                for width, height in ((1440, 900), (390, 844)):
                    page = browser.new_page(viewport=dict(width=width, height=height))
                    errors = []
                    page.on("pageerror", lambda error: errors.append(str(error)))
                    def api(route):
                        if route.request.url.endswith("/api/ops-board"):
                            route.fulfill(json=board)
                        elif "/poolrad-dashboard/" in route.request.url:
                            route.fulfill(status=503, json={"detail": "outside this fixture"})
                        else:
                            route.fulfill(json={})
                    page.route("**/api/**", api)
                    page.goto(f"http://127.0.0.1:{server.server_port}/dash/operations")
                    page.locator('[data-lane-status="%missing"]').wait_for()
                    for pane, label in (
                        ("%missing", "inferred: no activity source"),
                        ("%declared", "inferred: opencode declared turns"),
                        ("%expired", "inferred: turn expired without an end"),
                        ("%backend", "source: terminal backend"),
                    ):
                        cell = page.locator(f'[data-lane-status="{pane}"]')
                        assert cell.is_visible() and label in cell.inner_text(), cell.inner_text()
                    assert page.locator('[data-lane-status="%missing"]').inner_text().startswith("—")
                    assert page.locator('[data-lane-status="%declared"]').inner_text().startswith("working")
                    assert not errors, errors
                    assert page.evaluate("document.documentElement.scrollWidth <= innerWidth")
                    print(f"PASS {width}x{height}: four status/provenance cases visible, no page errors or document overflow")
                    page.close()
            finally:
                browser.close()
    finally:
        server.shutdown()
        server.server_close()
        thread.join(timeout=5)


if __name__ == "__main__":
    main()
