"""Offline CLI contract for the S3/S10 naming diagnostic."""

from contextlib import redirect_stderr, redirect_stdout
import importlib.util
from io import StringIO
from pathlib import Path
import subprocess
import sys
from tempfile import TemporaryDirectory
import unittest
from unittest.mock import patch


ROOT = Path(__file__).resolve().parents[2]
SCRIPT = ROOT / "scripts/hass/item_name_phrase_parity.py"
PASS = "PASS item_name_phrase_parity"
FAIL = "FAIL item_name_phrase_parity"


def snapshot():
    entries = {}
    for tree in (ROOT / "hass", ROOT / "storefront-mockup"):
        for path in (tree, *tree.rglob("*")):
            info = path.lstat()
            entries[path.relative_to(ROOT)] = (info.st_size, info.st_mtime_ns)
    return entries


class ItemNamePhraseParityTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        spec = importlib.util.spec_from_file_location("item_name_phrase_parity", SCRIPT)
        assert spec is not None and spec.loader is not None
        cls.tool = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(cls.tool)

    def invoke(self, phrases):
        stdout, stderr = StringIO(), StringIO()
        with patch.object(self.tool, "PHRASES", phrases), redirect_stdout(stdout), redirect_stderr(stderr):
            status = self.tool.main([])
        self.assertEqual(stderr.getvalue(), "")
        return status, stdout.getvalue().splitlines()

    def cli(self, *args):
        with TemporaryDirectory() as directory:
            return subprocess.run(
                [sys.executable, "-B", str(SCRIPT), *args], cwd=directory,
                capture_output=True, text=True, timeout=15,
            )

    def assert_result(self, status, lines, expected_status, trailer):
        self.assertEqual(status, expected_status)
        self.assertEqual(lines[-1:], [trailer])

    def test_c1_full_pass(self):
        # Both readers accepting is a pass, even if their clean captures differ.
        with patch.object(self.tool.job, "owner_item", return_value="clover honey"):
            status, lines = self.invoke(("name: honey",))
        self.assert_result(status, lines, 0, PASS)
        self.assertEqual(lines, ["name 01 s3=yes s10=yes", PASS])

    def test_c2_findings_trailer(self):
        # A later clean phrase must not reset the aggregate failure status.
        status, lines = self.invoke(("it's honey", "this is honey"))
        self.assert_result(status, lines, 1, FAIL)
        self.assertEqual(lines, ["name 01 s3=yes s10=no", "FAIL name-disagree 01",
                                 "name 02 s3=no s10=no", FAIL])

    def test_c2_1_assets_unreadable(self):
        # A failed read must not skip comparison and pass, or leak exception text.
        with patch("hass.npp.assets", side_effect=ValueError("synthetic asset detail")):
            status, lines = self.invoke(("this is honey",))
        self.assert_result(status, lines, 1, FAIL)
        self.assertEqual(lines, ["FAIL assets-unreadable", FAIL])

    def test_c2_2_name_disagree(self):
        # Catch one-sided XOR checks and treating a non-name edit as a name.
        status, lines = self.invoke(("it's honey", "call it honey", "from honey"))
        self.assert_result(status, lines, 1, FAIL)
        self.assertEqual(lines, ["name 01 s3=yes s10=no", "FAIL name-disagree 01",
                                 "name 02 s3=no s10=yes", "FAIL name-disagree 02",
                                 "name 03 s3=no s10=no", FAIL])

    def test_c2_3_name_lead_kept(self):
        # Check either capture, case, start and word boundary, with ordered findings.
        status, lines = self.invoke(("it's Called honey", "name: NAMED honey",
                                     "it's calledness honey", "name: honey named"))
        self.assert_result(status, lines, 1, FAIL)
        self.assertEqual(lines, [
            "name 01 s3=yes s10=no", "FAIL name-disagree 01", "FAIL name-lead-kept 01",
            "name 02 s3=no s10=yes", "FAIL name-disagree 02", "FAIL name-lead-kept 02",
            "name 03 s3=yes s10=no", "FAIL name-disagree 03",
            "name 04 s3=no s10=yes", "FAIL name-disagree 04", FAIL,
        ])
        # Two retained leads still make exactly one finding, even without disagreement.
        with patch.object(self.tool.job, "owner_item", return_value="called honey"):
            status, lines = self.invoke(("name: named honey",))
        self.assert_result(status, lines, 1, FAIL)
        self.assertEqual(lines, ["name 01 s3=yes s10=yes", "FAIL name-lead-kept 01", FAIL])

    def test_c3_usage_exit_2(self):
        # No argument can run the diagnostic, including implicit argparse flags.
        for arg in ("extra", "--unknown", "--help", "--"):
            with self.subTest(arg=arg):
                result = self.cli(arg)
                self.assertEqual(result.returncode, 2)
                self.assertEqual(result.stdout, "")  # No stdout trailer for usage errors.
                self.assertTrue(result.stderr.startswith("usage: "))
                self.assertIn("unrecognized arguments", result.stderr.splitlines()[-1])

    def test_c4_read_only(self):
        # Catch generated sidecars and rewrites, including same-size edits.
        before = snapshot()
        result = self.cli()
        self.assert_result(result.returncode, result.stdout.splitlines(), 1, FAIL)
        self.assertEqual(snapshot(), before)

    def test_c5_output_shape(self):
        # Raw words, parser traces, or additional diagnostics must not escape.
        result = self.cli()
        lines = result.stdout.splitlines()
        self.assert_result(result.returncode, lines, 1, FAIL)
        self.assertEqual(result.stderr, "")
        for line in lines[:-1]:
            self.assertRegex(line, r"\A(?:name [0-9]{2} s3=(?:yes|no) s10=(?:yes|no)|"
                                  r"FAIL (?:assets-unreadable|name-(?:disagree|lead-kept) [0-9]{2}))\Z")

    def test_c6_fixture(self):
        # A hard-coded matrix, or a requirement that at least one reader accepts, fails here.
        status, lines = self.invoke(("the name is honey", "this is honey"))
        self.assert_result(status, lines, 0, PASS)
        self.assertEqual(lines, ["name 01 s3=no s10=no", "name 02 s3=no s10=no", PASS])

    def test_c7_live_pins(self):
        # Detect drift in the real readers and ordering for the unpatched phrase matrix.
        result = self.cli()
        lines = result.stdout.splitlines()
        self.assert_result(result.returncode, lines, 1, FAIL)
        self.assertEqual([line for line in lines if line.startswith("name ")], [
            f"name {position:02d} s3={s3} s10={s10}"
            for position, (s3, s10) in enumerate(
                [("yes", "no")] * 6 + [("no", "yes")] * 3
                + [("no", "no")] * 3 + [("yes", "no")] + [("no", "no")] * 2,
                1,
            )
        ])
        self.assertEqual([line for line in lines[:-1] if line.startswith("FAIL ")], [
            *(f"FAIL name-disagree {position:02d}" for position in (*range(1, 10), 13)),
            "FAIL name-lead-kept 13",
        ])


if __name__ == "__main__":
    unittest.main()
