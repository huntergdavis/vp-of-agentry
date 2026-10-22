#!/usr/bin/env python3
"""Cost per agent, free-model work volume and the usage panel, from local files.

No model, no network: harness session logs on this host (Claude JSONL, Codex
rollouts, pi sessions, the OpenCode database), the free-model ledger, and the
provider-usage readings the metrics collector already stored. Every number is a
{value, as_of, reason} cell; a harness that keeps no dollar figure is null with
that reason, never a zero.

An "agent" here is a harness working in one checkout directory. Two panes in
the same checkout share a row: session logs carry a directory, not a pane.

Codex alone keeps ~5 GB of rollouts a month, so every log is read
incrementally: the cache keeps a byte offset per file and hourly buckets, and a
tick only reads what was appended since the last one.
"""

from __future__ import annotations

import json
import os
import re
import sqlite3
import subprocess
import time
from datetime import datetime, timedelta, timezone
from pathlib import Path
from zoneinfo import ZoneInfo

ROOT = Path(__file__).resolve().parent.parent
HOME = Path(os.environ.get("VP_COST_HOME", Path.home()))
CACHE = ROOT / "data" / "agent-costs-cache.json"
OPS_DB = Path(os.environ.get("VP_OPS_DB", ROOT / "data" / "operations.sqlite3"))
LEDGER = Path(os.environ.get(
    "FREE_MODEL_LEDGER", "/home/hunter/workspace/dunkingsheep/docs/FREE_MODEL_LEDGER.md"))
LOCAL = ZoneInfo("America/Los_Angeles")
KEEP_DAYS = 40  # a calendar month to date plus slack; older buckets are dropped
CACHE_VERSION = 1
# Token columns, normalised across harnesses: uncached input, cache read,
# cache write, output (reasoning included). The fifth slot is dollars, only
# where the harness itself recorded one; the sixth is the message count.
IN, CREAD, CWRITE, OUT, USD, MSGS = range(6)
# Free tier by catalog name. 'big-pickle' is OpenCode's free model; anything
# else must say free in its id. A recorded cost of 0 is not proof of free.
FREE_NAMES = {"big-pickle"}
NO_DOLLARS = {
    "claude": "Claude logs record tokens, not dollars; covered by the fixed subscription",
    "codex": "Codex rollouts record tokens, not dollars; covered by the fixed subscription",
}


def is_free(model):
    name = (model or "").rsplit("/", 1)[-1]
    return name in FREE_NAMES or name.endswith("-free") or name.endswith(":free")


