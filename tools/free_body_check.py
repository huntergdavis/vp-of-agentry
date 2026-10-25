#!/usr/bin/env python3
"""Mechanically judge a free model's DECODE of one Poolrad body.

The nvidia 550B free model, given tools, decoded `OVL_0025_06AF` correctly: right body,
right overlay base arithmetic (31618 - 0x6AF = 0x74D3), every instruction byte matching
the file - and one endianness slip on the `retf 4` immediate (`CA 00 04` instead of
`CA 04 00`). That is the shape of free-model error: shallow and mechanical, not deep and
plausible. So a free decode is cheap to check and cheap to fix.

This tool does exactly one thing: it takes the report's claimed FILE OFFSET and byte dump,
reads those bytes from the game file itself, and compares. It prints one of

    BYTES MATCH        the dump is byte-identical to the file at the claimed offset
    BYTES DIFFER       shows the first differing byte, file value vs claimed value
    PREFIX ONLY        the dump is shorter than --expect-length: bytes may match but it is not a decode
    NO DUMP            the report printed no checkable byte dump
    OFFSET UNRESOLVED  the claimed offset is outside the file

It does not judge the prose and must not be read as a credit decision.

Usage: free_body_check.py <report.md> [--ovr PATH]
Exit: 0 match, 1 differ/unresolved, 2 no dump / usage error.
"""
from __future__ import annotations

import re
import sys
from pathlib import Path

DEFAULT_OVR = Path("resources/DOS/POOLRAD/GAME.OVR")

# "file offset 31618" / "offset 0x7B82" / "+31618" / "@ 31618"
OFFSET_RE = re.compile(
    r"(?:file\s+offset|offset|@|\bat\b)[\s:=`'\"]*(0x[0-9A-Fa-f]+|\d{4,7})", re.I
)
# a run of >=6 hex byte pairs, tolerating "55 89 e5", "5589E5" and "0x55, 0x89"
BYTES_RE = re.compile(r"(?:\b[0-9A-Fa-f]{2}\b[\s,]*){6,}")
BYTES_COMPACT_RE = re.compile(r"\b(?:[0-9A-Fa-f]{2}){12,}\b")


def claimed_offsets(text: str) -> list[int]:
    """Every plausible offset the report names, in the order it names them."""
    vals: list[int] = []
    for m in OFFSET_RE.findall(text):
        try:
            v = int(m, 16) if m.lower().startswith("0x") else int(m)
        except ValueError:
            continue
        if 0 < v < 2 * 1024 * 1024 and v not in vals:
            vals.append(v)
    return vals


LISTING_LINE_RE = re.compile(r"^\s*((?:[0-9A-Fa-f]{2}[ \t]+)+)")


def claimed_bytes(text: str) -> bytes | None:
    # objdump-style listing: "55              push bp" - the bytes are the leading column.
    # Two or more such lines in a row is a dump; one alone could be a stray hex cell.
    runs: list[bytes] = []
    cur = bytearray()
    for line in text.splitlines():
        m = LISTING_LINE_RE.match(line)
        if m and re.search(r"\S{2,}", line[m.end():]):  # something follows the bytes
            cur.extend(bytes.fromhex(re.sub(r"[^0-9A-Fa-f]", "", m.group(1))))
        else:
            if len(cur) >= 6:
                runs.append(bytes(cur))
            cur = bytearray()
    if len(cur) >= 6:
        runs.append(bytes(cur))
    best: bytes | None = max(runs, key=len) if runs else None
    for m in BYTES_RE.finditer(text):
        raw = re.sub(r"[^0-9A-Fa-f]", "", m.group(0))
        if len(raw) % 2:
            raw = raw[:-1]
        b = bytes.fromhex(raw)
        if best is None or len(b) > len(best):
            best = b
    for m in BYTES_COMPACT_RE.finditer(text):
        b = bytes.fromhex(m.group(0))
        if best is None or len(b) > len(best):
            best = b
    return best


def main(argv: list[str]) -> int:
    if len(argv) < 2:
        print("usage: free_body_check.py <report.md> [--ovr PATH]", file=sys.stderr)
        return 2
    rep = Path(argv[1])
    ovr = DEFAULT_OVR
    expect: int | None = None
    expect_len: int | None = None
    rest = argv[2:]
    while rest:
        if rest[0] == "--ovr" and len(rest) > 1:
            ovr = Path(rest[1]); rest = rest[2:]
        elif rest[0] == "--expect-offset" and len(rest) > 1:
            expect = int(rest[1], 0); rest = rest[2:]
        elif rest[0] == "--expect-length" and len(rest) > 1:
            expect_len = int(rest[1], 0); rest = rest[2:]
        else:
            rest = rest[1:]
    if not rep.exists():
        print(f"REFUSED: no report at {rep}", file=sys.stderr)
        return 2
    if not ovr.exists():
        print(f"REFUSED: no game file at {ovr}", file=sys.stderr)
        return 2
    text = rep.read_text(errors="replace")
    offs = claimed_offsets(text)
    cb = claimed_bytes(text)
    data = ovr.read_bytes()
    print(f"== {rep}")
    if cb is None:
        print("   NO DUMP: the report printed no byte dump, so nothing is checkable.")
        return 2
    claimed_has_expected = expect is not None and expect in offs
    if expect is not None:
        # The body implies where its bytes live. A claimed offset that differs does not get
        # a second chance: a model must not pass by naming the right bytes at a wrong place.
        offs = [expect]
    if not offs:
        print(f"   OFFSET UNRESOLVED: {len(cb)} bytes claimed, no file offset found.")
        return 1
    # Try every offset the report names: a report may mention the overlay base before the
    # file offset, so the first number is not necessarily the subject.
    if expect_len is not None and len(cb) < expect_len:
        ok = 0 <= offs[0] and data[offs[0] : offs[0] + len(cb)] == cb
        print(f"   PREFIX ONLY: dump has {len(cb)} of the expected {expect_len} bytes"
              f" ({'matching the file' if ok else 'and they differ from the file'}); not a decode.")
        return 1
    for cand in offs:
        if 0 <= cand and data[cand : cand + len(cb)] == cb:
            print(f"   BYTES MATCH: {len(cb)} bytes at {cand} are byte-identical to {ovr.name}.")
            return 0
    off = offs[0]
    got = data[off : off + len(cb)]
    print(f"   tried offsets: {', '.join(str(o) for o in offs[:5])} (none matched)")
    for i, (x, y) in enumerate(zip(got, cb)):
        if x != y:
            print(
                f"   BYTES DIFFER: first difference at +{i} (offset {off + i}): "
                f"file {x:02x}, claimed {y:02x}."
            )
            print(f"      file   : {' '.join(f'{v:02x}' for v in got[:48])}")
            print(f"      claimed: {' '.join(f'{v:02x}' for v in cb[:48])}")
            return 1
    print(f"   BYTES DIFFER: claimed dump is longer/shorter than the file slice ({len(got)} vs {len(cb)}).")
    return 1


if __name__ == "__main__":
    sys.exit(main(sys.argv))
