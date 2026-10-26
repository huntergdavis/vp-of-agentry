import hashlib
import json
from pathlib import Path
import subprocess
import tempfile
import unittest
from unittest.mock import patch
from tools.theme_wave_checks import OPEN_ICON_CHECK, target_meets_minimum, visible_focus
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

    def test_manifest_detects_build_config_mutation_and_excludes_ignored_files(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            subprocess.run(['git', 'init', '-q', str(root)], check=True, capture_output=True)
            (root / 'web').mkdir()
            (root / '.gitignore').write_text('web/.env\n')
            config = root / 'web/vite.config.js'
            config.write_text('export default {}')
            (root / 'web/.env').write_text('PRIVATE_TEST_SENTINEL=ignored')
            with patch.object(wave, 'ROOT', root):
                before = wave.source_hashes()
                self.assertIn('web/vite.config.js', before)
                self.assertNotIn('web/.env', before)
                config.write_text('export default {base:"/changed/"}')
                after = wave.source_hashes()
            self.assertNotEqual(before['web/vite.config.js'], after['web/vite.config.js'])

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
                    checks=[dict(name='Target >=24', passed=False), dict(name=OPEN_ICON_CHECK, passed=True)], openDialogRejected=True,
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

    def test_open_icon_failure_is_named_advisory_only_at_320(self):
        with tempfile.TemporaryDirectory() as directory:
            output = Path(directory); row = self.case(output, 320)
            row.update(theme='crt', textScale=2)
            row['checks'] = [dict(name=OPEN_ICON_CHECK, passed=False)]
            report = dict(cases=[row])
            self.assertEqual(wave.advisory_rows(report), [dict(case=row['id'], width=320, theme='crt', view='operations', textScale=2, check=OPEN_ICON_CHECK)])
            self.assertEqual(wave.browser_failures(report, {row['id']}, output), [])
            row['width'] = 390
            row['id'] = 'crt-operations-390-text2'
            self.assertEqual(wave.advisory_rows(report), [])
            self.assertTrue(any(OPEN_ICON_CHECK in f for f in wave.browser_failures(report, {row['id']}, output)))

    def test_missing_open_icon_check_is_structural_failure_even_at_320(self):
        with tempfile.TemporaryDirectory() as directory:
            output = Path(directory); row = self.case(output, 320)
            row['checks'] = [dict(name='Some other check', passed=True)]
            self.assertTrue(any('missing open-icon hit-test' in f for f in wave.browser_failures(dict(cases=[row]), {row['id']}, output)))

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
