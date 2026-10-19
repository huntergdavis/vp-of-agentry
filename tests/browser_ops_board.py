"""Browser check for the compact Poolrad view and the deterministic ops board.

Uses the owner credentials from the local private file and takes screenshots
into the ignored data directory. No message is sent and no setting is
changed; the check only reads the two dashboards.
"""

import os
from pathlib import Path

from playwright.sync_api import sync_playwright

ROOT = Path(__file__).resolve().parents[1]
BASE = os.getenv("VP_BASE_URL", "http://127.0.0.1:8787")
credential_path = Path(os.getenv("VP_TEST_CREDENTIALS_PATH", ROOT / "data" / "owner-credentials"))
PASSWORD = dict(
    line.split(": ", 1)
    for line in credential_path.read_text().strip().splitlines()
)["Password"]


def chromium_path():
    configured = os.getenv("PLAYWRIGHT_CHROMIUM_EXECUTABLE")
    if configured:
        return configured
    cached = sorted((Path.home() / ".cache/ms-playwright").glob("chromium-*/chrome-linux64/chrome"))
    return str(cached[-1]) if cached else None


with sync_playwright() as playwright:
    browser = playwright.chromium.launch(
        headless=True, executable_path=chromium_path(), args=["--no-sandbox"]
    )
    for width, height in ((1440, 900), (390, 844)):
        page = browser.new_page(viewport={"width": width, "height": height})
        errors = []
        page.on("pageerror", lambda error: errors.append(str(error)))
        page.goto(BASE, wait_until="networkidle")
        page.locator("#password").fill(PASSWORD)
        page.get_by_role("button", name="Open desk").click()
        page.locator(".composer").wait_for()
        page.wait_for_timeout(1500)

        # The old read-only pane grid is gone; the live terminal UI has its slot.
        assert page.get_by_role("button", name="Herdr panes").count() == 0, "the old Herdr panes section is still there"
        assert page.get_by_role("button", name="Herdr web UI").count() == 1, "the Herdr web UI slot is missing"

        page.get_by_role("button", name="Operations dashboard").click()
        page.locator(".dash-stats").wait_for(timeout=20000)
        page.wait_for_timeout(1200)
        stats = page.locator(".dash-stats > .dash-stat")
        assert stats.count() >= 8, f"expected the headline cards, saw {stats.count()}"
        assert page.locator(".dash-panel").count() >= 4, "the task, inbox, dunk, and health panels are missing"
        assert page.locator(".dash-stats").inner_text().strip(), "the ops board rendered empty"
        assert not errors, errors
        page.screenshot(path=str(ROOT / "data" / f"ops-board-{width}x{height}.png"))

        page.get_by_role("button", name="Poolrad dashboard").click()
        page.locator(".poolrad-hero, .dash-figures").first.wait_for(timeout=20000)
        page.wait_for_timeout(800)
        numbers = page.locator(".dash-figure .num")
        assert numbers.count() == 2, "the Poolrad view must show exactly two completion numbers"
        text = page.locator(".dash-figures").inner_text()
        assert "%" in text, f"no percentage in the Poolrad view: {text}"
        evidence = page.locator(".dash-evidence").inner_text()
        assert len(evidence.splitlines()) == 1, "the evidence line must be one line"
        assert not errors, errors
        page.screenshot(path=str(ROOT / "data" / f"poolrad-progress-{width}x{height}.png"))
        print(f"{width}x{height}: ops board and Poolrad view render; Poolrad numbers={text!r}")

    # The four standalone routes the herdr web UI frames.
    for name, marker in (("poolrad", ".dash-figures"), ("operations", ".dash-stats"),
                         ("play", ".game-view"), ("vp", ".dash-conversation")):
        page = browser.new_page(viewport={"width": 1440, "height": 900})
        errors = []
        page.on("pageerror", lambda error: errors.append(str(error)))
        page.goto(BASE, wait_until="networkidle")
        page.locator("#password").fill(PASSWORD)
        page.get_by_role("button", name="Open desk").click()
        page.locator(".composer").wait_for()
        page.goto(f"{BASE}/dash/{name}", wait_until="networkidle")
        page.locator(marker).first.wait_for(timeout=20000)
        page.wait_for_timeout(600)
        assert page.locator(".dash-root").count() == 1, f"/dash/{name} did not render the dashboard shell"
        assert page.locator(".sidebar").count() == 0, f"/dash/{name} still shows the desk sidebar"
        assert page.locator(".dash-nav").count() == 1, f"/dash/{name} is missing the dashboard nav"
        assert not errors, errors
        page.screenshot(path=str(ROOT / "data" / f"dash-{name}.png"))
        print(f"/dash/{name}: standalone view renders without desk chrome")

    # Without a session the route must show the password UI, never content.
    fresh = browser.new_context(viewport={"width": 1440, "height": 900})
    page = fresh.new_page()
    page.goto(f"{BASE}/dash/poolrad", wait_until="networkidle")
    assert "/?next=" in page.url, f"the unauthenticated route did not return to the login: {page.url}"
    page.locator("#password").wait_for(timeout=15000)
    assert page.locator("#password").count() == 1, "the password UI is missing"
    assert page.locator(".dash-figures").count() == 0, "dashboard content leaked to an unauthenticated caller"
    fresh.close()
    print("unauthenticated /dash/poolrad returns to the password UI")
    browser.close()
print("browser check passed")
