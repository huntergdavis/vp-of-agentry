"""Read-only Chromium acceptance against a temporary server and its built bundle.

VP_BASE_URL=http://127.0.0.1:18879 VP_TEST_CREDENTIALS_PATH=data/t90-server/owner-credentials
.venv/bin/python tests/browser_ops_compact.py
"""
import json
import os
from pathlib import Path
from playwright.sync_api import sync_playwright

ROOT = Path(__file__).resolve().parents[1]
BASE = os.environ["VP_BASE_URL"]
credentials = Path(os.environ["VP_TEST_CREDENTIALS_PATH"])
password = dict(line.split(": ", 1) for line in credentials.read_text().strip().splitlines())["Password"]
chrome = sorted((Path.home() / ".cache/ms-playwright").glob("chromium-*/chrome-linux64/chrome"))[-1]

with sync_playwright() as p:
    browser = p.chromium.launch(executable_path=str(chrome), args=["--no-sandbox"])
    for width, height in ((1440, 900), (390, 844)):
        page = browser.new_page(viewport={"width": width, "height": height})
        errors = []
        page.on("pageerror", lambda error: errors.append(str(error)))
        page.goto(BASE + "/dash/operations")
        page.locator("#password").fill(password)
        page.get_by_role("button", name="Open desk").click()
        page.locator("[data-ops-section=brief]").wait_for(timeout=45000)
        board = page.request.get(BASE + "/api/ops-board").json()
        assert board["no_model"] is True
        assert set(board) - {"generated_at", "interval_s", "no_model", "refresh_error"} == {"brief", "attention", "reference"}
        for source in board["brief"].values():
            assert source["source"] and source["state"] and source["generated_at"]
        assert page.locator("[data-ops-section]").count() == 3
        assert page.locator("details").count() == 1
        assert page.locator("details[open]").count() == 0
        assert page.locator("table:visible").count() == 0
        assert not errors, errors
        assert page.evaluate("document.documentElement.scrollWidth <= innerWidth")
        page.screenshot(path=str(ROOT / "data" / f"ops-live-{width}.png"))
        page.locator("summary").click()
        assert page.locator("table:visible").count() == 3
        page.locator("summary").click()

        # Source failures never look like healthy zeroes.
        missing = json.loads(json.dumps(board))
        missing["brief"]["tasks"].update(state="unavailable", open=None, owner=None)
        missing["attention"]["owner"].update(state="unavailable", items=[])
        page.route("**/api/ops-board", lambda r: r.fulfill(json=missing))
        page.reload()
        page.get_by_text("Owner task assignments unavailable.").wait_for()
        assert "unavailable open tasks" in page.locator(".ops-brief").inner_text()

        # Project grouping stays one level deep; terminal selection still works.
        rows = [
            dict(pane_id="%a", name="alpha", project="Project A", agent="codex", last_activity_s=2, send="guarded", can_type=False),
            dict(pane_id="%b", name="beta", project="Project A", agent="claude", last_activity_s=8, send="guarded", can_type=False),
            dict(pane_id="%c", name="gamma", project="Project B", agent="pi", last_activity_s=None, send="guarded", can_type=False),
        ]
        page.route("**/api/fleet", lambda r: r.fulfill(json={"rows": rows}))
        page.route("**/api/pane-text?*", lambda r: r.fulfill(json={"text": "synthetic terminal"}))
        page.goto(BASE + "/dash/fleet")
        page.locator(".fleet-project").first.wait_for()
        assert page.locator(".fleet-project").count() == 2
        assert page.locator("details details").count() == 0
        page.locator(".fleet-project summary").first.click()
        page.get_by_role("button", name="alpha").click()
        page.get_by_text("synthetic terminal").wait_for()
        assert page.get_by_role("button", name="Send", exact=True).is_disabled()
        # A daemon outage must be explicit, not an empty fleet.
        page.unroute("**/api/fleet")
        page.route("**/api/fleet", lambda r: r.fulfill(json={
            "state": "unavailable", "error": "identity refused", "rows": [], "count": None}))
        page.reload()
        page.get_by_role("alert").filter(has_text="Fleet unavailable: identity refused").wait_for()
        assert page.get_by_text("No active agents right now.").count() == 0
        page.unroute("**/api/fleet")
        page.route("**/api/fleet", lambda r: r.fulfill(json={"state": "ok", "rows": []}))
        page.reload()
        page.get_by_text("No active agents right now.").wait_for()
        assert page.get_by_role("alert").count() == 0
        assert not errors, errors
        print(f"{width}x{height}: live three-section API, closed reference, source failure, project grouping and terminal selection pass")
        page.close()
    browser.close()
