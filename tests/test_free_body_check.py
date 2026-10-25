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
        p.write_text(f"1. FILE OFFSET: {offset}\n2. BYTE DUMP:\n{dump}\n")
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


if __name__ == "__main__":
    unittest.main()
