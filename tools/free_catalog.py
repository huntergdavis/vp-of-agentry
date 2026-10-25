#!/usr/bin/env python3
"""Daily watch of free models on OpenRouter and OpenCode.

Writes the Dunking Sheep context article subject `free-model-catalog` (class
fact, global) and keeps first_seen / last_seen in data/free_catalog_state.json.
An arrival is only LISTED here; it counts as working after the four-body gate.
"""
import json
import subprocess
import sys
import urllib.request
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
STATE = ROOT / "data" / "free_catalog_state.json"
SUBJECT = "free-model-catalog"


def now():
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def openrouter_free():
    request = urllib.request.Request("https://openrouter.ai/api/v1/models",
                                     headers={"User-Agent": "vp-free-catalog"})
    with urllib.request.urlopen(request, timeout=30) as response:
        rows = json.load(response)["data"]
    ids = set()
    for row in rows:
        pricing = row.get("pricing") or {}
        if str(row["id"]).endswith(":free") or (
                pricing.get("prompt") == "0" and pricing.get("completion") == "0"):
            ids.add("openrouter/" + row["id"])
    return ids


def opencode_free():
    """OpenCode models: free-tier ids, plus every opencode-go id (plan-included)."""
    out = subprocess.run(["opencode", "models"], capture_output=True, text=True,
                         timeout=60, check=True).stdout.split()
    return {m for m in out if m.startswith("opencode-go/") or m.endswith("-free")
            or m.endswith(":free")}


def main():
    state = json.loads(STATE.read_text()) if STATE.exists() else {"models": {}}
    sources, errors = {}, []
    for name, fetch in (("openrouter", openrouter_free), ("opencode", opencode_free)):
        try:
            sources[name] = fetch()
        except Exception as exc:  # a failed source is reported, never read as "no models"
            errors.append(f"{name}: {type(exc).__name__}: {exc}")
    stamp = now()
    seen = set().union(*sources.values()) if sources else set()
    arrivals = sorted(m for m in seen if m not in state["models"])
    first_run = not state["models"]
    for model in seen:
        row = state["models"].setdefault(model, {"first_seen": stamp})
        row["last_seen"] = stamp
    checked_sources = set(sources)
    gone = sorted(m for m, row in state["models"].items()
                  if m not in seen and row.get("last_seen") and m.split("/")[0] in checked_sources
                  and not row.get("gone_at"))
    for model in gone:
        state["models"][model]["gone_at"] = stamp
    state["last_checked"] = stamp
    state["errors"] = errors
    STATE.parent.mkdir(exist_ok=True)
    STATE.write_text(json.dumps(state, indent=1, sort_keys=True))

    lines = [f"# Free model catalogue (watched, not verified)", "",
             f"Checked {stamp}. Sources ok: {', '.join(sorted(sources)) or 'none'}."]
    if errors:
        lines += ["", "SOURCE ERRORS (a failed source is not an empty one):"] + [f"- {e}" for e in errors]
    lines += ["", "An arrival is LISTED, not working: a model becomes usable only after "
              "the four-body gate (proposals that reproduced a body).", ""]
    lines += [f"## Arrivals this check ({len(arrivals)})"]
    lines += [f"- {m}" for m in arrivals] if arrivals and not first_run else \
        (["- baseline run: all models below are first-seen now"] if first_run else ["- none"])
    lines += ["", f"## Departed this check ({len(gone)})"] + ([f"- {m}" for m in gone] or ["- none"])
    lines += ["", f"## Current ({len(seen)})"]
    lines += [f"- {m} (first seen {state['models'][m]['first_seen']})" for m in sorted(seen)]
    body = "\n".join(lines) + "\n"

    tmp = ROOT / "data" / "free_catalog_article.md"
    tmp.write_text(body)
    slug = state.get("article_slug")
    if slug:
        result = subprocess.run(["dunkingsheep", "context", "supersede", "--global", slug, str(tmp)],
                                capture_output=True, text=True)
    else:
        result = subprocess.run(["dunkingsheep", "context", "add", "--class", "fact",
                                 "--subject", SUBJECT, "--global", "--source", "tools/free_catalog.py",
                                 str(tmp)], capture_output=True, text=True)
    if result.returncode != 0:
        print("article write FAILED:", result.stderr.strip() or result.stdout.strip(), file=sys.stderr)
        return 2
    if not slug:
        word = (result.stdout.strip().split() or [""])[-1]
        state["article_slug"] = word.split("/")[-1]
        STATE.write_text(json.dumps(state, indent=1, sort_keys=True))
    print(f"catalogue: {len(seen)} free/included models, {len(arrivals)} arrivals, "
          f"{len(gone)} departed, errors={len(errors)}")
    for model in arrivals:
        print("  arrival:", model)
    return 0 if not errors else 1


if __name__ == "__main__":
    sys.exit(main())
