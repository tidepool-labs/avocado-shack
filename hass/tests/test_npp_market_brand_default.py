"""Offline tests for scripts/hass/npp_market_brand_default.py (fixtures only, no network)."""

import contextlib
import importlib.util
import io
from pathlib import Path
import re
import subprocess
import sys
import unittest
from unittest import mock


ROOT = Path(__file__).resolve().parents[2]
SCRIPT = ROOT / "scripts/hass/npp_market_brand_default.py"
TRAILER_PASS = "PASS npp_market_brand_default"
TRAILER_FAIL = "FAIL npp_market_brand_default"
C7 = [
    "case 0 defaulted=[0]", "case 1 defaulted=[]", "case 2 defaulted=[]", "case 3 defaulted=[]",
    "case 4 defaulted=[]", "case 5 defaulted=[]", "case 6 defaulted=[]", "case 7 defaulted=[1]",
    "case 8 defaulted=[]", "case 9 defaulted=[]",
]
LINE_FORMS = re.compile(
    r"case \d+ defaulted=\[[\d, ]*\]|FAIL supplied-brand-exempted \d+|FAIL defaulted-changed \d+"
    r"|FAIL check-error|PASS npp_market_brand_default|FAIL npp_market_brand_default")


def load():
    spec = importlib.util.spec_from_file_location("npp_market_brand_default_under_test", SCRIPT)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def every_new_product_exempt(draft):
    return {i for i, r in enumerate(draft.get("records") or [])
            if r.get("collection") == "products" and r.get("before") is None}


def snapshot():
    state = {}
    for tree in ("hass", "storefront-mockup"):
        for path in sorted((ROOT / tree).rglob("*")):
            if "__pycache__" in path.parts:
                continue  # the test process itself may write bytecode; the script run must not
            info = path.stat()
            state[str(path)] = (info.st_size, info.st_mtime_ns)
    return state


class MarketBrandDefaultTests(unittest.TestCase):
    def setUp(self):
        self.module = load()

    def in_process(self, replacement=None):
        out = io.StringIO()
        with contextlib.ExitStack() as stack:
            if replacement is not None:
                stack.enter_context(mock.patch.object(self.module.claims, "_defaulted", replacement))
            stack.enter_context(contextlib.redirect_stdout(out))
            code = self.module.main([])
        return code, out.getvalue().splitlines()

    def run_script(self, *args):
        return subprocess.run([sys.executable, "-B", str(SCRIPT), *args], cwd=ROOT,
                              capture_output=True, text=True, timeout=30)

    def test_c1_full_pass(self):
        # A script that prints findings at main, or exits non-zero, breaks the drift guard's pass.
        result = self.run_script()
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        self.assertEqual(result.stdout.splitlines()[-1], TRAILER_PASS)

    def test_c2_findings_trailer(self):
        # A run with a finding that still exits 0 or ends in PASS would hide drift.
        code, lines = self.in_process(lambda draft: set())
        self.assertEqual(code, 1)
        self.assertEqual(lines[-1], TRAILER_FAIL)

    def test_c2_1_supplied_brand_exempted(self):
        # A _defaulted that exempts every new product lets a supplied or invented label skip the gate.
        code, lines = self.in_process(every_new_product_exempt)
        self.assertEqual(code, 1)
        self.assertEqual([line for line in lines if line.startswith("FAIL ") and line != TRAILER_FAIL], [
            "FAIL supplied-brand-exempted 1", "FAIL defaulted-changed 1",
            "FAIL supplied-brand-exempted 2", "FAIL defaulted-changed 2",
            "FAIL supplied-brand-exempted 3", "FAIL defaulted-changed 3",
            "FAIL supplied-brand-exempted 5", "FAIL defaulted-changed 5",
            "FAIL supplied-brand-exempted 6", "FAIL defaulted-changed 6",
            "FAIL defaulted-changed 7"])
        self.assertEqual(lines[-1], TRAILER_FAIL)
        self.assertEqual([i for i in self.module.MUST_EMPTY], [1, 2, 3, 4, 5, 6, 8, 9])

    def test_c2_2_defaulted_changed(self):
        # A _defaulted that stops exempting the generated brand line changes the pinned answers.
        code, lines = self.in_process(lambda draft: set())
        self.assertEqual(code, 1)
        self.assertEqual([line for line in lines if line.startswith("FAIL ")],
                         ["FAIL defaulted-changed 0", "FAIL defaulted-changed 7", TRAILER_FAIL])
        self.assertEqual(self.module.EXPECTED, C7)

    def test_c2_3_check_error(self):
        # A repo call that raises must be a named FAIL once, not a traceback or a silent skip.
        calls = []

        def boom(draft):
            calls.append(draft)
            raise RuntimeError("secret detail")

        code, lines = self.in_process(boom)
        self.assertEqual(code, 1)
        self.assertEqual(lines, ["FAIL check-error", TRAILER_FAIL])
        self.assertEqual(len(calls), 1)

    def test_c3_usage_exit_2(self):
        for args in (("extra",), ("--nope",)):
            with self.subTest(args=args):
                result = self.run_script(*args)
                self.assertEqual(result.returncode, 2)
                self.assertEqual(result.stdout, "")

    def test_c4_read_only(self):
        # A script that writes a cache, report or bytecode into the trees would change this snapshot.
        before = snapshot()
        result = self.run_script()
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(snapshot(), before)

    def test_c5_output_shape(self):
        result = self.run_script()
        self.assertEqual(result.stderr, "")
        for line in result.stdout.splitlines():
            self.assertIsNotNone(LINE_FORMS.fullmatch(line), line)
        _, lines = self.in_process(every_new_product_exempt)
        for line in lines:
            self.assertIsNotNone(LINE_FORMS.fullmatch(line), line)
        self.assertIsNone(LINE_FORMS.fullmatch("FAIL check-error: RuntimeError"))

    def test_c6_fixture(self):
        code, lines = self.in_process(lambda draft: set())
        self.assertEqual(code, 1)
        self.assertEqual([line for line in lines if line.startswith("FAIL defaulted")],
                         ["FAIL defaulted-changed 0", "FAIL defaulted-changed 7"])
        self.assertEqual(lines[-1], TRAILER_FAIL)

    def test_c7_live_pins(self):
        # Pins the answers read from the repo's own claims._defaulted, not from this script.
        result = self.run_script()
        self.assertEqual(result.returncode, 0, result.stderr)
        lines = result.stdout.splitlines()
        self.assertEqual(lines, C7 + [TRAILER_PASS])
        self.assertEqual(len(self.module.CASES), 10)
        self.assertEqual(self.module.claims._defaulted(self.module.CASES[0]), {0})
        self.assertEqual(self.module.claims._defaulted(self.module.CASES[7]), {1})


if __name__ == "__main__":
    unittest.main()
