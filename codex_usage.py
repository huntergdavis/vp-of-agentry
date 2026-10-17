"""Read explicit Codex session token anchors for isolated trial measurement.

Wall-clock slicing of token events can miss a final turn.  This tool requires
two event indices from the same session and rejects counters that reset between
them.  It emits only token counters and event metadata, never prompts or
account details.
"""

import argparse
import json
from pathlib import Path


TOKEN_FIELDS = (
    "input_tokens",
    "cached_input_tokens",
    "cache_write_input_tokens",
    "output_tokens",
    "reasoning_output_tokens",
    "total_tokens",
)


def anchors(path: Path) -> list[dict]:
    found = []
    with path.open(encoding="utf-8") as stream:
        for line_number, line in enumerate(stream, 1):
            event = json.loads(line)
            payload = event.get("payload") or {}
            if event.get("type") != "event_msg" or payload.get("type") != "token_count":
                continue
            totals = (payload.get("info") or {}).get("total_token_usage")
            if totals is None:
                continue
            if any(type(totals.get(field)) is not int or totals[field] < 0 for field in TOKEN_FIELDS):
                raise ValueError(f"invalid token counter on line {line_number}")
            found.append({"index": len(found), "timestamp": event.get("timestamp"),
                          "line": line_number, "tokens": {field: totals[field] for field in TOKEN_FIELDS}})
    if not found:
        raise ValueError("no complete token counters in session log")
    return found


def usage_delta(points: list[dict], start_index: int, end_index: int) -> dict:
    if not 0 <= start_index < end_index < len(points):
        raise ValueError("start and end must be ordered token event indices in this session")
    for previous, current in zip(points[start_index:end_index], points[start_index + 1:end_index + 1]):
        if any(current["tokens"][field] < previous["tokens"][field] for field in TOKEN_FIELDS):
            raise ValueError("token counter reset inside trial interval")
    start, end = points[start_index], points[end_index]
    return {"start": start, "end": end,
            "tokens": {field: end["tokens"][field] - start["tokens"][field] for field in TOKEN_FIELDS}}


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("session_log", type=Path)
    parser.add_argument("--start-index", type=int)
    parser.add_argument("--end-index", type=int)
    args = parser.parse_args()
    points = anchors(args.session_log)
    if args.start_index is None and args.end_index is None:
        result = {"session": args.session_log.name, "latest_anchor": points[-1]}
    elif args.start_index is not None and args.end_index is not None:
        result = {"session": args.session_log.name,
                  **usage_delta(points, args.start_index, args.end_index)}
        result["usage_source"] = (
            f"codex-session-token-count:{args.session_log.name}:"
            f"{args.start_index}-{args.end_index}"
        )
    else:
        parser.error("provide both --start-index and --end-index")
    print(json.dumps(result, sort_keys=True))


if __name__ == "__main__":
    main()
