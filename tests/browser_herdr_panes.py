"""Exercise a built UI with synthetic APIs; never read owner credentials.

Usage: .venv/bin/python tests/browser_herdr_panes.py /path/to/web-dist
Requires the same optional Playwright installation as browser_smoke.py.
"""

from functools import partial
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer
import os
from pathlib import Path
import re
import sys
import threading
from urllib.parse import urlsplit

from playwright.sync_api import sync_playwright, expect


class QuietHandler(SimpleHTTPRequestHandler):
    def log_message(self, *args):
        pass


def main():
    dist = Path(sys.argv[1]).resolve()
    version = re.search(r'<script[^>]+src="([^"]+)"', (dist / 'index.html').read_text())[1]
    server = ThreadingHTTPServer(('127.0.0.1', 0), partial(QuietHandler, directory=str(dist)))
    threading.Thread(target=server.serve_forever, daemon=True).start()
    cached = sorted((Path.home() / '.cache/ms-playwright').glob('chromium-*/chrome-linux64/chrome'))
    executable = os.getenv('PLAYWRIGHT_CHROMIUM_EXECUTABLE') or (str(cached[-1]) if cached else None)
    try:
        with sync_playwright() as playwright:
            browser = playwright.chromium.launch(headless=True, executable_path=executable, args=['--no-sandbox'])
            for width, height in ((1440, 900), (390, 844)):
                page = browser.new_page(viewport={'width': width, 'height': height})
                errors, methods = [], []
                phase = {'calls': 0, 'failed': False, 'empty': False}
                page.on('pageerror', lambda error: errors.append(str(error)))

                def api(route):
                    path = urlsplit(route.request.url).path
                    methods.append(route.request.method)
                    if path == '/api/panes/activity':
                        phase['calls'] += 1
                        if phase['failed']:
                            route.fulfill(status=503, json={'detail': 'Herdr panes unavailable'})
                            return
                        payload = {'checked_at': '2026-10-17T23:00:00Z', 'panes': [] if phase['empty'] else [
                            {'pane_id': 'w1:p1', 'name': 'Code lane', 'workspace': 'Project', 'agent': 'codex',
                             'status': 'working', 'error': None,
                             'text': '\n'.join(f'Output {i}' for i in range(39)) + f'\nRefresh {phase["calls"]} <img src=x onerror=alert(1)>'},
                            {'pane_id': 'w1:p2', 'name': 'Terminal', 'workspace': 'Project', 'agent': None,
                             'status': 'unknown', 'error': 'Pane output unavailable', 'text': ''},
                        ]}
                    elif path == '/api/channels':
                        payload = {'checked_at': '2026-10-17T23:00:00Z', 'channels': [
                            {'id': 'vp', 'name': 'VP', 'kind': 'active', 'online': True, 'status': 'idle',
                             'activity_group': 'standby', 'can_message': True},
                        ]}
                    elif path == '/api/activity':
                        payload = {'text': 'Synthetic output', 'status': 'idle'}
                    elif path == '/api/version':
                        payload = {'version': version}
                    else:
                        payload = {'items': [], 'has_more': False, 'next_before': None}
                    route.fulfill(json=payload)

                page.route('**/api/**', api)
                page.goto(f'http://127.0.0.1:{server.server_port}', wait_until='networkidle')
                page.get_by_role('button', name='Herdr panes').click()
                expect(page.locator('.herdr-card')).to_have_count(2)
                expect(page.locator('.herdr-card pre').first).to_contain_text('Refresh 1')
                assert page.locator('.herdr-card img').count() == 0, 'output must be escaped text'
                assert page.locator('.herdr-pane-error').inner_text() == 'Pane output unavailable · retrying'
                page.get_by_role('button', name='Focus pane').first.click()
                expect(page.locator('.herdr-card:visible')).to_have_count(1)
                page.keyboard.press('Escape')
                expect(page.locator('.herdr-card:visible')).to_have_count(2)
                assert page.evaluate('document.documentElement.scrollWidth <= innerWidth'), 'horizontal page overflow'
                columns = page.locator('.herdr-grid').evaluate('e => getComputedStyle(e).gridTemplateColumns.split(" ").filter(track => parseFloat(track) > 0).length')
                assert columns == (2 if width == 1440 else 1), columns
                if width == 1440:
                    output = page.locator('.herdr-card pre').first
                    output.evaluate('e => { e.scrollTop = 0; e.dispatchEvent(new Event("scroll")); }')
                    expect(output).to_contain_text('Refresh 2', timeout=6500)
                    assert output.evaluate('e => e.scrollTop') == 0, 'refresh overrode reader scroll'
                    phase['failed'] = True
                    expect(page.get_by_role('alert')).to_contain_text('may be stale', timeout=6500)
                    expect(output).to_contain_text('Refresh 2')
                    phase['failed'] = False
                    expect(page.locator('.herdr-error')).to_have_count(0, timeout=6500)
                    # A hidden browser tab stops polling; visibility resumes it.
                    page.evaluate('Object.defineProperty(document, "hidden", { configurable: true, value: true }); document.dispatchEvent(new Event("visibilitychange"));')
                    calls = phase['calls']
                    page.wait_for_timeout(4300)
                    assert phase['calls'] == calls
                    page.evaluate('Object.defineProperty(document, "hidden", { configurable: true, value: false }); document.dispatchEvent(new Event("visibilitychange"));')
                    expect(output).to_contain_text(f'Refresh {calls + 1}', timeout=2000)
                    phase['empty'] = True
                    expect(page.get_by_text('No live panes.', exact=True)).to_be_visible(timeout=6500)
                page.locator('.sidebar button.channel').filter(has_text='VP').click()
                calls = phase['calls']
                page.wait_for_timeout(4300)
                assert phase['calls'] == calls, 'closed view still polls'
                assert set(methods) == {'GET'}, methods
                assert not errors, errors
                print(f'{width}x{height}: grid, focus, escaped output, read-only requests and polling passed')
                page.close()
            browser.close()
    finally:
        server.shutdown()
        server.server_close()


if __name__ == '__main__':
    main()
