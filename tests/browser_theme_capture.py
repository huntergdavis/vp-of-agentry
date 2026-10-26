"""Serial Chromium theme evidence against a separately built temporary server.

VP_BASE_URL=http://127.0.0.1:PORT .venv/bin/python tests/browser_theme_capture.py
Uses synthetic APIs only. Run through poolrad-heavy.sh. Every screenshot goes
through ThemeCapture; the deliberately open Appearance negative control must
refuse capture. Fixture shape and guard design reuse codex-design i25587.
"""
import json
import os
from pathlib import Path
import re
import subprocess
import sys
from datetime import datetime
from urllib.parse import urlparse

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from tools.theme_capture import CaptureBlocked, ThemeCapture
from tools.theme_contrast import DEFAULT_CSS, measure, theme_tokens
from playwright.sync_api import expect, sync_playwright

BASE = os.environ['VP_BASE_URL'].rstrip('/')
OUTPUT = Path(os.environ.get('VP_TEST_ARTIFACTS', ROOT / 'data/theme-gate'))
STAMP = subprocess.check_output(['date', '-u', '+%Y-%m-%dT%H:%M:%SZ'], text=True).strip()
CSS = Path(os.environ.get('VP_THEME_CSS', DEFAULT_CSS))
THEMES = set(theme_tokens(CSS.read_text()))
RATIOS = measure(CSS.read_text())
assert all(row['status'] != 'FAIL' for row in RATIOS), RATIOS


def source(**values):
    return dict(state='ok', source='Synthetic theme fixture', generated_at=STAMP, **values)


BOARD = dict(generated_at=STAMP, no_model=True,
    brief=dict(tasks=source(open=2, owner=1), lanes=source(working=1, idle=1)),
    attention=dict(alarms=[], owner=source(items=[dict(id='t-fixture', title='Review theme evidence')])),
    budget=dict(generated_at=STAMP, providers=[], dollars_reason='Synthetic fixture; no account data.'),
    reference=dict(tasks=source(items=[dict(id='t-fixture', title='Review theme evidence', status='open', assignees=['owner'], age_s=120)]),
        lanes=source(items=[dict(pane_id='fixture', tab_label='Theme lane', agent_status='working')]),
        schedules=source(items=[dict(id='d-fixture', name='Review', target_label='Theme', running=True)])))
PROGRESS = dict(strict_full_c=0, ceiling=815, strict_percent=0, identities=0, identity_percent=0,
    bound_kind='upper_bound', evidence_line='Synthetic fixture, not game credit.', source='Theme fixture', status='example',
    commit='fixture', observed_at=STAMP, generated=STAMP, accounting_source='Synthetic values only.',
    replacements=dict(count=0, state='example', source='Fixture', commit='fixture', observed_at=STAMP))
CHANNELS = [dict(id=name, name=name.upper(), pane_id='fixture', status='idle', can_message=False) for name in ('cos', 'vp')]
MESSAGES = [dict(id=1, role='agent', body='Synthetic theme review. Compare readable text and the page background.', created_at=STAMP, attachments=[])]


def main():
    chrome = Path(os.environ['CHROMIUM_PATH']) if os.environ.get('CHROMIUM_PATH') else sorted((Path.home() / '.cache/ms-playwright').glob('chromium-*/chrome-linux64/chrome'))[-1]
    recorder = ThemeCapture(OUTPUT, {'source_head': os.environ.get('VP_TEST_SOURCE_SHA'), 'token_source': str(CSS),
                                     'observed_at': STAMP, 'contrast_pairs': RATIOS, 'fixture_source': 'codex-design i25587'})
    with sync_playwright() as p:
        browser = p.chromium.launch(executable_path=str(chrome), args=['--no-sandbox'])
        recorder.evidence['metadata']['browser'] = browser.version
        try:
            for width, height in ((1440, 900), (390, 844)):
                for view in ('cos', 'operations'):
                    context = browser.new_context(viewport={'width': width, 'height': height}, reduced_motion='reduce')
                    page = context.new_page(); errors, writes, unexpected = [], [], []
                    page.on('pageerror', lambda error: errors.append(str(error)))
                    def api(route):
                        path = urlparse(route.request.url).path
                        if route.request.method != 'GET':
                            writes.append(path); route.abort(); return
                        data = {'/api/channels': {'channels': CHANNELS}, '/api/messages': {'items': MESSAGES},
                                '/api/ops-board': BOARD, '/api/poolrad-dashboard/progress': PROGRESS}
                        if path == '/api/version': route.abort(); return
                        if path not in data: unexpected.append(path); route.fulfill(status=404, json={}); return
                        route.fulfill(json=data[path])
                    page.route('**/api/**', api)
                    page.route(re.compile(r'https://.*'), lambda route: route.abort())
                    page.clock.set_fixed_time(datetime.fromisoformat(STAMP.replace('Z', '+00:00')))
                    page.goto(BASE + '/dash/' + view, wait_until='networkidle')
                    if view == 'cos': page.locator('.message-wrap').first.wait_for()
                    else: page.locator('[data-ops-section=reference]').wait_for()
                    trigger = page.get_by_role('button', name='Appearance', exact=True)
                    trigger.click()
                    select = page.get_by_label('Theme', exact=True)
                    options = set(select.locator('option').evaluate_all('(items)=>items.map(item=>item.value)'))
                    assert options == THEMES, (options, THEMES)
                    blocked_name = f'negative-appearance-{view}-{width}.png'
                    try:
                        recorder.capture(page, blocked_name, expected_rejection=True, width=width, view=view)
                    except CaptureBlocked:
                        assert not (OUTPUT / blocked_name).exists()
                    else: raise AssertionError('Capture allowed while Appearance was left open')
                    for theme in sorted(THEMES):
                        select.select_option(theme)
                        page.keyboard.press('Escape')
                        expect(page.get_by_role('dialog')).to_have_count(0)
                        expect(page.locator('html')).to_have_attribute('data-theme', theme)
                        page.evaluate('document.fonts.ready')
                        assert page.evaluate('document.documentElement.scrollWidth<=innerWidth')
                        recorder.capture(page, f'{theme}-{view}-{width}.png', theme=theme, view=view, width=width, height=height)
                        trigger.click()
                    page.keyboard.press('Escape')
                    assert not errors and not writes and not unexpected, (errors, writes, unexpected)
                    context.close()
                    print(f'{view} {width}x{height}: open Appearance refused; {len(THEMES)} dialog-closed captures; no API writes/JS errors', flush=True)
        finally:
            browser.close()
            recorder.write()
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
