"""Drift guard for the house shape check of a new product record (scripts/hass/npp_product_record_shape.py).

Offline: every fixture is built in-process; patches use unittest.mock and are undone with the test.
"""

import contextlib
import importlib.util
import io
from pathlib import Path
import re
import subprocess
import sys
import unittest
from unittest import mock

from hass import house_style

ROOT = Path(__file__).resolve().parents[2]
SCRIPT = ROOT / "scripts/hass/npp_product_record_shape.py"
TRAILER_PASS = "PASS npp_product_record_shape"
TRAILER_FAIL = "FAIL npp_product_record_shape"
# Written out here on purpose: the test pins the answers independently of the script's own EXPECTED.
LIVE = [
    "case 0 pass=yes score=100 hard=[]",
    "case 1 pass=no score=88 hard=['picture path']",
    "case 2 pass=no score=81 hard=['shelf is one of the nine']",
    "case 3 pass=no score=81 hard=['maker link']",
    "case 4 pass=yes score=88 hard=[]",
    "case 5 pass=yes score=100 hard=[]",
    "case 6 pass=yes score=94 hard=[]",
    "case 7 pass=yes score=94 hard=[]",
    "case 8 pass=no score=81 hard=['fields']",
    "case 9 pass=no score=81 hard=['fields']",
    "case 10 pass=no score=94 hard=['name and brand text']",
    "case 11 pass=yes score=100 hard=[]",
    "case 12 pass=no score=81 hard=['maker link']",
]
LINE_SHAPES = (
    re.compile(r"case \d+ pass=(yes|no) score=\d+ hard=\[.*\]"),
    re.compile(r"FAIL (bad-record-passed|record-changed) \d+"),
    re.compile(r"FAIL check-error"),
    re.compile(r"(PASS|FAIL) npp_product_record_shape"),
)


def load_script():
    spec = importlib.util.spec_from_file_location("npp_product_record_shape", SCRIPT)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


tool = load_script()


def run_inprocess():
    out = io.StringIO()
    with contextlib.redirect_stdout(out):
        code = tool.main([])
    return code, out.getvalue().splitlines()


def run_subprocess(*args):
    return subprocess.run([sys.executable, "-B", str(SCRIPT), *args], cwd=ROOT,
                          capture_output=True, text=True, timeout=60)


def snapshot(*names):
    seen = {}
    for name in names:
        for path in sorted((ROOT / name).rglob("*")):
            info = path.stat()
            seen[str(path.relative_to(ROOT))] = (info.st_size, info.st_mtime_ns)
    return seen


