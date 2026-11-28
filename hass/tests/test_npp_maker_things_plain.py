"""Behavioral tests for the offline maker product phrase guard."""

from contextlib import redirect_stderr, redirect_stdout
import importlib.util
from io import StringIO
from pathlib import Path
import subprocess
import sys
import unittest
from unittest.mock import call, patch


ROOT = Path(__file__).resolve().parents[2]
SCRIPT = ROOT / "scripts/hass/npp_maker_things_plain.py"
PASS = "PASS npp_maker_things_plain"
FAIL = "FAIL npp_maker_things_plain"
LIVE_LINES = [
    "case 0 things='honey and beeswax candles'",
    "case 1 things='jam, jelly and marmalade'",
    "case 2 things=None",
    "case 3 things=None",
    "case 4 things='honey'",
    "case 5 things=None",
    "case 6 things=None",
    "case 7 things='small-batch honey'",
    "case 8 things=None",
    "case 9 things='sourdough bread'",
    "case 10 things=None",
    "case 11 things=None",
]


def tree_snapshot():
    entries = {}
    for name in ("hass", "storefront-mockup"):
        tree = ROOT / name
        for path in (tree, *tree.rglob("*")):
            stat = path.lstat()
            entries[path.relative_to(ROOT)] = (stat.st_size, stat.st_mtime_ns)
    return entries


class MakerThingsPlainTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        spec = importlib.util.spec_from_file_location(SCRIPT.stem, SCRIPT)
        if spec is None or spec.loader is None:
            raise ImportError("could not load the maker phrase guard")
        cls.tool = importlib.util.module_from_spec(spec)
        with patch.object(sys, "path", sys.path[:]):
            spec.loader.exec_module(cls.tool)

    def run_cli(self, *args):
        return subprocess.run(
            [sys.executable, "-B", str(SCRIPT), *args], cwd=ROOT,
            capture_output=True, text=True, timeout=10,
        )

    def run_main(self, code, trailer):
        stdout, stderr = StringIO(), StringIO()
        with redirect_stdout(stdout), redirect_stderr(stderr):
            result = self.tool.main([])
        lines = stdout.getvalue().splitlines()
        self.assertEqual(result, code)
        self.assertEqual(stderr.getvalue(), "")
        self.assertEqual(lines[-1:], [trailer])
        return lines[:-1]

    def run_without_cut_words(self):
        with patch.object(self.tool.maker_site, "CUT_WORDS", frozenset()):
            return self.run_main(1, FAIL)

    def test_c1_full_pass(self):
        # The standalone entry point must propagate success and emit a final PASS.
        run = self.run_cli()
        self.assertEqual(run.returncode, 0, run.stderr)
        self.assertEqual(run.stdout.splitlines()[-1:], [PASS])

    def test_c2_findings_trailer(self):
        # Buffering findings until the end loses their association with each case.
        expected = []
        for i, line in enumerate(LIVE_LINES):
            if i in (1, 4, 9):
                expected.extend([f"case {i} things=None", f"FAIL things-changed {i}"])
            else:
                expected.append(line)
        self.assertEqual(self.run_without_cut_words(), expected)

    def test_c2_1_non_product_thing_read(self):
        # Equality drift alone would miss the distinct non-product finding.
        with patch.object(self.tool.maker_site, "_thing_word", lambda word: True):
            lines = self.run_main(1, FAIL)
        self.assertEqual(lines, LIVE_LINES[:11] + [
            "case 11 things='honey and gravel'",
            "FAIL non-product-thing-read 11",
            "FAIL things-changed 11",
        ])

    def test_c2_2_things_changed(self):
        # Losing a genuine product still needs a finding, even outside MUST_NONE.
        lines = self.run_without_cut_words()
        for i in (1, 4, 9):
            offset = lines.index(f"case {i} things=None")
            self.assertEqual(lines[offset + 1], f"FAIL things-changed {i}")

    def test_c2_3_check_error(self):
        # A late exception must preserve earlier output, hide details and stop checks.
        real = self.tool.maker_site._things

        def raise_on_second_case(phrase):
            if phrase == "jam, jelly and marmalade in small batches.":
                raise RuntimeError("synthetic exception detail")
            return real(phrase)

        with patch.object(self.tool.maker_site, "_things", side_effect=raise_on_second_case) as reader:
            self.assertEqual(self.run_main(1, FAIL), LIVE_LINES[:1] + ["FAIL check-error"])
        self.assertEqual(reader.call_args_list, [
            call("honey and beeswax candles."), call("jam, jelly and marmalade in small batches."),
        ])

    def test_c3_usage_exit_2(self):
        # No argument, including argparse's usual help and delimiter, is accepted.
        for arg in ("extra", "--unknown", "--help", "-h", "--"):
            with self.subTest(arg=arg):
                run = self.run_cli(arg)
                self.assertEqual(run.returncode, 2)
                self.assertEqual(run.stdout, "")
                self.assertTrue(run.stderr.startswith("usage:"), run.stderr)

    def test_c4_read_only(self):
        # A saved diagnostic or touched source file would violate read-only operation.
        before = tree_snapshot()
        run = self.run_cli()
        self.assertEqual(run.returncode, 0, run.stderr)
        self.assertEqual(run.stdout.splitlines()[-1:], [PASS])
        self.assertEqual(tree_snapshot(), before)

    def test_c5_output_shape(self):
        # Logging, blank lines, or dropped case records break consumers of stdout.
        run = self.run_cli()
        lines = run.stdout.splitlines()
        self.assertEqual(run.returncode, 0, run.stderr)
        self.assertEqual(lines[-1:], [PASS])
        self.assertEqual(run.stderr, "")
        self.assertEqual(len(lines[:-1]), 12)
        for i, line in enumerate(lines[:-1]):
            self.assertRegex(line, rf"^case {i} things=(?:None|'[^']*')$")

    def test_c6_fixture(self):
        # Removing the cut words must change exactly the three cut-dependent cases.
        lines = self.run_without_cut_words()
        self.assertEqual([line for line in lines if line.startswith("FAIL ")], [
            "FAIL things-changed 1", "FAIL things-changed 4", "FAIL things-changed 9",
        ])

    def test_c7_live_pins(self):
        # Check literal pins and exact inputs: cached or reordered cases must not pass.
        maker_site = self.tool.maker_site
        with patch.object(maker_site, "_things", wraps=maker_site._things) as reader:
            self.assertEqual(self.run_main(0, PASS), LIVE_LINES)
        self.assertEqual(reader.call_args_list, [
            call("honey and beeswax candles."),
            call("jam, jelly and marmalade in small batches."),
            call("honey and relieves migraines."),
            call("every kind of honey."),
            call("honey for 30 dollars."),
            call("and honey."),
            call("honey and and jam."),
            call("small-batch honey."),
            call("cures for colds."),
            call("sourdough bread for the farmers market."),
            call(""),
            call("honey and gravel."),
        ])
