"""Dock opens everywhere and uses only the direct chat transport; synthetic sends."""
import os,subprocess
from pathlib import Path
from playwright.sync_api import sync_playwright
ROOT=Path(__file__).resolve().parents[1]
BASE=os.environ['VP_BASE_URL']
password=dict(line.split(': ',1) for line in Path(os.environ['VP_TEST_CREDENTIALS_PATH']).read_text().strip().splitlines())['Password']
chrome=sorted((Path.home()/'.cache/ms-playwright').glob('chromium-*/chrome-linux64/chrome'))[-1]
stamp=subprocess.check_output(['date','-u','+%Y-%m-%dT%H:%M:%SZ'],text=True).strip()
with sync_playwright() as p:
 b=p.chromium.launch(executable_path=str(chrome),args=['--no-sandbox'])
 for width,height in ((1440,900),(390,844)):
  page=b.new_page(viewport={'width':width,'height':height});errors=[];posts=[];items=[]
  page.on('pageerror',lambda e:errors.append(str(e)))
  page.route('**/api/messages?*',lambda r:r.fulfill(json={'items':items}))
  def send(route):
   payload=route.request.post_data_json;posts.append(payload)
   item=dict(id=len(posts),channel=payload['channel'],role='owner',body=payload['text'],delivery='unconfirmed',outcome='unconfirmed',created_at=stamp,attachments=[])
   items.append(item);route.fulfill(json=item)
  page.route('**/api/pane-send',send)
  page.goto(BASE+'/dash/operations');page.locator('#password').fill(password);page.get_by_role('button',name='Open desk').click()
  trigger=page.get_by_role('button',name='Message CoS / VP')
  trigger.wait_for();trigger.focus();page.keyboard.press('Control+/')
  dialog=page.get_by_role('dialog',name='Message CoS or VP');dialog.wait_for()
  assert page.locator('#dock-message').evaluate('e=>e===document.activeElement')
  page.get_by_label('Message',exact=True).fill('cos dock fixture')
  page.get_by_label('Recipient').select_option('vp')
  page.get_by_label('Message',exact=True).fill('vp retained draft')
  page.get_by_label('Recipient').select_option('cos')
  assert page.get_by_label('Message',exact=True).input_value()=='cos dock fixture'
  page.get_by_role('button',name='Send message',exact=True).wait_for()
  page.wait_for_function("!document.querySelector('.message-dock button[type=submit]').disabled")
  dialog.locator('form').evaluate('f=>{f.requestSubmit();f.requestSubmit()}')
  dialog.get_by_role('status').filter(has_text='unconfirmed').wait_for()
  assert len(posts)==1 and posts[0]['channel']=='cos'
  assert page.get_by_label('Message',exact=True).input_value()==''
  page.get_by_label('Recipient').select_option('vp')
  assert page.get_by_label('Message',exact=True).input_value()=='vp retained draft'
  page.keyboard.press('Escape');assert not dialog.is_visible()
  assert trigger.evaluate('e=>e===document.activeElement')
  page.goto(BASE+'/dash/cos');page.get_by_text('cos dock fixture',exact=True).wait_for()
  for route in ('cos','vp','fleet','play','operations'):
   page.goto(BASE+'/dash/'+route)
   page.get_by_role('button',name='Message CoS / VP').wait_for()
   page.keyboard.press('Control+/');dialog.wait_for()
   assert page.evaluate('document.documentElement.scrollWidth<=innerWidth')
   box=dialog.bounding_box();assert box['x']>=0 and box['x']+box['width']<=width
   page.keyboard.press('Escape')
  assert not errors,errors
  print(f'{width}x{height}: five routes,keyboard focus/Escape,draft isolation,one direct POST,exact outcome and history pass')
  page.close()
 b.close()
