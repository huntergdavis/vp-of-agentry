# Free models are the default worker tier (owner #1202, 2026-10-21)

> "let's make it our default to slow usage on codex and claude and ds4.1-flash by
> heavily having them delegate to all these free models! That should be their
> default mode now, that they delegate heavily"

OpenRouter is live on this host with a **$1 hard limit**. That limit exists so we
can never accidentally spend: **only zero-cost models may be called.**

## The rule

1. **Paid lanes delegate by default.** Claude, codex and ds4.1-flash lanes are for
   judgement, evidence and acceptance. Mechanical, bounded, checkable work goes to
   a free model first.
2. **Only free models.** A call is legitimate only if the model's catalog entry is
   `:free` (or otherwise priced 0 in/out). Never call a paid model to "save time" -
   the $1 limit is a guard rail, not a budget.
3. **A lane accepts whatever a free model produces.** Free models never write
   accounting, ledger, credit, caveat or classifier files, never get pane control,
   and always run headless and `nice`d.
4. **Every delegated task states its acceptance check before it runs** - the same
   pre-registration discipline as the device experiments. "Did the model do it"
   is not a check; "does the output name the bytes it used" is.

## What to delegate (proven shapes)

- **Independent re-derivation**: read raw bytes + an evidence doc, report
  AGREE/DISAGREE with the specific reason. Static only - it cannot run the
  differential harness, so it catches doc-vs-bytes drift, not behaviour.
- **Lookup and triage**: propose a symbol mapping, classify a never-equal site,
  extract a claim-to-check table, find a missing checker row.
- **Drafting with immediate review**: doc sections, summaries, checklists.

## What never to delegate

- Anything whose wrong answer is absorbed silently into a record.
- Anything requiring execution evidence (differential runs, device captures).
- Anything touching credentials, accounting, or pane control.

## Measurement (the point of the exercise)

For each workstream: **items in / accepted without rework / accepted after rework /
rejected / failed**. A model that errors is counted as failed, not as zero work.
The target the owner set is "half our work"; the number decides whether that is
true, per workstream, and it gets reported as a number, not an impression.

## Inventory at the time of writing (verify, do not trust)

- `pi auth check --provider openrouter` -> **ready**
- **17** `:free` entries visible in `pi --list-models` out of 396 openrouter rows
- `typesafe/jev-router` is present (chat tier); the *classifier* JEV route is not
  yet confirmed here - check `pi --list-models | grep -i jev` before claiming it
