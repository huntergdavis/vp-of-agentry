---
name: vp-gameplay
description: Run Pool of Radiance in the VP Play pane, stream frames and audio, and collect private gameplay and debugger evidence for the decompilation.
---

# Poolrad gameplay in the VP desk

Use this skill when the owner wants to play Poolrad or an agent needs evidence from that play. Read the repo's `AGENTS.md` first. Before debugging, run `deja "<specific query>"` and cite findings reused.

## Play

In the web desk, choose **Play Poolrad**, then **Start game** or **Resume saved run**. **New run** makes a fresh audited copy. Click the game picture to focus keyboard controls, and click Play in the audio control. The browser may require that gesture before playing audio. The authenticated server streams multipart JPEG frames from a private Xvfb display and Ogg Opus audio from a private PulseAudio sink. It logs allowed browser keys in `vp-input.jsonl` beside the private game copy.

The server calls `../poolrad-decomp/tools/oracle/prepare_run.sh` to verify DOS v1.3 hashes and copy the private installation into ignored `../poolrad-decomp/resources/oracle-runs/<run-name>`. DOSBox-X runs under Bubblewrap with the copied run as its only writable game tree. `data/poolrad-last-run.txt` records the selected run locally. **Stop game** terminates the emulator, Xvfb, and audio sink while retaining saves for resumption; service shutdown also stops the session.

## Debugger and evidence

The emulator's backend terminal is `tmux -L vp-poolrad attach -t oracle`; detach with `Ctrl+B`, then `D`. DOSBox-X on Linux requires a terminal for its debugger. Its default break shortcut is `Alt+Pause`, and `F5` resumes; check the installed build's available debugger commands with `HELP`. An agent can trigger the shortcut using `xdotool` on the private display after reading `DISPLAY` and `XAUTHORITY` from the live session. The terminal log is `vp-dosbox-terminal.log` in the ignored run directory. See the [DOSBox-X debugger guide](https://github.com/joncampbell123/dosbox-x/blob/master/README.debugger).

For each useful play segment, record run name, starting and ending save hashes, input sequence, area and position, event or text ID, party changes, combat result, and what remains uncertain. The JSONL input trace helps reconstruct the route but is not proof of exact emulated timing. Keep screenshots, logs, original DOS files, and saves in ignored `resources/`; publish only behavioral summaries, IDs, hashes, counts, and offsets. Read `../poolrad-decomp/docs/oracle/README.md` and `docs/research/LATE_SAVE_SEEDS.md` for oracle conventions. Later-game priorities include Sokal Keep, the first wilderness transition, and Kobold Caves; existing scripts cover startup, save selection, and a short movement step.

## Check and recover

Use `./vpctl status`, `systemctl --user status vp-of-agentry.service`, and `tmux -L vp-poolrad list-sessions`. Check `command -v dosbox-x Xvfb xauth xdotool bwrap ffmpeg pactl tmux`, the private `vp-xvfb.log` and `vp-dosbox-terminal.log`, and `pactl list short sinks` if a stream fails. `systemctl --user restart vp-of-agentry.service` restarts the desk. After Stop, verify that the dedicated tmux session, Xvfb, FFmpeg streams, and null sink are gone. Never commit original media, saves, screenshots, credentials, or private traces.

The reproducible code for this feature is tracked in `server/gameplay.py`, `server/app.py`, and `web/src/main.jsx`; the private assets remain on this PC.
