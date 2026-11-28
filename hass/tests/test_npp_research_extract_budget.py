"""Exercise the offline S4 budget diagnostic against the real request builder."""

from contextlib import redirect_stderr, redirect_stdout
import importlib.util
import io
import json
from pathlib import Path
import subprocess
import sys
from tempfile import TemporaryDirectory
import unittest
from unittest.mock import patch

REPO = Path(__file__).resolve().parents[2]
SCRIPT = REPO / "scripts/hass/npp_research_extract_budget.py"
PASS = "PASS npp_research_extract_budget"
FAIL = "FAIL npp_research_extract_budget"


class ExtractBudgetTests(unittest.TestCase):
    def setUp(self):
        temp = TemporaryDirectory(dir=REPO)
        self.addCleanup(temp.cleanup)
        self.root = Path(temp.name)
        spec = importlib.util.spec_from_file_location("npp_research_extract_budget", SCRIPT)
        assert spec is not None and spec.loader is not None
        self.tool = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(self.tool)

    def run_main(self, code, trailer):
        stdout, stderr = io.StringIO(), io.StringIO()
        with redirect_stdout(stdout), redirect_stderr(stderr):
            status = self.tool.main([])
        return self.assert_result(status, stdout.getvalue(), stderr.getvalue(), code, trailer)

    def invoke(self, *args):
        return subprocess.run(
            [sys.executable, "-B", str(SCRIPT), *args], cwd=self.root,
            capture_output=True, text=True, timeout=10,
        )

    def assert_result(self, status, stdout, stderr, code, trailer):
        self.assertEqual(status, code, stdout + stderr)
        self.assertEqual(stderr, "")
        lines = stdout.splitlines()
        self.assertTrue(lines, "missing trailer")
        self.assertEqual(lines[-1], trailer)
        return lines

    def assert_cli(self, result, code, trailer):
        return self.assert_result(result.returncode, result.stdout, result.stderr, code, trailer)

    def test_c1_full_pass(self):
        # An unconditional FAIL or lost block would reject the small, adequate request.
        with patch.object(self.tool, "CASES", self.tool.CASES[:1]):
            self.assertEqual(self.run_main(0, PASS), [
                "case 0 page 0 kept 2 of 2", "case 0 page 1 kept 1 of 1", PASS,
            ])

    def test_c2_findings_trailer(self):
        # A summary that uses only the last case would lose an earlier failure.
        small, full, *_ = self.tool.CASES
        with patch.object(self.tool, "CASES", (full, small)):
            lines = self.run_main(1, FAIL)
        self.assertEqual(lines[-4:], [
            "FAIL page-starved 0 1", "case 1 page 0 kept 2 of 2",
            "case 1 page 1 kept 1 of 1", FAIL,
        ])

    def test_c2_1_page_starved(self):
        # Including empty pages in the request is not enough; only eligible blocks count.
        home, about = self.tool.HOME, self.tool.ABOUT
        full_home = self.tool.CASES[1][home]
        for length, code, trailer, findings in (
            (1600, 1, FAIL, ["FAIL page-starved 0 1"]),
            (1601, 0, PASS, []),
        ):
            with self.subTest(length=length):
                cases = ({home: full_home, about: ["a" * length]},)
                with patch.object(self.tool, "CASES", cases):
                    self.assertEqual(self.run_main(code, trailer), [
                        "case 0 page 0 kept 15 of 15", "case 0 page 1 kept 0 of 1",
                        *findings, trailer,
                    ])

    def test_c2_2_wrong_request(self):
        # Any of these three independent drifts can pass if only the page counts are checked.
        models = self.tool.research_hermes.Models
        real_call = models._call

        def altered_call(model, *args, **kwargs):
            runner = model.runner

            def alter(request):
                if drift == "request keys":
                    request["extra"] = None
                elif drift == "images":
                    request["images"] = ["fixture"]
                else:
                    start, payload, end = request["text"].splitlines()
                    data = json.loads(payload)
                    del data["maker"]
                    request["text"] = "\n".join((start, json.dumps(data), end))
                return runner(request)

            with patch.object(model, "runner", alter):
                return real_call(model, *args, **kwargs)

        for drift in ("request keys", "images", "data keys"):
            with (self.subTest(drift=drift),
                  patch.object(self.tool, "CASES", self.tool.CASES[:1]),
                  patch.object(models, "_call", altered_call)):
                self.assertEqual(self.run_main(1, FAIL), [
                    "FAIL wrong-request 0", "case 0 page 0 kept 2 of 2",
                    "case 0 page 1 kept 1 of 1", FAIL,
                ])

    def test_c2_3_check_error(self):
        # An unexpected extractor exception must not leak text, skip silently, or stop later checks.
        models = self.tool.research_hermes.Models
        real_extract = models.extract
        small, full, *_ = self.tool.CASES

        def extract(model, maker, pages, seconds):
            if pages == full:
                raise RuntimeError("synthetic detail")
            return real_extract(model, maker, pages, seconds)

        with (patch.object(self.tool, "CASES", (full, small)),
              patch.object(models, "extract", extract)):
            self.assertEqual(self.run_main(1, FAIL), [
                "FAIL check-error", "case 1 page 0 kept 2 of 2",
                "case 1 page 1 kept 1 of 1", FAIL,
            ])

    def test_c3_usage_exit_2(self):
        # No extra tokens are accepted, even argparse's usual help spelling.
        for arg in ("extra", "--unknown", "--help", "-h", "--"):
            with self.subTest(arg=arg):
                result = self.invoke(arg)
                self.assertEqual(result.returncode, 2)
                self.assertEqual(result.stdout, "")  # no last stdout line
                self.assertIn("usage: npp_research_extract_budget.py", result.stderr)
                self.assertEqual(result.stderr.splitlines()[-1],
                                 f"npp_research_extract_budget.py: error: unrecognized arguments: {arg}")

    def test_c4_read_only(self):
        # Catch cache or report writes in either product tree during the CLI run.
        def snapshot():
            entries = {}
            for root in (REPO / "hass", REPO / "storefront-mockup", self.root):
                for path in (root, *root.rglob("*")):
                    info = path.lstat()
                    entries[path.relative_to(REPO)] = (info.st_size, info.st_mtime_ns)
            return entries

        before = snapshot()
        self.assert_cli(self.invoke(), 1, FAIL)
        self.assertEqual(snapshot(), before)

    def test_c5_output_shape(self):
        # Debug logs, blank lines or raw request dumps must not pollute the report.
        lines = self.assert_cli(self.invoke(), 1, FAIL)
        for line in lines[:-1]:
            self.assertRegex(line, r"^(?:case \d+ page \d+ kept \d+ of \d+|FAIL page-starved \d+ \d+)$")

    def test_c6_fixture(self):
        # Sorting or ignoring input order would let the home page starve About again.
        reversed_cases = tuple(dict(reversed(tuple(pages.items()))) for pages in self.tool.CASES)
        with patch.object(self.tool, "CASES", reversed_cases):
            self.assertEqual(self.run_main(0, PASS), [
                "case 0 page 0 kept 1 of 1", "case 0 page 1 kept 2 of 2",
                "case 1 page 0 kept 1 of 1", "case 1 page 1 kept 14 of 15",
                "case 2 page 0 kept 1 of 1", "case 2 page 1 kept 0 of 1",
                "case 3 page 0 kept 1 of 1", "case 3 page 1 kept 14 of 15", PASS,
            ])

    def test_c7_live_pins(self):
        # Re-measured on origin/main: catches changed budget, truncation or reporting order.
        self.assertEqual(self.run_main(1, FAIL), [
            "case 0 page 0 kept 2 of 2", "case 0 page 1 kept 1 of 1",
            "case 1 page 0 kept 15 of 15", "case 1 page 1 kept 0 of 1", "FAIL page-starved 1 1",
            "case 2 page 0 kept 0 of 1", "case 2 page 1 kept 1 of 1",
            "case 3 page 0 kept 15 of 15", "case 3 page 1 kept 0 of 1", "FAIL page-starved 3 1",
            FAIL,
        ])


if __name__ == "__main__":
    unittest.main()
