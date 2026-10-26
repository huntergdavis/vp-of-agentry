import json
from pathlib import Path
import tempfile
import unittest
from tools.theme_capture import CaptureBlocked, ThemeCapture


class Page:
    def __init__(self, **counts):
        self.counts = dict(role_dialog=0, modal=0, backdrop=0, open_dialog=0)
        self.counts.update(counts); self.screenshots = []
    def evaluate(self, script): return self.counts
    def screenshot(self, **kwargs): self.screenshots.append(kwargs)


class CaptureTests(unittest.TestCase):
    def test_each_dialog_signal_refuses_capture_and_records_failure(self):
        for signal in ('role_dialog', 'modal', 'backdrop', 'open_dialog'):
            with self.subTest(signal=signal), tempfile.TemporaryDirectory() as directory:
                page = Page(**{signal: 1}); recorder = ThemeCapture(directory)
                with self.assertRaises(CaptureBlocked): recorder.capture(page, 'blocked.png')
                self.assertEqual(page.screenshots, [])
                result = json.loads((Path(directory) / 'evidence.json').read_text())['captures'][0]
                self.assertFalse(result['dialog_closed']); self.assertFalse(result['captured'])
                self.assertEqual(result['dialog_counts'][signal], 1)

    def test_closed_page_capture_is_recorded(self):
        with tempfile.TemporaryDirectory() as directory:
            page = Page(); recorder = ThemeCapture(directory)
            recorder.capture(page, 'closed.png', theme='crt', width=390)
            self.assertEqual(len(page.screenshots), 1)
            result = recorder.evidence['captures'][0]
            self.assertTrue(result['dialog_closed']); self.assertTrue(result['captured'])
            self.assertEqual(result['theme'], 'crt')


if __name__ == '__main__': unittest.main()
