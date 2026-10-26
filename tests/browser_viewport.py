"""Run against an isolated served build; only authentication and viewport POSTs allowed."""
from pathlib import Path
from datetime import datetime
from urllib.parse import urlsplit
import json,os,subprocess
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
        for width,height in ((1440,900),(390,844)):
            context=browser.new_context(viewport=dict(width=width,height=height),device_scale_factor=1)
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
            with page.expect_response(lambda r:urlsplit(r.url).path=='/api/viewport') as sent:
                page.get_by_role('button',name='Open desk').click()
            response=sent.value
            assert response.status==200,response.status
            expected=dict(innerWidth=width,innerHeight=height,devicePixelRatio=1)
            assert samples==[expected],samples
            status=page.request.get(BASE+'/api/channels')
            assert status.status==200
            assert expected in status.json()['viewports']
            counts={s:page.locator(s).count() for s in ('[role="dialog"]',':modal','.modal-backdrop','dialog[open]')}
            assert not any(counts.values()),counts
            page.get_by_label('Message text',exact=True).wait_for()
            page.screenshot(path=str(OUT/f'viewport-{width}.png'))
            record=dict(timestamp=stamp,viewport=expected,httpStatus=response.status,
                        recordedInStatus=True,dialog_closed=True,dialogCounts=counts)
            with page.expect_response(lambda r:urlsplit(r.url).path=='/api/viewport') as resized:
                page.set_viewport_size(dict(width=320,height=height))
                page.clock.run_for(11000)
            assert resized.value.status==200
            latest=dict(expected,innerWidth=320)
            assert samples==[expected,latest],samples
            viewports=page.request.get(BASE+'/api/channels').json()['viewports']
            assert latest in viewports and expected not in viewports
            record['resizeReplacedLatest']=latest
            assert not errors,errors
            assert not forbidden,forbidden
            evidence.append(record);print(json.dumps(record),flush=True)
            page.request.post(BASE+'/api/logout')  # Explicit test cleanup, outside the page route.
            context.close()
    finally:
        browser.close()
        (OUT/'results.json').write_text(json.dumps(evidence,indent=2)+'\n')
