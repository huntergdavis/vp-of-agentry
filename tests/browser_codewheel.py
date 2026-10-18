"""Private DOS-reference regression with mocked APIs: never types into the game.

Usage: .venv/bin/python tests/browser_codewheel.py /path/to/web-dist [reference.png]
Needs optional Playwright + Chromium, ffmpeg, and private data/codewheel GIFs.
The reference is the owner's 800x600 Xvfb image, not a distributable fixture.
"""

from functools import partial
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer
import os
from pathlib import Path
import re
import subprocess
import sys
import threading
from urllib.parse import urlsplit

from playwright.sync_api import sync_playwright, expect

ROOT = Path(__file__).resolve().parents[1]


class QuietHandler(SimpleHTTPRequestHandler):
    def log_message(self, *args): pass


def main():
    dist = Path(sys.argv[1]).resolve()
    reference = Path(sys.argv[2]) if len(sys.argv) > 2 else ROOT.parent / 'poolrad-macmaps/scratch/dos-code-prompt.png'
    if not reference.is_file():
        raise SystemExit('Supply the private 800x600 DOS reference PNG as the second argument.')
    # Exactly the same crop/scale as the desk video; keep pixels only in memory.
    frame = subprocess.run(['ffmpeg', '-hide_banner', '-loglevel', 'error', '-i', str(reference),
                            '-vf', 'crop=640:400:80:100,scale=1280:800:flags=neighbor',
                            '-frames:v', '1', '-f', 'image2pipe', '-c:v', 'png', 'pipe:1'],
                           capture_output=True, check=True, timeout=30).stdout
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
                page.set_default_timeout(30000)
                errors, typed, unexpected_posts = [], [], []
                page.on('pageerror', lambda error: errors.append(str(error)))

                def api(route):
                    path = urlsplit(route.request.url).path
                    if route.request.method == 'POST':
                        if path == '/api/game/type': typed.append(route.request.post_data_json)
                        else: unexpected_posts.append(path)
                        route.fulfill(json={'ok': True}); return
                    if path == '/api/game/video':
                        route.fulfill(body=frame, content_type='image/png'); return
                    if path.startswith('/api/game/codewheel/'):
                        name = path.rsplit('/', 1)[-1]
                        assert re.fullmatch(r'(?:esp|det)(?:0[1-9]|[12][0-9]|3[0-6])\.gif', name)
                        route.fulfill(body=(ROOT / 'data/codewheel' / name).read_bytes(), content_type='image/gif'); return
                    if path == '/api/channels':
                        payload = {'checked_at': '2026-10-18T01:00:00Z', 'channels': [
                            {'id': 'vp', 'name': 'VP', 'kind': 'active', 'online': True, 'status': 'idle',
                             'activity_group': 'standby', 'can_message': True},
                        ]}
                    elif path == '/api/game/status': payload = {'running': True, 'audio': False, 'run_name': 'synthetic-test'}
                    elif path == '/api/activity': payload = {'text': 'Synthetic output', 'status': 'idle'}
                    elif path == '/api/version': payload = {'version': version}
                    else: payload = {'items': [], 'has_more': False, 'next_before': None}
                    route.fulfill(json=payload)

                page.route('**/api/**', api)
                page.goto(f'http://127.0.0.1:{server.server_port}', wait_until='networkidle')
                page.get_by_role('button', name='Play Poolrad', exact=False).click()
                expect(page.locator('.game-stage img')).to_have_count(1)
                expect(page.get_by_role('button', name='Type code word', exact=True)).to_be_disabled()
                page.get_by_role('button', name='Auto code word', exact=True).click()
                expect(page.locator('.wheel-result')).to_contain_text('No typing: A complete pair', timeout=45000)
                expect(page.locator('.wheel-result')).to_contain_text('Visible path: dashes')
                assert typed == [], 'the private Decimer reference must ABSTAIN'
                expect(page.locator('.rune-choice')).to_have_count(72)
                expect(page.get_by_role('combobox', name='Wheel path')).to_have_value('')
                page.get_by_role('button', name='Espruar rune 21', exact=True).click()
                page.get_by_role('button', name='Dethek rune 14', exact=True).click()
                expect(page.get_by_role('button', name='Type code word', exact=True)).to_be_disabled()
                page.get_by_role('combobox', name='Wheel path').select_option('2')
                expect(page.get_by_label('Computed code word')).to_have_text('WYVERN')
                assert typed == [], 'picker selections alone must not send input'
                page.get_by_role('button', name='Type code word', exact=True).click()
                expect(page.locator('.wheel-result')).to_have_text('Typed WYVERN + Enter.')
                assert typed == [{'text': 'WYVERN', 'submit': True}], typed
                expect(page.locator('.game-stage img')).to_have_count(1)  # /type returns {ok}, not game status.
                page.get_by_role('spinbutton', name='Espruar rune number').fill('37')
                expect(page.get_by_role('button', name='Type code word', exact=True)).to_be_disabled()
                page.get_by_role('textbox', name='Text to type into the game').fill('ZOMBIE')
                page.get_by_role('button', name='Send only', exact=True).click()
                page.wait_for_timeout(300)
                assert typed[-1] == {'text': 'ZOMBIE', 'submit': False}
                assert not unexpected_posts, unexpected_posts
                assert page.evaluate('document.documentElement.scrollWidth <= innerWidth'), 'horizontal page overflow'
                assert not errors, errors
                print(f'{width}x{height}: private reference ABSTAINS; 72-rune picker, explicit path and manual typing pass', flush=True)
                page.close()
            browser.close()
    finally:
        server.shutdown(); server.server_close()


if __name__ == '__main__': main()
