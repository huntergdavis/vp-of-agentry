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

## Live handoff state — 2026-10-18 00:55 PDT

- **Harness: pi.** MCP servers `deja` and `dunkingsheep` are configured (`~/.pi/agent/mcp.json`). pi's default model is set in `~/.pi/agent/settings.json` to `opencode-go` / `deepseek-v4.1-flash` (owner directive: pi must always start on DeepSeek V4.1 Flash). The `deja` index broke earlier today (`append: EOF` from a stale staging dir) and was rebuilt (~247 MB); recall works again.
- **One VP at a time.** VP pane `w9:p8` (pi). Hourly reminder dunk `d50` targets it; `d49` is the Claude-lane reminder (`wR:p1`).
- **Poolrad is a 3-lane collaboration on the 815-body candidate ceiling. Strict count is now 134 / 190 identities (up from 82 / 143 this morning).** Owner directive: **no PM lane** — each lane is its own PM and no agent reviews or credits its own code; the **verifying lane records strict acceptance** and opens the checkpoint PR. The VP merges the checkpoints.
  - **Claude** (`wR:p1`, `../poolrad-decomp-claude-lane`): model is **Opus 5.5** (swapped off Fable); all-model week ~22% left. Large U33/U38/U25 batches merged today. Now on RES_00BA_26C2 + U86 +0729/+07D6.
  - **Codex Astra Max** (`wR:p4`, `../poolrad-decomp-codex`): the hard lane. U25/U6F/U77 work; recovered six stale Codex branches into PRs #913–#919. Now on U3C6 +071A. **Caution:** `codex` is aliased to `codex --yolo`; run bare `codex`.
  - **Reviewer/accounting lane** (`wR:p3`): the old OpenCode DS4 pane crashed (kimi-k3 upstream 400s) and was replaced by a **fresh pi session on deepseek-v4.1-flash**. It owns independent verification, the **schema-7** strict candidate queue (raw-CPU vs callback-interface caveats) and the accounting checkpoints. It authored the validated task-system fix patch.
- **Dunking Sheep 2.14.2 — global + per-pane task system (verified):** atomic `task next`, leases + reaper, `task follow` push, `task metrics`; 17 MCP tools, CLI, TUI, inbox-append. Use it instead of ad-hoc assignment. Note: a client may need to reconnect its MCP to pick up the new `task_*` tools.
- **VP desk features added today:** a read-only **Herdr panes** webview (live grid of all panes); the **Play Poolrad** tab enlarged (game fills the viewer, 2x-pixelated) with a **type-text box**, a **code-wheel lookup** (36-word table) and a **visual rune picker**. The DOS copy protection is the **"decimer rune window"**, which does NOT match the poolrad-macmaps esp/det rune templates, so auto-recognition **abstains** and typing is manual/picker-driven.
- **Cost rule (owner):** at or below 5% left on any account, stop using THAT account until reset. Current: Claude all-model ~22% left (reset Oct 22); Astra's Codex 99%; Claude usage credits 100% spent ($901.54/$900, reset Nov 1); OpenCode Go flat $10/mo. Token cost is dominated by the VP/Claude long-context sessions; the task queue exists to cut VP involvement.
- **Crackdown (separate project, `../crackdown-switch`):** source `saulob/crackdown-xbox360-recompiled` v0.3.0; target Switch Linux (LTS). box64 route crashes on a guest access violation at 0x70560000; a patched box64 (pthread_sigqueue) is built; the native ARM64 build is compiling. Owner plays on `name-laptop.local` (Ubuntu 24.04, glibc 2.39).
- **Owner brief style:** short, terse bullets in plain English (ELI5); attach the authenticated Operations + Poolrad dashboard PNG pair.
- **Services healthy** at this update: web desk and Telegram bridge up (`last_brief_id` 764), host `/tmp` ~40%; the four failed user units are desktop-only (claude-desktop autostart, baloo, kglobalaccel5, ksplash). Host load is high (critical/warning) because many agents run concurrently with the Crackdown build. A real Poolrad playthrough remains the highest-value oracle evidence (Sokal Keep, first wilderness transition, Kobold Caves).
