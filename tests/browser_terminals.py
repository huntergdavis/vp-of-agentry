"""Verify reachable messaging and current-screen scrolling on the isolated bundle."""
import os
from pathlib import Path
from playwright.sync_api import sync_playwright
ROOT=Path(__file__).resolve().parents[1]
BASE=os.environ["VP_BASE_URL"]
password=dict(line.split(": ",1) for line in Path(os.environ["VP_TEST_CREDENTIALS_PATH"]).read_text().strip().splitlines())["Password"]
chrome=sorted((Path.home()/".cache/ms-playwright").glob("chromium-*/chrome-linux64/chrome"))[-1]
rows=[dict(pane_id=f"%{i}",name=f"Lane {i}",project=f"Project {i:02}",agent="codex",
           last_activity_s=10,send="guarded",can_type=True) for i in range(16)]
with sync_playwright() as p:
 browser=p.chromium.launch(executable_path=str(chrome),args=["--no-sandbox"])
 for width,height in ((1440,900),(390,844)):
  page=browser.new_page(viewport={"width":width,"height":height})
  errors=[];posts=[]
  page.on("pageerror",lambda e:errors.append(str(e)))
  page.route("**/api/fleet",lambda r:r.fulfill(json={"state":"ok","rows":rows,"unrouted":{
    "state":"ok","note":"Process presence is not proof of active work",
    "rows":[{"pid":98765,"agent":"codex","project":"unrouted-fixture","reason":"No pane route found for this process","last_session_write_s":120,"session_age_reason":None}]}}))
  screen="\n".join(f"Screen row {i} "+("."*180) for i in range(40))
  page.route("**/api/pane-text?*",lambda r:r.fulfill(json={"text":screen}))
  def send(route):
   posts.append(route.request.post_data_json)
   route.fulfill(json={"pane":"%15","outcome":"queued","note":"daemon hold"})
  page.route("**/api/pane-send",send)
  page.goto(BASE+"/dash/fleet")
  page.locator("#password").fill(password);page.get_by_role("button",name="Open desk").click()
  inventory=page.get_by_role("region",name="Unrouted agent processes")
  inventory.wait_for()
  assert "unrouted-fixture" in inventory.inner_text()
  assert "No pane route" in inventory.inner_text()
  assert inventory.locator("button").count()==0
  group=page.locator(".fleet-project").last
  group.locator("button").click()
  page.locator(".dash-terminal-text").wait_for()
  box=page.locator("#lane-draft").bounding_box()
  assert box["y"]>=0 and box["y"]+box["height"]<=height,(width,box)
  assert page.locator(".fleet-body").evaluate("e=>e.scrollHeight>e.clientHeight")
  page.get_by_label("Message this agent").fill("guarded test")
  page.locator(".dash-terminal form").evaluate("f=>{f.requestSubmit();f.requestSubmit()}")
  page.get_by_role("status").filter(has_text="[queued]").wait_for()
  assert posts==[{"pane":"%15","text":"guarded test"}],posts
  assert page.locator("#lane-draft").input_value()==""
  assert "Current screen only" in page.get_by_test_id("pane-text").inner_text()
  terminal=page.locator(".dash-terminal-text")
  terminal.scroll_into_view_if_needed()
  terminal.hover();page.mouse.wheel(0,500)
  page.wait_for_timeout(200)
  assert terminal.evaluate("e=>e.scrollTop>0"),"captured screen did not wheel-scroll"
  assert terminal.evaluate("e=>e.scrollWidth>e.clientWidth")
  terminal.evaluate("e=>e.scrollLeft=200")
  assert terminal.evaluate("e=>e.scrollLeft>0")
  assert page.evaluate("document.documentElement.scrollWidth<=innerWidth")
  assert not errors,errors
  page.locator("#lane-draft").scroll_into_view_if_needed()
  page.screenshot(path=str(ROOT/"data"/f"terminals-fixed-{width}.png"))
  print(f"{width}x{height}: composer y={box['y']:.1f}, bottom={box['y']+box['height']:.1f}; outer/screen scrolling and single guarded POST pass")
  page.close()
 browser.close()
