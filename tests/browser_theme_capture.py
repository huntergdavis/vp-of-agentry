"""Serial Chromium theme evidence against a separately built temporary server.

VP_BASE_URL=http://127.0.0.1:PORT .venv/bin/python tests/browser_theme_capture.py
Or use tools/check_theme_wave.py for the complete build/static/browser contract.
Uses synthetic APIs only. Run through poolrad-heavy.sh. Closed page screenshots
use ThemeCapture; open-dialog controls are separately labelled, and paint checks
use their existing no-dialog guard. The open Appearance negative control must
refuse a closed-page capture. Fixture shape and guard design reuse codex-design i25587.
"""
import argparse
import hashlib
import json
import os
from pathlib import Path
import re
import subprocess
import sys
from datetime import datetime
from urllib.parse import urlparse
from urllib.request import urlopen

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from tools.theme_capture import CaptureBlocked, ThemeCapture
from tools.theme_wave_checks import target_meets_minimum, visible_focus
from tools.theme_contrast import DEFAULT_CSS, theme_tokens, read_css
from playwright.sync_api import expect, sync_playwright
from tests.browser_placeholder_paint import measure_placeholder_paint

STAMP = subprocess.check_output(['date', '-Iseconds'], text=True).strip()


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
CHANNELS = [dict(id=name, name=name.upper(), pane_id='fixture', status='idle', can_message=True) for name in ('cos', 'vp')]
MESSAGES = [dict(id=1, role='agent', body='Synthetic theme review. Compare readable text and the page background.', created_at=STAMP, attachments=[])]