class NppProductRecordShapeTests(unittest.TestCase):
    def test_c1_full_pass(self):
        # Contract: the unpatched repo passes with exit 0 and the PASS trailer last.
        # Bug caught: a clean run that exits non-zero or ends on another line.
        result = run_subprocess()
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        self.assertEqual(result.stdout.splitlines()[-1], TRAILER_PASS)

    def test_c2_findings_trailer(self):
        # Contract: any finding exits 1 and the FAIL trailer is the last stdout line.
        # Bug caught: findings printed but exit 0, or no FAIL trailer.
        with mock.patch.object(house_style, "OWNER_IMAGE_RE", re.compile(r"(?!x)x")):
            code, lines = run_inprocess()
        self.assertEqual(code, 1)
        self.assertEqual(lines[-1], TRAILER_FAIL)
        self.assertEqual(sum(line.startswith("FAIL ") for line in lines), 2)

    def test_c2_1_bad_record_passed(self):
        # Contract: a must-fail record that passes is named, ahead of record-changed in the same case.
        # Bug caught: a path regex that lets '../../private/photo.webp' through goes unreported.
        with mock.patch.object(house_style, "CATALOG_IMAGE_RE", re.compile(r".*", re.S)):
            code, lines = run_inprocess()
        self.assertEqual([x for x in lines if x.startswith("FAIL ")],
                         ["FAIL bad-record-passed 1", "FAIL record-changed 1", TRAILER_FAIL])
        self.assertEqual(code, 1)
        self.assertEqual(lines[-1], TRAILER_FAIL)

    def test_c2_2_record_changed(self):
        # Contract: any case line that differs from the pinned answer is a record-changed finding.
        # Bug caught: a changed score or hard-failure name is silently accepted.
        with mock.patch.object(house_style, "OWNER_IMAGE_RE", re.compile(r"(?!x)x")):
            code, lines = run_inprocess()
        self.assertEqual([x for x in lines if x.startswith("FAIL record-changed")], ["FAIL record-changed 11"])
        self.assertEqual(code, 1)
        self.assertEqual(lines[-1], TRAILER_FAIL)

    def test_c2_3_check_error(self):
        # Contract: a raising repo call is one nameless FAIL and stops the cases.
        # Bug caught: a traceback, exception text on stdout, or later cases still run.
        calls = []

        def boom(*args, **kwargs):
            calls.append(args)
            raise RuntimeError("secret detail")

        with mock.patch.object(house_style, "check_product", boom):
            code, lines = run_inprocess()
        self.assertEqual(lines, ["FAIL check-error", TRAILER_FAIL])
        self.assertEqual(code, 1)
        self.assertEqual(len(calls), 1)

    def test_c3_usage_exit_2(self):
        # Contract: positional arguments and unknown flags are argparse errors, exit 2, empty stdout.
        # Bug caught: the tool accepts and ignores arguments.
        for args in (("extra",), ("--nope",)):
            with self.subTest(args=args):
                result = run_subprocess(*args)
                self.assertEqual(result.returncode, 2)
                self.assertEqual(result.stdout, "")

    def test_c4_read_only(self):
        # Contract: a run creates or changes no file under hass/ or storefront-mockup/.
        # Bug caught: the check writing a spec, cache or report next to the repo content.
        before = snapshot("hass", "storefront-mockup")
        result = run_subprocess()
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(snapshot("hass", "storefront-mockup"), before)

    def test_c5_output_shape(self):
        # Contract: every stdout line has a named form and stderr is empty.
        # Bug caught: debug prints, warnings or tracebacks added to the output.
        result = run_subprocess()
        self.assertEqual(result.stderr, "")
        for line in result.stdout.splitlines():
            self.assertTrue(any(shape.fullmatch(line) for shape in LINE_SHAPES), line)
        with mock.patch.object(house_style, "CATALOG_IMAGE_RE", re.compile(r".*", re.S)):
            _code, lines = run_inprocess()
        for line in lines:
            self.assertTrue(any(shape.fullmatch(line) for shape in LINE_SHAPES), line)

    def test_c6_fixture(self):
        # Contract: with the owner picture pattern matching nothing, only case 11 changes.
        # Bug caught: the owner-path case no longer depends on OWNER_IMAGE_RE.
        with mock.patch.object(house_style, "OWNER_IMAGE_RE", re.compile(r"(?!x)x")):
            code, lines = run_inprocess()
        self.assertEqual([x for x in lines if x.startswith("FAIL ")], ["FAIL record-changed 11", TRAILER_FAIL])
        self.assertEqual(code, 1)
        self.assertEqual(lines[-1], TRAILER_FAIL)

    def test_c7_live_pins(self):
        # Contract: the measured answers over 13 records, including three soft-check passes (cases 4, 6, 7).
        # Bug caught: a change to scoring, weights, shelves, maker link or text rules that alters an answer.
        result = run_subprocess()
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        self.assertEqual(result.stdout.splitlines(), LIVE + [TRAILER_PASS])
        self.assertEqual(tool.EXPECTED, LIVE)
        self.assertEqual(tool.MUST_FAIL, (1, 2, 3, 8, 9, 10, 12))


if __name__ == "__main__":
    unittest.main()
