"""Offline CLI and mutation tests for the Hass writer's exact-piece guard."""

from contextlib import redirect_stderr, redirect_stdout
import importlib.util
import io
from pathlib import Path
import subprocess
import sys
import unittest
from unittest.mock import call, patch


ROOT = Path(__file__).resolve().parents[2]
SCRIPT = ROOT / "scripts/hass/npp_writer_exact_pieces.py"
PASS = "PASS npp_writer_exact_pieces"
FAIL = "FAIL npp_writer_exact_pieces"
LIVE_LINES = (
    "case 0 unproven=[]",
    "case 1 unproven=[]",
    "case 2 unproven=['wildflower honey from cedar row apiary.']",
    "case 3 unproven=[]",
    "case 4 unproven=['Try it on biscuits.']",
    "case 5 unproven=['Raw wildflower honey from Cedar Row']",
    "case 6 unproven=['Spoon it onto warm toast.']",
    "case 7 unproven=['Spoon it onto warm toast; it']",
    "case 8 unproven=[]",
    "case 9 unproven=['empty']",
)


def run_cli(*args):
    return subprocess.run(
        [sys.executable, "-B", str(SCRIPT), *args], cwd=ROOT,
        capture_output=True, text=True, timeout=10,
    )


def snapshot():
    entries = {}
    for name in ("hass", "storefront-mockup"):
        tree = ROOT / name
        for path in (tree, *tree.rglob("*")):
            info = path.lstat()
            entries[path.relative_to(ROOT)] = (info.st_size, info.st_mtime_ns)
    return entries


class NppWriterExactPiecesTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        spec = importlib.util.spec_from_file_location("npp_writer_exact_pieces", SCRIPT)
        if spec is None or spec.loader is None:
            raise ImportError("could not load the writer guard")
        cls.guard = importlib.util.module_from_spec(spec)
        with patch.object(sys, "path", sys.path.copy()):
            spec.loader.exec_module(cls.guard)

    def run_main(self):
        stdout, stderr = io.StringIO(), io.StringIO()
        with redirect_stdout(stdout), redirect_stderr(stderr):
            status = self.guard.main([])
        self.assertEqual(stderr.getvalue(), "")
        return status, stdout.getvalue().splitlines()

    def test_c1_full_pass(self):
        # A healthy checkout must yield a standalone CLI success receipt.
        result = run_cli()
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(result.stdout.splitlines()[-1], PASS)

    def test_c2_findings_trailer(self):
        # Late matching cases must not clear an earlier failure or end the run early.
        with patch.object(self.guard.newitem, "_fold", lambda text: ""):
            status, lines = self.run_main()
        self.assertEqual(status, 1)
        self.assertEqual(lines[-2:], ["case 9 unproven=['empty']", FAIL])
        self.assertIn("FAIL unproven-sentence-passed 7", lines)

    def test_c2_1_unproven_sentence_passed(self):
        # Collapsing sentence identity lets additions through; report both findings in place.
        with patch.object(self.guard.newitem, "_fold", lambda text: ""):
            status, lines = self.run_main()
        self.assertEqual(status, 1)
        self.assertEqual(lines, [
            "case 0 unproven=[]",
            "case 1 unproven=[]",
            "case 2 unproven=[]",
            "FAIL pieces-changed 2",
            "case 3 unproven=[]",
            "case 4 unproven=[]",
            "FAIL unproven-sentence-passed 4",
            "FAIL pieces-changed 4",
            "case 5 unproven=[]",
            "FAIL unproven-sentence-passed 5",
            "FAIL pieces-changed 5",
            "case 6 unproven=[]",
            "FAIL unproven-sentence-passed 6",
            "FAIL pieces-changed 6",
            "case 7 unproven=[]",
            "FAIL unproven-sentence-passed 7",
            "FAIL pieces-changed 7",
            "case 8 unproven=[]",
            "case 9 unproven=['empty']",
            FAIL,
        ])

    def test_c2_2_pieces_changed(self):
        # A formerly accepted piece becoming unproven is drift, not an unsafe admission.
        with patch.object(self.guard.newitem, "GENERIC_SERVING", ()):
            status, lines = self.run_main()
        self.assertEqual(status, 1)
        self.assertEqual(lines[-1], FAIL)
        self.assertEqual([line for line in lines if line.startswith("FAIL ")],
                         ["FAIL pieces-changed 8", FAIL])

    def test_c2_3_check_error(self):
        # An exception after one good case must stop further work without leaking details.
        newitem = self.guard.newitem
        real = newitem.writer_unproven

        def break_second_case(text, first, pool, use):
            if text == "Wildflower honey from Cedar Row Apiary. Spoon it onto warm toast.":
                raise RuntimeError("synthetic exception detail")
            return real(text, first, pool, use)

        with patch.object(newitem, "writer_unproven", side_effect=break_second_case) as checked:
            status, lines = self.run_main()
        self.assertEqual(checked.call_count, 2)
        self.assertEqual(status, 1)
        self.assertEqual(lines, [LIVE_LINES[0], "FAIL check-error", FAIL])

    def test_c3_usage_exit_2(self):
        # No input, help flag, or bare option terminator should start checking cases.
        for argument in ("extra", "--unknown", "-h", "--help", "--"):
            with self.subTest(argument=argument):
                result = run_cli(argument)
                self.assertEqual(result.returncode, 2)
                self.assertEqual(result.stdout, "")
                self.assertTrue(result.stderr.startswith("usage: "))
                self.assertEqual(
                    result.stderr.splitlines()[-1],
                    f"npp_writer_exact_pieces.py: error: unrecognized arguments: {argument}",
                )

    def test_c4_read_only(self):
        # No caches, generated files, or edits may appear in either input tree.
        before = snapshot()
        result = run_cli()
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(result.stdout.splitlines()[-1], PASS)
        self.assertEqual(snapshot(), before)

    def test_c5_output_shape(self):
        # Extra diagnostics on stdout or stderr make the receipt harder to consume.
        result = run_cli()
        self.assertEqual(result.returncode, 0)
        self.assertEqual(result.stderr, "")
        lines = result.stdout.splitlines()
        self.assertEqual(lines[-1], PASS)
        self.assertEqual(len(lines), 11)
        for i, line in enumerate(lines[:-1]):
            self.assertRegex(line, rf"^case {i} unproven=\[.*\]$")

    def test_c6_fixture(self):
        # A hardcoded generic whitelist would hide removal from the real repository pool.
        with patch.object(self.guard.newitem, "GENERIC_SERVING", ()):
            status, lines = self.run_main()
        self.assertEqual(status, 1)
        self.assertEqual(lines, [
            *LIVE_LINES[:8],
            "case 8 unproven=['Taste a little first, then decide']",
            "FAIL pieces-changed 8",
            LIVE_LINES[9],
            FAIL,
        ])

    def test_c7_live_pins(self):
        # Require the real selector's answers, not a replay of the expected receipt.
        newitem = self.guard.newitem
        with patch.object(newitem, "writer_unproven", wraps=newitem.writer_unproven) as checked:
            status, lines = self.run_main()
        self.assertEqual(checked.call_args_list, [
            call(text, self.guard.FIRST, self.guard.POOL, use)
            for text, use in self.guard.CASES
        ])
        self.assertEqual(status, 0)
        self.assertEqual(lines, [*LIVE_LINES, PASS])


if __name__ == "__main__":
    unittest.main()
