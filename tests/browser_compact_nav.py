"""Synthetic layout/scroll checks; both themes, widest roster status, no API writes."""
from datetime import datetime
from pathlib import Path
from urllib.parse import urlsplit, parse_qs
import importlib.util
import json
import os
import subprocess

from playwright.sync_api import sync_playwright

ROOT = Path(__file__).resolve().parents[1]
BASE = os.environ['VP_BASE_URL']
OUT = Path(os.environ['VP_TEST_ARTIFACTS'])
MODE = os.environ.get('VP_TEST_MODE', 'candidate')
OUT.mkdir(parents=True, exist_ok=True)
stamp = subprocess.check_output(['date', '-Iseconds'], text=True).strip()
spec = importlib.util.spec_from_file_location('roster', ROOT / 'server/roster.py')
roster = importlib.util.module_from_spec(spec)
spec.loader.exec_module(roster)
# Enumerate the actual channel formatter, including its missing-pane branch.
STATES = sorted({roster.presence(raw) for raw in ('working', 'idle', 'blocked', None)}
                | {roster.build_roster([dict(id='cos', name='Chief of Agent Staff',
                                            kind='active', match='fixture')], [])[0]['status']})
chrome = sorted((Path.home()/'.cache/ms-playwright').glob('chromium-*/chrome-linux64/chrome'))[-1]
results, failures = [], []
def row(i, body):
    return dict(id=i, role='agent', body=body, created_at=stamp, delivery='posted', attachments=[])

