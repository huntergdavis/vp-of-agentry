"""Browser check for the compact Poolrad view and the deterministic ops board.

Uses the owner credentials from the local private file and takes screenshots
into the ignored data directory. No message is sent and no setting is
changed; the check only reads the two dashboards.
"""

import os
import struct
import zlib
from pathlib import Path

from playwright.sync_api import sync_playwright

ROOT = Path(__file__).resolve().parents[1]
BASE = os.getenv("VP_BASE_URL", "http://127.0.0.1:8787")
# Headless Chromium does not hit-test native scrollbars at all, so the drag
# interaction is only meaningful in a real browser: run it headed under Xvfb.
HEADED = os.getenv("VP_HEADED") == "1"
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


def scrollbar_geometry(page, selector):
    """Where the scrollbar sits and how long its thumb is."""
    return page.locator(selector).evaluate("""e => {
        const box = e.getBoundingClientRect();
        const ratio = e.scrollHeight > 0 ? e.clientHeight / e.scrollHeight : 1;
        return {
            x: box.x + box.width - 7,
            top: box.y,
            thumbHeight: Math.max(48, e.clientHeight * ratio),
            scrollHeight: e.scrollHeight,
            clientHeight: e.clientHeight,
        };
    }""")


def png_rows(path):
    """Minimal PNG reader: (width, height, channels, rows) for 8-bit RGB/RGBA."""
    data = Path(path).read_bytes()
    if data[:8] != b"\x89PNG\r\n\x1a\n":
        raise ValueError("not a PNG")
    pos, idat, header = 8, b"", None
    while pos < len(data):
        length = int.from_bytes(data[pos:pos + 4], "big")
        kind = data[pos + 4:pos + 8]
        payload = data[pos + 8:pos + 8 + length]
        pos += 12 + length
        if kind == b"IHDR":
            header = payload
        elif kind == b"IDAT":
            idat += payload
        elif kind == b"IEND":
            break
    width, height, depth, color, _, _, interlace = struct.unpack(">IIBBBBB", header)
    if depth != 8 or color not in (2, 6) or interlace:
        raise ValueError("unsupported PNG layout")
    channels = 3 if color == 2 else 4
    raw = zlib.decompress(idat)
    stride = width * channels
    rows, previous, offset = [], bytearray(stride), 0
    for _ in range(height):
        filt = raw[offset]
        offset += 1
        line = bytearray(raw[offset:offset + stride])
        offset += stride
        for i in range(stride):
            a = line[i - channels] if i >= channels else 0
            b = previous[i]
            c = previous[i - channels] if i >= channels else 0
            if filt == 1:
                line[i] = (line[i] + a) & 0xFF
            elif filt == 2:
                line[i] = (line[i] + b) & 0xFF
            elif filt == 3:
                line[i] = (line[i] + (a + b) // 2) & 0xFF
            elif filt == 4:
                p = a + b - c
                pa, pb, pc = abs(p - a), abs(p - b), abs(p - c)
                pred = a if (pa <= pb and pa <= pc) else (b if pb <= pc else c)
                line[i] = (line[i] + pred) & 0xFF
        rows.append(bytes(line))
        previous = line
    return width, height, channels, rows


def thumb_length(screenshot, clip, thumb_rgb):
    """Count the thumb-coloured rows in a scrollbar strip screenshot.

    The clip is a 14px-wide strip of the page, so the thumb is sampled down
    the middle of it, not at the page coordinate.
    """
    _, _, channels, rows = png_rows(screenshot)
    offset = (clip["width"] // 2) * channels
    count = 0
    for y in range(min(clip["height"], len(rows))):
        if tuple(rows[y][offset:offset + 3]) == thumb_rgb:
            count += 1
    return count


def assert_grabbable(page, selector, label):
    """Owner #943: a visible, wide, draggable scrollbar with a clickable track."""
    width = page.locator(selector).evaluate("e => e.offsetWidth - e.clientWidth")
    assert width >= 12, f"{label}: scrollbar is {width}px wide, expected at least 12px"
    # Park the pointer away from the bar, or the thumb reads as hovered.
    page.mouse.move(4, 4)
    page.wait_for_timeout(150)
    thumb = page.locator(selector).evaluate(
        "e => getComputedStyle(e, '::-webkit-scrollbar-thumb').backgroundColor")
    minimum = page.locator(selector).evaluate(
        "e => getComputedStyle(e, '::-webkit-scrollbar-thumb').minHeight")
    assert minimum == "48px", f"{label}: thumb minimum is {minimum}, expected 48px"
    # Nothing above the bar may swallow a drag.
    blocked = page.locator(selector).evaluate("""e => {
        const chain = [];
        for (let node = e; node && node !== document.body; node = node.parentElement) {
            chain.push(getComputedStyle(node).pointerEvents);
        }
        return chain.filter(value => value === 'none').length;
    }""")
    assert blocked == 0, f"{label}: {blocked} ancestor(s) set pointer-events:none and would swallow the drag"
    geometry = scrollbar_geometry(page, selector)
    if HEADED and geometry["scrollHeight"] > geometry["clientHeight"] + 20:
        # A real browser: drag the thumb and confirm the view moved.
        page.mouse.move(geometry["x"], geometry["top"] + geometry["thumbHeight"] / 2)
        page.mouse.down()
        page.mouse.move(geometry["x"], geometry["top"] + geometry["thumbHeight"] / 2 + 140, steps=12)
        page.mouse.up()
        page.wait_for_timeout(200)
        after = page.locator(selector).evaluate("e => e.scrollTop")
        assert after > 0, f"{label}: dragging the thumb did not scroll"
    return width, thumb


def assert_thumb_length(page, label):
    """Owner #943: measure the RENDERED thumb, not the declared minimum.

    A global `scrollbar-width` in Chromium switches to the native scrollbar
    path, which ignores ::-webkit-scrollbar-thumb { min-height } and renders a
    sliver. This measures the pixels of a very long scroller.
    """
    page.evaluate("""() => {
        const probe = document.createElement('div');
        probe.id = 'sb-probe';
        probe.style.cssText = 'position:fixed;right:60px;top:120px;width:200px;height:200px;overflow:auto;z-index:99999;background:#11111b';
        probe.innerHTML = '<div style="height:20000px"></div>';
        document.body.appendChild(probe);
    }""")
    page.wait_for_timeout(250)
    box = page.locator("#sb-probe").bounding_box()
    clip = {"x": int(box["x"] + box["width"] - 14), "y": int(box["y"]), "width": 14, "height": 200}
    shot = ROOT / "data" / ("scrollbar-probe-" + label.strip("/").replace("/", "-") + ".png")
    page.screenshot(path=str(shot), clip=clip)
    length = thumb_length(shot, clip, (108, 112, 134))
    page.evaluate("() => document.getElementById('sb-probe').remove()")
    assert length >= 40, f"{label}: the rendered thumb is {length}px on long content, expected at least 40px"
    print(f"{label}: rendered thumb {length}px on 20,000px of content (screenshot {shot.name})")
    return length


with sync_playwright() as playwright:
    browser = playwright.chromium.launch(
        headless=not HEADED, executable_path=chromium_path(), args=["--no-sandbox"]
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

        # Owner #941/#943: the desk's own scroller keeps a classic visible scrollbar.
        desk_width, desk_thumb = assert_grabbable(page, ".conversation", "desk conversation")
        assert desk_thumb == "rgb(111, 121, 135)", f"the desk scrollbar thumb is {desk_thumb}, expected #6f7987"

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
    for name, marker, scroller in (("poolrad", ".dash-figures", ".dash-body"),
                                   ("operations", ".dash-stats", ".dash-body"),
                                   ("play", ".game-view", ".game-view"),
                                   ("vp", ".dash-conversation", ".dash-body")):
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
        # Owner #941/#943: the scrollbar must be a classic, always-visible one.
        width, thumb = assert_grabbable(page, scroller, f"/dash/{name}")
        assert thumb == "rgb(108, 112, 134)", f"/dash/{name} scrollbar thumb is {thumb}, expected #6c7086"
        if HEADED and name == "operations":
            assert_thumb_length(page, f"/dash/{name}")
        page.screenshot(path=str(ROOT / "data" / f"dash-{name}.png"))
        print(f"/dash/{name}: standalone view renders without desk chrome; scrollbar {width}px, thumb {thumb}")

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
