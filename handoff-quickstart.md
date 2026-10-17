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

## Live handoff state — 2026-10-17 11:12 PDT

- **Harness switch (OpenCode -> pi): no new document needed.** The takeover prompt and procedure live in this file and [docs/VP_HANDOFF.md](docs/VP_HANDOFF.md); `AGENTS.md`/`README.md` carry the role. pi is already configured with the `deja` and `dunkingsheep` MCP servers (`~/.pi/agent/mcp.json`, extensions under `~/.pi/agent/extensions/`). Restart pi with its working directory set to this repo, paste the takeover prompt, and confirm the two MCP servers load.
- **One VP at a time.** Stop the previous VP pane when the new one takes over. The hourly VP reminder is dunk `d50` (name "VP hourly host and agent check-in"), currently targeting pane `w9:p8`; if the new VP runs in a different pane, retarget `d50` to it. The web desk discovers new panes automatically.
- **Poolrad is a 3-lane collaboration** on the 815-body candidate ceiling (82 PM-reviewed strict bodies; 143 verified identities; main `9ede23b3`):
  - Claude Fable (wR:p1, `../poolrad-decomp-claude-lane`): U33 grid + U9E dice clusters. PR **#859** (U33 +0D13, +0E9E) strict full-C with Unicorn + DOSBox-X parity, in peer review. Next: cluster 5 (+0BDE, +11B4).
  - Codex Astra Max (wR:p4, `../poolrad-decomp-codex`, branch `codex/poolrad-lane`): the hard lane. U5E +263D recon pushed (`521c445`); working OVL_0025_0000. **Caution:** `codex` is aliased to `codex --yolo` in `~/.bash_aliases`, so run bare `codex`.
  - OpenCode DS4.1 Flash (wR:p3, `../poolrad-decomp-opencode-ds41flash`, branch `opencode/ds41flash-lane`): U1C batch, owns the ranked queue (PR **#848**, schema-3) and now peer review/merge. Recovered 10 lost translations into PRs **#849-#858**; translating OVL_03C2_057B (full-state) to unblock Astra's +263D.
- **Cost rule (owner):** if any model/account drops to or below 5% left, stop using **that account** until it resets. Read each account's own quota; never apply one account's reading to another (a fresh VP already misread a separate Codex account's 5% and wrongly paused Astra). Last readings: Claude Fable 38% left (08:07 PDT, reset Oct 22 02:00 PDT); a separate Codex account 5% left (06:48, reset Oct 23 07:49; effectively paused); Astra's Codex account 99% left (reset Oct 24 08:07). OpenCode Go is a flat $10/mo; its limits are monthly **dollars per model** with 5h=20%, week=50%, month=100% of the model's monthly limit (DeepSeek V4.1 Flash = $80/mo).
- **Cleanup done:** removed 45 retired Poolrad checkouts and 65 Slamdemonium side-dirs after verifying archives at `~/.local/share/poolrad-agent-archive/2026-10-17/` and `~/.local/share/slamdemonium-agent-archive/2026-10-17/` (dirty work preserved). Kept `poolrad-decomp` + the three lanes + `slamdemonium`. The private game and dashboard data stay on this PC.
- **Owner brief style:** short, terse bullets in plain English (ELI5), no dense paragraphs or jargon; attach the authenticated Operations + Poolrad dashboard PNG pair. Terse beats complete.
- Services healthy at handoff: web desk and Telegram bridge up (`last_brief_id` 677), host `/tmp` OK; the four failed user units are desktop-only (claude-desktop autostart, baloo, kglobalaccel5, ksplash). The Play Poolrad pane works; a real playthrough is the highest-value oracle evidence and is encouraged (Sokal Keep, first wilderness transition, Kobold Caves).
