"""Private, evidence-labelled operations metrics for the VP desk.

This collector stores observations, never terminal transcripts or message text.
Missing sources remain missing; a failed poll does not become a zero.
"""

from __future__ import annotations

import argparse
import json
import os
import sqlite3
import subprocess
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parent
DATA = Path(os.environ.get("VP_DATA_DIR", ROOT / "data"))
DB = Path(os.environ.get("VP_OPS_DB", DATA / "operations.sqlite3"))
MESSAGE_DB = DATA / "messages.sqlite3"
POOLRAD_REPO = Path(os.environ.get("POOLRAD_REPO", ROOT.parent / "poolrad-decomp"))
PROJECT = "poolrad"
POLL_INTERVAL_S = 60
EXTERNAL_INTERVAL_S = 300

SCHEMA = """
CREATE TABLE IF NOT EXISTS collection_runs (
    id INTEGER PRIMARY KEY,
    observed_at TEXT NOT NULL,
    panes_state TEXT NOT NULL,
    github_state TEXT NOT NULL,
    vp_messages_state TEXT NOT NULL,
    dunk_metrics_state TEXT NOT NULL,
    errors_json TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS runs_observed_at ON collection_runs(observed_at);
CREATE TABLE IF NOT EXISTS lane_assignments (
    project TEXT NOT NULL,
    pane_id TEXT NOT NULL,
    role TEXT NOT NULL CHECK(role IN ('pm','coder','reviewer','other')),
    focus TEXT NOT NULL,
    updated_at TEXT NOT NULL,
    PRIMARY KEY(project,pane_id)
);
CREATE TABLE IF NOT EXISTS pane_samples (
    run_id INTEGER NOT NULL REFERENCES collection_runs(id) ON DELETE CASCADE,
    pane_id TEXT NOT NULL,
    project TEXT NOT NULL,
    agent_kind TEXT,
    agent_status TEXT,
    role TEXT NOT NULL,
    PRIMARY KEY(run_id,pane_id)
);
CREATE INDEX IF NOT EXISTS pane_samples_pane_run ON pane_samples(pane_id,run_id);
CREATE TABLE IF NOT EXISTS pr_latest (
    project TEXT NOT NULL,
    number INTEGER NOT NULL,
    state TEXT NOT NULL,
    head_oid TEXT,
    merged_at TEXT,
    first_seen_at TEXT NOT NULL,
    last_seen_at TEXT NOT NULL,
    PRIMARY KEY(project,number)
);
CREATE TABLE IF NOT EXISTS pr_state_events (
    project TEXT NOT NULL,
    number INTEGER NOT NULL,
    state TEXT NOT NULL,
    head_oid TEXT NOT NULL DEFAULT '',
    observed_at TEXT NOT NULL,
    merged_at TEXT,
    PRIMARY KEY(project,number,state,head_oid)
);
CREATE TABLE IF NOT EXISTS vp_message_counts (
    run_id INTEGER NOT NULL REFERENCES collection_runs(id) ON DELETE CASCADE,
    channel TEXT NOT NULL,
    role TEXT NOT NULL,
    total INTEGER NOT NULL,
    PRIMARY KEY(run_id,channel,role)
);
CREATE TABLE IF NOT EXISTS quota_observations (
    id INTEGER PRIMARY KEY,
    project TEXT NOT NULL,
    provider TEXT NOT NULL,
    cohort TEXT NOT NULL,
    pane_id TEXT NOT NULL,
    observed_at TEXT NOT NULL,
    precision TEXT NOT NULL CHECK(precision IN ('second','minute','reported')),
    weekly_percent_left REAL NOT NULL CHECK(weekly_percent_left BETWEEN 0 AND 100),
    reset_at TEXT NOT NULL,
    evidence_ref TEXT NOT NULL,
    UNIQUE(project,provider,cohort,observed_at,evidence_ref)
);
CREATE INDEX IF NOT EXISTS quota_recent ON quota_observations(project,provider,cohort,observed_at);
CREATE TABLE IF NOT EXISTS goal_observations (
    id INTEGER PRIMARY KEY,
    project TEXT NOT NULL,
    scope TEXT NOT NULL CHECK(scope IN ('local','overall')),
    goal_key TEXT NOT NULL,
    observed_at TEXT NOT NULL,
    status TEXT NOT NULL CHECK(status IN ('planned','in_progress','blocked','verified','unknown')),
    value REAL,
    target REAL,
    unit TEXT,
    evidence_ref TEXT NOT NULL,
    note TEXT NOT NULL DEFAULT '',
    UNIQUE(project,goal_key,observed_at,evidence_ref)
);
CREATE INDEX IF NOT EXISTS goals_latest ON goal_observations(project,goal_key,id);
CREATE TABLE IF NOT EXISTS dunk_metrics_snapshots (
    id INTEGER PRIMARY KEY,
    observed_at TEXT NOT NULL,
    generated_at TEXT NOT NULL,
    interval_start TEXT NOT NULL,
    interval_end TEXT NOT NULL,
    schema_version INTEGER NOT NULL,
    payload_json TEXT NOT NULL,
    UNIQUE(generated_at,interval_start,interval_end)
);
"""


