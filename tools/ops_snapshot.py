#!/usr/bin/env python3
"""Collect one ops+poolrad snapshot (schema: docs/OPS_SNAPSHOT_SCHEMA.md).

Read-only, idempotent, no model: one paginated gh call per repo, one checkpoint
read, one query per database, one pane list. Every number is a
{value, as_of, reason} cell; a missing source is null+reason, never a zero and
never the previous snapshot.
"""

from __future__ import annotations

import csv
import json
import os
import re
import sqlite3
import subprocess
import sys
import time
from datetime import datetime, timedelta, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import agent_costs  # noqa: E402
import delivery_stats  # noqa: E402
import credit_stats  # noqa: E402
import free_leaderboard  # noqa: E402

ROOT = Path(__file__).resolve().parent.parent
SNAPSHOT = ROOT / "data" / "ops-snapshot.json"
CHECKPOINT = Path(os.environ.get(
    "POOLRAD_CHECKPOINT",
    "/home/hunter/workspace/poolrad-decomp/docs/re/function_accounting_checkpoint.json"))
DUNK_DIR = Path(os.environ.get("DUNKINGSHEEP_DIR", "/home/hunter/.config/dunkingsheep"))
TASKS_DB = DUNK_DIR / "tasks.db"
METRICS_DB = DUNK_DIR / "metrics.db"
INBOX_DB = DUNK_DIR / "inbox.db"
MESSAGES_DB = ROOT / "data" / "messages.sqlite3"
HYBRID = Path("/home/hunter/workspace/poolrad-decomp/tools/dashboard/hybrid_status.json")
CREDIT_CSV = Path("/home/hunter/workspace/poolrad-decomp/docs/re/credit_evidence_kind.csv")
CRACKDOWN_RESULT = Path("/home/hunter/workspace/crackdown-switch/discovery/shadow-mode-20261021/RESULT.txt")
HYBRID_GLUE = Path("/home/hunter/workspace/poolrad-decomp/docs/HYBRID_GLUE_BATCH1.md")
PROJECTS = {
    "poolrad": ("poolrad-decomp", "huntergdavis/poolrad-decomp"),
    "crackdown": ("crackdown-switch", "huntergdavis/crackdown-switch"),
}
WINDOW_H = 24
STRICT_CEILING = 815  # poolrad body ceiling; a ceiling, not a verified denominator
# Branch prefixes are the lane convention (caught by the forward rule). A known
# prefix is the attribution; anything else is unattributed, never guessed.
# A LANE is not a harness. 'claude' is a tool; 'par-c' is an agent. These are
# the lane tokens our branch names actually carry.
KNOWN_LANES = ("par-a", "par-b", "par-c", "par-d", "par-e", "par-f",
               "ds4", "codex", "dunky", "vp", "crackdown")
# The harness/type comes from the lane registry, never from the branch prefix.
LANE_TYPE = {"par-a": "claude", "par-b": "claude", "par-c": "claude",
             "par-d": "claude", "par-e": "claude", "par-f": "claude",
             "ds4": "opencode", "codex": "codex", "dunky": "pi",
             "vp": "claude", "crackdown": "codex"}


class SourceError(Exception):
    pass


def now():
    return datetime.now(timezone.utc)


