import hashlib
import json
from pathlib import Path
import subprocess
import tempfile
import unittest
from tests.browser_theme_capture import target_meets_minimum, visible_focus
from tools import check_theme_wave as wave
from tools import theme_contrast as gate, theme_contrast_consumers as usage


class WaveTests(unittest.TestCase):
    def test_wrapped_union_does_not_hide_short_fragments(self):
        geometry = dict(union=dict(width=100, height=37), fragments=[dict(width=100, height=16), dict(width=50, height=16)])
        self.assertFalse(target_meets_minimum(geometry))
        geometry = dict(union=dict(width=100, height=24), fragments=[dict(width=100, height=24)])
        self.assertTrue(target_meets_minimum(geometry))
        geometry['fragments'] = []
        self.assertFalse(target_meets_minimum(geometry))

    def test_focus_pseudo_state_without_visible_outline_fails(self):
        geometry = dict(focused=True, focusVisible=True, outlineStyle='solid', outlineWidth=2, ringContained=True, unobscured=True)
        self.assertTrue(visible_focus(geometry))
        self.assertFalse(visible_focus(dict(geometry, outlineWidth=0)))
        self.assertFalse(visible_focus(dict(geometry, outlineStyle='none')))
        self.assertFalse(visible_focus(dict(geometry, ringContained=False)))

    def icon_report(self, own):
        css = gate.read_css() + own
        rows = usage.measure_icon_button(css, usage.read_consumers(), gate)
        for theme in ('default', 'crt', 'candidate'):
            for name in wave.NAMED[2:]: rows.append(dict(theme=theme, pair=name, status='PASS', ratio=7))
        return dict(pairs=rows)

    def test_omitted_own_tokens_fail_even_when_both_fallbacks_pass(self):
        own = ':root[data-theme="candidate"] { --white:#000; --border:#fff; }'
        report = self.icon_report(own)
        self.assertTrue(all(r['status'] in ('PASS', 'MARGINAL') for r in report['pairs'] if r['theme'] == 'candidate'))
        rows = wave.named_rows(report, 'candidate', own)
        failed = [r for r in rows if r['status'] == 'FAIL']
        self.assertEqual(len(failed), 2)
        self.assertTrue(all('declare its own' in r['error'] for r in failed))

    def test_low_named_contrast_fails_with_tokens_present(self):
        own = ':root[data-theme="candidate"] { --white:#000; --icon-button-border:#000; --icon-button-panel-border:#fff; }'
        rows = wave.named_rows(self.icon_report(own), 'candidate', own)
        row = next(r for r in rows if r['theme'] == 'candidate' and r['pair'] == wave.NAMED[0])
        self.assertEqual(row['status'], 'FAIL'); self.assertEqual(row['ratio'], 1)
        self.assertEqual(row['contrast_kind'], 'STATIC')

    def test_missing_named_row_is_not_a_pass(self):
        rows = wave.named_rows(dict(pairs=[]), 'candidate', ':root[data-theme="candidate"] { --icon-button-border:#000; }')
        self.assertTrue(all(r['status'] == 'FAIL' for r in rows))

    def case(self, output, width=390):
        image = output / 'image.png'; image.write_bytes(b'captured-image')
        capture = dict(file=image.name, sha256=hashlib.sha256(image.read_bytes()).hexdigest(), captured=True, dialog_closed=True)
        return dict(id=f'crt-operations-{width}-text1', width=width, view='operations', completed=True,
                    checks=[dict(name='Target >=24', passed=False)], openDialogRejected=True,
                    openDialogCapture=dict(capture, dialog_closed=False),
                    captures=[dict(capture, state=s) for s in ('closed', 'keyboard-focus')])

    def test_only_320_measured_findings_are_advisory(self):
        with tempfile.TemporaryDirectory() as directory:
            output = Path(directory); row = self.case(output, 320)
            self.assertEqual(wave.browser_failures(dict(cases=[row]), {row['id']}, output), [])
            row['width'] = 390
            self.assertTrue(wave.browser_failures(dict(cases=[row]), {row['id']}, output))

    def test_missing_image_or_case_always_fails_even_at_320(self):
        with tempfile.TemporaryDirectory() as directory:
            output = Path(directory); row = self.case(output, 320)
            (output / 'image.png').unlink()
            self.assertTrue(wave.browser_failures(dict(cases=[row]), {row['id']}, output))
            self.assertTrue(wave.browser_failures(dict(cases=[]), {row['id']}, output))

    def test_image_mutation_and_dialog_guard_fail_closed(self):
        with tempfile.TemporaryDirectory() as directory:
            output = Path(directory); row = self.case(output, 320)
            (output / 'image.png').write_bytes(b'changed')
            self.assertTrue(wave.browser_failures(dict(cases=[row]), {row['id']}, output))
            row['openDialogRejected'] = False
            self.assertTrue(any('negative dialog' in x for x in wave.browser_failures(dict(cases=[row]), {row['id']}, output)))

    def test_existing_baseline_expiry_is_not_hidden(self):
        baseline = json.loads(usage.DEFAULT_BASELINE.read_text()); entry = baseline['entries'][0]
        row = dict(entry, status='FAIL', referenced=True)
        self.assertEqual(usage.apply_baseline([row], baseline)[0]['status'], 'BASELINE-FAIL')
        self.assertEqual(usage.apply_baseline([row], baseline, ['t192'])[0]['status'], 'FAIL')

    def test_unscoped_css_tool_returns_nonzero(self):
        with tempfile.TemporaryDirectory() as directory:
            p = Path(directory) / 'candidate.css'; p.write_text('body { color:#fff; }')
            result = subprocess.run(['node', 'web/tools/check-theme-scope.cjs', directory], cwd=wave.ROOT, capture_output=True, text=True)
            self.assertEqual(result.returncode, 1); self.assertIn('unscoped selector', result.stderr)


if __name__ == '__main__': unittest.main()
