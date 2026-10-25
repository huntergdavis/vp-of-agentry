"""Total input accounting and bounded, seeded corruption controls (no model calls)."""
from contextlib import redirect_stdout
from dataclasses import asdict, replace
import importlib.util
import io
from pathlib import Path
import random
import sys
import tempfile
import unittest

TOOLS = Path(__file__).resolve().parents[1] / "tools"
HEADER = "FILE OFFSET: 257 (0x101)\n"
BODY = bytes(range(1, 18))
VALID = "00000101: " + BODY.hex(" ") + "\n"
SEED = 0x2704


def load_parser():
    spec = importlib.util.spec_from_file_location("accounting_judge", TOOLS / "free_body_check.py")
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


def reviewer_v3_cases():
    """Exact retained controls from reviewer i24948 / review-vp27-v3/controls.py."""
    cases = {}
    for size in (3, 5):
        bad = "00000101: " + bytes([255, 238, 221, 204, 187][:size]).hex(" ") + "\n"
        for order in ("before", "after"):
            cases[f"conflict-{size}-{order}"] = HEADER + (bad + "\n" + VALID if order == "before" else VALID + "\n" + bad)
    cases.update({
        "invalid-address-token": HEADER + VALID + "\n0000010G: ff ee dd cc bb aa\n",
        "bad-first-byte-explicit-section": HEADER + VALID + "\nBYTE DUMP:\nGG 02 03 04 05 06 07 08\n",
        "bad-interior-byte-token": HEADER + VALID + "\nBYTE DUMP:\n01 02 03 04 05 06 GG 08\n",
        "duplicate-addressed-row": HEADER + VALID + VALID,
    })
    return cases