def iso(stamp):
    return stamp.astimezone(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ") if stamp else None


def cell(value, as_of, reason=None):
    return {"value": value, "as_of": iso(as_of) if as_of else None, "reason": reason}


def guard(path, *, table=None, columns=(), min_rows=0):
    """Assert a source's premise. Returns a reason string, or None when it holds.

    A wrong path or a missing table looks exactly like 'no work done' - a
    confident zero. This makes the null+reason rule enforceable: the cell is
    null with the failed premise, never a zero.
    """
    p = Path(path)
    if not p.exists():
        return f"{p} absent"
    if table is not None:
        try:
            with sqlite3.connect(f"file:{p}?mode=ro", uri=True) as conn:
                names = [row[1] for row in conn.execute(f"PRAGMA table_info({table})")]
                if not names:
                    return f"table {table!r} absent at {p}"
                missing = [name for name in columns if name not in names]
                if missing:
                    return f"column(s) {', '.join(missing)} absent in {table!r} at {p}"
                rows = conn.execute(f"SELECT COUNT(*) FROM {table}").fetchone()[0]
                if rows < min_rows:
                    return f"{table!r} has {rows} row(s), expected at least {min_rows}, at {p}"
        except sqlite3.Error as exc:
            return f"{p}: {exc}"
    return None


def failed(reason):
    return cell(None, None, reason)


def oldest(cells):
    stamps = [c.get("as_of") for c in cells if isinstance(c, dict) and c.get("as_of")]
    return min(stamps) if stamps else None


def gh_prs(repo, since):
    """One paginated gh call for the window. The PR list is verifiable."""
    proc = subprocess.run(
        ["gh", "pr", "list", "--repo", repo, "--state", "merged", "--limit", "200",
         "--search", f"merged:>={since.strftime('%Y-%m-%dT%H:%M:%SZ')}",
         "--json", "number,title,mergedAt,headRefName,author"],
        capture_output=True, text=True, timeout=180)
    if proc.returncode != 0:
        raise SourceError(proc.stderr.strip() or f"gh exit {proc.returncode}")
    return json.loads(proc.stdout)


def attribute(pr):
    """First known lane token anywhere in the branch, then [lane] in the title,
    then None. The git author is NOT a lane: it goes to its own named fallback
    row so a person's name is never read as an agent."""
    branch = (pr.get("headRefName") or "").casefold()
    for token in KNOWN_LANES:
        if re.search(r"(^|[/_.-])" + re.escape(token) + r"($|[/_.-])", branch):
            return token
    # A bare 'crackdown-<lane>' segment.
    match = re.search(r"crackdown-([a-z0-9]+)", branch)
    if match:
        return f"crackdown-{match.group(1)}"
    match = re.search(r"\[([a-zA-Z0-9_-]+)\]", pr.get("title") or "")
    if match and match.group(1).casefold() in KNOWN_LANES:
        return match.group(1).casefold()
    return None


AUTHOR_ROW = "unattributed (git author)"


def lane_type(lane):
    base = lane.split("-")[0] if lane else ""
    return LANE_TYPE.get(lane) or LANE_TYPE.get(base) or "unknown"


def collect_agents():
    rows, unattributed, warnings = {}, [], []
    as_of = now()
    for project, (_dir, repo) in PROJECTS.items():
        try:
            prs = gh_prs(repo, now() - timedelta(hours=WINDOW_H))
        except (SourceError, OSError, ValueError) as exc:
            warnings.append({"source": f"github:{project}", "reason": str(exc)})
            prs = None
        if prs is None:
            continue
        for pr in prs:
            lane = attribute(pr)
            if lane is None:
                # Kept as a named fallback row, not silently dropped and not a
                # person's name: the owner sees this is not an agent.
                author = ((pr.get("author") or {}).get("login") or "unknown").strip()
                unattributed.append({"number": pr["number"], "branch": pr.get("headRefName"),
                                     "title": pr.get("title"), "author": author,
                                     "reason": "no lane token in branch or title"})
                lane = AUTHOR_ROW
            row = rows.setdefault(lane, {"agent": lane, "pane": None, "type": lane_type(lane),
                                         "merged_prs": 0, "bodies_credited": 0,
                                         "tasks_completed": 0, "messages_handled": 0,
                                         "fallback": lane == AUTHOR_ROW})
            row["merged_prs"] += 1
    return rows, unattributed, warnings, as_of


def collect_checkpoint():
    broken = guard(CHECKPOINT)
    if broken:
        return None, None, None, broken
    try:
        data = json.loads(CHECKPOINT.read_text())
        for key in ("strict_full_c_originals", "verified_game_identities"):
            if key not in data:
                return None, None, None, f"{CHECKPOINT}: key {key!r} absent"
        stamp = datetime.fromtimestamp(CHECKPOINT.stat().st_mtime, timezone.utc)
        bodies = int(data["strict_full_c_originals"])
        ceiling = int(data["verified_game_identities"])
        commit = (data.get("reviewed_change") or {}).get("reviewed_commit") or "unknown"
        return bodies, ceiling, stamp, f"{CHECKPOINT} (reviewed_commit {commit})"
    except (OSError, ValueError, KeyError, TypeError) as exc:
        return None, None, None, f"{CHECKPOINT}: {exc}"


def scalar(db, sql, params=()):
    with sqlite3.connect(f"file:{db}?mode=ro", uri=True) as conn:
        return conn.execute(sql, params).fetchone()[0]


def collect_tasks(since):
    broken = guard(TASKS_DB, table="tasks", columns=("status", "completed_at"), min_rows=1)
    if broken:
        return None, broken
    try:
        done = scalar(TASKS_DB,
                      "SELECT COUNT(*) FROM tasks WHERE status='done' AND completed_at >= ?",
                      (since.timestamp(),))
        return done, now()
    except (sqlite3.Error, OSError) as exc:
        return None, f"tasks.db: {exc}"


def collect_messages(since):
    """Per-pane handled events, and the null-pane bucket separately.

    Guards the table/columns first: an absent events table is not 'no traffic'.

    The metrics DB has 16,823 events with pane_id IS NULL; counting them into
    the per-pane total would make 'unknown' the biggest bar. They are reported
    as unattributed_events, never dropped.
    """
    broken = guard(METRICS_DB, table="events", columns=("kind", "at", "pane_id"), min_rows=1)
    if broken:
        return None, None, broken
    try:
        stamp = since.timestamp()
        handled = scalar(METRICS_DB,
                         "SELECT COUNT(*) FROM events WHERE kind IN ('message.sent','inbox.read') "
                         "AND at >= ? AND pane_id IS NOT NULL", (stamp,))
        unattributed = scalar(METRICS_DB,
                              "SELECT COUNT(*) FROM events WHERE kind IN ('message.sent','inbox.read') "
                              "AND at >= ? AND pane_id IS NULL", (stamp,))
        return handled, unattributed, now()
    except (sqlite3.Error, OSError) as exc:
        return None, None, f"metrics.db: {exc}"


def reply_latency():
    broken = guard(MESSAGES_DB, table="messages",
                   columns=("role", "answered_at", "created_at", "id"), min_rows=1)
    if broken:
        return {"p50_s": None, "p90_s": None, "max_s": None, "n": 0,
                "window": "unavailable", "unanswered": None, "as_of": None,
                "source": broken}
    try:
        with sqlite3.connect(f"file:{MESSAGES_DB}?mode=ro", uri=True) as conn:
            rows = conn.execute(
                "SELECT created_at, answered_at FROM messages WHERE role='owner' "
                "AND answered_at IS NOT NULL ORDER BY id DESC LIMIT 80").fetchall()
            unanswered = conn.execute(
                "SELECT COUNT(*) FROM messages WHERE role='owner' AND answered_at IS NULL"
            ).fetchone()[0]
        values = []
        for created, answered in rows:
            start = datetime.fromisoformat(str(created).replace("Z", "+00:00")).timestamp()
            end = datetime.fromisoformat(str(answered).replace("Z", "+00:00")).timestamp()
            if end >= start:
                values.append(end - start)
        values.sort()

        def pct(q):
            if not values:
                return None
            return values[min(len(values) - 1, int(round(q * (len(values) - 1))))]

        return {"p50_s": round(pct(.5)), "p90_s": round(pct(.9)),
                "max_s": round(max(values)) if values else None, "n": len(values),
                "window": "last 80 answered owner messages, ordered by message id desc; "
                          "nearest-rank percentiles",
                "unanswered": unanswered, "as_of": iso(now()),
                "source": "vp-of-agentry/data/messages.sqlite3 (created_at -> answered_at)"}
    except (sqlite3.Error, OSError, ValueError) as exc:
        return {"p50_s": None, "p90_s": None, "max_s": None, "n": 0,
                "window": "unavailable", "unanswered": None, "as_of": None,
                "source": f"messages.sqlite3: {exc}"}


def collect_reproducibility():
    broken = guard(CREDIT_CSV)
    if broken:
        return None, None, {}, None, broken
    try:
        rows = list(csv.DictReader(CREDIT_CSV.open()))
        if not rows or "kind" not in rows[0]:
            return None, None, {}, None, f"{CREDIT_CSV}: no rows or no 'kind' column"
        breakdown = {}
        for row in rows:
            breakdown[row["kind"]] = breakdown.get(row["kind"], 0) + 1
        stamp = datetime.fromtimestamp(CREDIT_CSV.stat().st_mtime, timezone.utc)
        return breakdown.get("checker", 0), len(rows), breakdown, stamp, str(CREDIT_CSV)
    except (OSError, KeyError, ValueError) as exc:
        return None, None, {}, None, f"{CREDIT_CSV}: {exc}"


def collect_crackdown():
    broken = guard(CRACKDOWN_RESULT)
    if broken:
        return None, None, None, broken
    try:
        text = CRACKDOWN_RESULT.read_text()
        match = re.search(r"shadow OFF \(mode 0\)\s+([\d.]+) / ([\d.]+)\s+([\d.]+)/([\d.]+)", text)
        if not match:
            raise ValueError("shadow OFF row not found")
        first, second, cpu_first, cpu_second = (float(x) for x in match.groups())
        fps = round(max(first, second), 1)  # the reported headroom window
        cpu = round((cpu_first + cpu_second) / 2, 1)
        stamp = datetime.fromtimestamp(CRACKDOWN_RESULT.stat().st_mtime, timezone.utc)
        return fps, cpu, stamp, f"{CRACKDOWN_RESULT} (sha 36b413d8)"
    except (OSError, ValueError, AttributeError) as exc:
        return None, None, None, f"{CRACKDOWN_RESULT}: {exc}"


def collect_hybrid_denominator():
    broken = guard(HYBRID_GLUE)
    if broken:
        return None, None, None, broken
    try:
        text = HYBRID_GLUE.read_text()
        match = re.search(r"(\d+)\s+of the\s+(\d+)\s+credited bodies", text)
        if not match:
            return None, None, None, f"{HYBRID_GLUE}: denominator not stated"
        return int(match.group(1)), int(match.group(2)), str(HYBRID_GLUE), None
    except (OSError, ValueError) as exc:
        return None, None, None, f"{HYBRID_GLUE}: {exc}"


def collect_agent_activity(since):
    """Per-pane message rate, median answer time, unread and oldest unread.

    All from inbox.db. Median is the true middle of the per-message latencies
    (created_at -> first read or ack), not an average. null+reason when the
    table/column premise fails.
    """
    stamp = since.timestamp()
    broken = guard(INBOX_DB, table="messages",
                   columns=("pane_id", "created_at", "read_at", "acked_at", "state"),
                   min_rows=0)
    if broken:
        return None, broken
    try:
        with sqlite3.connect(f"file:{INBOX_DB}?mode=ro", uri=True) as conn:
            rows = conn.execute(
                "SELECT pane_id, created_at, read_at, acked_at FROM messages "
                "WHERE created_at >= ? AND pane_id IS NOT NULL", (stamp,)).fetchall()
            unread = conn.execute(
                "SELECT pane_id, COUNT(*), MIN(created_at) FROM messages "
                "WHERE state = 'queued' AND pane_id IS NOT NULL GROUP BY pane_id").fetchall()
        counts, latencies = {}, {}
        for pane, created, read, acked in rows:
            counts[pane] = counts.get(pane, 0) + 1
            answered = read or acked
            if answered is not None:
                latencies.setdefault(pane, []).append(max(0.0, answered - created))
        out = {}
        for pane in set(counts) | {row[0] for row in unread}:
            values = sorted(latencies.get(pane, []))
            median = round(values[len(values) // 2], 1) if values else None
            out[pane] = {
                "messages_24h": cell(counts.get(pane, 0), since),
                "median_answer_s": (cell(median, since) if median is not None
                                    else failed("no answered messages in the window")),
            }
        try:
            with sqlite3.connect(f"file:{TASKS_DB}?mode=ro", uri=True) as conn:
                done = conn.execute(
                    "SELECT completed_by, COUNT(*) FROM tasks WHERE status='done' "
                    "AND completed_at >= ? AND completed_by IS NOT NULL GROUP BY completed_by",
                    (stamp,)).fetchall()
        except (sqlite3.Error, OSError):
            done = []
        for pane, n in done:
            out.setdefault(pane, {})["tasks_completed"] = cell(n, since)
        for pane, n, oldest in unread:
            entry = out.setdefault(pane, {})
            entry["unread"] = cell(n, since)
            entry["oldest_unread_s"] = cell(round(now().timestamp() - oldest, 1), since)
        return out, None
    except (sqlite3.Error, OSError) as exc:
        return None, f"inbox.db: {exc}"


CONTEXT_BIN = os.environ.get("DUNKINGSHEEP_BIN", "/home/hunter/.local/bin/dunkingsheep")


def collect_context(project_dir=None):
    """The context store as agents see it: the digest verbatim plus per-article
    delivery and read counts.

    One CLI call, no model, no git. The command runs with record=False on the
    digest side, so collecting a snapshot is a VIEW and does not inflate
    injected_7d - a dashboard that polls must not look like a reader.
    """
    env = dict(os.environ)
    # Honour --dunk-dir: a collector told to read an empty config dir must not
    # quietly read the live one (the negative test depends on this).
    env["DUNKINGSHEEP_DIR"] = str(DUNK_DIR)
    env["DUNKINGSHEEP_FRESH"] = "1"            # never serve a cached snapshot
    try:
        proc = subprocess.run([CONTEXT_BIN, "context", "snapshot"], capture_output=True,
                              text=True, timeout=30, env=env, cwd=project_dir or None)
    except (OSError, subprocess.SubprocessError) as exc:
        return {"status": "failed", "reason": f"context snapshot failed: {exc}",
                "articles": failed(f"context snapshot failed: {exc}"),
                "facts": failed("context snapshot failed"),
                "never_read": failed("context snapshot failed"),
                "digest": None, "entries": [], "as_of": None}
    if proc.returncode != 0:
        reason = (proc.stderr or "").strip().splitlines()[-1:] or ["no output"]
        reason = reason[0][:200]
        return {"status": "failed", "reason": f"context snapshot exit {proc.returncode}: {reason}",
                "articles": failed("context snapshot failed"),
                "facts": failed("context snapshot failed"),
                "never_read": failed("context snapshot failed"),
                "digest": None, "entries": [], "as_of": None}
    try:
        data = json.loads(proc.stdout)
        stores = data["stores"]
        data["digest"]
    except (ValueError, KeyError) as exc:
        return {"status": "failed", "reason": f"unreadable context snapshot: {exc}",
                "articles": failed("unreadable context snapshot"),
                "facts": failed("unreadable context snapshot"),
                "never_read": failed("unreadable context snapshot"),
                "digest": None, "entries": [], "as_of": None}
    merged, entries, live_stores = {}, [], []
    for name, store in stores.items():
        if store.get("status", "ok") != "ok":
            continue
        live_stores.append(name)
        for cls, count in (store.get("counts") or {}).items():
            merged[cls] = merged.get(cls, 0) + count
        for entry in store.get("entries") or []:
            entries.append(dict(entry, store=name))
    if not live_stores:
        reason = f"no context store at {', '.join(s.get('path', '?') for s in stores.values()) or 'any selected path'}"
        return {"status": "failed", "reason": reason,
                "articles": failed(reason), "facts": failed(reason),
                "never_read": failed(reason), "digest": None, "entries": [], "as_of": None}
    stamp_at = datetime.fromtimestamp(data["as_of"], timezone.utc) if data.get("as_of") else None
    stamp = iso(stamp_at)
    never = [e for e in entries if not e.get("reads")]
    return {"status": "ok", "reason": None,
            "articles": cell(sum(merged.values()), stamp_at),
            "facts": cell(merged.get("fact", 0) + merged.get("provisional", 0), stamp_at),
            "ground_truths": cell(merged.get("ground-truth", 0), stamp_at),
            "never_read": cell(len(never), stamp_at),
            "digest": data.get("digest"),
            "entries": sorted(entries, key=lambda e: (e.get("store") != "global",
                                                      e.get("class") != "ground-truth",
                                                      e.get("subject") or "")),
            "as_of": stamp}


def collect_dispatch():
    """The dispatcher's own last tick: idle lanes, dispatched this hour, blocked.

    Reads the state file the tick writes - never runs a tick and never a model.
    A missing file means the dispatcher has not run, which is stated, not zeroed.
    """
    path = DUNK_DIR / "dispatch-state.json"
    try:
        with open(path, encoding="utf-8") as handle:
            state = json.load(handle)
    except OSError as exc:
        reason = f"no dispatcher tick yet ({exc.strerror or exc})"
        return {"status": "absent", "reason": reason,
                "idle": failed(reason), "dispatched_1h": failed(reason),
                "blocked": [], "dead": [], "queue_depth": failed(reason),
                "retired": failed(reason), "as_of": None}
    except ValueError as exc:
        reason = f"dispatcher state unreadable: {exc}"
        return {"status": "failed", "reason": reason,
                "idle": failed(reason), "dispatched_1h": failed(reason),
                "blocked": [], "dead": [], "queue_depth": failed(reason), "as_of": None}
    stamp_at = datetime.fromtimestamp(state["tick_at"], timezone.utc) if state.get("tick_at") else None
    blocked = [dict(b) for b in state.get("blocked") or []]
    # Counted from the retire file itself, so it is available even before the
    # next tick: no file means nothing is retired, which is a fact, not a gap.
    try:
        with open(DUNK_DIR / "retired-panes.json", encoding="utf-8") as handle:
            retired_records = json.load(handle) or {}
        retired_count = len(retired_records)
    except (OSError, ValueError):
        retired_count = 0
    return {"status": "ok", "reason": None,
            "idle": cell(len(state.get("idle_unfilled") or []), stamp_at),
            "dispatched_1h": cell(state.get("dispatched_1h"), stamp_at),
            "ready": cell(state.get("ready"), stamp_at),
            "queue_depth": cell(state.get("queue_depth"), stamp_at),
            "queue_empty": bool(state.get("queue_empty")),
            "retired": cell(retired_count, stamp_at),
            "retired_panes": sorted(retired_records) if retired_count else [],
            "blocked": blocked,
            "dead": [dict(d) for d in state.get("dead") or []],
            "as_of": iso(stamp_at)}


def collect_backlog():
    """The dunkies feature backlog. AGE is the interesting number, not the count."""
    try:
        with sqlite3.connect(f"file:{TASKS_DB}?mode=ro", uri=True) as conn:
            conn.row_factory = sqlite3.Row
            rows = [dict(r) for r in conn.execute(
                "SELECT id,title,status,priority,created_at,block_reason FROM tasks "
                "WHERE status IN ('open','in_progress','blocked')")]
        stamp = time.time()
        order = {"urgent": 0, "high": 1, "medium": 2, "low": 3}

        def item(row):
            return {"id": row["id"], "title": row["title"], "status": row["status"],
                    "priority": row["priority"],
                    "age_s": int(stamp - float(row["created_at"]))}

        top = sorted(rows, key=lambda r: (order.get(r["priority"], 9), r["created_at"]))[:5]
        held = [r for r in rows if (r.get("block_reason") or "").strip().upper()
                .startswith("HELD FOR OWNER DECISION")]
        opens = [r for r in rows if r["status"] == "open"]
        oldest = min(opens, key=lambda r: r["created_at"]) if opens else None
        return {"open": sum(1 for r in rows if r["status"] == "open"),
                "in_progress": sum(1 for r in rows if r["status"] == "in_progress"),
                "blocked": sum(1 for r in rows if r["status"] == "blocked"),
                "top": [item(r) for r in top],
                "oldest_open": item(oldest) if oldest else None,
                "held": {"count": len(held),
                         "oldest_days": round(max((stamp - float(r["created_at"])) / 86400
                                                  for r in held), 1) if held else None,
                         "ids": [r["id"] for r in held]},
                "as_of": iso(now())}
    except (sqlite3.Error, OSError, ValueError) as exc:
        return {"open": None, "in_progress": None, "blocked": None, "top": [],
                "oldest_open": None, "reason": f"tasks.db: {exc}", "as_of": None}


def hybrid_claim():
    broken = guard(HYBRID)
    if broken:
        return None, None, broken
    try:
        data = json.loads(HYBRID.read_text())
        claims = data.get("claims") or {}
        running = claims.get("running_as_c") or {}
        return running.get("value"), running.get("source"), running.get("proof")
    except (OSError, ValueError, KeyError, TypeError) as exc:
        return None, None, f"{HYBRID}: {exc}"


def main(argv=None):
    import argparse
    parser = argparse.ArgumentParser(description="Collect one ops snapshot (read-only).")
    parser.add_argument("--out", type=Path, default=None,
                        help="write here; only the default path is production")
    parser.add_argument("--dunk-dir", type=Path, default=None,
                        help="Dunking Sheep config dir (default DUNKINGSHEEP_DIR)")
    args = parser.parse_args(argv)
    global TASKS_DB, METRICS_DB, INBOX_DB, SNAPSHOT, DUNK_DIR
    if args.dunk_dir is not None:
        DUNK_DIR = Path(args.dunk_dir)
        TASKS_DB = Path(args.dunk_dir) / "tasks.db"
        METRICS_DB = Path(args.dunk_dir) / "metrics.db"
        INBOX_DB = Path(args.dunk_dir) / "inbox.db"
    out = Path(args.out) if args.out is not None else SNAPSHOT
    started = time.time()
    since = now() - timedelta(hours=WINDOW_H)
    rows, unattributed, gh_warnings, pr_as_of = collect_agents()
    bodies, ceiling, checkpoint_at, checkpoint_ref = collect_checkpoint()
    tasks_done, tasks_at = collect_tasks(since)
    messages_n, messages_unattributed, messages_at = collect_messages(since)
    activity, activity_error = collect_agent_activity(since)
    latency = reply_latency()
    hybrid_running, hybrid_source, hybrid_proof = hybrid_claim()
    repro_checker, repro_total, repro_breakdown, repro_at, repro_ref = collect_reproducibility()
    crack_fps, crack_cpu, crack_at, crack_ref = collect_crackdown()
    hybrid_num, hybrid_den, hybrid_den_ref, hybrid_den_reason = collect_hybrid_denominator()
    # The scan cache sits beside the snapshot, so a test --out never touches production's.
    costs = agent_costs.collect(cache_path=out.with_name(out.stem + "-costs-cache.json"))
    free = costs["free_model"]
    delivery = delivery_stats.collect(DUNK_DIR)
    credit = credit_stats.collect(CHECKPOINT.parents[2])
    leaderboard = free_leaderboard.collect()

    agents = []
    for lane in sorted(rows):
        row = rows[lane]
        agents.append({
            "agent": row["agent"], "pane": row["pane"], "type": row["type"],
            "fallback": row.get("fallback", False),
            "merged_prs": cell(row["merged_prs"], pr_as_of),
            "bodies_credited": failed("no per-lane checkpoint delta source"),
            "tasks_completed": failed("no per-assignee task completion source in window"),
            "messages_handled": failed("no per-pane metrics split source"),
            "free_model": None,
        })
    types = {}
    for agent in agents:
        kind = types.setdefault(agent["type"], {"type": agent["type"], "agents": 0,
                                                "merged_prs": 0, "bodies_credited": 0,
                                                "tasks_completed": 0, "messages_handled": 0})
        kind["agents"] += 1
        for key in ("merged_prs", "bodies_credited", "tasks_completed", "messages_handled"):
            value = agent[key].get("value")
            kind[key] = None if kind[key] is None or value is None else kind[key] + value
    for kind in types.values():
        for key in ("merged_prs", "bodies_credited", "tasks_completed", "messages_handled"):
            value = kind[key]
            kind[key] = cell(value, pr_as_of) if value is not None else failed("a member lane cell is null")

    projects = [
        {"id": "poolrad", "label": "Poolrad", "metric": "strict bodies",
         "value": cell(bodies, checkpoint_at) if bodies is not None else failed(checkpoint_ref),
         "denominator": cell(STRICT_CEILING, checkpoint_at) if bodies is not None else failed(checkpoint_ref),
         "denominator_label": "CEILING", "evidence_ref": checkpoint_ref,
         "truth": "815 is an upper bound, not a verified denominator."},
        {"id": "hybrid", "label": "Hybrid", "metric": "credited bodies running as our C",
         "value": cell(hybrid_num or hybrid_running, checkpoint_at) if (hybrid_num or hybrid_running) is not None else failed(hybrid_proof),
         "denominator": cell(hybrid_den, checkpoint_at) if hybrid_den is not None else failed(
             hybrid_den_reason or "denominator = credited bodies reached on the measured route"),
         "denominator_label": "credited bodies reached",
         "evidence_ref": hybrid_den_ref or hybrid_source,
         "truth": "Running as our C is the claim; credited is the input."},
        {"id": "reproducibility", "label": "Reproducibility", "metric": "credits rebuildable by one command",
         "value": cell(repro_checker, repro_at) if repro_checker is not None else failed(repro_ref),
         "denominator": cell(repro_total, repro_at) if repro_total is not None else failed(repro_ref),
         "denominator_label": "credits", "evidence_ref": repro_ref, "breakdown": repro_breakdown,
         "truth": "98 of 280 credits can be rebuilt with one command; the other kinds are a breakdown, not the bar."},
        {"id": "crackdown", "label": "Crackdown", "metric": "measured FPS",
         "value": cell(crack_fps, crack_at) if crack_fps is not None else failed(crack_ref),
         "denominator": cell(30, None), "denominator_label": "target",
         "evidence_ref": crack_ref,
         "configuration": ("50%% resolution, LOD0, shadows OFF (mode 0); CPU %.1f ms binds" % crack_cpu) if crack_cpu is not None else None,
         "truth": "Measured on <configuration>; a different config is a different number."},
    ]

    sources = {
        "github": {"status": "ok" if not gh_warnings else "partial",
                   "as_of": iso(pr_as_of), "detail": "one paginated gh pr list per project",
                   "pr_source": "gh"},
        "checkpoint": {"status": "ok" if bodies is not None else "nulled",
                       "as_of": iso(checkpoint_at),
                       "reason": None if bodies is not None else checkpoint_ref},
        "tasks": {"status": "ok" if tasks_done is not None else "nulled",
                  "as_of": iso(tasks_at) if tasks_done is not None else None,
                  "reason": None if tasks_done is not None else tasks_at},
        "metrics": {"status": "ok" if messages_n is not None else "nulled",
                    "as_of": iso(messages_at) if messages_n is not None else None,
                    "reason": None if messages_n is not None else messages_at,
                    "per_pane_events": messages_n,
                    "unattributed_events": messages_unattributed},
        "messages": {"status": "ok" if latency.get("p50_s") is not None else "nulled",
                     "as_of": latency.get("as_of"),
                     "reason": None if latency.get("p50_s") is not None else latency.get("source")},
        "hybrid": {"status": "ok" if hybrid_running is not None else "nulled",
                   "reason": None if hybrid_running is not None else hybrid_proof},
        "crackdown": {"status": "ok" if crack_fps is not None else "nulled",
                      "reason": None if crack_fps is not None else crack_ref},
        "reproducibility": {"status": "ok" if repro_checker is not None else "nulled",
                            "reason": None if repro_checker is not None else repro_ref},
        "freemodel": {"status": free.get("status", "nulled"),
                      "reason": free.get("reason") or (None if free["outcomes"] is not None
                                                       else free["outcomes_recorded"]["reason"])},
        "costs": {"status": costs["cost_per_agent"]["status"],
                  "reason": costs["cost_per_agent"].get("reason") or "; ".join(
                      f"{h}: {r}" for h, r in costs["cost_per_agent"].get("failed_sources", {}).items()) or None},
        "usage": {"status": costs["usage"]["status"], "reason": costs["usage"].get("reason")},
        **{name: {"status": section.get("status"), "reason": section.get("reason")}
           for name, section in delivery.items()},
        # REPLACED is absent from sources on purpose: "not yet collected" is its
        # expected state until a lane writes the file, not a broken source.
        "credited": {"status": credit["credited"]["status"], "reason": credit["credited"].get("reason")},
        "credit_rate": {"status": credit["rate"]["status"], "reason": credit["rate"].get("credited_reason")},
        "free_leaderboard": {"status": leaderboard["status"],
                             "reason": leaderboard.get("reason") or "; ".join(leaderboard.get("problems") or []) or None},
    }
    context = collect_context()
    dispatch = collect_dispatch()
    warnings = gh_warnings + [
        {"source": name, "reason": source.get("reason") or source.get("status")}
        for name, source in sources.items()
        if source.get("status") != "ok"]
    if context.get("status") != "ok":
        warnings.append({"source": "context", "reason": context.get("reason")})
    if dispatch.get("status") != "ok":
        warnings.append({"source": "dispatch", "reason": dispatch.get("reason")})

    snapshot = {
        "schema": "ops-snapshot/1", "generated_at": iso(now()),
        "oldest_as_of": oldest(
            [a[c] for a in agents for c in ("merged_prs", "bodies_credited", "tasks_completed", "messages_handled")]
            + [p["value"] for p in projects]
            + [context.get("articles") or {}]),
        "collector": {"duration_s": round(time.time() - started, 2), "sources_failed": len(warnings)},
        "warnings": warnings,
        "sources": sources,
        "reply_latency": latency,
        "agent_activity": activity if activity is not None else {"error": activity_error},
        "backlog": collect_backlog(),
        "dispatch": collect_dispatch(),
        "context": context,
        "cost_per_agent": costs["cost_per_agent"],
        "free_model": free,
        "usage": costs["usage"],
        **delivery,
        "credited": credit["credited"],
        "replaced": credit["replaced"],
        "credit_rate": credit["rate"],
        "free_leaderboard": leaderboard,
        "attribution": {
            "attributed": sum(a["merged_prs"]["value"] or 0 for a in agents if not a.get("fallback")),
            "unattributed": sum(a["merged_prs"]["value"] or 0 for a in agents if a.get("fallback")),
            "method": "branch lane token -> [lane] title token -> 'unattributed (git author)'"},
        "agents_unattributed": unattributed,
        "agents": agents,
        "types": list(types.values()),
        "projects": projects,
    }
    out.parent.mkdir(parents=True, exist_ok=True)
    temporary = out.with_suffix(".json.tmp")
    with open(temporary, "w", encoding="utf-8") as handle:
        handle.write(json.dumps(snapshot, indent=2) + "\n")
        handle.flush()
        os.fsync(handle.fileno())
    # Atomic swap: a reader sees the old file or the new one, never a partial.
    os.replace(temporary, out)
    print(json.dumps({"wrote": str(out), "agents": len(agents),
                      "unattributed": len(unattributed), "warnings": len(warnings),
                      "oldest_as_of": snapshot["oldest_as_of"]}))
    return 0


if __name__ == "__main__":
    sys.exit(main())
