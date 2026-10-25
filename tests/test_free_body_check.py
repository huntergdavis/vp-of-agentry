"""The free-model judge must not be rescued by a wrong offset or a short dump, and the citation
gate must resolve paths against the SUBJECT repo, not the repo the tool lives in."""
import os
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

TOOLS = Path(__file__).resolve().parents[1] / "tools"
BODY = bytes(range(0x10, 0x10 + 64))  # 64 distinct bytes


def run(*args, env=None):
    e = dict(os.environ, **(env or {}))
    return subprocess.run([sys.executable, *map(str, args)], capture_output=True, text=True, env=e)


class JudgeTests(unittest.TestCase):
    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp())
        data = bytearray(4096)
        data[2048:2048 + 64] = BODY            # the real bytes live at 2048
        self.ovr = self.tmp / "GAME.OVR"
        self.ovr.write_bytes(bytes(data))

    def report(self, offset, nbytes=64):
        dump = " ".join(f"{b:02x}" for b in BODY[:nbytes])
        p = self.tmp / "r.md"
        p.write_text(f"1. FILE OFFSET: {offset} (0x{offset:x})\n2. BYTE DUMP:\n{dump}\n")
        return p

    def test_expected_offset_is_exclusive(self):
        # the model names offset 2048 (where those bytes really are) but the body implies 1024
        r = run(TOOLS / "free_body_check.py", self.report(2048), "--ovr", self.ovr, "--expect-offset", 1024)
        self.assertEqual(r.returncode, 1, r.stdout)
        self.assertNotIn("BYTES MATCH", r.stdout)

    def test_expected_offset_still_matches_when_right(self):
        r = run(TOOLS / "free_body_check.py", self.report(2048), "--ovr", self.ovr, "--expect-offset", 2048)
        self.assertEqual(r.returncode, 0, r.stdout)
        self.assertIn("BYTES MATCH", r.stdout)

    def test_short_dump_is_a_prefix_not_a_decode(self):
        r = run(TOOLS / "free_body_check.py", self.report(2048, nbytes=6), "--ovr", self.ovr,
                "--expect-offset", 2048, "--expect-length", 64)
        self.assertEqual(r.returncode, 1, r.stdout)
        self.assertIn("PREFIX ONLY", r.stdout)
        self.assertNotIn("BYTES MATCH", r.stdout)

    def test_full_length_dump_passes_the_length_gate(self):
        r = run(TOOLS / "free_body_check.py", self.report(2048), "--ovr", self.ovr,
                "--expect-offset", 2048, "--expect-length", 64)
        self.assertEqual(r.returncode, 0, r.stdout)


class CitationRepoTests(unittest.TestCase):
    def test_paths_resolve_against_poolrad_repo_not_the_tool_repo(self):
        repo = Path(tempfile.mkdtemp())
        (repo / "docs").mkdir()
        (repo / "docs" / "ONLY_IN_SUBJECT_REPO.md").write_text("x")
        rep = repo / "r.md"
        rep.write_text("Evidence: I opened docs/ONLY_IN_SUBJECT_REPO.md which describes 0x0400.\n")
        with_env = run(TOOLS / "free_verify_citations.py", "OVL_0025_0400", rep, env={"POOLRAD_REPO": str(repo)})
        self.assertEqual(with_env.returncode, 0, with_env.stdout)
        self.assertIn("citations resolve", with_env.stdout)
        without = run(TOOLS / "free_verify_citations.py", "OVL_0025_0400", rep, env={"POOLRAD_REPO": ""})
        self.assertEqual(without.returncode, 1, without.stdout)  # resolves against the tool repo: missing
        self.assertIn("FABRICATED", without.stdout)


def reviewer_cases():
    """PR27 reviewer cases, preserving their exact synthetic bytes and headers."""
    body = bytes(range(80, 96))
    plain = body.hex(" ")
    header = "FILE OFFSET: 80 (0x50)\n"
    return {
        "correct-addressed": header + "BYTE DUMP:\n00000050: " + body[:8].hex(" ") +
                             "\n00000058: " + body[8:].hex(" ") + "\n",
        "wrong-claimed-offset": "FILE OFFSET: 96 (0x60)\n" + plain + "\n",
        "correct-plain": header + plain + "\n",
        "old-arithmetic-only": "FILE OFFSET: base 64 + 16 = 80\n" + plain + "\n",
        "old-wrong-plus-strict-correct": "FILE OFFSET: 96\n" + header + plain + "\n",
        "strict-correct-plus-old-wrong": header + "FILE OFFSET: 96\n" + plain + "\n",
        "two-strict-correct": header + header + plain + "\n",
        "strict-correct-plus-old-wrong-separated": header + "FILE OFFSET: 96\nBYTE DUMP:\n" + plain + "\n",
    }


