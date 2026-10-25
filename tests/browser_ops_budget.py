"""Budget UI acceptance; uses the same temporary server setup as browser_ops_compact."""
import json
import os
import sys
import subprocess
from datetime import datetime, timedelta
from pathlib import Path
from playwright.sync_api import sync_playwright

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
import ops_budget
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
        page.wait_for_function("!document.querySelector('.ops-budget').innerText.includes('not read yet')", timeout=65000)
        board = page.request.get(BASE + "/api/ops-board").json()
        assert board["no_model"] is True
        assert board["budget"]["source"] == "dunkingsheep --json usage"
        assert len(board["budget"]["providers"]) >= 3
        assert page.locator("[data-ops-section]").count() == 4
        assert page.locator("details").count() == 0
        assert page.evaluate("document.documentElement.scrollWidth <= innerWidth")
        page.screenshot(path=str(ROOT / "data" / f"budget-live-{width}.png"), full_page=True)

        # Exercise missing data rather than depending on today's account availability.
        fixture = json.loads(json.dumps(board))
        codex = next(r for r in fixture["budget"]["providers"] if r["provider"] == "codex")
        codex.update(windows=[], state="unknown", reason="no windows reported")
        claude = next(r for r in fixture["budget"]["providers"] if r["provider"] == "claude")
        claude.update(state="stale", meaning="percent_used", extra_usage=dict(used_credits=90154, monthly_limit=90000, utilization=100, spend_limit_reached=False))
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
        # Actual stale collector shape must retain a number plus its measurement age.
        now = datetime.fromisoformat(subprocess.check_output(
            ["date", "-u", "+%Y-%m-%dT%H:%M:%SZ"], text=True).strip().replace("Z", "+00:00"))
        fixture["budget"] = ops_budget.project([
            dict(provider="codex", status="unknown", meaning="percent_used",
                 measured_at=(now - timedelta(minutes=10)).timestamp(),
                 last_snapshot=dict(percent_used=33, window_minutes=10080,
                                    resets_at=(now + timedelta(days=2)).timestamp())),
            dict(provider="claude", status="error", meaning="unknown",
                 measured_at=now.timestamp(), error="usage endpoint HTTP 429: rate_limit_error"),
        ], [], now)
        page.reload()
        page.locator(".ops-budget").wait_for()
        assert "33.0% used" in codex_ui.inner_text()
        assert "read 10 min ago" in codex_ui.inner_text()
        assert "stale" not in codex_ui.inner_text()
        assert "claude endpoint rate-limited (HTTP 429)" in claude_ui.inner_text()
        assert "checked " in claude_ui.inner_text()
        assert "0.0%" not in claude_ui.inner_text()
        # A twelve-minute reading is normal under the owner's thirty-minute cadence.
        fixture["budget"]["providers"][0]["measured_at"] = (now-timedelta(minutes=12)).isoformat()
        fixture["budget"]["providers"][0]["age_s"] = 720
        fixture["budget"]["providers"].append(dict(
            provider="pi", state="not_read_yet", meaning="unknown", measured_at=None,
            age_s=None, windows=[], reason="Waiting for the first provider reading"))
        page.reload()
        page.locator(".ops-budget").wait_for()
        assert "read 12 min ago" in codex_ui.inner_text()
        assert "stale" not in codex_ui.inner_text()
        assert "not read yet" in page.locator(".budget-provider").filter(
            has=page.locator(".budget-provider-head strong", has_text="pi")).inner_text()
        # A rate limit retains the previous successful quota, distinctly labelled.
        fixture["budget"]["providers"][1] = ops_budget.project([dict(
            provider="claude", status="error", measured_at=now.timestamp(), error="HTTP 429",
            last_good=dict(provider="claude", status="ok", meaning="percent_used",
                           measured_at=(now - timedelta(minutes=10)).timestamp(),
                           windows=[dict(name="weekly", percent_used=82, percent_remaining=18)]))], [], now)["providers"][0]
        page.reload()
        page.locator(".ops-budget").wait_for()
        assert "82.0% used" in claude_ui.inner_text()
        assert "Last reading" in claude_ui.inner_text()
        assert "read 10 min ago" in claude_ui.inner_text()
        assert "HTTP 429" in claude_ui.inner_text() and "failed " in claude_ui.inner_text()
        page.screenshot(path=str(ROOT / "data" / f"budget-stale-{width}.png"), full_page=True)
        assert not errors, errors
        print(f"{width}x{height}: live budget, ten/twelve-minute neutral value+age, retained429 values, pending/expired data pass")
        page.close()
    browser.close()
