"""Offline tests for the label-claim sanitize drift guard (fixtures only).

Each test protects one CONTRACT item of scripts/hass/npp_label_claim_sanitize.py.
The believable bug for every item: a later change to product_claims.sanitize,
protected, food or label_text alters a pinned listing, or the script stops
calling the repo function (a constant would still print the pinned lines, so
the patched runs below must change the output).
"""

import collections
from contextlib import redirect_stderr, redirect_stdout
import importlib.util
import io
from pathlib import Path
import re
import subprocess
import sys
import unittest
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[2]
SCRIPT = ROOT / "scripts/hass/npp_label_claim_sanitize.py"
SPEC = importlib.util.spec_from_file_location("npp_label_claim_sanitize", SCRIPT)
assert SPEC is not None and SPEC.loader is not None
CHECK = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(CHECK)
product_claims = CHECK.product_claims

PASS = "PASS npp_label_claim_sanitize"
FAIL = "FAIL npp_label_claim_sanitize"
CASE_LINE = re.compile(r"case \d+ label=\[.*\] name=.* description=.* dropped=\[.*\]")
FINDING_LINE = re.compile(r"FAIL (claim-kept-public \d+|listing-changed \d+|check-error)")
EXPECTED_LINES = [
    "case 0 label=['Cedar Row Apiary'] name='Wildflower Honey' description='Wildflower honey from Label says: \\u201cCedar Row Apiary\\u201d.' dropped=[]",
    "case 1 label=['Cedar Row Apiary'] name='Wildflower Honey' description='Wildflower honey.' dropped=['It cures colds.']",
    "case 2 label=['Cedar Row Apiary'] name='New item' description='New item' dropped=['Organic Wildflower Honey', 'Organic honey.']",
    "case 3 label=['Cedar Row Apiary', 'Certified organic'] name='Wildflower Honey' description='Label says: \\u201cCertified organic\\u201d honey.' dropped=[]",
    "case 4 label=['Cedar Row Apiary'] name='Organic Honey' description='Organic Honey' dropped=['Organic honey from the farm.']",
    "case 5 label=['Cedar Row Apiary'] name='Claw Hammer' description='Claw Hammer' dropped=['A hammer that cures colds.']",
    "case 6 label=['Cedar Row Apiary'] name='Wildflower Honey' description='Wildflower Honey' dropped=['Call 000-555-0100 for honey.']",
    "case 7 label=['Cedar Row Apiary'] name='Wildflower Honey' description='Wildflower honey raw.' dropped=['gluten free']",
    "case 8 label=['Cedar Row Apiary'] name='Wildflower Honey' description='Wildflower Honey' dropped=['Award winning honey.']",
]


def snapshot():
    seen = {}
    for tree in ("hass", "storefront-mockup"):
        for path in sorted((ROOT / tree).rglob("*")):
            if "__pycache__" in path.parts:
                continue
            info = path.lstat()
            seen[str(path.relative_to(ROOT))] = (info.st_size, info.st_mtime_ns)
    return seen


def in_process():
    out, err = io.StringIO(), io.StringIO()
    with redirect_stdout(out), redirect_stderr(err):
        code = CHECK.main([])
    return code, out.getvalue().splitlines(), err.getvalue()


def findings(lines):
    return [line for line in lines if line.startswith("FAIL ") and line != FAIL]


