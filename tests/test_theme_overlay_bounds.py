import copy
import hashlib
import json
from pathlib import Path
import subprocess
import tempfile
import unittest
from unittest.mock import patch
from tools import check_theme_wave as wave
from tools import theme_overlay_bounds as overlay


def fixture():
    themes = ['crt', 'default']
    tokens = {'default': {'overlay': 'none'}, 'crt': {
        'overlay': 'repeating-linear-gradient(0deg, rgba(0, 0, 0, 0.12) 0 1px, transparent 1px 4px)'}}
    named = [dict(theme=t, pair=p, status='PASS', foreground_value='#000', background_value='#fff')
             for t in themes for p in overlay.ICON_PAIRS]
    cases = [dict(id=f'{t}-{v}-390-text{s}', theme=t, width=390, view=v, textScale=s,
                  iconOpen=dict(opaque=True, border='rgb(0, 0, 0)', surface='rgb(255, 255, 255)'))
             for t in themes for v in ('cos', 'operations') for s in (1, 2)]
    return dict(themes=themes, widths=[390], named_rows=named, browser=dict(cases=cases), failures=[]), tokens


class OverlayTests(unittest.TestCase):
    def test_reviewed_crt_bound_and_current_token_opacity(self):
        row = overlay.bounds('#315c3d', '#c1f4c7', .12)
        self.assertAlmostEqual(row['endpointMinimum'], 4.770273840214675)
        self.assertAlmostEqual(row['independentContinuousPhaseLowerBound'], 4.770273840214675)
        self.assertEqual(overlay.overlay_alpha({'overlay': 'none'}), 0)
        tokens = {'overlay': 'repeating-linear-gradient(0deg, rgb(0 0 0 / var(--scanline-strength)) 0 1px, transparent 1px 4px)',
                  'scanline-strength': '0.2'}
        self.assertEqual(overlay.overlay_alpha(tokens), .2)
        with self.assertRaises(ValueError):
            overlay.overlay_alpha({'overlay': 'linear-gradient(red, blue)'})

    def test_interval_overlap_is_not_a_contrast_pass(self):
        row = overlay.bounds('#777', '#888', .5)
        self.assertEqual(row['independentContinuousPhaseLowerBound'], 1)

    def test_summary_links_exact_artifact_and_rows(self):
        summary, tokens = fixture()
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory)
            wave.record_overlay_bounds(summary, path, tokens)
            link = summary['overlay_bounds']; artifact = path / link['file']
            proof = json.loads(artifact.read_text())
            self.assertTrue(link['passed']); self.assertFalse(summary['failures'])
            self.assertEqual((link['named_rows'], link['computed_rows']), (4, 8))
            self.assertEqual(link['sha256'], hashlib.sha256(artifact.read_bytes()).hexdigest())
            self.assertEqual(link['min_endpoint_minimum'], min(r['endpointMinimum'] for r in proof['rows']))
            self.assertEqual(link['min_continuous'], min(r['independentContinuousPhaseLowerBound'] for r in proof['rows']))

    def test_missing_duplicate_nonopaque_or_invalid_rows_fail_closed(self):
        original, tokens = fixture()
        for mutation in ('missing', 'duplicate', 'nonopaque', 'missing-color', 'low-color'):
            with self.subTest(mutation=mutation):
                summary = copy.deepcopy(original)
                cases = summary['browser']['cases']
                if mutation == 'missing': cases.pop()
                elif mutation == 'duplicate': cases.append(cases[0])
                elif mutation == 'nonopaque': cases[0]['iconOpen']['opaque'] = False
                elif mutation == 'missing-color': del cases[0]['iconOpen']['border']
                else: cases[0]['iconOpen']['border'] = cases[0]['iconOpen']['surface']
                self.assertFalse(overlay.overlay_proof(summary, tokens)['passed'])
        summary = copy.deepcopy(original); summary['named_rows'].pop()
        self.assertFalse(overlay.overlay_proof(summary, tokens)['passed'])

    def test_all_twelve_declared_overlays_resolve_and_missing_is_distinct(self):
        tokens = wave.contrast.theme_tokens(wave.contrast.read_css())
        self.assertEqual(len(tokens), 12)
        for theme, values in tokens.items():
            with self.subTest(theme=theme):
                self.assertIn('overlay', values)
                self.assertEqual(overlay.overlay_alpha(values), .12 if theme in ('crt', 'nostromo') else 0)
        summary, profiles = fixture()
        del profiles['crt']['overlay']
        proof = overlay.overlay_proof(summary, profiles)
        self.assertFalse(proof['passed'])
        self.assertTrue(any('crt' in e and 'Missing --overlay declaration' in e for e in proof['errors']))
        profiles['crt']['overlay'] = 'linear-gradient(red, blue)'
        proof = overlay.overlay_proof(summary, profiles)
        self.assertFalse(proof['passed'])
        self.assertTrue(any('crt' in e and 'Unsupported --overlay' in e for e in proof['errors']))

    def test_320_analytical_rows_are_retained_and_block_on_failure(self):
        summary, tokens = fixture()
        summary['widths'] = [320]
        for case in summary['browser']['cases']:
            case['width'] = 320
            case['id'] = case['id'].replace('-390-', '-320-')
        proof = overlay.overlay_proof(summary, tokens)
        self.assertTrue(proof['passed'])
        self.assertEqual(sum(r.get('width') == 320 for r in proof['rows']), 8)
        summary['browser']['cases'][0]['iconOpen']['border'] = 'rgb(255, 255, 255)'
        proof = overlay.overlay_proof(summary, tokens)
        self.assertFalse(proof['passed'])
        self.assertTrue(any('crt panel computed color width 320' in e for e in proof['errors']))
        self.assertIn('blocking at every width including 320', proof['method'])

    def run_wave(self, low_color):
        """Real main orchestration; mock external stages, not overlay/gating logic."""
        summary, tokens = fixture()
        if low_color:
            summary['browser']['cases'][0]['iconOpen']['border'] = 'rgb(255, 255, 255)'
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory); (root/'web/src/themes').mkdir(parents=True)
            (root/'web/src/themes/default.css').write_text('')
            dist = root/'web/dist'; dist.mkdir(parents=True)
            (dist/'index.html').write_text('<script src="/assets/fixture.js"></script>')
            (dist/'assets').mkdir(); (dist/'assets/fixture.js').write_text('// fixture')
            def run(cmd, **kwargs):
                if 'tools/theme_contrast.py' in cmd:
                    kwargs['stdout'].write(json.dumps({'pairs': []}))
                elif 'tests/browser_theme_capture.py' in cmd:
                    out = Path(cmd[cmd.index('--output')+1]); out.mkdir()
                    (out/'results.json').write_text(json.dumps(summary['browser']))
                return subprocess.CompletedProcess(cmd, 0)
            with patch.object(wave, 'ROOT', root), patch.object(wave, 'WIDTHS', (390,)), \
                 patch.object(wave, 'source_hashes', return_value={}), \
                 patch.object(wave, 'named_rows', return_value=summary['named_rows']), \
                 patch.object(wave, 'browser_failures', return_value=[]), \
                 patch.object(wave, 'advisory_rows', return_value=[]), \
                 patch.object(wave.contrast, 'read_css', return_value=''), \
                 patch.object(wave.contrast, 'theme_tokens', return_value=tokens), \
                 patch.object(wave.subprocess, 'check_output', return_value='fixture'), \
                 patch.object(wave.subprocess, 'run', side_effect=run):
                code = wave.main(['--theme', 'default', '--base', 'fixture', '--artifacts', str(root/'data/wave')])
            return code, json.loads((root/'data/wave/summary.json').read_text())

    def test_failing_overlay_row_fails_actual_wave_exit(self):
        code, summary = self.run_wave(True)
        self.assertEqual(code, 1)
        self.assertFalse(summary['passed'])
        self.assertFalse(summary['overlay_bounds']['passed'])
        self.assertTrue(any('overlay bounds failed' in s for s in summary['failures']))

    def test_passing_overlay_rows_complete_wave(self):
        code, summary = self.run_wave(False)
        self.assertEqual(code, 0)
        self.assertTrue(summary['passed'])
        self.assertTrue(summary['overlay_bounds']['passed'])
        self.assertFalse(any('stage 2' in s for s in summary['not_covered']))


if __name__ == '__main__':
    unittest.main()
