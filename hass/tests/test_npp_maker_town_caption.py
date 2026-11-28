"""Offline CLI contract for the maker-and-town caption check."""

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
SCRIPT = ROOT / "scripts/hass/npp_maker_town_caption.py"
PASS = "PASS npp_maker_town_caption"
FAIL = "FAIL npp_maker_town_caption"
CLEAN = "made by Etto Farm; based in Arroyo Grande"
DIRTY = "made by Etto Farm based in Arroyo Grande"


def tree_snapshot():
    snapshot = {}
    for name in ("hass", "storefront-mockup"):
        tree = ROOT / name
        for path in (tree, *tree.rglob("*")):
            info = path.lstat()
            snapshot[path.relative_to(ROOT)] = (info.st_size, info.st_mtime_ns)
    return snapshot


class MakerTownCaptionTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        spec = importlib.util.spec_from_file_location("npp_maker_town_caption", SCRIPT)
        assert spec is not None and spec.loader is not None
        cls.tool = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(cls.tool)

    def run_cli(self, *args):
        with TemporaryDirectory(dir=ROOT) as tmp:
            return subprocess.run(
                [sys.executable, "-B", str(SCRIPT), *args], cwd=tmp,
                capture_output=True, text=True, timeout=10,
            )

    def run_main(self, captions, code, trailer):
        stdout, stderr = io.StringIO(), io.StringIO()
        with patch.object(self.tool, "CAPTIONS", captions), redirect_stdout(stdout), redirect_stderr(stderr):
            self.assertEqual(self.tool.main([]), code)
        self.assertEqual(stderr.getvalue(), "")
        lines = stdout.getvalue().splitlines()
        self.assertEqual(lines[-1:], [trailer])
        return lines

    def assert_cli_findings(self, result):
        self.assertEqual(result.returncode, 1)
        lines = result.stdout.splitlines()
        self.assertEqual(lines[-1:], [FAIL])
        return lines

    def test_c1_full_pass(self):
        # An informational missing town or S10 ask must not make the run fail.
        self.run_main(("made by Etto Farm, Arroyo Grande", CLEAN), 0, PASS)

    def test_c2_findings_trailer(self):
        # A later good caption must not reset a previously recorded failure.
        self.run_main((DIRTY, CLEAN), 1, FAIL)

    def test_c2_1_caption_findings(self):
        # One caption can have all three findings; a folded town match is not a fourth.
        returns = [
            self.tool.edits.Edit(patch=(("maker", "Other Maker"), ("makerTown", "Other Town"))),
            self.tool.edits.Edit(patch=(("maker", "etto farm"), ("makerTown", "arroyo grande"))),
        ]
        with patch.object(self.tool.edits, "read", side_effect=returns):
            lines = self.run_main((DIRTY, CLEAN), 1, FAIL)
        self.assertEqual(lines, [
            "caption 01 s3-maker=other s3-town=no s10-maker=other s10-town=other",
            "FAIL s3-maker 01", "FAIL s10-maker 01", "FAIL s10-town 01",
            "caption 02 s3-maker=exact s3-town=yes s10-maker=exact s10-town=exact",
            FAIL,
        ])

    def test_c2_2_check_error(self):
        # Every check boundary must fail closed without leaking exception text.
        for module, name in (
            (self.tool.private_numbers, "finance"), (self.tool.missing, "_owner_maker"),
            (self.tool.stages, "_site_words"), (self.tool.edits, "read"),
        ):
            with self.subTest(check=name), patch.object(module, name, side_effect=ValueError("hidden detail")):
                self.assertEqual(self.run_main((CLEAN,), 1, FAIL), ["FAIL check-error", FAIL])

    def test_c3_usage_exit_2(self):
        # The tool takes no arguments, including the usual help flags.
        for arg in ("caption", "--unknown", "--help", "-h", "--"):
            with self.subTest(arg=arg):
                result = self.run_cli(arg)
                self.assertEqual(result.returncode, 2)
                self.assertEqual(result.stdout, "")
                self.assertIn("usage:", result.stderr)
                self.assertTrue(result.stderr.splitlines()[-1].endswith(f"unrecognized arguments: {arg}"))

    def test_c4_read_only(self):
        # Catch added artifacts or writes to the inspected trees despite a valid report.
        before = tree_snapshot()
        self.assert_cli_findings(self.run_cli())
        self.assertEqual(tree_snapshot(), before)

    def test_c5_output_shape(self):
        # Raw input, parser diagnostics, or extra blank lines aren't allowed in a report.
        result = self.run_cli()
        lines = self.assert_cli_findings(result)
        self.assertEqual(result.stderr, "")
        for line in lines[:-1]:
            self.assertRegex(line, r"\A(?:caption [0-9]{2} s3-maker=(?:exact|other|none) "
                             r"s3-town=(?:yes|no) s10-maker=(?:exact|other|ask) "
                             r"s10-town=(?:exact|other|none)|"
                             r"FAIL (?:(?:s3-maker|s10-maker|s10-town) [0-9]{2}|check-error))\Z")

    def test_c6_fixture(self):
        # Explicitly pin the semicolon control: S3 separates both fields, S10 asks.
        self.assertEqual(self.run_main((CLEAN,), 0, PASS), [
            "caption 01 s3-maker=exact s3-town=yes s10-maker=ask s10-town=none", PASS,
        ])

    def test_c7_live_pins(self):
        # Catch drift in the merged readers or the order/coverage of the caption matrix.
        lines = self.assert_cli_findings(self.run_cli())
        captions = [line for line in lines if line.startswith("caption ")]
        self.assertEqual([line.split()[1] for line in captions], [f"{n:02d}" for n in range(1, 11)])
        self.assertEqual(captions[2], "caption 03 s3-maker=other s3-town=no s10-maker=other s10-town=none")
        self.assertEqual(captions[5], "caption 06 s3-maker=none s3-town=no s10-maker=other s10-town=none")
        self.assertEqual([line for line in lines[:-1] if line.startswith("FAIL ")], [
            "FAIL s3-maker 03", "FAIL s10-maker 03", "FAIL s3-maker 04", "FAIL s10-maker 04",
            "FAIL s3-maker 05", "FAIL s10-maker 05", "FAIL s3-maker 06", "FAIL s10-maker 06",
            "FAIL s3-maker 10", "FAIL s10-maker 10",
        ])
