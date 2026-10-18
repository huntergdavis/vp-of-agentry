# VP of Agentry handoff quickstart

This is the handoff point for a new VP agent on any model or harness. Open this GitHub repository on the owner's PC, then read [AGENTS.md](AGENTS.md), [README.md](README.md), and [the detailed handoff](docs/VP_HANDOFF.md). Code and instructions are in Git; credentials, channel mappings, media, and live state stay in ignored local files.

## Paste this to the new VP

> You are the owner's VP of Agentry. Work from this repository on the owner's PC. Read `handoff-quickstart.md`, `AGENTS.md`, `README.md`, `docs/VP_HANDOFF.md`, and relevant tracked skills. Use fresh Los Angeles timestamps for every user-visible message and tool operation, including a literal timestamp comment as the first shell line. Before debugging, run `deja "<query>"` and cite what you reuse. Pair with Dunking Sheep: read the VP inbox, inspect live panes and existing auto-dunks, and retarget the single hourly VP reminder to your pane. Its inbox send already nudges recipients, so do not double-message. Check host health, `/tmp`, services, project agents, costs, and Claude's weekly balance. Keep Claude Fable moving substantive Poolrad C ports with max thinking until only 5% of its weekly usage remains; keep OpenCode's strict-C queue lane separate. Send each substantive owner update once through `./vpctl brief --channel vp`; the local bridge forwards it to Telegram. Verify `./telegram-bridge status` advanced `last_brief_id`. The owner can play Poolrad in the Play pane; read `skills/vp-gameplay/SKILL.md` for frame and audio forwarding, debugger terminal, saves, and evidence. Preserve private data and unpublished work. Continue outstanding tasks.

## First five minutes

```sh
cd /home/hunter/workspace/vp-of-agentry
./vpctl status
./telegram-bridge status
./opsctl summary
python3 host_watch.py --status
df -h /tmp
df -i /tmp
systemctl --user --failed
git status --short
```

Read `dunkingsheep inbox read`, inspect the pane roster and existing auto-dunks, and then check live branches before assigning work. The active VP reminder was `d50` on 2026-10-17; confirm its target before changing it. The web desk discovers active and standby panes at load and refresh, while the Operations dashboard shows current costs and host readings.

The primary Poolrad checkout is `../poolrad-decomp`; Claude uses `../poolrad-decomp-claude-lane`; OpenCode uses `../poolrad-decomp-opencode-ds41flash`. Claude's target is real C ports with a direct 5%-remaining weekly quota stop. OpenCode's independent task is a strict C candidate queue. The owner wants later-game oracle evidence from manual play. The [tracked gameplay skill](skills/vp-gameplay/SKILL.md) covers the **Play Poolrad** pane and local debugger backend. Confirm these lanes are still current through the inbox and Git before acting.

The Poolrad dashboard renderer is tracked under `integrations/poolrad-dashboard` (source snapshot from Poolrad commit `f314e2f6`); generated HTML and state there are ignored. The web refresh uses `POOLRAD_DASHBOARD_REPO`, defaulting to the current OpenCode checkout. Check the displayed source commit before treating the numbers as current main. The private game and all dashboard-generated data stay on this PC.

For each owner check-in, publish one VP brief for web and Telegram and verify bridge delivery. Put repeated VP checks into the existing direct auto-dunk, and repeated instructions to another agent into scheduled inbox delivery. Preserve unique work before deleting old directories. Update and commit this quickstart when the machine or core workflow changes so a future VP with only this repo and PC can take over.

## Live handoff state — 2026-10-18 04:45 PDT

