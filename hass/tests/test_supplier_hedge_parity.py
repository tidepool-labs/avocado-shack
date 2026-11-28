"""Offline CLI contract for the S10 supplier hedge comparison."""

from contextlib import redirect_stderr, redirect_stdout
import importlib.util
import io
from pathlib import Path
import subprocess
import sys
from tempfile import TemporaryDirectory
import unittest
from unittest.mock import patch

from hass import npp
from hass.npp import edits


ROOT = Path(__file__).resolve().parents[2]
SCRIPT = ROOT / "scripts/hass/supplier_hedge_parity.py"
PASS = "PASS supplier_hedge_parity"
FAIL = "FAIL supplier_hedge_parity"


def snapshot(root):
    entries = {}
    for path in (root, *root.rglob("*")):
        info = path.lstat()
        entries[path.relative_to(root)] = (info.st_size, info.st_mtime_ns)
    return entries


class SupplierHedgeParityTests(unittest.TestCase):
    def setUp(self):
        spec = importlib.util.spec_from_file_location("supplier_hedge_parity", SCRIPT)
        assert spec is not None and spec.loader is not None
        self.tool = importlib.util.module_from_spec(spec)
        # Loading the CLI must not leave its sys.path bootstrap in the test runner.
        with patch.object(sys, "path", list(sys.path)):
            spec.loader.exec_module(self.tool)

    def invoke_main(self, code, trailer):
        stdout, stderr = io.StringIO(), io.StringIO()
        with redirect_stdout(stdout), redirect_stderr(stderr):
            result = self.tool.main([])
        return self.check_report(result, stdout.getvalue(), stderr.getvalue(), code, trailer)

    def invoke_cli(self, cwd, *args):
        return subprocess.run(
            [sys.executable, "-B", str(SCRIPT), *args], cwd=cwd,
            capture_output=True, text=True, timeout=15,
        )

    def check_report(self, result, stdout, stderr, code, trailer):
        self.assertEqual(result, code, stderr)
        self.assertEqual(stderr, "")
        lines = stdout.splitlines()
        self.assertTrue(lines)
        self.assertEqual(lines[-1], trailer)
        return lines

    def test_c1_full_pass(self):
        # Agreement on accepting a name must pass, not be treated like a disagreement.
        with patch.object(self.tool, "WORDS", ("Valley",)):
            self.assertEqual(self.invoke_main(0, PASS), ["hedge Valley form=patch sentence=keep", PASS])

    def test_c2_findings_trailer(self):
        # A later agreeing word must not clear the failure status or displace the trailer.
        with patch.object(self.tool, "WORDS", ("either", "or")):
            self.assertEqual(self.invoke_main(1, FAIL), [
                "hedge either form=ask sentence=keep", "FAIL hedge-disagree either",
                "hedge or form=ask sentence=drop", FAIL,
            ])

    def test_c2_1_assets_unreadable(self):
        # A loader exception must not leak its text or be counted as a pass.
        with patch.object(npp, "assets", side_effect=ValueError("synthetic detail")):
            self.assertEqual(self.invoke_main(1, FAIL), ["FAIL assets-unreadable", FAIL])

    def test_c2_2_supplier_form_missing(self):
        # Neither a missing match nor a wrong form should produce a hedge row or stop the loop.
        real_match = edits.Grammar.match

        def match(grammar, text):
            if text == "from Etto maybe Farm":
                return None
            if text == "from Etto not Farm":
                return "maker", {"value": "Etto not Farm"}
            return real_match(grammar, text)

        with patch.object(self.tool, "WORDS", ("maybe", "not", "or")), patch.object(edits.Grammar, "match", match):
            self.assertEqual(self.invoke_main(1, FAIL), [
                "FAIL supplier-form-missing maybe", "FAIL supplier-form-missing not",
                "hedge or form=ask sentence=drop", FAIL,
            ])

    def test_c2_3_hedge_disagree(self):
        # Both directions are findings; sorting or reporting only the first one loses evidence.
        with patch.object(self.tool, "WORDS", ("instead", "either", "please")):
            self.assertEqual(self.invoke_main(1, FAIL), [
                "hedge instead form=patch sentence=drop", "FAIL hedge-disagree instead",
                "hedge either form=ask sentence=keep", "FAIL hedge-disagree either",
                "hedge please form=patch sentence=drop", "FAIL hedge-disagree please", FAIL,
            ])

    def test_c3_usage_exit_2(self):
        # Even argparse's usual help flag is not accepted by this no-argument CLI.
        with TemporaryDirectory() as cwd:
            for arg in ("extra", "--unknown", "--help", "-h", "--"):
                with self.subTest(arg=arg):
                    result = self.invoke_cli(cwd, arg)
                    self.assertEqual(result.returncode, 2, result.stderr)
                    self.assertEqual(result.stdout, "")  # No last line on usage errors.
                    self.assertTrue(result.stderr.startswith("usage: "))
                    self.assertIn("error: unrecognized arguments:", result.stderr.splitlines()[-1])

    def test_c4_read_only(self):
        # Catch mutations under either input tree or the caller's working directory.
        with TemporaryDirectory() as cwd:
            roots = (ROOT / "hass", ROOT / "storefront-mockup", Path(cwd))
            before = [snapshot(root) for root in roots]
            result = self.invoke_cli(cwd)
            self.assertEqual([snapshot(root) for root in roots], before)
            self.check_report(result.returncode, result.stdout, result.stderr, 1, FAIL)

    def test_c5_output_shape(self):
        # A debug line or extra trailer would make the CLI output unusable as a line protocol.
        with TemporaryDirectory() as cwd:
            result = self.invoke_cli(cwd)
        lines = self.check_report(result.returncode, result.stdout, result.stderr, 1, FAIL)
        for line in lines[:-1]:
            self.assertRegex(line, r"^(hedge [a-z]+ form=(ask|patch) sentence=(keep|drop)|"
                                   r"FAIL (assets-unreadable|(supplier-form-missing|hedge-disagree) [a-z]+))$")

    def test_c6_fixture(self):
        # Bypassing WORDS or misclassifying ask/drop would break the three-word control.
        with patch.object(self.tool, "WORDS", ("or", "maybe", "not")):
            self.assertEqual(self.invoke_main(0, PASS), [
                "hedge or form=ask sentence=drop", "hedge maybe form=ask sentence=drop",
                "hedge not form=ask sentence=drop", PASS,
            ])

    def test_c7_live_pins(self):
        # A changed asset or screen, omitted word, or reordered word list invalidates the measured baseline.
        lines = self.invoke_main(1, FAIL)
        rows = [line for line in lines if line.startswith("hedge ")]
        self.assertEqual([line.split()[1] for line in rows],
                         "or maybe probably think guess not either please change add remove replace instead".split())
        self.assertIn("hedge either form=ask sentence=keep", rows)
        self.assertIn("hedge please form=patch sentence=drop", rows)
        self.assertEqual([line for line in lines[:-1] if line.startswith("FAIL ")], [
            "FAIL hedge-disagree either", "FAIL hedge-disagree please", "FAIL hedge-disagree change",
            "FAIL hedge-disagree add", "FAIL hedge-disagree remove", "FAIL hedge-disagree replace",
            "FAIL hedge-disagree instead",
        ])
