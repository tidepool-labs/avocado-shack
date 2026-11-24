"""Offline contract tests for the NPP approval prompt round-trip checker."""

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


ROOT = Path(__file__).resolve().parents[2]
SCRIPT = ROOT / "scripts/hass/npp_ready_reply_round_trip.py"
PASS = "PASS npp_ready_reply_round_trip"
FAIL = "FAIL npp_ready_reply_round_trip"
VERSIONS = (1, 2, 9, 123456789)
FIXTURE_YES = re.compile(r"yes ([0-9a-f]{4,12})-([1-9][0-9]{0,8})", re.I)


def template(ready):
    return (None, None, {
        "prompts": {"ready": ready},
        "brackets": {"compose": {"drop_order": [], "separator": "; "}, "parts": {}},
        "caps": {"bracket_max_chars": 1},
    })


def snapshot():
    tree = {}
    for directory in (ROOT / "hass", ROOT / "storefront-mockup"):
        for path in (directory, *directory.rglob("*")):
            stat = path.lstat()
            tree[path.relative_to(ROOT)] = (stat.st_size, stat.st_mtime_ns)
    return tree


class NppReadyReplyRoundTripTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        spec = importlib.util.spec_from_file_location(SCRIPT.stem, SCRIPT)
        assert spec is not None and spec.loader is not None
        cls.tool = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(cls.tool)

    def run_cli(self, *args):
        with TemporaryDirectory() as cwd:
            return subprocess.run([sys.executable, "-B", str(SCRIPT), *args], cwd=cwd,
                                  capture_output=True, text=True, timeout=15)

    def assert_run(self, status, *lines):
        stdout, stderr = io.StringIO(), io.StringIO()
        with redirect_stdout(stdout), redirect_stderr(stderr):
            result = self.tool.main([])
        self.assertEqual(result, status)
        self.assertEqual(stdout.getvalue(), "\n".join(lines) + "\n")
        self.assertEqual(stderr.getvalue(), "")

    def test_c1_full_pass(self):
        # The script must import from its own checkout, even outside the repo cwd.
        result = self.run_cli()
        self.assertEqual(result.returncode, 0)
        self.assertEqual(result.stdout.splitlines()[-1], PASS)
        self.assertEqual(result.stderr, "")

    def test_c2_findings_trailer(self):
        # One code width can be refused while the other eight checks still pass.
        with patch.object(self.tool.npp, "assets", return_value=template("Reply yes {code}-{n}")), \
             patch.object(self.tool.job, "YES", re.compile(r"yes ([0-9a-f]{6,12})-([0-9]+)")):
            self.assert_run(1, *(f"FAIL reply-refused 1 {v}" for v in VERSIONS), "prompts 12", FAIL)

    def test_c2_1_assets_unreadable(self):
        # Asset-load failures must not leak the loader's exception details.
        with patch.object(self.tool.npp, "assets", side_effect=OSError("fixture detail")):
            self.assert_run(1, "FAIL assets-unreadable", FAIL)

    def test_c2_2_reply_missing(self):
        # A changed instruction verb must report every missing reply in matrix order.
        with patch.object(self.tool.npp, "assets", return_value=template("Reply ok {code}-{n}")):
            self.assert_run(1, *(f"FAIL reply-missing {c} {v}" for c in (1, 2, 3) for v in VERSIONS),
                            "prompts 12", FAIL)

    def test_c2_3_reply_refused(self):
        # A successful regex match is not enough if either captured value is wrong.
        for ready in ("Reply yes feed-{n}", "Reply yes {code}-3"):
            with self.subTest(ready=ready), \
                 patch.object(self.tool.npp, "assets", return_value=template(ready)), \
                 patch.object(self.tool.job, "YES", FIXTURE_YES):
                self.assert_run(1, *(f"FAIL reply-refused {c} {v}" for c in (1, 2, 3) for v in VERSIONS),
                                "prompts 12", FAIL)

    def test_c2_4_check_error(self):
        # A render exception must fail closed, without a traceback or partial pass.
        with patch.object(self.tool.npp, "assets", return_value=template("Reply yes {code}-{n}")), \
             patch.object(self.tool.reply, "ready_line", side_effect=ValueError("fixture detail")):
            self.assert_run(1, "FAIL check-error", FAIL)

    def test_c3_usage_exit_2(self):
        # No options (even implicit help) or positional values are admitted.
        for arg in ("--unknown", "value", "--help", "-h", "--"):
            with self.subTest(arg=arg):
                result = self.run_cli(arg)
                self.assertEqual(result.returncode, 2)
                self.assertEqual(result.stdout, "")
                self.assertIn("error: unrecognized arguments:", result.stderr.splitlines()[-1])

    def test_c4_read_only(self):
        # Detect generated files and in-place changes in either repo tree.
        before = snapshot()
        result = self.run_cli()
        self.assertEqual(result.returncode, 0)
        self.assertEqual(result.stdout.splitlines()[-1], PASS)
        self.assertEqual(snapshot(), before)

    def test_c5_output_shape(self):
        # Mixed failures must remain ordered and never echo the prompt. A later
        # correct instruction must not rescue an incorrect first instruction.
        assets = template("Reply yes {code}-{n}")
        ready_line = self.tool.reply.ready_line

        def render(replies, code, version):
            if code == "4ed1" and version == 1:
                return "fixture without an instruction"
            prompt = ready_line(replies, code, version)
            return f"yes feed-2; {prompt}" if code == "4ed1" and version == 2 else prompt

        with patch.object(self.tool.npp, "assets", return_value=assets), \
             patch.object(self.tool.job, "YES", FIXTURE_YES), \
             patch.object(self.tool.reply, "ready_line", side_effect=render):
            self.assert_run(1, "FAIL reply-missing 1 1", "FAIL reply-refused 1 2", "prompts 12", FAIL)

    def test_c6_fixture_pass(self):
        # The parser that requires a version still accepts all synthetic instructions.
        with patch.object(self.tool.npp, "assets", return_value=template("Reply yes {code}-{n}")), \
             patch.object(self.tool.job, "YES", FIXTURE_YES):
            self.assert_run(0, "prompts 12", PASS)

    def test_c7_live_pins(self):
        # Unlike the fixtures, this catches drift in the repo's actual pins or parser.
        self.assert_run(0, "prompts 12", PASS)


if __name__ == "__main__":
    unittest.main()
