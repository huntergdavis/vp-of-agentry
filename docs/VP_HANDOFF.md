# VP handoff and restart

## Start another model or harness

1. Stop or park the previous **VP agent pane** so only one agent handles owner messages. Leave the web, Telegram, metrics, and host-watch services running.
2. Open a new agent pane in Herdr with your chosen harness (Codex, Claude, OpenCode, or another model). Set its working directory to `/home/hunter/workspace/vp-of-agentry` and a clear tab label such as `VP of Agentry`. A new pane is automatically discovered by the web desk; update ignored `channels.json` if you want the stable `vp` channel to point to a different tab label.
3. Paste the takeover prompt below. The new agent should read this repository, the VP inbox, and Dunking Sheep's existing auto-dunks before replying. Check `./vpctl status`, `./telegram-bridge status`, `python3 host_watch.py --status`, `df -h /tmp`, `df -i /tmp`, and `systemctl --user --failed` without opening or printing credential files.
4. Open the VP web desk and refresh. Its channel roster is rebuilt from Dunking Sheep live panes on page load and every 12 seconds. Confirm the new VP pane is active and the old pane is idle or absent. Retarget the existing hourly VP Dunking Sheep reminder (`d50` on this host; find it by name if its ID changes) to the new VP pane. Post a short `./vpctl brief --channel vp` and confirm `./telegram-bridge status` advanced `last_brief_id`. The local bridge forwards the same web brief to Telegram; do not send a duplicate Telegram update.

Takeover prompt:

> You are the owner's VP of Agentry. Your workspace is `/home/hunter/workspace/vp-of-agentry`. Read `AGENTS.md`, `README.md`, and `docs/VP_HANDOFF.md`; then pair with Dunking Sheep: read the VP inbox, inspect live panes, and review existing auto-dunks. Dunking Sheep is the beating heart of this system; retarget its hourly VP reminder to your pane, put recurring VP actions into direct auto-dunks and recurring instructions for other agents into scheduled inbox delivery, and avoid duplicate prompts. At takeover and on every VP check-in, inspect `python3 host_watch.py --status`, `df -h /tmp`, `df -i /tmp`, `systemctl --user --failed`, and the VP/Telegram/metrics/watch services; investigate stale processes or temporary files when readings warrant it, preserving unpublished work. Continue outstanding agent and project work. Publish one owner update through `./vpctl brief --channel vp`; the local `vp-telegram.service` bridge forwards it from the web desk to the paired Telegram chat. Verify `./telegram-bridge status` advanced `last_brief_id`; do not send a duplicate Telegram message or expose the bot token. Keep secrets and machine-specific private data out of Git. Before debugging, run `dunkingsheep memory recall "<query>"` and cite reused findings. Use fresh Los Angeles timestamps per `AGENTS.md`.

## Local services and state

| What | Check | Restart if needed |
| --- | --- | --- |
| VP web desk | `./vpctl status` | `systemctl --user restart vp-of-agentry.service` |
| Telegram bridge | `./telegram-bridge status` | `systemctl --user restart vp-telegram.service` |
| Operations collector | `./opsctl summary` | `systemctl --user start vp-ops-metrics.service`; timer: `vp-ops-metrics.timer` |
| Host watch | `python3 host_watch.py --status` | `systemctl --user start vp-host-watch.service`; timer: `vp-host-watch.timer` |
| Agent panes/inbox | `dunkingsheep panes` and `dunkingsheep inbox read` | use Herdr/Dunking Sheep to relaunch the agent; do not start a second web or Telegram poller |

The private data under `data/`, ignored `channels.json`, and local Dunking Sheep/Herdr state are needed for continuity on this host. They are not in Git. Keep their permissions private, do not print their contents into logs, and back them up through an owner-approved private path if moving machines. On a fresh host, run `./run.sh`, then the install scripts described in [README.md](../README.md), set up Telegram locally, and restore private state only through a secure channel.

## Current priorities and checks (state at 2026-10-20 06:44 PDT)

**Poolrad: 244 strict / 290 identities** of an 815 upper bound (`93ff` main line, latest merged `9231b5d5`). Four bodies were credited in one night (`RES_0464_2595`, `U3B9_048F`, `U3CE_014E`, `RES_00BA_1693`). The cheap queue is **closed with evidence**: every remaining candidate costs **>=132 B per unlocked row**, with the sub-100 ones failing for named reasons (identity not establishable for the `0x7F` pair; a hop into the declined `0C77` chain for `13D7`; a BIOS-thunk boundary for `03C6_0105`). The author lane is **on hold with nothing assigned**; more credit is a funding decision with a chain ceiling quoted in advance.

**Two decisions belong to the owner and neither has moved:**
1. **Crackdown:** accept **~18.5 FPS** at 75% internal and ~19-20 at 50%, or fund a **short feasibility step** (not the multi-week project) to establish what work can actually be removed or parallelised. 30 FPS needs roughly **-39% GPU and -34% CPU simultaneously**; no one has shown that work exists. The 8-page invalidation experiment was **demoted to UNCONFIRMED / NOT ADOPTED** after two pairs came back inside their own drift, under a pass/fail rule pre-registered before the second pair ran.
2. **Poolrad:** fund a chain (cheapest credited option `16EC` at **~131 B/row**, one-hop ceiling to be re-derived before any body is written) or rest at 244/290.