def utc_now() -> datetime:
    return datetime.now(timezone.utc)


def iso(value: datetime) -> str:
    if value.tzinfo is None:
        raise ValueError("timestamp requires a timezone")
    return value.astimezone(timezone.utc).isoformat(timespec="seconds").replace("+00:00", "Z")


def parse_time(value: str) -> datetime:
    parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    if parsed.tzinfo is None:
        raise ValueError("timestamp requires a timezone offset")
    return parsed.astimezone(timezone.utc)


def connect(path: Path = DB) -> sqlite3.Connection:
    path.parent.mkdir(parents=True, exist_ok=True)
    old_umask = os.umask(0o077)
    try:
        conn = sqlite3.connect(path, timeout=10)
    finally:
        os.umask(old_umask)
    os.chmod(path, 0o600)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys=ON")
    conn.execute("PRAGMA journal_mode=WAL")
    conn.executescript(SCHEMA)
    return conn


def command_json(argv: list[str], *, cwd: Path | None = None) -> Any:
    result = subprocess.run(argv, cwd=cwd, capture_output=True, text=True, timeout=25, check=False)
    if result.returncode:
        raise RuntimeError(f"{argv[0]} {argv[-1]} exited {result.returncode}")
    return json.loads(result.stdout)


def _source_due(conn: sqlite3.Connection, column: str, now: datetime) -> bool:
    if column not in {"github_state", "dunk_metrics_state"}:
        raise ValueError("unknown source")
    row = conn.execute(
        f"SELECT observed_at FROM collection_runs WHERE {column}='ok' ORDER BY id DESC LIMIT 1"
    ).fetchone()
    return row is None or (now - parse_time(row["observed_at"])).total_seconds() >= EXTERNAL_INTERVAL_S


def _vp_counts(path: Path = MESSAGE_DB) -> list[tuple[str, str, int]]:
    if not path.exists():
        raise FileNotFoundError("VP message database is absent")
    with sqlite3.connect(f"file:{path}?mode=ro", uri=True) as conn:
        return [(str(channel), str(role), int(total)) for channel, role, total in conn.execute(
            "SELECT channel,role,COUNT(*) FROM messages GROUP BY channel,role"
        )]


def _valid_dunk_metrics(value: Any) -> dict:
    if not isinstance(value, dict) or value.get("schema_version") != 1:
        raise ValueError("Dunking Sheep metrics schema_version 1 required")
    interval = value.get("interval")
    if not isinstance(interval, dict):
        raise ValueError("Dunking Sheep metrics interval required")
    for key in ("start", "end"):
        if not isinstance(interval.get(key), str):
            raise ValueError(f"Dunking Sheep interval.{key} required")
        parse_time(interval[key])
    if not isinstance(value.get("generated_at"), str):
        raise ValueError("Dunking Sheep generated_at required")
    parse_time(value["generated_at"])
    # The upstream contract is aggregate-only. Reject known content keys before persistence.
    forbidden = {"body", "text", "subject", "filename", "email", "token", "secret"}
    def check(item: Any) -> None:
        if isinstance(item, dict):
            if forbidden.intersection(k.lower() for k in item):
                raise ValueError("Dunking Sheep metrics contains content-bearing keys")
            for child in item.values():
                check(child)
        elif isinstance(item, list):
            for child in item:
                check(child)
    check(value)
    return value


