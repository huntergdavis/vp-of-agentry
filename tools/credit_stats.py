#!/usr/bin/env python3
"""CREDITED, REPLACED and their per-day rate (owner #1386). No model, nothing hand-entered.

CREDITED is the strict count pinned in poolrad-decomp's
docs/re/function_accounting_checkpoint.json, read from the checkout's HEAD
commit (not the working tree), with its evidence-kind breakdown from
docs/re/credit_evidence_kind.csv at the same commit.

The rate is computed from timestamped events: every commit that changed the
checkpoint, with the strict count that commit pinned. A reversal is a negative
event, so a day's rate is net. Commit time is when the acceptance was
committed, not when it reached main.

REPLACED has no source yet. Its contract is REPLACED_FILE below: one record per
body the game executes as our C, proven by an identical run (zero differing
pixels or zero non-equal arrivals). Until a lane writes that file the cell is
null with the reason, never a zero. Prose claims (hybrid_status.json parses
'run as our C' out of a markdown file) are not proof and are not counted.
"""

from __future__ import annotations

import csv
import io
import json
import os
import subprocess
from datetime import datetime, timedelta, timezone
from pathlib import Path
from zoneinfo import ZoneInfo

REPO = Path(os.environ.get("POOLRAD_REPO", "/home/hunter/workspace/poolrad-decomp"))
CHECKPOINT = "docs/re/function_accounting_checkpoint.json"
KINDS = "docs/re/credit_evidence_kind.csv"
REPLACED_FILE = "docs/re/replaced_bodies.json"
LOCAL = ZoneInfo("America/Los_Angeles")
DAYS = 14