**Quotas:** Claude is **parked at 5% left** until its reset on the 22nd; `d57` re-enables it. Codex is at **42%** and carries the Poolrad lane.

**Dashboard:** the live roster refreshes automatically; Operations shows fixed subscriptions and separate OpenCode model-cost estimate. Check source age before quoting a metric.

**Host:** inspect `/tmp`, free space, stuck processes, and old checkouts. Preserve unpublished branches and files before removing a checkout.

## Recurring work in Dunking Sheep

Review the current dunk list at takeover. Keep one recurring VP self-reminder for host health, project state, agent deliverables, quota, and a concise owner brief. Schedule repeated work prompts to other agents through their durable inbox when available, with a cadence and stop condition. Prefer `only_when="idle"` and `skip_if_unconsumed=true`; remove a dunk when its task is complete. The service timers sample health and metrics, while Dunking Sheep turns those observations into agent action across harness restarts.

When sending any agent a durable `inbox_send`, Dunking Sheep also sends its own short direct nudge to check the inbox. Do not add a separate `send_text` or other direct prompt for that same item. Check the inbox message ID and read/ack state instead. This avoids duplicate work and interrupted inputs.

## Owner brief format (owner directive, VP web #1021, 2026-07-20)

Every brief published with `./vpctl brief --channel vp` uses **`*****` section separators**, each followed by a section name under the rule, so the owner can parse between blocks in the web desk and Telegram:

```
*****
SECTION NAME
*****
content
```

Sections he named: **DECISIONS I NEED**, **POOLRAD**, **CRACKDOWN**, **DUNKIES / OPS**, and a **FORMAT** note when the format itself changes. Open with the decision list when anything is waiting on him - that is the block he reads first.

## Evidence discipline (learned 2026-10-20, one-night tally)

These are VP-side failures, not lane failures. Each cost a cycle and each is now a rule.

