"""Send-row unit: layout, reachable controls and one synthetic button send; hint footer stays."""
from pathlib import Path
import os, json, subprocess
from playwright.sync_api import sync_playwright, expect
BASE=os.environ['VP_BASE_URL']
OUT=Path(os.environ['VP_TEST_ARTIFACTS']);OUT.mkdir(parents=True,exist_ok=True)
MODE=os.environ.get('VP_TEST_MODE','candidate')
stamp=subprocess.check_output(['date','-Iseconds'],text=True).strip()
chrome=sorted((Path.home()/'.cache/ms-playwright').glob('chromium-*/chrome-linux64/chrome'))[-1]
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
            for width,height,text_scale in [(w,900 if w>480 else 844,1) for w in (1440,1422,1067,960,800,720,480,390,320)]+[(320,844,2)]:
                page=browser.new_page(viewport=dict(width=width,height=height),device_scale_factor=1.8,screen=dict(width=1920,height=1080))
                page.add_init_script(f"localStorage.setItem('vp-theme',{json.dumps(theme)})")
                errors=[];writes=[];sent=[];available=[True]
                page.on('pageerror',lambda e:errors.append(str(e)))
                def route(r):
                    if r.request.method=='POST' and r.request.url.endswith('/api/viewport'):
                        sample=r.request.post_data_json
                        assert set(sample)=={'width','height','dpr','screen_width','screen_height'},sample
                        r.fulfill(status=204)
                        return
                    if r.request.method=='POST' and r.request.url.endswith('/api/pane-send'):
                        sent.append(r.request.post_data_json)
                        r.fulfill(json=dict(id=1001,role='owner',body=sent[-1]['text'],created_at=stamp,delivery='ok',outcome='ok',attachments=[]))
                        return
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
                if text_scale==2:
                    # Computed sizes are snapshotted before applying any changes, avoiding inherited double scaling.
                    page.evaluate("""() => {
                        const sizes=[...document.querySelectorAll('body *')].map(e=>[e,parseFloat(getComputedStyle(e).fontSize)]);
                        sizes.forEach(([e,size])=>e.style.fontSize=(size*2)+'px');
                    }""")
                suffix=f'{theme}-{width}-text{text_scale}'
                metrics=page.evaluate("""() => {
                    const rect=e=>{const r=e.getBoundingClientRect();return {x:r.x,y:r.y,right:r.right,bottom:r.bottom,width:r.width,height:r.height,clientWidth:e.clientWidth,scrollWidth:e.scrollWidth};};
                    const composer=document.querySelector('.composer'), editor=document.querySelector('.editor'), send=composer.querySelector('.send');
                    const box=rect(composer),input=rect(editor),button=rect(send),conversation=rect(document.querySelector('.conversation'));
                    const controls=[...composer.querySelectorAll('button')].map(e=>{
                        const range=document.createRange();range.selectNodeContents(e);
                        return {text:e.textContent,...rect(e),textLines:new Set([...range.getClientRects()].map(r=>Math.round(r.y))).size};
                    });
                    const toolbar=[...composer.querySelectorAll('.toolbar button')].map(rect);
                    const descendants=[...composer.querySelectorAll('*')].filter(e=>e.getClientRects().length);
                    const overflow=descendants.filter(e=>e.scrollWidth>e.clientWidth).map(e=>({tag:e.tagName,classes:e.className,client:e.clientWidth,scroll:e.scrollWidth}));
                    const targets=controls.every(r=>r.width>=24&&r.height>=24);
                    const rgb=value=>value.match(/[0-9.]+/g).map(Number);
                    const blend=(f,b)=>f.slice(0,3).map((v,i)=>v*(f[3]??1)+b[i]*(1-(f[3]??1)));
                    const surface=e=>e ? blend(rgb(getComputedStyle(e).backgroundColor),surface(e.parentElement)) : [255,255,255];
                    const luminance=c=>c.map(v=>{v/=255;return v<=.04045?v/12.92:((v+.055)/1.055)**2.4;}).reduce((v,c,i)=>v+c*[.2126,.7152,.0722][i],0);
                    const contrast=(a,b)=>{const x=luminance(a),y=luminance(b);return (Math.max(x,y)+.05)/(Math.min(x,y)+.05);};
                    const colorTargets=[...composer.querySelectorAll('button,.editor,.composer-footer')];
                    const textContrasts=colorTargets.map(e=>{const bg=surface(e);
                        return {label:e.getAttribute('title')||e.className,ratio:contrast(blend(rgb(getComputedStyle(e).color),bg),bg)};});
                    const editorBoundary=contrast(rgb(getComputedStyle(editor).borderTopColor),surface(composer));

                    return {composer:box,editor:input,send:button,controls,overflow,targets,textContrasts,editorBoundary,above:conversation.y,below:innerHeight-conversation.bottom,
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
                record=dict(theme=theme,width=width,height=height,timestamp=stamp,textScale=text_scale,deviceScaleFactor=1.8,emulated=True,**metrics)
                results.append(record)
                record.update(capture(page,OUT/f'{suffix}-empty.png'))
                if MODE=='candidate':
                    checks=dict(flexRow=metrics['composerDisplay']=='flex',
                                hintFooterRetained=metrics['footerCount']==1,
                                sendBeside=metrics['sendBeside'],sendFullHeight=metrics['sendFullHeight'],
                                sendNarrower=metrics['sendNarrower'],controlsFit=metrics['controlsFit'],
                                controlsSingleLine=metrics['controlsSingleLine'],targets24=metrics['targets'],noDescendantOverflow=not metrics['overflow'],
                                textContrast=all(c['ratio']>=4.5 for c in metrics['textContrasts']),editorBoundaryContrast=metrics['editorBoundary']>=3,
                                noPageOverflow=not metrics['pageOverflow'])
                    record['checks']=checks
                    failures.extend(f'{theme}/{width}/text{text_scale}: {k}' for k,v in checks.items() if not v)
                    if width==320 and text_scale==2:
                        reach=[]
                        for control in page.locator('.composer button:not([disabled]), .composer [contenteditable="true"]').all():
                            before=control.bounding_box()
                            control.evaluate("e=>e.scrollIntoView({block:'center',inline:'nearest',behavior:'instant'})")
                            after=control.evaluate("""e=>{
                                const r=e.getBoundingClientRect();
                                const points=[[r.x+r.width/2,r.y+r.height/2],[r.x+1,r.y+r.height/2],
                                    [r.right-1,r.y+r.height/2],[r.x+r.width/2,r.y+1],[r.x+r.width/2,r.bottom-1]];
                                const uncovered=points.every(([x,y])=>{const hit=document.elementFromPoint(x,y);return hit===e||e.contains(hit);});
                                const ancestors=[];for(let p=e.parentElement;p;p=p.parentElement){
                                    const c=getComputedStyle(p);if(p.scrollHeight>p.clientHeight||c.overflowY!=='visible')
                                        ancestors.push({tag:p.tagName,classes:p.className,height:p.clientHeight,scrollHeight:p.scrollHeight,
                                            scrollTop:p.scrollTop,overflowY:c.overflowY,position:c.position});
                                }
                                return {label:e.getAttribute('title')||e.getAttribute('aria-label')||e.textContent,
                                    x:r.x,y:r.y,right:r.right,bottom:r.bottom,
                                    insideViewport:r.x>=0&&r.y>=0&&r.right<=innerWidth&&r.bottom<=innerHeight,
                                    uncovered,ancestors};
                            }""")
                            reach.append(dict(before=before,after=after))
                            if not (after['insideViewport'] and after['uncovered']):
                                failures.append(f'{theme}/{width}/text{text_scale}: unreachable composer control '+after['label'])
                        record['scrollIntoViewReachability']=reach
                    if width in (480,320):
                        controls=page.locator('.composer button:not([disabled]), .composer [contenteditable="true"]')
                        controls.first.focus();walk=[]
                        for _ in range(controls.count()):
                            item=page.evaluate("""() => {
                                const e=document.activeElement,r=e.getBoundingClientRect();
                                const hit=document.elementFromPoint(r.x+r.width/2,r.y+r.height/2);
                                return {label:e.getAttribute('title')||e.getAttribute('aria-label')||e.textContent,
                                    inside:!!e.closest('.composer'),x:r.x,y:r.y,right:r.right,bottom:r.bottom,
                                    visible:r.x>=0&&r.y>=0&&r.right<=innerWidth&&r.bottom<=innerHeight,
                                    unobscured:hit===e||e.contains(hit)};
                            }""")
                            walk.append(item)
                            if not (item['inside'] and item['visible'] and item['unobscured']):
                                failures.append(f'{theme}/{width}/text{text_scale}: keyboard focus '+str(item))
                            page.keyboard.press('Tab')
                        record['tabWalk']=walk
                    footer=page.locator('.composer-footer')
                    expect(footer).to_contain_text('Enter to send')
                    editor.fill('Unit 3 synthetic send')
                    page.get_by_role('button',name='Send message',exact=True).click()
                    expect(editor).to_have_text('')
                    assert len(sent)==1 and sent[0]['text']=='Unit 3 synthetic send',sent
                    assert sent[0]['pane']=='fixture' and sent[0]['channel']=='cos'
                    record['syntheticSendButtonPassed']=True
                    available[0]=False;page.clock.install();page.clock.run_for(6000)
                    expect(page.get_by_role('button',name='Send message',exact=True)).to_be_disabled()
                    expect(footer).to_contain_text('Agent unavailable')
                    capture(page,OUT/f'{suffix}-unavailable.png')
                    editor.fill('Unavailable draft');editor.press('Enter')
                    assert editor.inner_text().strip()=='Unavailable draft'
                    assert len(sent)==1
                    record['unavailableFooterAndSendBlocked']=True
                assert not errors,errors
                assert not writes,writes
                print(json.dumps(record),flush=True)
                page.close()
    finally:
        browser.close()
        (OUT/'results.json').write_text(json.dumps(dict(mode=MODE,results=results,failures=failures),indent=2)+'\n')
assert not failures,failures
