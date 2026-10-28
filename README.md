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

For channels using direct owner pushes, **stored** becomes **delivered in Xs** only after a matching harness pickup receipt. The channel also shows its last confirmed delivery time, including when that message is outside the current history page. The duration runs from the desk accepting the message to the recorded pickup, excluding browser polling delay; pickup does not mean a reply is ready. This requires the read-only `owner_receipts` API from Dunking Sheep 2.70.80 (PR #52) to be loaded in the running daemon. Missing, mismatched, or invalid timestamps leave the previous stored state unchanged. A backward wall-clock step preserves confirmed pickup but shows **timing unavailable** instead of an elapsed value. Message bodies and the original transport outcome are preserved. Reverting the desk change leaves two unused nullable timing columns in the local message database; no data removal is needed.

`tools/raw_storage_probe.py --dist <isolated-built-directory> --output <scratch-directory>` checks the message text path with temporary SQLite databases and real Chromium at 1440×900 and 390×844. First build with `npm run build --prefix web -- --outDir <scratch-built-directory>`; run both heavy steps through the shared heavy-job wrapper. The probe needs the desk Python dependencies, Playwright, and an installed Chromium (`--chromium` can select its executable). It serves only its own temporary loopback origin and substitutes synthetic APIs and transport. No credentials, live desk, or agent pane are used. Its receipt records input bytes, normalized SQLite hex before transport/after push/after pickup, API bytes, expected and actual DOM text, source/build hashes, and screenshots. Run the storage corruption controls with `python -m unittest tests.test_raw_storage_probe -v`.

Stored Markdown bytes must equal the writer's input bytes. Visible DOM text is a separate promise: composer escapes should restore the original visible input, while agent `**bold**` may become a bold element. SQL/DOM inequality alone does not prove a rendering defect. The probe checks `$901`, literal brackets, permitted emphasis, paragraph count, and absence of delivery timing on agent replies; it does not verify live delivery, authentication, other browsers/devices, or full accessibility. Keep its receipts and screenshots in ignored or scratch storage.

The receipt and `rendering-table.md` contain four named assertions with stored/DOM hex on both sides: no added bracket escape when the stored fixture had none, exact dollar preservation, one paragraph without inserted hard breaks, and correct emphasis as a passing control despite unequal bytes. Normal viewport wrapping is allowed. Unit controls deliberately add a bracket escape, remove a dollar sign, split a paragraph or insert a hard break, and remove the strong element; each must fail its named row.

Agents post durable Markdown replies with `echo 'Brief' | ./vpctl brief --channel vp`; add `--answers 123,124` to link the owner messages this brief answers, and `--attach /path/to/image.png` to include a private image. Answer links apply only to owner messages in the same channel; existing links are preserved. Omitting `--answers` leaves messages unanswered. The right panel shows recent, volatile `read_pane` output; search covers stored website messages and posted briefs. The owner Bearer token works with the same API. A browser tab opened before an upgrade needs one refresh; newer tabs show an update notice.

Host health monitoring: `./install-host-watch-service.sh` installs a separate user timer that samples `/tmp` capacity, inode use, and host load every minute. It sends a private VP inbox alert only when a threshold changes; owner briefs stay on the hourly cadence. `/tmp` warns at 60% used, 2 GiB free, or 70% of inodes; critical begins at 85% used, 0.75 GiB free, or 90% of inodes. Load warns after three spaced high samples and becomes critical after two spaced extreme samples. `python3 host_watch.py --status` shows the last saved sample; `--dry-run` samples without alerting. The monitor does not remove files.

The UI reuses MIT licensed [ChatScope](https://github.com/chatscope/chat-ui-kit-react), [Tiptap](https://github.com/ueberdosis/tiptap), [Turndown](https://github.com/mixmark-io/turndown), and [react-markdown](https://github.com/remarkjs/react-markdown). Open WebUI and LibreChat were evaluated, but their model-provider paths need an adapter to target a running Herdr pane and local guarded queue.

## What :8787 serves now

The herdr web UI on **:8789** is the front door (owner #956). The desk on
**:8787** is now a service behind it, not a place to arrive:

| Served by :8787 | What it is |
| --- | --- |
| `/dash/poolrad`, `/dash/operations`, `/dash/play`, `/dash/vp` | the four standalone dashboard documents the shell frames |
| `/assets/…` | the bundle those documents load |
| `/api/…` | dashboard data, login/logout, health |
| `/` | the password page (and the `?next=` handoff target) |

**Every other path is a permanent redirect (308) to the shell**, built from
the host the visitor used: `http://<request host>:8789/`. A path the shell
owns keeps its path and query (`/session/...`), everything else goes to the
shell root. The redirect target is always on the shell's port, so a redirect
can never bounce back to the desk.

Two consequences worth knowing:

- Opening `http://<host>:8787/` while signed in lands on the herdr web UI;
  while signed out it shows the password page, because that is where the
  shell sends a visitor who needs to sign in (`/?next=…`).
- The old aliases `/poolrad`, `/operations`, `/play` and `/vp` now land on the
  matching dashboard inside the shell: `http://<host>:8789/#dash/<name>`. The
  fragment is read by the shell, so the owner's old link brings them to the
  view they meant rather than to a terminal with no context.

## Dashboard routes

Each dashboard has one clean standalone route that renders without the desk
sidebar or nav chrome, so the herdr web UI can frame it:

| Route | Dashboard |
| --- | --- |
| `/dash/poolrad` | Poolrad completion: two percentages and one evidence line |
| `/dash/operations` | Operations board: deterministic, refreshed on a timer |
| `/dash/play` | Play Poolrad: the live private DOS run |
| `/dash/vp` | VP of Agentry: the agent conversation |

`/dash` redirects to `/dash/poolrad`. A trailing slash (`/dash/poolrad/`)
redirects to the canonical path.

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

`VP_HERDR_WEBUI_URL` does double duty: it is the address the desk frames, and
its port is the only absolute return target the login accepts besides the
desk's own port. That coupling is deliberate - the frame address and the
allowed return port cannot drift apart - so if the Herdr web UI proxy ever
moves to another port, set the variable to that new address and both follow.

## Poolrad dashboard

Choose **Poolrad dashboard** in the desk sidebar, or open `/dash/poolrad` on its own, to see two completion numbers and one evidence line: **strict C** and **verified identities**, each as a percentage of the PM-reviewed 815 upper bound, plus a single line naming the published checkpoint, the scoped pixel comparisons behind it, and the fact that this is not whole-game completion. The long prose was removed on purpose; the research snapshot keeps the full candidate list.

The numbers come from the PM-reviewed accounting checkpoint published on `main`, read through the private operations database, and fall back to the configured local checkout when no published snapshot is stored yet. **Refresh snapshot** re-reads the published checkpoint, records it, and regenerates the standalone HTML page; it does not rerun verification. `GET /api/poolrad-dashboard/progress` returns the same compact view as JSON (cached for a minute); `GET /api/poolrad-dashboard/dashboard.html` still serves the standalone page and `state/reports/{file}` serves the cited public report copies, both behind owner auth.

The VP server uses `POOLRAD_DASHBOARD_DIR` if the dashboard is outside the default sibling `poolrad-decomp/tools/dashboard` location. PM assignments come from separate workstream and source-gate queues. The candidate list does not award strict C credit.

Checks: `.venv/bin/python -m unittest discover -s tests -p 'test_*.py' -v`; authenticated browser check: `VP_TEST_SEND=1 .venv/bin/python tests/browser_smoke.py` (requires Playwright).

For read-only served evidence, use `VP_TEST_CREDENTIALS_PATH=/path/to/local-credentials .venv/bin/python tools/capture_served.py --url http://127.0.0.1:PORT --path /dash/cos --output /path/to/new-evidence`. It requires Playwright/Chromium, authenticates once, and captures 1440x900 and 390x844 with dialogs closed. The receipt records HTTP status, response-byte SHA-256 hashes of served JavaScript and screenshots, and wall-clock timestamps; it omits credentials, cookies and request bodies. HTTP redirects are refused before follow-up requests, and captured bundle name/hash sets must match across viewports. Every subsequent non-GET attempt, including viewport telemetry, refuses the run and removes its screenshots. No live acceptance follows from a refused run. Validate against temporary loopback fixtures with `VP_CAPTURE_BROWSER_TEST=1 .venv/bin/python -m unittest tests.test_capture_served -v` through the shared heavy wrapper; `VP_CAPTURE_TEST_ARTIFACTS` optionally preserves the successful fixture captures. This is viewport emulation, not real browser zoom or full accessibility verification.

## Play: character editor

Open **Play Pool of Radiance → Character editor** (`/dash/play?panel=editor`).
Import copied DOS save files, inspect the records, then give the output copy a
name. **Write unchanged copy** preserves the save bytes; **Write edited copy**
applies only the selected reference profiles. Download includes the save files
and a receipt with filenames, hashes and every changed byte. Saved copies can
be inspected and exported again. Originals are never overwritten.

The backend invokes the Poolrad `tools/character/edit_save.py` schema-1 CLI;
set `POOLRAD_EDITOR_TOOL` to its installed path if the default sibling checkout
is unavailable. It also needs `disk_save.py` beside it for unchanged exports.
Use the accepted PR1608 interface (merge `3203fd0af63b37006ff05d30749d978bb614c999`)
or a compatible revision. No new package dependency is required. When the CLI
is missing the editor reports it as unavailable; the game view remains usable.
Private imports and outputs live under `data/character-editor/`; the UI reports
the output path relative to `data/`, and downloads omit private absolute paths.
The routes use the desk's existing owner authentication.

Only the exact hash-bound STR 17→16 and reference fighter level 1→2 transitions
are supported. The level change does not recalculate XP, HP or spells. Other
records can be inspected and exported unchanged. Every new output is labelled
**UNVERIFIED**, with `game_build_loaded: null`: creating a copy does not load it
in a game or inherit historical game validation. This view sends no game input.

Adapter/model checks and optional real CLI identity check:

```bash
.venv/bin/python -m unittest discover -s tests -p 'test_character_editor*.py' -v
node --test web/src/character-editor-model.test.js
POOLRAD_EDITOR_TEST_TOOL=/path/to/edit_save.py .venv/bin/python -m unittest discover -s tests -p test_character_editor_cli.py -v
```

For browser verification, build to a scratch directory with
`npm run build --prefix web -- --outDir <scratch-dist>`, then run
`tools/check_character_editor.py --dist <scratch-dist> --output <evidence-dir>`
through the shared heavy-job wrapper. It exercises actual HTTP/ASGI upload,
inspection, ordered edits, copy download, unchanged originals and unknown-record
re-export at 1440×900 and 390×844 in every registered theme. Its CLI is a
synthetic contract double; it cannot establish real reference editing or game
loading. The optional CLI test uses the actual installed scripts with synthetic
files for no-op identity and refusal of unsupported hashes.

## Play: original or replacement build

`VP_PLAY_BUILD=original` is the default. It launches the original `START.EXE`
using `VP_DOSBOX_X`, whose default remains `/usr/bin/dosbox-x`.
The installed checkpoint binary is an explicit opt-in:
`VP_DOSBOX_X=~/.local/share/vp-of-agentry/dosbox-x-5a9c7c53/dosbox-x`
(use the expanded absolute path in the server environment).
Its native restore check currently fails; keep that opt-in off until the
[restore diagnostic](docs/PINNED_PLAY.md) is resolved. Returning
`VP_DOSBOX_X` to `/usr/bin/dosbox-x` selects the system binary on the next launch.
Preserve any active game before restarting the server. To select the experimental hybrid,
set `VP_PLAY_BUILD=replacement` in the server environment and restart the server.
The Play status API reports the selected `build`. Switching the flag back to
`original` restores the original launch path.

Replacement mode uses these private files under the configured Poolrad checkout:

- the stable pinned executable, overridden by `VP_REPLACEMENT_DOSBOX_X`;
- `resources/hybrid/registry_all.tsv`, overridden by `VP_REPLACEMENT_REGISTRY`;
- `resources/hybrid/play-dispatch.txt`, overridden by `VP_REPLACEMENT_DISPATCH`.

The dispatch file contains one comma-separated line of supported `RES_…` / `OVL_…`
IDs from the measured hybrid build. Each selected ID requires exactly one
registry row: a four-digit hexadecimal IP matching the ID's entry offset,
a positive signature length up to 256 bytes, equal-length hexadecimal
signature/mask bytes, and a `unique` marker. Masks use `00`/`ff` bytes and
must check at least one byte. Missing, duplicated or malformed selected rows
fail before display or emulator launch. Registry input is bytes separated only
by LF, with a 4094-byte maximum physical line. Data rows permit ASCII letters,
digits, underscore, equals, comma, hyphen and TAB; comments must begin with `#`
and permit printable ASCII and TAB. CRLF, trailing spaces in data, NUL, BOM,
non-ASCII bytes and other control separators are rejected. Accepted registry
bytes are copied unchanged. Each run copies the registry and dispatch list,
uses the normal CPU core and routed bus, and records hybrid logs in its private
run directory. Both modes clear inherited hybrid and checkpoint controls,
including test seed pins. Replacement mode still starts `START.EXE`; only the
listed functions can run as C. Registry membership alone does not prove that
the emulator implements an ID; use a dispatch list from the reviewed build.

`tests/test_registry_agreement.py` compiles the pinned observer loader with the
reusable `tests/support/cpp_format_probe.py` harness and synthetic inputs. It
checks that Python acceptance implies the actual C++ loader reads exactly the
selected row, including its IP, signature and mask. These tests require `c++`;
missing compiler support fails the test rather than skipping the agreement gate.

NOT verified by the selector tests: live desk audio/video, save-state migration
between builds, replacement gameplay parity, or complete C execution. No
service configuration is changed merely by querying status. Installation,
provenance, status semantics, archive verification and the native validation
record are described in [Pinned Play](docs/PINNED_PLAY.md).

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

The **Operations dashboard**, also served at `/dash/operations`, has four sections:
a short brief with task/lane counts and a compact Poolrad headline, actionable
exceptions and explicitly owner-assigned tasks, provider budgets, and one always-visible reference for tasks, lanes and schedules. Unknown lane activity stays
unknown; a blocked agent task is not inferred to require the owner. Terminals are
grouped by project in single-level disclosures. The Terminals page scrolls within
the viewport, with the selected agent's composer above its captured screen. The
screen has its own scroll area and represents the current screen only; app
scrollback and remote scrolling keys are not provided.

`ops_board.py` reads Dunking Sheep and the saved host sample without model calls.
`GET /api/ops-board` returns `no_model: true`, `generated_at`, and the four
content sections `brief`, `attention`, `budget`, and `reference`. Each numerical source
carries its status and timestamp; unavailable values stay null. The board refreshes
on its existing timer and the view polls every 15 seconds. Healthy source chips,
empty throughput/configuration panels, duplicate credit cards, the inbox table,
and the nested legacy metrics view have been removed from this overview.

Poolrad now lives on Operations at `/dash/operations#poolrad`; the former
`/dash/poolrad` route redirects there after authentication, and its separate
navigation entry is removed. The headline preserves strict-C and identity counts
against the labelled CEILING; published scoped comparisons, source status,
commit and timestamps live in the same visible reference. Comparison rows
remain labelled as reported in source and not rerun by the dashboard.
Recorded replacements are read from the exact checkpoint commit; an absent
record remains unknown instead of borrowing a count from another revision.

The budget section preserves provider window names, used/remaining percentages,
measurement ages, and reset times. Old values remain visible; past-reset windows
are labelled expired and missing values stay unknown. Fixed monthly subscriptions
come from the operations database and are shown separately. Extra-usage credits
remain credits with the provider's spend-limit flag; pi's local session estimate
is explicitly neither quota nor a bill. No per-agent dollar balance is inferred.

Provider budget polling uses one policy for Claude, Codex, pi, and OpenCode Go. The desk starts all four reads immediately; pending providers say "not read yet". Successful reads are reused for 30 minutes (VP_USAGE_REFRESH_S=1800), independently of the Operations board's 30-second task/host refresh. Measurement age stays visible and is neutral until it exceeds twice the provider interval. Codex and pi are observations from local session records; refreshing them never calls a model or invents a new measurement timestamp.

Failed reads preserve the last successful value for the running service, show a named error and its failure time, and retry after 5, 10, then 30 minutes (VP_USAGE_BACKOFF_S=300,600,1800; capped at the provider interval). With no prior successful read, allowance remains unknown. Both settings are environment variables for the desk service. This policy bounds the desk's requests; independent CLI callers have their own cadence.


Historical metrics remain available through `GET /api/ops-metrics`,
`GET /api/ops-metrics/history`, and `./opsctl summary`.

### Private collector

The private collector stores timestamped observations in ignored `data/operations.sqlite3` (mode `0600`). Run `./install-ops-metrics-service.sh` to collect pane presence every minute; recent GitHub PR states and Dunking Sheep aggregate telemetry are polled at most every five minutes. Open **Operations dashboard** below Poolrad in the sidebar, or read `./opsctl summary` or authenticated `GET /api/ops-metrics`. Its **Refresh data** button calls authenticated `POST /api/ops-metrics/refresh` for a fresh sample, including external sources. The summary gives source ages and leaves unavailable sources unavailable. Pane presence is not verified coding output; recent PRs are not a whole-game denominator.

The Operations overview reads exact published accounting on one GitHub main commit. The reviewed 815-body upper bound yields minimum function coverage, not whole-game completion. Completion per hour appears only after two comparable checkpoints at least one hour apart; a missing interval remains unknown. The hourly price is owner-reported fixed monthly subscriptions divided by calendar hours in the current month, excluding usage charges and actual coder hours. See `docs/operations-sources.md` for definitions.

Record direct quota readings with `./opsctl quota --provider codex|claude --pane PANE --left PERCENT --reset ISO_TIME --observed-at ISO_TIME --evidence SOURCE`. The Operations dashboard shows separate Codex and Claude weekly percentages, observation ages, and reset times; an unobserved provider remains unavailable. Record owner-reported fixed costs with `./opsctl subscription --provider PROVIDER --monthly-usd AMOUNT --evidence SOURCE`. Record scoped checkpoints with `./opsctl goal --key KEY --scope local|overall --status STATUS --evidence SOURCE`, and private role assignments with `./opsctl lane --pane PANE --role pm|coder|reviewer|other --focus DESCRIPTION`. Subscription totals are separate from usage; token and additional usage charges stay unknown until a billing source is available. Dunking Sheep telemetry is accepted only as aggregate schema-versioned data, with message content rejected.

For an isolated Codex trial, run `python3 codex_usage.py SESSION.jsonl` immediately before sending work and again after the last completed turn. Save both printed token event indices. Then run `python3 codex_usage.py SESSION.jsonl --start-index START --end-index END` to obtain exact counter deltas and a `usage_source` reference for `./opsctl trial`. The anchors must bracket only that trial in the same session; a wall-clock range alone is insufficient. The reader rejects counter resets. Token counts are usage evidence, not dollar charges; leave `--metered-usd` empty until a billing source exists.

For an isolated Claude trial, run `python3 claude_usage.py SESSION.jsonl` before and after the work, then `python3 claude_usage.py SESSION.jsonl --start-index START --end-index END`. Its message indices bracket the trial; repeated JSONL records with the same API message ID count once. It reports uncached input, cache write, cache read, output, and their total input. It refuses conflicting duplicate records or a mixed-model interval. Record `total_input_tokens` and `output_tokens` with the returned `usage_source` in `./opsctl trial`. Spawned agents with separate session logs require their own usage records; this single-session result is not a whole-trial total when they participate. These are token usage, not billed dollars; leave `--metered-usd` empty without a billing source.

When PM records an accepted body without a trial ID, Operations inherits the trial from an authored event only for the same original function and exact source head. This also applies when the authored event is imported after the acceptance. A changed head remains unattributed until the reviewer supplies a verified trial ID; model efficiency must not infer it from timing alone.

## Telegram

Create a private bot with [@BotFather](https://t.me/BotFather), then run `./telegram-bridge setup` locally and paste the token at the hidden prompt. Run `./install-telegram-service.sh`, then DM the bot the `/pair` command printed by setup. The token and one-chat pairing stay in ignored `data/telegram.json` (mode `0600`); `./telegram-bridge status` shows pairing without revealing secrets.

The bridge uses outbound long polling, forwards text/photos/files to the Chief of Staff (cos) channel by default, and sends that channel’s new replies and attachments back to the paired chat.

Set `VP_TELEGRAM_CHANNEL=vp` in a vp-telegram.service environment override to route both directions to VP instead; the environment value takes precedence over the channel in the local, nonsecret data/telegram-routing.json, then defaults to cos. Both bridge and watchdog import the single dunk_telegram_routing.resolve_telegram_channel reader from Dunking Sheep. After independent review, first install/merge Dunking Sheep PR47 into the DS checkout, then run DUNKING_SHEEP_DIR=/absolute/path/to/dunkingsheep ./install-telegram-service.sh from the deployed desk tree. The installer refuses before changing the unit if dunk_telegram_routing.py is missing, and writes both DUNKING_SHEEP_DIR and PYTHONPATH into the generated service unit. It defaults to the sibling dunkingsheep checkout; no package copy or second resolver is used. There is no duplicate fallback reader if that dependency is missing. The VP desk channel remains independently usable.

`DUNKING_SHEEP_DIR` selects the desk's Dunking Sheep dependency checkout; `DUNKINGSHEEP_DIR` selects Dunking Sheep's configuration directory (default `~/.config/dunkingsheep`).

Use the same routing directory, VP_CHANNELS_FILE registry override (if any), and VP_TELEGRAM_CHANNEL environment override for bridge and watchdog. Restart both after changing the route. The routing file may be absent (shared default cos), empty {}, or contain only {"channel":"vp"} (or another configured desk ID); it contains no token or pairing information. Keep it local with mode0600. The bridge refuses an old channel setting in credential-only telegram.json: move that field to telegram-routing.json before restart, leaving credentials untouched. A channel switch starts forwarding at the destination’s current tail, so historical replies and any unfinished send from the previous channel are not replayed; subsequent replies are forwarded. Pairing and the inbound Telegram update offset are preserved, and a retried incoming update is deduplicated across channels. The status command reports the configured channel and the forwarding cursor’s channel without credentials. The nonsecret telegram-status.json includes channel; delivery-health consumers must match both channel and brief ID. Telegram's hosted Bot API limits downloads to 20 MB; use the web desk for larger files. Do not run a second poller or configure a webhook for this bot.

Terminals also lists detected agent processes without a desk pane route, with workspace, PID, routing reason and session-write age where a single open session file identifies it. This inventory reads local process metadata and file mtimes, never session contents. Missing ages remain unknown; process presence is not evidence of active work. Codex app-server processes are excluded, and unknown harnesses are not inferred from prompt text. An unavailable inventory is shown as unavailable rather than an empty success.

Owner #1702: every former disclosure is now an always-visible section. Operations keeps all task rows visible, with blocked, owner-assigned and in-progress tasks first; project lanes and evidence also require no expansion.
Incoming messages follow the newest message only while the reader remains at the bottom. Scrolling up in either a channel chat or Play's VP chat preserves the reading position and shows a New messages button; pressing it resumes following. Channel navigation starts at the newest message. Already-loaded messages remain present when the server's polling window advances, so an incoming message does not remove the history currently being read.
Press Ctrl+/ (Cmd+/ on macOS), or select Message CoS / VP in the navigation, to open the global message dock from any desk page. Choose the recipient and send through the same direct pane endpoint used by channel chat. Drafts are separate per recipient, Escape closes the dock and restores focus, and the receipt displays the returned outcome with a link to the stored conversation.
