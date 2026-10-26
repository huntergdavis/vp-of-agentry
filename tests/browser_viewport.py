"""Run against an isolated served build; only authentication and viewport POSTs allowed."""
from pathlib import Path
from datetime import datetime
from urllib.parse import urlsplit
import json,os,subprocess,time
from playwright.sync_api import sync_playwright
BASE=os.environ['VP_BASE_URL'].rstrip('/')
OUT=Path(os.environ['VP_TEST_ARTIFACTS']);OUT.mkdir(parents=True,exist_ok=True)
password=dict(line.split(': ',1) for line in Path(os.environ['VP_TEST_CREDENTIALS_PATH']).read_text().strip().splitlines())['Password']
stamp=subprocess.check_output(['date','-Iseconds'],text=True).strip()
chrome=sorted((Path.home()/'.cache/ms-playwright').glob('chromium-*/chrome-linux64/chrome'))[-1]
evidence=[]
with sync_playwright() as pw:
    browser=pw.chromium.launch(executable_path=str(chrome),args=['--no-sandbox'])
    try:
        for width,height in ((1440,900),(1422,900),(1067,900),(960,900),(800,900),(720,900),(480,844),(390,844),(320,844)):
            context=browser.new_context(viewport=dict(width=width,height=height),device_scale_factor=1.8,screen=dict(width=1920,height=1080))
            page=context.new_page();errors=[];forbidden=[];samples=[]
            page.on('pageerror',lambda e:errors.append(str(e)))
            page.clock.install(time=datetime.fromisoformat(stamp))
            def route(r):
                path=urlsplit(r.request.url).path
                if r.request.method!='GET' and path not in ('/api/login','/api/viewport'):
                    forbidden.append(path);r.abort();return
                if path=='/api/viewport':samples.append(r.request.post_data_json)
                if path=='/api/messages':
                    r.fulfill(json={'items':[]});return
                r.continue_()
            page.route('**/api/**',route)
            page.goto(BASE+'/dash/cos')
            page.locator('#password').fill(password)
            received_after=time.time()
            with page.expect_response(lambda r:urlsplit(r.url).path=='/api/viewport') as sent:
                page.get_by_role('button',name='Open desk').click()
            response=sent.value
            assert response.status==200,response.status
            expected=page.evaluate("() => ({innerWidth,innerHeight,devicePixelRatio,screenWidth:screen.width,screenHeight:screen.height})")
            assert expected['innerWidth']==width and expected['innerHeight']==height
            assert expected['screenWidth']==1920 and expected['screenHeight']==1080
            assert abs(expected['devicePixelRatio']-1.8)<1e-6  # Browser reports the actual floating-point value.
            assert samples==[expected],samples
            status=page.request.get(BASE+'/api/channels')
            assert status.status==200
            stored=status.json()['viewports']
            assert len(stored)==1
            assert {k:v for k,v in stored[0].items() if k!='viewport_at'}==expected
            assert received_after<=stored[0]['viewport_at']<=time.time()
            sample_time=stored[0]['viewport_at']
            counts={s:page.locator(s).count() for s in ('[role="dialog"]',':modal','.modal-backdrop','dialog[open]')}
            assert not any(counts.values()),counts
            page.get_by_label('Message text',exact=True).wait_for()
            page.screenshot(path=str(OUT/f'viewport-{width}.png'))
            record=dict(timestamp=stamp,viewport=expected,requestedDeviceScaleFactor=1.8,httpStatus=response.status,
                        recordedInStatus=True,viewport_at=sample_time,dialog_closed=True,dialogCounts=counts)
            with page.expect_response(lambda r:urlsplit(r.url).path=='/api/viewport') as resized:
                page.set_viewport_size(dict(width=321,height=height))
                page.clock.run_for(11000)
            assert resized.value.status==200
            latest=dict(expected,innerWidth=321)
            assert samples==[expected,latest],samples
            viewports=page.request.get(BASE+'/api/channels').json()['viewports']
            assert len(viewports)==1
            assert {k:v for k,v in viewports[0].items() if k!='viewport_at'}==latest
            assert viewports[0]['viewport_at']>sample_time
            record['resizeViewportAt']=viewports[0]['viewport_at']
            record['resizeReplacedLatest']=latest
            assert not errors,errors
            assert not forbidden,forbidden
            evidence.append(record);print(json.dumps(record),flush=True)
            page.request.post(BASE+'/api/logout')  # Explicit test cleanup, outside the page route.
            context.close()
    finally:
        browser.close()
        (OUT/'results.json').write_text(json.dumps(evidence,indent=2)+'\n')