GEOMETRY = """e => {
 const rect=r=>({x:r.x,y:r.y,width:r.width,height:r.height,right:r.right,bottom:r.bottom});
 const r=e.getBoundingClientRect(),s=getComputedStyle(e),extent=parseFloat(s.outlineWidth)+Math.max(0,parseFloat(s.outlineOffset));
 let contained=r.x-extent>=0&&r.y-extent>=0&&r.right+extent<=innerWidth&&r.bottom+extent<=innerHeight;
 for(let p=e.parentElement;p;p=p.parentElement){const ps=getComputedStyle(p),pr=p.getBoundingClientRect();
  if(ps.overflowX!=='visible')contained&&=r.x-extent>=pr.x&&r.right+extent<=pr.right;
  if(ps.overflowY!=='visible')contained&&=r.y-extent>=pr.y&&r.bottom+extent<=pr.bottom;
 }
 const points=[[r.x+1,r.y+r.height/2],[r.right-1,r.y+r.height/2],[r.x+r.width/2,r.y+1],[r.x+r.width/2,r.bottom-1]];
 return {union:rect(r),fragments:[...e.getClientRects()].map(rect),focused:document.activeElement===e,focusVisible:e.matches(':focus-visible'),outlineStyle:s.outlineStyle,outlineWidth:parseFloat(s.outlineWidth),outlineOffset:parseFloat(s.outlineOffset),ringContained:contained,unobscured:points.every(([x,y])=>{const hit=document.elementFromPoint(x,y);return hit===e||e.contains(hit)})};
}"""
ICON = """e => {
 const rgb=s=>s.match(/[0-9.]+/g).map(Number),lum=c=>c.slice(0,3).map(v=>{v/=255;return v<=.04045?v/12.92:((v+.055)/1.055)**2.4}).reduce((n,v,i)=>n+v*[.2126,.7152,.0722][i],0);
 const s=getComputedStyle(e),fg=rgb(s.borderTopColor),bg=rgb(s.backgroundColor),a=lum(fg),b=lum(bg),opaque=(fg[3]??1)===1&&(bg[3]??1)===1;
 return {contrast_kind:'STATIC',border:s.borderTopColor,surface:s.backgroundColor,opaque,ratio:opaque?(Math.max(a,b)+.05)/(Math.min(a,b)+.05):null};
}"""


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--base-url', default=os.environ.get('VP_BASE_URL'))
    parser.add_argument('--output', type=Path, default=Path(os.environ.get('VP_TEST_ARTIFACTS', ROOT / 'data/theme-gate')))
    parser.add_argument('--source-sha', default=os.environ.get('VP_TEST_SOURCE_SHA'))
    parser.add_argument('--theme', action='append')
    parser.add_argument('--width', type=int, action='append')
    parser.add_argument('--version')
    args = parser.parse_args(argv)
    if not args.base_url or urlparse(args.base_url).hostname != '127.0.0.1': parser.error('A temporary loopback server is required')
    base = args.base_url.rstrip('/'); output = args.output; output.mkdir(parents=True, exist_ok=True)
    css = Path(os.environ.get('VP_THEME_CSS', DEFAULT_CSS)); available = set(theme_tokens(read_css(css)))
    themes = sorted(set(args.theme or available)); widths = args.width or [1422, 1067, 960, 800, 700, 390, 320]
    if not set(themes).issubset(available): parser.error('Requested theme not in token source')
    version = args.version
    if not version:
        with urlopen(base + '/dash/cos') as response: version = re.search(r'src="([^"]+\.js)"', response.read().decode())[1]
    chrome = Path(os.environ['CHROMIUM_PATH']) if os.environ.get('CHROMIUM_PATH') else sorted((Path.home() / '.cache/ms-playwright').glob('chromium-*/chrome-linux64/chrome'))[-1]
    metadata = dict(source_head=args.source_sha, token_source=str(css), timestamp=STAMP, contrast_kind='STATIC',
                    emulated=True, requested_device_scale_factor=1.8, fixture_source='codex-design i25587',
                    not_covered=['OVERLAY-INCLUSIVE endpoint/continuous-phase bounds (stage 2)', 'Real zoom, full accessibility, font conformance'])
    recorder = ThemeCapture(output, metadata); results = dict(metadata=metadata, cases=[])
    try:
        with sync_playwright() as pw:
            browser = pw.chromium.launch(executable_path=str(chrome), args=['--no-sandbox'])
            metadata['browser'] = browser.version
            try:
                for width in widths:
                    height = 900 if width > 480 else 844
                    for view in ('cos', 'operations'):
                        for theme in themes:
                            for scale in (1, 2):
                                name = f'{theme}-{view}-{width}-text{scale}'
                                row = dict(id=name, width=width, height=height, view=view, theme=theme, textScale=scale, checks=[], captures=[], completed=False)
                                results['cases'].append(row)
                                context = browser.new_context(viewport=dict(width=width, height=height), device_scale_factor=1.8)
                                page = context.new_page(); errors, writes, unexpected = [], [], []
                                page.on('pageerror', lambda error: errors.append(str(error)))
                                def check(condition, label): row['checks'].append(dict(name=label, passed=bool(condition), advisory=width == 320))
                                def capture(state):
                                    filename = name + '-' + state + '.png'
                                    recorder.capture(page, filename, theme=theme, width=width, view=view, textScale=scale, state=state)
                                    c = dict(recorder.evidence['captures'][-1]); c['sha256'] = hashlib.sha256((output / filename).read_bytes()).hexdigest(); row['captures'].append(c)
                                def api(route):
                                    path = urlparse(route.request.url).path
                                    if path == '/api/viewport' and route.request.method == 'POST': route.fulfill(status=204); return
                                    if route.request.method != 'GET': writes.append(path); route.abort(); return
                                    data = {'/api/channels': {'channels': CHANNELS}, '/api/messages': {'items': MESSAGES}, '/api/ops-board': BOARD,
                                            '/api/poolrad-dashboard/progress': PROGRESS, '/api/version': {'version': version}}
                                    if path not in data: unexpected.append(path); route.fulfill(status=404, json={}); return
                                    route.fulfill(json=data[path])
                                page.route('**/api/**', api); page.route(re.compile(r'https://.*'), lambda route: route.abort())
                                page.add_init_script('localStorage.setItem("vp-theme",' + json.dumps(theme) + ')')
                                page.clock.set_fixed_time(datetime.fromisoformat(STAMP))
                                try:
                                    page.goto(base + '/dash/' + view, wait_until='domcontentloaded')
                                    page.locator('.message-wrap' if view == 'cos' else '[data-ops-section=reference]').first.wait_for()
                                    trigger = page.get_by_role('button', name='Appearance', exact=True); trigger.click()
                                    select = page.get_by_label('Theme', exact=True)
                                    assert set(select.locator('option').evaluate_all('(items)=>items.map(x=>x.value)')) == available, 'Picker registry mismatch'
                                    for picked in ('crt', 'default', theme): select.select_option(picked); expect(page.locator('html')).to_have_attribute('data-theme', picked)
                                    page.evaluate('document.fonts.ready')
                                    if scale == 2:
                                        page.evaluate("""() => {const sizes=[...document.querySelectorAll('body *')].map(e=>[e,parseFloat(getComputedStyle(e).fontSize)]);sizes.forEach(([e,n])=>e.style.fontSize=(n*2)+'px');}""")
                                    row['viewport'] = page.evaluate('({width:innerWidth,height:innerHeight,dpr:devicePixelRatio})')
                                    assert row['viewport']['width'] == width, 'Wrong viewport'
                                    icon = page.get_by_role('button', name='Close appearance', exact=True)
                                    row['iconOpen'] = icon.evaluate(ICON); row['iconTarget'] = icon.evaluate(GEOMETRY)
                                    check(row['iconOpen']['opaque'] and row['iconOpen']['ratio'] >= 3, 'STATIC panel icon boundary >=3')
                                    check(target_meets_minimum(row['iconTarget']), 'Dialog icon target union and fragments >=24')
                                    # An intentional open-dialog image is separately labelled; the page guard MUST reject it.
                                    negative = name + '-rejected.png'
                                    try: recorder.capture(page, negative, expected_rejection=True)
                                    except CaptureBlocked: assert not (output / negative).exists(); row['openDialogRejected'] = True
                                    else: raise AssertionError('Page capture accepted open dialog')
                                    open_name = name + '-dialog-open.png'; page.screenshot(path=str(output / open_name), animations='disabled')
                                    row['openDialogCapture'] = dict(file=open_name, dialog_closed=False, sha256=hashlib.sha256((output / open_name).read_bytes()).hexdigest())
                                    page.keyboard.press('Escape'); expect(page.get_by_role('dialog')).to_have_count(0)
                                    assert trigger.evaluate('e=>e===document.activeElement'), 'Picker focus restore'
                                    row['closedIconCount'] = page.locator('.icon-button').count()
                                    row['appearanceFocus'] = trigger.evaluate(GEOMETRY)
                                    f = row['appearanceFocus']; check(visible_focus(f), 'Appearance keyboard focus visible/contained/unobscured')
                                    check(page.evaluate('document.documentElement.scrollWidth<=innerWidth'), 'No document horizontal overflow')
                                    row['targets'] = []
                                    for target in page.locator('button,a[href],summary,select,[role="textbox"]').all():
                                        if not target.is_visible(): continue
                                        geometry = target.evaluate(GEOMETRY)
                                        row['targets'].append(dict(label=target.get_attribute('aria-label') or target.inner_text(), geometry=geometry))
                                        check(target_meets_minimum(geometry), 'Target union and fragments >=24: ' + row['targets'][-1]['label'])
                                    capture('closed')
                                    if view == 'cos':
                                        editor = page.get_by_label('Message text', exact=True); placeholder = page.locator('.composer-placeholder'); row['paint'] = []
                                        hint_font_size = placeholder.evaluate('e=>getComputedStyle(e).fontSize')
                                        for state in ('empty', 'focused-empty', 'typed', 'cleared'):
                                            if state == 'focused-empty': editor.focus()
                                            if state == 'typed': editor.fill('Synthetic draft, never sent')
                                            if state == 'cleared': editor.press('Control+A'); editor.press('Backspace'); expect(editor).to_have_text('')
                                            expect(placeholder).to_have_count(0 if state == 'typed' else 1)
                                            if state != 'typed':
                                                placeholder.evaluate('(e,size)=>e.style.fontSize=size', hint_font_size)
                                                measured = measure_placeholder_paint(page, editor, placeholder, output / (name + '-' + state + '-paint'))
                                                # This is a glyph-visibility/noise check, not a phase-bound contrast result.
                                                paint = {k: measured[k] for k in ('passed', 'changedPixels', 'contrastPixels', 'controlChangedPixels', 'captures')}
                                                paint['captures'] = [dict(file=Path(f).name, sha256=hashlib.sha256(Path(f).read_bytes()).hexdigest()) for f in paint['captures']]
                                                paint['state'] = state; row['paint'].append(paint); check(paint['passed'], 'Composer paint ' + state)
                                            capture(state)
                                    else:
                                        link = page.get_by_role('link', name='Evidence and timestamps', exact=True)
                                        row['linkInitial'] = link.evaluate(GEOMETRY)
                                        check(target_meets_minimum(row['linkInitial']), 'Evidence link union AND each fragment >=24')
                                        page.get_by_role('button', name='Refresh', exact=True).focus(); page.keyboard.press('Tab')
                                        row['linkFocus'] = link.evaluate(GEOMETRY); f = row['linkFocus']
                                        check(visible_focus(f), 'Evidence keyboard focus visible/contained/unobscured')
                                        capture('keyboard-focus')
                                    assert not errors and not writes and not unexpected, (errors, writes, unexpected)
                                    row['completed'] = True
                                except Exception as error: row['error'] = type(error).__name__ + ': ' + str(error)
                                finally:
                                    row.update(jsErrors=errors, unexpectedWrites=writes, unexpectedApi=unexpected)
                                    context.close()
                                    (output / 'results.json').write_text(json.dumps(results, indent=2) + '\n')
                                print(name + ': ' + ('complete' if row['completed'] else row.get('error', 'incomplete')), flush=True)
            finally: browser.close()
    finally:
        recorder.write(); (output / 'results.json').write_text(json.dumps(results, indent=2) + '\n')
    return int(any(not r['completed'] or (r['width'] != 320 and any(not c['passed'] for c in r['checks'])) for r in results['cases']))


if __name__ == '__main__': raise SystemExit(main())
