"""Offline CLI and drift checks for the maker-page sentence report."""

from contextlib import redirect_stderr, redirect_stdout
import importlib.util
import io
from pathlib import Path
import re
import subprocess
import sys
import unittest
from unittest.mock import call, patch


ROOT = Path(__file__).resolve().parents[2]
SCRIPT = ROOT / "scripts/hass/npp_maker_page_sentence.py"
PASS = "PASS npp_maker_page_sentence"
FAIL = "FAIL npp_maker_page_sentence"
KEPT = (0, 1, 8, 11)


def case_lines(kept):
    return [f"case {i} kept={'yes' if i in kept else 'no'}" for i in range(14)]


def snapshot():
    entries = {}
    for tree in (ROOT / "hass", ROOT / "storefront-mockup"):
        for path in (tree, *tree.rglob("*")):
            stat = path.lstat()
            entries[path.relative_to(ROOT)] = (stat.st_size, stat.st_mtime_ns)
    return entries


class MakerPageSentenceTests(unittest.TestCase):
    def setUp(self):
        spec = importlib.util.spec_from_file_location(SCRIPT.stem, SCRIPT)
        if spec is None or spec.loader is None:
            raise ImportError(f"Cannot load {SCRIPT.name}")
        self.script = importlib.util.module_from_spec(spec)
        # The standalone script bootstraps sys.path; don't leak that to other tests.
        with patch.object(sys, "path", sys.path[:]):
            spec.loader.exec_module(self.script)

    def cli(self, *args):
        return subprocess.run(
            [sys.executable, "-B", str(SCRIPT), *args],
            cwd=SCRIPT.parent, capture_output=True, text=True, timeout=10,
        )

    def run_main(self, status, trailer):
        stdout, stderr = io.StringIO(), io.StringIO()
        with redirect_stdout(stdout), redirect_stderr(stderr):
            code = self.script.main([])
        self.assertEqual(code, status)
        self.assertEqual(stderr.getvalue(), "")
        lines = stdout.getvalue().splitlines()
        self.assertEqual(lines[-1:], [trailer])
        return lines[:-1]

    def test_c1_full_pass(self):
        # Catch a broken entry point or a success report with the wrong status.
        result = self.cli()
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(result.stdout.splitlines()[-1:], [PASS])

    def test_c2_findings_trailer(self):
        # Catch findings batched after the cases, reversed, or reported as success.
        with patch.object(self.script.maker_site, "DROP", re.compile(r"(?!x)x")):
            lines = self.run_main(1, FAIL)
        expected = case_lines((*KEPT, 5))
        expected[6:6] = ["FAIL unsafe-sentence-kept 5", "FAIL sentence-changed 5"]
        self.assertEqual(lines, expected)

    def test_c2_1_unsafe_sentence_kept(self):
        # A weaker word filter admits the unsafe sentence; pinning alone isn't enough.
        with patch.object(self.script.maker_site, "DROP", re.compile(r"(?!x)x")):
            lines = self.run_main(1, FAIL)
        self.assertEqual([line for line in lines if line.startswith("FAIL ")],
                         ["FAIL unsafe-sentence-kept 5", "FAIL sentence-changed 5"])

    def test_c2_2_sentence_changed(self):
        # Catch comparisons that only look for wrongly kept sentences, not lost ones.
        with patch.object(self.script.maker_site, "MIN_LEN", 70):
            lines = self.run_main(1, FAIL)
        expected = case_lines(())
        for i in reversed(KEPT):
            expected.insert(i + 1, f"FAIL sentence-changed {i}")
        self.assertEqual(lines, expected)

    def test_c2_3_check_error(self):
        # Catch leaked exception text, a silent skip, or continued checks after failure.
        maker_site = self.script.maker_site
        source_ok = maker_site.source_ok
        first, second = self.script.CASES[:2]

        def fail_on_second(*args):
            if args == second:
                raise RuntimeError("synthetic exception detail")
            return source_ok(*args)

        with patch.object(maker_site, "source_ok", side_effect=fail_on_second) as check:
            lines = self.run_main(1, FAIL)
        self.assertEqual(lines, ["case 0 kept=yes", "FAIL check-error"])
        self.assertEqual(check.call_args_list, [call(*first), call(*second)])

    def test_c3_usage_exit_2(self):
        # Catch accidental accepted options (including implicit help) and report leakage.
        for argument in ("extra", "--unknown", "--help", "-h", "--"):
            with self.subTest(argument=argument):
                result = self.cli(argument)
                self.assertEqual(result.returncode, 2)
                self.assertEqual(result.stdout, "")
                self.assertTrue(result.stderr.startswith("usage: "))
                self.assertEqual(result.stderr.splitlines()[-1],
                                 f"{SCRIPT.name}: error: unrecognized arguments: {argument}")

    def test_c4_read_only(self):
        # Catch an incidental cache, report file, or rewrite in either input tree.
        before = snapshot()
        result = self.cli()
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(result.stdout.splitlines()[-1:], [PASS])
        self.assertEqual(snapshot(), before)

    def test_c5_output_shape(self):
        # Catch debug output, sentence content, or other uncontracted diagnostics.
        result = self.cli()
        self.assertEqual(result.returncode, 0)
        self.assertEqual(result.stderr, "")
        lines = result.stdout.splitlines()
        self.assertEqual(lines[-1:], [PASS])
        for line in lines[:-1]:
            self.assertRegex(line, r"\Acase (?:[0-9]|1[0-3]) kept=(?:yes|no)\Z")

    def test_c6_fixture(self):
        # Catch a stale report that ignores the repo's length setting or stops early.
        with patch.object(self.script.maker_site, "MIN_LEN", 70):
            lines = self.run_main(1, FAIL)
        self.assertEqual([line for line in lines if line.startswith("FAIL ")], [
            "FAIL sentence-changed 0", "FAIL sentence-changed 1",
            "FAIL sentence-changed 8", "FAIL sentence-changed 11",
        ])
        self.assertEqual([line for line in lines if line.startswith("case ")], case_lines(()))

    def test_c7_live_pins(self):
        # Catch drift in acceptance, case order, or a report that replays cached answers.
        maker_site = self.script.maker_site
        with patch.object(maker_site, "source_ok", wraps=maker_site.source_ok) as check:
            self.assertEqual(self.run_main(0, PASS), case_lines(KEPT))
        self.assertEqual(check.call_args_list, [call(*case) for case in self.script.CASES])
