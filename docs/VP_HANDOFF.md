# VP handoff and restart

## Start another model or harness

1. Stop or park the previous **VP agent pane** so only one agent handles owner messages. Leave the web, Telegram, metrics, and host-watch services running.
2. Open a new agent pane in Herdr with your chosen harness (Codex, Claude, OpenCode, or another model). Set its working directory to `/home/hunter/workspace/vp-of-agentry` and a clear tab label such as `VP of Agentry`. A new pane is automatically discovered by the web desk; update ignored `channels.json` if you want the stable `vp` channel to point to a different tab label.
3. Paste the takeover prompt below. The new agent should read this repository, the VP inbox, and Dunking Sheep's existing auto-dunks before replying. Check `./vpctl status`, `./telegram-bridge status`, `python3 host_watch.py --status`, `df -h /tmp`, `df -i /tmp`, and `systemctl --user --failed` without opening or printing credential files.
4. Open the VP web desk and refresh. Its channel roster is rebuilt from Dunking Sheep live panes on page load and every 12 seconds. Confirm the new VP pane is active and the old pane is idle or absent. Retarget the existing hourly VP Dunking Sheep reminder (`d50` on this host; find it by name if its ID changes) to the new VP pane. Post a short `./vpctl brief --channel vp` and confirm `./telegram-bridge status` advanced `last_brief_id`. The local bridge forwards the same web brief to Telegram; do not send a duplicate Telegram update.

Takeover prompt:

> You are the owner's VP of Agentry. Your workspace is `/home/hunter/workspace/vp-of-agentry`. Read `AGENTS.md`, `README.md`, and `docs/VP_HANDOFF.md`; then pair with Dunking Sheep: read the VP inbox, inspect live panes, and review existing auto-dunks. Dunking Sheep is the beating heart of this system; retarget its hourly VP reminder to your pane, put recurring VP actions into direct auto-dunks and recurring instructions for other agents into scheduled inbox delivery, and avoid duplicate prompts. At takeover and on every VP check-in, inspect `python3 host_watch.py --status`, `df -h /tmp`, `df -i /tmp`, `systemctl --user --failed`, and the VP/Telegram/metrics/watch services; investigate stale processes or temporary files when readings warrant it, preserving unpublished work. Continue outstanding agent and project work. Publish one owner update through `./vpctl brief --channel vp`; the local `vp-telegram.service` bridge forwards it from the web desk to the paired Telegram chat. Verify `./telegram-bridge status` advanced `last_brief_id`; do not send a duplicate Telegram message or expose the bot token. Keep secrets and machine-specific private data out of Git. Before debugging, run `dunkingsheep memory recall "<query>"` and cite reused findings. Use fresh Los Angeles timestamps per `AGENTS.md`.

## Local services and state

| What | Check | Restart if needed |
| --- | --- | --- |
| VP web desk | `./vpctl status` | `systemctl --user restart vp-of-agentry.service` |
| Telegram bridge | `./telegram-bridge status` | `systemctl --user restart vp-telegram.service` |
| Operations collector | `./opsctl summary` | `systemctl --user start vp-ops-metrics.service`; timer: `vp-ops-metrics.timer` |
| Host watch | `python3 host_watch.py --status` | `systemctl --user start vp-host-watch.service`; timer: `vp-host-watch.timer` |
| Agent panes/inbox | `dunkingsheep panes` and `dunkingsheep inbox read` | use Herdr/Dunking Sheep to relaunch the agent; do not start a second web or Telegram poller |

The private data under `data/`, ignored `channels.json`, and local Dunking Sheep/Herdr state are needed for continuity on this host. They are not in Git. Keep their permissions private, do not print their contents into logs, and back them up through an owner-approved private path if moving machines. On a fresh host, run `./run.sh`, then the install scripts described in [README.md](../README.md), set up Telegram locally, and restore private state only through a secure channel.

## Current priorities and checks

- Poolrad Claude Fable: substantive C ports, independently verified evidence, weekly allowance stop at 5% remaining. Ask for the current direct quota reading; do not derive it from dollars.
- Poolrad OpenCode: independent strict candidate queue lane in its clean checkout; deliver one PR with ranked candidates and regression examples.
- Dashboard: the live roster refreshes automatically; Operations shows fixed subscriptions and separate OpenCode model-cost estimate. Check source age before quoting a metric.
- Host: inspect `/tmp`, free space, stuck processes, and old checkouts. Preserve unpublished branches and files before removing a checkout.

The VP inbox and latest `./opsctl summary` supersede this snapshot when state changes.

## Recurring work in Dunking Sheep

Review the current dunk list at takeover. Keep one recurring VP self-reminder for host health, project state, agent deliverables, quota, and a concise owner brief. Schedule repeated work prompts to other agents through their durable inbox when available, with a cadence and stop condition. Prefer `only_when="idle"` and `skip_if_unconsumed=true`; remove a dunk when its task is complete. The service timers sample health and metrics, while Dunking Sheep turns those observations into agent action across harness restarts.

When sending any agent a durable `inbox_send`, Dunking Sheep also sends its own short direct nudge to check the inbox. Do not add a separate `send_text` or other direct prompt for that same item. Check the inbox message ID and read/ack state instead. This avoids duplicate work and interrupted inputs.

## Evidence discipline (learned 2026-10-20, one-night tally)

These are VP-side failures, not lane failures. Each cost a cycle and each is now a rule.

- **A number is not the quantity in the sentence.** Seven claims had to be withdrawn in one night, all the same move: reading a measurement as if it established the mechanism named in the prose. Examples: scheduled CPU time minus sparse GPU intervals read as critical-path slack; a 606,042 ns aggregate probe gap compared against a ~1 ms/frame effect; per-thread counters read as thread locality when they are attaching-thread lineages; a stack-attributed bucket sum called "optimisable"; a hand-remembered "no family above 1.2 ms" contradicted by the lane's own aggregates. Check the artifact, not the summary - including this file.
- **Pre-register the decision rule before the result.** For the 8-page invalidation experiment the pass/fail rule (favourable sign in both arms and effect larger than each arm's drift) was written to `PAIR2-DECISION-RULE.json` before the second pair produced numbers, and the second pair then failed it. Run without that, the same data would have been reported as a win.
- **An operator's own recurring prompt is a source of stale work.** A `dunkingsheep` reminder still carrying a closed priority list made a lane re-derive already-merged PRs twice. Rewrite or retire the prompt when the list closes; a recurring instruction is code and needs the same review.
- **Your prose about an agent's numbers is less reliable than their artifacts.** After this night the standing rule is: when summarising a lane's result for the owner, quote the artifact's own wording, or say that you are paraphrasing.
- **Stated limits belong in the document carrying the claim.** Masked ranges with byte counts, coverage gaps with named unexercised paths, lineage-vs-thread attribution, unknown missing-event counts, and model-vs-measurement asymptotes each go next to the number they qualify, never in a footnote or a chat message.

When a lane corrects you, adopt the correction in the document the owner reads - do not defend the version already published.
