# Static theme contrast gate

Run python3 tools/theme_contrast.py --json. The original four palette pairs
and their calibration remain. The CLI also parses web/src/style.css and
web/src/dash.css using pinned PostCSS 8.5.29, without changing CSS.
--consumer-css FILE is repeatable for isolated fixtures.

For each theme, enumerate every token whose name contains ink or fg against
every token containing surface or starting with bg (4.5:1), and every border
token against those surfaces (3:1). Names can be in multiple sets. The original
ink/bg floor stays 7:1. Selected var fallbacks and alias chains, including
dashboard aliases, identify referenced pairs. Rules split across files join
only for identical selector text and conditional context. Reports include
source/line/selector evidence.

Below-floor referenced pairs FAIL; below-floor unused combinations WARN.
Passing ratios within 0.3 of the floor are MARGINAL; others PASS. Unsupported
referenced colors FAIL, unsupported unused combinations WARN. Missing consumer
variables, cycles and ambiguous local color overrides fail closed. Opaque
backgrounds and hex colors are required by this static color model.

The measure() Python function retains the original palette calibration API;
measure_all() and the CLI perform the extended gate.

The explicit inherited-surface cases ops-reference-ink/bg at 4.5 and
ops-reference-border/bg at 3.0 remain mandatory even without a background on
the same rule. One named temporary exception, legacy-ops-reference-border,
matches only exact foreground #405c64 on Default, CRT and Nostromo, expiring
with t189. It prints KNOWN-FAIL and expiry, never PASS. Changed failing colors
are not exempt; repaired passing colors need no exception. Supply
--completed-task t189 to enforce expiry; remove the obsolete exception when
the design repair lands.

## Design-triaged baseline

The first widened measurement of main ed8b29c found 49 Default and 50 CRT
referenced FAIL rows, plus one reference-border KNOWN-FAIL per theme.
Design supplied all99 entries in tools/theme_contrast_baseline.json:
55 fix-in-theme deferrals and44 scoped decorative-separator deferrals, all
expiring with t192. These are temporary BASELINE-FAIL records, not passing
contrast or final rendered waiver acceptance. Reasons, decisions, colors and
floors are preserved from design triage; source paths are repository-relative.

The CLI loads that baseline by default. Use --baseline FILE for a reviewed
replacement or --no-baseline for the raw report. Entries have this schema:

~~~json
{
  "version": 1,
  "source_head": "<40-character measured Git SHA>",
  "entries": [{
    "theme": "<theme ID>",
    "pair": "<foreground/background>",
    "foreground_value": "<exact resolved color>",
    "background_value": "<exact resolved color>",
    "floor": 4.5,
    "expires_with": "t192",
    "reason": "<design triage and planned repair>",
    "evidence": [{
      "source": "web/src/style.css",
      "selector": ".panel",
      "context": []
    }]
  }]
}
~~~

Exact existing failures report BASELINE-FAIL with reason/expiry, not PASS.
New pairs, changed colors/floors, changed consumer selectors/files/conditions,
unresolved colors and expired entries FAIL. Line-number movement alone is allowed.
Supply completed expiry tasks with repeatable --completed-task tNNN.
Task state is explicit input so the tool stays deterministic and never queries
the daemon. A baseline cannot revive an expired named exception. Gate callers
must supply completed-task inputs and remove obsolete entries as repairs land.
Final independent review remains required.

Exit 0 means no unexcepted FAIL; 1 means contrast failure; 2 means invalid
input/parser failure. JSON enumerates all unused combinations as well.

## Limits

This is static pair coverage, not whole-page accessibility certification.
It does not infer DOM ancestor surfaces, selector equivalence/specificity across
different selectors, image/gradient pixels, paint occlusion or actual fonts.
Matched references are conservative, not proof of which rule wins in a DOM.
Rendered-surface checks and screenshot review remain required under t160.
A warning does not certify a token as safe for future use.