def collect(conn: sqlite3.Connection, *, now: datetime | None = None) -> dict:
    now = now or utc_now()
    observed_at = iso(now)
    states = {"panes": "skipped", "github": "skipped", "vp_messages": "skipped", "dunk_metrics": "skipped"}
    errors: dict[str, str] = {}
    panes: list[dict] = []
    prs: list[dict] = []
    counts: list[tuple[str, str, int]] = []
    metrics: dict | None = None
    try:
        result = command_json(["dunkingsheep", "--json", "panes"])
        panes = result["panes"]
        if not isinstance(panes, list):
            raise ValueError("panes must be a list")
        states["panes"] = "ok"
    except (OSError, RuntimeError, ValueError, KeyError, subprocess.TimeoutExpired) as exc:
        states["panes"] = "unavailable"
        errors["panes"] = type(exc).__name__
    try:
        counts = _vp_counts()
        states["vp_messages"] = "ok"
    except (OSError, sqlite3.Error) as exc:
        states["vp_messages"] = "unavailable"
        errors["vp_messages"] = type(exc).__name__
    if _source_due(conn, "github_state", now):
        try:
            prs = command_json(
                ["gh", "pr", "list", "--state", "all", "--limit", "100", "--json",
                 "number,state,headRefOid,mergedAt"],
                cwd=POOLRAD_REPO,
            )
            if not isinstance(prs, list):
                raise ValueError("PR list must be a list")
            states["github"] = "ok"
        except (OSError, RuntimeError, ValueError, subprocess.TimeoutExpired) as exc:
            states["github"] = "unavailable"
            errors["github"] = type(exc).__name__
    if _source_due(conn, "dunk_metrics_state", now):
        try:
            metrics = _valid_dunk_metrics(command_json(["dunkingsheep", "--json", "metrics", "--window", "3600"]))
            states["dunk_metrics"] = "ok"
        except (OSError, RuntimeError, ValueError, subprocess.TimeoutExpired) as exc:
            states["dunk_metrics"] = "unavailable"
            errors["dunk_metrics"] = type(exc).__name__

    with conn:
        run_id = conn.execute(
            "INSERT INTO collection_runs(observed_at,panes_state,github_state,vp_messages_state,dunk_metrics_state,errors_json) "
            "VALUES(?,?,?,?,?,?)",
            (observed_at, states["panes"], states["github"], states["vp_messages"],
             states["dunk_metrics"], json.dumps(errors, sort_keys=True)),
        ).lastrowid
        assignments = {row["pane_id"]: row["role"] for row in conn.execute(
            "SELECT pane_id,role FROM lane_assignments WHERE project=?", (PROJECT,)
        )}
        for pane in panes:
            if pane.get("workspace_label") != "poolrad-decomp":
                continue
            pane_id = str(pane.get("pane_id", ""))
            if not pane_id:
                continue
            role = assignments.get(pane_id, "other")
            conn.execute(
                "INSERT INTO pane_samples(run_id,pane_id,project,agent_kind,agent_status,role) VALUES(?,?,?,?,?,?)",
                (run_id, pane_id, PROJECT, pane.get("agent_type") or pane.get("agent"),
                 pane.get("agent_status"), role),
            )
        for channel, role, total in counts:
            conn.execute(
                "INSERT INTO vp_message_counts(run_id,channel,role,total) VALUES(?,?,?,?)",
                (run_id, channel, role, total),
            )
        for pr in prs:
            number = int(pr["number"])
            state = str(pr["state"])
            head = pr.get("headRefOid") or ""
            merged_at = pr.get("mergedAt")
            conn.execute(
                "INSERT INTO pr_latest(project,number,state,head_oid,merged_at,first_seen_at,last_seen_at) "
                "VALUES(?,?,?,?,?,?,?) ON CONFLICT(project,number) DO UPDATE SET "
                "state=excluded.state,head_oid=excluded.head_oid,merged_at=excluded.merged_at,last_seen_at=excluded.last_seen_at",
                (PROJECT, number, state, head, merged_at, observed_at, observed_at),
            )
            conn.execute(
                "INSERT OR IGNORE INTO pr_state_events(project,number,state,head_oid,observed_at,merged_at) "
                "VALUES(?,?,?,?,?,?)",
                (PROJECT, number, state, head, observed_at, merged_at),
            )
        if metrics is not None:
            conn.execute(
                "INSERT OR IGNORE INTO dunk_metrics_snapshots"
                "(observed_at,generated_at,interval_start,interval_end,schema_version,payload_json) "
                "VALUES(?,?,?,?,?,?)",
                (observed_at, metrics["generated_at"], metrics["interval"]["start"],
                 metrics["interval"]["end"], 1, json.dumps(metrics, separators=(",", ":"), sort_keys=True)),
            )
    return summary(conn, now=now)


