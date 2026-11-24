"""Behavioral tests for the offline half-and-half spelling audit."""

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
SCRIPT = ROOT / "scripts/hass/npp_idiom_variants.py"
PASS = "PASS npp_idiom_variants"
FAIL = "FAIL npp_idiom_variants"
ACCEPTED = ("half-and-half", "half and half")


def snapshot(root):
    entries = {}
    for path in (root, *root.rglob("*")):
        stats = path.lstat()
        entries[path.relative_to(ROOT)] = (stats.st_size, stats.st_mtime_ns)
    return entries


class NppIdiomVariantsTests(unittest.TestCase):
    def setUp(self):
        spec = importlib.util.spec_from_file_location("npp_idiom_variants", SCRIPT)
        assert spec is not None and spec.loader is not None
        self.script = importlib.util.module_from_spec(spec)
        with patch.object(sys, "path", sys.path.copy()):
            spec.loader.exec_module(self.script)

    def invoke(self):
        stdout, stderr = io.StringIO(), io.StringIO()
        with redirect_stdout(stdout), redirect_stderr(stderr):
            status = self.script.main([])
        self.assertEqual(stderr.getvalue(), "")
        return status, stdout.getvalue().splitlines()

    def cli(self, *args):
        with TemporaryDirectory() as cwd:
            result = subprocess.run(
                [sys.executable, "-B", str(SCRIPT), *args], cwd=cwd,
                capture_output=True, text=True, timeout=10,
            )
            self.assertEqual(list(Path(cwd).iterdir()), [])
        return result

    def test_c1_full_pass(self):
        # A clean classification must not leave the diagnostic in a failed state.
        with patch.object(self.script, "VARIANTS", ACCEPTED[:1]):
            status, lines = self.invoke()
        self.assertEqual(status, 0)
        self.assertEqual(lines[-1], PASS)
        self.assertEqual(lines, ["idiom 01 problem=none", PASS])

    def test_c2_findings_trailer(self):
        # A later acceptance must not clear an earlier finding or change the exit code.
        with patch.object(self.script, "VARIANTS", ("Half & Half", *ACCEPTED)):
            status, lines = self.invoke()
        self.assertEqual(status, 1)
        self.assertEqual(lines[-1], FAIL)
        self.assertEqual([line for line in lines[:-1] if line.startswith("FAIL ")],
                         ["FAIL idiom-refused 01"])

    def test_c2_1_idiom_refused(self):
        # Findings must be numbered by spelling position, not by refusal count.
        variants = (ACCEPTED[0], "Half & Half", ACCEPTED[1], "half/half")
        with patch.object(self.script, "VARIANTS", variants):
            status, lines = self.invoke()
        self.assertEqual(status, 1)
        self.assertEqual(lines[-1], FAIL)
        self.assertEqual(lines, [
            "idiom 01 problem=none",
            "idiom 02 problem=number-unclear", "FAIL idiom-refused 02",
            "idiom 03 problem=none",
            "idiom 04 problem=number-unclear", "FAIL idiom-refused 04", FAIL,
        ])

    def test_c2_2_check_error(self):
        # Bad return values and exceptions must not leak or skip subsequent rows.
        bad_results = (RuntimeError("synthetic-error-detail"), 42, "", "a" * 41,
                       "UPPERCASE", "bad\n", "é")
        for bad_result in bad_results:
            with (
                self.subTest(bad_result=bad_result),
                patch.object(self.script, "VARIANTS", ACCEPTED),
                patch.object(self.script.private_numbers, "problem",
                             side_effect=[bad_result, None]),
            ):
                status, lines = self.invoke()
                self.assertEqual(status, 1)
                self.assertEqual(lines[-1], FAIL)
                self.assertEqual(lines, ["FAIL check-error", "idiom 02 problem=none", FAIL])

    def test_c3_usage_exit_2(self):
        # Argparse's default help and a bare separator must not bypass the no-args rule.
        for argument in ("extra", "--unknown", "--help", "-h", "--"):
            with self.subTest(argument=argument):
                result = self.cli(argument)
                self.assertEqual(result.returncode, 2)
                self.assertEqual(result.stdout, "")  # Usage errors have no stdout trailer.
                self.assertTrue(result.stderr.startswith("usage:"))
                self.assertEqual(result.stderr.splitlines()[-1],
                                 f"npp_idiom_variants.py: error: unrecognized arguments: {argument}")

    def test_c4_read_only(self):
        # Imports or a diagnostic writer must not leave caches or reports in either tree.
        trees = (ROOT / "hass", ROOT / "storefront-mockup")
        before = tuple(snapshot(tree) for tree in trees)
        result = self.cli()
        after = tuple(snapshot(tree) for tree in trees)
        self.assertEqual(result.returncode, 1)
        self.assertEqual(result.stdout.splitlines()[-1], FAIL)
        self.assertTrue(before == after, "the audit changed a protected tree")

    def test_c5_output_shape(self):
        # No banner, raw spelling, exception detail or stderr output may join the protocol.
        result = self.cli()
        lines = result.stdout.splitlines()
        self.assertEqual(result.returncode, 1)
        self.assertEqual(lines[-1], FAIL)
        self.assertEqual(result.stderr, "")
        for line in lines[:-1]:
            self.assertRegex(line, r"\A(?:idiom [0-9]{2} problem=[a-z-]{1,40}|"
                                   r"FAIL idiom-refused [0-9]{2}|FAIL check-error)\Z")

    def test_c6_fixture(self):
        # The full fixture override must be used instead of a cached default inventory.
        with patch.object(self.script, "VARIANTS", ACCEPTED):
            status, lines = self.invoke()
        self.assertEqual(status, 0)
        self.assertEqual(lines[-1], PASS)
        self.assertEqual(lines, ["idiom 01 problem=none", "idiom 02 problem=none", PASS])

    def test_c7_live_pins(self):
        # Detect spelling swaps (even among equal outcomes) and changes in the real screen.
        self.assertEqual(self.script.VARIANTS, (
            "half-and-half", "half and half", "Half & Half", "half & half",
            "half n half", "half 'n' half", "half-n-half", "half/half",
            "Half and Half cream", "organic half-and-half", "half-and-half creamer", "half-&-half",
        ))
        status, lines = self.invoke()
        self.assertEqual(status, 1)
        self.assertEqual(lines[-1], FAIL)
        refused = (3, 4, 5, 6, 7, 8, 12)
        self.assertEqual([line for line in lines if line.startswith("idiom ")], [
            f"idiom {i:02d} problem={'number-unclear' if i in refused else 'none'}"
            for i in range(1, 13)
        ])
        self.assertEqual([line for line in lines[:-1] if line.startswith("FAIL ")],
                         [f"FAIL idiom-refused {i:02d}" for i in refused])


if __name__ == "__main__":
    unittest.main()
