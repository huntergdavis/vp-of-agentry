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
stamp = '2026-10-25T23:58:58-07:00'  # Full-width two-digit hour; fixed across the matrix.
spec = importlib.util.spec_from_file_location('roster', ROOT / 'server/roster.py')
roster = importlib.util.module_from_spec(spec)
spec.loader.exec_module(roster)
# Enumerate the actual channel formatter, including its missing-pane branch.
STATES = sorted({roster.presence(raw) for raw in ('working', 'idle', 'blocked', None)}
                | {roster.build_roster([dict(id='cos', name='Chief of Agent Staff',
                                            kind='active', match='fixture')], [])[0]['status']})
chrome = sorted((Path.home()/'.cache/ms-playwright').glob('chromium-*/chrome-linux64/chrome'))[-1]
CASES = [dict(name=str(w), width=w, dpr=1) for w in map(int, os.environ.get('VP_TEST_WIDTHS', '1440,1361,1360,1281,1280,1151,1150,1100,1099,1024,960,900,720,701,700,480,390,320').split(','))]
if 'VP_TEST_WIDTHS' not in os.environ:
    CASES += [dict(name=name, width=w, dpr=1.8) for name,w in [('owner-1920',1067),('owner-2560',1422),('owner-1440',800)]]
    CASES += [dict(name='text-200', width=320, dpr=1, textScale=2)]
if os.environ.get('VP_TEST_CASES'):
    CASES = [c for c in CASES if c['name'] in os.environ['VP_TEST_CASES'].split(',')]
results, failures = [], []
def row(i, body):
    return dict(id=i, role='agent', body=body, created_at=stamp, delivery='posted', attachments=[])