- **Harness: pi.** MCP servers `deja` and `dunkingsheep` configured. pi default model = `opencode-go` / `deepseek-v4.1-flash` (`~/.pi/agent/settings.json`). `deja` was rebuilt (~247 MB) and now has a 15-min `deja-health` timer surfaced in `opsctl summary`.
- **One VP at a time.** VP pane `w9:p8` (pi). Dunks: `d50` VP check-in (now in **quiet hours: no owner messaging until 07:00 PST 2026-10-18**), `d49` Claude-lane reminder (`wR:p1`), `d52` reviewer (`wR:p3`), `d53` Astra (`wR:p4`), `d54` Crackdown perf (`wS:p1`, 30m).
- **Poolrad: strict 185 / 236 identities, schema-8 queue (498 candidates / 66 composable).** Owner rule: no PM lane — each lane is its own PM, no self-review, the **verifying lane records strict acceptance** and opens the checkpoint PR; the VP merges checkpoints. **Rule: once an acceptance PR has merged, open a NEW one for further credit — never force-push a merged branch** (this race cost two re-credits tonight). The composable queue is essentially dry, so credit now comes from **evidence-only harvesting** and **blocker-first runtime models** (e.g. GetMem, StrStore leaves), whose bodies are then claimed.
  - **Claude** (`wR:p1`, Opus 5.5): all-model week **~14% left** (reset Oct 22 02:00); stop at 5%. Now on the U6F +1446 raw-CPU entry (its evidence gap).
  - **Codex Astra Max** (`wR:p4`): the hard lane; finished the evidence-only harvest (#970–#972) and is now composing **U5E +32E6**. **Route its mail to `wR:p4`**.
  - **Reviewer/accounting** (`wR:p3`): fresh pi session on deepseek-v4.1-flash (the old OpenCode pane died on kimi-k3 400s). Owns independent verification, the schema-8 queue and accounting checkpoints.
- **Under-5% ice rule (owner):** if any account drops to ≤5% left, stop that lane and schedule a one-shot re-enable dunk at its reset time. Reset dates: Claude Oct 22 02:00; Astra Codex Oct 24 08:07; a separate Codex account Oct 23 07:49 (paused).
- **Task system:** Dunking Sheep **2.14.2** global + per-pane tasks (verified): atomic `task next`, leases + reaper, `task follow` push, `task metrics`, 17 MCP tools, CLI, TUI, inbox-append.
- **VP desk features:** Herdr panes webview; Play Poolrad enlarged with type-text box, code-wheel lookup and visual rune picker (auto-recognition abstains on the DOS "decimer rune window"). Dashboard renders from the reviewer's checkout; refresh via `/api/poolrad-dashboard/refresh`.
- **Crackdown native (the owner's overnight focus, `../crackdown-switch`):** game `saulob/crackdown-xbox360-recompiled` v0.3.0, target Switch Linux `name-laptop.local` (Ubuntu 24.04.4, glibc 2.39). Native ARM64 build + both desktop icons installed. Measured native gameplay FPS at 1280x720 low: **2.77 → 6.43 → 9.33 → 10.07 → 13.43 → 14.53 → 14.73 → 14.97 @50% internal (75% ≈ 14.13 with the provisional shader optimizer ON, default OFF)**; **25 FPS menu @75% internal**. Fixes so far: `XamCreateEnumeratorHandle` uninitialized output count (the 0x70820008 stack-guard fault/retry storm), audio-sync busy-wait (94%→~18% per core), inline guest event-clear (~66% worker removed), finite-wait truncation (94%→1.16% CPU), and a guard-safe write-watch fast path (200 writes 15.6× faster; also fixed a stale-protection bug where read-only/no-access writes weren't trapping). Remaining: **GPU command thread ~95% of a core** (92% user / 3% kernel) is the wall; tested CPU/GPU affinity + `vrev32` byte-reversal in progress. Rejected ideas (kept as evidence, not installed): shader-constant reuse, cached 64-byte uniform uploads (measured slower). Three-A startup automated. Clocks already maxed (CPU 1963 MHz, GPU 768 MHz) — no overclock headroom. **box64 route still stalls at the title** (deprioritized). Owned by `wS:p1` with autonomous overnight mandate + `d54`.
- **Owner brief style:** short, terse ELI5 bullets; attach the Operations + Poolrad dashboard PNG pair. Quiet hours (no owner messaging) until 07:00 PST.
- **Services:** web desk + Telegram bridge up; the 4 known desktop-only units fail; host load is high from the agent fleet but `/tmp` was cleared to ~16%.
