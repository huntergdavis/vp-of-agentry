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

## Live handoff state — 2026-10-17 12:45 PDT

- **Harness switch (OpenCode -> pi): no new document needed.** The takeover prompt and procedure live in this file and [docs/VP_HANDOFF.md](docs/VP_HANDOFF.md); `AGENTS.md`/`README.md` carry the role. pi is already configured with the `deja` and `dunkingsheep` MCP servers (`~/.pi/agent/mcp.json`, extensions under `~/.pi/agent/extensions/`). Restart pi with its working directory set to this repo, paste the takeover prompt, and confirm the two MCP servers load.
- **One VP at a time.** The VP pane is `w9:p8` (pi). The hourly VP reminder is dunk `d50`, retargeted to `w9:p8`. Dunk `d49` is the Claude-lane hourly reminder (targets `wR:p1`). The web desk discovers panes automatically.
- **Poolrad is a 3-lane collaboration** on the 815-body candidate ceiling (82 PM-reviewed strict bodies; 143 verified identities). The `deja` MCP recall repeatedly times out (index slow); the CLI `deja "query"` also times out. Lanes cite recall from their own panes.
  - Claude (wR:p1, `../poolrad-decomp-claude-lane`): **model swapped Fable -> Opus 5.5** at 11:54 PDT on owner directive (Fable was down to 9% left). Binding limit is now the all-model weekly pool (~26% left, reset Oct 22 02:00 PDT). Merged PRs #847, #859, #861 (7 complete U33 grid bodies). Reviewing #848, next cluster +1577.
  - Codex Astra Max (wR:p4, `../poolrad-decomp-codex`, branch `codex/poolrad-lane`): the hard lane. U25 complete: #862 (string cores), #863 (+0000), #864 (+1EA6), #866 (+0136) all merged. Working U5E +17F6. **Caution:** `codex` is aliased to `codex --yolo` in `~/.bash_aliases`, so run bare `codex`.
  - OpenCode DS4.1 Flash (wR:p3, `../poolrad-decomp-opencode-ds41flash`, branch `opencode/ds41flash-lane`): owns the ranked queue and peer review/merge. Queue is now **schema-4** (PR #848, transitive callee closure; ~104/600 composable). Independently verified+merged #861-#866.
- **Cost rule (owner):** if any model/account drops to or below 5% left, stop using **that account** until it resets. Read each account's own quota; never apply one account's reading to another. Current: Claude pane on Opus, all-model ~26% left; a separate Codex account 5% left (paused, reset Oct 23 07:49); Astra's Codex account 99% left (reset Oct 24 08:07). Claude usage credits 100% spent ($901.54/$900, resets Nov 1). OpenCode Go is a flat $10/mo.
- **Open gap (needs owner decision):** merges keep landing but the strict counter stays 82 because nothing performs PM strict-review and there is no active Poolrad PM pane. Ask the owner whether to stand up a PM lane, have the VP/lanes do strict review, or wait.
- **Owner brief style:** short, terse bullets in plain English (ELI5), no dense paragraphs or jargon; attach the authenticated Operations + Poolrad dashboard PNG pair. Terse beats complete.
- Services healthy at this update: web desk and Telegram bridge up (`last_brief_id` 684), host `/tmp` OK; the four failed user units are desktop-only (claude-desktop autostart, baloo, kglobalaccel5, ksplash). The Play Poolrad pane works; a real playthrough remains the highest-value oracle evidence (Sokal Keep, first wilderness transition, Kobold Caves).
