# VP of Agentry

A private LAN desk for the owner's existing Herdr agents. Messages use Dunking Sheep's durable inbox where the agent has a unique mailbox; generic shared mailboxes use guarded exact-pane delivery. The website does not start a new model session.

## Run

```bash
./run.sh                    # first run installs dependencies and builds the UI
./install-service.sh        # optional: keep it running with systemd
./vpctl status              # health check
```

Open `http://<LAN-host>:8787`. The initial password and API token are in ignored `data/owner-credentials` (mode `0600`). Change the password with the gear icon, or edit that file's `Password:` line; the next sign-in applies a newer file. The API token is preserved. Set `VP_BIND`, `VP_PORT`, or `DUNKING_SHEEP_DIR` if needed. Access this HTTP app only on a trusted LAN or VPN.

## Channels

Copy `channels.example.json` to `channels.json` and edit the local file for your agents. `channels.json` is Git ignored; the checked-in example contains only generic labels. Each entry needs a unique `id`, display `name`, Herdr pane label `match`, and `kind` (`active`, `standby`, or `monitor`). Add `"dashboard": true` to the channel linked from the project dashboard. The server reads the local file at startup and uses the generic example if no local file exists. Set `VP_CHANNELS_FILE` to use a different private file; an explicit missing path is an error. Restart the service after edits.

## Delivery

Enter sends; Shift+Enter adds a line. Messages and uploads (up to 25 MB each) are saved in ignored `data/` and copied into a unique agent inbox when available. The chat shows **in inbox**, **read**, and **handled** as the agent processes them; state is checked every five seconds. Shared generic mailboxes use the guarded pane queue, and show **queued** or **sent**. A timeout is marked **delivery uncertain** and never resent automatically.

Agents post durable Markdown replies with `echo 'Brief' | ./vpctl brief --channel vp`; add `--attach /path/to/image.png` to include a private image. The right panel shows recent, volatile `read_pane` output; search covers stored website messages and posted briefs. The owner Bearer token works with the same API. A browser tab opened before an upgrade needs one refresh; newer tabs show an update notice.

Host health monitoring: `./install-host-watch-service.sh` installs a separate user timer that samples `/tmp` capacity, inode use, and host load every minute. It sends a private VP inbox alert only when a threshold changes; owner briefs stay on the hourly cadence. `/tmp` warns at 60% used, 2 GiB free, or 70% of inodes; critical begins at 85% used, 0.75 GiB free, or 90% of inodes. Load warns after three spaced high samples and becomes critical after two spaced extreme samples. `python3 host_watch.py --status` shows the last saved sample; `--dry-run` samples without alerting. The monitor does not remove files.

The UI reuses MIT licensed [ChatScope](https://github.com/chatscope/chat-ui-kit-react), [Tiptap](https://github.com/ueberdosis/tiptap), [Turndown](https://github.com/mixmark-io/turndown), and [react-markdown](https://github.com/remarkjs/react-markdown). Open WebUI and LibreChat were evaluated, but their model-provider paths need an adapter to target a running Herdr pane and local guarded queue.

## Poolrad dashboard

Choose **Poolrad dashboard** in the desk sidebar to see bounded function coverage, the playable demo gate, and collapsed evidence. **Refresh snapshot** regenerates the view from the configured local Poolrad checkout; it does not rerun verification. The source commit and generation time appear inside the view, and a verification from a different commit is marked stale.

The VP server uses `POOLRAD_DASHBOARD_DIR` if the dashboard is outside the default sibling `poolrad-decomp/tools/dashboard` location. Only the generated page and cited public report copies are served through authenticated routes. The embedded view runs in a sandboxed frame. The full candidate list remains in the ignored research snapshot; PM assignments come from separate workstream and source-gate queues. The list does not award strict C credit.

Checks: `.venv/bin/python -m unittest discover -s tests -p 'test_*.py' -v`; authenticated browser check: `VP_TEST_SEND=1 .venv/bin/python tests/browser_smoke.py` (requires Playwright).

## Operations metrics

The private collector stores timestamped observations in ignored `data/operations.sqlite3` (mode `0600`). Run `./install-ops-metrics-service.sh` to collect pane presence every minute; recent GitHub PR states and Dunking Sheep aggregate telemetry are polled at most every five minutes. Open **Operations dashboard** below Poolrad in the sidebar, or read `./opsctl summary` or authenticated `GET /api/ops-metrics`. Its **Refresh data** button calls authenticated `POST /api/ops-metrics/refresh` for a fresh sample, including external sources. The summary gives source ages and leaves unavailable sources unavailable. Pane presence is not verified coding output; recent PRs are not a whole-game denominator.

The Operations overview reads exact published accounting on one GitHub main commit. The reviewed 815-body upper bound yields minimum function coverage, not whole-game completion. Completion per hour appears only after two comparable checkpoints at least one hour apart; a missing interval remains unknown. The hourly price is owner-reported fixed monthly subscriptions divided by calendar hours in the current month, excluding usage charges and actual coder hours. See `docs/operations-sources.md` for definitions.

Record direct quota readings with `./opsctl quota --provider codex|claude --pane PANE --left PERCENT --reset ISO_TIME --observed-at ISO_TIME --evidence SOURCE`. The Operations dashboard shows separate Codex and Claude weekly percentages, observation ages, and reset times; an unobserved provider remains unavailable. Record owner-reported fixed costs with `./opsctl subscription --provider PROVIDER --monthly-usd AMOUNT --evidence SOURCE`. Record scoped checkpoints with `./opsctl goal --key KEY --scope local|overall --status STATUS --evidence SOURCE`, and private role assignments with `./opsctl lane --pane PANE --role pm|coder|reviewer|other --focus DESCRIPTION`. Subscription totals are separate from usage; token and additional usage charges stay unknown until a billing source is available. Dunking Sheep telemetry is accepted only as aggregate schema-versioned data, with message content rejected.

## Telegram

Create a private bot with [@BotFather](https://t.me/BotFather), then run `./telegram-bridge setup` locally and paste the token at the hidden prompt. Run `./install-telegram-service.sh`, then DM the bot the `/pair` command printed by setup. The token and one-chat pairing stay in ignored `data/telegram.json` (mode `0600`); `./telegram-bridge status` shows pairing without revealing secrets. The bridge uses outbound long polling, forwards text/photos/files to the VP inbox, and sends new VP briefs and attachments back to the paired chat. Telegram's hosted Bot API limits downloads to 20 MB; use the web desk for larger files. Do not run a second poller or configure a webhook for this bot.
