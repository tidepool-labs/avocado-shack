"""Behavioral checks for the offline unread-edit diagnostic."""

from contextlib import redirect_stderr, redirect_stdout
import importlib.util
import io
from pathlib import Path
import re
import subprocess
import sys
from tempfile import TemporaryDirectory
import unittest
from unittest.mock import patch

from hass.npp import edits, reply

ROOT = Path(__file__).resolve().parents[2]
SCRIPT = ROOT / "scripts/hass/npp_unread_edit_blocks.py"
PASS = "PASS npp_unread_edit_blocks"
FAIL = "FAIL npp_unread_edit_blocks"


def snapshot():
    result = {}
    for name in ("hass", "storefront-mockup"):
        root = ROOT / name
        for path in (root, *root.rglob("*")):
            stat = path.lstat()
            result[path.relative_to(ROOT)] = (stat.st_size, stat.st_mtime_ns)
    return result


class UnreadEditBlocksTests(unittest.TestCase):
    def setUp(self):
        self.cwd = self.enterContext(TemporaryDirectory())
        spec = importlib.util.spec_from_file_location(SCRIPT.stem, SCRIPT)
        assert spec is not None and spec.loader is not None
        self.tool = importlib.util.module_from_spec(spec)
        with patch.object(sys, "path", sys.path.copy()):
            spec.loader.exec_module(self.tool)

    def cli(self, *args):
        return subprocess.run(
            [sys.executable, "-B", str(SCRIPT), *args], cwd=self.cwd,
            capture_output=True, text=True, timeout=10,
        )

    def run_main(self):
        stdout, stderr = io.StringIO(), io.StringIO()
        with redirect_stdout(stdout), redirect_stderr(stderr):
            code = self.tool.main([])
        return code, stdout.getvalue().splitlines(), stderr.getvalue()

    def assert_outcome(self, result, code, trailer):
        actual_code, lines, stderr = result
        self.assertEqual(actual_code, code, stderr)
        self.assertEqual(stderr, "")
        self.assertTrue(lines)
        self.assertEqual(lines[-1], trailer)
        return lines

    def run_without_earlier_unclear(self):
        real_edit, real_read = reply.Stages.edit, edits.read

        def edit(stages, work):
            last = work.request["texts"][-1]

            def read(grammar, text, finance, mapper=None):
                parsed = real_read(grammar, text, finance, mapper)
                if text != last and parsed.ask == "ask_edit_unclear":
                    return edits.Edit()
                return parsed

            with patch.object(edits, "read", side_effect=read):
                return real_edit(stages, work)

        with patch.object(reply.Stages, "edit", autospec=True, side_effect=edit):
            return self.run_main()

    def test_c1_full_pass(self):
        # An informational question alone must not turn a clean run red.
        lines = self.assert_outcome(self.run_without_earlier_unclear(), 0, PASS)
        self.assertFalse(any(line.startswith("FAIL ") for line in lines))

    def test_c2_findings_trailer(self):
        # Do not stop at the first finding or print the trailer before later cases.
        lines = self.assert_outcome(self.run_main(), 1, FAIL)
        self.assertEqual(lines.count(FAIL), 1)
        self.assertLess(lines.index("FAIL blocked 2"), lines.index("case 3 question=ask_edit_unclear"))
        self.assertLess(lines.index("FAIL blocked 3"), lines.index("case 4 question=ask_edit_unclear"))

    def test_c2_1_blocked(self):
        # Change only a standalone parse. The stage still asks in case 3, but
        # the finding must disappear if its final text cannot patch on its own.
        real_read = edits.read

        def read(grammar, text, finance, mapper=None):
            parsed = real_read(grammar, text, finance, mapper)
            if not finance and text == "put it in dairy":
                self.assertTrue(parsed.patch)
                return edits.Edit()
            return parsed

        with patch.object(edits, "read", side_effect=read) as observed:
            lines = self.assert_outcome(self.run_main(), 1, FAIL)
        self.assertTrue(any(call.args[1:3] == ("put it in dairy", {}) for call in observed.call_args_list))
        self.assertIn("case 3 question=ask_edit_unclear", lines)
        self.assertEqual([line for line in lines[:-1] if line.startswith("FAIL ")], ["FAIL blocked 2"])

    def test_c2_2_check_error(self):
        # A loader error must not be skipped, leaked, or reported as a clean run.
        with patch("hass.npp.assets", side_effect=RuntimeError("synthetic detail")) as assets:
            lines = self.assert_outcome(self.run_main(), 1, FAIL)
        assets.assert_called_once_with()
        self.assertEqual(lines, ["FAIL check-error", FAIL])

    def test_c3_usage_exit_2(self):
        # No options (including default argparse help) bypass the no-argument contract.
        for arg in ("unexpected", "--unknown", "--help", "--"):
            with self.subTest(arg=arg):
                result = self.cli(arg)
                self.assertEqual(result.returncode, 2)
                self.assertEqual(result.stdout, "")
                self.assertIn("usage:", result.stderr)
                self.assertIn("error: unrecognized arguments:", result.stderr.splitlines()[-1])

    def test_c4_read_only(self):
        # Catch accidental writes to either repo tree, including import caches.
        before = snapshot()
        result = self.cli()
        self.assert_outcome((result.returncode, result.stdout.splitlines(), result.stderr), 1, FAIL)
        self.assertEqual(snapshot(), before)

    def test_c5_output_shape(self):
        # Stray debug or human-readable reply text would violate the line protocol.
        result = self.cli()
        lines = self.assert_outcome((result.returncode, result.stdout.splitlines(), result.stderr), 1, FAIL)
        allowed = re.compile(r"case [0-4] (?:patch=(?:\w+(?:,\w+)*)?|question=\w+)"
                             r"|FAIL (?:blocked [0-4]|check-error)")
        for line in lines[:-1]:
            self.assertIsNotNone(allowed.fullmatch(line), line)

    def test_c6_fixture(self):
        # Ignoring earlier unclear text must retain later patches in order and
        # must not also swallow the unclear final text in cases 1 and 4.
        lines = self.assert_outcome(self.run_without_earlier_unclear(), 0, PASS)
        self.assertEqual(lines, [
            "case 0 patch=name",
            "case 1 question=ask_edit_unclear",
            "case 2 patch=name",
            "case 3 patch=name,category",
            "case 4 question=ask_edit_unclear",
            PASS,
        ])

    def test_c7_live_pins(self):
        # Pin the measured baseline so a change in the real replay is visible.
        lines = self.assert_outcome(self.run_main(), 1, FAIL)
        self.assertEqual(lines, [
            "case 0 patch=name",
            "case 1 question=ask_edit_unclear",
            "case 2 question=ask_edit_unclear",
            "FAIL blocked 2",
            "case 3 question=ask_edit_unclear",
            "FAIL blocked 3",
            "case 4 question=ask_edit_unclear",
            FAIL,
        ])
