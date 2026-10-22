#!/usr/bin/env python3
"""Collect one ops+poolrad snapshot (schema: docs/OPS_SNAPSHOT_SCHEMA.md).

Read-only, idempotent, no model: one paginated gh call per repo, one checkpoint
read, one query per database, one pane list. Every number is a
{value, as_of, reason} cell; a missing source is null+reason, never a zero and
never the previous snapshot.
"""

from __future__ import annotations

import json
import os
import re
import sqlite3
import subprocess
import sys
import time
from datetime import datetime, timedelta, timezone
from pathlib import Path

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
PROJECTS = {
    "poolrad": ("poolrad-decomp", "huntergdavis/poolrad-decomp"),
    "crackdown": ("crackdown-switch", "huntergdavis/crackdown-switch"),
}
WINDOW_H = 24
STRICT_CEILING = 815  # poolrad body ceiling; a ceiling, not a verified denominator
# Branch prefixes are the lane convention (caught by the forward rule). A known
# prefix is the attribution; anything else is unattributed, never guessed.
LANE_TYPES = (("claude", "claude"), ("codex", "codex"), ("pi", "pi"),
              ("opencode", "opencode"), ("free", "free-model"))


class SourceError(Exception):
    pass


def now():
    return datetime.now(timezone.utc)


def iso(stamp):
    return stamp.astimezone(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ") if stamp else None


def cell(value, as_of, reason=None):
    return {"value": value, "as_of": iso(as_of) if as_of else None, "reason": reason}


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


def lane_tokens():
    """Known lane tokens from the live panes, so attribution stays data-driven."""
    try:
        out = subprocess.run(["/home/hunter/.local/bin/dunkingsheep", "--json", "panes"],
                             capture_output=True, text=True, timeout=30).stdout
        panes = json.loads(out).get("panes") or []
    except Exception:  # noqa: BLE001
        return {}
    tokens = {}
    for pane in panes:
        for key in ("agent_name", "lane_name"):
            name = (pane.get(key) or "").strip()
            if name and not name.startswith("w"):
                tokens[name.casefold()] = name
                tokens[name.casefold().replace(" ", "-")] = name
    return tokens


def attribute(pr):
    """Branch prefix first, then a [lane] title token, else None (unattributed).

    The branch convention is 'claude/par-c-0411', 'checker-batch-1',
    'hybrid-glue-...' - the first segment names the lane. We do not attribute
    by author (one account authors every PR).
    """
    branch = (pr.get("headRefName") or "").strip()
    prefix = re.split(r"[/_-]", branch, maxsplit=1)[0].casefold()
    known = {name for name, _ in LANE_TYPES} | {"par-a", "par-b", "par-c", "par-d", "par-e",
                                                "checker-batch", "hybrid-glue"}
    if prefix in known:
        return prefix
    for name in known:
        if name != prefix and re.match(re.escape(name) + r"[/_-]", branch.casefold()):
            return name
    match = re.search(r"\[([a-zA-Z0-9_-]+)\]", pr.get("title") or "")
    if match and match.group(1).casefold() in known:
        return match.group(1).casefold()
    return None


def lane_type(lane):
    for prefix, kind in LANE_TYPES:
        if lane == prefix or lane.startswith(prefix):
            return kind
    return "unknown"


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
                unattributed.append({"number": pr["number"], "branch": pr.get("headRefName"),
                                     "title": pr.get("title"), "reason": "no lane token in branch or title"})
                continue
            row = rows.setdefault(lane, {"agent": lane, "pane": None, "type": lane_type(lane),
                                         "merged_prs": 0, "bodies_credited": 0,
                                         "tasks_completed": 0, "messages_handled": 0})
            row["merged_prs"] += 1
    return rows, unattributed, warnings, as_of


def collect_checkpoint():
    try:
        data = json.loads(CHECKPOINT.read_text())
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
    try:
        done = scalar(TASKS_DB,
                      "SELECT COUNT(*) FROM tasks WHERE status='done' AND completed_at >= ?",
                      (since.timestamp(),))
        return done, now()
    except (sqlite3.Error, OSError) as exc:
        return None, f"tasks.db: {exc}"


def collect_messages(since):
    try:
        n = scalar(METRICS_DB,
                   "SELECT COUNT(*) FROM events WHERE kind IN ('message.sent','inbox.read') "
                   "AND at >= ?", (since.timestamp(),))
        return n, now()
    except (sqlite3.Error, OSError) as exc:
        return None, f"metrics.db: {exc}"


def reply_latency():
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
                "window": "last 80 answered owner messages, ordered by message id desc",
                "unanswered": unanswered, "as_of": iso(now()),
                "source": "vp-of-agentry/data/messages.sqlite3 (created_at -> answered_at)"}
    except (sqlite3.Error, OSError, ValueError) as exc:
        return {"p50_s": None, "p90_s": None, "max_s": None, "n": 0,
                "window": "unavailable", "unanswered": None, "as_of": None,
                "source": f"messages.sqlite3: {exc}"}