def record_quota(
    conn: sqlite3.Connection, *, pane: str, percent_left: float, reset_at: str,
    observed_at: str, evidence: str, provider: str = "codex",
    cohort: str = "poolrad-codex", precision: str = "second",
) -> None:
    if not 0 <= percent_left <= 100:
        raise ValueError("percent left must be between 0 and 100")
    if precision not in {"second", "minute", "reported"}:
        raise ValueError("invalid timestamp precision")
    with conn:
        conn.execute(
            "INSERT OR IGNORE INTO quota_observations"
            "(project,provider,cohort,pane_id,observed_at,precision,weekly_percent_left,reset_at,evidence_ref) "
            "VALUES(?,?,?,?,?,?,?,?,?)",
            (PROJECT, provider, cohort, pane, iso(parse_time(observed_at)), precision,
             percent_left, iso(parse_time(reset_at)), evidence),
        )


def record_goal(
    conn: sqlite3.Connection, *, key: str, scope: str, status: str, evidence: str,
    value: float | None = None, target: float | None = None, unit: str | None = None,
    note: str = "", observed_at: str | None = None,
) -> None:
    if scope not in {"local", "overall"} or status not in {"planned", "in_progress", "blocked", "verified", "unknown"}:
        raise ValueError("invalid goal scope or status")
    when = iso(parse_time(observed_at)) if observed_at else iso(utc_now())
    with conn:
        conn.execute(
            "INSERT INTO goal_observations"
            "(project,scope,goal_key,observed_at,status,value,target,unit,evidence_ref,note) "
            "VALUES(?,?,?,?,?,?,?,?,?,?)",
            (PROJECT, scope, key, when, status, value, target, unit, evidence, note),
        )


