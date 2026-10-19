# VP of Agentry

New VP agent: start with [handoff-quickstart.md](handoff-quickstart.md). Owner gameplay in the **Play Poolrad** pane is documented in [the tracked gameplay skill](skills/vp-gameplay/SKILL.md).

A private LAN desk for the owner's existing Herdr agents. Messages use Dunking Sheep's durable inbox where the agent has a unique mailbox; generic shared mailboxes use guarded exact-pane delivery. The website does not start a new model session.

For a new VP agent on any model or harness, read [AGENTS.md](AGENTS.md) and [the handoff guide](docs/VP_HANDOFF.md).

## Run

```bash
./run.sh                    # first run installs dependencies and builds the UI
./install-service.sh        # optional: keep it running with systemd
./vpctl status              # health check
```

Open `http://<LAN-host>:8787`. The initial password and API token are in ignored `data/owner-credentials` (mode `0600`). Change the password with the gear icon, or edit that file's `Password:` line; the next sign-in applies a newer file. The API token is preserved. Set `VP_BIND`, `VP_PORT`, or `DUNKING_SHEEP_DIR` if needed. Access this HTTP app only on a trusted LAN or VPN.

## Channels

Copy `channels.example.json` to `channels.json` and edit the local file for stable named channels and message history. `channels.json` is Git ignored; the checked-in example contains only generic labels. Each entry needs a unique `id`, display `name`, Herdr pane label `match`, and legacy `kind` (`active`, `standby`, or `monitor`). Add `"dashboard": true` to the channel linked from the project dashboard. The server reads the local file at startup and uses the generic example if no local file exists. Set `VP_CHANNELS_FILE` to use a different private file; an explicit missing path is an error. Restart the service after config edits. The website also discovers unconfigured live agent panes on every load and 12-second refresh. Active/standby grouping comes from live agent status, and each row shows its current workspace; new panes need no config edit to appear.

## Delivery

Enter sends; Shift+Enter adds a line. Messages and uploads (up to 25 MB each) are saved in ignored `data/` and copied into a unique agent inbox when available. The chat shows **in inbox**, **read**, and **handled** as the agent processes them; state is checked every five seconds. Shared generic mailboxes use the guarded pane queue, and show **queued** or **sent**. A timeout is marked **delivery uncertain** and never resent automatically.

Agents post durable Markdown replies with `echo 'Brief' | ./vpctl brief --channel vp`; add `--attach /path/to/image.png` to include a private image. The right panel shows recent, volatile `read_pane` output; search covers stored website messages and posted briefs. The owner Bearer token works with the same API. A browser tab opened before an upgrade needs one refresh; newer tabs show an update notice.

Host health monitoring: `./install-host-watch-service.sh` installs a separate user timer that samples `/tmp` capacity, inode use, and host load every minute. It sends a private VP inbox alert only when a threshold changes; owner briefs stay on the hourly cadence. `/tmp` warns at 60% used, 2 GiB free, or 70% of inodes; critical begins at 85% used, 0.75 GiB free, or 90% of inodes. Load warns after three spaced high samples and becomes critical after two spaced extreme samples. `python3 host_watch.py --status` shows the last saved sample; `--dry-run` samples without alerting. The monitor does not remove files.