def collect_backlog():
    """The dunkies feature backlog. AGE is the interesting number, not the count."""
    try:
        with sqlite3.connect(f"file:{TASKS_DB}?mode=ro", uri=True) as conn:
            conn.row_factory = sqlite3.Row
            rows = [dict(r) for r in conn.execute(
                "SELECT id,title,status,priority,created_at FROM tasks "
                "WHERE status IN ('open','in_progress','blocked')")]
        stamp = time.time()
        order = {"urgent": 0, "high": 1, "medium": 2, "low": 3}

        def item(row):
            return {"id": row["id"], "title": row["title"], "status": row["status"],
                    "priority": row["priority"],
                    "age_s": int(stamp - float(row["created_at"]))}

        top = sorted(rows, key=lambda r: (order.get(r["priority"], 9), r["created_at"]))[:5]
        opens = [r for r in rows if r["status"] == "open"]
        oldest = min(opens, key=lambda r: r["created_at"]) if opens else None
        return {"open": sum(1 for r in rows if r["status"] == "open"),
                "in_progress": sum(1 for r in rows if r["status"] == "in_progress"),
                "blocked": sum(1 for r in rows if r["status"] == "blocked"),
                "top": [item(r) for r in top],
                "oldest_open": item(oldest) if oldest else None,
                "as_of": iso(now())}
    except (sqlite3.Error, OSError, ValueError) as exc:
        return {"open": None, "in_progress": None, "blocked": None, "top": [],
                "oldest_open": None, "reason": f"tasks.db: {exc}", "as_of": None}


def hybrid_claim():
    try:
        data = json.loads(HYBRID.read_text())
        claims = data.get("claims") or {}
        running = claims.get("running_as_c") or {}
        return running.get("value"), running.get("source"), running.get("proof")
    except (OSError, ValueError, KeyError, TypeError) as exc:
        return None, None, f"{HYBRID}: {exc}"