def corruption_corpus(seed=SEED):
    """72 malformed mutations and three valid controls; exact corpus is deterministic.

    Syntactically valid truncations are matching prefixes, not dropped syntax.
    All malformed mutations live inside declared dump content, with a correct
    complete dump also present to detect any silent-drop rescue.
    """
    rng = random.Random(seed)
    cases = []
    for trial in range(72):
        kind = trial % 6
        tokens = BODY.hex(" ").split()
        if kind == 0:
            index = rng.choice([0, len(tokens) // 2, len(tokens) - 1])
            token = list(tokens[index]); token[rng.randrange(2)] = rng.choice("GZ?!")
            tokens[index] = "".join(token)
            row = "00000101: " + " ".join(tokens)
            category = "bad-byte-first-middle-last"
        elif kind == 1:
            address = list("00000101")
            corruption = rng.choice("GZ?! ")
            index = rng.randrange(1, len(address) - 1) if corruption == " " else rng.randrange(len(address))
            address[index] = corruption
            row = "".join(address) + ": " + " ".join(tokens)
            category = "bad-address"
        elif kind == 2:
            row = "00000101:" if trial % 12 == 2 else "00000101: " + " ".join(tokens)[:-1]
            category = "truncated-column"
        elif kind == 3:
            tokens.insert(rng.randrange(len(tokens) + 1), rng.choice(["!", ";", ",", "("]))
            row = "00000101: " + " ".join(tokens)
            category = "stray-punctuation"
        elif kind == 4:
            tokens[0] = rng.choice(["GG", "?1", "Z", "!"])
            row = " ".join(tokens)
            category = "bad-first-unaddressed"
        else:
            row = rng.choice(["00000101; ", "row 00000?01: ", "0000010G  "]) + " ".join(tokens)
            category = "damaged-address-syntax"
        gap = "\n" if rng.randrange(2) else ""
        fenced = bool(rng.randrange(2))
        dump = ("\x60\x60\x60hex\n" if fenced else "") + gap + row + "\n" + ("\x60\x60\x60\n" if fenced else "")
        cases.append({"name": f"{trial:02d}-{category}", "text": HEADER + VALID + "\nBYTE DUMP:\n" + dump, "requires_drop": True})
    for name, row in [("clean", VALID), ("valid-prefix", "00000101: 01 02 03\n"),
                      ("row-marker", "row " + VALID)]:
        cases.append({"name": name, "text": HEADER + VALID + "\nBYTE DUMP:\n" + row, "requires_drop": False})
    return cases


def evaluate(parser, report, media, text):
    report.write_text(text)
    parsed = parser.parse_dump_report(text)
    output = io.StringIO()
    with redirect_stdout(output):
        code = parser.main(["judge", str(report), "--ovr", str(media), "--expect-offset", "257", "--expect-length", "17"])
    return {"exit": code, "output": output.getvalue(), "nonblank_lines": sum(bool(line.strip()) for line in text.splitlines()),
            "counts": parsed.line_counts, "dispositions": [asdict(line) for line in parsed.lines],
            "dropped": [asdict(item) for item in parsed.dropped]}


class AccountingInvariantTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.parser = load_parser()

    def setUp(self):
        directory = tempfile.TemporaryDirectory()
        self.addCleanup(directory.cleanup)
        self.tmp = Path(directory.name)
        self.media = self.tmp / "bytes.bin"
        self.media.write_bytes(bytes(range(256)) * 4)
        self.report = self.tmp / "report.md"

    def check(self, text):
        result = evaluate(self.parser, self.report, self.media, text)
        expected = [i for i, line in enumerate(text.splitlines(), 1) if line.strip()]
        self.assertEqual([line["line"] for line in result["dispositions"]], expected)
        self.assertEqual(sum(result["counts"].values()), result["nonblank_lines"])
        self.assertEqual(result["counts"]["dropped-in-dump-context"], len(result["dropped"]))
        if result["dropped"]:
            self.assertNotEqual(result["exit"], 0, result)
            self.assertNotIn("BYTES MATCH", result["output"])
        return result

    def test_bad_first_byte_in_explicit_section_cannot_be_rescued(self):
        result = self.check(reviewer_v3_cases()["bad-first-byte-explicit-section"])
        self.assertEqual(result["exit"], 1)
        self.assertEqual(len(result["dropped"]), 1)
        self.assertIn("report offset", result["output"])

    def test_bad_address_token_cannot_be_rescued(self):
        result = self.check(reviewer_v3_cases()["invalid-address-token"])
        self.assertEqual(result["exit"], 1)
        self.assertEqual(len(result["dropped"]), 1)
        self.assertIn("0000010G", result["output"])

    def test_numbered_offset_header_is_prose_metadata(self):
        for header in ("1. FILE OFFSET: 257 (0x101)", "1. **FILE OFFSET:** 257 (0x101)"):
            with self.subTest(header=header):
                result = self.check(header + "\n" + VALID)
                self.assertEqual(result["exit"], 0, result)
                self.assertEqual(result["dispositions"][0]["bucket"], "prose-outside-dump")
                self.assertFalse(result["dropped"])

    def test_all_eight_retained_v3_reviewer_controls(self):
        for name, text in reviewer_v3_cases().items():
            with self.subTest(name=name):
                result = self.check(text)
                self.assertEqual(result["exit"], 1)
                self.assertIn("BYTES DIFFER", result["output"])
                self.assertEqual(len(result["dropped"]), 0 if name.startswith("conflict-") else 1)

    def test_seeded_corruption_accounting_invariant(self):
        for case in corruption_corpus():
            with self.subTest(name=case["name"], seed=SEED):
                result = self.check(case["text"])
                if case["requires_drop"]:
                    self.assertGreater(len(result["dropped"]), 0, result)
                    self.assertEqual(result["exit"], 1, result)
                else:
                    self.assertEqual(len(result["dropped"]), 0, result)
                    self.assertEqual(result["exit"], 0, result)

    def test_exact_dispositions_cover_all_nonblank_lines(self):
        text = HEADER + "Outside explanation.\nbe careful here\n\nBYTE DUMP:\n\x60\x60\x60hex\n" + VALID + "\nGG 02\n\x60\x60\x60\nClosing explanation.\n"
        result = self.check(text)
        self.assertEqual(result["counts"], {"parsed-dump": 1, "dropped-in-dump-context": 1,
                                          "noise": 1, "prose-outside-dump": 6})

    def test_blank_lines_do_not_end_declared_dump_context(self):
        text = HEADER + VALID + "\nBYTE DUMP:\n\n\nGG 02 03\n"
        self.assertEqual(len(self.check(text)["dropped"]), 1)

    def test_unfenced_section_does_not_silently_end_on_prose(self):
        text = HEADER + "BYTE DUMP:\n" + VALID + "\ncannot confirm\nGG 02\n"
        self.assertEqual(len(self.check(text)["dropped"]), 2)

    def test_matching_fence_ends_section_before_prose(self):
        text = HEADER + "BYTE DUMP:\n\x60\x60\x60hex\n" + VALID + "\x60\x60\x60\nOrdinary explanation.\nSHA-256: " + BODY.hex() + "\n"
        result = self.check(text)
        self.assertEqual(result["exit"], 0, result)
        self.assertFalse(result["dropped"])

    def test_mismatched_fence_does_not_hide_bad_content(self):
        text = HEADER + "BYTE DUMP:\n\x60\x60\x60hex\n" + VALID + "\x60\x60\x60\x60\nGG 02\n"
        self.assertEqual(len(self.check(text)["dropped"]), 2)

    def test_bad_address_recognition_is_independent_of_valid_hex(self):
        for address in ("0000010G", "G0000101", "00000!01", "GGGGGGGG", "0000 101"):
            with self.subTest(address=address):
                text = HEADER + VALID + "\n" + address + ": ff ee dd\n"
                self.assertEqual(len(self.check(text)["dropped"]), 1)

    def test_opening_fence_preserves_an_active_implicit_dump(self):
        text = HEADER + VALID + "\x60\x60\x60\nGG 02\n\x60\x60\x60\n"
        result = self.check(text)
        self.assertEqual(len(result["dropped"]), 1)
        self.assertEqual(result["exit"], 1)

    def test_accounting_assertion_detects_missing_duplicate_and_unknown_buckets(self):
        for mutation in ("missing", "duplicate", "unknown"):
            with self.subTest(mutation=mutation):
                text = HEADER + VALID
                parsed = self.parser.parse_dump_report(text)
                if mutation == "missing":
                    parsed.lines.pop()
                elif mutation == "duplicate":
                    parsed.lines.append(parsed.lines[-1])
                else:
                    parsed.lines[-1] = replace(parsed.lines[-1], bucket="silent-skip")
                with self.assertRaises(AssertionError):
                    parsed.assert_accounted(text)

    def test_invalid_offset_still_accounts_for_malformed_content(self):
        result = self.check("FILE OFFSET: 257\nBYTE DUMP:\nGG 02\n")
        self.assertEqual(result["exit"], 1)
        self.assertIn("OFFSET UNRESOLVED", result["output"])
        self.assertEqual(len(result["dropped"]), 1)


if __name__ == "__main__":
    unittest.main()
