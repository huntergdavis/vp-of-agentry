#!/usr/bin/env python3
"""Reply-latency leaderboard for every agent with a mailbox. Timestamps only, no model.

Source: Dunking Sheep inbox.db, one row per pane (mail addressed by name or by
pane id is the same agent seat; a pane reused by a new agent keeps its row and
takes the newest name). For each message delivered to a mailbox, the
interval from arrival (created_at) to the mailbox owner's first owned action on
it: read (read_at) or acknowledge (acked_at), whichever came first. Only the
owner reads its own inbox, so both are the agent's actions. A reply in the
outbox is not used: messages carry no thread id, so a reply cannot be matched
to the message it answers without guessing.

Window: messages that arrived in the last 24 h. Percentiles are nearest rank,
the same method as the owner-channel reply latency.

Unhandled: arrived in the window, never read or acked, not cancelled or
archived. Silent: every open unhandled message (any age) older than 3x the
agent's own p50; an agent with no handled message has no median, so all its
open messages count as silent and the row says so.
"""

from __future__ import annotations

import json
import os
import re
import sqlite3
import subprocess
import time
from datetime import datetime, timezone
from pathlib import Path

DUNK_DIR = Path(os.environ.get("DUNKINGSHEEP_DIR", "/home/hunter/.config/dunkingsheep"))
WINDOW_S = 24 * 3600
MIN_RANKED = 5  # fewer handled messages than this are listed, not ranked
SILENT_FACTOR = 3


def iso(epoch):
    return (datetime.fromtimestamp(epoch, timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
            if isinstance(epoch, (int, float)) else None)


def cell(value, as_of, reason=None):
    return {"value": value, "as_of": iso(as_of) if as_of else None, "reason": reason}


def failed(reason):
    return cell(None, None, reason)


def nearest_rank(values, q):
    ordered = sorted(values)
    return ordered[min(len(ordered) - 1, int(round(q * (len(ordered) - 1))))]


PANE = re.compile(r"\b(w[0-9A-Za-z]+:p[0-9A-Za-z]+)\b")


def seat(pane_id, mailbox, label):
    """The pane an agent sits in: the recorded pane id, else one named in the mailbox or label."""
    if pane_id:
        return pane_id
    for text in (mailbox, label):
        found = PANE.search(text or "")
        if found:
            return found.group(1)
    return mailbox


def live_panes(runner=None):
    argv = [os.environ.get("DUNKINGSHEEP_BIN", "dunkingsheep"), "--json", "panes"]
    try:
        out = runner(argv) if runner else subprocess.run(argv, capture_output=True, text=True, timeout=30).stdout
        data = json.loads(out)
    except (OSError, subprocess.SubprocessError, ValueError):
        return None
    panes = data if isinstance(data, list) else (data or {}).get("panes") or []
    return {p.get("pane_id") for p in panes if isinstance(p, dict)}


def collect(dunk_dir=None, *, now=None, runner=None):
    path = Path(dunk_dir or DUNK_DIR) / "inbox.db"
    now = now or time.time()
    if not path.is_file():
        return {"status": "nulled", "reason": f"{path} absent", "rows": [], "as_of": iso(now)}
    since = now - WINDOW_S
    try:
        with sqlite3.connect(f"file:{path}?mode=ro", uri=True, timeout=2) as conn:
            rows = conn.execute(
                "SELECT id, pane_id, mailbox_label, mailbox, created_at, read_at, acked_at, "
                "cancelled_at, archived_at, state FROM messages WHERE created_at >= ? OR "
                "(read_at IS NULL AND acked_at IS NULL AND cancelled_at IS NULL AND archived_at IS NULL "
                "AND state != 'cancelled')", (since,)).fetchall()
    except sqlite3.Error as exc:
        return {"status": "nulled", "reason": f"{path}: {exc}", "rows": [], "as_of": iso(now)}
    agents = {}
    # One agent seat is one pane: mail addressed by name and mail addressed by
    # pane id land in the same row. The label is the newest human name seen.
    for ident, pane_id, label, name, created, read, acked, cancelled, archived, state in sorted(rows, key=lambda r: r[4]):
        mailbox = seat(pane_id, name, label)
        entry = agents.setdefault(mailbox, {"label": None, "waits": [], "unhandled": 0, "open": []})
        if label and label != mailbox:
            entry["label"] = label
        elif name and name != mailbox and not entry["label"]:
            entry["label"] = f"{name} ({mailbox})"
        actions = [t for t in (read, acked) if isinstance(t, (int, float)) and t >= created]
        closed = cancelled is not None or archived is not None or state == "cancelled"
        if actions and created >= since:
            entry["waits"].append(min(actions) - created)
        elif not actions and not closed:
            entry["open"].append((created, ident))
            if created >= since:
                entry["unhandled"] += 1
    if dunk_dir is not None and runner is None and Path(dunk_dir).resolve() != DUNK_DIR.resolve():
        live = None  # the CLI reports the default daemon, not this store
    else:
        live = live_panes(runner)
    out = []
    for mailbox, entry in agents.items():
        waits = entry["waits"]
        p50 = nearest_rank(waits, .5) if waits else None
        no_traffic = "no messages handled in window"
        if p50 is not None:
            threshold = SILENT_FACTOR * p50
            silent = [(c, i) for c, i in entry["open"] if now - c > threshold]
            silent_rule = f"open longer than {SILENT_FACTOR}x its p50 ({round(threshold)} s)"
        else:
            silent = list(entry["open"])
            silent_rule = "no handled message to set a median: every open message counts as silent"
        oldest = min(silent) if silent else None
        if not waits and not entry["open"] and not entry["unhandled"]:
            continue  # nothing arrived in the window and nothing is open
        out.append({
            "mailbox": mailbox, "label": entry["label"] or mailbox,
            "handled": cell(len(waits), now),
            "p50_s": cell(round(p50, 1), now) if waits else failed(no_traffic),
            "p90_s": cell(round(nearest_rank(waits, .9), 1), now) if waits else failed(no_traffic),
            "max_s": cell(round(max(waits), 1), now) if waits else failed(no_traffic),
            "unhandled_24h": cell(entry["unhandled"], now),
            "silent": cell(len(silent), now),
            "silent_rule": silent_rule,
            "oldest_silent": {"id": oldest[1], "age_s": round(now - oldest[0])} if oldest else None,
            "pane_open": (mailbox in live) if live is not None else None,
            "ranked": len(waits) >= MIN_RANKED and (live is None or mailbox in live),
        })
    out.sort(key=lambda r: (not r["ranked"], r["pane_open"] is False, r["p50_s"]["value"] is None,
                            r["p50_s"]["value"] if r["p50_s"]["value"] is not None else 0, -r["handled"]["value"]))
    return {
        "status": "ok", "as_of": iso(now), "source": f"{path} (created_at -> first of read_at, acked_at)",
        "window": "messages that arrived in the last 24 h; nearest-rank percentiles",
        "rows": out,
        "panes_reason": None if live is not None else "pane list unreadable: open/closed unknown",
        "method": f"Ranked by p50 among agents with at least {MIN_RANKED} handled messages; the rest are listed "
                  "below, unranked. Silent counts open messages of any age.",
        "deterministic": "Computed from message timestamps, no model involved.",
        "truth": "First read or ack is the agent seeing the message, not finishing the work. A reply cannot be "
                 "matched to its message (no thread id), so replies are not used.",
    }


if __name__ == "__main__":
    import json
    print(json.dumps(collect(), indent=2))
