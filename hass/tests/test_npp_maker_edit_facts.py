"""CLI contract for the fixture-only maker edit facts check."""

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
SCRIPT = ROOT / "scripts/hass/npp_maker_edit_facts.py"
PASS = "PASS npp_maker_edit_facts"
FAIL = "FAIL npp_maker_edit_facts"


def tree_snapshot():
    entries = {}
    for tree in (ROOT / "hass", ROOT / "storefront-mockup"):
        for path in (tree, *tree.rglob("*")):
            info = path.lstat()
            entries[path.relative_to(ROOT)] = (info.st_size, info.st_mtime_ns)
    return entries


class NppMakerEditFactsTests(unittest.TestCase):
    def setUp(self):
        spec = importlib.util.spec_from_file_location("npp_maker_edit_facts", SCRIPT)
        if spec is None or spec.loader is None:
            self.fail("could not load the maker edit checker")
        self.tool = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(self.tool)

    def run_main(self, cases):
        stdout, stderr = io.StringIO(), io.StringIO()
        with patch.object(self.tool, "CASES", cases), redirect_stdout(stdout), redirect_stderr(stderr):
            code = self.tool.main([])
        self.assertEqual(stderr.getvalue(), "")
        return code, stdout.getvalue().splitlines()

    def run_cli(self, *args):
        with TemporaryDirectory() as cwd:
            return subprocess.run([sys.executable, "-B", str(SCRIPT), *args], cwd=cwd,
                                  capture_output=True, text=True, timeout=15)

    def test_c1_full_pass(self):
        # Harmless edits must not make an otherwise clean run fail.
        code, lines = self.run_main(("", "made by Etto Farm", "call it Clover Honey"))
        self.assertEqual(code, 0)
        self.assertEqual(lines[-1], PASS)
        self.assertEqual(len(lines[:-1]), 3)
        for number, line in enumerate(lines[:-1], 1):
            self.assertRegex(line, rf"^case {number:02d} fresh=(yes|no) foreign=0$")

    def test_c2_findings_trailer(self):
        # A clean last case must not overwrite the prior failure status.
        code, lines = self.run_main(("made by Bee Hill Apiary", ""))
        self.assertEqual(code, 1)
        self.assertEqual(lines[-1], FAIL)
        self.assertTrue(lines[-2].startswith("case 02 "))

    def test_c2_1_foreign_facts(self):
        # Reporting only the first failure or numbering just findings loses a case.
        code, lines = self.run_main(("made by Bee Hill Apiary from Arroyo Grande", "", "made by Bee Hill Apiary"))
        self.assertEqual(code, 1)
        self.assertEqual(lines[-1], FAIL)
        self.assertEqual([line for line in lines[:-1] if line.startswith("FAIL ")],
                         ["FAIL foreign-facts 01", "FAIL foreign-facts 03"])

    def test_c2_2_not_reached(self):
        # A prior capture must not hide a later render that returns early.
        cls = self.tool.stages.ProductionStages
        render = cls.render_listing

        def skip_name_edit(port, work, listing, *, local=False):
            if listing["name"] == "Clover Honey":
                return None
            return render(port, work, listing, local=local)

        with patch.object(cls, "render_listing", skip_name_edit):
            code, lines = self.run_main(("", "call it Clover Honey", "made by Etto Farm"))
        self.assertEqual(code, 1)
        self.assertEqual(lines, ["case 01 fresh=yes foreign=0", "FAIL not-reached 02",
                                 "case 03 fresh=yes foreign=0", FAIL])

    def test_c2_3_check_error(self):
        # A raised check is neither an unnoticed skip nor a diagnostic data leak.
        for owner, name in ((self.tool.stages.ProductionStages, "render_listing"),
                            (self.tool.edits, "read"), (self.tool.edits, "apply")):
            with self.subTest(method=name), patch.object(owner, name, side_effect=ValueError("fixture exception")):
                code, lines = self.run_main(("call it Clover Honey",))
                self.assertEqual(code, 1)
                self.assertEqual(lines, ["FAIL check-error", FAIL])

    def test_c3_usage_exit_2(self):
        # No positional, option, help, or delimiter argument is admitted.
        for arg in ("positional", "--unknown", "--help", "--"):
            with self.subTest(arg=arg):
                result = self.run_cli(arg)
                self.assertEqual(result.returncode, 2)
                self.assertEqual(result.stdout, "")
                self.assertTrue(result.stderr.startswith("usage: "))
                self.assertEqual(result.stderr.splitlines()[-1],
                                 f"npp_maker_edit_facts.py: error: unrecognized arguments: {arg}")

    def test_c4_read_only(self):
        # Draft generation or capture could leave a new or modified repo asset.
        before = tree_snapshot()
        result = self.run_cli()
        self.assertEqual(tree_snapshot(), before)
        self.assertEqual(result.returncode, 1)
        self.assertEqual(result.stdout.splitlines()[-1], FAIL)

    def test_c5_output_shape(self):
        # Debug output could disclose the quote, maker, or internal exception text.
        result = self.run_cli()
        self.assertEqual(result.returncode, 1)
        self.assertEqual(result.stderr, "")
        lines = result.stdout.splitlines()
        self.assertEqual(lines[-1], FAIL)
        for line in lines[:-1]:
            self.assertRegex(line, r"^(?:case [0-9]{2} fresh=(?:yes|no) foreign=[0-9]+"
                                  r"|FAIL (?:foreign-facts [0-9]{2}|not-reached [0-9]{2}|check-error))$")

    def test_c6_fixture(self):
        # A no-edit run must reach the real boundary with the original maker fresh.
        code, lines = self.run_main(("",))
        self.assertEqual(code, 0)
        self.assertEqual(lines, ["case 01 fresh=yes foreign=0", PASS])

    def test_c7_live_pins(self):
        # The replay must catch the two stale-fact paths but not the product rename.
        result = self.run_cli()
        self.assertEqual(result.returncode, 1)
        lines = result.stdout.splitlines()
        self.assertEqual(lines[-1], FAIL)
        cases = [line for line in lines if line.startswith("case ")]
        self.assertEqual(len(cases), 5)
        self.assertIn("case 02 fresh=yes foreign=1", cases)
        self.assertIn("case 04 fresh=yes foreign=0", cases)
        self.assertEqual([line for line in lines[:-1] if line.startswith("FAIL ")],
                         ["FAIL foreign-facts 02", "FAIL foreign-facts 05"])


if __name__ == "__main__":
    unittest.main()
