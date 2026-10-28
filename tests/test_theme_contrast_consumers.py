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
    def test_default_only_control_tokens_do_not_leak_to_variants(self):
        css = TOKENS + """
        :root { --white:#fff; --topbar-border:#eee; --border:#000; }
        :root:not([data-theme]), :root[data-theme="default"] {
          --icon-button-border:var(--border);
        }
        :root[data-theme="future"] { --bg:#fff; }
        """
        parsed = gate.theme_tokens(css)
        self.assertIn('icon-button-border', parsed['default'])
        self.assertNotIn('icon-button-border', parsed['future'])
        rules = consumers('.icon-button { border:1px solid var(--icon-button-border,var(--topbar-border)); background:var(--white); }')
        rows = usage.measure_icon_button(css, rules, gate)
        self.assertEqual(pair(rows, 'icon-button-border/own-surface')['status'], 'PASS')
        self.assertEqual(pair(rows, 'icon-button-border/own-surface', 'future')['status'], 'FAIL')
        self.assertEqual(pair(rows, 'icon-button-border/own-surface', 'future')['foreground_value'], '#eee')
        for selector in (':root:not([data-theme])',
                         ':root:not([data-theme]), :root[data-theme="future"]',
                         ':root:not([data-theme]), :root[data-theme="default"], body'):
            with self.subTest(selector=selector), self.assertRaises(ValueError):
                gate.theme_tokens(TOKENS + selector + ' { --icon-button-border:#000; }')

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

    @staticmethod
    def mixed_baseline():
        entries, rows = [], []
        for index in range(179):
            entry = dict(theme='fixture', pair=f'pair-{index}/bg',
                         foreground_value='#eee', background_value='#fff', floor=3,
                         expires_with='t192' if index < 99 else 't203',
                         reason='Exact-value design deferral',
                         evidence=[dict(source='fixture.css', selector='.panel', context=[])])
            entries.append(entry)
            rows.append(dict(entry, status='FAIL'))
        inputs = [
            dict(id='original', source_head='a'*40, input_sha256='1'*64,
                 entry_start=0, entry_count=99, expires_with='t192'),
            dict(id='new-themes', source_head='b'*40, input_sha256='2'*64,
                 adjusted_input_sha256='3'*64,
                 entry_start=99, entry_count=80, expires_with='t203'),
        ]
        return rows, dict(version=2, inputs=inputs, entries=entries)

    def test_mixed_provenance_stamps_each_input_and_expires_independently(self):
        rows, baseline = self.mixed_baseline()
        result = usage.apply_baseline(rows, baseline, ['t191'])
        self.assertEqual(len(result), 179)
        self.assertTrue(all(r['status'] == 'BASELINE-FAIL' for r in result))
        for row in result[:99]:
            self.assertEqual(row['baseline']['source_head'], 'a'*40)
            self.assertEqual(row['baseline']['input_sha256'], '1'*64)
            self.assertNotIn('adjusted_input_sha256', row['baseline'])
        for row in result[99:]:
            self.assertEqual(row['baseline']['source_head'], 'b'*40)
            self.assertEqual(row['baseline']['input_sha256'], '2'*64)
            self.assertEqual(row['baseline']['adjusted_input_sha256'], '3'*64)
        expired = usage.apply_baseline(rows, baseline, ['t203'])
        self.assertTrue(all(r['status'] == 'BASELINE-FAIL' for r in expired[:99]))
        self.assertTrue(all(r['status'] == 'FAIL' and r['baseline']['expired']
                            for r in expired[99:]))
        legacy_expired = usage.apply_baseline(rows, baseline, ['t192'])
        self.assertTrue(all(r['status'] == 'FAIL' and r['baseline']['expired']
                            for r in legacy_expired[:99]))
        self.assertTrue(all(r['status'] == 'BASELINE-FAIL' for r in legacy_expired[99:]))
        # Input data and measured rows stay immutable.
        self.assertNotIn('baseline', rows[0])
        self.assertNotIn('source_head', baseline['entries'][99])

    def test_mixed_provenance_rejects_count_expiry_and_identity_drift(self):
        rows, baseline = self.mixed_baseline()
        mutations = [
            ('entry_count', 79), ('entry_start', 98), ('entry_start', 100),
            ('expires_with', 't191'), ('source_head', 'not-a-head'),
            ('input_sha256', 'not-a-hash'), ('adjusted_input_sha256', ''),
            ('id', 'original'),
        ]
        for key, value in mutations:
            with self.subTest(key=key, value=value):
                broken = json.loads(json.dumps(baseline))
                broken['inputs'][1][key] = value
                with self.assertRaises(ValueError):
                    usage.apply_baseline(rows, broken)
        broken = json.loads(json.dumps(baseline))
        broken['entries'][99]['expires_with'] = 't191'
        with self.assertRaises(ValueError):
            usage.apply_baseline(rows, broken)
        broken = dict(baseline, inputs=baseline['inputs'][:1])
        with self.assertRaises(ValueError):
            usage.apply_baseline(rows, broken)

    def test_repository_baseline_input_counts_and_expiry_match_entries(self):
        baseline = json.loads(usage.DEFAULT_BASELINE.read_text())
        self.assertEqual(baseline['version'], 2)
        self.assertEqual([(s['entry_count'], s['expires_with']) for s in baseline['inputs']],
                         [(99, 't192')])
        self.assertEqual(len(usage.baseline_provenance(baseline)), len(baseline['entries']))
        for source in baseline['inputs']:
            entries = baseline['entries'][source['entry_start']:
                                          source['entry_start'] + source['entry_count']]
            self.assertEqual(len(entries), source['entry_count'])
            self.assertEqual({entry['expires_with'] for entry in entries},
                             {source['expires_with']})

    def test_named_icon_border_resolves_actual_declaration_not_proposal(self):
        css = TOKENS + ':root {--topbar-border:#e4e9ed;--border-strong:#45475a;--white:white;}'
        actual = consumers('.icon-button {border:1px solid var(--topbar-border);background:var(--white);}')
        row = pair(gate.measure_all(css, actual), 'icon-button-border/own-surface')
        self.assertEqual(row['status'], 'FAIL')
        self.assertAlmostEqual(row['ratio'], 1.2225475, places=6)
        self.assertEqual(row['border_expression'], '1px solid var(--topbar-border)')
        entry = {field: row[field] for field in usage.BASELINE_FIELDS}
        entry.update(evidence=row['evidence'], expires_with='t193', reason='Invalid attempted control deferral')
        baseline = dict(version=1, source_head='0'*40, entries=[entry])
        self.assertEqual(usage.apply_baseline([row], baseline)[0]['status'], 'FAIL')
        self.assertEqual(row['remediation_task'], 't193')
        proposal = consumers('.icon-button {border:1px solid var(--border-strong);background:var(--white);}')
        row = pair(gate.measure_all(css, proposal), 'icon-button-border/own-surface')
        self.assertEqual(row['status'], 'PASS')
        self.assertAlmostEqual(row['ratio'], 9.1226047, places=6)

    def test_named_icon_proposed_alias_four_theme_calibration(self):
        css = TOKENS + ':root {--border-strong:#45475a;--white:white;}'
        for name, border, surface in [('crt','#5b8b68','#c1f4c7'),('nostromo','#b0a16f','#f5edc9'),('2001','#595b63','#202126')]:
            css += f':root[data-theme="{name}"] {{ --border-strong:{border};--white:{surface};}}'
        rules = consumers('.icon-button {border:1px solid var(--border-strong);background:var(--white);}')
        rows = gate.measure_all(css, rules)
        for theme, expected, status in [('default',9.12,'PASS'),('crt',3.19,'MARGINAL'),('nostromo',2.18,'FAIL'),('2001',2.37,'FAIL')]:
            row = pair(rows, 'icon-button-border/own-surface', theme)
            self.assertAlmostEqual(row['ratio'], expected, places=2)
            self.assertEqual(row['status'], status)


    def test_base_icon_token_and_fallback_branches(self):
        rules = consumers('.icon-button {border:1px solid var(--icon-button-border,var(--topbar-border));background:var(--white);}')
        for defined, expected, status in ((False, '#eee', 'FAIL'), (True, '#000', 'PASS')):
            with self.subTest(defined=defined):
                css = TOKENS + ':root {--topbar-border:#eee;--white:#fff;}'
                if defined: css += ':root {--icon-button-border:#000;}'
                row = pair(gate.measure_all(css, rules), 'icon-button-border/own-surface')
                self.assertEqual(row['foreground_value'], expected)
                self.assertEqual(row['background_value'], '#fff')
                self.assertEqual(row['status'], status)
                self.assertEqual(row['border_evidence']['selector'], '.icon-button')

    def test_panel_icon_token_and_fallback_use_actual_panel_surface(self):
        rules = consumers("""
          .dash-root {--dash-panel-2:var(--surface-raised);--dash-border:var(--border);}
          .icon-button {border:1px solid var(--topbar-border);background:var(--white);}
          .dash-root .settings-modal .icon-button {
            border-color:var(--icon-button-panel-border,var(--dash-border));
            background:var(--dash-panel-2);
          }
        """)
        for defined, expected, status in ((False, '#111', 'FAIL'), (True, '#fff', 'PASS')):
            with self.subTest(defined=defined):
                css = TOKENS + ':root {--topbar-border:#000;--white:#fff;--surface-raised:#000;--border:#111;}'
                if defined: css += ':root {--icon-button-panel-border:#fff;}'
                rows = gate.measure_all(css, rules)
                row = pair(rows, 'icon-button-panel-border/own-surface')
                self.assertEqual(row['foreground_value'], expected)
                self.assertEqual(row['background_value'], '#000')
                self.assertEqual(row['status'], status)
                self.assertEqual(row['border_evidence']['selector'], '.dash-root .settings-modal .icon-button')
                self.assertEqual(row['surface_expression'], 'var(--dash-panel-2)')
                self.assertEqual(pair(rows, 'icon-button-border/own-surface')['background_value'], '#fff')

    def test_defined_icon_tokens_do_not_require_inactive_fallbacks(self):
        css = TOKENS + ':root {--white:#fff;--surface-raised:#000;--icon-button-border:#000;--icon-button-panel-border:#fff;}'
        rules = consumers("""
          .dash-root {--dash-panel-2:var(--surface-raised);}
          .icon-button {border:1px solid var(--icon-button-border,var(--topbar-border));background:var(--white);}
          .dash-root .settings-modal .icon-button {border-color:var(--icon-button-panel-border,var(--dash-border));background:var(--dash-panel-2);}
        """)
        rows = gate.measure_all(css, rules)
        for name in ('icon-button-border/own-surface', 'icon-button-panel-border/own-surface'):
            self.assertEqual(pair(rows, name)['status'], 'PASS')

    def test_panel_specificity_and_important_choose_actual_winning_border(self):
        css = TOKENS + ':root {--white:#fff;--surface-raised:#000;}'
        for panel_important, expected in (('', '#000'), ('!important', '#fff')):
            rules = consumers("""
              .dash-root .settings-modal .icon-button {border-color:#fff %s;background:var(--surface-raised);}
              .icon-button {border:1px solid #000 !important;background:var(--white);}
            """ % panel_important)
            row = pair(gate.measure_all(css, rules), 'icon-button-panel-border/own-surface')
            self.assertEqual(row['foreground_value'], expected)
            self.assertEqual(row['background_value'], '#000')

    def test_named_panel_failure_cannot_be_baselined(self):
        css = TOKENS + ':root {--white:#fff;--surface-raised:#000;}'
        rules = consumers("""
          .icon-button {border:1px solid #000;background:var(--white);}
          .dash-root .settings-modal .icon-button {border-color:#111;background:var(--surface-raised);}
        """)
        row = pair(gate.measure_all(css, rules), 'icon-button-panel-border/own-surface')
        entry = {field: row[field] for field in usage.BASELINE_FIELDS}
        entry.update(evidence=row['evidence'], expires_with='t193', reason='Invalid named-panel deferral')
        baseline = dict(version=1, source_head='0'*40, entries=[entry])
        self.assertEqual(usage.apply_baseline([row], baseline)[0]['status'], 'FAIL')

    def test_attach_named_rows_use_actual_own_surface_and_override(self):
        css = TOKENS + ':root {--surface-raised:#000;--control-boundary:#fff;--muted:#fff;}'
        rules = consumers("""
          .dash-root {--dash-panel-2:var(--surface-raised);--dash-muted:var(--muted);}
          .composer {background:#fff;}
          .composer > .attach {border:1px solid var(--control-boundary);background:var(--surface-raised);color:var(--muted);}
          .dash-root .composer > .attach {background:var(--dash-panel-2);color:#111;}
        """)
        rows = gate.measure_all(css, rules)
        self.assertEqual(pair(rows, 'attach-base-text/own-surface')['status'], 'PASS')
        text = pair(rows, 'attach-text/own-surface')
        self.assertEqual(text['status'], 'FAIL')
        self.assertEqual(text['foreground_value'], '#111')
        self.assertEqual(text['background_value'], '#000')
        self.assertEqual(text['foreground_evidence']['selector'], '.dash-root .composer > .attach')
        self.assertEqual(pair(rows, 'attach-border/own-surface')['status'], 'PASS')

    def test_attach_surface_change_fails_boundary_even_when_token_passes_elsewhere(self):
        css = TOKENS + ':root {--surface-raised:#000;--control-boundary:#fff;--muted:#000;}'
        rules = consumers("""
          .composer > .attach {border:1px solid var(--control-boundary);background:var(--surface-raised);color:#fff;}
          .dash-root .composer > .attach {background:#fff;color:var(--muted);}
        """)
        rows = gate.measure_all(css, rules)
        self.assertEqual(pair(rows, 'attach-base-border/own-surface')['status'], 'PASS')
        boundary = pair(rows, 'attach-border/own-surface')
        self.assertEqual(boundary['foreground'], 'control-boundary')
        self.assertEqual(boundary['ratio'], 1)
        self.assertEqual(boundary['status'], 'FAIL')
        self.assertEqual(pair(rows, 'attach-text/own-surface')['status'], 'PASS')
        entry = {field: boundary[field] for field in usage.BASELINE_FIELDS}
        entry.update(evidence=boundary['evidence'], expires_with='t238', reason='Invalid Attach waiver')
        baseline = dict(version=1, source_head='0'*40, entries=[entry])
        self.assertEqual(usage.apply_baseline([boundary], baseline)[0]['status'], 'FAIL')

    def test_attach_all_themes_and_alpha_fail_closed(self):
        css = TOKENS + ':root {--surface-raised:#000;--control-boundary:#fff;--muted:#fff;}'
        css += ':root[data-theme="dim"] {--control-boundary:#111;--muted:#ffffff00;}'
        rules = consumers("""
          .composer > .attach {border:1px solid var(--control-boundary);background:var(--surface-raised);color:var(--muted);}
          .dash-root .composer > .attach {background:var(--surface-raised);}
        """)
        rows = gate.measure_all(css, rules)
        named = [r for r in rows if r.get('control', '').endswith('.attach')]
        self.assertEqual(len(named), 8)
        for theme, status in [('default', 'PASS'), ('dim', 'FAIL')]:
            for name in ['attach-base-border', 'attach-base-text', 'attach-border', 'attach-text']:
                self.assertEqual(pair(rows, name+'/own-surface', theme)['status'], status)
        transparent = gate.measure_all(css+':root {--surface-raised:#0000;}', rules)
        row = pair(transparent, 'attach-text/own-surface')
        self.assertEqual(row['status'], 'FAIL')
        self.assertIn('opaque', row['error'])



if __name__ == '__main__': unittest.main()
