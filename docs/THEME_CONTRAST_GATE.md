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

## Named icon-button boundaries

Two mandatory 3:1 checks resolve actual unconditional declarations:

- icon-button-border/own-surface: .icon-button border against its background.
- icon-button-panel-border/own-surface: .dash-root .settings-modal .icon-button
  against its own background, inheriting base properties before applying that
  known higher-specificity override. !important precedence is retained.

Default-only tokens may use the exact combined scope
:root:not([data-theme]), :root[data-theme="default"]. These values apply only
to Default; other themes retain generic-root inheritance and their own fallback
branches. Other complex token selectors still fail closed.

Both use the existing nested var() resolver. Defined primary tokens win;
missing primaries select their fallbacks. Aliases such as --white and
--dash-panel-2 resolve to the actual surfaces. Reports include the winning
border/background expressions and source selector, file and line. Tests cover
both primary/fallback branches, inactive missing fallbacks and the explicit
base/panel precedence model. Other selectors and conditional overrides require
rendered analysis; this is not a general DOM cascade implementation.

Measured main ee43ece uses topbar-border/white for the base: Default1.2225 and
CRT1.0085 FAIL. Its panel uses dash-border/dash-panel-2: Default1.3046 and
CRT2.0534 FAIL. Dedicated task t193 repairs these two contexts through separate
base and panel border tokens. Neither named control can receive a baseline
exception. Do not merge the widened default gate while current-main named
control failures remain. Actual rendered compositing and occlusion still
require the rendered-surface gate. The proposal fixture separately proves
border-strong/white ratios9.12/3.19/2.18/2.37; it does not imply a shipped remap.

## Design-triaged baseline

The first widened measurement of main ed8b29c found 49 Default and 50 CRT
referenced FAIL rows, plus one reference-border KNOWN-FAIL per theme.
Design supplied all99 entries in tools/theme_contrast_baseline.json:
57 fix-in-theme deferrals and42 scoped decorative-separator deferrals, all
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
different selectors beyond the two explicit icon contexts above, image/gradient
pixels, paint occlusion or actual fonts.
Matched references are conservative, not proof of which rule wins in a DOM.
Rendered-surface checks and screenshot review remain required under t160.
A warning does not certify a token as safe for future use.
