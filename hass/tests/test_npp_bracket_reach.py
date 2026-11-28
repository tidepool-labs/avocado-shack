"""Contract tests for the offline ready-prompt bracket report."""

from contextlib import redirect_stderr, redirect_stdout
import importlib.util
import io
import json
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import patch

from hass import npp

ROOT = Path(__file__).resolve().parents[2]
SCRIPT = ROOT / "scripts/hass/npp_bracket_reach.py"
MAKER = ("maker_left_off_label", "brand")
PASS = "PASS npp_bracket_reach"
FAIL = "FAIL npp_bracket_reach"
spec = importlib.util.spec_from_file_location("npp_bracket_reach", SCRIPT)
assert spec is not None and spec.loader is not None
reach = importlib.util.module_from_spec(spec)
spec.loader.exec_module(reach)


def snapshot(*trees):
    entries = {}
    for tree in trees:
        for path in (tree, *tree.rglob("*")):
            stat = path.lstat()
            entries[path] = (stat.st_size, stat.st_mtime_ns)
    return entries


class BracketReachTests(unittest.TestCase):
    def setUp(self):
        scratch = tempfile.TemporaryDirectory()
        self.addCleanup(scratch.cleanup)
        self.scratch = Path(scratch.name)

    def fixture_assets(self, parts, *, cap=10, brand=4):
        schema = self.scratch / "identify.schema.json"
        schema.write_text(json.dumps({"properties": {"brand_on_label": {"maxLength": brand}}}),
                          encoding="utf-8")
        replies = {
            "caps": {"bracket_max_chars": cap},
            "brackets": {
                "compose": {"drop_order": list(reversed(parts)), "separator": "; "},
                "parts": parts,
            },
        }
        return {}, {"hass-product-identify/identify.schema.json": schema.read_bytes()}, replies

    def invoke_main(self):
        stdout, stderr = io.StringIO(), io.StringIO()
        with redirect_stdout(stdout), redirect_stderr(stderr):
            code = reach.main([])
        return subprocess.CompletedProcess([], code, stdout.getvalue(), stderr.getvalue())

    def invoke_fixture(self, parts, **options):
        with patch.object(npp, "assets", return_value=self.fixture_assets(parts, **options)):
            return self.invoke_main()

    def invoke_cli(self, *args):
        return subprocess.run([sys.executable, "-B", str(SCRIPT), *args],
                              cwd=self.scratch, capture_output=True, text=True, timeout=15)

    def assert_report(self, result, code, last_line):
        self.assertEqual(result.returncode, code, result.stderr)
        self.assertEqual(result.stderr, "")
        lines = result.stdout.splitlines()
        self.assertTrue(lines)
        self.assertEqual(lines[-1], last_line)
        return lines

    def test_c1_full_pass(self):
        # A strict comparison or failing to parse escaped braces rejects this valid fixture.
        result = self.invoke_fixture({"made_fixed": "{{ok}}", MAKER[0]: "abc {brand}"})
        self.assertEqual(self.assert_report(result, 0, PASS), [
            "part made_fixed fixed chars=6",
            "part maker_left_off_label shown-max=4 source-max=4",
            PASS,
        ])

    def test_c2_findings_trailer(self):
        # Returning on the first finding loses the second; sorting changes file order.
        result = self.invoke_fixture({"z_fixed": "123456789", "a_new": "{unmapped}"})
        self.assertEqual(self.assert_report(result, 1, FAIL), [
            "part z_fixed fixed chars=9",
            "FAIL part-too-long z_fixed",
            "FAIL part-unmapped a_new",
            FAIL,
        ])

    def test_c2_1_assets_unreadable(self):
        # Don't leak the exception text or treat unreadable inputs as an empty pass.
        with patch.object(npp, "assets", side_effect=ValueError("not for stdout")):
            result = self.invoke_main()
        self.assertEqual(self.assert_report(result, 1, FAIL), ["FAIL assets-unreadable", FAIL])

    def test_c2_2_part_too_long(self):
        # The text fits the raw cap but the composed bracket needs two parentheses.
        result = self.invoke_fixture({"fixed": "1234567890"})
        self.assertEqual(self.assert_report(result, 1, FAIL), [
            "part fixed fixed chars=10", "FAIL part-too-long fixed", FAIL,
        ])

    def test_c2_3_part_unmapped(self):
        # A known part key is insufficient if its placeholder field changes.
        result = self.invoke_fixture({MAKER[0]: "{other}"})
        self.assertEqual(self.assert_report(result, 1, FAIL), [
            "FAIL part-unmapped maker_left_off_label", FAIL,
        ])

    def test_c2_4_part_unreachable(self):
        # Pin both search endpoints: no fitting value, and a real fit beyond 200.
        for cap, brand, shown in ((2, 1, 0), (204, 201, 200)):
            with self.subTest(cap=cap):
                result = self.invoke_fixture({MAKER[0]: "{brand}"}, cap=cap, brand=brand)
                self.assertEqual(self.assert_report(result, 1, FAIL), [
                    f"part maker_left_off_label shown-max={shown} source-max={brand}",
                    "FAIL part-unreachable maker_left_off_label",
                    FAIL,
                ])

    def test_c3_usage_exit_2(self):
        # No args are allowed, even the usual built-in argparse help switches.
        for arg in ("positional", "--unknown", "--help", "-h", "--"):
            with self.subTest(arg=arg):
                result = self.invoke_cli(arg)
                self.assertEqual(result.returncode, 2)
                self.assertEqual(result.stdout, "")
                self.assertEqual(result.stderr.splitlines()[-1],
                                 f"npp_bracket_reach.py: error: unrecognized arguments: {arg}")

    def test_c4_read_only(self):
        # Detect writes and new names in either tree or in the CLI working directory.
        trees = (ROOT / "hass", ROOT / "storefront-mockup", self.scratch)
        before = snapshot(*trees)
        self.assert_report(self.invoke_cli(), 1, FAIL)
        self.assertEqual(snapshot(*trees), before)

    def test_c5_output_shape(self):
        # Extra logging or raw template text is not a report line.
        lines = self.assert_report(self.invoke_cli(), 1, FAIL)
        for line in lines[:-1]:
            self.assertRegex(line, r"^(?:part \w+ (?:fixed chars=\d+|shown-max=\d+ source-max=\d+)"
                                   r"|FAIL (?:part-too-long|part-unmapped|part-unreachable) \w+"
                                   r"|FAIL assets-unreadable)$")

    def test_c6_fixture(self):
        # Patching only the source limit must not change the measured reply limit.
        with patch.dict(reach.SOURCES, {MAKER: 30}):
            lines = self.assert_report(self.invoke_main(), 0, PASS)
        self.assertIn("part maker_left_off_label shown-max=31 source-max=30", lines)

    def test_c7_live_pins(self):
        # Real checked-in assets: only the maker-label note has a reach gap.
        lines = self.assert_report(self.invoke_cli(), 1, FAIL)
        parts = [line for line in lines if line.startswith("part ")]
        self.assertEqual(len(parts), 7)
        self.assertIn("part maker_left_off fixed chars=41", parts)
        self.assertIn("part maker_left_off_label shown-max=31 source-max=60", parts)
        self.assertIn("part claim_left_off shown-max=48 source-max=40", parts)
        self.assertEqual([line for line in lines[:-1] if line.startswith("FAIL ")],
                         ["FAIL part-unreachable maker_left_off_label"])
