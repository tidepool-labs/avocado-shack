"""Contract tests for the offline NPP caption diagnostic."""

from contextlib import redirect_stderr, redirect_stdout
from dataclasses import replace
import importlib.util
import io
from pathlib import Path
import re
import subprocess
import sys
from tempfile import TemporaryDirectory
import unittest
from unittest.mock import patch


ROOT = Path(__file__).resolve().parents[2]
SCRIPT = ROOT / "scripts/hass/npp_two_number_captions.py"
PASS = "PASS npp_two_number_captions"
FAIL = "FAIL npp_two_number_captions"


def snapshot():
    paths = {}
    for name in ("hass", "storefront-mockup"):
        root = ROOT / name
        for path in (root, *root.rglob("*")):
            info = path.lstat()
            paths[path.relative_to(ROOT)] = (info.st_size, info.st_mtime_ns)
    return paths


class NPPTwoNumberCaptionsTests(unittest.TestCase):
    def setUp(self):
        temporary = TemporaryDirectory(dir=ROOT.parent)
        self.addCleanup(temporary.cleanup)
        self.cwd = Path(temporary.name)
        spec = importlib.util.spec_from_file_location("npp_two_number_captions", SCRIPT)
        assert spec is not None and spec.loader is not None
        self.tool = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(self.tool)
        self.numbers = self.tool.private_numbers

    def run_main(self, status, trailer):
        out, err = io.StringIO(), io.StringIO()
        with redirect_stdout(out), redirect_stderr(err):
            self.assertEqual(self.tool.main([]), status)
        self.assertEqual(err.getvalue(), "")
        lines = out.getvalue().splitlines()
        self.assertEqual(lines[-1:], [trailer])
        return lines[:-1]

    def run_cli(self, *args):
        return subprocess.run([sys.executable, "-B", str(SCRIPT), *args], cwd=self.cwd,
                              capture_output=True, text=True, timeout=10)

    def test_c1_full_pass(self):
        # Clean results from the real parser must not produce a fixed FAIL trailer.
        with patch.object(self.tool, "CAPTIONS", ("$5 each", "paid $3, selling $5 each")):
            self.assertEqual(self.run_main(0, PASS), [
                "case 0 price=5.00_each cost=0 count=0",
                "case 1 price=5.00_each cost=1 count=0",
            ])

    def test_c2_findings_trailer(self):
        # A failure early in the run must not be cleared by a later clean case.
        with patch.object(self.tool, "CAPTIONS", ("$6 each", "$5 each")):
            self.assertEqual(self.run_main(1, FAIL), [
                "case 0 price=6.00_each cost=0 count=0",
                "FAIL price-lost 0",
                "case 1 price=5.00_each cost=0 count=0",
            ])

    def test_c2_1_price_lost(self):
        # Checking for price presence instead of exact equality misses a wrong basis.
        with patch.object(self.tool, "CAPTIONS", ("$5 per lb",)):
            self.assertEqual(self.run_main(1, FAIL), [
                "case 0 price=5.00_per_lb cost=0 count=0",
                "FAIL price-lost 0",
            ])

    def test_c2_2_number_in_public(self):
        # A digit in public text must be flagged even when the price is right.
        finance = self.numbers.finance

        def leaked_digit(caption):
            return replace(finance(caption), public_words="synthetic digit 2")

        with patch.object(self.tool, "CAPTIONS", ("$5 each",)), \
                patch.object(self.numbers, "finance", side_effect=leaked_digit):
            self.assertEqual(self.run_main(1, FAIL), [
                "case 0 price=5.00_each cost=0 count=0",
                "FAIL number-in-public 0",
            ])

    def test_c2_3_check_error(self):
        # An unexpected parser error must not be skipped, echoed, or stop later checks.
        finance = self.numbers.finance

        def broken_first(caption):
            if caption == "$5 each":
                raise RuntimeError("synthetic error details")
            return finance(caption)

        with patch.object(self.tool, "CAPTIONS", ("$5 each", "$5 each, have 12")), \
                patch.object(self.numbers, "finance", side_effect=broken_first):
            self.assertEqual(self.run_main(1, FAIL), [
                "FAIL check-error",
                "case 1 price=5.00_each cost=0 count=1",
            ])

    def test_c3_usage_exit_2(self):
        # No arguments are accepted, including argparse's usual help option.
        for arg in ("caption", "--unknown", "--help", "--"):
            with self.subTest(arg=arg):
                result = self.run_cli(arg)
                self.assertEqual(result.returncode, 2)
                self.assertEqual(result.stdout, "")
                self.assertEqual(result.stderr.splitlines()[0], "usage: npp_two_number_captions.py")
                self.assertEqual(result.stderr.splitlines()[-1],
                                 f"npp_two_number_captions.py: error: unrecognized arguments: {arg}")

    def test_c4_read_only(self):
        # Detect artifacts or modifications in either source tree during a real CLI run.
        before = snapshot()
        result = self.run_cli()
        self.assertEqual(result.returncode, 1)
        self.assertEqual(result.stdout.splitlines()[-1:], [FAIL])
        self.assertEqual(snapshot(), before)

    def test_c5_output_shape(self):
        # Debug output, raw caption dumps, or extra trailer lines break the report format.
        result = self.run_cli()
        self.assertEqual(result.returncode, 1)
        self.assertEqual(result.stderr, "")
        lines = result.stdout.splitlines()
        self.assertEqual(lines[-1:], [FAIL])
        self.assertEqual([line.split()[1] for line in lines if line.startswith("case ")],
                         [str(i) for i in range(8)])
        for line in lines[:-1]:
            self.assertRegex(line, r"^(?:case [0-7] price=\S+ cost=[01] count=[01]"
                                   r"|FAIL (?:price-lost|number-in-public) [0-7]|FAIL check-error)$")

    def test_c6_fixture(self):
        # The diagnostic must follow the real parser when clause splitting changes.
        original = self.numbers._CLAUSE_BREAK
        wider_break = re.compile(original.pattern + r"|\s+and\s+|\s*\(|\)", original.flags)
        with patch.object(self.numbers, "_CLAUSE_BREAK", wider_break):
            lines = self.run_main(1, FAIL)
        self.assertEqual([line for line in lines if line.startswith("FAIL ")], [
            "FAIL price-lost 3", "FAIL price-lost 4", "FAIL price-lost 6",
        ])
        self.assertIn("case 5 price=5.00_each cost=1 count=0", lines)

    def test_c7_live_pins(self):
        # A change to the real parser or caption ordering must move these measured pins.
        with patch.object(self.numbers, "finance", wraps=self.numbers.finance) as finance:
            self.assertEqual(self.run_main(1, FAIL), [
                "case 0 price=5.00_each cost=0 count=0",
                "case 1 price=5.00_each cost=1 count=0",
                "case 2 price=5.00_each cost=0 count=1",
                "case 3 price=none cost=0 count=0",
                "FAIL price-lost 3",
                "case 4 price=none cost=0 count=0",
                "FAIL price-lost 4",
                "case 5 price=none cost=0 count=0",
                "FAIL price-lost 5",
                "case 6 price=none cost=0 count=0",
                "FAIL price-lost 6",
                "case 7 price=5.00_each cost=0 count=1",
            ])
        self.assertEqual([call.args for call in finance.call_args_list], [
            ("$5 each",), ("paid $3, selling $5 each",), ("$5 each, have 12",),
            ("$5 each and 12 in stock",), ("$5 each, we have twelve",),
            ("$5 each (paid $3)",), ("$5 each and $3 cost",), ("selling $5 each, got 12",),
        ])
