"""Offline CLI contract for the S3 shelf report; no production stage or service."""

from contextlib import redirect_stderr, redirect_stdout
from dataclasses import replace
import importlib.util
from io import StringIO
import json
from pathlib import Path
import subprocess
import sys
from tempfile import TemporaryDirectory
import unittest
from unittest.mock import patch

from hass import npp
from hass.npp import missing


ROOT = Path(__file__).resolve().parents[2]
SCRIPT = ROOT / "scripts/hass/npp_shelf_choice_matrix.py"
PASS = "PASS npp_shelf_choice_matrix"
FAIL = "FAIL npp_shelf_choice_matrix"


def invoke(*args, cwd=ROOT):
    return subprocess.run(
        [sys.executable, "-B", str(SCRIPT), *args], cwd=cwd,
        capture_output=True, text=True, timeout=10,
    )


def snapshot():
    entries = {}
    for name in ("hass", "storefront-mockup"):
        tree = ROOT / name
        for path in (tree, *tree.rglob("*")):
            info = path.lstat()
            entries[path.relative_to(ROOT)] = (info.st_size, info.st_mtime_ns)
    return entries


class ShelfChoiceMatrixTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        spec = importlib.util.spec_from_file_location(SCRIPT.stem, SCRIPT)
        assert spec is not None and spec.loader is not None
        cls.script = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(cls.script)

    def invoke_main(self):
        stdout, stderr = StringIO(), StringIO()
        with redirect_stdout(stdout), redirect_stderr(stderr):
            status = self.script.main([])
        return subprocess.CompletedProcess([], status, stdout.getvalue(), stderr.getvalue())

    def assert_trailer(self, result, status, trailer):
        self.assertEqual(result.returncode, status, result.stderr)
        self.assertEqual(result.stderr, "")
        lines = result.stdout.splitlines()
        self.assertEqual(lines[-1:], [trailer])
        return lines[:-1]

    def with_categories(self, overrides):
        decide = missing.MissingInfo.decide

        def changed(mi, reading, *, price):
            decision = decide(mi, reading, price=price)
            cell = reading["kind"], reading["category_guess"], reading["confidence"]["category"]
            return replace(decision, category=overrides[cell]) if cell in overrides else decision

        with patch.object(missing.MissingInfo, "decide", changed):
            return self.invoke_main()

    def assert_findings(self, result, expected):
        lines = self.assert_trailer(result, 1, FAIL)
        self.assertEqual([line for line in lines if line.startswith("FAIL ")], expected)
        return lines

    def test_c1_full_pass(self):
        # A broken standalone launcher or inverted success status must fail.
        with TemporaryDirectory() as work:
            self.assert_trailer(invoke(cwd=Path(work)), 0, PASS)

    def test_c2_findings_trailer(self):
        # Do not stop at the first finding or suppress another check on the same cell.
        result = self.with_categories({
            ("food", "vegetables", 0.9): "invented",
            ("non-food", None, 0.3): "fruit",
        })
        lines = self.assert_findings(result, [
            "FAIL not-a-shelf food vegetables 0.9",
            "FAIL confident-guess-lost food vegetables",
            "FAIL nonfood-shelf none 0.3",
        ])
        self.assertEqual(sum(line.startswith("shelf ") for line in lines), 32)

    def test_c2_1_not_a_shelf(self):
        # A weak answer still needs a real shelf, even without a confident guess to compare.
        result = self.with_categories({("food", None, 0.3): "invented"})
        self.assert_findings(result, ["FAIL not-a-shelf food none 0.3"])

    def test_c2_2_nonfood_shelf(self):
        # Membership alone would accept an incorrect but real non-food shelf.
        result = self.with_categories({("non-food", "flowers", 0.9): "flowers"})
        self.assert_findings(result, ["FAIL nonfood-shelf flowers 0.9"])

    def test_c2_3_confident_guess_lost(self):
        # A valid kind default is not an acceptable substitute for the strong guess.
        result = self.with_categories({("drink", "vegetables", 0.9): "drinks"})
        self.assert_findings(result, ["FAIL confident-guess-lost drink vegetables"])

    def test_c2_4_check_error(self):
        # A thrown decision must yield a finding, not a traceback or a skipped green cell.
        decide = missing.MissingInfo.decide

        def broken(mi, reading, *, price):
            if (reading["kind"], reading["category_guess"], reading["confidence"]["category"]) == (
                "food", "vegetables", 0.9,
            ):
                raise ValueError("fixture decision error")
            return decide(mi, reading, price=price)

        with patch.object(missing.MissingInfo, "decide", broken):
            lines = self.assert_findings(self.invoke_main(), ["FAIL check-error"])
        self.assertEqual(sum(line.startswith("shelf ") for line in lines), 31)
        self.assertFalse(any(line.startswith("shelf food vegetables 0.9 ") for line in lines))

    def test_c3_usage_exit_2(self):
        # No arguments are supported, including the implicit argparse help flag.
        for arg in ("extra", "--unknown", "--help", "--"):
            with self.subTest(arg=arg):
                result = invoke(arg)
                self.assertEqual(result.returncode, 2)
                self.assertEqual(result.stdout, "")
                self.assertTrue(result.stderr.startswith("usage:"))
                self.assertEqual(result.stderr.splitlines()[-1],
                                 f"{SCRIPT.name}: error: unrecognized arguments: {arg}")

    def test_c4_read_only(self):
        # Catch caches or accidental writes to inputs, even when the report still passes.
        before = snapshot()
        self.assert_trailer(invoke(), 0, PASS)
        self.assertEqual(snapshot(), before)

    def test_c5_output_shape(self):
        # Progress messages or debug output must not break the line-oriented report.
        lines = self.assert_trailer(invoke(), 0, PASS)
        self.assertEqual(len(lines), 32)
        for line in lines:
            self.assertRegex(line, r"^shelf (food|drink|fresh|non-food) "
                                   r"(vegetables|flowers|general|none) (0\.9|0\.3) -> [a-z-]+$")

    def test_c6_fixture(self):
        # A duplicated default or finding on a changed but valid weak answer breaks this.
        pins, files, replies = npp.assets()
        rules = json.loads(files[missing.RULES])
        rules["kind_default_category"]["fresh"] = "vegetables"
        with TemporaryDirectory() as work:
            copy = Path(work) / "missing-info.json"
            copy.write_text(json.dumps(rules), encoding="utf-8")
            with patch.object(npp, "assets", return_value=(
                pins, {**files, missing.RULES: copy.read_bytes()}, replies,
            )):
                lines = self.assert_trailer(self.invoke_main(), 0, PASS)
        self.assertEqual([line for line in lines if line.startswith("shelf fresh ") and " 0.3 " in line], [
            f"shelf fresh {guess} 0.3 -> vegetables"
            for guess in ("vegetables", "flowers", "general", "none")
        ])

    def test_c7_live_pins(self):
        # Pin the observed base matrix independently of the implementation and asset loader.
        # Dropping a cell, swapping confidence levels, or ignoring a pinned default fails.
        lines = self.assert_trailer(invoke(), 0, PASS)
        columns = ("vegetables 0.9", "vegetables 0.3", "flowers 0.9", "flowers 0.3",
                   "general 0.9", "general 0.3", "none 0.9", "none 0.3")
        shelves = (
            ("food", "vegetables pantry flowers pantry general pantry pantry pantry"),
            ("drink", "vegetables drinks flowers drinks general drinks drinks drinks"),
            ("fresh", "vegetables fruit flowers fruit general fruit fruit fruit"),
            ("non-food", "general general general general general general general general"),
        )
        self.assertEqual(lines, [
            f"shelf {kind} {column} -> {shelf}"
            for kind, row in shelves for column, shelf in zip(columns, row.split(), strict=True)
        ])