- **A number is not the quantity in the sentence.** Seven claims had to be withdrawn in one night, all the same move: reading a measurement as if it established the mechanism named in the prose. Examples: scheduled CPU time minus sparse GPU intervals read as critical-path slack; a 606,042 ns aggregate probe gap compared against a ~1 ms/frame effect; per-thread counters read as thread locality when they are attaching-thread lineages; a stack-attributed bucket sum called "optimisable"; a hand-remembered "no family above 1.2 ms" contradicted by the lane's own aggregates. Check the artifact, not the summary - including this file.
- **Pre-register the decision rule before the result.** For the 8-page invalidation experiment the pass/fail rule (favourable sign in both arms and effect larger than each arm's drift) was written to `PAIR2-DECISION-RULE.json` before the second pair produced numbers, and the second pair then failed it. Run without that, the same data would have been reported as a win.
- **An operator's own recurring prompt is a source of stale work.** A `dunkingsheep` reminder still carrying a closed priority list made a lane re-derive already-merged PRs twice. Rewrite or retire the prompt when the list closes; a recurring instruction is code and needs the same review.
- **Your prose about an agent's numbers is less reliable than their artifacts.** After this night the standing rule is: when summarising a lane's result for the owner, quote the artifact's own wording, or say that you are paraphrasing.
- **Stated limits belong in the document carrying the claim.** Masked ranges with byte counts, coverage gaps with named unexercised paths, lineage-vs-thread attribution, unknown missing-event counts, and model-vs-measurement asymptotes each go next to the number they qualify, never in a footnote or a chat message.

When a lane corrects you, adopt the correction in the document the owner reads - do not defend the version already published.

### Free-model screening: what it is good for (calibrated 2026-10-20)

Six headless screens of already-credited bodies returned AGREE on every one, re-deriving from raw media rather than from our records. On `RES_00BA_13AB` the screen was right about the body hash, the file offsets, and all 18 conditionals - and wrong about one **derived** number (it reported image offset 7719, a transposition of 0x1F4B). The reviewer caught it.

So the calibration is: **trust the screen for hashes, decoded instructions and semantics; spot-check every derived number a script would consume** (image offsets, shifts, extents). A wrong derived offset does not look wrong - it reads the wrong bytes plausibly. Screens also cannot re-execute Unicorn or DOSBox-X, so they never test behaviour, and they must never write accounting, ledger, caveat or credit files.


### Differential coverage: account on successors, not flags (2026-07-20)

A harness that retires an untaken branch by reading the conditional jump's flags can be wrong in a way no assertion catches — a wrong CF/ZF reading silently marks a path covered. Compute coverage from the **successor**: when a conditional jump executes, the next IP *is* the side taken. That removes the class of error at the source instead of testing for it.

Corollary for exclusions: a branch may be legitimately unreachable, and the honest forms are **unreachable by composition** (a callee clears the state the compare reads — measure it across pre-set values) or **unreachable by contract** (the composed callee cannot return a value in the range the branch needs — record the search, not just the conclusion). State both verbatim in the doc, name the state that would make each feasible, and have the checker assert the exclusion list so a newly reachable path fails loudly rather than leaving a stale exclusion standing.

### Poolrad selection rules (from the 2026-10-20 night, all enforced in the queue doc)

- **Identity is not readiness.** A row's classification says what the body *is*; readiness says whether its C translation exists. Pricing a candidate against the classification column counts identity-known but untranslated callees as free, which understated one candidate by 18x (94 B/row claimed, 1,714 B/row real). Ready = strict table + runtime-covered endpoints + manifest-full residents.
- **Cost per unlocked row, not absolute body size.** The two options that look expensive in bytes can be the cheapest per row.
- **Every unconfirmed row figure is a floor.** The estimates have only ever moved one way; seven rows carried trailing data in one night.
- **Decode and size before authoring.** Three targets were declined in minutes each because sizing came first; all three would have consumed a night.
- **A hop into an unready or declined body makes a small item a chain.** A 94 B body whose four calls land in a declined 1.6 KB closure is a chain with a 94 B tail.
- **Resident declarations are credit-gated**, overlay manifest rows confer nothing, and readiness is re-derived from the products rather than the checkpoint.

### Why the lane's numbers can be trusted after two errors in an hour

Both of the 2026-10-20 method errors (94 B/row vs 1,714 B/row for `OVL_001C_13D7`; 580 B vs 49 targets for `OVL_001C_2F2D`) were found by the reviewer **trying to reproduce its own published number**, not by anyone challenging it.

That worked because **re-derivation is cheap**: the pricer is a script, the queue is deterministic, and the extracted media is immutable. Make re-derivation cheap and self-correction becomes routine rather than lucky; make it expensive and the same person defends the same error for weeks. When designing a lane's tooling, the price of re-deriving a published number matters more than the speed of producing one.

The corollary for the VP: **quote the artifact, publish the method, and keep the script next to the result** - then a wrong number is a ten-minute fix instead of an argument.

### The stopping rule generalises (2026-07-20, three stops in one night)

Three targets were declined at three different kinds of obstacle, all in one shift: **cost** (`OVL_0025_0C77`, a 1,672 B lower bound against a 1,500 cap), **identity** (`RES_00BA_16EC`'s dependency set, four bodies with no establishable ownership), and **engineering time** (`OVL_0077_275B`'s native capture, 0-byte `RESULT.BIN` after three fixes, two estimates past its boundary). Each cost a period of work and each avoided a much larger spend on evidence that would not have been accepted.

The same four steps covered all of them: **measure, name the blocker, refuse to ship an unverified claim, and write down where you stopped.** The discipline is not prize-specific - it is a loop that happens to work on cost, on identity, and on your own time.

Corollary for the VP: when a lane reports a stop, the useful questions are *what is the number it stopped on* and *where does the next person start* - not *why did it not finish*.

### Play Poolrad: latency and host contention (2026-07-20)

Owner-visible symptoms and what actually caused them, in the order they were measured:

- **"Typing does nothing for 30 s"** was **not** the input path: keys reached the server and the guest throughout (they are logged with timestamps in the run's `vp-input.jsonl`). Three separate causes: (1) the video stream captured at 15 fps and **upscaled 800×600 to 1600×1200 before JPEG**, costing ~0.9 core — now 4 fps, native size, coarser JPEG (~30× cheaper); (2) DOSBox-X ran **`cycles=auto`**, which ramps down when the guest looks idle and reads as a hang — now `cpu cycles=fixed 16000` (16 MHz, ~2× a 386; 60 000 burned a whole core for nothing); (3) **DOSBox-X pauses when its X window loses focus**, and in the desk the window is never focused because the owner is in a browser elsewhere — now `sdl pauseonfocusloss=false`.
- **Measure the legs separately before changing anything**: key injection was 138–296 ms; the emulator reported `16000 cycles/ms` in its own window title; the remaining seconds were browser-side multipart-JPEG buffering.
- **The desk keeps exactly ONE stream per kind.** A second viewer (including a diagnostic `curl`) **terminates the first** — so a test of the video endpoint freezes the owner's page. Never probe that endpoint while someone is playing.
- **Host contention is the other half.** Four agents plus a census plus the emulator on 8 cores drove load to 27 and CPU pressure to 76%: every lane now wraps heavy work in **`/home/hunter/workspace/poolrad-heavy.sh <command>`**, which allows **one slot while a `dosbox-x` is running and two otherwise**, all at nice 15, and returns **exit 75** so the agent does reading or fixture design instead of piling on. Stale slots expire after 30 minutes; detection reads `/proc/*/exe`, not `pgrep`, which counted itself.
- Corollary: a blanket "renice everything above X%" rule will eventually **renice the VP's own process and the Dunking Sheep daemon**. Use an explicit allowlist.
