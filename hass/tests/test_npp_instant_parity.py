"""Offline output and exit contracts for the NPP instant comparison."""

from contextlib import redirect_stderr, redirect_stdout
import importlib.util
import io
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import Mock, patch


ROOT = Path(__file__).resolve().parents[2]
SCRIPT = ROOT / "scripts/hass/npp_instant_parity.py"
PASS = "PASS npp_instant_parity"
FAIL = "FAIL npp_instant_parity"
UTC = "2026-11-21T09:30:00Z"
NEGATIVE_OFFSET = "2026-11-21T01:30:00-08:00"
POSITIVE_OFFSET = "2026-11-21T09:30:00+00:00"


def snapshot(root):
    entries = {}
    for tree in (root / "hass", root / "storefront-mockup"):
        for path in (tree, *tree.rglob("*")):
            stat = path.lstat()
            entries[path.relative_to(root)] = (stat.st_size, stat.st_mtime_ns)
    return entries


class NppInstantParityTests(unittest.TestCase):
    def setUp(self):
        spec = importlib.util.spec_from_file_location("npp_instant_parity", SCRIPT)
        assert spec is not None and spec.loader is not None
        self.tool = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(self.tool)

    def invoke(self, values):
        stdout, stderr = io.StringIO(), io.StringIO()
        with patch.object(self.tool, "VALUES", values), redirect_stdout(stdout), redirect_stderr(stderr):
            code = self.tool.main([])
        self.assertEqual(stderr.getvalue(), "")
        return code, stdout.getvalue().splitlines()

    def cli(self, *args):
        with tempfile.TemporaryDirectory() as cwd:
            return subprocess.run(
                [sys.executable, "-B", str(SCRIPT), *args], cwd=cwd,
                capture_output=True, text=True, timeout=10,
            )

    def test_c1_full_pass(self):
        # A shared refusal is agreement, not a failed check.
        code, lines = self.invoke(("2026-11-21T09:30:00",))
        self.assertEqual(code, 0)
        self.assertEqual(lines, ["instant 01 receipt=refused evidence=refused", PASS])

    def test_c2_findings_trailer(self):
        # A matching final stamp must not reset a prior finding's verdict.
        code, lines = self.invoke((POSITIVE_OFFSET, UTC))
        self.assertEqual(code, 1)
        self.assertEqual(lines[-1], FAIL)

    def test_c2_1_instant_disagree(self):
        # Using the count of findings, or comparing only receipt-accepted stamps,
        # would miss the second finding (an evidence-only acceptance).
        with patch.object(self.tool.receipt, "instant", side_effect=[object(), object(), None]):
            code, lines = self.invoke((POSITIVE_OFFSET, UTC, UTC))
        self.assertEqual(code, 1)
        self.assertEqual(lines, [
            "instant 01 receipt=ok evidence=refused",
            "FAIL instant-disagree 01",
            "instant 02 receipt=ok evidence=ok",
            "instant 03 receipt=refused evidence=ok",
            "FAIL instant-disagree 03",
            FAIL,
        ])

    def test_c2_2_check_error(self):
        # Unexpected failures must not be reported as refusals or leak their text.
        broken_record = Mock()
        broken_record.approval.side_effect = RuntimeError("synthetic error detail")
        for target, name, responses in (
            (self.tool.receipt, "instant", [ValueError("synthetic error detail"), object()]),
            (self.tool.evidence, "Evidence", [broken_record, self.tool.evidence.Evidence()]),
        ):
            with self.subTest(boundary=name), patch.object(target, name, side_effect=responses):
                code, lines = self.invoke((UTC, POSITIVE_OFFSET))
                self.assertEqual(code, 1)
                self.assertEqual(lines, [
                    "FAIL check-error",
                    "instant 02 receipt=ok evidence=refused",
                    "FAIL instant-disagree 02",
                    FAIL,
                ])

    def test_c3_usage_exit_2(self):
        # The bare marker and built-in help must not bypass the no-arguments rule.
        for arg in ("unexpected", "--unknown", "--help", "--"):
            with self.subTest(arg=arg):
                result = self.cli(arg)
                self.assertEqual(result.returncode, 2)
                self.assertEqual(result.stdout, "")  # No last stdout line on usage errors.
                self.assertTrue(result.stderr.startswith("usage: "), result.stderr)
                self.assertIn("error:", result.stderr.splitlines()[-1])

    def test_c4_read_only(self):
        # A switch from classification to persisting evidence would change the snapshot.
        before = snapshot(ROOT)
        result = self.cli()
        self.assertEqual(result.returncode, 1)
        self.assertEqual(result.stdout.splitlines()[-1], FAIL)
        self.assertEqual(snapshot(ROOT), before)

    def test_c5_output_shape(self):
        # A banner, timestamp echo, or debug print would violate the closed output grammar.
        result = self.cli()
        self.assertEqual(result.returncode, 1)
        self.assertEqual(result.stderr, "")
        lines = result.stdout.splitlines()
        self.assertEqual(lines[-1], FAIL)
        for line in lines[:-1]:
            self.assertRegex(line, r"\A(?:instant [0-9]{2} receipt=(?:ok|refused) evidence=(?:ok|refused)"
                                  r"|FAIL instant-disagree [0-9]{2}|FAIL check-error)\Z")

    def test_c6_fixture(self):
        # The two shared accepted forms must pass without consulting the default matrix.
        code, lines = self.invoke((UTC, NEGATIVE_OFFSET))
        self.assertEqual(code, 0)
        self.assertEqual(lines, [
            "instant 01 receipt=ok evidence=ok",
            "instant 02 receipt=ok evidence=ok",
            PASS,
        ])

    def test_c7_live_pins(self):
        # The untouched readers can drift independently; pin the measured CLI findings.
        result = self.cli()
        self.assertEqual(result.returncode, 1)
        lines = result.stdout.splitlines()
        self.assertEqual(lines[-1], FAIL)
        instants = [line for line in lines if line.startswith("instant ")]
        self.assertEqual(len(instants), 12)
        self.assertEqual(instants[1], "instant 02 receipt=ok evidence=refused")
        self.assertEqual(instants[8], "instant 09 receipt=refused evidence=refused")
        self.assertEqual([line for line in lines[:-1] if line.startswith("FAIL ")], [
            "FAIL instant-disagree 02",
            "FAIL instant-disagree 04",
            "FAIL instant-disagree 06",
            "FAIL instant-disagree 07",
            "FAIL instant-disagree 08",
            "FAIL instant-disagree 10",
        ])
