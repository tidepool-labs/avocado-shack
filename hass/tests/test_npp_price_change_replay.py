"""Offline CLI contract tests for the synthetic card-out price replay."""

from contextlib import redirect_stderr, redirect_stdout
import importlib.util
from io import StringIO
from pathlib import Path
import subprocess
import sys
from tempfile import TemporaryDirectory
import unittest
from unittest.mock import patch

from hass.npp.job import Plan


ROOT = Path(__file__).resolve().parents[2]
SCRIPT = ROOT / "scripts/hass/npp_price_change_replay.py"
PASS = "PASS npp_price_change_replay"
FAIL = "FAIL npp_price_change_replay"


def tree_snapshot():
    snapshot = {}
    for name in ("hass", "storefront-mockup"):
        subtree = ROOT / name
        for path in (subtree, *subtree.rglob("*")):
            stat = path.lstat()
            snapshot[path.relative_to(ROOT)] = (stat.st_size, stat.st_mtime_ns)
    return snapshot


class NppPriceChangeReplayTests(unittest.TestCase):
    def setUp(self):
        self.cwd = self.enterContext(TemporaryDirectory())
        spec = importlib.util.spec_from_file_location("npp_price_change_replay", SCRIPT)
        if spec is None or spec.loader is None:
            self.fail("could not load the replay script")
        self.replay = importlib.util.module_from_spec(spec)
        with patch.object(sys, "path", sys.path.copy()):
            spec.loader.exec_module(self.replay)

    def run_cli(self, *args):
        result = subprocess.run(
            [sys.executable, "-B", str(SCRIPT), *args], cwd=self.cwd,
            capture_output=True, text=True, timeout=15,
        )
        return result.returncode, result.stdout.splitlines(), result.stderr

    def run_main(self, wordings):
        stdout, stderr = StringIO(), StringIO()
        with patch.object(self.replay, "WORDINGS", wordings), redirect_stdout(stdout), redirect_stderr(stderr):
            code = self.replay.main([])
        return code, stdout.getvalue().splitlines(), stderr.getvalue()

    def assert_outcome(self, run, code, trailer):
        status, lines, stderr = run
        self.assertEqual(status, code)
        self.assertTrue(lines)
        self.assertEqual(lines[-1], trailer)
        self.assertEqual(stderr, "")
        return lines[:-1]

    def test_c1_full_pass(self):
        # A clean edit should not inherit the failure exit or trailer.
        self.assert_outcome(self.run_main(("sell it for $5 each",)), 0, PASS)

    def test_c2_findings_trailer(self):
        # A routed question is still a failure, even when it is the only check.
        lines = self.assert_outcome(self.run_main(("$5",)), 1, FAIL)
        self.assertIn("FAIL price-asked 01", lines)

    def test_c2_1_price_findings(self):
        # Grouping findings by reason instead of row would reorder this fixture.
        run = self.run_main(("it's $5 now", "$5 each", "make it $5", "price is now $5", "price: $5"))
        lines = self.assert_outcome(run, 1, FAIL)
        self.assertEqual([line for line in lines if line.startswith("FAIL ")], [
            "FAIL price-not-routed 01", "FAIL price-asked 03",
            "FAIL price-not-routed 04", "FAIL price-asked 05",
        ])

    def test_c2_2_price_other(self):
        # A question-free plan is not necessarily a successful price edit.
        with patch.object(self.replay.Stages, "edit", side_effect=[
            Plan(listing={"sellingPrice": "4.00"}), Plan(),
        ]):
            run = self.run_main(("$5 each", "make it $5 each"))
        self.assertEqual(self.assert_outcome(run, 1, FAIL), [
            "price 01 routed=yes read=yes result=other",
            "FAIL price-other 01",
            "price 02 routed=yes read=yes result=other",
            "FAIL price-other 02",
        ])

    def test_c2_3_check_error(self):
        # An exception from any check must not escape or expose its text.
        for owner, method in ((self.replay.Stages, "takes_turn"),
                              (self.replay.private_numbers, "finance"),
                              (self.replay.Stages, "edit")):
            with self.subTest(method=method), patch.object(owner, method, side_effect=ValueError("synthetic detail")):
                run = self.run_main(("$5 each",))
                self.assertEqual(self.assert_outcome(run, 1, FAIL), ["FAIL check-error"])

    def test_c3_usage_exit_2(self):
        # Do not accept a positional, flag, or even argparse's default help flag.
        for argument in ("unexpected", "--unknown", "--help"):
            with self.subTest(argument=argument):
                status, lines, stderr = self.run_cli(argument)
                self.assertEqual(status, 2)
                self.assertEqual(lines, [])  # No stdout trailer on argparse errors.
                self.assertTrue(stderr.startswith("usage: "), stderr)
                self.assertTrue(stderr.splitlines()[-1].endswith(f"unrecognized arguments: {argument}"), stderr)

    def test_c4_read_only(self):
        # Catch an accidental write back into either source tree, even on failure.
        before = tree_snapshot()
        run = self.run_cli()
        self.assert_outcome(run, 1, FAIL)
        self.assertEqual(tree_snapshot(), before)

    def test_c5_output_shape(self):
        # Catch incidental logging or disclosure of a wording or amount.
        lines = self.assert_outcome(self.run_cli(), 1, FAIL)
        for line in lines:
            self.assertRegex(line, r"\A(?:price [0-9]{2} routed=(?:yes|no) read=(?:yes|no) "
                                   r"result=(?:applied|asked|other|skipped)|"
                                   r"FAIL (?:price-(?:asked|not-routed|other) [0-9]{2}|check-error))\Z")

    def test_c6_fixture(self):
        # Detect a hard-coded replay matrix or incorrect successful-row formatting.
        run = self.run_main(("$5 each", "make it $5 each"))
        self.assertEqual(self.assert_outcome(run, 0, PASS), [
            "price 01 routed=yes read=yes result=applied",
            "price 02 routed=yes read=yes result=applied",
        ])

    def test_c7_live_pins(self):
        # Detect routing/finance/edit drift on the unpatched repo assets.
        lines = self.assert_outcome(self.run_cli(), 1, FAIL)
        rows = [line for line in lines if line.startswith("price ")]
        self.assertEqual(len(rows), 12)
        self.assertEqual(rows[3], "price 04 routed=yes read=yes result=applied")
        self.assertEqual(rows[7], "price 08 routed=yes read=no result=asked")
        self.assertEqual(rows[10], "price 11 routed=no read=no result=skipped")
        self.assertEqual([line for line in lines if line.startswith("FAIL ")], [
            "FAIL price-asked 05", "FAIL price-asked 06", "FAIL price-asked 07",
            "FAIL price-asked 08", "FAIL price-asked 09", "FAIL price-asked 10",
            "FAIL price-not-routed 11", "FAIL price-not-routed 12",
        ])
