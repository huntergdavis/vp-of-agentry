"""Real layout checks with synthetic messages; never sends to an agent."""
import os,subprocess
from pathlib import Path
from urllib.parse import urlsplit,parse_qs
from playwright.sync_api import sync_playwright
ROOT=Path(__file__).resolve().parents[1]
BASE=os.environ['VP_BASE_URL']
password=dict(line.split(': ',1) for line in Path(os.environ['VP_TEST_CREDENTIALS_PATH']).read_text().strip().splitlines())['Password']
chrome=sorted((Path.home()/'.cache/ms-playwright').glob('chromium-*/chrome-linux64/chrome'))[-1]
stamp=subprocess.check_output(['date','-u','+%Y-%m-%dT%H:%M:%SZ'],text=True).strip()
def row(identifier,body):
 return dict(id=identifier,role='agent',body=body,created_at=stamp,delivery='posted',attachments=[])
with sync_playwright() as p:
 browser=p.chromium.launch(executable_path=str(chrome),args=['--no-sandbox'])
 for width,height in ((1440,900),(390,844)):
  page=browser.new_page(viewport={'width':width,'height':height});errors=[]
  page.on('pageerror',lambda e:errors.append(str(e)))
  messages={name:[row(i,f'{name} fixture {i}. '+('Readable message text. '*12)) for i in range(1,41)] for name in ('cos','vp')}
  page.route('**/api/messages?*',lambda r:r.fulfill(json={'items':messages[parse_qs(urlsplit(r.request.url).query)['channel'][0]]}))
  page.route('**/api/game/status',lambda r:r.fulfill(json={'running':False,'states':[]}))
  page.route('**/api/game/states',lambda r:r.fulfill(json={'states':[]}))
  page.goto(BASE+'/dash/cos');page.locator('#password').fill(password);page.get_by_role('button',name='Open desk').click()
  page.locator('.conversation').get_by_text('cos fixture 40.',exact=False).wait_for()
  page.clock.install()
  for route,selector,channel in (('cos','.conversation','cos'),('play','.game-chat-log','vp')):
   if route=='play':
    page.goto(BASE+'/dash/play')
    page.locator(selector).get_by_text('vp fixture 40.',exact=False).wait_for()
   pane=page.locator(selector)
   assert pane.evaluate('e=>e.scrollHeight>e.clientHeight'),(width,route,'no body scroller')
   assert pane.evaluate('e=>e.scrollHeight-e.clientHeight-e.scrollTop')<2,(route, width, pane.evaluate('e=>({top:e.scrollTop,height:e.scrollHeight,client:e.clientHeight})'))
   # An upward move disarms follow even within the forty-pixel bottom threshold.
   pane.evaluate('e=>e.scrollTop-=20');page.wait_for_timeout(100)
   top=pane.evaluate('e=>e.scrollTop')
   marker=f'{route} incoming-one'
   messages[channel]=messages[channel][1:]+[row(41,marker+' '+('new content '*20))]
   page.clock.run_for(6000)
   pane.get_by_text(marker,exact=False).wait_for()
   assert abs(pane.evaluate('e=>e.scrollTop')-top)<2,(route,top,pane.evaluate('e=>e.scrollTop'))
   chip=page.get_by_role('button',name='New messages · Jump to latest')
   chip.wait_for();assert pane.get_by_text(f'{channel} fixture 1.',exact=False).count()==1
   # Same IDs/status polling must not add another reason to jump.
   page.clock.run_for(6000)
   assert abs(pane.evaluate('e=>e.scrollTop')-top)<2
   chip.click()
   assert pane.evaluate('e=>e.scrollHeight-e.clientHeight-e.scrollTop')<2,(route, width, pane.evaluate('e=>({top:e.scrollTop,height:e.scrollHeight,client:e.clientHeight})'))
   messages[channel].append(row(42,f'{route} incoming-two '+('new content '*20)))
   page.clock.run_for(6000)
   pane.get_by_text(f'{route} incoming-two',exact=False).wait_for()
   assert pane.evaluate('e=>e.scrollHeight-e.clientHeight-e.scrollTop')<2,(route, width, pane.evaluate('e=>({top:e.scrollTop,height:e.scrollHeight,client:e.clientHeight})'))
   assert chip.count()==0
   pane.evaluate('e=>e.scrollTop=0');page.wait_for_timeout(100)
   messages[channel].append(row(43,f'{route} incoming-three'))
   page.clock.run_for(6000);pane.get_by_text(f'{route} incoming-three',exact=False).wait_for()
   assert pane.evaluate('e=>e.scrollTop')<2
   print(f'{width}x{height} {route}: upward scroll preserved;new-message jump and bottom following pass')
  page.goto(BASE+'/dash/vp')
  page.locator('.conversation').get_by_text('play incoming-three',exact=False).wait_for()
  assert page.locator('.conversation').evaluate('e=>e.scrollHeight-e.clientHeight-e.scrollTop')<2
  assert not errors,errors
  print(f'{width}x{height}: channel navigation starts at newest;no JS errors')
  page.close()
 browser.close()
