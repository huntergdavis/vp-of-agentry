"""Deterministic operations board for the VP desk.

The board is a projection of two sources and nothing else:

* Dunking Sheep's daemon API: the global task queue, agent inboxes, scheduled
  dunks, live panes, and the daemon's own health self-check.
* The private operations database: PM-reviewed accounting, quota readings,
  owner-reported subscriptions, host samples, and the published credit series.

No model is consulted anywhere in this module. Every number is read from a
record; nothing is inferred, interpolated, or summarised in prose. A source
that cannot be read stays ``unavailable`` and keeps its age instead of
becoming a zero, and a missing observation is never back-filled.
"""

from __future__ import annotations

import os
import sqlite3
import sys
import threading
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parent
DUNKING_SHEEP = Path(os.getenv("DUNKING_SHEEP_DIR", ROOT.parent / "dunkingsheep"))
if str(DUNKING_SHEEP) not in sys.path:
    sys.path.insert(0, str(DUNKING_SHEEP))

REFRESH_INTERVAL_S = max(10, int(os.getenv("VP_OPS_BOARD_INTERVAL_S", "30")))
CLIENT_TIMEOUT_S = 5.0
TASK_WINDOW_S = 3600
CREDIT_WINDOW_H = 168
ACTIVE_STATUSES = ("open", "in_progress", "blocked")
PRIORITY_RANK = {"urgent": 0, "high": 1, "medium": 2, "low": 3}

LIMITS = [
    "Task, inbox, dunk, pane and daemon values are read live from Dunking Sheep; nothing is inferred between reads.",
    "A source that cannot be read is unavailable with its age; it is never reported as zero.",
    "Poolrad percentages come from the PM-reviewed accounting checkpoint and the reviewed 815 upper bound, not from local drafts, PR counts, or candidate rows.",
    "Pane presence is sampled agent presence, not verified productive work and not token usage.",
    "Fixed subscriptions are owner-reported monthly totals; the hourly figure divides them by calendar hours in the current month.",
    "Quota percentages are direct readings with an observation age; an unobserved provider stays unavailable.",
]


def _now() -> datetime:
    return datetime.now(timezone.utc)


def _iso(value: datetime) -> str:
    return value.astimezone(timezone.utc).isoformat(timespec="seconds").replace("+00:00", "Z")


def _age_seconds(now: datetime, value: Any) -> int | None:
    """Age of a record in seconds, whatever timestamp shape it uses."""
    if value is None:
        return None
    try:
        if isinstance(value, (int, float)) and not isinstance(value, bool):
            moment = datetime.fromtimestamp(float(value), timezone.utc)
        else:
            parsed = datetime.fromisoformat(str(value).replace("Z", "+00:00"))
            moment = parsed if parsed.tzinfo else parsed.replace(tzinfo=timezone.utc)
    except (OSError, OverflowError, TypeError, ValueError):
        return None
    return max(0, int((now - moment.astimezone(timezone.utc)).total_seconds()))


def _seconds_until(now: datetime, value: Any) -> int | None:
    """Seconds until a future timestamp, or None when it is not in the future."""
    if value is None:
        return None
    try:
        if isinstance(value, (int, float)) and not isinstance(value, bool):
            moment = datetime.fromtimestamp(float(value), timezone.utc)
        else:
            parsed = datetime.fromisoformat(str(value).replace("Z", "+00:00"))
            moment = parsed if parsed.tzinfo else parsed.replace(tzinfo=timezone.utc)
    except (OSError, OverflowError, TypeError, ValueError):
        return None
    delta = (moment.astimezone(timezone.utc) - now).total_seconds()
    return max(0, int(delta)) if delta > 0 else None


def _client():
    """A Dunking Sheep client with a short timeout; the daemon is local."""
    from dunk_client import FlockClient

    client = FlockClient.connect_or_start()
    client.timeout = CLIENT_TIMEOUT_S
    return client


def _unavailable(error: str) -> dict:
    return {"state": "unavailable", "error": error}


