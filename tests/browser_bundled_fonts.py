"""Local-font gate against built baseline/candidate; synthetic APIs, no owner service.

Run through poolrad-heavy.sh with --dist, --base-dist and --output paths.
"""
import argparse
import functools
import hashlib
import http.server
import json
from pathlib import Path
import re
import sys
import threading
from urllib.parse import urlparse

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from playwright.sync_api import sync_playwright
from tests.browser_theme_capture import BOARD, PROGRESS, CHANNELS, MESSAGES
from tools.theme_capture import ThemeCapture

MAP = {'nostromo': 'Black Ops One', '2001': 'Michroma', 'tron': 'Oxanium', 'lcars': 'Dosis'}
THEMES = ['default', 'crt', *MAP]


def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


class Static(http.server.SimpleHTTPRequestHandler):
    def log_message(self, *_):
        pass

    def do_GET(self):
        if self.path.startswith('/dash/'):
            self.path = '/index.html'
        super().do_GET()


def serve(dist):
    server = http.server.ThreadingHTTPServer(('127.0.0.1', 0), functools.partial(Static, directory=str(dist)))
    threading.Thread(target=server.serve_forever, daemon=True).start()
    return server, f'http://127.0.0.1:{server.server_port}'


SNAPSHOT = '''() => {
 const display=document.querySelector('.dash-nav-brand');
 const style=e=>{const s=getComputedStyle(e);return Object.fromEntries([...s].filter(k=>!k.startsWith('--')).map(k=>[k,s.getPropertyValue(k)]))};
 return {display:display?getComputedStyle(display).fontFamily:null,
   body:getComputedStyle(document.body).fontFamily,
   faces:[...document.fonts].map(f=>({family:f.family,status:f.status})),
   styles:Object.fromEntries(['html','body','.dash-root','.dash-nav-brand'].map(s=>[s,document.querySelector(s)?style(document.querySelector(s)):null]))};
}'''


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('--dist', type=Path, required=True)
    p.add_argument('--base-dist', type=Path, required=True)
    p.add_argument('--output', type=Path, required=True)
    args = p.parse_args()
    args.output.mkdir(parents=True, exist_ok=False)
    report = {'cases': [], 'failures': [], 'not_verified': ['Real zoom/devices', 'Non-Latin or bold/italic coverage', 'Full layout/accessibility', 'Production deployment']}
    rows = json.loads((ROOT/'web/src/fonts/manifest.json').read_text())
    font_dir = ROOT/'web/src/fonts'
    total = sum(f.stat().st_size for f in font_dir.rglob('*') if f.is_file())
    assert total <= 110789, total
    emitted = list(args.dist.rglob('*.woff2'))
    assert len(emitted) == len(rows) == 4
    assert sum(f.stat().st_size for f in emitted) <= 89698
    for row in rows:
        assert sha(ROOT/row['path']) == row['sha256']
        assert (ROOT/row['path']).read_bytes()[:4] == b'wOF2'
        assert sha(ROOT/row['license_path']) == row['license_sha256']
        assert sum(sha(f) == row['sha256'] for f in emitted) == 1
        slug = row['package'].split('/')[-1]
        assert sha(args.dist/'assets'/f'{slug}-LICENSE.txt') == row['license_sha256']
    report['size'] = {'font_source_tree_bytes': total, 'font_payload_bytes': sum(f.stat().st_size for f in emitted)}
    for name, dist in [('base', args.base_dist), ('candidate', args.dist)]:
        report['size'][name+'_dist_bytes'] = sum(f.stat().st_size for f in dist.rglob('*') if f.is_file())
    report['size']['dist_growth_bytes'] = report['size']['candidate_dist_bytes']-report['size']['base_dist_bytes']
    recorder = ThemeCapture(args.output/'captures', {'emulated': True, 'dpr': 1, 'synthetic_apis': True})
    servers = []
    baseline = {}
    try:
        with sync_playwright() as pw:
            chrome = sorted((Path.home()/'.cache/ms-playwright').glob('chromium-*/chrome-linux64/chrome'))[-1]
            browser = pw.chromium.launch(executable_path=str(chrome), args=['--no-sandbox'])
            report['browser'] = browser.version
            for phase, dist in [('base', args.base_dist), ('candidate', args.dist), ('fallback', args.dist)]:
                server, base = serve(dist); servers.append(server)
                version = re.search(r'src="([^"]+\.js)"', (dist/'index.html').read_text())[1]
                for width in (1440, 390):
                    for view in ('cos', 'operations'):
                        for theme in THEMES if phase != 'fallback' else MAP:
                            context = browser.new_context(viewport={'width': width, 'height': 900 if width == 1440 else 844}, device_scale_factor=1)
                            page = context.new_page()
                            errors, external, requests, blocked = [], [], [], []
                            page.on('pageerror', lambda e: errors.append(str(e)))
                            page.on('request', lambda r: external.append(r.url) if urlparse(r.url).netloc != urlparse(base).netloc else None)
                            page.on('response', lambda r: requests.append({'url': urlparse(r.url).path, 'status': r.status}) if '.woff2' in r.url else None)
                            data = {'/api/channels': {'channels': CHANNELS}, '/api/messages': {'items': MESSAGES}, '/api/ops-board': BOARD, '/api/poolrad-dashboard/progress': PROGRESS, '/api/version': {'version': version}}
                            def api(route):
                                path = urlparse(route.request.url).path
                                if path == '/api/viewport' and route.request.method == 'POST':
                                    route.fulfill(status=204); return
                                if route.request.method != 'GET' or path not in data:
                                    errors.append('Unexpected API '+route.request.method+' '+path)
                                    route.abort(); return
                                route.fulfill(json=data[path])
                            page.route('**/api/**', api)
                            if phase == 'fallback':
                                def block(route):
                                    blocked.append(urlparse(route.request.url).path); route.abort()
                                page.route('**/*.woff2', block)
                            page.add_init_script('localStorage.setItem("vp-theme",'+json.dumps(theme)+')')
                            page.goto(base+'/dash/'+view, wait_until='networkidle')
                            page.locator('.message-wrap' if view == 'cos' else '[data-ops-section=reference]').first.wait_for()
                            page.evaluate('document.fonts.ready')
                            snapshot = page.evaluate(SNAPSHOT)
                            key = f'{theme}-{view}-{width}'
                            row = {'id': phase+'-'+key, 'theme': theme, 'phase': phase, 'width': width, 'view': view, 'snapshot': snapshot, 'requests': requests, 'blocked_fonts': blocked, 'external_requests': external, 'errors': errors, 'failures': []}
                            report['cases'].append(row)
                            if errors or external: row['failures'].append('JS/API error or other-origin request')
                            if phase == 'base':
                                baseline[key] = snapshot
                            else:
                                if snapshot['body'] != baseline[key]['body']: row['failures'].append('Body stack changed')
                                if theme in ('default', 'crt'):
                                    if any(snapshot[k] != baseline[key][k] for k in ('display', 'body', 'styles')):
                                        row['failures'].append('Default/CRT computed snapshot changed')
                                else:
                                    expected = MAP[theme]
                                    if snapshot['display'].split(',')[0].strip(' "\'') != expected: row['failures'].append('Display consumer did not adopt '+expected)
                                    loaded = any(f['family'].strip('"\'') == expected and f['status'] == 'loaded' for f in snapshot['faces'])
                                    if phase == 'candidate' and (not loaded or not any(r['status'] == 200 for r in requests)): row['failures'].append('Expected local face not loaded/requested')
                                    if phase == 'fallback' and (loaded or not blocked): row['failures'].append('Fallback control did not block used face')
                                recorder.capture(page, row['id']+'.png', theme=theme, view=view, width=width, phase=phase)
                            report['failures'] += [{'case': row['id'], 'reason': f} for f in row['failures']]
                            context.close()
            browser.close()
    finally:
        for server in servers: server.shutdown(); server.server_close()
        (args.output/'result.json').write_text(json.dumps(report, indent=2)+'\n')
    print(json.dumps({'cases': len(report['cases']), 'failures': report['failures'], 'size': report['size']}))
    return 1 if report['failures'] else 0


if __name__ == '__main__':
    raise SystemExit(main())