def iso(stamp):
    return stamp.astimezone(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ") if stamp else None


def cell(value, as_of, reason=None):
    return {"value": value, "as_of": iso(as_of) if as_of else None, "reason": reason}


def failed(reason):
    return cell(None, None, reason)


def git(repo, *args):
    proc = subprocess.run(["git", "-C", str(repo), *args], capture_output=True, text=True, timeout=60)
    if proc.returncode != 0:
        raise RuntimeError((proc.stderr or f"git {args[0]} exited {proc.returncode}").strip()[:200])
    return proc.stdout


def at_commit(repo, commit, path):
    return git(repo, "show", f"{commit}:{path}")


def strict_events(repo, since):
    """[(time, commit, strict, subject)] for every commit touching the checkpoint since `since`,
    plus the last one before it so the window starts from a known value."""
    log = git(repo, "log", "--format=%H %cI %s", "HEAD", "--", CHECKPOINT).split("\n")
    events = []
    for line in log:
        if not line.strip():
            continue
        commit, stamp, subject = (line.split(" ", 2) + [""])[:3]
        when = datetime.fromisoformat(stamp)
        try:
            strict = json.loads(at_commit(repo, commit, CHECKPOINT)).get("strict_full_c_originals")
        except (RuntimeError, ValueError):
            continue
        if isinstance(strict, int):
            events.append((when, commit, strict, subject))
        if when < since:
            break  # the first one before the window is the baseline
    events.sort(key=lambda e: e[0])
    return events


def value_at(events, moment, floor=None):
    """The count pinned at `moment`; `floor` before the first event (None = unknown)."""
    known = [e for e in events if e[0] <= moment]
    return known[-1][2] if known else floor


def daily(events, now, days=DAYS, floor=None):
    """Net change per Los Angeles calendar day, oldest first, from the event series.

    floor is the value before the first event: unknown (None) for the checkpoint,
    which did not exist; 0 for replaced, since nothing is replaced before its proof."""
    today = now.astimezone(LOCAL).replace(hour=0, minute=0, second=0, microsecond=0)
    rows = []
    for back in range(days - 1, -1, -1):
        start = today - timedelta(days=back)
        end = min(start + timedelta(days=1), now)
        before, after = value_at(events, start, floor), value_at(events, end, floor)
        rows.append({"day": start.strftime("%Y-%m-%d"),
                     "net": (after - before) if before is not None and after is not None else None,
                     "events": sum(1 for e in events if start <= e[0] < end)})
    return rows


def collect_credited(repo, now):
    try:
        head = git(repo, "log", "-1", "--format=%H %cI", "HEAD", "--", CHECKPOINT).split()
        commit, stamp = head[0], datetime.fromisoformat(head[1])
        pinned = json.loads(at_commit(repo, commit, CHECKPOINT))
        kinds_commit = git(repo, "log", "-1", "--format=%H", "HEAD", "--", KINDS).strip()
        rows = list(csv.DictReader(io.StringIO(at_commit(repo, "HEAD", KINDS))))
    except (RuntimeError, ValueError, IndexError, OSError) as exc:
        reason = f"{repo}: {exc}"
        return {"status": "nulled", "reason": reason, "value": failed(reason), "as_of": None}, []
    strict = pinned.get("strict_full_c_originals")
    since = now - timedelta(days=DAYS + 1)
    try:
        events = strict_events(repo, since)
    except RuntimeError as exc:
        events, events_reason = [], str(exc)
    else:
        events_reason = None
    by_kind = {}
    for row in rows:
        by_kind[row.get("kind") or "unstated"] = by_kind.get(row.get("kind") or "unstated", 0) + 1
    # A kind that left the table in the window is a real zero, not an absent kind.
    try:
        for line in git(repo, "log", f"--since={iso(since)}", "--format=%H", "HEAD", "--", KINDS).split():
            for row in csv.DictReader(io.StringIO(at_commit(repo, line, KINDS))):
                by_kind.setdefault(row.get("kind") or "unstated", 0)
    except RuntimeError:
        pass

    def delta(hours):
        before = value_at(events, now - timedelta(hours=hours))
        if before is None or strict is None:
            return failed(events_reason or f"no checkpoint commit before {hours} h ago in the history read")
        return cell(strict - before, now)
    mismatch = (None if len(rows) == strict else
                f"the kind table has {len(rows)} rows but the checkpoint pins {strict}")
    return {
        # as_of is when we read it (the STALE rule); committed_at is when the number last changed.
        "status": "ok", "as_of": iso(now),
        "source": f"poolrad-decomp {CHECKPOINT} @ {commit[:10]} (HEAD of the local main checkout); "
                  f"kinds from {KINDS} @ {kinds_commit[:10]}",
        "commit": commit, "committed_at": iso(stamp),
        "value": cell(strict, stamp) if isinstance(strict, int) else failed("checkpoint has no strict_full_c_originals"),
        "identities": cell(pinned.get("verified_game_identities"), stamp),
        "by_kind": [{"kind": k, "count": cell(v, stamp)} for k, v in sorted(by_kind.items(), key=lambda kv: -kv[1])],
        "kind_mismatch": mismatch,
        "delta_24h": delta(24), "delta_7d": delta(24 * 7),
        "truth": "Credited is reviewed strict C bodies pinned in the checkpoint. It is not 'runs in the game': "
                 "that is REPLACED. 815 is a ceiling, not a verified denominator.",
    }, events


def collect_replaced(repo, now):
    path = Path(repo) / REPLACED_FILE
    if not path.is_file():
        reason = (f"not yet collected: no lane has reported a replaced count ({REPLACED_FILE} absent "
                  f"in poolrad-decomp)")
        return {"status": "nulled", "reason": reason, "value": failed(reason), "as_of": iso(now),
                "source": f"poolrad-decomp {REPLACED_FILE}", "contract": CONTRACT,
                "truth": "Replaced means the game executes the body as our C, proven by an identical run. "
                         "A doc saying a body 'runs as our C' is a claim, not this number."}, []
    try:
        data = json.loads(path.read_text())
        bodies = data["bodies"]
        proven = [b for b in bodies if (b.get("evidence") or {}).get("differing") == 0 and b.get("proven_at")]
        events, running = [], 0
        for body in sorted(proven, key=lambda b: b["proven_at"]):
            running += 1
            events.append((datetime.fromisoformat(body["proven_at"].replace("Z", "+00:00")), body.get("id"), running, ""))
        as_of = datetime.fromtimestamp(path.stat().st_mtime, timezone.utc)
    except (OSError, ValueError, KeyError, TypeError) as exc:
        reason = f"{path}: unreadable ({type(exc).__name__}: {exc})"
        return {"status": "nulled", "reason": reason, "value": failed(reason), "as_of": None,
                "source": str(path), "contract": CONTRACT}, []
    rejected = len(bodies) - len(proven)
    return {"status": "ok", "as_of": iso(now), "written_at": iso(as_of),
            "source": f"poolrad-decomp {REPLACED_FILE}",
            "value": cell(len(proven), as_of),
            "not_counted": cell(rejected, as_of),
            "truth": "Counted only with differing == 0 from an identical run and a proven_at time."}, events


CONTRACT = {
    "path": REPLACED_FILE,
    "schema": {"schema": "replaced/1", "bodies": [
        {"id": "OVL_UUUU_OOOO", "proven_at": "ISO-8601 time of the identical run",
         "evidence": {"kind": "pixels | arrivals", "differing": 0, "run_ref": "artifact path or commit"}}]},
}


def collect(repo=None, *, now=None):
    repo = Path(repo or REPO)
    now = now or datetime.now(timezone.utc)
    credited, credit_events = collect_credited(repo, now)
    replaced, replace_events = collect_replaced(repo, now)
    rate = {
        "as_of": iso(now), "days": DAYS,
        "method": "net change per Los Angeles calendar day from timestamped events: checkpoint commits "
                  "(credited) and proven_at records (replaced). Not a difference of snapshots.",
        "credited": daily(credit_events, now) if credit_events else None,
        "credited_reason": None if credit_events else (credited.get("reason") or "no checkpoint events in the window"),
        "replaced": daily(replace_events, now, floor=0) if replace_events else None,
        "replaced_reason": None if replace_events else (replaced.get("reason") or "no proven replacements yet"),
        "source": f"git log of {CHECKPOINT}; {REPLACED_FILE} proven_at",
    }
    if credit_events:
        total = sum(d["net"] or 0 for d in rate["credited"][-7:])
        rate["credited_per_day_7d"] = cell(round(total / 7, 2), now)
    else:
        rate["credited_per_day_7d"] = failed(rate["credited_reason"])
    rate["replaced_per_day_7d"] = (cell(round(sum(d["net"] or 0 for d in rate["replaced"][-7:]) / 7, 2), now)
                                   if replace_events else failed(rate["replaced_reason"]))
    # A batch publication moves the count by many bodies in one commit; name the
    # biggest ones so a tall day is read as a batch, not a day's work.
    steps = [{"at": iso(b[0]), "commit": b[1][:10], "change": b[2] - a[2], "subject": b[3][:120]}
             for a, b in zip(credit_events, credit_events[1:]) if b[0] >= now - timedelta(days=DAYS)]
    rate["largest_steps"] = sorted(steps, key=lambda x: -abs(x["change"]))[:3]
    rate["status"] = "ok" if credit_events else "nulled"
    return {"credited": credited, "replaced": replaced, "rate": rate}


if __name__ == "__main__":
    print(json.dumps(collect(), indent=2))
