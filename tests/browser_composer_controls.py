"""Composer-only geometry, keyboard, paint and synthetic-send evidence.
Run against own temporary baseline/candidate servers via poolrad-heavy.sh.
Reuses ThemeCapture and the existing placeholder noise-control paint check.
"""
import argparse
import hashlib
import json
from pathlib import Path
import re
import subprocess
import sys
from urllib.parse import urlparse
from urllib.request import urlopen

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from playwright.sync_api import sync_playwright, expect
from tools.theme_capture import ThemeCapture
from tests.browser_placeholder_paint import measure_placeholder_paint

METRICS = """() => {
 const box=e=>{const r=e.getBoundingClientRect();return {x:r.x,y:r.y,width:r.width,height:r.height,right:r.right,bottom:r.bottom};};
 const c=document.querySelector('.composer'),t=c.querySelector('.formatting-controls, .toolbar'),e=c.querySelector('.editor'),s=c.querySelector('.send'),a=c.querySelector('.attach')||[...t.querySelectorAll('button')].find(b=>b.title.startsWith('Attach'));
 const css=getComputedStyle(c),hint=c.querySelector('.composer-placeholder');
 const luminance=color=>color.match(/[0-9.]+/g).slice(0,3).map(Number).map(v=>v/255).map(v=>v<=.04045?v/12.92:((v+.055)/1.055)**2.4).reduce((n,v,i)=>n+v*[.2126,.7152,.0722][i],0);
 const acss=getComputedStyle(a),ink=luminance(acss.color),surface=luminance(css.backgroundColor);
 const boundary=luminance(acss.borderColor),ownSurface=luminance(acss.backgroundColor);
 const formatButtons=[...t.querySelectorAll('button')].map(box);

 return {composer:box(c),toolbar:box(t),editor:box(e),send:box(s),attach:box(a),hint:hint?box(hint):null,
  attachTextContrast:(Math.max(ink,surface)+.05)/(Math.min(ink,surface)+.05),
  attachBoundary:{color:acss.borderColor,surface:acss.backgroundColor,width:parseFloat(acss.borderWidth),style:acss.borderStyle,
   ratio:(Math.max(boundary,ownSurface)+.05)/(Math.min(boundary,ownSurface)+.05)},
  formattingButtons:formatButtons,
  toolbarOpacity:Number(getComputedStyle(t).opacity),focusWithin:c.matches(':focus-within'),
  padding:{top:parseFloat(css.paddingTop),bottom:parseFloat(css.paddingBottom),left:parseFloat(css.paddingLeft),right:parseFloat(css.paddingRight)},
  controls:[...c.querySelectorAll('button')].map(b=>({name:b.getAttribute('aria-label')||b.title||b.textContent,union:box(b),fragments:[...b.getClientRects()].map(r=>({width:r.width,height:r.height}))})),
  documentOverflow:document.documentElement.scrollWidth>innerWidth,hoverNone:matchMedia('(hover:none)').matches};
}"""


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--base-url', required=True)
    parser.add_argument('--mode', choices=['baseline', 'candidate'], required=True)
    parser.add_argument('--output', type=Path, required=True)
    parser.add_argument('--baseline-results', type=Path)
    args = parser.parse_args()
    assert urlparse(args.base_url).hostname == '127.0.0.1', 'owned loopback server required'
    out = args.output; out.mkdir(parents=True, exist_ok=True)
    stamp = subprocess.check_output(['date', '-Iseconds'], text=True).strip()
    with urlopen(args.base_url+'/dash/cos') as response:
        version = re.search(r'src="([^"]+\.js)"', response.read().decode())[1]
    baseline = {}
    if args.baseline_results:
        baseline = {r['id']: r for r in json.loads(args.baseline_results.read_text())['cases']}
    recorder = ThemeCapture(out, dict(timestamp=stamp, mode=args.mode, fixture='synthetic APIs', dpr=1.8))
    report = dict(timestamp=stamp, mode=args.mode, cases=[], failures=[])
    chrome = sorted((Path.home()/'.cache/ms-playwright').glob('chromium-*/chrome-linux64/chrome'))[-1]
    with sync_playwright() as pw:
        browser = pw.chromium.launch(executable_path=str(chrome), args=['--no-sandbox'])
        try:
            for width in [1067, 390]:
                for theme, scale in [(t,s) for t in ['default','crt'] for s in [1,2]]:
                    name = f'{theme}-{width}-text{scale}'
                    row = dict(id=name, width=width, theme=theme, textScale=scale, states={}, checks=[], captures=[])
                    report['cases'].append(row)
                    context = browser.new_context(viewport=dict(width=width, height=844 if width==390 else 900),
                        device_scale_factor=1.8, has_touch=width==390, is_mobile=width==390)
                    page = context.new_page(); available = [True]; sent=[]; errors=[]; unexpected=[]
                    page.add_init_script(f"localStorage.setItem('vp-theme',{json.dumps(theme)})")
                    page.on('pageerror', lambda error: errors.append(str(error)))
                    def api(route):
                        path = urlparse(route.request.url).path
                        if route.request.method == 'POST' and path == '/api/viewport':
                            route.fulfill(status=204); return
                        if route.request.method == 'POST' and path == '/api/pane-send':
                            sent.append(route.request.post_data_json)
                            route.fulfill(json=dict(id='fixture-send', role='owner', body=sent[-1]['text'],
                                created_at=stamp, outcome='fixture delivered', attachments=[])); return
                        if route.request.method != 'GET':
                            unexpected.append(path); route.abort(); return
                        data = {
                            '/api/channels': {'channels':[dict(id='cos', name='Chief of Agent Staff',
                                status='idle', can_message=available[0], pane_id='fixture')]},
                            '/api/messages': {'items':[dict(id=1, role='agent', body='Synthetic composer review.',
                                created_at=stamp, attachments=[])]},
                            '/api/version': {'version':version},
                        }
                        route.fulfill(json=data.get(path, {}))
                    page.route('**/api/**', api)
                    page.route('https://**', lambda route: route.abort())
                    def check(ok, label):
                        row['checks'].append(dict(name=label, passed=bool(ok)))
                        if not ok: report['failures'].append(dict(case=name, assertion=label))
                    def state(label):
                        metrics=page.evaluate(METRICS); row['states'][label]=metrics
                        filename=f'{name}-{label}.png'
                        recorder.capture(page, filename, theme=theme, width=width, view='cos', state=label)
                        row['captures'].append(dict(file=filename, sha256=hashlib.sha256((out/filename).read_bytes()).hexdigest()))
                        check(not metrics['documentOverflow'], label+': no horizontal overflow')
                        check(abs(metrics['send']['height']-metrics['editor']['height'])<.5 and
                              abs(metrics['send']['y']-metrics['editor']['y'])<.5 and
                              metrics['send']['x']>=metrics['editor']['right'], label+': Send full-height beside input')
                        if args.mode=='candidate' and metrics['hint']:
                            h=metrics['hint'];e=metrics['editor']
                            check(h['x']>=e['x']-.5 and h['right']<=e['right']+.5 and h['y']>=e['y']-.5 and h['bottom']<=e['bottom']+.5,
                                  label+': entire hint contained within editor')
                        return metrics
                    def idle():
                        page.mouse.move(0,0); page.evaluate('document.activeElement?.blur()')
                    def paint(label):
                        editor=page.get_by_label('Message text', exact=True)
                        hint=page.locator('.composer-placeholder')
                        result=measure_placeholder_paint(page, editor, hint, out/f'{name}-{label}-paint')
                        row.setdefault('paint', {})[label]=result
                        check(result['passed'], label+': hint painted')
                    try:
                        page.goto(args.base_url+'/dash/cos')
                        editor=page.get_by_label('Message text', exact=True); editor.wait_for()
                        page.evaluate('document.fonts.ready')
                        if scale==2:
                            page.evaluate("""() => {
                                const sizes=[...document.querySelectorAll('body *')].map(e=>[e,parseFloat(getComputedStyle(e).fontSize)]);
                                sizes.forEach(([e,size])=>e.style.fontSize=(size*2)+'px');
                            }""")
                            page.add_style_tag(content='.composer-placeholder {font-size:20px !important}')
                        idle()
                        first=state('idle')
                        if args.mode=='baseline':
                            row['completed']=True
                            continue
                        check(first['toolbarOpacity']==1, 'Formatting always visible while idle')
                        boundary=first['attachBoundary']
                        check(boundary['style']=='solid' and boundary['width']>=1 and boundary['ratio']>=3,
                              'Attach has a real outline with >=3:1 against its own surface')
                        buttons=first['formattingButtons']
                        check(len(buttons)==6 and len({b['y'] for b in buttons})==2 and len({b['x'] for b in buttons})==3,
                              'Formatting occupies two rows of three buttons')
                        check(first['toolbar']['right']<=first['editor']['x'] and first['editor']['right']<=first['attach']['x']
                              and first['attach']['right']<=first['send']['x'],
                              'Visual order formatting then editor then Attach then Send')
                        check(all(c['union']['width']>=24 and c['union']['height']>=24 for c in first['controls']),
                              'Idle controls each measure at least 24x24')
                        check(first['attachTextContrast']>=4.5, 'Attach retains readable desk text contrast')
                        check(abs(first['padding']['bottom']-2)<.1, 'Bottom padding exactly 2px')
                        row['mainIdleHeight']=baseline[name]['states']['idle']['composer']['height']
                        row['idleHeightDelta']=first['composer']['height']-row['mainIdleHeight']
                        check(row['idleHeightDelta']<0, 'One-row composer reclaims height versus main307ec0ee')
                        paint('idle')
                        t=first['toolbar']; page.mouse.move(t['right']-2,t['y']+t['height']/2)
                        hovered=state('hovered')
                        check(hovered['toolbarOpacity']==1, 'Hover retains visible formatting')
                        idle()
                        page.evaluate("""() => {
                          window.formatFocus=[];
                          document.querySelector('.formatting-controls').addEventListener('focusin',e=>{
                            const s=getComputedStyle(e.target);
                            window.formatFocus.push({name:e.target.getAttribute('aria-label'),
                              opacity:getComputedStyle(e.currentTarget).opacity,
                              outline:s.outlineStyle,outlineWidth:parseFloat(s.outlineWidth)});
                          });
                        }""")
                        editor.focus(); walk=[]
                        for _ in range(8):
                            page.keyboard.press('Tab')
                            walk.append(page.evaluate("document.activeElement.getAttribute('aria-label')||document.activeElement.title"))
                            if len(walk)==3:
                                keyboard=state('keyboard-focused')
                                paint('keyboard-focused')
                        check(walk==['Send message','Attach images or files','Bold','Italic','Heading','Bullet list','Quote','Code block'],
                              'Tab order Send then Attach then six formatting buttons')
                        row['tabOrder']=walk;row['formatFocus']=page.evaluate('window.formatFocus')
                        check(len(row['formatFocus'])==6 and all(float(f['opacity'])==1 and f['outline'] not in ['none','hidden'] and f['outlineWidth']>0 for f in row['formatFocus']),
                              'Formatting visible with focus outline at focus event')
                        check(page.locator('.formatting-controls').get_attribute('role')=='group' and
                              page.locator('.formatting-controls').get_attribute('aria-label')=='Message formatting' and
                              page.locator('.formatting-controls button[aria-hidden="true"]').count()==0,
                              'Formatting accessible group retains focused controls')
                        row['accessibleComposer']=page.locator('.composer').aria_snapshot()
                        for label in ['hovered','keyboard-focused']:
                            m=row['states'][label]
                            check(all(abs(m[key][part]-first[key][part])<.1 for key in ['composer','editor','send']
                                      for part in ['x','y','width','height']), label+': zero interaction layout shift')
                            check(all(c['union']['width']>=24 and c['union']['height']>=24 and c['fragments'] and
                                      all(f['width']>=24 and f['height']>=24 for f in c['fragments']) for c in m['controls']),
                                  label+': every control union and fragment >=24')
                        check(keyboard['attach']['right']<=keyboard['send']['x'], 'Attach physically left of Send')
                        with page.expect_file_chooser() as chooser:
                            page.get_by_role('button',name='Attach images or files',exact=True).click()
                        chooser.value.set_files([]);row['attachChooserOpened']=True
                        editor.fill('Typed draft');idle();typed=state('typed')
                        check(typed['toolbarOpacity']==1, 'Typed draft retains visible formatting')
                        if width==390:
                            editor.fill('');idle();editor.tap()
                            touch=state('touch-focused')
                            check(touch['hoverNone'] and touch['focusWithin'] and touch['toolbarOpacity']==1,
                                  'No-hover phone reaches formatting by editor focus')
                        editor.fill('Composer send-button fixture')
                        page.get_by_role('button',name='Send message',exact=True).click()
                        expect(editor).to_have_text('')
                        editor.fill('Composer Enter fixture');editor.press('Enter');expect(editor).to_have_text('')
                        check(len(sent)==2 and [s['text'] for s in sent]==['Composer send-button fixture','Composer Enter fixture']
                              and all(s['pane']=='fixture' and s['channel']=='cos' for s in sent), 'Button and Enter retain pane-send behavior')
                        editor.fill('Line one');editor.press('Shift+Enter');editor.type('Line two')
                        check(len(sent)==2 and 'Line two' in editor.inner_text(), 'Shift+Enter retains newline without sending')
                        editor.fill('');idle()
                        available[0]=False;page.reload()
                        editor=page.get_by_label('Message text',exact=True);editor.wait_for()
                        expect(page.get_by_role('button',name='Send message',exact=True)).to_be_disabled()
                        page.evaluate('document.fonts.ready')
                        if scale==2:
                            page.evaluate("""() => {
                                const sizes=[...document.querySelectorAll('body *')].map(e=>[e,parseFloat(getComputedStyle(e).fontSize)]);
                                sizes.forEach(([e,size])=>e.style.fontSize=(size*2)+'px');
                            }""")
                            page.add_style_tag(content='.composer-placeholder {font-size:20px !important}')
                        idle();state('unavailable');paint('unavailable')
                        check(page.locator('.composer-placeholder').get_attribute('data-hint')=='Agent unavailable', 'Unavailable idle hint text retained')
                        editor.fill('Unavailable draft');editor.press('Enter')
                        check(len(sent)==2 and editor.inner_text()=='Unavailable draft', 'Unavailable Enter cannot send')
                        check(not errors,'No JavaScript errors');check(not unexpected,'No unexpected writes')
                        row['completed']=True
                    except Exception as error:
                        report['failures'].append(dict(case=name, assertion=str(error)))
                    finally:
                        context.close()
                        (out/'results.json').write_text(json.dumps(report,indent=2)+'\n')
        finally: browser.close()
    print(json.dumps(dict(cases=len(report['cases']),failures=report['failures']),indent=2))
    return int(bool(report['failures']))


if __name__=='__main__':
    raise SystemExit(main())
