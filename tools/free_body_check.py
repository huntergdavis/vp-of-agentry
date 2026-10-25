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
    OFFSET UNRESOLVED  the one strict offset declaration is missing, competing, malformed or wrong

Requires exactly one FILE OFFSET: <decimal> (0x<hex>) declaration. All parsed
byte sequences must match; no matching dump can rescue a conflicting one.
Addressed rows must be contiguous. Address labels may be VMAs; their relocation
provenance and all assembly/prose semantics are NOT verified by this tool.
It must not be read as a credit decision.

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



# Address labels may be file offsets or a disassembler VMA. Check their
# continuity, not relocation provenance; the strict header fixes the file slice.
ADDRESS_LINE_RE = re.compile(
    r"^\s*(?:(?:0x)?([0-9A-Fa-f]{1,8}):[ \t]+|"
    r"([0-9A-Fa-f]{6,8})[ \t]+|([0-9A-Fa-f]{4})[ \t]{2,})(.*)$"
)
HEX_TOKEN_RE = re.compile(r"(?:[0-9A-Fa-f]{2})+")
INLINE_BYTES_RE = re.compile(
    r"^(?:\d+[.)]\s*)?(?:disassembly\s*\(bytes\)|byte dump|bytes):\s*", re.I
)


def byte_column(text: str) -> bytes:
    # A double space/tab separates the bytes from xxd ASCII or assembly text.
    # Within the byte column accept byte pairs and xxd/objdump packed groups.
    column = re.split(r"\t| {2,}", text.lstrip(), maxsplit=1)[0]
    tokens = []
    for token in column.split():
        if not HEX_TOKEN_RE.fullmatch(token):
            break
        tokens.append(token)
    return bytes.fromhex("".join(tokens))


def dump_candidates(text: str) -> list[bytes]:
    """Keep independent dumps separate and refuse broken addressed sequences.

    Supported: xxd rows, addressed objdump rows, byte-leading instruction
    listings, plain hex rows and an explicit inline 'Disassembly (bytes):'.
    Prose hashes are not dumps. No longest-fragment rescue across bad rows.
    """
    runs: list[bytes] = []
    current = bytearray()
    mode = None
    next_address = None

    def flush():
        if len(current) >= 6:
            runs.append(bytes(current))
        current.clear()

    for line in text.splitlines():
        match = ADDRESS_LINE_RE.match(line)
        if match:
            address = int(next(part for part in match.groups()[:3] if part is not None), 16)
            chunk = byte_column(match[4])
            if not chunk:
                flush(); mode = None; next_address = None
                continue
            if mode == "addressed" and address != next_address:
                raise ValueError(f"addressed dump gap/overlap: 0x{address:x}, expected 0x{next_address:x}")
            if mode != "addressed":
                flush()
            mode = "addressed"
            next_address = address + len(chunk)
        else:
            chunk = byte_column(INLINE_BYTES_RE.sub("", line.strip()))
            if not chunk:
                flush(); mode = None; next_address = None
                continue
            if mode != "plain":
                flush()
            mode = "plain"
            next_address = None
        current.extend(chunk)
    flush()
    return runs


def claimed_bytes(text: str) -> bytes | None:
    """Compatibility helper; main checks EVERY candidate before choosing a size."""
    return max(dump_candidates(text), key=len, default=None)


def declared_file_offset(text: str) -> int | None:
    """Count all declarations, including legacy/malformed/competing ones."""
    plain = text.replace("*", "").replace("`", "")
    declarations = re.findall(r"\bFILE\s+OFFSET\b", plain, re.I)
    headers = re.findall(
        r"^[ \t]*(?:1[.)][ \t]*)?FILE OFFSET:[ \t]*([0-9]+)[ \t]+"
        r"\((0x[0-9a-fA-F]+)\)[ \t]*$", plain, re.M | re.I,
    )
    if len(declarations) != 1 or len(headers) != 1:
        return None
    decimal, hexadecimal = headers[0]
    value = int(decimal, 10)
    return value if value == int(hexadecimal, 16) else None


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
    data = ovr.read_bytes()
    print(f"== {rep}")
    off = declared_file_offset(text)
    if off is None or (expect is not None and off != expect):
        print("   OFFSET UNRESOLVED: require exactly one FILE OFFSET declaration: "
              "FILE OFFSET: <decimal> (0x<hex>), with both values equal to the expected body offset.")
        return 1
    try:
        candidates = dump_candidates(text)
    except ValueError as exc:
        print(f"   BYTES DIFFER: {exc}; malformed addressed dump.")
        return 1
    if not candidates:
        print("   NO DUMP: the report printed no byte dump, so nothing is checkable.")
        return 2
    for cb in candidates:
        got = data[off:off + len(cb)]
        if got != cb:
            for i, (x, y) in enumerate(zip(got, cb)):
                if x != y:
                    print(f"   BYTES DIFFER: first difference at +{i} (offset {off + i}): "
                          f"file {x:02x}, claimed {y:02x}.")
                    print(f"      file   : {' '.join(f'{v:02x}' for v in got[:48])}")
                    print(f"      claimed: {' '.join(f'{v:02x}' for v in cb[:48])}")
                    return 1
            print(f"   BYTES DIFFER: dump extends outside the file ({len(got)} vs {len(cb)}).")
            return 1
    cb = max(candidates, key=len)
    if expect_len is not None and len(cb) < expect_len:
        print(f"   PREFIX ONLY: dump has {len(cb)} of the expected {expect_len} bytes "
              "(matching the file); not a decode.")
        return 1
    print(f"   BYTES MATCH: {len(cb)} bytes at {off} are byte-identical to {ovr.name}.")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))
