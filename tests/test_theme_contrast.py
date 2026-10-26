import contextlib
import io
from pathlib import Path
import tempfile
import unittest
from tools import theme_contrast as gate


class ThemeContrastTests(unittest.TestCase):
    def test_current_palette_calibration(self):
        rows = gate.measure(gate.read_css())
        actual = {(r['theme'], r['pair']): r for r in rows}
        expected = {'default': (12.97, 8.42, 8.91), 'crt': (15.57, 8.59, 15.59)}
        for theme, ratios in expected.items():
            for pair, expected_ratio in zip(('ink/bg', 'muted/bg', 'accent/bg'), ratios):
                self.assertAlmostEqual(actual[theme, pair]['ratio'], expected_ratio, places=2)
        self.assertTrue(all(r['status'] != 'FAIL' for r in rows))
        self.assertEqual(gate.contrast((0, 0, 0), (255, 255, 255)), 21)

    def test_directory_loads_new_css_without_shared_file_edits(self):
        with tempfile.TemporaryDirectory() as directory:
            directory = Path(directory)
            (directory / 'default.css').write_text(gate.read_css())
            (directory / 'new.css').write_text(':root[data-theme="new"] { --ink:#ffffff; }')
            (directory / 'new.json').write_text('{"id":"new","name":"New","order":20}')
            rows = gate.measure(gate.read_css(directory))
            self.assertEqual(len([row for row in rows if row['theme'] == 'new']), 4)
        with tempfile.TemporaryDirectory() as directory, self.assertRaises(ValueError):
            gate.read_css(directory)

    def test_new_theme_alias_inheritance_and_later_blocks(self):
        css = gate.read_css() + '''
        :root[data-theme="future"] { --ink: #000; --local: #fff; }
        :root[data-theme="future"] { --ink: var(--local); }
        '''
        rows = [r for r in gate.measure(css) if r['theme'] == 'future']
        self.assertEqual(len(rows), 4)
        bg = gate.color(gate.theme_tokens(css)['default']['bg'])
        self.assertEqual(rows[0]['ratio'], gate.contrast((255, 255, 255), bg))

    def test_failure_names_pair_and_suggests_a_color_that_really_passes(self):
        # This synthetic theme still supplies the shared control-boundary alias target.
        css = gate.read_css() + ':root[data-theme="bad"] { --ink: var(--bg); --icon-button-panel-border: var(--muted); }'
        row = next(r for r in gate.measure(css) if r['theme'] == 'bad' and r['pair'] == 'ink/bg')
        self.assertEqual(row['status'], 'FAIL')
        self.assertGreaterEqual(gate.contrast(gate.color(row['suggestion']), gate.color(row['background_value'])), 7)
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / 'tokens.css'; path.write_text(css)
            out = io.StringIO()
            with contextlib.redirect_stdout(out): result = gate.main([str(path)])
        self.assertEqual(result, 1)
        self.assertIn('FAIL bad ink/bg', out.getvalue())
        self.assertIn('WOULD PASS', out.getvalue())

    def test_marginal_and_unrounded_failure(self):
        css = ':root { --bg:#fff; --ink:#595959; --muted:#777; --accent:#000; --accent-contrast:#fff; }'
        rows = gate.measure(css)
        self.assertEqual(rows[0]['status'], 'MARGINAL')
        self.assertEqual(rows[1]['status'], 'FAIL')
        self.assertLess(rows[1]['ratio'], 4.5)
        suggestion = gate.passing_foreground((200, 200, 200), (255, 255, 255), 7)
        self.assertGreaterEqual(gate.contrast(gate.color(suggestion), (255, 255, 255)), 7)
        self.assertIsNone(gate.passing_foreground((120, 120, 120), (119, 119, 119), 7))

    def test_every_foreground_role_fails_and_guidance_passes(self):
        for foreground, background, floor in gate.PAIRS:
            with self.subTest(foreground=foreground):
                css = gate.read_css() + f':root[data-theme="broken"] {{ --{foreground}: var(--{background}); }}'
                row = next(r for r in gate.measure(css) if r['theme'] == 'broken' and r['foreground'] == foreground)
                self.assertEqual(row['status'], 'FAIL')
                self.assertEqual(row['ratio'], 1)
                self.assertGreaterEqual(gate.contrast(gate.color(row['suggestion']), gate.color(row['background_value'])), floor)

    def test_foreground_alpha_composites_instead_of_disappearing(self):
        css = ':root { --bg:#000; --ink:#fff1; --muted:#fff; --accent:#fff; --accent-contrast:#000; }'
        row = gate.measure(css)[0]
        self.assertEqual(row['status'], 'FAIL')
        self.assertLess(row['ratio'], 2)
        self.assertEqual(gate.foreground_color('#fff0', (0, 0, 0)), (0, 0, 0))
        self.assertEqual(gate.foreground_color('#ffffffff', (0, 0, 0)), (255, 255, 255))

    def test_unsupported_or_missing_tokens_never_pass(self):
        baseline = gate.read_css()
        for extra in (':root { --ink:var(--absent); }', ':root { --ink:var(--ink); }',
                      ':root { --bg:#ffffff80; }',
                      '@media print { :root { --bg:#fff; } }',
                      '@media print { :root { --alias:#fff; } }',
                      ':root[data-theme="crt"]:hover { --ink:#000; }'):
            with self.subTest(extra=extra), self.assertRaises(ValueError): gate.measure(baseline + extra)
        with self.assertRaises(ValueError): gate.measure('')


if __name__ == '__main__': unittest.main()
