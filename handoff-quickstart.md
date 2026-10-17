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

## Live handoff state — 2026-10-17 10:08 PDT

- The web desk is running with the **Play Poolrad** pane. A real browser displayed an 800×600 frame and audio control; authenticated HTTP start, video, audio, key, and stop passed. The private saved run is recorded in ignored `data/poolrad-last-run.txt`. The dashboard refreshes from the tracked renderer in this repo. The root handoff and code were pushed to GitHub at VP commit `977c5d0` before this state note.
- `/tmp` recovery is complete: 337 aged, unreferenced Poolrad temporary directories were archived and removed. The verified private archive and manifests are under `/home/hunter/.local/share/poolrad-agent-archive/2026-10-17/`; `/tmp` was 18% used afterward. Host watcher briefly reported load WARNING during archive/cleanup, then returned to **OK** at 10:06 PDT with 16% CPU pressure. Recheck live readings.
- **Retired checkout cleanup remains to do.** The 85-name archive at `retired-checkouts.tar.zst` completed as a 4.9 GiB file, but tar exited **1** after warning that `poolrad-decomp-codex-worker2/resources` changed while read during the owner's concurrent cleanup. Forty retired directories were removed by that command; **45 remain**. The conflicting `rm` was terminated and the slow checksum pass was stopped for handoff; no archive or deletion process should remain. Run `zstd -tq` and list/compare tar's top-level members with `retired-checkouts.txt`, then separately preserve any dirty or unpublished work that might have changed during the archive before removing the 45 remaining paths. Do **not** claim this is a complete backup solely from the compressed-file test. A separate verified `dashboard-worktree.tar.zst` preserves the old dashboard worktree. Its live VP renderer is now tracked here, and the service no longer depends on the old worktree.
- Keep exactly these three Poolrad decomp checkouts: `../poolrad-decomp`, `../poolrad-decomp-claude-lane`, and `../poolrad-decomp-opencode-ds41flash`. Remove retired worktrees with `git worktree remove --force` only after preservation; handle independent clones separately and prune stale worktree metadata. `../poolrad-decomp` has an old divergent local `main` and dirty dashboard files; do not reset it blindly. The unrelated `poolrad-macmaps*` project is outside this cleanup.
- Claude Fable was working in its lane; OpenCode has a durable inbox assignment for a strict C candidate queue but may be idle or still on other installs. Check its inbox acknowledgment and current pane before assigning or assuming progress. The active VP reminder was `d50`. Read VP inbox as `dunkingsheep inbox read w9:p8` if this shell's default pane ID is stale, but discover the new VP pane ID at takeover.
