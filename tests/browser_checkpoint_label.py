"""Synthetic status fixtures: archive integrity never implies creator-build provenance."""
from pathlib import Path
import subprocess,json,os
stamp=subprocess.check_output(["date","-u","+%Y-%m-%dT%H:%M:%SZ"],text=True).strip()
from playwright.sync_api import sync_playwright
BASE=os.environ['VP_BASE_URL'].rstrip('/')
ARTIFACTS=Path(os.environ.get('VP_TEST_ARTIFACTS','data/checkpoint-proof'))
ARTIFACTS.mkdir(parents=True,exist_ok=True)
chrome=sorted((Path.home()/'.cache/ms-playwright').glob('chromium-*/chrome-linux64/chrome'))[-1]
with sync_playwright() as p:
 b=p.chromium.launch(executable_path=str(chrome),args=['--no-sandbox'])
 for width,height in ((1440,900),(390,844)):
  page=b.new_page(viewport={'width':width,'height':height});errors=[];posts=[]
  page.on('pageerror',lambda e:errors.append(str(e)))
  status={'running':True,'run_name':'isolated-fixture','emulator':{'kind':'checkpoint','build_id':'dosbox-x-5a9c7c53-parity-o1','release':'2026.01.02','sha256':'fc66e91e8e8d48cc0b176bc350febab753bff297f2d93fc6c1e9d1f21cb6efae','scope':'running_session'},'state_archive':{'status':'verified','verified_count':14,'archived_at':stamp}}
  def route(r):
   if r.request.method!='GET':posts.append(r.request.url);r.abort();return
   path=r.request.url.split('/api/',1)[1].split('?',1)[0]
   if path=='game/video':r.fulfill(content_type='image/svg+xml',body='<svg xmlns="http://www.w3.org/2000/svg" width="640" height="400"><rect width="640" height="400" fill="#222"/><text x="20" y="40" fill="white">Synthetic screen</text></svg>');return
   result={'game/status':status,'channels':{'channels':[]},'messages':{'items':[]},'game/states':{'states':[]}}.get(path,{})
   r.fulfill(json=result)
  page.route('**/api/**',route)
  page.goto(BASE+'/dash/play')
  label=page.get_by_label('Session build',exact=True)
  label.get_by_text('This session uses the checkpoint build (2026.01.02 fc66e91e)',exact=True).wait_for()
  assert page.get_by_role('note').inner_text()=='States from earlier sessions are archived. We cannot verify which build wrote them.'
  assert 'creator_build' not in status['state_archive']
  assert 'written by' not in page.locator('body').inner_text().lower()
  assert page.evaluate('document.documentElement.scrollWidth<=innerWidth')
  page.screenshot(path=str(ARTIFACTS/f'play-{width}.png'))
  page.get_by_role('note').scroll_into_view_if_needed()
  page.screenshot(path=str(ARTIFACTS/f'saves-{width}.png'))
  status['running']=False
  status['emulator']['scope']='next_start'
  page.reload();label.get_by_text('Next session uses the checkpoint build (2026.01.02 fc66e91e)',exact=True).wait_for()
  for archive_status in ('pending','unavailable'):
   status['state_archive']={'status':archive_status,'verified_count':0,'archived_at':None}
   page.reload();label.wait_for();assert page.get_by_role('note').count()==0
  status['emulator']['kind']='other'
  page.reload();label.get_by_text('Next session uses another emulator build.',exact=True).wait_for()
  status.clear();status['running']=False
  page.reload();label.get_by_text('Checkpoint build identity is not available.',exact=True).wait_for()
  assert page.get_by_role('note').count()==0
  if os.environ.get('VP_STATUS_FIXTURE'):
   actual=json.loads(Path(os.environ['VP_STATUS_FIXTURE']).read_text())
   status.clear();status.update(actual)
   page.reload();label.wait_for()
   em=actual['emulator'];scope='This session uses' if em['scope']=='running_session' else 'Next session uses'
   if em['kind']=='checkpoint':
    expected=f"{scope} the checkpoint build ({em['release']} {em['sha256'][:8]})"
   elif em['kind']=='other':expected=f'{scope} another emulator build.'
   else:expected='Checkpoint build identity is not available.'
   assert label.inner_text()==expected
   archived=actual['state_archive']['status']=='verified' and actual['state_archive']['verified_count']>0
   assert page.get_by_role('note').count()==int(archived)
   print(f'{width}x{height}: recorded deployed API fields render faithfully; archive claim={archived}',flush=True)
  assert 'written by' not in page.locator('body').inner_text().lower()
  assert not errors,errors
  assert not posts,posts
  print(f'{width}x{height}: provisional running/stopped/missing identity and archive cases pass; no API writes or JS errors',flush=True)
  page.close()
 b.close()
