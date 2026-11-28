"""Offline CLI contract for the NPP edit wording reach check."""

from contextlib import redirect_stderr, redirect_stdout
import importlib.util
import io
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import patch

from hass import npp


ROOT = Path(__file__).resolve().parents[2]
SCRIPT = ROOT / "scripts/hass/npp_edit_wording_reach.py"
PASS = "PASS npp_edit_wording_reach"
FAIL = "FAIL npp_edit_wording_reach"


def snapshot(root):
    entries = {}
    for path in (root, *root.rglob("*")):
        info = path.lstat()
        entries[path.relative_to(root)] = (info.st_size, info.st_mtime_ns)
    return entries


class NppEditWordingReachTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        spec = importlib.util.spec_from_file_location("npp_edit_wording_reach", SCRIPT)
        assert spec is not None and spec.loader is not None
        cls.tool = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(cls.tool)

    def setUp(self):
        work = tempfile.TemporaryDirectory()
        self.addCleanup(work.cleanup)
        self.work = Path(work.name)

    def invoke(self, *args):
        return subprocess.run(
            [sys.executable, "-B", str(SCRIPT), *args], cwd=self.work,
            capture_output=True, text=True, timeout=10,
        )

    def main_output(self):
        stdout, stderr = io.StringIO(), io.StringIO()
        with redirect_stdout(stdout), redirect_stderr(stderr):
            status = self.tool.main([])
        self.assertEqual(stderr.getvalue(), "")
        return status, stdout.getvalue().splitlines()

    def test_c1_full_pass(self):
        # A routed wording marked model is informational, not a failure.
        with patch.object(self.tool, "PHRASES", ("change the name to Wildflower honey",)):
            status, lines = self.main_output()
        self.assertEqual(status, 0)
        self.assertEqual(lines, ["edit 01 routed=yes reading=model", PASS])

    def test_c2_findings_trailer(self):
        # A later successful row must not reset the failure or replace the trailer.
        with patch.object(self.tool, "PHRASES", ("new photo", "from Etto")):
            status, lines = self.main_output()
        self.assertEqual(status, 1)
        self.assertEqual(lines[-1], FAIL)
        self.assertIn("edit 02 routed=yes reading=form", lines[:-1])

    def test_c2_1_assets_unreadable(self):
        # Asset loader exceptions must not expose diagnostics or start the checks.
        with patch.object(npp, "assets", side_effect=ValueError("fixture-only detail")):
            status, lines = self.main_output()
        self.assertEqual(status, 1)
        self.assertEqual(lines, ["FAIL assets-unreadable", FAIL])

    def test_c2_2_edit_missed(self):
        # Do not stop on the first miss or number findings by failure count.
        with patch.object(self.tool, "PHRASES", ("from Etto", "new photo", "move it to pantry")):
            status, lines = self.main_output()
        self.assertEqual(status, 1)
        self.assertEqual(lines[-1], FAIL)
        self.assertEqual([line for line in lines[:-1] if line.startswith("FAIL")], [
            "FAIL edit-missed 02", "FAIL edit-missed 03",
        ])

    def test_c3_usage_exit_2(self):
        # No arguments are supported, including default argparse help switches.
        for argument in ("extra", "--unknown", "--help", "-h", "--"):
            with self.subTest(argument=argument):
                result = self.invoke(argument)
                self.assertEqual(result.returncode, 2)
                self.assertEqual(result.stdout, "")  # No last line on usage errors.
                self.assertIn("error: unrecognized arguments:", result.stderr)

    def test_c4_read_only(self):
        # A report cache or rewrite of the input trees would change the snapshot.
        roots = (ROOT / "hass", ROOT / "storefront-mockup", self.work)
        before = [snapshot(root) for root in roots]
        result = self.invoke()
        self.assertEqual(result.returncode, 1, result.stderr)
        self.assertEqual(result.stdout.splitlines()[-1], FAIL)
        self.assertEqual([snapshot(root) for root in roots], before)

    def test_c5_output_shape(self):
        # Keep prose, phrase text, and diagnostic stream noise out of the report.
        result = self.invoke()
        self.assertEqual(result.returncode, 1, result.stderr)
        self.assertEqual(result.stderr, "")
        lines = result.stdout.splitlines()
        self.assertEqual(lines[-1], FAIL)
        for line in lines[:-1]:
            self.assertRegex(line, r"\A(?:edit [0-9]{2} routed=(?:yes reading=(?:form|model)|no reading=missed)"
                                   r"|FAIL edit-missed [0-9]{2})\Z")

    def test_c6_fixture(self):
        # Passing input uses the injected corpus, not the live list or canned rows.
        with patch.object(self.tool, "PHRASES", ("call it Wildflower honey", "from Etto", "shelf: pantry")):
            status, lines = self.main_output()
        self.assertEqual(status, 0)
        self.assertEqual(lines, [
            "edit 01 routed=yes reading=form",
            "edit 02 routed=yes reading=form",
            "edit 03 routed=yes reading=form",
            PASS,
        ])

    def test_c7_live_pins(self):
        # Catch drift in the sample corpus, routing, or the real no-mapper read.
        result = self.invoke()
        self.assertEqual(result.returncode, 1, result.stderr)
        lines = result.stdout.splitlines()
        self.assertEqual(lines[-1], FAIL)
        rows = [line for line in lines[:-1] if line.startswith("edit ")]
        self.assertEqual(len(rows), 14)
        self.assertEqual(rows[1:3], ["edit 02 routed=yes reading=model", "edit 03 routed=no reading=missed"])
        self.assertEqual([line for line in lines[:-1] if line.startswith("FAIL")], [
            "FAIL edit-missed 03", "FAIL edit-missed 08", "FAIL edit-missed 12", "FAIL edit-missed 13",
        ])