class StrictHeaderAndDumpTests(unittest.TestCase):
    """Original eight controls plus competing declarations and addressed dumps."""
    def setUp(self):
        directory = tempfile.TemporaryDirectory()
        self.addCleanup(directory.cleanup)
        self.tmp = Path(directory.name)
        self.body = bytes(range(0x10, 0x20))
        data = bytearray(range(256))
        data[80:96] = self.body
        self.ovr = self.tmp / "GAME.OVR"
        self.ovr.write_bytes(data)
        self.dump = self.body.hex(" ")

    def judge(self, header="FILE OFFSET: 80 (0x50)", dump=None, length=16, pin=True):
        report = self.tmp / "report.md"
        report.write_text(header + "\n\nBYTE DUMP:\n" + (self.dump if dump is None else dump) + "\n")
        args = [TOOLS / "free_body_check.py", report, "--ovr", self.ovr,
                "--expect-length", length]
        if pin:
            args += ["--expect-offset", 80]
        return run(*args)

    def assert_verdict(self, result, code, verdict):
        self.assertEqual(result.returncode, code, result.stdout + result.stderr)
        self.assertIn(verdict, result.stdout)
        if code:
            self.assertNotIn("BYTES MATCH", result.stdout)

    def test_positive_strict_header(self):
        self.assert_verdict(self.judge(), 0, "BYTES MATCH: 16 bytes")

    def test_wrong_offset(self):
        self.assert_verdict(self.judge("FILE OFFSET: 96 (0x60)"), 1, "OFFSET UNRESOLVED")

    def test_contradictory_decimal_and_hex(self):
        self.assert_verdict(self.judge("FILE OFFSET: 80 (0x60)"), 1, "OFFSET UNRESOLVED")

    def test_duplicate_strict_headers(self):
        for second in ("FILE OFFSET: 80 (0x50)", "FILE OFFSET: 96 (0x60)"):
            with self.subTest(second=second):
                self.assert_verdict(self.judge("FILE OFFSET: 80 (0x50)\n" + second),
                                    1, "OFFSET UNRESOLVED")

    def test_legacy_and_arithmetic_only_declarations_are_rejections(self):
        for header in ("FILE OFFSET: 80", "FILE OFFSET: 0x50", "FILE OFFSET: base 64 + 16 = 80"):
            with self.subTest(header=header):
                self.assert_verdict(self.judge(header), 1, "OFFSET UNRESOLVED")

    def test_short_matching_dump(self):
        self.assert_verdict(self.judge(dump=self.body[:8].hex(" ")), 1, "PREFIX ONLY")

    def test_wrong_bytes(self):
        self.assert_verdict(self.judge(dump=(bytes([0xff]) + self.body[1:]).hex(" ")),
                            1, "BYTES DIFFER")

    def test_no_dump(self):
        self.assert_verdict(self.judge(dump="cannot confirm"), 2, "NO DUMP")

    def test_competing_legacy_declaration_never_rescued_in_either_order(self):
        strict = "FILE OFFSET: 80 (0x50)"
        competitors = ("FILE OFFSET: 96", "FILE OFFSET: 80", "FILE OFFSET: 0x60",
                       "**FILE OFFSET:** 96", "file offset = 96", "FILE OFFSET: malformed")
        for competitor in competitors:
            for separator in ("\n", "\n\nArithmetic explanation.\n\n"):
                for lines in ((competitor, strict), (strict, competitor)):
                    with self.subTest(lines=lines, separator=separator):
                        self.assert_verdict(self.judge(separator.join(lines)), 1, "OFFSET UNRESOLVED")

    def test_competing_declaration_below_dump_is_not_ignored(self):
        self.assert_verdict(self.judge(dump=self.dump + "\nFILE OFFSET: 96"), 1, "OFFSET UNRESOLVED")

    def test_competing_declarations_fail_without_expected_offset_too(self):
        self.assert_verdict(self.judge("FILE OFFSET: 96\nFILE OFFSET: 80 (0x50)", pin=False),
                            1, "OFFSET UNRESOLVED")

    def test_complete_addressed_dump_with_and_without_colons(self):
        for colon in (":", ""):
            dump = f"00000050{colon}  {self.body[:8].hex(' ')}\n00000058{colon}  {self.body[8:].hex(' ')}"
            with self.subTest(colon=colon):
                self.assert_verdict(self.judge(dump=dump), 0, "BYTES MATCH: 16 bytes")

    def test_xxd_packed_groups_with_ascii(self):
        def packed(data):
            return " ".join(data[i:i + 2].hex() for i in range(0, len(data), 2))
        dump = f"00000050: {packed(self.body[:8])}  face\n00000058: {packed(self.body[8:])}  dead"
        self.assert_verdict(self.judge(dump=dump), 0, "BYTES MATCH: 16 bytes")

    def test_addressed_objdump_and_byte_leading_listings(self):
        for prefix in (True, False):
            dump = "\n".join((f"{80+i:04x}: " if prefix else "") +
                             f"{value:02x}  synthetic-op" for i, value in enumerate(self.body))
            with self.subTest(addressed=prefix):
                self.assert_verdict(self.judge(dump=dump), 0, "BYTES MATCH: 16 bytes")

    def test_gap_overlap_or_duplicate_address_is_refused(self):
        for address in (0x59, 0x57, 0x50):
            dump = f"00000050: {self.body[:8].hex(' ')}\n{address:08x}: {self.body[8:].hex(' ')}"
            with self.subTest(address=address):
                self.assert_verdict(self.judge(dump=dump), 1, "gap/overlap")

    def test_one_correct_dump_cannot_rescue_conflicting_dump(self):
        bad = (bytes([0x99]) + self.body[1:]).hex(" ")
        for first, second in ((self.dump, bad), (bad, self.dump)):
            with self.subTest(first=first):
                self.assert_verdict(self.judge(dump=first + "\n\nSecond dump:\n" + second),
                                    1, "BYTES DIFFER")

    def test_full_inline_dump_can_accompany_matching_addressed_prefix(self):
        dump = f"00000050: {self.body[:8].hex(' ')}\n\nDisassembly (bytes): {self.dump}"
        self.assert_verdict(self.judge(dump=dump), 0, "BYTES MATCH: 16 bytes")

    def test_sha_prose_is_not_a_byte_dump(self):
        self.assert_verdict(self.judge(dump="SHA-256: " + self.body.hex()), 2, "NO DUMP")

    def test_original_author_eight_controls(self):
        self.ovr.write_bytes(bytes(range(256)))
        cases = [('correct', 'FILE OFFSET: 16 (0x10)\n10 11 12 13 14 15 16 17\n', 0, 'BYTES MATCH'),
 ('wrong-offset', 'FILE OFFSET: 32 (0x20)\n10 11 12 13 14 15 16 17\n', 1, 'OFFSET UNRESOLVED'),
 ('contradiction',
  'FILE OFFSET: 16 (0x20)\n10 11 12 13 14 15 16 17\n',
  1,
  'OFFSET UNRESOLVED'),
 ('ambiguous',
  'FILE OFFSET: 16 (0x10)\nFILE OFFSET: 32 (0x20)\n10 11 12 13 14 15 16 17\n',
  1,
  'OFFSET UNRESOLVED'),
 ('arithmetic',
  'FILE OFFSET: base 8 + 8 = 16\n10 11 12 13 14 15 16 17\n',
  1,
  'OFFSET UNRESOLVED'),
 ('short', 'FILE OFFSET: 16 (0x10)\n10 11 12 13 14 15\n', 1, 'PREFIX ONLY'),
 ('wrong-bytes', 'FILE OFFSET: 16 (0x10)\n99 11 12 13 14 15 16 17\n', 1, 'BYTES DIFFER'),
 ('no-dump', 'FILE OFFSET: 16 (0x10)\nNo dump.\n', 2, 'NO DUMP')]
        for name, text, code, verdict in cases:
            with self.subTest(name=name):
                report = self.tmp / "original-author.md"
                report.write_text(text)
                self.assert_verdict(run(TOOLS / "free_body_check.py", report, "--ovr", self.ovr,
                                        "--expect-offset", 16, "--expect-length", 8), code, verdict)

    def test_reviewers_exact_seven_judge_cases(self):
        self.ovr.write_bytes(bytes(range(256)))
        for name, text in reviewer_cases().items():
            if name == "strict-correct-plus-old-wrong-separated":
                continue  # this additional fixture belongs to the five runner cases
            with self.subTest(name=name):
                report = self.tmp / "reviewer.md"
                report.write_text(text)
                code = 0 if name in ("correct-addressed", "correct-plain") else 1
                self.assert_verdict(run(TOOLS / "free_body_check.py", report, "--ovr", self.ovr,
                                        "--expect-offset", 80, "--expect-length", 16),
                                    code, "BYTES MATCH" if code == 0 else "OFFSET UNRESOLVED")


