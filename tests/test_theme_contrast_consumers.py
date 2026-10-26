import contextlib
import io
import json
from pathlib import Path
import tempfile
import unittest
from tools import theme_contrast as gate
from tools import theme_contrast_consumers as usage


TOKENS = '''
:root { --bg:#fff; --surface:#fff; --ink:#000; --muted:#000;
--accent:#000; --accent-contrast:#fff; --ops-reference-ink:#000;
--ops-reference-border:#000; --alias-ink:var(--ink); --edge-border:#000; }
'''


def consumers(css):
    return usage.parse_consumers([dict(source='fixture.css', css=css)])


def pair(rows, name, theme='default'):
    return next(r for r in rows if r['theme'] == theme and r['pair'] == name)


class ConsumerContrastTests(unittest.TestCase):
    def test_pale_alias_consumed_by_rule_fails_while_palette_passes(self):
        css = TOKENS + ':root[data-theme="fake"] { --alias-ink:#eee; }'
        rows = gate.measure_all(css, consumers('.panel { color:var(--alias-ink); background:var(--surface); }'))
        row = pair(rows, 'alias-ink/surface', 'fake')
        self.assertEqual(row['status'], 'FAIL')
        self.assertTrue(row['referenced'])
        self.assertEqual(row['evidence'][0]['selector'], '.panel')
        self.assertTrue(all(r['status'] == 'PASS' for r in gate.measure(css)))
        self.assertGreaterEqual(row['suggestion_ratio'], 4.5)

    def test_unreferenced_bad_combination_warns_not_fails(self):
        css = TOKENS + ':root { --unused-ink:#eee; }'
        rows = gate.measure_all(css, consumers('.panel { color:var(--ink); background:var(--surface); }'))
        row = pair(rows, 'unused-ink/surface')
        self.assertEqual(row['status'], 'WARN')
        self.assertFalse(row['referenced'])
        self.assertFalse(any(r['status'] == 'FAIL' for r in rows))

    def test_same_selector_split_rules_and_component_alias_chains(self):
        css = TOKENS + ':root { --alias-ink:#eee; }'
        rules = '.dash-root { --dash-fg:var(--alias-ink); --dash-bg:var(--surface); }'
        rules += '.panel { color:var(--dash-fg); } .panel { background:var(--dash-bg); }'
        row = pair(gate.measure_all(css, consumers(rules)), 'alias-ink/surface')
        self.assertEqual(row['status'], 'FAIL')
        self.assertEqual(len(row['evidence']), 2)

    def test_rule_local_alias_and_active_fallback(self):
        rules = '.panel { --local-fg:#eee; color:var(--absent,var(--local-fg)); background:var(--surface); }'
        rows = gate.measure_all(TOKENS, consumers(rules))
        self.assertEqual(pair(rows, 'local-fg/surface')['status'], 'FAIL')
        rules = '.panel { color:var(--ink,var(--missing-fg)); background:var(--surface); }'
        rows = gate.measure_all(TOKENS, consumers(rules))
        self.assertFalse(any(r['status'] == 'FAIL' for r in rows))

    def test_different_conditions_do_not_make_a_referenced_pair(self):
        css = TOKENS + ':root { --alias-ink:#eee; }'
        rules = '@media print { .panel {color:var(--alias-ink);} } .panel {background:var(--surface);}'
        row = pair(gate.measure_all(css, consumers(rules)), 'alias-ink/surface')
        self.assertEqual(row['status'], 'WARN')
        self.assertFalse(row['referenced'])

    def test_missing_cyclic_and_ambiguous_local_aliases_fail_closed(self):
        for css in ('.panel { color:var(--missing-ink); background:var(--surface); }',
                    '.panel { --a:var(--b); --b:var(--a); color:var(--a); }',
                    '.a {--local-ink:#eee;color:var(--local-ink);} .b {--local-ink:#000;color:var(--local-ink);}'):
            with self.subTest(css=css), self.assertRaises(ValueError):
                gate.measure_all(TOKENS, consumers(css))

    def test_reference_cases_gate_without_same_rule_background(self):
        css = TOKENS + ':root[data-theme="2001"] { --ops-reference-ink:#cfe0dc; }'
        rows = gate.measure_all(css, consumers('.ops-reference { color:var(--ops-reference-ink); }'))
        row = pair(rows, 'ops-reference-ink/bg', '2001')
        self.assertEqual(row['status'], 'FAIL')
        self.assertTrue(row['named_case'])
        fixed = gate.measure_all(css + ':root[data-theme="2001"] { --ops-reference-ink:var(--ink); }', consumers(''))
        self.assertEqual(pair(fixed, 'ops-reference-ink/bg', '2001')['status'], 'PASS')

    def test_named_border_known_failure_expiry_and_no_broad_allowlist(self):
        css = TOKENS + ':root {--bg:#11111b;--ink:#fff;--muted:#fff;--accent:#fff;--accent-contrast:#000;--ops-reference-ink:#fff;--ops-reference-border:#405c64;}'
        css += ':root[data-theme="crt"] {} :root[data-theme="nostromo"] {} :root[data-theme="new"] {}'
        rows = gate.measure_all(css, consumers(''))
        for theme in ('default', 'crt', 'nostromo'):
            row = pair(rows, 'ops-reference-border/bg', theme)
            self.assertEqual(row['status'], 'KNOWN-FAIL')
            self.assertEqual(row['known_fail']['expires_with'], 't189')
        self.assertEqual(pair(rows, 'ops-reference-border/bg', 'new')['status'], 'FAIL')
        expired = gate.measure_all(css, consumers(''), expired_known_fails=('t189',))
        self.assertEqual(pair(expired, 'ops-reference-border/bg')['status'], 'FAIL')
        self.assertTrue(pair(expired, 'ops-reference-border/bg')['known_fail']['expired'])
        changed = gate.measure_all(css + ':root {--ops-reference-border:#222;}', consumers(''))
        self.assertEqual(pair(changed, 'ops-reference-border/bg')['status'], 'FAIL')

    def test_marginal_and_border_floor(self):
        css = TOKENS + ':root {--alias-ink:#767676;--edge-border:#999;}'
        rows = gate.measure_all(css, consumers('.panel {color:var(--alias-ink);background:var(--surface);border:1px solid var(--edge-border);}'))
        self.assertEqual(pair(rows, 'alias-ink/surface')['status'], 'MARGINAL')
        row = pair(rows, 'edge-border/surface')
        self.assertEqual(row['floor'], 3)
        self.assertEqual(row['status'], 'FAIL')

    def test_cli_warn_exit_zero_and_referenced_fail_exit_one(self):
        with tempfile.TemporaryDirectory() as temp:
            token = Path(temp) / 'tokens.css'; rules = Path(temp) / 'rules.css'
            token.write_text(TOKENS + ':root {--alias-ink:#eee;}'); rules.write_text('')
            with contextlib.redirect_stdout(io.StringIO()) as output:
                code = gate.main([str(token), '--consumer-css', str(rules), '--json'])
            self.assertEqual(code, 0)
            self.assertEqual(pair(json.loads(output.getvalue())['pairs'], 'alias-ink/surface')['status'], 'WARN')
            rules.write_text('.panel {color:var(--alias-ink);background:var(--surface);}')
            with contextlib.redirect_stdout(io.StringIO()):
                self.assertEqual(gate.main([str(token), '--consumer-css', str(rules)]), 1)


    def test_baseline_only_defers_exact_old_pair_until_task_expiry(self):
        rules = consumers('.panel {color:var(--alias-ink);background:var(--surface);}')
        css = TOKENS + ':root {--alias-ink:#eee;}'
        rows = gate.measure_all(css, rules)
        failing = pair(rows, 'alias-ink/surface')
        entry = {field: failing[field] for field in usage.BASELINE_FIELDS}
        entry['evidence'] = failing['evidence']
        entry.update(expires_with='t190', reason='Design triage fixture; repair tracked separately')
        baseline = dict(version=1, source_head='0'*40, entries=[entry])
        self.assertEqual(pair(usage.apply_baseline(rows, baseline), 'alias-ink/surface')['status'], 'BASELINE-FAIL')
        self.assertEqual(pair(usage.apply_baseline(rows, baseline, ['t190']), 'alias-ink/surface')['status'], 'FAIL')
        changed = gate.measure_all(css + ':root {--alias-ink:#ddd;}', rules)
        self.assertEqual(pair(usage.apply_baseline(changed, baseline), 'alias-ink/surface')['status'], 'FAIL')
        different_consumer = gate.measure_all(css, consumers('.new-control {color:var(--alias-ink);background:var(--surface);}'))
        changed_scope = pair(usage.apply_baseline(different_consumer, baseline), 'alias-ink/surface')
        self.assertEqual(changed_scope['status'], 'FAIL')
        self.assertTrue(changed_scope['baseline']['scope_changed'])
        new_pair = gate.measure_all(css + ':root {--new-ink:#eee;}', consumers('.panel {color:var(--new-ink);background:var(--surface);}'))
        self.assertEqual(pair(usage.apply_baseline(new_pair, baseline), 'new-ink/surface')['status'], 'FAIL')
        for bad in (dict(entry, expires_with=''), {k:v for k,v in entry.items() if k!='reason'}):
            with self.assertRaises(ValueError):
                usage.apply_baseline(rows, dict(baseline, entries=[bad]))


if __name__ == '__main__': unittest.main()