with sync_playwright() as pw:
    browser = pw.chromium.launch(executable_path=str(chrome), args=['--no-sandbox'])
    try:
        for theme in ('default', 'crt'):
            for case in CASES:
                width, height = case['width'], 844 if case['width'] <= 700 else 900
                page = browser.new_page(viewport=dict(width=width, height=height), locale='en-US', timezone_id='America/Los_Angeles', device_scale_factor=case['dpr'])
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
                page.evaluate('document.fonts.ready')
                if case.get('textScale'):
                    # Double computed font sizes without changing CSS viewport dimensions.
                    page.evaluate('''() => {
                        const fonts=[...document.querySelectorAll('body, body *')].map(e=>[e,parseFloat(getComputedStyle(e).fontSize)]);
                        fonts.forEach(([e,size])=>e.style.fontSize=(size*2)+'px');
                    }''')
                expected_time = page.evaluate("s => 'updated ' + new Date(s).toLocaleTimeString()", stamp)
                assert page.get_by_text(expected_time, exact=True).count() == 1
                assert widths[status[0]] == max(widths.values())
                metrics = page.evaluate("""() => {
                    const rect = s => { const e=document.querySelector(s),r=e.getBoundingClientRect();
                        return {x:r.x,y:r.y,width:r.width,height:r.height,right:r.right,bottom:r.bottom,clientWidth:e.clientWidth,scrollWidth:e.scrollWidth,overflowX:getComputedStyle(e).overflowX,flexWrap:getComputedStyle(e).flexWrap}; };
                    const nav=rect('.dash-nav'), body=rect('.conversation'), links=rect('.dash-nav > .dash-nav-links');
                    const fixed=[...document.querySelectorAll('.dash-nav-brand, .dash-nav-status > .dash-meta, .dash-nav-right > button')].map(e=>{
                        const r=e.getBoundingClientRect();return {text:e.textContent,x:r.x,right:r.right,y:r.y,bottom:r.bottom,width:r.width};
                    });
                    const root=document.querySelector('.dash-nav');
                    const visible=e=>e.getClientRects().length && getComputedStyle(e).visibility!=='hidden';
                    const descendants=[...root.querySelectorAll('*')].filter(visible);
                    const controls=[...root.querySelectorAll(':scope > .dash-nav-brand, :scope > .dash-nav-links > a, .dash-nav-boards > summary, .dash-nav-status > .dash-meta, .dash-nav-right > button')].filter(visible);
                    // Controls share a row only while their vertical intervals overlap.
                    // Compare offsetTop/offsetHeight, with no hard-coded pixel tolerance;
                    // this also catches wrapping inside the links or right-hand group.
                    const rows=[];
                    for (const e of controls.sort((a,b)=>a.offsetTop-b.offsetTop)) {
                        const top=e.offsetTop, bottom=top+e.offsetHeight, row=rows.at(-1);
                        if (!row || top>=row.bottom) rows.push({top,bottom});
                        else row.bottom=Math.min(row.bottom,bottom);
                    }
                    const overflow=[root,...descendants].filter(e=>Math.ceil(e.scrollWidth)>Math.ceil(e.clientWidth)).map(e=>({tag:e.tagName,cls:e.className,sw:e.scrollWidth,cw:e.clientWidth}));
                    const outside=descendants.filter(e=>{const r=e.getBoundingClientRect();return r.left<nav.x || r.right>nav.right;}).map(e=>({tag:e.tagName,cls:e.className,text:e.textContent}));
                    const status=root.querySelector('.dash-nav-status');
                    const statusHeight=status?.getBoundingClientRect().height || 0;
                    const badgeHeight=status?.firstElementChild?.getBoundingClientRect().height || 0;
                    const targets=[...root.querySelectorAll('a,button,summary'),...document.querySelectorAll('.composer .send')].filter(visible).map(e=>{const r=e.getBoundingClientRect();return {name:e.getAttribute('aria-label')||e.textContent.trim(),width:r.width,height:r.height};});
                    const rgb=c=>c.match(/[0-9.]+/g).slice(0,3).map(Number).map(v=>{v/=255;return v<=.04045?v/12.92:((v+.055)/1.055)**2.4;});
                    const lum=c=>rgb(c).reduce((sum,v,i)=>sum+v*[.2126,.7152,.0722][i],0);
                    const contrast=[...root.querySelectorAll('a,button,summary,.dash-meta,.dash-nav-mark')].filter(visible).map(e=>{
                        let p=e,bg=getComputedStyle(p).backgroundColor;
                        while(bg==='rgba(0, 0, 0, 0)' && p.parentElement){p=p.parentElement;bg=getComputedStyle(p).backgroundColor;}
                        const fg=getComputedStyle(e).color,a=lum(fg),b=lum(bg);
                        return {name:e.getAttribute('aria-label')||e.textContent.trim(),foreground:fg,background:bg,ratio:(Math.max(a,b)+.05)/(Math.min(a,b)+.05)};
                    });
                    return {nav,links,fixed,rows,overflow,outside,statusHeight,badgeHeight,targets,contrast,
                        innerWidth,devicePixelRatio,screenWidth:screen.width,screenHeight:screen.height,
                        statusCount:root.querySelectorAll('.dash-nav-status').length,
                        statusHasContent:!!status?.textContent.trim(),
                        controlOffsets:controls.map(e=>e.offsetTop),
                        navHeight:getComputedStyle(root).height, linksOverflowX:getComputedStyle(document.querySelector('.dash-nav > .dash-nav-links')).overflowX,
                        above:body.y,below:innerHeight-body.bottom,
                        pageOverflow:document.documentElement.scrollWidth>innerWidth,
                        oneLine:getComputedStyle(document.querySelector('.dash-nav')).flexWrap==='nowrap' &&
                            fixed.every(r=>r.y>=nav.y && r.bottom<=nav.bottom),
                        fixedVisible:fixed.every(r=>r.x>=0 && r.right<=innerWidth),
                        titleBands:document.querySelectorAll('.dash-header').length};
                }""")
                dialog_counts = {s: page.locator(s).count() for s in
                                 ('[role="dialog"]', ':modal', '.modal-backdrop', 'dialog[open]')}
                assert not any(dialog_counts.values()), dialog_counts
                record = dict(case=case['name'], textScale=case.get('textScale',1), theme=theme, width=width, height=height, timestamp=stamp,
                              statusWidths=widths, widestState=status[0], fullTimestamp=expected_time,
                              dialogCounts=dialog_counts, dialog_closed=True, **metrics)
                results.append(record)
                page.screenshot(path=str(OUT/f"{theme}-{case['name']}.png"))
                if width in (1440,390) and case.get('textScale',1)==1 and case['dpr']==1:
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
                    # Count the visible controls' rows, including status and timestamp.
                    expected_rows = 2 if width < 700 else 1
                    checks = dict(navInkContrast=all(c['ratio']>=7 for c in metrics['contrast']),
                                  targetSize=all(t['width']>=24 and t['height']>=24 for t in metrics['targets']),
                                  statusPresent=metrics['statusCount']==1 and metrics['statusHasContent'],
                                  statusRowCompact=width>=700 or case.get('textScale',1)>1 or metrics['statusHeight']==metrics['badgeHeight'],
                                  rowCount=case.get('textScale',1)>1 or len(metrics['rows'])==expected_rows,
                                  noPageOverflow=not metrics['pageOverflow'],
                                  noNavOverflow=not metrics['overflow'],
                                  controlsInside=not metrics['outside'],
                                  fixedVisible=metrics['fixedVisible'], titleBandRemoved=metrics['titleBands']==0)
                    record['checks'] = checks
                    failures.extend(f'{theme}/{width}: {name}' for name, passed in checks.items() if not passed)
                    assert page.locator('.dash-nav-brand').get_attribute('href') == '/'
                    assert page.get_by_role('link', name='Open the desk ↗').count() == 0
                    if width <= 1100:
                        boards = page.locator('.dash-nav-boards')
                        boards.locator('summary').click()
                        menu = boards.locator('a')
                        assert menu.count() == 5
                        assert menu.evaluate_all('es=>es.every(e=>e.tabIndex>=0)')
                        assert boards.locator('.dash-nav-links, .dash-nav-links *').evaluate_all('es=>es.every(e=>Math.ceil(e.scrollWidth)<=Math.ceil(e.clientWidth))')
                        for index in range(5):
                            page.keyboard.press('Tab')
                            assert menu.nth(index).evaluate('e=>e===document.activeElement')
                        record['menuTargets'] = menu.evaluate_all("es=>es.map(e=>({width:e.getBoundingClientRect().width,height:e.getBoundingClientRect().height}))")
                        assert all(t['width']>=24 and t['height']>=24 for t in record['menuTargets'])
                        assert menu.evaluate_all("es=>es.every(e=>e.getClientRects().length && e.getBoundingClientRect().right<=innerWidth)")
                        assert menu.evaluate_all("es=>es.map(e=>e.getAttribute('href'))") == ['/dash/cos','/dash/vp','/dash/fleet','/dash/operations','/dash/play']
                        page.screenshot(path=str(OUT/f"{theme}-{case['name']}-boards.png"))
                        page.keyboard.press('Escape')
                        assert not boards.evaluate('e=>e.open')
                        assert boards.locator('summary').evaluate('e=>e===document.activeElement')
                        record['boardsMenuPassed'] = True
                    else:
                        assert page.locator('.dash-nav > .dash-nav-links > a:visible').count()==5
                        assert not page.locator('.dash-nav-boards').is_visible()
                if MODE == 'candidate':
                    page.keyboard.press('Tab')
                    page.locator('.dash-nav-brand').focus()
                    record['brandFocus'] = page.locator('.dash-nav-brand').evaluate('''e=>{
                        const s=getComputedStyle(e), bg=getComputedStyle(e.closest('nav')).backgroundColor;
                        const rgb=c=>c.match(/[0-9.]+/g).slice(0,3).map(Number).map(v=>{v/=255;return v<=.04045?v/12.92:((v+.055)/1.055)**2.4;});
                        const lum=c=>rgb(c).reduce((sum,v,i)=>sum+v*[.2126,.7152,.0722][i],0);
                        const a=lum(s.outlineColor),b=lum(bg);
                        return {outline:s.outlineStyle,width:parseFloat(s.outlineWidth),color:s.outlineColor,background:bg,contrast:(Math.max(a,b)+.05)/(Math.min(a,b)+.05)};
                    }''')
                    assert record['brandFocus']['width']>0 and record['brandFocus']['outline']!='none'
                    assert record['brandFocus']['contrast']>=3
                    if width in (480,320):
                        focus=[]
                        for step in range(30):
                            state=page.evaluate('''()=>{const e=document.activeElement,r=e.getBoundingClientRect(),hit=document.elementFromPoint(r.x+r.width/2,r.y+r.height/2);return {tag:e.tagName,name:e.getAttribute('aria-label')||e.textContent.trim().slice(0,40),inside:r.x>=0&&r.y>=0&&r.right<=innerWidth&&r.bottom<=innerHeight,unobscured:!!hit&&(e===hit||e.contains(hit)),brand:e.matches('.dash-nav-brand')};}''')
                            if state['tag']!='BODY':
                                focus.append(state)
                                if not state['inside'] or not state['unobscured']:
                                    failures.append(f"{theme}/{case['name']}: focused control obscured {state}")
                            page.keyboard.press('Tab')
                            if page.locator('.dash-nav-brand').evaluate('e=>e===document.activeElement'): break
                        record['keyboardFocus'] = focus
                assert not errors, errors
                assert not writes, writes
                print(json.dumps(record), flush=True)
                page.close()
    finally:
        browser.close()
        (OUT/'results.json').write_text(json.dumps(dict(mode=MODE, results=results, failures=failures), indent=2)+'\n')
assert not failures, failures
