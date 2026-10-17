"""Measure an isolated Claude trial from explicit session message anchors.

Claude session JSONL repeats assistant message records. Usage is per API
message, so each message ID is counted once. The selected interval must
contain only the trial and one model; timestamps alone do not prove that.
Only usage metadata is emitted, never prompts or account details.
"""

import argparse
import json
from pathlib import Path


TOKEN_FIELDS = (
    "input_tokens",
    "cache_creation_input_tokens",
    "cache_read_input_tokens",
    "output_tokens",
)


def anchors(path: Path) -> list[dict]:
    found = []
    by_id = {}
    with path.open(encoding="utf-8") as stream:
        for line_number, line in enumerate(stream, 1):
            event = json.loads(line)
            message = event.get("message") or {}
            if event.get("type") != "assistant" or not isinstance(message, dict):
                continue
            usage = message.get("usage")
            if usage is None:
                continue
            message_id, model = message.get("id"), message.get("model")
            if not isinstance(message_id, str) or not message_id or not isinstance(model, str) or not model:
                raise ValueError(f"assistant usage lacks message ID or model on line {line_number}")
            if not isinstance(usage, dict) or any(
                type(usage.get(field)) is not int or usage[field] < 0 for field in TOKEN_FIELDS
            ):
                raise ValueError(f"invalid Claude usage on line {line_number}")
            tokens = {field: usage[field] for field in TOKEN_FIELDS}
            previous = by_id.get(message_id)
            if previous is not None:
                if previous["model"] != model or previous["tokens"] != tokens:
                    raise ValueError(f"conflicting repeated Claude message on line {line_number}")
                previous["last_line"] = line_number
                previous["last_timestamp"] = event.get("timestamp")
                continue
            point = {"index": len(found), "line": line_number, "last_line": line_number,
                     "timestamp": event.get("timestamp"), "last_timestamp": event.get("timestamp"),
                     "model": model, "tokens": tokens}
            found.append(point)
            by_id[message_id] = point
    if not found:
        raise ValueError("no complete Claude usage messages in session log")
    return found


def usage_between(points: list[dict], start_index: int, end_index: int) -> dict:
    if not 0 <= start_index < end_index < len(points):
        raise ValueError("start and end must be ordered message indices in this session")
    selected = points[start_index + 1:end_index + 1]
    models = {point["model"] for point in selected}
    if len(models) != 1:
        raise ValueError("mixed Claude models in trial interval")
    totals = {field: sum(point["tokens"][field] for point in selected) for field in TOKEN_FIELDS}
    totals["total_input_tokens"] = sum(totals[field] for field in TOKEN_FIELDS[:3])
    return {"start": points[start_index], "end": points[end_index],
            "message_count": len(selected), "model": models.pop(), "tokens": totals}


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
                  **usage_between(points, args.start_index, args.end_index)}
        result["usage_source"] = (
            f"claude-session-message-usage:{args.session_log.name}:"
            f"{args.start_index}-{args.end_index}"
        )
    else:
        parser.error("provide both --start-index and --end-index")
    print(json.dumps(result, sort_keys=True))


if __name__ == "__main__":
    main()