def iso(stamp):
    return stamp.astimezone(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ") if stamp else None


def cell(value, as_of, reason=None):
    return {"value": value, "as_of": iso(as_of) if as_of else None, "reason": reason}


def failed(reason):
    return cell(None, None, reason)


def hour_key(stamp):
    """'2026-10-22T15' (UTC) from an ISO string or epoch seconds; None if unparseable."""
    try:
        if isinstance(stamp, (int, float)):
            moment = datetime.fromtimestamp(stamp, timezone.utc)
        else:
            moment = datetime.fromisoformat(str(stamp).replace("Z", "+00:00"))
        return moment.astimezone(timezone.utc).strftime("%Y-%m-%dT%H")
    except (ValueError, OverflowError, OSError):
        return None


def add(buckets, hour, model, tokens, usd=None):
    if hour is None:
        return
    row = buckets.setdefault(hour, {}).setdefault(model or "unknown", [0, 0, 0, 0, None, 0])
    for slot, value in enumerate(tokens):
        row[slot] += max(0, int(value or 0))
    if usd is not None:
        row[USD] = (row[USD] or 0.0) + float(usd)
    row[MSGS] += 1


# --- per-harness line readers: each updates one file's state in place --------

def read_claude(state, event):
    if event.get("type") != "assistant":
        return
    message = event.get("message") or {}
    usage = message.get("usage")
    ident = message.get("id")
    if not isinstance(usage, dict) or not ident:
        return
    state["cwd"] = state.get("cwd") or event.get("cwd")
    # Claude repeats an assistant record per content block with the same usage;
    # each API message counts once.
    seen = state.setdefault("seen", [])
    if ident in seen[-64:]:
        return
    seen.append(ident)
    del seen[:-64]
    add(state["buckets"], hour_key(event.get("timestamp")), message.get("model"),
        (usage.get("input_tokens"), usage.get("cache_read_input_tokens"),
         usage.get("cache_creation_input_tokens"), usage.get("output_tokens")))


def read_codex(state, event):
    payload = event.get("payload") or {}
    kind = event.get("type")
    if kind == "session_meta":
        state["cwd"] = state.get("cwd") or payload.get("cwd")
        return
    if kind == "turn_context":
        state["model"] = payload.get("model") or state.get("model")
        state["cwd"] = state.get("cwd") or payload.get("cwd")
        return
    if kind != "event_msg" or payload.get("type") != "token_count":
        return
    total = ((payload.get("info") or {}).get("total_token_usage")) or {}
    if not total:
        return
    # The cumulative counter is the truth; the same event is often emitted
    # twice. Delta it, and a counter that went down is a reset, not negative work.
    prev = state.get("prev") or {}
    delta = {}
    for name in ("input_tokens", "cached_input_tokens", "output_tokens"):
        now_v, was = int(total.get(name) or 0), int(prev.get(name) or 0)
        delta[name] = now_v - was if now_v >= was else now_v
    state["prev"] = {k: int(total.get(k) or 0) for k in delta}
    if not any(delta.values()):
        return
    cached = delta["cached_input_tokens"]
    add(state["buckets"], hour_key(event.get("timestamp")), state.get("model"),
        (delta["input_tokens"] - cached, cached, 0, delta["output_tokens"]))


def read_pi(state, event):
    if event.get("type") == "session":
        state["cwd"] = state.get("cwd") or event.get("cwd")
        return
    if event.get("type") != "message":
        return
    message = event.get("message") or {}
    usage = message.get("usage")
    if message.get("role") != "assistant" or not isinstance(usage, dict):
        return
    model = message.get("model")
    provider = message.get("provider")
    cost = (usage.get("cost") or {}).get("total")
    add(state["buckets"], hour_key(event.get("timestamp")),
        f"{provider}/{model}" if provider else model,
        (usage.get("input"), usage.get("cacheRead"), usage.get("cacheWrite"), usage.get("output")),
        cost if isinstance(cost, (int, float)) else None)


HARNESSES = {
    # harness: (root, glob, reader)
    "claude": (HOME / ".claude" / "projects", "**/*.jsonl", read_claude),
    "codex": (HOME / ".codex" / "sessions", "**/*.jsonl", read_codex),
    "pi": (HOME / ".pi" / "agent" / "sessions", "*/*.jsonl", read_pi),
}
CODEX_NEEDLES = (b'"token_count"', b'"turn_context"', b'"session_meta"')
PI_NEEDLES = (b'"usage"', b'"type":"session"')


def wanted(harness, line):
    """Cheap byte test before json.loads; most lines are prompts and tool output."""
    if harness == "claude":
        return b'"usage"' in line
    if harness == "codex":
        return any(n in line for n in CODEX_NEEDLES)
    return any(n in line for n in PI_NEEDLES)


def scan_file(harness, path, state, reader):
    """Read what was appended since the cached offset. Returns bytes read."""
    stat = path.stat()
    if stat.st_size < state.get("offset", 0):
        # Truncated or replaced: what we counted is no longer this file.
        state.clear()
        state["harness"] = harness
    state.setdefault("buckets", {})
    offset = state.get("offset", 0)
    if stat.st_size == offset:
        return 0
    # Stream: one Codex rollout passed 1.5 GB; never hold a file in memory.
    position = offset
    with path.open("rb") as handle:
        handle.seek(offset)
        for raw in handle:
            if not raw.endswith(b"\n"):
                break  # a line still being written; take it next tick
            position += len(raw)
            if not wanted(harness, raw):
                continue
            try:
                reader(state, json.loads(raw))
            except (ValueError, TypeError, AttributeError):
                state["bad_lines"] = state.get("bad_lines", 0) + 1
    state["offset"] = position
    state["mtime"] = stat.st_mtime
    return position - offset


def load_cache(path):
    try:
        data = json.loads(path.read_text())
        if data.get("version") == CACHE_VERSION:
            return data
    except (OSError, ValueError, AttributeError):
        pass
    return {"version": CACHE_VERSION, "files": {}}


def write_atomic(path, payload):
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(path.suffix + ".tmp")
    with open(temporary, "w", encoding="utf-8") as handle:
        handle.write(json.dumps(payload, separators=(",", ":")))
        handle.flush()
        os.fsync(handle.fileno())
    os.replace(temporary, path)


def scan_logs(cache, horizon):
    """Bring every recent session file up to date. Returns per-harness status."""
    files = cache["files"]
    cutoff = horizon.timestamp()
    status = {}
    for harness, (root, pattern, reader) in HARNESSES.items():
        if not root.is_dir():
            status[harness] = {"ok": False, "reason": f"{root} absent", "files": 0, "bytes_read": 0}
            continue
        seen = read = 0
        errors = []
        for path in root.glob(pattern):
            try:
                if path.stat().st_mtime < cutoff:
                    continue
                state = files.setdefault(str(path), {"harness": harness})
                state["harness"] = harness
                read += scan_file(harness, path, state, reader)
                seen += 1
            except OSError as exc:
                errors.append(f"{path.name}: {exc.strerror}")
        status[harness] = {"ok": True, "files": seen, "bytes_read": read,
                           "reason": "; ".join(errors[:3]) or None}
    # Forget files that have aged out or vanished.
    keep = (horizon - timedelta(days=1)).strftime("%Y-%m-%dT%H")
    for name in list(files):
        state = files[name]
        if not Path(name).exists() or state.get("mtime", 0) < cutoff:
            del files[name]
            continue
        state["buckets"] = {h: v for h, v in state.get("buckets", {}).items() if h >= keep}
    return status


def opencode_rows(month_start, db=None):
    """Per-session, per-model sums from OpenCode's own message records."""
    db = db or HOME / ".local" / "share" / "opencode" / "opencode.db"
    if not db.is_file():
        return None, f"{db} absent"
    sql = (
        "SELECT session_id, json_extract(data,'$.path.cwd'), "
        "json_extract(data,'$.providerID'), json_extract(data,'$.modelID'), "
        "time_created, json_extract(data,'$.cost'), "
        "json_extract(data,'$.tokens.input'), json_extract(data,'$.tokens.cache.read'), "
        "json_extract(data,'$.tokens.cache.write'), json_extract(data,'$.tokens.output') "
        "FROM message WHERE time_created >= ? AND json_extract(data,'$.role')='assistant'")
    try:
        with sqlite3.connect(f"file:{db}?mode=ro", uri=True, timeout=2) as conn:
            rows = conn.execute(sql, (int(month_start.timestamp() * 1000),)).fetchall()
    except sqlite3.Error as exc:
        return None, f"{db}: {exc}"
    return rows, None


def pane_map(command=None):
    """(harness, cwd) -> pane names now open there. None when panes are unreadable."""
    argv = command or [os.environ.get("DUNKINGSHEEP_BIN", "dunkingsheep"), "--json", "panes"]
    try:
        proc = subprocess.run(argv, capture_output=True, text=True, timeout=30)
        data = json.loads(proc.stdout)
    except (OSError, subprocess.SubprocessError, ValueError):
        return None
    panes = data if isinstance(data, list) else data.get("panes", [])
    found = {}
    for pane in panes:
        agent, cwd = pane.get("agent"), pane.get("cwd")
        if agent and cwd:
            label = pane.get("tab_label") or pane.get("pane_id")
            found.setdefault((agent, cwd), []).append(f"{pane.get('pane_id')} {label}")
    return found


def windows(now):
    local = now.astimezone(LOCAL)
    month = local.replace(day=1, hour=0, minute=0, second=0, microsecond=0)
    return {"24h": (now - timedelta(hours=24)).strftime("%Y-%m-%dT%H"),
            "month": month.astimezone(timezone.utc).strftime("%Y-%m-%dT%H")}, month


def summarise(cache, opencode, now):
    """Fold buckets into per-agent and per-free-model totals for both windows."""
    starts, _ = windows(now)
    agents, free = {}, {}

    def blank():
        return {w: [0, 0, 0, 0, None, 0] for w in starts}

    def fold(total, row):
        for slot in (IN, CREAD, CWRITE, OUT, MSGS):
            total[slot] += row[slot]
        if row[USD] is not None:
            total[USD] = (total[USD] or 0.0) + row[USD]

    def account(harness, cwd, session, hour, model, row):
        key = (harness, cwd or "unknown")
        entry = agents.setdefault(key, {"totals": blank(), "sessions": {w: set() for w in starts},
                                        "models": set()})
        entry["models"].add(model)
        for window, start in starts.items():
            if hour >= start:
                fold(entry["totals"][window], row)
                entry["sessions"][window].add(session)
                if is_free(model):
                    item = free.setdefault(model, {"totals": blank(),
                                                   "runs": {w: set() for w in starts},
                                                   "output": {w: {} for w in starts},
                                                   "harnesses": set()})
                    fold(item["totals"][window], row)
                    item["runs"][window].add(session)
                    item["output"][window][session] = item["output"][window].get(session, 0) + row[OUT]
                    item["harnesses"].add(harness)

    for path, state in cache["files"].items():
        for hour, models in state.get("buckets", {}).items():
            for model, row in models.items():
                account(state["harness"], state.get("cwd"), path, hour, model, row)
    for session, cwd, provider, model, created, cost, t_in, t_read, t_write, t_out in opencode or ():
        row = [t_in or 0, t_read or 0, t_write or 0, t_out or 0,
               float(cost) if cost is not None else None, 1]
        account("opencode", cwd, session, hour_key(created / 1000),
                f"{provider}/{model}" if provider else model, row)
    return agents, free


def tokens_cell(total, now):
    return cell(total[IN] + total[CREAD] + total[CWRITE] + total[OUT], now)


def cost_rows(agents, panes, now):
    rows = []
    for (harness, cwd), entry in agents.items():
        row = {"harness": harness, "checkout": cwd,
               "label": f"{harness} · {Path(cwd).name if cwd != 'unknown' else 'unknown dir'}",
               "panes": panes.get((harness, cwd), []) if panes is not None else None,
               "models": sorted(m for m in entry["models"] if m)}
        for window, total in entry["totals"].items():
            row[f"tokens_{window}"] = tokens_cell(total, now)
            row[f"output_tokens_{window}"] = cell(total[OUT], now)
            # Cache reads are most of every total and cost a tenth or less; this is the rest.
            row[f"fresh_tokens_{window}"] = cell(total[IN] + total[CWRITE] + total[OUT], now)
            row[f"sessions_{window}"] = cell(len(entry["sessions"][window]), now)
            if harness in NO_DOLLARS:
                row[f"usd_{window}"] = failed(NO_DOLLARS[harness])
            elif total[USD] is None and total[MSGS]:
                row[f"usd_{window}"] = failed(f"{harness} recorded no cost on these messages")
            else:
                row[f"usd_{window}"] = cell(round(total[USD] or 0.0, 4), now)
        if row["tokens_month"]["value"]:
            rows.append(row)
    rows.sort(key=lambda r: -(r["tokens_month"]["value"] or 0))
    return rows


LEDGER_OUTCOMES = ("accepted after rework", "accepted", "rejected", "failed")


def ledger_outcomes(path=None):
    """Outcome counts per model from the free-model ledger table. (counts, as_of, reason)."""
    path = path or LEDGER
    try:
        text = path.read_text()
        as_of = datetime.fromtimestamp(path.stat().st_mtime, timezone.utc)
    except OSError as exc:
        return None, None, f"{path}: {exc.strerror}"
    header, counts = None, {}
    for line in text.splitlines():
        if not line.startswith("|"):
            header = None if not line.strip() else header
            continue
        cells = [c.strip().strip("*").strip() for c in line.strip("|").split("|")]
        if header is None:
            header = [c.lower() for c in cells]
            continue
        if set("".join(cells)) <= set("-: "):
            continue
        if "model" not in header or "outcome" not in header:
            continue
        record = dict(zip(header, cells))
        outcome = record["outcome"].lower()
        bucket = next((o for o in LEDGER_OUTCOMES if outcome.startswith(o)), "other")
        model = counts.setdefault(record["model"], {o: 0 for o in LEDGER_OUTCOMES + ("other",)})
        model[bucket] += 1
    if not counts:
        return None, as_of, f"{path} has no outcome rows"
    return counts, as_of, None


def free_section(free, outcomes, outcomes_at, outcomes_reason, now):
    models = []
    for model, item in sorted(free.items(), key=lambda kv: -len(kv[1]["runs"]["month"])):
        models.append({
            "model": model, "harnesses": sorted(item["harnesses"]),
            "runs_24h": cell(len(item["runs"]["24h"]), now),
            "runs_month": cell(len(item["runs"]["month"]), now),
            # A session that got no output tokens back is almost always an endpoint failure.
            "runs_no_output_month": cell(sum(1 for v in item["output"]["month"].values() if not v), now),
            "tokens_month": tokens_cell(item["totals"]["month"], now),
            "output_tokens_month": cell(item["totals"]["month"][OUT], now),
        })
    reviewed = None
    if outcomes is not None:
        reviewed = [{"model": m, **{k.replace(" ", "_"): cell(v, outcomes_at) for k, v in c.items()}}
                    for m, c in sorted(outcomes.items())]
    runs_month = sum(m["runs_month"]["value"] for m in models)
    recorded = sum(sum(c.values()) for c in outcomes.values()) if outcomes else None
    return {
        "models": models,
        "runs_24h": cell(sum(m["runs_24h"]["value"] for m in models), now),
        "runs_month": cell(runs_month, now),
        "outcomes": reviewed,
        "outcomes_recorded": cell(recorded, outcomes_at) if recorded is not None else failed(outcomes_reason),
        "outcomes_source": LEDGER.name,
        "method": "a run is one harness session (pi file or OpenCode session) that called a free model; "
                  "free = catalog id ending -free or :free, or big-pickle",
        "truth": "Runs count sessions that called a free model, not useful work. Only ledger rows are "
                 "reviewed outcomes; a run with no ledger row is unreviewed, not accepted.",
    }


def usage_section(db=None):
    """Latest provider windows and the owner-reported subscriptions, never summed."""
    db = db or OPS_DB
    if not db.is_file():
        return {"status": "nulled", "reason": f"{db} absent", "providers": [], "subscriptions": []}
    try:
        with sqlite3.connect(f"file:{db}?mode=ro", uri=True, timeout=2) as conn:
            conn.row_factory = sqlite3.Row
            latest = conn.execute(
                "SELECT observed_at,status,payload_json FROM provider_usage_snapshots "
                "ORDER BY id DESC LIMIT 1").fetchone()
            subs = [dict(r) for r in conn.execute(
                "SELECT provider, monthly_usd_cents, observed_at, evidence_ref FROM subscription_costs s "
                "WHERE id=(SELECT MAX(id) FROM subscription_costs WHERE project=s.project AND provider=s.provider)"
                " ORDER BY provider")]
    except sqlite3.Error as exc:
        return {"status": "nulled", "reason": f"{db}: {exc}", "providers": [], "subscriptions": []}
    subscriptions = [{"provider": s["provider"],
                      "monthly_usd": {"value": s["monthly_usd_cents"] / 100, "as_of": s["observed_at"],
                                      "reason": None},
                      "evidence": "owner-reported"} for s in subs]
    if latest is None:
        return {"status": "nulled", "reason": "no provider usage reading stored yet",
                "providers": [], "subscriptions": subscriptions}
    try:
        payload = json.loads(latest["payload_json"])
    except ValueError:
        return {"status": "nulled", "reason": "stored usage reading is not JSON",
                "providers": [], "subscriptions": subscriptions}
    providers = []
    for reading in payload.get("readings") or []:
        measured = reading.get("measured_at")
        as_of = (datetime.fromtimestamp(measured, timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
                 if isinstance(measured, (int, float)) else latest["observed_at"])
        ok = reading.get("status") == "ok"
        item = {"provider": reading.get("provider"), "status": reading.get("status"),
                "meaning": reading.get("meaning"), "as_of": as_of,
                "reason": None if ok else (reading.get("error") or reading.get("status")),
                "windows": [{"name": w.get("name"),
                             "percent_used": {"value": w.get("percent_used"), "as_of": as_of,
                                              "reason": None if w.get("percent_used") is not None
                                              else "provider gave no percentage"},
                             "resets_at": w.get("resets_at")}
                            for w in reading.get("windows") or []],
                "notes": (reading.get("notes") or [])[:3]}
        extra = reading.get("extra_usage")
        if isinstance(extra, dict) and extra.get("is_enabled"):
            scale = 10 ** int(extra.get("decimal_places") or 0)
            item["extra_usage"] = {
                "used": {"value": round(extra["used_credits"] / scale, 2) if extra.get("used_credits") is not None else None,
                         "as_of": as_of, "reason": None},
                "limit": {"value": round(extra["monthly_limit"] / scale, 2) if extra.get("monthly_limit") is not None else None,
                          "as_of": as_of, "reason": None},
                "currency": extra.get("currency"),
                "truth": "Usage billed beyond the subscription, as the provider reports it this month.",
            }
        if reading.get("meaning") == "local_session_estimate":
            item["truth"] = "A local session estimate at list price, not a bill and not a quota."
        providers.append(item)
    return {"status": "ok" if payload.get("exit_code") == 0 else "partial",
            "observed_at": latest["observed_at"], "providers": providers,
            "subscriptions": subscriptions,
            "truth": "Fixed subscriptions and window percentages are different units and are never summed; "
                     "a percentage is the provider's own window, not dollars."}


def collect(*, now=None, cache_path=None, panes_command=None):
    """Returns {cost_per_agent, free_model, usage, status}; writes the scan cache."""
    now = now or datetime.now(timezone.utc)
    started = time.time()
    cache_path = Path(cache_path or CACHE)
    _, month_start = windows(now)
    horizon = month_start.astimezone(timezone.utc) - timedelta(days=KEEP_DAYS - 31)
    if os.environ.get("VP_COST_SCAN", "1") == "0":
        reason = "harness log scan disabled (VP_COST_SCAN=0)"
        return {"cost_per_agent": {"status": "nulled", "reason": reason, "rows": []},
                "free_model": {"status": "nulled", "reason": reason},
                "usage": usage_section()}
    cache = load_cache(cache_path)
    status = scan_logs(cache, horizon)
    opencode, opencode_reason = opencode_rows(month_start)
    status["opencode"] = {"ok": opencode is not None, "reason": opencode_reason,
                          "messages": len(opencode) if opencode is not None else None}
    write_atomic(cache_path, cache)
    agents, free = summarise(cache, opencode, now)
    panes = pane_map(panes_command)
    outcomes, outcomes_at, outcomes_reason = ledger_outcomes()
    failed_sources = {h: s["reason"] for h, s in status.items() if not s["ok"]}
    return {
        "cost_per_agent": {
            "status": "ok" if not failed_sources else "partial",
            "as_of": iso(now), "failed_sources": failed_sources, "sources": status,
            "panes_reason": None if panes is not None else "dunkingsheep panes unreadable",
            "windows": {"24h": "rolling 24 hours",
                        "month": f"since {month_start.strftime('%Y-%m-%d')} (America/Los_Angeles)"},
            "rows": cost_rows(agents, panes or {}, now),
            "truth": "Dollars are only what a harness recorded at list price (pi, OpenCode); they are not "
                     "bills. Claude and Codex record tokens only. One row is a harness in a checkout, "
                     "not a pane. Tokens include cache reads, which dominate and are cheap.",
            "scan_s": round(time.time() - started, 2),
        },
        "free_model": {"status": "ok", **free_section(free, outcomes, outcomes_at, outcomes_reason, now)},
        "usage": usage_section(),
    }


if __name__ == "__main__":
    print(json.dumps(collect(cache_path=Path(os.environ.get("VP_COST_CACHE", CACHE))), indent=2))