The UI reuses MIT licensed [ChatScope](https://github.com/chatscope/chat-ui-kit-react), [Tiptap](https://github.com/ueberdosis/tiptap), [Turndown](https://github.com/mixmark-io/turndown), and [react-markdown](https://github.com/remarkjs/react-markdown). Open WebUI and LibreChat were evaluated, but their model-provider paths need an adapter to target a running Herdr pane and local guarded queue.

## Dashboard routes

Each dashboard has one clean standalone route that renders without the desk
sidebar or nav chrome, so the herdr web UI can frame it:

| Route | Dashboard |
| --- | --- |
| `/dash/poolrad` | Poolrad completion: two percentages and one evidence line |
| `/dash/operations` | Operations board: deterministic, refreshed on a timer |
| `/dash/play` | Play Poolrad: the live private DOS run |
| `/dash/vp` | VP of Agentry: the agent conversation |

`/dash` redirects to `/dash/poolrad`, and the older paths `/poolrad`,
`/operations`, `/play` and `/vp` redirect to the new routes, so no bookmark
404s. A trailing slash (`/dash/poolrad/`) redirects to the canonical path.

The routes use the same `vp_session` cookie as the desk, so a framed dashboard
needs no second login. **Without a live session a dashboard route never serves
dashboard content**: the request is redirected (302) to the password UI with a
return target, `/?next=<path>`, and after a successful sign-in the desk goes
straight back to that dashboard. The return target is validated on the server:
a path is always accepted, and an absolute URL only when it names this host
and a port the desk owns (its own port, or the Herdr web UI port that proxies
to it). Anything else falls back to the desk.

Frame the routes with the host the owner signed in on, not a hard-coded
address: `http://<request host>:8787/dash/<name>`. The session cookie is bound
to that hostname, so a frame pointed elsewhere gets no cookie and shows the
password UI instead of the dashboard.

## Poolrad dashboard

Choose **Poolrad dashboard** in the desk sidebar, or open `/dash/poolrad` on its own, to see two completion numbers and one evidence line: **strict C** and **verified identities**, each as a percentage of the PM-reviewed 815 upper bound, plus a single line naming the published checkpoint, the scoped pixel comparisons behind it, and the fact that this is not whole-game completion. The long prose was removed on purpose; the research snapshot keeps the full candidate list.

The numbers come from the PM-reviewed accounting checkpoint published on `main`, read through the private operations database, and fall back to the configured local checkout when no published snapshot is stored yet. **Refresh snapshot** re-reads the published checkpoint, records it, and regenerates the standalone HTML page; it does not rerun verification. `GET /api/poolrad-dashboard/progress` returns the same compact view as JSON (cached for a minute); `GET /api/poolrad-dashboard/dashboard.html` still serves the standalone page and `state/reports/{file}` serves the cited public report copies, both behind owner auth.

The VP server uses `POOLRAD_DASHBOARD_DIR` if the dashboard is outside the default sibling `poolrad-decomp/tools/dashboard` location. PM assignments come from separate workstream and source-gate queues. The candidate list does not award strict C credit.

Checks: `.venv/bin/python -m unittest discover -s tests -p 'test_*.py' -v`; authenticated browser check: `VP_TEST_SEND=1 .venv/bin/python tests/browser_smoke.py` (requires Playwright).

## Play: save states

While a private run is live, the **Save states** row in **Play Poolrad** drives
DOSBox-X's own save-state feature. **Save state** focuses the emulator window and
sends the mapper save chord to the next free slot (the run starts with
`saveslot=1`, `saveremark=false`, and `forceloadstate=true`), then records the tag,
slot, timestamp, size, and SHA-256 in ignored `vp-savestates.json` inside the run.
**Quick load** lists tagged states and loads one with the mapper load chord. Every
button calls an authenticated server endpoint (`POST /api/game/savestate`,
`GET /api/game/states`, `POST /api/game/loadstate`); none route through the VP chat.
States and the list stay in the private run tree and are never committed.

The live video stream passes `draw_mouse=0`, so the host X cursor is not drawn into
the frame; an emulated pointer that the game itself draws is unaffected.

## Play: code word helper

In **Play Poolrad**, open **Visual rune picker**, choose Espruar (outer) and Dethek
(inner), explicitly choose the path, then press **Type code word**. Numbered
inputs and the existing known-word text entry remain available. This is the
supported manual route for the DOS Decimer screen; the wheel formula is unchanged.

**Auto code word** calls authenticated `POST /api/game/autocodeword`. The server
captures the live game window with ffmpeg, drops the decorative chain border, and
runs the same model-free solver the desk previously ran in the browser: it segments
red marks, classifies the repeated path, preserves each rune's aspect ratio, and
compares both possible ring assignments. It types into the game only when two
captures agree, both runes score at least 0.90, each exceeds its next candidate by
0.08, and the ring assignment is unambiguous. Missing/ambiguous marks, unsupported
frames, missing templates, or changed prompts produce **No typing** and expose the
picker. Nothing is typed just by opening the view or selecting a rune. The private
GIFs are decoded on the host and no model is involved. These conservative thresholds
are not a claim of DOS/Mac artwork parity or validation across every game prompt.

The owner's private 800×600 DOS Decimer reference contains only one identifiable
red glyph and five dashes; its upper prompt is clipped. It **abstains**, rather than
inventing a second rune. No complete pair or automatic word has been verified for
that frame. Screenshots and template pixels are not stored in the repository.

Personal template setup: copy `esp01.gif`–`esp36.gif` and `det01.gif`–`det36.gif`
from the existing local Macmaps codewheel assets into ignored `data/codewheel/`
(directory mode `0700`, files `0600`). Alternatively set `VP_CODEWHEEL_DIR` to a
private directory. The authenticated, filename-allowlisted
`/api/game/codewheel/{filename}` route serves the GIFs with `Cache-Control: no-store`.
They are not frontend public assets; see [the artwork notice](licenses/CODEWHEEL.md).

The standard Python and frontend tests cover route authentication, path and shape
ambiguity, scale, ring order, and the lookup formula. The optional private regression
`.venv/bin/python tests/browser_codewheel.py /path/to/web-dist /path/to/dos-code-prompt.png`
uses Playwright and ffmpeg to reproduce the desk's crop/scale, checks reference-frame
abstention and manual selection on desktop/mobile, and mocks **all** typing requests.

## Herdr web UI

The desk used to carry a read-only **Herdr panes** grid. That section is gone: the live terminal UI is a separate service (herdr-webui), and the desk only frames it. Choose **Herdr web UI** in the sidebar; the frame's address comes from `GET /api/herdr-webui`, which reads the `VP_HERDR_WEBUI_URL` environment variable (`VP_HERDR_WEBUI_LABEL` names the item). With the variable unset the view says the UI is not configured on this host yet, and nothing is framed.

The service is reached through a small proxy that validates the desk's own `vp_session` cookie before forwarding to the loopback-only web UI, so there is no second login and no unauthenticated terminal on the LAN. That cookie is bound to the hostname the owner signed in on, so the endpoint rewrites the configured host with the hostname of the request and keeps the port and path: a frame pointed at another host would not carry the cookie and would answer 401. A frame that shows "unauthorized" therefore means the owner opened the desk under a different hostname than the one the cookie was issued for, not that the service is down.

The authenticated `GET /api/panes/activity` endpoint stays in the backend: it shares a four-second in-memory snapshot across browsers, bounds output per pane, and uses at most four concurrent socket reads. Errors are cached too; individual failed panes remain visible. Output is volatile and responses use `Cache-Control: no-store`.

After deploying this branch, run `npm run build --prefix web`, restart `vp-of-agentry.service`, refresh the signed-in desk, and select **Herdr panes**. To validate without touching the running desk, build with `npm run build --prefix web -- --outDir /tmp/vp-herdr-build`, then run `.venv/bin/python tests/browser_herdr_panes.py /tmp/vp-herdr-build`. This optional Playwright check uses synthetic APIs and no owner credentials, covering desktop/mobile layout, polling, stale output, focus, and read-only requests. Backend coverage is included in the normal Python suite.

## Operations dashboard

The **Operations dashboard** is a deterministic board, also served on its own at `/dash/operations`. Every number is read from Dunking Sheep's daemon API (task queue, agent inboxes, scheduled dunks, live panes, daemon health) and from the private operations database (PM-reviewed accounting, quota readings, owner subscriptions, host samples). **No model is consulted**: `ops_board.py` is a projection, not a written summary, and a source that cannot be read stays `unavailable` with its age instead of turning into a zero.

`ops_board.py` refreshes the board on a timer (30 seconds by default, `VP_OPS_BOARD_INTERVAL_S`) in a background thread, so the desk never waits on a refresh and the numbers move as operations happen. `GET /api/ops-board` returns the cached snapshot and `POST /api/ops-board/refresh` forces a fresh read. The view polls every 15 seconds and shows the age of the snapshot it is displaying, plus one chip per source so a failed read is visible.

The previous metrics view (credit history charts, quota cards, cost planning) still works behind **Detailed reference** in the same page and behind `GET /api/ops-metrics`, `GET /api/ops-metrics/history`, and `POST /api/ops-metrics/refresh`.

### Private collector

The private collector stores timestamped observations in ignored `data/operations.sqlite3` (mode `0600`). Run `./install-ops-metrics-service.sh` to collect pane presence every minute; recent GitHub PR states and Dunking Sheep aggregate telemetry are polled at most every five minutes. Open **Operations dashboard** below Poolrad in the sidebar, or read `./opsctl summary` or authenticated `GET /api/ops-metrics`. Its **Refresh data** button calls authenticated `POST /api/ops-metrics/refresh` for a fresh sample, including external sources. The summary gives source ages and leaves unavailable sources unavailable. Pane presence is not verified coding output; recent PRs are not a whole-game denominator.

The Operations overview reads exact published accounting on one GitHub main commit. The reviewed 815-body upper bound yields minimum function coverage, not whole-game completion. Completion per hour appears only after two comparable checkpoints at least one hour apart; a missing interval remains unknown. The hourly price is owner-reported fixed monthly subscriptions divided by calendar hours in the current month, excluding usage charges and actual coder hours. See `docs/operations-sources.md` for definitions.

Record direct quota readings with `./opsctl quota --provider codex|claude --pane PANE --left PERCENT --reset ISO_TIME --observed-at ISO_TIME --evidence SOURCE`. The Operations dashboard shows separate Codex and Claude weekly percentages, observation ages, and reset times; an unobserved provider remains unavailable. Record owner-reported fixed costs with `./opsctl subscription --provider PROVIDER --monthly-usd AMOUNT --evidence SOURCE`. Record scoped checkpoints with `./opsctl goal --key KEY --scope local|overall --status STATUS --evidence SOURCE`, and private role assignments with `./opsctl lane --pane PANE --role pm|coder|reviewer|other --focus DESCRIPTION`. Subscription totals are separate from usage; token and additional usage charges stay unknown until a billing source is available. Dunking Sheep telemetry is accepted only as aggregate schema-versioned data, with message content rejected.

For an isolated Codex trial, run `python3 codex_usage.py SESSION.jsonl` immediately before sending work and again after the last completed turn. Save both printed token event indices. Then run `python3 codex_usage.py SESSION.jsonl --start-index START --end-index END` to obtain exact counter deltas and a `usage_source` reference for `./opsctl trial`. The anchors must bracket only that trial in the same session; a wall-clock range alone is insufficient. The reader rejects counter resets. Token counts are usage evidence, not dollar charges; leave `--metered-usd` empty until a billing source exists.

For an isolated Claude trial, run `python3 claude_usage.py SESSION.jsonl` before and after the work, then `python3 claude_usage.py SESSION.jsonl --start-index START --end-index END`. Its message indices bracket the trial; repeated JSONL records with the same API message ID count once. It reports uncached input, cache write, cache read, output, and their total input. It refuses conflicting duplicate records or a mixed-model interval. Record `total_input_tokens` and `output_tokens` with the returned `usage_source` in `./opsctl trial`. Spawned agents with separate session logs require their own usage records; this single-session result is not a whole-trial total when they participate. These are token usage, not billed dollars; leave `--metered-usd` empty without a billing source.

When PM records an accepted body without a trial ID, Operations inherits the trial from an authored event only for the same original function and exact source head. This also applies when the authored event is imported after the acceptance. A changed head remains unattributed until the reviewer supplies a verified trial ID; model efficiency must not infer it from timing alone.

## Telegram

Create a private bot with [@BotFather](https://t.me/BotFather), then run `./telegram-bridge setup` locally and paste the token at the hidden prompt. Run `./install-telegram-service.sh`, then DM the bot the `/pair` command printed by setup. The token and one-chat pairing stay in ignored `data/telegram.json` (mode `0600`); `./telegram-bridge status` shows pairing without revealing secrets. The bridge uses outbound long polling, forwards text/photos/files to the VP inbox, and sends new VP briefs and attachments back to the paired chat. Telegram's hosted Bot API limits downloads to 20 MB; use the web desk for larger files. Do not run a second poller or configure a webhook for this bot.
