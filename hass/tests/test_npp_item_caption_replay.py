"""Contract tests for the offline caption replay, not for live NPP jobs."""

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
SCRIPT = ROOT / "scripts/hass/npp_item_caption_replay.py"
PASS = "PASS npp_item_caption_replay"
FAIL = "FAIL npp_item_caption_replay"


class NppItemCaptionReplayTests(unittest.TestCase):
    def setUp(self):
        temp = TemporaryDirectory(dir=ROOT)
        self.addCleanup(temp.cleanup)
        self.cwd = Path(temp.name)
        spec = importlib.util.spec_from_file_location("npp_item_caption_replay", SCRIPT)
        assert spec is not None and spec.loader is not None
        self.replay = importlib.util.module_from_spec(spec)
        with patch.object(sys, "path", sys.path.copy()):
            spec.loader.exec_module(self.replay)

    def invoke_main(self, *captions):
        stdout, stderr = io.StringIO(), io.StringIO()
        with (patch.object(self.replay, "CAPTIONS", captions),
              redirect_stdout(stdout), redirect_stderr(stderr)):
            code = self.replay.main([])
        self.assertEqual(stderr.getvalue(), "")
        return code, stdout.getvalue().splitlines()

    def invoke_cli(self, *args):
        return subprocess.run(
            [sys.executable, "-B", str(SCRIPT), *args], cwd=self.cwd,
            capture_output=True, text=True, timeout=10,
        )

    def test_c1_full_pass(self):
        # A caption without a named item or price is not a loss or a run failure.
        code, lines = self.invoke_main("hello")
        self.assertEqual(code, 0)
        self.assertEqual(lines[-1], PASS)

    def test_c2_findings_trailer(self):
        # The CLI must forward main's failing status and end on the summary, not a row.
        result = self.invoke_cli()
        self.assertEqual(result.returncode, 1)
        self.assertEqual(result.stdout.splitlines()[-1], FAIL)

    def test_c2_1_item_lost(self):
        # Interleave a clean case so renumbered, omitted or duplicate losses fail.
        code, lines = self.invoke_main(
            "item: honey. $4 each", "it's honey", "it's honey selling $4 each",
        )
        self.assertEqual(code, 1)
        self.assertEqual(lines, [
            "caption 01 raw-item=yes item=no price=no",
            "FAIL item-lost 01",
            "caption 02 raw-item=yes item=yes price=no",
            "caption 03 raw-item=yes item=no price=no",
            "FAIL item-lost 03",
            FAIL,
        ])

    def test_c2_2_check_error(self):
        # Don't leak the exception, count it as a loss, or abandon subsequent rows.
        finance = self.replay.private_numbers.finance
        with patch.object(self.replay.private_numbers, "finance", side_effect=[
            ValueError("synthetic private exception text"), finance("it's honey"),
        ]):
            code, lines = self.invoke_main("it's honey selling $4 each", "it's honey")
        self.assertEqual(code, 1)
        self.assertEqual(lines, ["FAIL check-error", "caption 02 raw-item=yes item=yes price=no", FAIL])

    def test_c3_usage_exit_2(self):
        # Don't silently accept a positional, an option, or argparse's special flags.
        for arg in ("fixture", "--unknown", "--help", "-h", "--"):
            with self.subTest(arg=arg):
                result = self.invoke_cli(arg)
                self.assertEqual(result.returncode, 2)
                self.assertEqual(result.stdout, "")  # No last stdout line on usage errors.
                self.assertTrue(result.stderr.startswith("usage: "), result.stderr)

    def test_c4_read_only(self):
        # Catch sidecars or rewrites in either tree, and writes relative to the caller.
        def snapshot():
            entries = {}
            for tree in (ROOT / "hass", ROOT / "storefront-mockup", self.cwd):
                for path in (tree, *tree.rglob("*")):
                    stat = path.lstat()
                    entries[path] = (stat.st_size, stat.st_mtime_ns)
            return entries

        before = snapshot()
        result = self.invoke_cli()
        self.assertEqual(result.returncode, 1)
        self.assertEqual(result.stdout.splitlines()[-1], FAIL)
        self.assertEqual(snapshot(), before)

    def test_c5_output_shape(self):
        # Reject debug banners, raw or parsed text, and unexpected stderr.
        result = self.invoke_cli()
        self.assertEqual(result.returncode, 1)
        self.assertEqual(result.stderr, "")
        lines = result.stdout.splitlines()
        self.assertEqual(lines[-1], FAIL)
        for line in lines[:-1]:
            self.assertRegex(line, r"^(caption [0-9]{2} raw-item=(yes|no) "
                             r"item=(yes|no) price=(yes|no)|FAIL (item-lost [0-9]{2}|check-error))$")

    def test_c6_fixture(self):
        # The fixture distinguishes an absent price from a readable price with a retained item.
        code, lines = self.invoke_main("it's honey", "it's honey, selling $4 each")
        self.assertEqual(code, 0)
        self.assertEqual(lines, [
            "caption 01 raw-item=yes item=yes price=no",
            "caption 02 raw-item=yes item=yes price=yes",
            PASS,
        ])

    def test_c7_live_pins(self):
        # Catch dropped/reordered rows and treating an item gained after parsing as a loss.
        result = self.invoke_cli()
        self.assertEqual(result.returncode, 1)
        lines = result.stdout.splitlines()
        self.assertEqual(lines[-1], FAIL)
        rows = [line for line in lines if line.startswith("caption ")]
        self.assertEqual([line.split()[1] for line in rows], [f"{i:02d}" for i in range(1, 13)])
        self.assertEqual(rows[2], "caption 03 raw-item=yes item=no price=no")
        self.assertEqual(rows[3], "caption 04 raw-item=no item=yes price=yes")
        self.assertEqual([line for line in lines[:-1] if line.startswith("FAIL ")], [
            "FAIL item-lost 03", "FAIL item-lost 06", "FAIL item-lost 12",
        ])
