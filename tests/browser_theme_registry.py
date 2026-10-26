"""Picker regression reuses WEB PR30/data/check_theme_picker.py; captures now require closed dialogs."""
from pathlib import Path
import re, os, json, subprocess, sys
from datetime import datetime
ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT))
from tools.theme_capture import ThemeCapture
from playwright.sync_api import sync_playwright
root=Path.cwd();dist=Path(os.environ['VP_TEST_DIST'])
out=Path(os.environ['VP_TEST_ARTIFACTS']);out.mkdir(parents=True,exist_ok=True)
base=os.environ['VP_BASE_URL'].rstrip('/')
stamp=os.environ.get('VP_TEST_STAMP') or subprocess.check_output(['date','-Iseconds'],text=True).strip()
recorder=ThemeCapture(out,{'source_head':os.environ.get('VP_TEST_SOURCE_SHA'),'timestamp':stamp,'emulated':True,'requested_dpr':1.8})
probes=[]
def probe(page,theme,width):
 return dict(theme=theme,width=width,styles=page.evaluate('''() => {
   const targets=['html','body','.dash-root','.dash-nav','.dash-header','h1','.conversation',
     '.message-wrap','.cs-message','.cs-message__content','.composer','.editor','.toolbar button','.composer .send'];
   const snapshot=(element,pseudo)=>{const s=getComputedStyle(element,pseudo);return Object.fromEntries([...s].sort().map(k=>[k,s.getPropertyValue(k)]));};
   return {...Object.fromEntries(targets.map(selector=>{const e=document.querySelector(selector);return [selector,e?snapshot(e):null]})),
     'body::after':snapshot(document.body,'::after')};
 }'''))
version=re.search(r'src="([^"]+\.js)"',dist.joinpath('index.html').read_text())[1]
chrome=sorted((Path.home()/'.cache/ms-playwright').glob('chromium-*/chrome-linux64/chrome'))[-1]
with sync_playwright() as p:
 browser=p.chromium.launch(executable_path=str(chrome),args=['--no-sandbox'])
 for width in (1440,1422,1067,960,800,700,390):
  height=900 if width>480 else 844
  page=browser.new_page(viewport={'width':width,'height':height},device_scale_factor=1.8);errors=[];writes=[]
  page.on('pageerror',lambda e:errors.append(str(e)))
  page.clock.set_fixed_time(datetime.fromisoformat(stamp))
  def route(r):
   if r.request.method=='POST' and r.request.url.endswith('/api/viewport'):
    assert set(r.request.post_data_json)=={'innerWidth','innerHeight','devicePixelRatio','screenWidth','screenHeight'}
    r.fulfill(status=204);return
   if r.request.method!='GET':writes.append(r.request.url);r.abort();return
   path=r.request.url.split('/api/',1)[1].split('?',1)[0]
   result={'channels':{'channels':[{'id':n,'name':n.upper(),'status':'ready','can_message':True,'pane_id':'fixture'} for n in ('cos','vp')]},'messages':{'items':[{'id':1,'role':'agent','body':'Synthetic theme registry probe','created_at':stamp,'attachments':[]}]},'version':{'version':version}}.get(path,{})
   r.fulfill(json=result)
  page.route('**/api/**',route)
  page.goto(base+'/dash/cos')
  trigger=page.get_by_role('button',name='Appearance',exact=True);trigger.wait_for()
  assert page.locator('html').get_attribute('data-theme')=='default'
  page.evaluate('window.pickerNavigationMarker=42')
  trigger.click();dialog=page.get_by_role('dialog',name='Appearance',exact=True)
  select=dialog.get_by_label('Theme',exact=True)
  assert select.evaluate('e=>e===document.activeElement')
  assert dialog.locator('input[type=password]').count()==0
  assert select.locator('option').all_text_contents()==['Default','1980s CRT']
  baseline=page.evaluate('getComputedStyle(document.documentElement).getPropertyValue("--bg").trim()')
  assert baseline, 'Token stylesheet missing'
  page.keyboard.press('Escape')
  page.locator('.message-wrap').first.wait_for()
  page.evaluate('document.fonts.ready')
  probes.append(probe(page,'default',width))
  recorder.capture(page,f'default-{width}.png',theme='default',width=width,height=height)
  trigger.click()
  select.select_option('crt')
  assert page.locator('html').get_attribute('data-theme')=='crt'
  assert page.evaluate('localStorage.getItem("vp-theme")')=='crt'
  assert page.evaluate('window.pickerNavigationMarker')==42
  crt=page.evaluate('getComputedStyle(document.documentElement).getPropertyValue("--bg").trim()')
  assert crt!=baseline, 'CRT stylesheet has no visual token override'
  assert page.evaluate('document.documentElement.scrollWidth<=innerWidth')
  page.keyboard.press('Escape')
  page.evaluate('document.fonts.ready')
  probes.append(probe(page,'crt',width))
  recorder.capture(page,f'crt-{width}.png',theme='crt',width=width,height=height)
  trigger.click()
  # Focus wraps within this appearance surface; Escape restores the trigger.
  page.keyboard.press('Tab');assert dialog.get_by_role('button',name='Close appearance').evaluate('e=>e===document.activeElement')
  page.keyboard.press('Shift+Tab');assert select.evaluate('e=>e===document.activeElement')
  page.keyboard.press('Escape');assert dialog.count()==0
  assert trigger.evaluate('e=>e===document.activeElement')
  page.reload();trigger.wait_for();assert page.locator('html').get_attribute('data-theme')=='crt'
  page.goto(base+'/dash/vp');trigger.wait_for();assert page.locator('html').get_attribute('data-theme')=='crt'
  trigger.click();select.select_option('default');assert page.locator('html').get_attribute('data-theme')=='default'
  assert page.evaluate('getComputedStyle(document.documentElement).getPropertyValue("--bg").trim()')==baseline
  page.evaluate('localStorage.setItem("vp-theme","unrecognized")');page.reload();trigger.wait_for()
  assert page.locator('html').get_attribute('data-theme')=='default'
  # Both read and write storage failures must retain usable Default controls.
  page.add_init_script("Object.defineProperty(window,'localStorage',{get(){throw new DOMException('blocked','SecurityError')}})")
  page.reload();trigger.wait_for();assert page.locator('html').get_attribute('data-theme')=='default'
  trigger.click();select.select_option('crt')
  assert page.locator('html').get_attribute('data-theme')=='default'
  dialog.get_by_role('status').wait_for()
  assert not errors,errors
  assert not writes,writes
  print(f'{width}x{height}: default/CRT live swap, distinct bg tokens, reload and route persistence, invalid/blocked storage fallback, focus/Escape, no password surface/unexpected API writes/JS errors PASS',flush=True)
  page.close()
 browser.close()

(out/'probes.json').write_text(json.dumps(probes,indent=2)+'\n')
