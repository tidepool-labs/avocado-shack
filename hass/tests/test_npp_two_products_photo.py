"""Offline tests for scripts/hass/npp_two_products_photo.py.

Contract protected: item_add.several_products keeps asking (True) when two
products are on one photo and Mike has not named one, and keeps its pinned
answers. Each test fails if the script stops calling the repo function or the
repo answer drifts (for example _bare_list or _STATES changes).
"""

import contextlib
import importlib.util
import io
import os
from pathlib import Path
import re
import subprocess
import sys
import unittest
from unittest import mock

ROOT = Path(__file__).resolve().parents[2]
SCRIPT = ROOT / "scripts/hass/npp_two_products_photo.py"
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from hass.skills import item_add  # noqa: E402

_SPEC = importlib.util.spec_from_file_location("npp_two_products_photo_under_test", SCRIPT)
tool = importlib.util.module_from_spec(_SPEC)
_SPEC.loader.exec_module(tool)

LIVE = [
    "case 0 several=no",
    "case 1 several=yes",
    "case 2 several=no",
    "case 3 several=no",
    "case 4 several=yes",
    "case 5 several=yes",
    "case 6 several=no",
    "case 7 several=yes",
    "case 8 several=yes",
    "case 9 several=no",
    "case 10 several=yes",
]
TRAILER_FAIL = "FAIL npp_two_products_photo"
TRAILER_PASS = "PASS npp_two_products_photo"
LINE_FORMS = re.compile(
    r"case \d+ several=(?:yes|no)"
    r"|FAIL (?:two-products-one-listing \d+|several-changed \d+|check-error)"
    r"|PASS npp_two_products_photo|FAIL npp_two_products_photo"
)


def run_main():
    out = io.StringIO()
    with contextlib.redirect_stdout(out):
        code = tool.main([])
    return code, out.getvalue().splitlines()


def findings(lines):
    return [line for line in lines if line.startswith("FAIL ") and line != TRAILER_FAIL]


def snapshot(*names):
    result = {}
    for name in names:
        for dirpath, dirnames, filenames in os.walk(ROOT / name):
            for entry in dirnames + filenames:
                path = Path(dirpath) / entry
                info = path.lstat()
                result[str(path)] = (info.st_size, info.st_mtime_ns)
    return result


class NppTwoProductsPhotoTests(unittest.TestCase):
    def run_script(self, *args):
        return subprocess.run([sys.executable, "-B", str(SCRIPT), *args],
                              cwd=ROOT, capture_output=True, text=True, timeout=60)

    def test_c1_full_pass(self):
        # A dead tool or a changed trailer would fail the exit code or last line.
        result = self.run_script()
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(result.stdout.splitlines()[-1], TRAILER_PASS)

    def test_c2_findings_trailer(self):
        # Findings must exit 1 and end on the FAIL trailer, not PASS.
        with mock.patch.object(item_add, "_bare_list", lambda name, turn: False):
            code, lines = run_main()
        self.assertEqual(code, 1)
        self.assertEqual(lines[-1], TRAILER_FAIL)
        self.assertNotIn(TRAILER_PASS, lines)

    def test_c2_1_two_products_one_listing(self):
        # If the list check stopped asking, one listing would be drafted for two.
        with mock.patch.object(item_add, "_bare_list", lambda name, turn: False):
            code, lines = run_main()
        self.assertEqual(code, 1)
        self.assertEqual(findings(lines), [
            "FAIL two-products-one-listing 1", "FAIL several-changed 1",
            "FAIL two-products-one-listing 4", "FAIL several-changed 4",
            "FAIL two-products-one-listing 5", "FAIL several-changed 5",
            "FAIL two-products-one-listing 10", "FAIL several-changed 10",
        ])
        # Each case's findings sit right after that case's own line.
        self.assertEqual(lines[lines.index("case 1 several=no") + 1],
                         "FAIL two-products-one-listing 1")
        self.assertEqual(lines[-1], TRAILER_FAIL)

    def test_c2_2_several_changed(self):
        # A moved pinned answer that is not a must-ask case is still reported.
        with mock.patch.object(item_add, "_STATES", frozenset()):
            code, lines = run_main()
        self.assertEqual(code, 1)
        self.assertEqual(findings(lines), ["FAIL several-changed 6"])
        self.assertEqual(lines[-1], TRAILER_FAIL)

    def test_c2_3_check_error(self):
        # A raising repo call is a named FAIL, once, with no later case checked.
        with mock.patch.object(item_add, "several_products",
                               side_effect=RuntimeError("secret detail")):
            code, lines = run_main()
        self.assertEqual(code, 1)
        self.assertEqual(lines, ["FAIL check-error", TRAILER_FAIL])

    def test_c3_usage_exit_2(self):
        for args in (("extra",), ("--bogus",)):
            with self.subTest(args=args):
                result = self.run_script(*args)
                self.assertEqual(result.returncode, 2)
                self.assertEqual(result.stdout, "")

    def test_c4_read_only(self):
        before = snapshot("hass", "storefront-mockup")
        self.assertTrue(before)
        result = self.run_script()
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(snapshot("hass", "storefront-mockup"), before)

    def test_c5_output_shape(self):
        result = self.run_script()
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(result.stderr, "")
        lines = result.stdout.splitlines()
        self.assertTrue(lines)
        for line in lines:
            self.assertIsNotNone(LINE_FORMS.fullmatch(line), line)
        self.assertEqual(lines[-1], TRAILER_PASS)

    def test_c6_fixture(self):
        # Without the state list "Juniper Ridge, Oregon" reads as two products.
        with mock.patch.object(item_add, "_STATES", frozenset()):
            code, lines = run_main()
        self.assertEqual(code, 1)
        self.assertEqual(findings(lines), ["FAIL several-changed 6"])
        self.assertIn("case 6 several=yes", lines)
        self.assertEqual(lines[-1], TRAILER_FAIL)

    def test_c7_live_pins(self):
        # Measured at c8cdcc95 and re-measured on this base; unchanged.
        code, lines = run_main()
        self.assertEqual(code, 0)
        self.assertEqual(lines, LIVE + [TRAILER_PASS])
        self.assertEqual(list(tool.EXPECTED), LIVE)
        self.assertEqual(tool.MUST_ASK, (1, 4, 5, 7, 8, 10))
        self.assertEqual(len(tool.CASES), 11)


if __name__ == "__main__":
    unittest.main()
