"""Provider allowance windows, separate from fixed subscription prices."""
from __future__ import annotations

import json
import math
import sqlite3
import subprocess
from datetime import datetime, timezone

MAX_AGE_S = 300
SOURCE = "dunkingsheep --json usage"


def _number(value):
    return value if isinstance(value, (int, float)) and not isinstance(value, bool) and math.isfinite(value) else None


def _time(value):
    try:
        if _number(value) is not None:
            return datetime.fromtimestamp(value, timezone.utc)
        parsed = datetime.fromisoformat(str(value).replace("Z", "+00:00"))
        return parsed.replace(tzinfo=timezone.utc) if parsed.tzinfo is None else parsed.astimezone(timezone.utc)
    except (ValueError, TypeError, OSError, OverflowError):
        return None


def read_usage():
    result = subprocess.run(["dunkingsheep", "--json", "usage", "--max-age", "60"],
                            capture_output=True, text=True, timeout=20)
    try:
        payload = json.loads(result.stdout)
    except ValueError:
        raise ValueError((result.stderr or "usage command returned invalid JSON").strip()[:240]) from None
    # A nonzero exit can mean one provider failed; preserve per-provider statuses.
    if not isinstance(payload, list) or any(not isinstance(row, dict) for row in payload):
        raise ValueError("usage command returned an invalid provider list")
    return payload


def project(readings, subscriptions, now, *, error=None):
    generated = now.isoformat().replace("+00:00", "Z")
    prices = {row["provider"]: row for row in subscriptions}
    providers = []
    seen = set()
    for reading in readings:
        name = reading.get("provider")
        if not isinstance(name, str) or not name:
            continue
        seen.add(name)
        measured = _time(reading.get("measured_at"))
        age = max(0, int((now - measured).total_seconds())) if measured else None
        state = reading.get("status") or "unknown"
        if state == "ok" and (age is None or age > MAX_AGE_S):
            state = "stale"
        meaning = reading.get("meaning")
        windows = []
        if meaning == "percent_used":
            raw_windows = reading.get("windows")
            for window in raw_windows if isinstance(raw_windows, list) else []:
                if not isinstance(window, dict):
                    continue
                reset = _time(window.get("resets_at"))
                window_state = "expired" if reset and reset <= now else state
                used, left = _number(window.get("percent_used")), _number(window.get("percent_remaining"))
                if used is None and left is None:
                    window_state = "unknown"
                windows.append({
                    "name": str(window.get("name") or "unnamed"),
                    "state": window_state, "percent_used": used, "percent_remaining": left,
                    "resets_at": reset.isoformat().replace("+00:00", "Z") if reset else None,
                })
        subscription = prices.get("opencode" if name == "opencode-go" else name)
        price = None
        if subscription:
            price = {"monthly_usd": subscription["monthly_usd_cents"] / 100,
                     "state": "ok", "source": "owner-reported subscription",
                     "observed_at": subscription["observed_at"]}
        extra = reading.get("extra_usage")
        extra = ({key: extra.get(key) for key in
                  ("used_credits", "monthly_limit", "utilization", "spend_limit_reached")}
                 if isinstance(extra, dict) else None)
        if extra:
            for key in ("used_credits", "monthly_limit", "utilization"):
                extra[key] = _number(extra[key])
            if not isinstance(extra["spend_limit_reached"], bool):
                extra["spend_limit_reached"] = None
        local = None
        if meaning == "local_session_estimate":
            local = {key: _number(reading.get(key)) for key in
                     ("session_cost_usd", "last_context_tokens", "session_messages_with_usage")}
        providers.append({
            "provider": name, "source": SOURCE, "state": state, "meaning": meaning,
            "generated_at": generated,
            "measured_at": measured.isoformat().replace("+00:00", "Z") if measured else None,
            "age_s": age, "reason": str(reading.get("reason") or "")[:240],
            "windows": windows, "subscription": price, "extra_usage": extra, "local_estimate": local,
        })
    for name, subscription in prices.items():
        canonical = "opencode-go" if name == "opencode" else name
        if canonical not in seen:
            providers.append({
                "provider": canonical, "source": SOURCE, "state": "unavailable",
                "meaning": "percent_used", "generated_at": generated, "measured_at": None,
                "age_s": None, "reason": error or "no provider reading", "windows": [],
                "extra_usage": None, "local_estimate": None,
                "subscription": {"monthly_usd": subscription["monthly_usd_cents"] / 100,
                                 "state": "ok", "source": "owner-reported subscription",
                                 "observed_at": subscription["observed_at"]},
            })
    return {"source": SOURCE, "state": "unavailable" if error else "ok",
            "generated_at": generated, "error": error, "providers": providers,
            "dollars_remaining": None,
            "dollars_reason": "Dollars remaining and per-agent dollar balances are unknown. Subscriptions are fixed prices; allowance percentages are shared provider limits."}


def build(conn, now):
    from ops_metrics import PROJECT
    subscriptions = []
    subscription_error = None
    try:
        subscriptions = [dict(row) for row in conn.execute(
            "SELECT provider,monthly_usd_cents,observed_at FROM subscription_costs s "
            "WHERE project=? AND id=(SELECT MAX(id) FROM subscription_costs "
            "WHERE project=s.project AND provider=s.provider) ORDER BY provider", (PROJECT,))]
    except sqlite3.Error:
        subscription_error = "Subscription source unavailable"
    try:
        readings, error = read_usage(), None
    except (OSError, subprocess.SubprocessError, ValueError) as exc:
        readings, error = [], str(exc)[:240]
    budget = project(readings, subscriptions, now, error=error)
    budget["subscription_error"] = subscription_error
    return budget
