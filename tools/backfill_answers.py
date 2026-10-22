#!/usr/bin/env python3
"""Backfill answer links for historical owner messages, carefully.

For every owner message with answered_at IS NULL, link it to the FIRST agent
message in the same channel with a higher id. If no later agent message exists
the message is genuinely unanswered and stays NULL. A link older than two hours
is reported as a late answer.

Dry run by default; --apply commits in one transaction. The counts are printed
and are meant to go in the commit message.
"""

from __future__ import annotations

import argparse
import sqlite3
import sys
from datetime import datetime
from pathlib import Path

DEFAULT_DB = Path(__file__).resolve().parent.parent / "data" / "messages.sqlite3"
LATE_S = 2 * 3600


def _epoch(stamp):
    if not stamp:
        return None
    try:
        return datetime.fromisoformat(str(stamp).replace("Z", "+00:00")).timestamp()
    except ValueError:
        return None


def plan(conn):
    """Return [(owner_id, channel, brief_id, brief_created_at, late_s)] and leftovers."""
    rows = conn.execute(
        "SELECT id, channel, created_at FROM messages "
        "WHERE role='owner' AND answered_at IS NULL ORDER BY id").fetchall()
    links, unanswered = [], []
    for owner_id, channel, created_at in rows:
        brief = conn.execute(
            "SELECT id, created_at FROM messages WHERE channel=? AND role='agent' AND id>? "
            "ORDER BY id LIMIT 1", (channel, owner_id)).fetchone()
        if brief is None:
            unanswered.append(owner_id)
            continue
        late = None
        start, end = _epoch(created_at), _epoch(brief[1])
        if start is not None and end is not None:
            late = max(0, end - start)
        links.append((owner_id, channel, brief[0], brief[1], late))
    return links, unanswered


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--db", type=Path, default=DEFAULT_DB)
    parser.add_argument("--apply", action="store_true",
                        help="commit the links (default: report only)")
    args = parser.parse_args(argv)
    conn = sqlite3.connect(args.db)
    try:
        links, unanswered = plan(conn)
        late = [item for item in links if item[4] is not None and item[4] > LATE_S]
        print(f"db: {args.db}")
        print(f"owner messages unlinked before: {len(links) + len(unanswered)}")
        print(f"backfilled: {len(links)}")
        print(f"still unanswered (no later agent message): {len(unanswered)}")
        print(f"late answers (>2h): {len(late)}")
        if late:
            print("late ids (owner -> brief, seconds):")
            for owner_id, _channel, brief_id, _stamp, seconds in late:
                print(f"  {owner_id} -> {brief_id}: {int(seconds)}s")
        if unanswered:
            print(f"unanswered ids: {unanswered}")
        if not args.apply:
            print("dry run: nothing written; re-run with --apply")
            return 0
        with conn:  # one transaction; a failure rolls every link back
            for owner_id, _channel, brief_id, stamp, _late in links:
                conn.execute(
                    "UPDATE messages SET answer_id=?, answered_at=? "
                    "WHERE id=? AND answered_at IS NULL AND role='owner'",
                    (brief_id, stamp, owner_id))
        remaining = conn.execute(
            "SELECT COUNT(*) FROM messages WHERE role='owner' AND answered_at IS NULL"
        ).fetchone()[0]
        print(f"applied; owner messages still unlinked: {remaining}")
        return 0
    finally:
        conn.close()


if __name__ == "__main__":
    sys.exit(main())
