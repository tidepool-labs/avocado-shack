"""Offline CLI contract tests for the frozen-picture drift guard."""

from contextlib import redirect_stderr, redirect_stdout
import importlib.util
import io
from pathlib import Path
import subprocess
import sys
from tempfile import TemporaryDirectory
import unittest
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[2]
SCRIPT = ROOT / "scripts/hass/npp_frozen_picture_match.py"
PASS = "PASS npp_frozen_picture_match"
FAIL = "FAIL npp_frozen_picture_match"
LIVE_LINES = [
    "case 0 match=yes note='picture: your own photo'",
    "case 1 match=yes note='picture: house style'",
    "case 2 match=yes note=''",
    "case 3 match=no note='picture: your own photo'",
    "case 4 match=no note='picture: your own photo'",
    "case 5 match=no note='picture: your own photo'",
    "case 6 match=no note='picture: your own photo'",
    "case 7 match=no note='picture: your own photo'",
    "case 8 match=no note=''",
]
NOTE_CHANGES = [f"FAIL match-changed {i}" for i in (0, 1, 3, 4, 5, 6, 7)]


def snapshot():
    entries = {}
    for name in ("hass", "storefront-mockup"):
        tree = ROOT / name
        for path in (tree, *tree.rglob("*")):
            info = path.lstat()
            entries[path.relative_to(ROOT)] = (info.st_size, info.st_mtime_ns)
    return entries


class FrozenPictureMatchTests(unittest.TestCase):
    def shell_run(self, *args):
        with TemporaryDirectory() as cwd:
            return subprocess.run(
                [sys.executable, "-B", str(SCRIPT), *args], cwd=cwd,
                capture_output=True, text=True, timeout=30, check=False,
            )

    def load_tool(self):
        spec = importlib.util.spec_from_file_location("npp_frozen_picture_match", SCRIPT)
        assert spec is not None and spec.loader is not None
        tool = importlib.util.module_from_spec(spec)
        with patch.object(sys, "path", sys.path.copy()):
            spec.loader.exec_module(tool)
        return tool

    def run_tool(self, tool, status, trailer):
        out, err = io.StringIO(), io.StringIO()
        with redirect_stdout(out), redirect_stderr(err):
            self.assertEqual(tool.main([]), status)
        self.assertEqual(err.getvalue(), "")
        lines = out.getvalue().splitlines()
        self.assertEqual(lines[-1], trailer)
        return lines[:-1]

    def assert_cli_pass(self, result):
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(result.stderr, "")
        lines = result.stdout.splitlines()
        self.assertEqual(lines[-1], PASS)
        return lines[:-1]

    def test_c1_full_pass(self):
        # A clean CLI run must not return a failure or omit the final receipt.
        self.assert_cli_pass(self.shell_run())

    def test_c2_findings_trailer(self):
        # Rejecting even exact matches must not leave a passing trailer or status.
        tool = self.load_tool()
        with patch.object(tool.picture.FrozenPicture, "matches_draft", return_value=False):
            lines = self.run_tool(tool, 1, FAIL)
        self.assertEqual([line for line in lines if line.startswith("FAIL ")], [
            "FAIL match-changed 0", "FAIL match-changed 1", "FAIL match-changed 2",
        ])

    def test_c2_1_match_on_other_bytes(self):
        # A path-only implementation accepts malformed/wrong digests at that path.
        def path_only(frozen, draft):
            return frozen.image_path in draft.get("assets", {})

        tool = self.load_tool()
        with patch.object(tool.picture.FrozenPicture, "matches_draft", path_only):
            lines = self.run_tool(tool, 1, FAIL)
        self.assertEqual([line for line in lines if line.startswith("FAIL ")], [
            "FAIL match-on-other-bytes 3", "FAIL match-changed 3",
            "FAIL match-on-other-bytes 4", "FAIL match-changed 4",
            "FAIL match-on-other-bytes 7", "FAIL match-changed 7",
            "FAIL match-on-other-bytes 8", "FAIL match-changed 8",
        ])

    def test_c2_2_match_changed(self):
        # Comparing just the match result would miss changed display notes.
        tool = self.load_tool()
        with patch.object(tool.picture, "_NOTES", {}):
            lines = self.run_tool(tool, 1, FAIL)
        self.assertEqual([line for line in lines if line.startswith("FAIL ")], NOTE_CHANGES)

    def test_c2_3_check_error(self):
        # A repo exception must not leak details, abort later cases, or pass.
        tool = self.load_tool()
        original = tool.picture.FrozenPicture.matches_draft

        def fail_house(frozen, draft):
            if frozen.variant == "house":
                raise RuntimeError("fixture error detail")
            return original(frozen, draft)

        with patch.object(tool.picture.FrozenPicture, "matches_draft", fail_house):
            lines = self.run_tool(tool, 1, FAIL)
        self.assertEqual(lines, [LIVE_LINES[0], "FAIL check-error", *LIVE_LINES[2:]])

    def test_c3_usage_exit_2(self):
        # Ignored tokens or implicit help would bypass the no-argument contract.
        for arg in ("fixture", "--unknown", "--help", "-h", "--"):
            with self.subTest(arg=arg):
                result = self.shell_run(arg)
                self.assertEqual(result.returncode, 2)
                self.assertEqual(result.stdout, "")
                self.assertTrue(result.stderr.startswith("usage: "))
                self.assertEqual(result.stderr.splitlines()[-1],
                                 f"npp_frozen_picture_match.py: error: unrecognized arguments: {arg}")

    def test_c4_read_only(self):
        # A future report file or asset write would change a tree snapshot.
        before = snapshot()
        self.assert_cli_pass(self.shell_run())
        self.assertEqual(snapshot(), before)

    def test_c5_output_shape(self):
        # Debug output or an unlisted finding must not become part of the protocol.
        for line in self.assert_cli_pass(self.shell_run()):
            self.assertRegex(line, r"^case [0-8] match=(yes|no) note='[^']*'$")
        tool = self.load_tool()
        with patch.object(tool.picture.FrozenPicture, "matches_draft", return_value=True):
            lines = self.run_tool(tool, 1, FAIL)
        for line in lines:
            self.assertRegex(line, r"^(?:case [0-8] match=(yes|no) note='[^']*'|"
                                   r"FAIL (match-on-other-bytes|match-changed) [0-8])$")

    def test_c6_fixture(self):
        # Hardcoded notes would survive clearing the repo's note map.
        tool = self.load_tool()
        with patch.object(tool.picture, "_NOTES", {}):
            lines = self.run_tool(tool, 1, FAIL)
        expected = []
        for i in range(9):
            expected.append(f"case {i} match={'yes' if i < 3 else 'no'} note=''")
            finding = f"FAIL match-changed {i}"
            if finding in NOTE_CHANGES:
                expected.append(finding)
        self.assertEqual(lines, expected)

    def test_c7_live_pins(self):
        # Normalizing a digest or changing note text must break the measured pins.
        self.assertEqual(self.assert_cli_pass(self.shell_run()), LIVE_LINES)
