# DOSBox-X 2026.10.01 staging and rollback (t16)

Date: 2026-10-19 (America/Los_Angeles)
Status: staged and unit-tested; **not deployed**, the desk was not restarted, and
the live game was not touched.

## Why

The installed DOSBox-X 2026.01.02 predates the upstream save-state load fixes
(v2026.06.02 "savestate load producing scrambled graphics" and the August
state-directory fixes). Cross-process save-state load was verified broken on the
old binary. On 2026.10.01, a real Poolrad run copy restored the saved title screen
**pixel-identically** across a brand-new emulator process, with no crash.

## Staged binary

- `~/.local/share/vp-of-agentry/dosbox-x-2026.10.01`
- DOSBox-X 2026.10.01, SHA-256
  `a11d55f0cb9bf10e36e69d8df27c3bd6bc303f5aacde32f3e7cdc96c3ebfe967`
- Built from upstream `dosbox-x-v2026.10.01` in `/tmp/dosbox-x-src` (unstripped
  debug build, 122,144,336 bytes). Rebuild/install later if a stripped or release
  build is preferred.

## Rollback reference

- `/usr/bin/dosbox-x` 2026.01.02, SHA-256
  `99d7460153175d13a21036fb4b0e7524e05b6a1e50cd4e59f2470afad12a0df3`
  (root-owned, package-managed, untouched by this change).
- The staged binary does not replace any system file.

## Selection

`server/gameplay.py` reads `VP_DOSBOX_X` and falls back to `dosbox-x` (PATH
lookup). The bwrap `--ro-bind /` and PATH launch are unchanged; an absolute
`VP_DOSBOX_X` path works inside the sandbox.

### Rollout (quiet window only)

1. No web rebuild is required for this change (backend only).
2. Add
   `Environment=VP_DOSBOX_X=/home/hunter/.local/share/vp-of-agentry/dosbox-x-2026.10.01`
   to the `vp-of-agentry.service` unit, or export it in `run.sh`.
3. `systemctl --user daemon-reload` and restart `vp-of-agentry.service` only when
   the owner is not playing.
4. Verify: start a private run; after the title screen, save a tagged state;
   restart the desk; resume; quick-load; confirm `verified` and a clean frame.
   States written by the old binary are not guaranteed to load in 2026.10.01;
   use the game's own SAVE for cross-version recovery.

### Rollback

1. Remove the `VP_DOSBOX_X` line (or point it at `/usr/bin/dosbox-x`).
2. Restart `vp-of-agentry.service` in a quiet window.
3. The system binary is untouched; there are no package changes to undo. States
   written by 2026.10.01 may not load in 2026.01.02; use the game's own SAVE.

## Load caveat

DOSBox-X shows "Program name mismatch. Load the state anyway?" if F12+L is pressed
while the guest is still in autoexec (current program `MOUNT`/`COMMAND`, not
`START`). **Forcing Yes crashed 2026.10.01 (`Aborted (core dumped)`)** in
isolated testing. `loadstate` now waits for `START.EXE` to have run (the game's
startup warning is present in `vp-dosbox-terminal.log`) and refuses with guidance
if it never does. Do not add an automatic Yes to that dialog.