def _percent(count: int, ceiling: int, bound_kind: str) -> float:
    """Share of the reviewed bound. An upper bound is reported at one decimal."""
    if not ceiling:
        return 0.0
    if bound_kind == "upper_bound":
        return (count * 1000 // ceiling) / 10
    return round(100 * count / ceiling, 1)


# -- Dunking Sheep sources ----------------------------------------------------


def _task_board(client, now: datetime) -> dict:
    try:
        listing = client.call("task_list", include_done=False, limit=200)
    except Exception as exc:  # noqa: BLE001 - a missing source is reported, not raised
        return _unavailable(type(exc).__name__)
    tasks = listing.get("tasks") if isinstance(listing, dict) else listing
    if not isinstance(tasks, list):
        return _unavailable("invalid task list")
    counts: dict[str, int] = {}
    items = []
    for task in tasks:
        status = str(task.get("status", "unknown"))
        counts[status] = counts.get(status, 0) + 1
        items.append({
            "id": task.get("id"),
            "title": task.get("title"),
            "status": status,
            "priority": task.get("priority"),
            "scope": task.get("scope"),
            "assignees": list(task.get("assignees") or []),
            "created_at": task.get("created_at"),
            "age_s": _age_seconds(now, task.get("created_at")),
            "updated_age_s": _age_seconds(now, task.get("updated_at")),
            "lease_expires_in_s": _seconds_until(now, task.get("lease_expires_at")),
            "blocked_by": list(task.get("blocked_by") or []),
            "eligible": bool(task.get("eligible")),
            "claimable": bool(task.get("claimable")),
            "attempts": task.get("attempts"),
        })
    items.sort(key=lambda row: (PRIORITY_RANK.get(row["priority"], 9),
                                -(row["age_s"] or 0), str(row["id"])))
    load: dict[str, int] = {}
    for task in items:
        for assignee in task["assignees"]:
            load[assignee] = load.get(assignee, 0) + 1
    depth = sum(counts.get(status, 0) for status in ACTIVE_STATUSES)
    return {
        "state": "ok",
        "counts": counts,
        "depth": depth,
        "items": items,
        "by_assignee": [{"assignee": name, "count": count}
                         for name, count in sorted(load.items(), key=lambda row: (-row[1], row[0]))],
    }


def _task_metrics(client) -> dict:
    try:
        metrics = client.call("task_metrics", window_s=TASK_WINDOW_S, bucket="hour")
    except Exception as exc:  # noqa: BLE001
        return _unavailable(type(exc).__name__)
    if not isinstance(metrics, dict):
        return _unavailable("invalid task metrics")
    return {
        "state": "ok",
        "window_seconds": (metrics.get("window") or {}).get("seconds"),
        "throughput": metrics.get("throughput") or {},
        "latency_ms": metrics.get("latency_ms") or {},
        "by_actor": metrics.get("by_actor") or {},
    }


def _inbox_board(client) -> dict:
    try:
        stats = client.call("inbox_stats")
    except Exception as exc:  # noqa: BLE001
        return _unavailable(type(exc).__name__)
    mailboxes = (stats or {}).get("mailboxes")
    if not isinstance(mailboxes, list):
        return _unavailable("invalid inbox stats")
    rows = []
    unread_total = 0
    oldest = None
    for row in mailboxes:
        unread = int(row.get("unread") or 0)
        unread_total += unread
        waiting = row.get("oldest_unread_s")
        if unread and waiting is not None:
            oldest = waiting if oldest is None else max(oldest, waiting)
        rows.append({
            "mailbox": row.get("mailbox"),
            "destination": row.get("destination"),
            "unread": unread,
            "total": int(row.get("total") or 0),
            "oldest_unread_s": waiting,
        })
    rows.sort(key=lambda row: (-row["unread"], -row["total"], str(row["mailbox"])))
    return {"state": "ok", "mailboxes": rows, "unread_total": unread_total,
            "oldest_unread_s": oldest}


def _dunk_board(client) -> dict:
    try:
        dunks = client.call("list_dunks")
    except Exception as exc:  # noqa: BLE001
        return _unavailable(type(exc).__name__)
    rows = (dunks or {}).get("dunks")
    if not isinstance(rows, list):
        return _unavailable("invalid dunk list")
    items = [{
        "id": dunk.get("id"),
        "name": dunk.get("name") or dunk.get("id"),
        "target": dunk.get("target_pane_id") or dunk.get("target_agent")
        or dunk.get("target_tab") or dunk.get("target_workspace") or "unknown",
        "target_label": dunk.get("target_label"),
        "interval_minutes": dunk.get("interval_minutes"),
        "running": bool(dunk.get("running")),
        "status": dunk.get("status"),
        "next_send_in_s": dunk.get("next_send_in_s"),
        "send_count": dunk.get("send_count"),
        "skip_count": dunk.get("skip_count"),
        "hold_count": dunk.get("hold_count"),
        "only_when": dunk.get("only_when"),
        "last_error": dunk.get("last_error"),
    } for dunk in rows]
    return {
        "state": "ok",
        "total": len(items),
        "running": sum(1 for dunk in items if dunk["running"]),
        "items": items,
    }


def _pane_board(client) -> dict:
    try:
        panes = client.call("list_panes")
    except Exception as exc:  # noqa: BLE001
        return _unavailable(type(exc).__name__)
    rows = (panes or {}).get("panes")
    if not isinstance(rows, list):
        return _unavailable("invalid pane list")
    items = [{
        "pane_id": pane.get("pane_id"),
        "agent": pane.get("agent"),
        "agent_status": pane.get("agent_status"),
        "workspace_label": pane.get("workspace_label"),
        "tab_label": pane.get("tab_label"),
        "is_self": bool(pane.get("is_self")),
    } for pane in rows]
    working = sum(1 for pane in items if (pane.get("agent_status") or "") == "working")
    return {"state": "ok", "total": len(items), "working": working,
            "idle": len(items) - working, "items": items}


def _daemon_board(client) -> dict:
    try:
        status = client.call("status")
    except Exception as exc:  # noqa: BLE001
        return _unavailable(type(exc).__name__)
    if not isinstance(status, dict):
        return _unavailable("invalid daemon status")
    return {
        "state": "ok",
        "version": status.get("version"),
        "uptime_s": status.get("uptime_s"),
        "herdr_available": status.get("herdr_available"),
        "herdr_hint": status.get("herdr_hint"),
        "queued_messages": status.get("queued_messages"),
        "inbox_unread": status.get("inbox_unread"),
        "task_followers": status.get("task_followers"),
        "quarantined_mailboxes": status.get("quarantined_mailboxes"),
        "dunkers": status.get("dunkers"),
        "running_dunks": status.get("running"),
        "message": status.get("message"),
    }


def _health_board(client) -> dict:
    try:
        health = client.call("health")
    except Exception as exc:  # noqa: BLE001
        return _unavailable(type(exc).__name__)
    if not isinstance(health, dict):
        return _unavailable("invalid health report")
    checks = health.get("checks") or {}
    return {
        "state": "ok",
        "ok": bool(health.get("ok")),
        "problems": list(health.get("problems") or []),
        "repairs": list(health.get("repairs") or []),
        "duration_ms": health.get("duration_ms"),
        "memory_ok": (checks.get("memory") or {}).get("ok"),
        "memory_sources": (checks.get("memory") or {}).get("sources"),
        "memory_chunks": (checks.get("memory") or {}).get("chunks"),
        "queue_depth": (checks.get("memory") or {}).get("queue_depth"),
        "stale_leases": (checks.get("stale_leases") or {}).get("expired_leases"),
        "wal_bytes": checks.get("wal_bytes"),
        "disk_free_bytes": checks.get("disk_free_bytes"),
    }


# -- operations database ------------------------------------------------------


def _ops_db_board(conn: sqlite3.Connection, now: datetime) -> dict:
    from ops_metrics import history, summary

    try:
        snapshot = summary(conn, now=now)
    except (OSError, sqlite3.Error, ValueError, KeyError, TypeError) as exc:
        return _unavailable(type(exc).__name__)
    try:
        timeline = history(conn, now=now, hours=CREDIT_WINDOW_H)
    except (OSError, sqlite3.Error, ValueError, KeyError, TypeError):
        timeline = {"goal_observations": []}
    progress = snapshot.get("function_progress")
    poolrad = {"state": "unavailable", "error": "no reviewed accounting snapshot"}
    if progress:
        poolrad = {
            "state": "ok",
            "strict_full_c": progress["strict_full_c"],
            "identities": progress["verified_game_identities"],
            "ceiling": progress["ceiling"],
            "bound_kind": progress["bound_kind"],
            "strict_percent": progress["strict_percent"],
            "identity_percent": progress["identity_percent"],
            "remaining": max(0, progress["ceiling"] - progress["strict_full_c"]),
            "observed_at": progress["observed_at"],
            "age_s": progress["age_s"],
            "commit_oid": progress["commit_oid"],
            "evidence_ref": progress["evidence_ref"],
        }
    series = [{
        "at": row["observed_at"],
        "value": float(row["value"]),
    } for row in timeline.get("goal_observations", [])
        if row.get("goal_key") == "strict_fullc" and row.get("value") is not None]
    return {
        "state": "ok",
        "poolrad": poolrad,
        "quota": snapshot.get("quota"),
        "quotas": snapshot.get("quotas"),
        "subscriptions": snapshot.get("subscriptions"),
        "monthly_fixed_usd": snapshot.get("monthly_fixed_usd"),
        "fixed_hourly_usd": snapshot.get("fixed_subscription_usd_per_calendar_hour"),
        "calendar_hours_in_month": snapshot.get("calendar_hours_in_month"),
        "host": snapshot.get("host_health"),
        "credit_series": series,
        "pr_merges": timeline.get("pr_merges", []),
        "goals": snapshot.get("goals", []),
        "latest_sample_at": snapshot.get("latest_sample_at"),
        "latest_sample_age_s": snapshot.get("latest_sample_age_s"),
        "sources": snapshot.get("sources", {}),
        "source_freshness": snapshot.get("source_freshness", {}),
    }


# -- board --------------------------------------------------------------------


def build(client, conn: sqlite3.Connection, *, now: datetime | None = None) -> dict:
    """Assemble the board from every source. Never raises for a missing source."""
    now = now or _now()
    board: dict[str, Any] = {
        "generated_at": _iso(now),
        "interval_s": REFRESH_INTERVAL_S,
        "no_model": True,
        "sources": {},
        "limits": LIMITS,
    }
    sections = {
        "tasks": lambda: _task_board(client, now),
        "task_metrics": lambda: _task_metrics(client),
        "inbox": lambda: _inbox_board(client),
        "dunks": lambda: _dunk_board(client),
        "panes": lambda: _pane_board(client),
        "daemon": lambda: _daemon_board(client),
        "health": lambda: _health_board(client),
        "ops_db": lambda: _ops_db_board(conn, now),
    }
    for name, reader in sections.items():
        try:
            board[name] = reader()
        except Exception as exc:  # noqa: BLE001 - one bad source never blanks the board
            board[name] = _unavailable(type(exc).__name__)
        board["sources"][name] = board[name].get("state", "unavailable")

    ops_db = board.get("ops_db") or {}
    board["poolrad"] = ops_db.get("poolrad") if ops_db.get("state") == "ok" else {
        "state": "unavailable", "error": ops_db.get("error", "operations database unavailable")}
    board["headline"] = _headline(board)
    return board


def _headline(board: dict) -> dict:
    """The small, always-correct set of numbers shown at the top of the board."""
    tasks = board.get("tasks") or {}
    inbox = board.get("inbox") or {}
    dunks = board.get("dunks") or {}
    panes = board.get("panes") or {}
    host = (board.get("ops_db") or {}).get("host") or {}
    poolrad = board.get("poolrad") or {}
    return {
        "strict_percent": poolrad.get("strict_percent"),
        "identity_percent": poolrad.get("identity_percent"),
        "strict_full_c": poolrad.get("strict_full_c"),
        "identities": poolrad.get("identities"),
        "ceiling": poolrad.get("ceiling"),
        "task_depth": tasks.get("depth"),
        "task_open": (tasks.get("counts") or {}).get("open"),
        "task_in_progress": (tasks.get("counts") or {}).get("in_progress"),
        "task_blocked": (tasks.get("counts") or {}).get("blocked"),
        "inbox_unread": inbox.get("unread_total"),
        "inbox_oldest_s": inbox.get("oldest_unread_s"),
        "dunks_running": dunks.get("running"),
        "dunks_total": dunks.get("total"),
        "panes_total": panes.get("total"),
        "panes_working": panes.get("working"),
        "tmp_used_fraction": host.get("tmp_used_fraction"),
        "tmp_free_gib": host.get("tmp_free_gib"),
        "host_stale": host.get("stale"),
        "load1": host.get("load1"),
        "cpus": host.get("cpus"),
    }


class BoardCache:
    """A cached board plus the timer that keeps it current.

    The refresh thread only reads. Nothing here calls a model, and a failed
    refresh keeps the previous snapshot with a fresh error note.
    """

    def __init__(self, interval_s: int = REFRESH_INTERVAL_S):
        self.interval_s = interval_s
        self._lock = threading.Lock()
        self._snapshot: dict | None = None
        self._error: str | None = None
        self._stop = threading.Event()
        self._thread: threading.Thread | None = None

    def _build(self) -> dict:
        from ops_metrics import connect

        conn = connect()
        try:
            client = _client()
            return build(client, conn)
        finally:
            conn.close()

    def refresh(self) -> dict:
        try:
            snapshot = self._build()
        except Exception as exc:  # noqa: BLE001 - keep the last good board
            with self._lock:
                self._error = type(exc).__name__
                if self._snapshot is not None:
                    stale = dict(self._snapshot)
                    stale["refresh_error"] = self._error
                    return stale
            raise
        with self._lock:
            self._snapshot = snapshot
            self._error = None
        return snapshot

    def snapshot(self, *, max_age_s: int | None = None) -> dict:
        with self._lock:
            current = self._snapshot
            error = self._error
        age_limit = max_age_s if max_age_s is not None else self.interval_s * 3
        if current is None:
            return self.refresh()
        age = _age_seconds(_now(), current.get("generated_at"))
        if age is not None and age > age_limit:
            try:
                return self.refresh()
            except Exception:  # noqa: BLE001 - serve the stale board with its age
                pass
        with self._lock:
            current = self._snapshot
        if error:
            current = {**current, "refresh_error": error}
        return current

    def start(self) -> None:
        if self._thread and self._thread.is_alive():
            return
        self._stop.clear()

        def loop() -> None:
            while not self._stop.wait(self.interval_s):
                try:
                    self.refresh()
                except Exception:  # noqa: BLE001 - the timer keeps running
                    continue

        self._thread = threading.Thread(target=loop, name="vp-ops-board", daemon=True)
        self._thread.start()

    def stop(self) -> None:
        self._stop.set()
        if self._thread:
            self._thread.join(timeout=5)
            self._thread = None


CACHE = BoardCache()


def main() -> None:
    import argparse
    import json

    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--json", action="store_true", help="print the board as JSON")
    parser.add_argument("--refresh", action="store_true", help="force a fresh read")
    args = parser.parse_args()
    board = CACHE.refresh() if args.refresh else CACHE.snapshot()
    print(json.dumps(board, indent=2, sort_keys=True, default=str))


if __name__ == "__main__":
    main()
