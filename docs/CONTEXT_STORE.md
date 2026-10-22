# `.dunkingsheep/` - declarative context store

Owner design discussion: #1167 (proposal), #1169 (ground truths), #1171 ("let's
build it"). Status: **approved for v0**.

## Why this exists, and why it is not memory

Dunking Sheep memory is **episodic**: every agent transcript, searchable, growing,
aging. It answers *"what happened?"*

This store is **declarative**: curated, small, current. It answers *"what is true,
and what do we do in this project?"*

> "Memory ages with time... We also need something more like a global context." - owner #1167

One is **searched**; the other is **maintained**. They must not be the same store.

## Layout

```
.dunkingsheep/
  README.md          what this store is + the front-matter schema
  ground-truth/      owner principles and history that do not age out
  facts/             measured/reproduced claims, dated, with a re-check horizon
  provisional/       working notes and hypotheses, decay fast
  history/           append-only records (incidents, decisions taken, why)
  .index.db          DERIVED cache (gitignored, rebuildable in seconds)
~/.config/dunkingsheep/context/   the GLOBAL store, same layout
```

One file per entry, Markdown, filename `YYYY-MM-DD-slug.md`.

## Front-matter

```yaml
---
class: ground-truth | fact | provisional | history
subject: poolrad-credits          # what it is about (stable key)
type: principle | decision | reference | lesson | measurement | incident
scope: global | project
authority: owner | measured | agent
stated: 2026-10-21                # when it was established
source: "web #1169"               # where it came from
recheck_after: 30d                # facts only; provisional defaults to 7d
supersedes: 2026-10-01-old-thing  # optional
superseded_by: null               # set when retired by supersession
---
```

## Lifecycle - the whole point

| class | expires? | how it changes | in the session digest |
| --- | --- | --- | --- |
| `ground-truth` | **never** | only by **supersession**, never edited in place | **always** |
| `fact` | flagged stale after `recheck_after` | re-verify and update, or supersede | when relevant |
| `provisional` | decays (default 7d) | promote it or let it die | when relevant |
| `history` | never | **append-only**; corrections are new entries | when relevant |

**A ground truth is not immutable, it is append-only.** Changing one writes a new
entry naming `supersedes:`, and the old entry stays for ever with
`superseded_by:`. The chain *is* the audit trail.

**Making a measured fact permanent to stop it going stale is forbidden.** The
2026-10-21 stale-doc failures (39 cases -> 41, 20 checks -> 23) were all `fact`
entries. Permanence would have made them wrong for ever instead of wrong for a day.

## Authority

- An **agent may propose** any entry, including `class: ground-truth`.
- Only an **owner act** promotes an entry to `class: ground-truth`.
- A ground-truth entry with `authority: agent` is **refused by the indexer**, not
  silently downgraded.
- Same rule as credits: authors propose, a reviewer accepts, self-promotion is
  never allowed.

## Digest (retrieval must be cheap and bounded)

At session start inject:

1. **All** ground truths (they are few by construction), with the **count shown**
   so drift is visible (`9 ground truths, was 8`).
2. Facts relevant to the current project, by `subject`, up to a hard byte cap.
3. Any `fact` past its `recheck_after` **as a warning line**, never as a claim.

Cap the whole digest (start: 8 KiB) and **state what was omitted** when the cap is
hit. A digest that silently truncates teaches the agent a false picture.

## The index is a cache

SQLite **FTS5** over the files, built by `context index`. Same engine the memory
service uses. **Delete it and it rebuilds; corrupt it and nothing is lost.**
The files are the source of truth, so the database choice is reversible.

Explicit non-goals: **no MySQL/Postgres server** (a daemon and a second security
surface for a few hundred documents per project), **no HTML as source** (HTML is
a rendering; an agent editing HTML is an agent editing markup around content),
**no transcript storage** (that is memory's job).

## CLI (v0)

```
dunkingsheep context init [--global]
dunkingsheep context add <file|-> --class ... --subject ... [--authority agent]
dunkingsheep context promote <slug>            # owner only; refuses otherwise
dunkingsheep context supersede <slug> <new>    # keeps the old entry, links both
dunkingsheep context retire <slug> --reason ...
dunkingsheep context get <subject|slug>
dunkingsheep context search "<query>" [--class ...] [--scope ...]
dunkingsheep context digest [--project .] [--max-bytes 8192]
dunkingsheep context check                      # schema, refusals, stale facts
dunkingsheep context serve [--port 0]           # markdown -> HTML on the fly
```

## v0 acceptance (the invariants, each with a test)

1. **A ground truth survives** a `context check` after any number of `fact`
   entries expire. It is never auto-retired.
2. **An agent-promoted ground truth is refused** by `context check` and by
   `context promote` without owner authority.
3. **Supersession preserves history**: after `supersede`, both entries exist, each
   linking the other, and `get` returns the new one with the chain.
4. **The index is disposable**: `rm .index.db && context index` reproduces
   identical `search` results.
5. **The digest is bounded and honest**: with entries above the cap, the digest is
   <= cap and names what it omitted; ground-truth count is always printed.
6. **Staleness is a warning, not a deletion**: a `fact` past `recheck_after` is
   reported by `check` and appears as a warning line in the digest, and its text
   is unchanged.

## What this is not

Not a replacement for `AGENTS.md` (that is the operating contract, read by every
agent) and not a replacement for memory (that is the evidence). It is the store
for **what is true**, so an agent does not have to rediscover it or trust a stale
copy.

## Access logging (required by owner #1235)

The owner wants the dashboard to show **how many articles, how many facts, ages of
facts, and access rates**. That last one only exists if the store records reads.

Rules:
- Every read of an entry appends `{slug, at, by}` to a **derived** `access.jsonl`
  next to the index (gitignored, same class of artifact as `.index.db`).
- The store never counts a write as an access, and never counts the digest build as
  an access of every entry (the digest reads ground truths wholesale; counting that
  would make the most-consulted article always the most-boring one).
- `context stats` prints: counts by class, age distribution (median/p90 per class),
  reads in the last 7 days, and entries never read since creation.
- Entries **never read** are the interesting number, not the read ones: an article
  nobody opens is either wrong, unknown, or in the wrong place.
