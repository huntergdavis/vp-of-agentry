"""Budget UI acceptance; uses the same temporary server setup as browser_ops_compact."""
import json
import os
from pathlib import Path
from playwright.sync_api import sync_playwright

ROOT = Path(__file__).resolve().parents[1]
BASE = os.environ["VP_BASE_URL"]
password = dict(line.split(": ", 1) for line in Path(os.environ["VP_TEST_CREDENTIALS_PATH"]).read_text().strip().splitlines())["Password"]
chrome = sorted((Path.home() / ".cache/ms-playwright").glob("chromium-*/chrome-linux64/chrome"))[-1]

with sync_playwright() as p:
    browser = p.chromium.launch(executable_path=str(chrome), args=["--no-sandbox"])
    for width, height in ((1440, 900), (390, 844)):
        page = browser.new_page(viewport={"width": width, "height": height})
        errors = []
        page.on("pageerror", lambda e: errors.append(str(e)))
        page.goto(BASE + "/dash/operations")
        page.locator("#password").fill(password)
        page.get_by_role("button", name="Open desk").click()
        page.locator(".ops-budget").wait_for(timeout=45000)
        board = page.request.get(BASE + "/api/ops-board").json()
        assert board["no_model"] is True
        assert board["budget"]["source"] == "dunkingsheep --json usage"
        assert len(board["budget"]["providers"]) >= 3
        assert page.locator("[data-ops-section]").count() == 4
        assert page.locator("details").count() == 1
        assert page.evaluate("document.documentElement.scrollWidth <= innerWidth")
        page.screenshot(path=str(ROOT / "data" / f"budget-live-{width}.png"), full_page=True)

        # Exercise missing data rather than depending on today's account availability.
        fixture = json.loads(json.dumps(board))
        codex = next(r for r in fixture["budget"]["providers"] if r["provider"] == "codex")
        codex.update(windows=[], state="unknown", reason="no windows reported")
        claude = next(r for r in fixture["budget"]["providers"] if r["provider"] == "claude")
        claude.update(state="stale", extra_usage=dict(used_credits=90154, monthly_limit=90000, utilization=100, spend_limit_reached=False))
        claude["windows"] = [dict(name="custom_window", state="expired", percent_used=25, percent_remaining=75, resets_at=None)]
        page.route("**/api/ops-board", lambda r: r.fulfill(json=fixture))
        page.reload()
        page.locator(".ops-budget").wait_for()
        codex_ui = page.locator(".budget-provider").filter(has=page.locator(".budget-provider-head strong", has_text="codex"))
        assert "No window data" in codex_ui.inner_text()
        assert "0.0% left" not in codex_ui.inner_text()
        claude_ui = page.locator(".budget-provider").filter(has=page.locator(".budget-provider-head strong", has_text="claude"))
        assert "custom_window" in claude_ui.inner_text()
        assert "75.0% left" in claude_ui.inner_text()
        assert "stale" in claude_ui.inner_text() and "expired" in claude_ui.inner_text()
        assert "90154 / 90000 credits" in claude_ui.inner_text()
        assert "spend_limit_reached: false" in claude_ui.inner_text()
        assert "Dollars remaining and per-agent dollar balances are unknown" in page.locator(".ops-budget").inner_text()
        assert not errors, errors
        print(f"{width}x{height}: live command budget, arbitrary windows, unknown/stale/expired data and raw credit flag pass")
        page.close()
    browser.close()