def main():
    started = time.time()
    since = now() - timedelta(hours=WINDOW_H)
    rows, unattributed, warnings, pr_as_of = collect_agents()
    bodies, ceiling, checkpoint_at, checkpoint_ref = collect_checkpoint()
    tasks_done, tasks_at = collect_tasks(since)
    messages_n, messages_at = collect_messages(since)
    latency = reply_latency()
    hybrid_running, hybrid_source, hybrid_proof = hybrid_claim()

    agents = []
    for lane in sorted(rows):
        row = rows[lane]
        agents.append({
            "agent": row["agent"], "pane": row["pane"], "type": row["type"],
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

    projects = [
        {"id": "poolrad", "label": "Poolrad", "metric": "strict bodies",
         "value": cell(bodies, checkpoint_at) if bodies is not None else failed(checkpoint_ref),
         "denominator": cell(STRICT_CEILING, checkpoint_at) if bodies is not None else failed(checkpoint_ref),
         "denominator_label": "CEILING", "evidence_ref": checkpoint_ref,
         "truth": "815 is an upper bound, not a verified denominator."},
        {"id": "hybrid", "label": "Hybrid", "metric": "credited bodies running as our C",
         "value": cell(hybrid_running, checkpoint_at) if hybrid_running is not None else failed(hybrid_proof),
         "denominator": failed("bodies reached not yet read"), "denominator_label": "bodies reached",
         "evidence_ref": hybrid_source, "truth": "Running as our C is the claim; credited is the input."},
        {"id": "reproducibility", "label": "Reproducibility", "metric": "registered checkers",
         "value": failed("registered-checker source not wired yet"),
         "denominator": cell(280, checkpoint_at) if bodies is not None else failed(checkpoint_ref),
         "denominator_label": "", "evidence_ref": checkpoint_ref,
         "truth": "A checker is registered when it fails a known-bad build."},
        {"id": "crackdown", "label": "Crackdown", "metric": "measured FPS",
         "value": failed("FPS source not wired yet"), "denominator": cell(30, None),
         "denominator_label": "target", "evidence_ref": None,
         "configuration": None,
         "truth": "Measured on <configuration>; a different config is a different number."},
    ]

    snapshot = {
        "schema": "ops-snapshot/1", "generated_at": iso(now()),
        "oldest_as_of": oldest([a[c] for a in agents for c in
                                ("merged_prs", "bodies_credited", "tasks_completed", "messages_handled")]
                               + [p["value"] for p in projects]),
        "collector": {"duration_s": round(time.time() - started, 2),
                      "sources_failed": len(warnings)},
        "warnings": warnings,
        "sources": {
            "github": {"status": "ok" if not warnings else "partial", "as_of": iso(pr_as_of),
                       "detail": "one paginated gh pr list per project", "pr_source": "gh"},
            "checkpoint": {"status": "ok" if bodies is not None else "nulled",
                           "as_of": iso(checkpoint_at), "reason": None if bodies is not None else checkpoint_ref},
            "tasks": {"status": "ok" if tasks_done is not None else "nulled",
                      "as_of": iso(tasks_at) if tasks_done is not None else None,
                      "reason": None if tasks_done is not None else tasks_at},
            "metrics": {"status": "ok" if messages_n is not None else "nulled",
                        "as_of": iso(messages_at) if messages_n is not None else None,
                        "reason": None if messages_n is not None else messages_at},
            "messages": {"status": "ok" if latency.get("p50_s") is not None else "nulled",
                         "as_of": latency.get("as_of")},
            "hybrid": {"status": "ok" if hybrid_running is not None else "nulled",
                       "reason": None if hybrid_running is not None else hybrid_proof},
            "freemodel": {"status": "nulled", "reason": "par-d tally not published yet"},
        },
        "reply_latency": latency,
        "backlog": collect_backlog(),
        "context": {
            "status": "not_initialised",
            "reason": "context store not yet initialised (v0 not built)",
            "articles": failed("context store not yet initialised"),
            "facts": failed("context store not yet initialised"),
            "oldest_fact": failed("context store not yet initialised"),
            "never_read": failed("context store not yet initialised"),
            "as_of": None,
        },
        "agents_unattributed": unattributed,
        "agents": agents,
        "types": list(types.values()),
        "projects": projects,
    }
    SNAPSHOT.parent.mkdir(parents=True, exist_ok=True)
    temporary = SNAPSHOT.with_suffix(".json.tmp")
    temporary.write_text(json.dumps(snapshot, indent=2) + "\n")
    os.replace(temporary, SNAPSHOT)
    print(json.dumps({"wrote": str(SNAPSHOT), "agents": len(agents),
                      "unattributed": len(unattributed), "warnings": len(warnings),
                      "oldest_as_of": snapshot["oldest_as_of"]}))
    return 0


if __name__ == "__main__":
    sys.exit(main())