def summary(conn: sqlite3.Connection, *, now: datetime | None = None) -> dict:
    now = now or utc_now()
    run = conn.execute("SELECT * FROM collection_runs ORDER BY id DESC LIMIT 1").fetchone()
    staff = {"pm": {}, "coder": {}, "reviewer": {}, "other": {}}
    if run and run["panes_state"] == "ok":
        for row in conn.execute(
            "SELECT role,COALESCE(agent_status,'unknown') status,COUNT(*) n "
            "FROM pane_samples WHERE run_id=? GROUP BY role,status", (run["id"],)
        ):
            staff[row["role"]][row["status"]] = row["n"]
    quota_rows = conn.execute(
        "SELECT * FROM quota_observations WHERE project=? ORDER BY observed_at DESC,id DESC LIMIT 2",
        (PROJECT,),
    ).fetchall()
    quota = None
    if quota_rows:
        latest = quota_rows[0]
        quota = {
            "pane": latest["pane_id"], "provider": latest["provider"], "cohort": latest["cohort"],
            "observed_at": latest["observed_at"], "age_s": max(0, int((now - parse_time(latest["observed_at"])).total_seconds())),
            "precision": latest["precision"], "weekly_percent_left": latest["weekly_percent_left"],
            "reset_at": latest["reset_at"], "evidence_ref": latest["evidence_ref"],
            "burn_percentage_points_per_hour": None,
        }
        if len(quota_rows) > 1:
            prior = quota_rows[1]
            hours = (parse_time(latest["observed_at"]) - parse_time(prior["observed_at"])).total_seconds() / 3600
            if (hours >= 0.5 and latest["cohort"] == prior["cohort"]
                    and latest["provider"] == prior["provider"] and latest["reset_at"] == prior["reset_at"]):
                quota["burn_percentage_points_per_hour"] = round(
                    (prior["weekly_percent_left"] - latest["weekly_percent_left"]) / hours, 2
                )
    goals = [dict(row) for row in conn.execute(
        "SELECT scope,goal_key,observed_at,status,value,target,unit,evidence_ref,note "
        "FROM goal_observations g WHERE project=? AND id=("
        "SELECT MAX(id) FROM goal_observations WHERE project=g.project AND goal_key=g.goal_key"
        ") ORDER BY scope,goal_key", (PROJECT,)
    )]
    prs = [dict(row) for row in conn.execute(
        "SELECT number,state,merged_at,last_seen_at FROM pr_latest WHERE project=? "
        "ORDER BY number DESC LIMIT 12", (PROJECT,)
    )]
    telemetry = conn.execute(
        "SELECT generated_at,interval_start,interval_end,schema_version,payload_json "
        "FROM dunk_metrics_snapshots ORDER BY id DESC LIMIT 1"
    ).fetchone()
    vp_counts = []
    if run and run["vp_messages_state"] == "ok":
        vp_counts = [dict(row) for row in conn.execute(
            "SELECT channel,role,total FROM vp_message_counts WHERE run_id=? ORDER BY channel,role",
            (run["id"],),
        )]
    return {
        "generated_at": iso(now),
        "project": PROJECT,
        "latest_sample_at": run["observed_at"] if run else None,
        "latest_sample_age_s": max(0, int((now - parse_time(run["observed_at"])).total_seconds())) if run else None,
        "sources": {name: run[f"{name}_state"] for name in ("panes", "github", "vp_messages", "dunk_metrics")} if run else {},
        "staff": staff,
        "quota": quota,
        "goals": goals,
        "tracked_recent_prs": prs,
        "vp_message_counts": vp_counts,
        "dunk_metrics": {
            "generated_at": telemetry["generated_at"],
            "age_s": max(0, int((now - parse_time(telemetry["generated_at"])).total_seconds())),
            "interval": {"start": telemetry["interval_start"], "end": telemetry["interval_end"]},
            "schema_version": telemetry["schema_version"],
            "data": json.loads(telemetry["payload_json"]),
        } if telemetry else None,
        "limitations": [
            "Pane state is sampled presence, not verified productive work or token consumption.",
            "PR list tracks recent visible PRs, not a whole-game completion denominator.",
            "Quota burn is percentage points per hour only after two direct readings at least 30 minutes apart with one reset.",
            "Money and token cost are unknown without a billing source.",
        ],
    }


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--db", type=Path, default=DB, help="private SQLite database path")
    sub = parser.add_subparsers(dest="command", required=True)
    sub.add_parser("init", help="create the private database")
    sub.add_parser("collect", help="sample known local APIs and update the database")
    sub.add_parser("summary", help="print a source-labelled JSON summary")
    quota = sub.add_parser("quota", help="record a directly observed weekly quota reading")
    quota.add_argument("--pane", required=True)
    quota.add_argument("--left", type=float, required=True)
    quota.add_argument("--reset", required=True, help="ISO timestamp with timezone")
    quota.add_argument("--observed-at", required=True, help="ISO timestamp with timezone")
    quota.add_argument("--precision", choices=["second", "minute", "reported"], default="second")
    quota.add_argument("--evidence", required=True)
    quota.add_argument("--provider", default="codex")
    quota.add_argument("--cohort", default="poolrad-codex")
    goal = sub.add_parser("goal", help="record a sourced local or overall goal checkpoint")
    goal.add_argument("--key", required=True)
    goal.add_argument("--scope", choices=["local", "overall"], required=True)
    goal.add_argument("--status", choices=["planned", "in_progress", "blocked", "verified", "unknown"], required=True)
    goal.add_argument("--value", type=float)
    goal.add_argument("--target", type=float)
    goal.add_argument("--unit")
    goal.add_argument("--evidence", required=True)
    goal.add_argument("--note", default="")
    goal.add_argument("--observed-at")
    lane = sub.add_parser("lane", help="update a pane's project role and focus")
    lane.add_argument("--pane", required=True)
    lane.add_argument("--role", choices=["pm", "coder", "reviewer", "other"], required=True)
    lane.add_argument("--focus", required=True)
    args = parser.parse_args()
    conn = connect(args.db)
    try:
        if args.command == "init":
            print(json.dumps({"database": str(args.db), "initialized": True}))
        elif args.command == "collect":
            print(json.dumps(collect(conn), sort_keys=True))
        elif args.command == "summary":
            print(json.dumps(summary(conn), sort_keys=True))
        elif args.command == "quota":
            record_quota(conn, pane=args.pane, percent_left=args.left, reset_at=args.reset,
                         observed_at=args.observed_at, precision=args.precision,
                         evidence=args.evidence, provider=args.provider, cohort=args.cohort)
            print(json.dumps({"recorded": True}))
        elif args.command == "goal":
            record_goal(conn, key=args.key, scope=args.scope, status=args.status,
                        value=args.value, target=args.target, unit=args.unit,
                        evidence=args.evidence, note=args.note, observed_at=args.observed_at)
            print(json.dumps({"recorded": True}))
        elif args.command == "lane":
            with conn:
                conn.execute(
                    "INSERT INTO lane_assignments(project,pane_id,role,focus,updated_at) VALUES(?,?,?,?,?) "
                    "ON CONFLICT(project,pane_id) DO UPDATE SET role=excluded.role,focus=excluded.focus,updated_at=excluded.updated_at",
                    (PROJECT, args.pane, args.role, args.focus, iso(utc_now())),
                )
            print(json.dumps({"recorded": True}))
    finally:
        conn.close()


if __name__ == "__main__":
    main()
