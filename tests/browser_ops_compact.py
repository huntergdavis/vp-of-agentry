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
        assert set(board) - {"generated_at", "interval_s", "no_model", "refresh_error"} == {"brief", "attention", "reference", "budget"}
        for source in board["brief"].values():
            assert source["source"] and source["state"] and source["generated_at"]
        assert page.locator("[data-ops-section]").count() == 4
        assert page.locator("details").count() == 0
        assert page.locator("details[open]").count() == 0
        assert page.locator("table:visible").count() == 3
        assert not errors, errors
        assert page.evaluate("document.documentElement.scrollWidth <= innerWidth")
        page.screenshot(path=str(ROOT / "data" / f"ops-live-{width}.png"))
        assert page.locator("table:visible").count() == 3

        expanded = json.loads(json.dumps(board))
        expanded["reference"]["tasks"].update(state="ok", items=[dict(
            id=f"t{i}", title=f"Visible task {i}", status="blocked" if i==44 else "in_progress" if i==43 else "open",
            assignees=["owner"] if i==42 else ["%18"], age_s=120) for i in range(45)])
        page.route("**/api/ops-board", lambda r: r.fulfill(json=expanded))
        page.reload()
        page.get_by_text("Visible task 44").wait_for()
        task_table=page.locator(".ops-reference .ops-table").filter(has=page.get_by_role("heading",name="Tasks",exact=True)).locator("table")
        assert task_table.locator("tbody tr").count()==45
        assert task_table.locator("tbody tr").nth(0).locator("td").first.inner_text()=="t44"
        assert task_table.locator("tbody tr").nth(1).locator("td").first.inner_text()=="t42"
        assert task_table.locator("tbody tr").nth(2).locator("td").first.inner_text()=="t43"
        assert page.locator("details, summary").count()==0
        assert page.evaluate("document.documentElement.scrollWidth <= innerWidth")
        page.screenshot(path=str(ROOT / "data" / f"ops-expanded-{width}.png"),full_page=True)

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
        print(f"{width}x{height}: live four-section API, always-visible reference, source failure, project grouping and terminal selection pass")
        page.close()
    browser.close()
