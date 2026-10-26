"""Synthetic composer layout/placeholder checks; no messages leave the browser."""
from pathlib import Path
import os, json, subprocess
from playwright.sync_api import sync_playwright
BASE=os.environ['VP_BASE_URL']
OUT=Path(os.environ['VP_TEST_ARTIFACTS']);OUT.mkdir(parents=True,exist_ok=True)
MODE=os.environ.get('VP_TEST_MODE','candidate')
stamp=subprocess.check_output(['date','-Iseconds'],text=True).strip()
chrome=sorted((Path.home()/'.cache/ms-playwright').glob('chromium-*/chrome-linux64/chrome'))[-1]
HINT='Enter to send - Shift+Enter for a new line - files stay on this host'
results=[];failures=[]
def capture(page,path):
    counts={s:page.locator(s).count() for s in ('[role="dialog"]',':modal','.modal-backdrop','dialog[open]')}
    assert not any(counts.values()),counts
    page.screenshot(path=str(path))
    return dict(dialog_closed=True,dialogCounts=counts)
with sync_playwright() as pw:
    browser=pw.chromium.launch(executable_path=str(chrome),args=['--no-sandbox'])
    try:
        for theme in ('default','crt'):
            for width,height in ((1440,900),(390,844),(320,844)):
                page=browser.new_page(viewport=dict(width=width,height=height))
                page.add_init_script(f"localStorage.setItem('vp-theme',{json.dumps(theme)})")
                errors=[];writes=[];available=[True]
                page.on('pageerror',lambda e:errors.append(str(e)))
                def route(r):
                    if r.request.method!='GET':
                        writes.append(r.request.url);r.abort();return
                    path=r.request.url.split('/api/',1)[1].split('?',1)[0]
                    data={'channels':{'channels':[dict(id='cos',name='Chief of Agent Staff',status='idle',can_message=available[0],pane_id='fixture')]},
                          'messages':{'items':[dict(id=i,role='agent',body=f'Fixture {i}. '+'Readable message. '*10,created_at=stamp,attachments=[]) for i in range(1,30)]}}.get(path,{})
                    r.fulfill(json=data)
                page.route('**/api/**',route)
                page.route('https://**',lambda r:r.abort())
                page.goto(BASE+'/dash/cos')
                editor=page.get_by_label('Message text',exact=True)
                editor.wait_for();page.evaluate('document.fonts.ready')
                metrics=page.evaluate("""() => {
                    const rect=e=>{const r=e.getBoundingClientRect();return {x:r.x,y:r.y,right:r.right,bottom:r.bottom,width:r.width,height:r.height,clientWidth:e.clientWidth,scrollWidth:e.scrollWidth};};
                    const composer=document.querySelector('.composer'), editor=document.querySelector('.editor'), send=composer.querySelector('.send');
                    const box=rect(composer),input=rect(editor),button=rect(send),conversation=rect(document.querySelector('.conversation'));
                    const controls=[...composer.querySelectorAll('button')].map(e=>{
                        const range=document.createRange();range.selectNodeContents(e);
                        return {text:e.textContent,...rect(e),textLines:new Set([...range.getClientRects()].map(r=>Math.round(r.y))).size};
                    });
                    const toolbar=[...composer.querySelectorAll('.toolbar button')].map(rect);
                    return {composer:box,editor:input,send:button,controls,above:conversation.y,below:innerHeight-conversation.bottom,
                        pageOverflow:document.documentElement.scrollWidth>innerWidth,
                        footerCount:composer.querySelectorAll('.composer-footer').length,
                        composerDisplay:getComputedStyle(composer).display,
                        bottomPadding:getComputedStyle(composer).paddingBottom,
                        controlsFit:controls.every(r=>r.x>=box.x&&r.right<=box.right&&r.x>=0&&r.right<=innerWidth&&r.scrollWidth<=r.clientWidth),
                        controlsSingleLine:controls.every(r=>r.textLines<=1),
                        toolbarSingleRow:Math.max(...toolbar.map(r=>r.y))-Math.min(...toolbar.map(r=>r.y))<1,
                        sendBeside:button.x>=input.right&&Math.abs(button.y-input.y)<1,
                        sendFullHeight:Math.abs(button.height-input.height)<1,
                        sendNarrower:button.width<input.width};
                }""")
                record=dict(theme=theme,width=width,height=height,timestamp=stamp,**metrics)
                results.append(record)
                record.update(capture(page,OUT/f'{theme}-{width}-empty.png'))
                if MODE=='candidate':
                    checks=dict(flexRow=metrics['composerDisplay']=='flex',
                                noFooter=metrics['footerCount']==0,noBottomPadding=metrics['bottomPadding']=='0px',
                                sendBeside=metrics['sendBeside'],sendFullHeight=metrics['sendFullHeight'],
                                sendNarrower=metrics['sendNarrower'],controlsFit=metrics['controlsFit'],
                                controlsSingleLine=metrics['controlsSingleLine'],toolbarSingleRow=metrics['toolbarSingleRow'],
                                noPageOverflow=not metrics['pageOverflow'])
                    record['checks']=checks
                    failures.extend(f'{theme}/{width}: {k}' for k,v in checks.items() if not v)
                    placeholder=page.locator('.composer-placeholder')
                    def rendered_hint():
                        return placeholder.evaluate("e=>getComputedStyle(e,'::before').content")
                    assert rendered_hint()==json.dumps(HINT)
                    assert editor.get_attribute('placeholder') is None
                    editor.focus()
                    assert rendered_hint()==json.dumps(HINT)
                    hint_rect=placeholder.bounding_box();input_rect=editor.bounding_box()
                    assert hint_rect['y']>=input_rect['y'] and hint_rect['y']+hint_rect['height']<=input_rect['y']+input_rect['height']+1
                    editor.fill('Typed draft')
                    assert placeholder.count()==0
                    editor.fill('')
                    placeholder.wait_for()
                    assert rendered_hint()==json.dumps(HINT)
                    record['placeholderEmptyFocusedTypedCleared']=True
                    available[0]=False;page.reload();editor.wait_for()
                    page.get_by_role('button',name='Send message',exact=True).wait_for()
                    assert page.get_by_role('button',name='Send message',exact=True).is_disabled()
                    assert rendered_hint()==json.dumps('Agent unavailable')
                    editor.focus();assert rendered_hint()==json.dumps('Agent unavailable')
                    capture(page,OUT/f'{theme}-{width}-unavailable.png')
                    editor.fill('Unavailable draft');editor.press('Enter')
                    assert editor.inner_text().strip()=='Unavailable draft'
                    record['unavailableVisibleAndSendBlocked']=True
                assert not errors,errors
                assert not writes,writes
                print(json.dumps(record),flush=True)
                page.close()
    finally:
        browser.close()
        (OUT/'results.json').write_text(json.dumps(dict(mode=MODE,results=results,failures=failures),indent=2)+'\n')
assert not failures,failures