def reviewer_v2_cases():
    """Exact six cases from codex-review-d i24878/new_controls.py."""
    body = (bytes(range(256)) * 4)[257:274]
    header = "FILE OFFSET: 257 (0x101)\n"
    plain = body.hex(" ") + "\n"
    return {
        "A-tabbed-competing-declaration": (header + "FILE\tOFFSET: 258\nBYTE DUMP:\n" + plain, "OFFSET UNRESOLVED"),
        "A-markdown-competing-declaration": ("**FILE OFFSET:** 258\n" + header + plain, "OFFSET UNRESOLVED"),
        "B-strict-positive-fixture-tail-mutation": (header + body[:-1].hex(" ") + " ff\n", "BYTES DIFFER"),
        "B-strict-short-fixture-wrong-prefix": (header + "ff " + body[1:6].hex(" ") + "\n", "BYTES DIFFER"),
        "C-conflicting-addressed-three-byte-fragment": (header + "00000101: " + body.hex(" ") + "\n\n00000101: ff ee dd\n", "BYTES DIFFER"),
        "C-conflicting-addressed-five-byte-fragment-first": (header + "00000101: ff ee dd cc bb\n\n00000101: " + body.hex(" ") + "\n", "BYTES DIFFER"),
    }


class DumpAccountingTests(unittest.TestCase):
    def setUp(self):
        directory = tempfile.TemporaryDirectory()
        self.addCleanup(directory.cleanup)
        self.tmp = Path(directory.name)
        self.ovr = self.tmp / "GAME.OVR"
        self.ovr.write_bytes(bytes(range(256)) * 4)
        self.body = self.ovr.read_bytes()[257:274]
        self.full = "00000101: " + self.body.hex(" ")

    def judge(self, dump, header="FILE OFFSET: 257 (0x101)", length=17):
        report = self.tmp / "report.md"
        report.write_text(header + "\n" + dump + "\n")
        return run(TOOLS / "free_body_check.py", report, "--ovr", self.ovr,
                   "--expect-offset", 257, "--expect-length", length)

    def assert_verdict(self, result, code, verdict, dropped=0, noise=0):
        self.assertEqual(result.returncode, code, result.stdout + result.stderr)
        lines = [line for line in result.stdout.splitlines() if verdict in line]
        self.assertEqual(len(lines), 1, result.stdout)
        self.assertIn(f"dropped: {dropped}", lines[0])
        self.assertIn(f"noise: {noise}", lines[0])
        if code:
            self.assertNotIn("BYTES MATCH", result.stdout)

    def test_exact_six_v2_reviewer_cases(self):
        for name, (text, verdict) in reviewer_v2_cases().items():
            with self.subTest(name=name):
                header, dump = text.split("\n", 1)
                self.assert_verdict(self.judge(dump, header=header), 1, verdict)

    def test_short_conflicting_candidates_never_rescued_in_either_order(self):
        for size in range(1, 6):
            for prefix in ("00000101: ", "row 00000101: ", "Bytes: ", ""):
                bad = prefix + bytes([255] * size).hex(" ")
                for first, second in ((self.full, bad), (bad, self.full)):
                    with self.subTest(size=size, prefix=prefix, first=first):
                        self.assert_verdict(self.judge(first + "\n\n" + second), 1, "BYTES DIFFER")

    def test_short_matching_candidates_are_retained(self):
        for size in range(1, 6):
            for prefix in ("00000101: ", "Bytes: ", ""):
                short = prefix + self.body[:size].hex(" ")
                with self.subTest(size=size, prefix=prefix):
                    self.assert_verdict(self.judge(short), 1, "PREFIX ONLY")
                    self.assert_verdict(self.judge(short + "\n\n" + self.full), 0, "BYTES MATCH")

    def test_one_byte_body_is_checkable(self):
        self.assert_verdict(self.judge("00000101: 01", length=1), 0, "BYTES MATCH")

    def test_explicit_inline_labels_start_independent_candidates(self):
        full = "Bytes: " + self.body.hex(" ")
        self.assert_verdict(self.judge(full + "\nBytes: 01 02 03"), 0, "BYTES MATCH")
        self.assert_verdict(self.judge(full + "\nBytes: ff ee dd"), 1, "BYTES DIFFER")

    def test_malformed_explicit_rows_are_counted_errors_in_both_orders(self):
        for bad in ("00000101:", "00000101: zz", "00000101: 01 02 zz", "row 00000101: zz"):
            for dump in (self.full + "\n\n" + bad, bad + "\n\n" + self.full):
                with self.subTest(dump=dump):
                    result = self.judge(dump)
                    self.assert_verdict(result, 1, "BYTES DIFFER", dropped=1)
                    self.assertIn("address 0x101", result.stdout)
                    self.assertIn("report offset", result.stdout)
                    self.assertIn("line ", result.stdout)

    def test_multiple_dropped_rows_name_every_offset(self):
        result = self.judge(self.full + "\n\n00000101: zz\n00000200:")
        self.assert_verdict(result, 1, "BYTES DIFFER", dropped=2)
        self.assertIn("address 0x101", result.stdout)
        self.assertIn("address 0x200", result.stdout)

    def test_gap_and_overlap_have_counts_and_offsets(self):
        for address in (0x101, 0x109, 0x111):
            dump = "00000101: " + self.body[:8].hex(" ") + f"\n{address:08x}: " + self.body[8:].hex(" ")
            if address == 0x109:  # positive continuity control
                self.assert_verdict(self.judge(dump), 0, "BYTES MATCH")
            else:
                result = self.judge(dump)
                self.assert_verdict(result, 1, "BYTES DIFFER", dropped=1)
                self.assertIn("gap/overlap", result.stdout)
                self.assertIn(f"address 0x{address:x}", result.stdout)

    def test_malformed_dump_shaped_and_labelled_runs_are_errors(self):
        for bad in ("Bytes: zz", "Bytes: 01 02 zz", "BYTE DUMP:\n01 02 zz",
                    "01 02 03 04 05 06 zz"):
            with self.subTest(bad=bad):
                result = self.judge(self.full + "\n\n" + bad)
                self.assert_verdict(result, 1, "BYTES DIFFER", dropped=1)
                self.assertIn("report offset", result.stdout)

    def test_ambiguous_prose_noise_is_counted_warning(self):
        result = self.judge("be careful here\nad hoc explanation\n\n" + self.full)
        self.assert_verdict(result, 0, "BYTES MATCH", noise=2)
        self.assertIn("WARNING: ignored ambiguous-prose noise runs: 2", result.stdout)

    def test_noise_alone_cannot_supply_dump_evidence(self):
        self.assert_verdict(self.judge("be careful here"), 2, "NO DUMP", noise=1)

    def test_unresolved_offset_still_reports_discarded_content(self):
        result = self.judge("00000101: zz", header="FILE OFFSET: 257")
        self.assert_verdict(result, 1, "OFFSET UNRESOLVED", dropped=1)
        self.assertIn("address 0x101", result.stdout)

    def test_every_verdict_has_discard_count(self):
        cases = [(self.full, "FILE OFFSET: 257 (0x101)", 0, "BYTES MATCH"),
                 ("00000101: ff", "FILE OFFSET: 257 (0x101)", 1, "BYTES DIFFER"),
                 ("00000101: 01", "FILE OFFSET: 257 (0x101)", 1, "PREFIX ONLY"),
                 ("cannot confirm", "FILE OFFSET: 257 (0x101)", 2, "NO DUMP"),
                 (self.full, "FILE OFFSET: 257", 1, "OFFSET UNRESOLVED")]
        for dump, header, code, verdict in cases:
            with self.subTest(verdict=verdict):
                self.assert_verdict(self.judge(dump, header=header), code, verdict)
        missing = run(TOOLS / "free_body_check.py", self.tmp / "missing.md", "--ovr", self.ovr)
        self.assertEqual(missing.returncode, 2)
        self.assertIn("REFUSED", missing.stderr)
        self.assertIn("dropped: 0", missing.stderr)


if __name__ == "__main__":
    unittest.main()
