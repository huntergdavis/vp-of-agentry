"""Authenticated browser check for chat layout, activity scroll, and send path.

Install Playwright separately from the production runtime:
  .venv/bin/pip install playwright
  .venv/bin/python -m playwright install chromium

Set VP_TEST_SEND=1 to submit one message in each viewport.
"""

import os
import time
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
        page.wait_for_timeout(2500)
        box = page.locator(".composer").bounding_box()
        assert box, "composer is missing"
        assert box["y"] >= 0 and box["y"] + box["height"] <= height + 1, (width, height, box)
        assert page.locator(".editor").is_visible(), "rich text editor is not visible"
        assert page.locator("button.send").is_visible(), "send button is not visible"
        assert not errors, errors
        screenshot = ROOT / "data" / f"browser-{width}x{height}.png"
        page.screenshot(path=str(screenshot))
        print(f"{width}x{height}: composer visible at y={box['y']:.0f}, bottom={box['y'] + box['height']:.0f}; screenshot={screenshot}")
        if width == 1440:
            activity = page.locator(".activity-body")
            activity_responses = []
            page.on("response", lambda response: activity_responses.append(response.status) if "/api/activity?" in response.url else None)
            scroll = activity.evaluate("e => ({height:e.clientHeight, content:e.scrollHeight, top:e.getBoundingClientRect().top, bottom:e.getBoundingClientRect().bottom})")
            assert scroll["bottom"] <= height + 1 and scroll["height"] > 0, scroll
            if scroll["content"] > scroll["height"]:
                activity.evaluate("e => e.scrollTop = 0")
                activity.hover()
                page.mouse.wheel(0, 400)
                assert activity.evaluate("e => e.scrollTop") > 0, "activity pane did not wheel-scroll"
                activity.evaluate("e => e.scrollTop = 0")
                page.wait_for_timeout(6000)
                assert activity.evaluate("e => e.scrollTop") <= 1, "activity poll overrode reader's scroll position"
                assert any(status == 200 for status in activity_responses), "activity did not refresh"
            print(f"desktop activity scroll: {scroll}")
            assert "refreshed" in page.locator(".activity-live").inner_text()
            if os.getenv("VP_TEST_STATUS") == "1":
                phase = {"value": "waiting"}
                def mocked_channels(route):
                    response = route.fetch()
                    payload = response.json()
                    for candidate in payload["channels"]:
                        if candidate["id"] == "vp":
                            candidate["status"] = phase["value"]
                            candidate["can_message"] = True
                    route.fulfill(response=response, json=payload)
                page.route("**/api/channels", mocked_channels)
                page.reload(wait_until="networkidle")
                page.locator(".status-badge.waiting").wait_for()
                assert page.locator("button.send").is_enabled()
                page.get_by_role("button", name="Message agent").click()
                assert page.locator(".editor").evaluate("e => document.activeElement === e")
                phase["value"] = "working"
                page.locator(".status-badge.working").wait_for(timeout=16000)
                page.unroute("**/api/channels", mocked_channels)
                print("waiting→working presence poll, message action while waiting: OK")
        if os.getenv("VP_TEST_SEND") == "1":
            marker = f"Browser keyboard check {width} {int(time.time())}"
            editor = page.locator(".editor")
            editor.fill(marker)
            editor.press("Shift+Enter")
            page.keyboard.type("second line")
            assert "<br" in editor.inner_html().lower(), "Shift+Enter did not create a line break"
            editor.evaluate("e => e.dispatchEvent(new KeyboardEvent('keydown', {key:'Enter', isComposing:true, bubbles:true, cancelable:true}))")
            assert page.locator(".message-wrap.owner").filter(has_text=marker).count() == 0, "IME composition sent unexpectedly"
            editor.press("Enter")
            editor.press("Enter")
            owner_message = page.locator(".message-wrap.owner").filter(has_text=marker)
            owner_message.wait_for(timeout=15000)
            assert owner_message.count() == 1, "Enter submitted a duplicate message"
            assert "second line" in owner_message.inner_text()
            assert owner_message.locator(".delivery").inner_text() in {"sent", "queued"}
            print(f"{width}x{height}: Shift+Enter newline, IME guard, and single Enter submission: OK")
        if width == 390:
            page.get_by_role("button", name="Live signal").click()
            assert page.locator(".activity.open").is_visible(), "mobile activity drawer is hidden"
            assert page.locator(".activity-body").bounding_box()["height"] > 100
            page.get_by_role("button", name="Close live signal").click()
        page.close()
    browser.close()
