# Incident 2026-10-18: a free model's pane cleanup killed the VP tab

**Status:** root-caused with logs; guard gap still open in Dunking Sheep.
**Impact:** the VP agent and all eight free-model verification agents died at
10:14:52 PDT. No files, credentials, or accounting were lost. The VP web
channel's activity endpoint 404'd until a new VP pane appeared (10:24), which
is why the desk looked half-down.

## What happened

The VP spawned eight free-model verification agents with:

```sh
herdr agent start "free-reN" --cwd /home/hunter/workspace/poolrad-decomp -- pi ...
```

`herdr agent start` without `--workspace`/`--tab` **splits into the caller's
current tab**. So the VP and all eight agents ended up as nine panes of one
tab (the herdr log shows each spawned pane at `cols=1`). A later cleanup loop
then ran `herdr tab close <tab-id-of-a-free-agent>`:

```sh
for p in w9:p9 ... w9:pG; do
  herdr tab close "$(herdr agent get $p ... tab_id)"
done
```

Because every free agent reported the VP's own tab id, the first iteration
closed the VP's tab. Herdr's log is unambiguous:

```
17:14:52.023  api request start    request_id="cli:tab:close" method="tab.close"
17:14:52.152  pane child exited    pane_id=112
17:14:52.292  pane child exited    pane_id=114
17:14:52.527  pane child exited    pane_id=113
17:14:52.635  pane child exited    pane_id=110
17:14:52.665  pane child exited    pane_id=100
17:14:52.903  ...                  (nine panes total, all Hangup)
17:14:53.697  api request complete  request_id="cli:tab:close" method="tab.close"
```

The previous VP session's last record is `17:14:51`; the tab close is one
second later. The Dunking Sheep daemon then logged
`d55: could not read w9:p8 input box` and `last_error target pane not found`.

## Root cause

Two independent mistakes compounded:

1. **Unsafe placement.** Agents were spawned without an explicit workspace or
   tab, so they inherited the VP's tab instead of a sandbox.
2. **Unguarded destruction.** The installed herdr guard covers only
   `pane run`, `pane send-text`, `pane send-keys`, and `agent send`. It does
   **not** cover `tab close`, `pane close`, or `workspace close`, so any agent
   could destroy any pane, including the one running it.

This is not an out-of-memory kill. Kernel logs show no OOM, and the host had
~23 GiB available. The host was busy (load 18.7, CPU pressure 63.8% at
10:10) because of the build plus nine cramped agents, but memory was not the
cause.

## Immediate mitigations applied

- VP check-in dunk `d55` retargeted from the dead `w9:p8` to `w9:pH`.
- Stale dunks aimed at closed panes (`d7`, `d8`, `d9`, `d10`, `d45`, `d48`)
  removed.
- Abandoned `/tmp` PR build dirs and pre-midnight Poolrad workdirs removed:
  `/tmp` went from 68% to 55% used and inodes from 21% to 17%.
- `tools/free_verify.sh` rewritten: headless workers only (no herdr pane, no
  pane control), host-pressure preflight, concurrency cap, and explicit
  big-pickle support.

## Required fix (open, assigned to Dunking Sheep)

The owner asked for a **superuser mode** for Dunking Sheep. Spec is in inbox
message `i18190` to `dunky pi`:

- A superuser allowlist (panes and/or agent names), with the VP registered.
- Gate `close pane|tab|workspace`, `shutdown`, and the herdr wrapper's
  `pane close` / `tab close` / `workspace close` behind it.
- Non-superusers may only use the inbox and task system.
- Refuse a tab close that contains the caller's own pane unless `--force`.
- Re-assert the VP in the allowlist during setup and recovery.

## Rules for the next VP

1. **Never run `herdr close`, `herdr tab close`, or `dunkingsheep close`
   against a tab/workspace you did not create for that purpose.** Closing your
   own tab kills you mid-turn.
2. **Always pass `--workspace` and `--tab` when starting an agent**, and give
   free/open models their own sandbox workspace.
3. Prefer **headless** free-model workers (`tools/free_verify.sh`). They need
   no pane and cannot hold a window.
4. Free models are a second pair of eyes, never a credit authority and never
   a control plane.