class NppLabelClaimSanitizeTests(unittest.TestCase):
    def test_c1_full_pass(self):
        # A changed pinned answer or a crash would break exit 0 or the exact last line.
        result = subprocess.run([sys.executable, "-B", str(SCRIPT)], cwd=ROOT,
                                capture_output=True, text=True, timeout=30)
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(result.stdout.splitlines()[-1], PASS)
        self.assertEqual(findings(result.stdout.splitlines()), [])

    def test_c2_findings_trailer(self):
        # Findings must exit 1 and end with the exact FAIL trailer, after each case's own line.
        with patch.object(product_claims, "food", lambda product: False):
            code, lines, err = in_process()
        self.assertEqual(code, 1)
        self.assertEqual(lines[-1], FAIL)
        self.assertEqual(err, "")
        self.assertEqual(lines.index("FAIL listing-changed 0"), 1)

    def test_c2_1_claim_kept_public(self):
        # If protected stops cutting claims, the public text keeps them: caught by name, in order.
        noop = lambda text, product, names=(): (collections.Counter(), set())
        with patch.object(product_claims, "protected", noop):
            code, lines, _ = in_process()
        self.assertEqual(code, 1)
        self.assertEqual(lines[-1], FAIL)
        self.assertEqual(findings(lines), [
            "FAIL claim-kept-public 1", "FAIL listing-changed 1",
            "FAIL claim-kept-public 2", "FAIL listing-changed 2",
            "FAIL listing-changed 4",
            "FAIL claim-kept-public 5", "FAIL listing-changed 5",
            "FAIL claim-kept-public 6", "FAIL listing-changed 6",
            "FAIL claim-kept-public 7", "FAIL listing-changed 7",
            "FAIL claim-kept-public 8", "FAIL listing-changed 8",
        ])

    def test_c2_2_listing_changed(self):
        # The pinned EXPECTED lines must be compared against the repo's real output.
        with patch.object(product_claims, "food", lambda product: False):
            code, lines, _ = in_process()
        self.assertEqual(code, 1)
        self.assertEqual(lines[-1], FAIL)
        self.assertEqual(findings(lines), ["FAIL listing-changed 0", "FAIL listing-changed 3"])
        self.assertEqual(CHECK.EXPECTED, EXPECTED_LINES)

    def test_c2_3_check_error(self):
        # A raising repo call is a named finding once, never a traceback or a silent skip.
        def boom(*args, **kwargs):
            raise RuntimeError("secret-detail")
        with patch.object(product_claims, "sanitize", boom):
            code, lines, err = in_process()
        self.assertEqual(code, 1)
        self.assertEqual(lines, ["FAIL check-error", FAIL])
        self.assertEqual(err, "")

    def test_c3_usage_exit_2(self):
        # Extra arguments must stay argparse usage errors with nothing on stdout.
        for args in (["extra"], ["--bogus"]):
            with self.subTest(args=args):
                result = subprocess.run([sys.executable, "-B", str(SCRIPT), *args], cwd=ROOT,
                                        capture_output=True, text=True, timeout=30)
                self.assertEqual(result.returncode, 2)
                self.assertEqual(result.stdout, "")

    def test_c4_read_only(self):
        # The run must not create or touch files under hass/ or storefront-mockup/.
        before = snapshot()
        result = subprocess.run([sys.executable, "-B", str(SCRIPT)], cwd=ROOT,
                                capture_output=True, text=True, timeout=30)
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(result.stdout.splitlines()[-1], PASS)
        self.assertEqual(snapshot(), before)

    def test_c5_output_shape(self):
        # Only the named line forms may appear, on stdout, and nothing on stderr.
        result = subprocess.run([sys.executable, "-B", str(SCRIPT)], cwd=ROOT,
                                capture_output=True, text=True, timeout=30)
        self.assertEqual(result.stderr, "")
        self.assertEqual(result.returncode, 0)
        lines = result.stdout.splitlines()
        self.assertEqual(len(lines), 10)
        for line in lines[:-1]:
            self.assertRegex(line, CASE_LINE)
        self.assertEqual(lines[-1], PASS)
        with patch.object(product_claims, "food", lambda product: False):
            code, lines, err = in_process()
        self.assertEqual(err, "")
        for line in lines:
            self.assertTrue(CASE_LINE.fullmatch(line) or FINDING_LINE.fullmatch(line)
                            or line == FAIL, line)

    def test_c6_fixture(self):
        # Without food attribution, only the two cases that carry label words change.
        with patch.object(product_claims, "food", lambda product: False):
            code, lines, _ = in_process()
        self.assertEqual(code, 1)
        self.assertEqual(findings(lines), ["FAIL listing-changed 0", "FAIL listing-changed 3"])
        self.assertEqual(lines[-1], FAIL)

    def test_c7_live_pins(self):
        # Pins the measured sanitize output, including the wrapped brand and kept 'raw'.
        code, lines, err = in_process()
        self.assertEqual(code, 0)
        self.assertEqual(err, "")
        self.assertEqual(lines[:-1], EXPECTED_LINES)
        self.assertEqual(lines[-1], PASS)


if __name__ == "__main__":
    unittest.main()
