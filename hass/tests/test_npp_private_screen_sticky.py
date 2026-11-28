"""Behavioral contracts for the offline NPP intake drift guard."""

from contextlib import redirect_stderr, redirect_stdout
from decimal import Decimal
import importlib.util
from io import StringIO
from pathlib import Path
import subprocess
import sys
from tempfile import TemporaryDirectory
import unittest
from unittest.mock import patch


ROOT = Path(__file__).resolve().parents[2]
SCRIPT = ROOT / "scripts/hass/npp_private_screen_sticky.py"
PASS = "PASS npp_private_screen_sticky"
FAIL = "FAIL npp_private_screen_sticky"


def load_tool():
    spec = importlib.util.spec_from_file_location("npp_private_screen_sticky", SCRIPT)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def snapshot():
    entries = {}
    for name in ("hass", "storefront-mockup"):
        tree = ROOT / name
        for path in (tree, *tree.rglob("*")):
            info = path.lstat()
            entries[path.relative_to(ROOT)] = (info.st_size, info.st_mtime_ns)
    return entries


def round_private(n):
    return Decimal(n).quantize(Decimal("1"))


class NppPrivateScreenStickyTests(unittest.TestCase):
    def cli(self, *args):
        with TemporaryDirectory() as cwd:
            return subprocess.run([sys.executable, "-B", str(SCRIPT), *args], cwd=cwd,
                                  capture_output=True, text=True, timeout=15)

    def invoke(self, tool, code, trailer):
        stdout, stderr = StringIO(), StringIO()
        with redirect_stdout(stdout), redirect_stderr(stderr):
            result = tool.main([])
        self.assertEqual(result, code, stdout.getvalue())
        self.assertEqual(stderr.getvalue(), "")
        lines = stdout.getvalue().splitlines()
        self.assertEqual(lines[-1:], [trailer])
        return lines[:-1]

    def test_c1_full_pass(self):
        # The standalone entry point could fail to import or discard main's status.
        result = self.cli()
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(result.stdout.splitlines()[-1:], [PASS])

    def test_c2_findings_trailer(self):
        # A real mismatch must not end with a success status or trailer.
        tool = load_tool()
        with patch.object(tool.job, "Decimal", round_private):
            self.invoke(tool, 1, FAIL)

    def test_c2_1_declassified(self):
        # A write that drops the cost flag must report the transition as well as drift.
        tool = load_tool()
        put = tool.openreq.OpenRequests.put

        def forget_cost(store, *args, **kwargs):
            if kwargs.get("request_id") is not None:
                slots = kwargs["slots"]
                kwargs["slots"] = {**slots, "intake": {**slots["intake"], "has_cost": False}}
            return put(store, *args, **kwargs)

        with patch.object(tool.openreq.OpenRequests, "put", forget_cost):
            lines = self.invoke(tool, 1, FAIL)
        self.assertEqual([line for line in lines if line.startswith("FAIL ")],
                         ["FAIL declassified 1", *(f"FAIL slot-changed {i}" for i in range(1, 7))])

    def test_c2_2_slot_changed(self):
        # Rounding adds the wrong value without shrinking the preceding private set.
        tool = load_tool()
        with patch.object(tool.job, "Decimal", round_private):
            lines = self.invoke(tool, 1, FAIL)
        self.assertEqual([line for line in lines if line.startswith("FAIL ")], ["FAIL slot-changed 6"])

    def test_c2_3_check_error(self):
        # Asset loading errors must fail closed without emitting exception details.
        tool = load_tool()
        with patch.object(tool.hass.npp, "assets", side_effect=RuntimeError("synthetic exception detail")):
            self.assertEqual(self.invoke(tool, 1, FAIL), ["FAIL check-error"])

    def test_c3_usage_exit_2(self):
        # Argparse's default help and bare separator must not bypass the no-args contract.
        for arg in ("unexpected", "--unknown", "--help", "--"):
            with self.subTest(arg=arg):
                result = self.cli(arg)
                self.assertEqual(result.returncode, 2)
                self.assertEqual(result.stdout, "")
                self.assertTrue(result.stderr.splitlines()[-1].startswith(f"{SCRIPT.name}: error: "))

    def test_c4_read_only(self):
        # An accidental write to a repo fixture could otherwise leave the CLI green.
        before = snapshot()
        result = self.cli()
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(result.stdout.splitlines()[-1:], [PASS])
        self.assertEqual(snapshot(), before)

    def test_c5_output_shape(self):
        # A debug line or stderr warning would break the operator-facing receipt.
        lines = self.invoke(load_tool(), 0, PASS)
        self.assertEqual(len(lines), 7)
        for i, line in enumerate(lines):
            self.assertRegex(line, rf"^step {i} \S+ price=(None|'[^']*') sold_by=(None|'[^']*') "
                                   r"private=\[(?:'[^']+'(?:, '[^']+')*)?\] cost=(yes|no) qty=(yes|no) "
                                   r"texts=\d+ turn=\w+$")

    def test_c6_fixture(self):
        # A constant replay would miss the changed step-6 value from real Decimal normalization.
        tool = load_tool()
        with patch.object(tool.job, "Decimal", round_private):
            lines = self.invoke(tool, 1, FAIL)
        self.assertEqual(lines[-2:], [
            "step 6 npp-working price=None sold_by=None private=['12', '3', '4'] cost=yes qty=yes texts=7 turn=edit",
            "FAIL slot-changed 6",
        ])
        self.assertEqual([line for line in lines if line.startswith("FAIL ")], ["FAIL slot-changed 6"])

    def test_c7_live_pins(self):
        # Independently pin the persisted intake through price replacement, clearing and photo edits.
        self.assertEqual(self.invoke(load_tool(), 0, PASS), [
            "step 0 npp-working price='5' sold_by='item' private=['3'] cost=yes qty=no texts=1 turn=start",
            "step 1 npp-working price='5' sold_by='item' private=['3'] cost=yes qty=no texts=2 turn=edit",
            "step 2 npp-working price='5' sold_by='item' private=['12', '3'] cost=yes qty=yes texts=3 turn=edit",
            "step 3 npp-working price='6' sold_by='pound' private=['12', '3'] cost=yes qty=yes texts=4 turn=edit",
            "step 4 npp-working price=None sold_by=None private=['12', '3'] cost=yes qty=yes texts=5 turn=edit",
            "step 5 npp-working price=None sold_by=None private=['12', '3'] cost=yes qty=yes texts=6 turn=photo",
            "step 6 npp-working price=None sold_by=None private=['12', '3', '3.5'] cost=yes qty=yes texts=7 turn=edit",
        ])
