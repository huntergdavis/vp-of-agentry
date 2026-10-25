"""Permanent Python-versus-actual-C++ registry framing regression (t116)."""
from pathlib import Path
import unittest

from server.gameplay import GameError, GameSession
from support.cpp_format_probe import CppFormatProbe


IDENT = "RES_0709_01DF"
ROW = b"RES_0709_01DF\t01DF\t1\t00\tff\tunique"
EXPECTED = b"RES_0709_01DF\t01DF\t00\tFF"
PROBE = r'''
#include "poolrad_observer_loader.hpp"
int main(int argc, char **argv) {
    if (argc != 2) return 2;
    setenv("PR_HYBRID_REGISTRY", argv[1], 1);
    setenv("PR_HYBRID_LOG", "observer", 1);
    pr_obs::load();
    for (const auto &entry : pr_obs::entries) {
        printf("%s\t%04X\t", entry.id.c_str(), entry.ip);
        for (auto byte : entry.sig) printf("%02X", byte);
        printf("\t");
        for (auto byte : entry.mask) printf("%02X", byte);
        printf("\n");
    }
    return 0;
}
'''


class RegistryAgreementTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.probe = CppFormatProbe(PROBE, Path(__file__).parent / "support/fixtures")
        cls.addClassCleanup(cls.probe.close)

    def accepts(self, data):
        try:
            GameSession._validate_replacement_registry(data, [IDENT])
        except GameError:
            return False
        return True

    def test_generated_acceptance_implies_observer_loads_exact_row(self):
        cases = [
            ("LF", ROW + b"\n", True),
            ("EOF", ROW, True),
            ("header", b"# id\tmetadata !\n" + ROW + b"\n", True),
            ("symbol", ROW + b"\tpr_example,pr_other\n", True),
            ("symbol absent", ROW + b"\t-\n", True),
            ("bounded comment", b"#" + b"x" * 4093 + b"\n" + ROW, True),
            ("CRLF six columns", ROW + b"\r\n", False),
            ("CRLF seven columns", ROW + b"\tpr_example\r\n", False),
            ("trailing space", ROW + b" \n", False),
            ("trailing symbol space", ROW + b"\tpr_example \n", False),
            ("NUL suffix", ROW + b"\0\n", False),
            ("BOM", b"\xef\xbb\xbf" + ROW + b"\n", False),
            ("duplicate", ROW + b"\n" + ROW, False),
            ("duplicate malformed", ROW + b"\n" + IDENT.encode() + b"\tbad", False),
            ("malformed signature", ROW.replace(b"\t00\t", b"\tgg\t"), False),
            ("malformed length", ROW.replace(b"\t1\t", b"\t2\t"), False),
            ("zero mask", ROW.replace(b"\tff\t", b"\t00\t"), False),
            ("empty mask", ROW.replace(b"\tff\t", b"\t\t"), False),
            ("overlong comment hiding row", b"#" + b"x" * 4094 + ROW + b"\n", False),
            ("overlong metadata", ROW + b"\t" + b"x" * 4096, False),
        ]
        separators = [bytes([n]) for n in range(32) if n not in (9, 10)]
        separators += [b"\x7f", b"\x85", b"\xc2\x85", b"\xe2\x80\xa8", b"\xe2\x80\xa9"]
        for separator in separators:
            cases.append(("comment separator " + separator.hex(), b"# comment" + separator + ROW, False))
            cases.append(("data separator " + separator.hex(), ROW + separator + b"\n", False))
        for label, data, should_accept in cases:
            with self.subTest(label=label):
                accepted = self.accepts(data)
                self.assertEqual(accepted, should_accept)
                loaded = self.probe.run(data).split(b"\n")
                if accepted:
                    selected = [line for line in loaded if line.startswith(IDENT.encode() + b"\t")]
                    self.assertEqual(selected, [EXPECTED])

    def test_reviewer_counterexample_is_rejected_and_loads_no_row(self):
        for separator in (b"\x0b", b"\x0c", b"\xe2\x80\xa8"):
            with self.subTest(separator=separator.hex()):
                data = b"# comment" + separator + ROW
                self.assertFalse(self.accepts(data))
                self.assertEqual(self.probe.run(data), b"")

    def test_masked_signature_matches_native_loader(self):
        data = b"RES_0709_01DF\t01df\t2\t00ab\tFF00\tunique\tpr_example\n"
        self.assertTrue(self.accepts(data))
        self.assertEqual(self.probe.run(data), b"RES_0709_01DF\t01DF\t00AB\tFF00\n")


if __name__ == "__main__":
    unittest.main()