with sync_playwright() as pw:
    browser = pw.chromium.launch(executable_path=str(chrome), args=['--no-sandbox'])
    try:
        for theme in ('default', 'crt'):
            for width, height in ((1440, 900), (1280, 900), (1024, 900), (390, 844)):
                page = browser.new_page(viewport=dict(width=width, height=height), locale='en-US')
                errors, writes = [], []
                page.on('pageerror', lambda e: errors.append(str(e)))
                page.add_init_script(f"localStorage.setItem('vp-theme', {json.dumps(theme)})")
                page.clock.set_fixed_time(datetime.fromisoformat(stamp))
                status = ['unknown']
                messages = [row(i, f'Fixture {i}. ' + 'Readable message text. '*12) for i in range(1, 41)]
                def route(r):
                    if r.request.method != 'GET':
                        writes.append(r.request.url)
                        r.abort()
                        return
                    path = urlsplit(r.request.url).path
                    data = {
                        '/api/channels': {'channels': [
                            dict(id=c, name=n, status=status[0], can_message=True, pane_id='fixture')
                            for c, n in [('cos', 'Chief of Agent Staff'), ('vp', 'VP of Agentry')]]},
                        '/api/messages': {'items': messages},
                        '/api/game/status': {'running': False, 'states': []},
                        '/api/game/states': {'states': []},
                    }.get(path, {})
                    r.fulfill(json=data)
                page.route('**/api/**', route)
                page.route('https://**', lambda r: r.abort())
                page.goto(BASE+'/dash/cos')
                page.get_by_text('Fixture 40.', exact=False).wait_for()
                page.evaluate('document.fonts.ready')
                widths = page.locator('.dash-meta').first.evaluate("""(e, states) => {
                    const clone = e.cloneNode(false);
                    Object.assign(clone.style, {position:'fixed',left:'-10000px',visibility:'hidden',whiteSpace:'nowrap'});
                    e.parentNode.appendChild(clone);
                    const result = Object.fromEntries(states.map(s => {
                        clone.textContent = 'Chief of Agent Staff · ' + s;
                        return [s, clone.getBoundingClientRect().width];
                    }));
                    clone.remove(); return result;
                }""", STATES)
                status[0] = max(widths, key=widths.get)
                page.reload()
                page.get_by_text('Chief of Agent Staff · '+status[0], exact=True).wait_for()
                page.get_by_text('Fixture 40.', exact=False).wait_for()
                expected_time = page.evaluate("s => 'updated ' + new Date(s).toLocaleTimeString()", stamp)
                assert page.get_by_text(expected_time, exact=True).count() == 1
                assert widths[status[0]] == max(widths.values())
                metrics = page.evaluate("""() => {
                    const rect = s => { const e=document.querySelector(s),r=e.getBoundingClientRect();
                        return {x:r.x,y:r.y,width:r.width,height:r.height,right:r.right,bottom:r.bottom,clientWidth:e.clientWidth,scrollWidth:e.scrollWidth,overflowX:getComputedStyle(e).overflowX,flexWrap:getComputedStyle(e).flexWrap}; };
                    const nav=rect('.dash-nav'), body=rect('.conversation'), links=rect('.dash-nav > .dash-nav-links');
                    const fixed=[...document.querySelectorAll('.dash-nav-brand, .dash-nav-right > .dash-meta, .dash-nav-right > button')].map(e=>{
                        const r=e.getBoundingClientRect();return {text:e.textContent,x:r.x,right:r.right,y:r.y,bottom:r.bottom,width:r.width};
                    });
                    return {nav,links,fixed,above:body.y,below:innerHeight-body.bottom,
                        pageOverflow:document.documentElement.scrollWidth>innerWidth,
                        oneLine:getComputedStyle(document.querySelector('.dash-nav')).flexWrap==='nowrap' &&
                            fixed.every(r=>r.y>=nav.y && r.bottom<=nav.bottom),
                        fixedVisible:fixed.every(r=>r.x>=0 && r.right<=innerWidth),
                        titleBands:document.querySelectorAll('.dash-header').length};
                }""")
                dialog_counts = {s: page.locator(s).count() for s in
                                 ('[role="dialog"]', ':modal', '.modal-backdrop', 'dialog[open]')}
                assert not any(dialog_counts.values()), dialog_counts
                record = dict(theme=theme, width=width, height=height, timestamp=stamp,
                              statusWidths=widths, widestState=status[0], fullTimestamp=expected_time,
                              dialogCounts=dialog_counts, dialog_closed=True, **metrics)
                results.append(record)
                page.screenshot(path=str(OUT/f'{theme}-{width}.png'))
                # Incoming polling preserves reading position; jump re-enables following.
                pane = page.locator('.conversation')
                page.clock.install()
                pane.evaluate('e=>e.scrollTop=e.scrollHeight')
                page.wait_for_timeout(100)
                pane.evaluate('e=>e.scrollTop-=20')
                page.wait_for_timeout(100)
                before = pane.evaluate('e=>e.scrollTop')
                messages.append(row(41, 'Incoming fixture. '+'More content '*30))
                page.clock.run_for(6000)
                page.get_by_text('Incoming fixture.', exact=False).wait_for()
                assert abs(pane.evaluate('e=>e.scrollTop')-before)<2
                page.get_by_role('button', name='New messages · Jump to latest').click()
                assert pane.evaluate('e=>e.scrollHeight-e.clientHeight-e.scrollTop')<2
                messages.append(row(42, 'Following fixture. '+'More content '*30))
                page.clock.run_for(6000)
                page.get_by_text('Following fixture.', exact=False).wait_for()
                assert pane.evaluate('e=>e.scrollHeight-e.clientHeight-e.scrollTop')<2
                record['scrollPreservedAndJumpPassed'] = True
                if MODE == 'candidate':
                    checks = dict(oneLine=metrics['oneLine'], noPageOverflow=not metrics['pageOverflow'],
                                  fixedVisible=metrics['fixedVisible'], titleBandRemoved=metrics['titleBands']==0,
                                  linksUsable=metrics['links']['width']>=40)
                    record['checks'] = checks
                    failures.extend(f'{theme}/{width}: {name}' for name, passed in checks.items() if not passed)
                    assert page.locator('.dash-nav-brand').get_attribute('href') == '/'
                    assert page.get_by_role('link', name='Open the desk ↗').count() == 0
                    links = page.locator('.dash-nav > .dash-nav-links')
                    if metrics['links']['scrollWidth']>metrics['links']['clientWidth']:
                        links.evaluate('e=>e.scrollLeft=e.scrollWidth')
                        record['linksScrollLeft'] = links.evaluate('e=>e.scrollLeft')
                        if metrics['links']['width']>0:
                            assert record['linksScrollLeft']>0
                assert not errors, errors
                assert not writes, writes
                print(json.dumps(record), flush=True)
                page.close()
    finally:
        browser.close()
        (OUT/'results.json').write_text(json.dumps(dict(mode=MODE, results=results, failures=failures), indent=2)+'\n')
assert not failures, failures
