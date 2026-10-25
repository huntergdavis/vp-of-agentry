"""Bakeoff verdict/preflight regressions: stubbed worker, no models or network."""
import os
from pathlib import Path
import shlex
import shutil
import subprocess
import tempfile
import unittest

from test_free_body_check import reviewer_cases, reviewer_v2_cases
from test_free_body_accounting import reviewer_v3_cases

TOOLS = Path(__file__).resolve().parents[1] / "tools"
BODY = bytes(range(0x10, 0x20))


class BakeoffTests(unittest.TestCase):
    def setUp(self):
        directory = tempfile.TemporaryDirectory()
        self.addCleanup(directory.cleanup)
        self.root = Path(directory.name)
        self.tools = self.root / "tools"
        self.tools.mkdir()
        self.repo = self.root / "repo"
        media = self.repo / "resources/DOS/POOLRAD"
        media.mkdir(parents=True)
        data = bytearray(range(256))
        data[80:96] = BODY
        (media / "GAME.OVR").write_bytes(data)
        for name in ("free_bakeoff.sh", "free_body_check.py"):
            shutil.copyfile(TOOLS / name, self.tools / name)
        self.report = self.root / "fixture.md"
        self.called = self.root / "worker-called"
        stub = self.tools / "free_sandbox.sh"
        stub.write_text("#!/bin/sh\nset -e\ntouch " + shlex.quote(str(self.called)) +
                        "\ncat " + shlex.quote(str(self.report)) + "\n")
        stub.chmod(0o700)

    def invoke(self, dump=None, header="FILE OFFSET: 80 (0x50)", spec="OVL_0025_06AF:80:16", report_text=None):
        self.report.write_text(report_text if report_text is not None else
                               header + "\n\nBYTE DUMP:\n" +
                               (BODY.hex(" ") if dump is None else dump) + "\n")
        result = subprocess.run(
            ["bash", str(self.tools / "free_bakeoff.sh"), "synthetic-no-api-model", spec, "1"],
            env=dict(os.environ, POOLRAD_REPO=str(self.repo)), capture_output=True,
            text=True, timeout=20)
        tables = list((self.root / "data/bakeoff").glob("*/results.tsv"))
        self.table = tables[0].read_text() if tables else ""
        return result

    def assert_result(self, result, verdict):
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        self.assertTrue(self.called.exists())
        self.assertEqual(len(self.table.splitlines()), 1, self.table)
        self.assertTrue(self.table.split("\t")[2].startswith(verdict), self.table)

    def test_complete_report_verifies(self):
        self.assert_result(self.invoke(), "VERIFIED")

    def test_multiline_mismatch_diagnostic_is_differs_not_unchecked(self):
        self.assert_result(self.invoke(dump=(bytes([0x99]) + BODY[1:8]).hex(" "),
                                       header="FILE OFFSET: 16 (0x10)", spec="OVL_0025_06AF:16:8"), "DIFFERS")
        checks = list((self.root / "data/bakeoff").glob("*/*/*.check"))
        self.assertIn("BYTES DIFFER", checks[0].read_text())
        self.assertIn("claimed:", checks[0].read_text())

    def test_short_report_is_not_verified(self):
        self.assert_result(self.invoke(dump=BODY[:6].hex(" "), header="FILE OFFSET: 16 (0x10)",
                                       spec="OVL_0025_06AF:16:8"), "SHORT")

    def test_wrong_offset_is_not_verified(self):
        self.assert_result(self.invoke(header="FILE OFFSET: 96 (0x60)"), "WRONG OR UNRESOLVED OFFSET")

    def test_report_with_no_dump(self):
        self.assert_result(self.invoke(dump="cannot confirm"), "DIFFERS")

    def test_missing_length_is_refused_before_worker(self):
        result = self.invoke(spec="OVL_0025_06AF:16")
        self.assertEqual(result.returncode, 2, result.stdout + result.stderr)
        self.assertIn("expected BODY:", result.stderr)
        self.assertFalse(self.called.exists())

    def test_zero_length_is_refused_before_worker(self):
        result = self.invoke(spec="OVL_0025_06AF:80:0")
        self.assertEqual(result.returncode, 2, result.stdout + result.stderr)
        self.assertFalse(self.called.exists())

    def test_nonzero_judge_exit_cannot_verify_printed_match(self):
        (self.tools / "free_body_check.py").write_text(
            "print('   BYTES MATCH: synthetic false claim')\nraise SystemExit(1)\n")
        self.assert_result(self.invoke(), "UNCHECKED")

    def test_addressed_complete_report_verifies(self):
        dump = f"00000050  {BODY[:8].hex(' ')}\n00000058  {BODY[8:].hex(' ')}"
        self.assert_result(self.invoke(dump=dump), "VERIFIED")

    def reviewer_case(self, name, verdict):
        (self.repo / "resources/DOS/POOLRAD/GAME.OVR").write_bytes(bytes(range(256)))
        self.assert_result(self.invoke(report_text=reviewer_cases()[name]), verdict)

    def test_reviewer_correct_plain(self):
        self.reviewer_case("correct-plain", "VERIFIED")

    def test_reviewer_wrong_claimed_offset(self):
        self.reviewer_case("wrong-claimed-offset", "WRONG OR UNRESOLVED OFFSET")

    def test_reviewer_correct_addressed(self):
        self.reviewer_case("correct-addressed", "VERIFIED")

    def test_reviewer_old_wrong_plus_strict_correct(self):
        self.reviewer_case("old-wrong-plus-strict-correct", "WRONG OR UNRESOLVED OFFSET")

    def test_reviewer_strict_correct_plus_old_wrong_separated(self):
        self.reviewer_case("strict-correct-plus-old-wrong-separated", "WRONG OR UNRESOLVED OFFSET")


    def test_short_addressed_conflicts_never_verify_in_either_order(self):
        media = self.repo / "resources/DOS/POOLRAD/GAME.OVR"
        media.write_bytes(bytes(range(256)) * 4)
        body = media.read_bytes()[257:274]
        full = "00000101: " + body.hex(" ")
        for bad in ("00000101: ff ee dd", "00000101: ff ee dd cc bb",
                    "row 00000101: ff ee dd"):
            for first, second in ((full, bad), (bad, full)):
                with self.subTest(bad=bad, first=first):
                    shutil.rmtree(self.root / "data", ignore_errors=True)
                    report = "FILE OFFSET: 257 (0x101)\n" + first + "\n\n" + second + "\n"
                    self.assert_result(self.invoke(report_text=report, spec="OVL_0025_06AF:257:17"), "DIFFERS")
                    self.assertNotIn("VERIFIED", self.table)
                    checks = list((self.root / "data/bakeoff").glob("*/*/*.check"))
                    self.assertIn("dropped: 0", checks[0].read_text())

    def test_exact_v2_reviewer_short_conflict_never_verifies(self):
        (self.repo / "resources/DOS/POOLRAD/GAME.OVR").write_bytes(bytes(range(256)) * 4)
        for name, (text, verdict) in reviewer_v2_cases().items():
            if not name.startswith("C-"):
                continue
            with self.subTest(name=name):
                shutil.rmtree(self.root / "data", ignore_errors=True)
                self.assert_result(self.invoke(report_text=text, spec="OVL_0025_06AF:257:17"), "DIFFERS")

    def test_discarded_addressed_content_never_verifies(self):
        result = self.invoke(dump="00000050: " + BODY.hex(" ") + "\n\n00000050: zz")
        self.assert_result(result, "DIFFERS")
        checks = list((self.root / "data/bakeoff").glob("*/*/*.check"))
        self.assertIn("dropped: 1", checks[0].read_text())
        self.assertIn("address 0x50", checks[0].read_text())

    def test_noise_warning_preserves_valid_verdict_and_count(self):
        text = "FILE OFFSET: 80 (0x50)\nbe careful here\n\n" + BODY.hex(" ") + "\n"
        self.assert_result(self.invoke(report_text=text), "VERIFIED")
        checks = list((self.root / "data/bakeoff").glob("*/*/*.check"))
        self.assertIn("WARNING", checks[0].read_text())
        self.assertIn("dropped: 0; noise: 1", checks[0].read_text())


    def test_v3_silent_drop_shapes_never_verify(self):
        (self.repo / "resources/DOS/POOLRAD/GAME.OVR").write_bytes(bytes(range(256)) * 4)
        for name in ("invalid-address-token", "bad-first-byte-explicit-section"):
            with self.subTest(name=name):
                shutil.rmtree(self.root / "data", ignore_errors=True)
                self.assert_result(self.invoke(report_text=reviewer_v3_cases()[name], spec="OVL_0025_06AF:257:17"), "DIFFERS")
                checks = list((self.root / "data/bakeoff").glob("*/*/*.check"))
                receipt = checks[0].read_text()
                self.assertIn("dropped: 1", receipt)
                self.assertIn("accounted:", receipt)


if __name__ == "__main__":
    unittest.main()
