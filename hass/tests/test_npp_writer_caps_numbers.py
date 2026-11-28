"""Offline CLI and drift checks for the writer's name and number fixtures."""

from contextlib import redirect_stderr, redirect_stdout
import importlib.util
import io
from pathlib import Path
import subprocess
import sys
import unittest
from unittest.mock import call, patch

from hass import newitem


ROOT = Path(__file__).resolve().parents[2]
SCRIPT = ROOT / "scripts/hass/npp_writer_caps_numbers.py"
PASS = "PASS npp_writer_caps_numbers"
FAIL = "FAIL npp_writer_caps_numbers"


class WriterCapsNumbersTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        spec = importlib.util.spec_from_file_location("npp_writer_caps_numbers", SCRIPT)
        if spec is None or spec.loader is None:
            raise ImportError("cannot load npp_writer_caps_numbers")
        cls.check = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(cls.check)

    def invoke(self, *args):
        return subprocess.run(
            [sys.executable, "-B", str(SCRIPT), *args], cwd=ROOT,
            capture_output=True, text=True, timeout=10,
        )

    def run_main(self, code, trailer):
        stdout, stderr = io.StringIO(), io.StringIO()
        with redirect_stdout(stdout), redirect_stderr(stderr):
            result = self.check.main([])
        self.assertEqual(result, code)
        self.assertEqual(stderr.getvalue(), "")
        lines = stdout.getvalue().splitlines()
        self.assertEqual(lines[-1:], [trailer])
        return lines[:-1]

    def split_match_lines(self):
        with patch.object(newitem, "_has", lambda haystack, needle: needle in haystack.split()):
            return self.run_main(1, FAIL)

    def test_c1_full_pass(self):
        # A script that always exits nonzero (or mislabels success) breaks the CLI.
        result = self.invoke()
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(result.stdout.splitlines()[-1:], [PASS])

    def test_c2_findings_trailer(self):
        # Grouping findings at the end or reversing the two reasons loses case context.
        with patch.object(newitem, "_has", lambda haystack, needle: True):
            lines = self.run_main(1, FAIL)
        expected = []
        for i in range(9):
            expected.append(f"case {i} ungrounded=[]")
            if i in (2, 4, 5, 6, 7):
                expected.extend((f"FAIL ungrounded-name-passed {i}", f"FAIL grounded-changed {i}"))
        self.assertEqual(lines, expected)

    def test_c2_1_ungrounded_name_passed(self):
        # A generic drift warning alone hides which unsupported claims slipped through.
        with patch.object(newitem, "_has", lambda haystack, needle: True):
            lines = self.run_main(1, FAIL)
        self.assertEqual(
            [line for line in lines if line.startswith("FAIL ")],
            [
                "FAIL ungrounded-name-passed 2", "FAIL grounded-changed 2",
                "FAIL ungrounded-name-passed 4", "FAIL grounded-changed 4",
                "FAIL ungrounded-name-passed 5", "FAIL grounded-changed 5",
                "FAIL ungrounded-name-passed 6", "FAIL grounded-changed 6",
                "FAIL ungrounded-name-passed 7", "FAIL grounded-changed 7",
            ],
        )

    def test_c2_2_grounded_changed(self):
        # Checking only empty results would miss a newly rejected grounded word.
        lines = self.split_match_lines()
        self.assertEqual([line for line in lines if line.startswith("FAIL ")],
                         ["FAIL grounded-changed 1"])

    def test_c2_3_check_error(self):
        # Skipping a failed call or leaking its diagnostic would violate the CLI contract.
        with patch.object(newitem, "grounded_text", side_effect=RuntimeError("fixture detail")) as check:
            self.assertEqual(self.run_main(1, FAIL), ["FAIL check-error"])
            check.assert_called_once()

    def test_c3_usage_exit_2(self):
        # In particular, argparse's default help would accept an argument on stdout.
        for arg in ("unexpected", "--unknown", "--help", "-h", "--"):
            with self.subTest(arg=arg):
                result = self.invoke(arg)
                self.assertEqual(result.returncode, 2)
                self.assertEqual(result.stdout, "")
                self.assertIn("error: unrecognized arguments:", result.stderr)

    def test_c4_read_only(self):
        # Accidental output or a rewritten file must change this metadata snapshot.
        def snapshot():
            entries = {}
            for name in ("hass", "storefront-mockup"):
                tree = ROOT / name
                for path in (tree, *tree.rglob("*")):
                    stat = path.lstat()
                    entries[path.relative_to(ROOT)] = (stat.st_size, stat.st_mtime_ns)
            return entries

        before = snapshot()
        result = self.invoke()
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(result.stdout.splitlines()[-1:], [PASS])
        self.assertEqual(snapshot(), before)

    def test_c5_output_shape(self):
        # A banner or debug print on either stream would contaminate the CLI receipt.
        result = self.invoke()
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(result.stderr, "")
        lines = result.stdout.splitlines()
        self.assertEqual(lines[-1:], [PASS])
        for line in lines[:-1]:
            self.assertRegex(line, r"^case [0-8] ungrounded=\[.*\]$")

    def test_c6_fixture(self):
        # Whitespace tokenisation misses the comma boundary on Fillmore, and only there.
        lines = self.split_match_lines()
        self.assertEqual(lines[1:3], ["case 1 ungrounded=['Fillmore']", "FAIL grounded-changed 1"])
        self.assertEqual([line for line in lines if line.startswith("FAIL ")],
                         ["FAIL grounded-changed 1"])

    def test_c7_live_pins(self):
        # Hardcoded reports bypass the repo function; changes to its live rules change these pins.
        with patch.object(newitem, "grounded_text", wraps=newitem.grounded_text) as check:
            lines = self.run_main(0, PASS)
            self.assertEqual(check.call_args_list, [call(text, self.check.ALLOWED) for text in self.check.CASES])
        self.assertEqual(lines, [
            "case 0 ungrounded=[]",
            "case 1 ungrounded=[]",
            "case 2 ungrounded=['Ojai']",
            "case 3 ungrounded=[]",
            "case 4 ungrounded=['16']",
            "case 5 ungrounded=['Gold', 'Medal']",
            "case 6 ungrounded=['1998']",
            "case 7 ungrounded=['Brie']",
            "case 8 ungrounded=[]",
        ])


if __name__ == "__main__":
    unittest.main()
