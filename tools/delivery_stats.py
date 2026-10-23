#!/usr/bin/env python3
"""Current dunks, inbox metrics and delivery health from Dunking Sheep (owner #1358).

No model. Sources, in order of preference:
- the daemon's live view (`dunkingsheep --json list` / `--json messages`), which
  carries the runtime state (held typing, queued reason) the files do not;
- its stores when the daemon cannot answer: dunks.json, inbox.db, metrics.db.

Every section names its source and as_of. A source that cannot be read is null
with the reason, never a zero.

Arrival -> delivery is the metrics `message.sent` duration: from the moment a
pane notice was queued to the moment its text was confirmed submitted. A
notice still waiting has no duration yet; it is reported beside the
percentiles as "still waiting", because a stall that has not finished would
otherwise be invisible in a distribution of finished sends.
"""

from __future__ import annotations

import json
import os
import sqlite3
import subprocess
import time
from datetime import datetime, timezone
from pathlib import Path

DUNK_DIR = Path(os.environ.get("DUNKINGSHEEP_DIR", "/home/hunter/.config/dunkingsheep"))
WINDOW_S = 24 * 3600


def iso(epoch):
    return (datetime.fromtimestamp(epoch, timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
            if isinstance(epoch, (int, float)) else None)


def cell(value, as_of, reason=None):
    return {"value": value, "as_of": iso(as_of) if as_of else None, "reason": reason}


def failed(reason):
    return cell(None, None, reason)


def nearest_rank(values, q):
    """Same method as reply_latency: nearest-rank on the sorted list."""
    if not values:
        return None
    ordered = sorted(values)
    return ordered[min(len(ordered) - 1, int(round(q * (len(ordered) - 1))))]


def daemon_json(args, runner=None):
    """One CLI read. The CLI coalesces bursts into a placeholder dict; retry once."""
    argv = [os.environ.get("DUNKINGSHEEP_BIN", "dunkingsheep"), "--json", *args]
    run = runner or (lambda a: subprocess.run(a, capture_output=True, text=True, timeout=30).stdout)
    for attempt in range(2):
        try:
            data = json.loads(run(argv) or "null")
        except (OSError, subprocess.SubprocessError, ValueError) as exc:
            return None, f"dunkingsheep {' '.join(args)}: {type(exc).__name__}"
        if isinstance(data, dict) and data.get("coalesced"):
            if attempt == 0:
                time.sleep(float(data.get("interval_s") or 2) + 0.5)
                continue
            return None, f"dunkingsheep {' '.join(args)}: coalesced twice, no fresh answer"
        return data, None
    return None, "unreachable"


def read_store(dunk_dir):
    path = Path(dunk_dir) / "dunks.json"
    try:
        return json.loads(path.read_text()), path.stat().st_mtime, None
    except (OSError, ValueError) as exc:
        return None, None, f"{path}: {exc}"


def gate(dunk):
    parts = []
    if dunk.get("only_when"):
        parts.append(f"{dunk['only_when']}-only")
    if dunk.get("hold_while_typing"):
        parts.append("holds while typing")
    if dunk.get("skip_if_unconsumed"):
        parts.append("skip-if-unconsumed")
    return parts


def dunk_state(dunk, now):
    """The daemon's status word when we have it; otherwise derived and labelled so."""
    status = dunk.get("status")
    if status and not status.startswith("Next"):
        return status, "daemon"
    if status:
        # "Next: 78:04" is a countdown at read time; the page shows next_send_at instead.
        return "scheduled", "daemon"
    if not dunk.get("running"):
        return "stopped", "derived"
    due = dunk.get("next_send_at")
    if isinstance(due, (int, float)) and due < now:
        return f"overdue {round((now - due) / 60)} min (held {dunk.get('hold_count') or 0}x)", "derived"
    return "scheduled", "derived"


def collect_dunks(dunk_dir, now, runner=None):
    live, live_reason = daemon_json(["list"], runner)
    if isinstance(live, dict) and isinstance(live.get("dunks"), list):
        live = live["dunks"]
    elif live is not None and not isinstance(live, list):
        live, live_reason = None, "dunkingsheep --json list: unexpected shape"
    store, store_at, store_reason = read_store(dunk_dir)
    if isinstance(live, list):
        dunks, source, as_of = live, "dunkingsheep --json list (daemon)", now
    elif store is not None:
        dunks = store.get("dunkers") or []
        source, as_of = f"{Path(dunk_dir) / 'dunks.json'} (daemon view unavailable: {live_reason})", store_at
    else:
        return {"status": "nulled", "reason": f"{live_reason}; {store_reason}", "rows": [],
                "as_of": None, "source": None}
    rows = []
    for d in dunks:
        state, state_source = dunk_state(d, now)
        rows.append({
            "id": d.get("id"), "name": d.get("name"),
            "target": {"pane": d.get("target_pane_id"), "label": d.get("target_tab"),
                       "workspace": d.get("target_workspace"), "agent": d.get("target_agent")},
            "running": bool(d.get("running")),
            "every_min": d.get("interval_minutes"),
            "max_sends": d.get("max_sends"), "sent": d.get("send_count"),
            "skips": d.get("total_skips"), "holds": d.get("hold_count"),
            "last_sent_at": iso(d.get("last_sent_at")),
            "next_send_at": iso(d.get("next_send_at")) if d.get("running") else None,
            "last_held_at": iso(d.get("last_held_at")),
            "awaiting_consumption": d.get("awaiting_consumption"),
            "overdue_min": (round((now - d["next_send_at"]) / 60)
                            if d.get("running") and isinstance(d.get("next_send_at"), (int, float))
                            and d["next_send_at"] < now else None),
            "gate": gate(d), "state": state, "state_source": state_source,
            "last_error": d.get("last_error"),
            "text": (d.get("text") or "")[:240],
        })
    rows.sort(key=lambda r: (not r["running"], r["id"] or ""))
    return {"status": "ok", "as_of": iso(as_of), "source": source, "rows": rows,
            "count": cell(len(rows), as_of),
            "truth": "Every dunk the daemon holds, running or not. 'Next' is the schedule, not a "
                     "promise: idle-only and hold-while-typing gates can delay a send."}


def collect_inbox(dunk_dir, now):
    path = Path(dunk_dir) / "inbox.db"
    if not path.is_file():
        return {"status": "nulled", "reason": f"{path} absent", "mailboxes": [], "as_of": None}
    since = now - WINDOW_S
    try:
        with sqlite3.connect(f"file:{path}?mode=ro", uri=True, timeout=2) as conn:
            unread = conn.execute(
                "SELECT COALESCE(mailbox_label, mailbox), COUNT(*), MIN(created_at) FROM messages "
                "WHERE read_at IS NULL AND cancelled_at IS NULL AND archived_at IS NULL "
                "AND state != 'cancelled' GROUP BY 1").fetchall()
            flow = conn.execute(
                "SELECT COALESCE(mailbox_label, mailbox), COALESCE(notify_state, 'none'), COUNT(*) "
                "FROM messages WHERE created_at >= ? GROUP BY 1, 2", (since,)).fetchall()
    except sqlite3.Error as exc:
        return {"status": "nulled", "reason": f"{path}: {exc}", "mailboxes": [], "as_of": None}
    boxes = {}

    def box(name):
        return boxes.setdefault(name, {"mailbox": name, "unread": 0, "oldest_unread_h": None,
                                       "arrived_24h": 0, "notice": {}})
    for name, count, oldest in unread:
        entry = box(name)
        entry["unread"] = count
        entry["oldest_unread_h"] = round((now - oldest) / 3600, 1) if oldest else None
    for name, notify, count in flow:
        entry = box(name)
        entry["arrived_24h"] += count
        entry["notice"][notify] = entry["notice"].get(notify, 0) + count
    mailboxes = sorted(boxes.values(), key=lambda b: (-b["unread"], b["mailbox"]))
    for entry in mailboxes:
        for key in ("unread", "oldest_unread_h", "arrived_24h"):
            entry[key] = cell(entry[key], now)
    total_notice = {}
    for entry in mailboxes:
        for k, v in entry["notice"].items():
            total_notice[k] = total_notice.get(k, 0) + v
    return {"status": "ok", "as_of": iso(now), "source": str(path), "mailboxes": mailboxes,
            "total": {"unread": cell(sum(b["unread"]["value"] for b in mailboxes), now),
                      "oldest_unread_h": cell(max((b["oldest_unread_h"]["value"] or 0) for b in mailboxes)
                                              if mailboxes else None, now),
                      "arrived_24h": cell(sum(b["arrived_24h"]["value"] for b in mailboxes), now),
                      "notice": total_notice},
            "truth": "Unread is every message not yet opened, at any age. Notice states count the pane "
                     "nudge for messages that arrived in 24 h: sent = typed and submitted, queued = "
                     "still waiting for the pane, failed = typed but not submitted, none = no nudge."}


def collect_latency(dunk_dir, now, queued):
    path = Path(dunk_dir) / "metrics.db"
    if not path.is_file():
        return {"status": "nulled", "reason": f"{path} absent", "as_of": None}
    since = now - WINDOW_S
    try:
        with sqlite3.connect(f"file:{path}?mode=ro", uri=True, timeout=2) as conn:
            rows = conn.execute(
                "SELECT mailbox, duration_ms FROM events WHERE kind='message.sent' AND at >= ? "
                "AND duration_ms IS NOT NULL", (since,)).fetchall()
            holds = conn.execute(
                "SELECT kind, COALESCE(reason, 'unstated'), COUNT(*) FROM events "
                "WHERE kind IN ('message.held', 'dunk.held') AND at >= ? GROUP BY 1, 2 "
                "ORDER BY 3 DESC", (since,)).fetchall()
            failures = conn.execute(
                "SELECT COUNT(*) FROM events WHERE kind='message.failed' AND at >= ?",
                (since,)).fetchone()[0]
    except sqlite3.Error as exc:
        return {"status": "nulled", "reason": f"{path}: {exc}", "as_of": None}

    def dist(values):
        seconds = [v / 1000 for v in values]
        return {"n": cell(len(seconds), now),
                "p50_s": cell(round(nearest_rank(seconds, .5), 1), now) if seconds else failed("no finished sends in 24 h"),
                "p90_s": cell(round(nearest_rank(seconds, .9), 1), now) if seconds else failed("no finished sends in 24 h"),
                "max_s": cell(round(max(seconds), 1), now) if seconds else failed("no finished sends in 24 h")}
    per = {}
    for mailbox, ms in rows:
        per.setdefault(mailbox or "unlabelled", []).append(ms)
    waits = [q.get("waiting_s") for q in (queued or []) if isinstance(q.get("waiting_s"), (int, float))]
    return {"status": "ok", "as_of": iso(now), "source": f"{path} (kind=message.sent, duration_ms)",
            "window": "last 24 h, nearest-rank percentiles",
            "all": dist([ms for _, ms in rows]),
            "per_mailbox": [{"mailbox": m, **dist(v)} for m, v in
                            sorted(per.items(), key=lambda kv: -max(kv[1]))],
            "still_waiting": {"n": cell(len(waits), now) if queued is not None else failed("daemon queue unreadable"),
                              "oldest_s": cell(round(max(waits)), now) if waits else
                              (cell(None, now, "nothing waiting") if queued is not None else failed("daemon queue unreadable"))},
            "failed_24h": cell(failures, now),
            "holds_24h": [{"kind": k, "reason": r, "count": cell(c, now)} for k, r, c in holds],
            "truth": "Percentiles cover sends that finished. A notice still in the queue is not in them; "
                     "it is counted under still waiting with its age so far."}


def classify_hold(message, live_panes):
    text = (message.get("message") or message.get("detail") or "").lower()
    if live_panes is not None and message.get("pane_id") not in live_panes:
        return "dead pane"
    for word, label in (("typing", "typing"), ("draft", "draft"), ("busy", "busy claim"),
                        ("working", "busy claim"), ("strand", "stranded")):
        if word in text:
            return label
    return text or "unstated"


def collect_health(dunk_dir, now, runner=None):
    data, reason = daemon_json(["messages"], runner)
    panes, panes_reason = daemon_json(["panes"], runner)
    live = None
    if isinstance(panes, list):
        live = {p.get("pane_id") for p in panes}
    elif isinstance(panes, dict) and isinstance(panes.get("panes"), list):
        live = {p.get("pane_id") for p in panes["panes"]}
    if not isinstance(data, dict):
        store, store_at, store_reason = read_store(dunk_dir)
        if store is None:
            return {"status": "nulled", "reason": f"{reason}; {store_reason}", "held": [], "as_of": None}, None
        held = [{"message_id": m.get("id"), "pane": m.get("pane_id"), "target": m.get("target_label"),
                 "reason": "dead pane" if live is not None and m.get("pane_id") not in live else "unknown (store has no reason)",
                 "detail": None, "holds": None,
                 "waiting_s": round(now - m["created_at"]) if m.get("created_at") else None,
                 "text": (m.get("text") or "")[:160]} for m in store.get("outbox") or []]
        return {"status": "partial", "as_of": iso(store_at),
                "source": f"{Path(dunk_dir) / 'dunks.json'} outbox (daemon view unavailable: {reason})",
                "held": held, "panes_reason": panes_reason if live is None else None}, None
    queued = data.get("queued") or []
    held = [{"message_id": m.get("message_id"), "pane": m.get("pane_id"), "target": m.get("target_label"),
             "reason": classify_hold(m, live), "detail": m.get("message"), "holds": m.get("holds"),
             "waiting_s": m.get("waiting_s"), "blocked_by": m.get("blocked_by"),
             "text": (m.get("text") or "")[:160]} for m in queued]
    held.sort(key=lambda h: -(h["waiting_s"] or 0))
    return {"status": "ok", "as_of": iso(now), "source": "dunkingsheep --json messages (daemon queue)",
            "held": held, "panes_reason": panes_reason if live is None else None,
            "truth": "Each row is a nudge that has NOT reached its pane. The message is in the inbox, but "
                     "the agent has not been told. 'dead pane' means the target pane no longer exists."}, queued


def collect(dunk_dir=None, *, now=None, runner=None):
    dunk_dir = Path(dunk_dir or DUNK_DIR)
    now = now or time.time()
    if runner is None and dunk_dir.resolve() != DUNK_DIR.resolve():
        # The CLI answers for the default daemon; mixing it into another store's numbers would lie.
        def runner(argv):
            raise OSError(f"CLI skipped: it reports the default daemon, not {dunk_dir}")
    health, queued = collect_health(dunk_dir, now, runner)
    return {"dunks": collect_dunks(dunk_dir, now, runner),
            "inbox": collect_inbox(dunk_dir, now),
            "delivery_latency": collect_latency(dunk_dir, now, queued),
            "delivery_health": health}


if __name__ == "__main__":
    print(json.dumps(collect(), indent=2))
