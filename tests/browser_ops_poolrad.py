"""Read-only acceptance for Poolrad in Operations using a temporary built server."""
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
        page.goto(BASE + "/dash/poolrad")
        page.locator("#password").fill(password)
        page.get_by_role("button", name="Open desk").click()
        page.wait_for_url("**/dash/operations#poolrad")
        page.locator("#poolrad").wait_for(timeout=45000)
        page.wait_for_function("document.querySelector('#poolrad').innerText.includes('CEILING')")
        assert page.locator(".dash-root").count() == 1
        assert page.locator(".dash-nav a[href='/dash/poolrad']").count() == 0
        assert page.locator("[data-ops-section]").count() == 4
        assert page.locator("details").count() == 1
        assert page.locator("details[open]").count() == 0
        assert page.locator(".ops-budget").count() == 1
        progress = page.request.get(BASE + "/api/poolrad-dashboard/progress").json()
        assert progress["replacements"]["commit"] == progress["commit"]
        text = page.locator("#poolrad").inner_text()
        assert "upper bound" in text and "not whole-game completion" in text
        assert f"{progress['identities']}/{progress['ceiling']}" in text
        page.get_by_role("link", name="Evidence and timestamps").click()
        assert page.locator("details[open]").count() == 1
        evidence = page.locator("#poolrad-details").inner_text()
        assert progress["generated"] in evidence
        assert progress["observed_at"] in evidence
        for comparison in progress["comparisons"]:
            assert comparison["scope"] in evidence
            assert comparison["status"] in evidence
            assert comparison["method"] in evidence
        assert "not rerun by dashboard" in evidence
        assert page.locator("details details").count() == 0
        page.screenshot(path=str(ROOT / "data" / f"poolrad-ops-evidence-{width}.png"), full_page=True)
        page.locator(".ops-reference summary").click()
        page.locator(".dash-body").evaluate("e => e.scrollTop=0")
        page.screenshot(path=str(ROOT / "data" / f"poolrad-ops-{width}.png"), full_page=True)
        assert page.evaluate("document.documentElement.scrollWidth <= innerWidth")
        assert not errors, errors
        print(f"{width}x{height}: old route redirects, one nav/page, compact ceiling headline, same-commit replacements and scoped evidence pass")
        print("headline:", text)
        page.close()
    browser.close()
