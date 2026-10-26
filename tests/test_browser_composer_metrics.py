"""Execute the focused browser's real METRICS against synthetic DOM/style snapshots.

This checks arithmetic and choice of surface, not browser rendering. Node is
already required by the web build. AST extraction avoids importing Playwright.
"""
import ast
import json
from pathlib import Path
import subprocess
import unittest


METRIC_FILE = Path(__file__).with_name('browser_composer_controls.py')

# Only the DOM/style methods used by METRICS are supplied. No replacement
# contrast implementation lives here: Node executes the actual measurement.
SNAPSHOT = r"""
const vm = require('node:vm');
const input = JSON.parse(require('node:fs').readFileSync(0, 'utf8'));
const rect = {x:0,y:0,width:24,height:24,right:24,bottom:24};
function element(className, style = {}) {
  return {className, style, children: [], title: '', textContent: '',
    getBoundingClientRect: () => rect, getClientRects: () => [rect],
    getAttribute: () => null, matches: () => true,
    querySelector: () => null, querySelectorAll: () => []};
}
const toolbar = element('formatting-controls', {opacity:'1'});
const editor = element('editor');
const send = element('primary send');
const attach = element('attach', {color:input.ink, backgroundColor:input.attach,
  borderColor:'rgb(128, 128, 128)', borderWidth:'1px', borderStyle:'solid'});
const composer = element('composer', {backgroundColor:input.composer,
  borderTopWidth:'0px', borderBottomWidth:'0px',
  paddingTop:'5px', paddingBottom:'5px', paddingLeft:'0px', paddingRight:'0px'});
composer.children = [toolbar, element('composer-input'), send, attach];
composer.querySelector = selector => ({
  '.formatting-controls, .toolbar':toolbar, '.editor':editor,
  '.send':send, '.attach':attach, '.composer-placeholder':null
})[selector];
composer.querySelectorAll = () => [send, attach];
const context = {document:{querySelector:() => composer,
    documentElement:{scrollWidth:1067}}, innerWidth:1067,
  getComputedStyle:element => element.style, matchMedia:() => ({matches:false})};
process.stdout.write(JSON.stringify(vm.runInNewContext('('+input.metrics+')()', context)));
"""


class ComposerMetricTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        tree = ast.parse(METRIC_FILE.read_text())
        cls.metrics = next(ast.literal_eval(node.value) for node in tree.body
                           if isinstance(node, ast.Assign)
                           and any(isinstance(t, ast.Name) and t.id == 'METRICS'
                                   for t in node.targets))

    def measure(self, composer, attach, ink):
        result = subprocess.run(['node', '-e', SNAPSHOT], check=True,
                                input=json.dumps(dict(metrics=self.metrics,
                                    composer=composer, attach=attach, ink=ink)),
                                text=True, capture_output=True)
        return json.loads(result.stdout)

    def test_dark_ink_on_dark_attach_fails_despite_light_composer(self):
        # Reviewer i28380 counterexample: the old composer denominator reports
        # 18.883 (false pass); Attach's actual surface gives 1.112 (failure).
        metric = self.measure('rgb(255, 255, 255)', 'rgb(0, 0, 0)', 'rgb(17, 17, 17)')
        self.assertTrue(metric['attachText']['opaque'])
        self.assertAlmostEqual(metric['attachTextContrast'], 1.1121078324840545)
        self.assertLess(metric['attachTextContrast'], 4.5)

    def test_dark_ink_on_light_attach_passes_despite_dark_composer(self):
        metric = self.measure('rgb(0, 0, 0)', 'rgb(255, 255, 255)', 'rgb(17, 17, 17)')
        self.assertTrue(metric['attachText']['opaque'])
        self.assertAlmostEqual(metric['attachTextContrast'], 18.883060964594996)
        self.assertGreaterEqual(metric['attachTextContrast'], 4.5)

    def test_changing_only_composer_does_not_change_attach_contrast(self):
        args = ('rgb(0, 0, 0)', 'rgb(255, 255, 255)')
        dark = self.measure('rgb(0, 0, 0)', *args)
        light = self.measure('rgb(255, 255, 255)', *args)
        self.assertEqual(dark['attachTextContrast'], light['attachTextContrast'])
        self.assertAlmostEqual(dark['attachTextContrast'], 21)


if __name__ == '__main__':
    unittest.main()
