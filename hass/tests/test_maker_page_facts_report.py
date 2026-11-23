"""Exercise the saved-HTML reporting CLI with disposable synthetic pages only."""

from contextlib import redirect_stderr, redirect_stdout
import importlib.util
import io
from pathlib import Path
import subprocess
import sys
from tempfile import TemporaryDirectory
import unittest
from unittest.mock import patch


SCRIPT = Path(__file__).resolve().parents[2] / "scripts/hass/maker_page_facts_report.py"
NAME = "Harbor Lane"
DAY = "2026-11-09"
TOWN = "Morro Bay"
TOWN_PAGE = (
    "<html><head><meta name='description' content='x'></head><body>"
    "<p>Harbor Lane makes small-batch fruit jam in a shared kitchen in Morro Bay.</p>"
    "<p>Harbor Lane was founded in 2015 by a cook.</p>"
    "<script>Harbor Lane makes salsa.</script></body></html>"
)
PLAIN_PAGE = "<p>We make small-batch fruit jam in a shared kitchen.</p>"
HYPE_PAGE = "<p>Harbor Lane makes the best organic jam ever!</p>"
PASS = "PASS maker_page_facts_report"
FAIL = "FAIL maker_page_facts_report"


class MakerPageFactsReportTests(unittest.TestCase):
    def setUp(self):
        temp = TemporaryDirectory()
        self.addCleanup(temp.cleanup)
        self.root = Path(temp.name).resolve()
        self.path = self.root / "saved-page.html"

    def options(self, *, path=None, name=NAME, today=DAY, town=None):
        args = ["--html", str(self.path if path is None else path), "--name", name, "--today", today]
        if town is not None:
            args.extend(("--town", town))
        return args

    def run_cli(self, args):
        return subprocess.run([sys.executable, "-B", str(SCRIPT), *args],
                              cwd=self.root, capture_output=True, text=True, timeout=10)

    def run_page(self, html, **options):
        self.path.write_text(html, encoding="utf-8")
        return self.run_cli(self.options(**options))

    def assert_report(self, result, code, *lines):
        self.assertEqual(result.returncode, code)
        self.assertEqual(result.stderr, "")
        self.assertEqual(result.stdout.splitlines(), [*lines, PASS if code == 0 else FAIL])

    def test_c1_full_pass(self):
        # Losing first-person source statements would prevent a valid one-sentence story.
        self.assert_report(self.run_page(PLAIN_PAGE), 0, "blocks 1", "fact makes yes",
                           "fact since no", "story sentences 1")

    def test_c2_findings_trailer(self):
        # Returning after a reason alone would lose the machine-readable failure trailer.
        self.assert_report(self.run_cli(self.options()), 1, "FAIL unsafe-input")

    def test_c2_1_unsafe_input(self):
        # Following a symlink would otherwise let a valid target pass.
        self.path.write_text(PLAIN_PAGE, encoding="utf-8")
        link = self.root / "linked-page.html"
        link.symlink_to(self.path)
        dangling = self.root / "dangling-page.html"
        dangling.symlink_to(self.root / "absent.html")
        for path in (link, dangling, self.root):
            with self.subTest(kind=path.name):
                self.assert_report(self.run_cli(self.options(path=path)), 1, "FAIL unsafe-input")

    def test_c2_2_too_large(self):
        # Truncating one extra byte would report a passing story from an oversized input.
        # Use multibyte padding to distinguish a byte cap from a character cap.
        raw = PLAIN_PAGE.encode() + "é".encode() * ((600_000 - len(PLAIN_PAGE)) // 2)
        raw = raw.ljust(600_000)
        self.path.write_bytes(raw)
        self.assert_report(self.run_cli(self.options()), 0, "blocks 1", "fact makes yes",
                           "fact since no", "story sentences 1")
        self.path.write_bytes(raw + b" ")
        self.assert_report(self.run_cli(self.options()), 1, "FAIL too-large")

    def test_c2_3_not_utf8(self):
        # Replacement decoding would keep the valid block and hide the invalid byte.
        self.path.write_bytes(PLAIN_PAGE.encode() + b"\xff")
        self.assert_report(self.run_cli(self.options()), 1, "FAIL not-utf8")

    def test_c2_4_no_story(self):
        # Promotional text must not be counted as a fact or a usable story.
        self.assert_report(self.run_page(HYPE_PAGE, town=TOWN), 1, "blocks 1",
                           "fact makes no", "fact since no", "fact town no", "story none", "FAIL no-story")

    def test_c2_5_unreadable_input(self):
        # A regular file can pass lstat yet fail to open; never echo the exception.
        self.path.write_text(PLAIN_PAGE, encoding="utf-8")
        spec = importlib.util.spec_from_file_location("maker_page_facts_report", SCRIPT)
        assert spec is not None and spec.loader is not None
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)
        stdout, stderr = io.StringIO(), io.StringIO()
        with (
            patch("builtins.open", side_effect=PermissionError(f"{self.path}: {PLAIN_PAGE}")) as opened,
            patch.object(module.maker_site, "extract", wraps=module.maker_site.extract) as extract,
            redirect_stdout(stdout), redirect_stderr(stderr),
        ):
            code = module.main(self.options())
        opened.assert_called_once()
        self.assertEqual(opened.call_args.args[:2], (self.path, "rb"))
        extract.assert_not_called()
        self.assertEqual(code, 1)
        self.assertEqual(stdout.getvalue(), "FAIL unreadable-input\nFAIL maker_page_facts_report\n")
        self.assertEqual(stderr.getvalue(), "")

    def test_c3_usage_exit_2(self):
        # Validation belongs to argparse, not to the findings path or permissive date parsing.
        cases = ([], self.options() + ["--unknown"], self.options(name=" \t "),
                 self.options(name="x" * 81), self.options(today="2026-02-30"),
                 self.options(today="20261109"), self.options(today="2026-W46-1"))
        for index, args in enumerate(cases):
            with self.subTest(case=index):
                result = self.run_cli(args)
                self.assertEqual(result.returncode, 2)
                self.assertEqual(result.stdout, "")
                self.assertTrue(result.stderr.startswith("usage: "))
                self.assertEqual(result.stderr.splitlines()[-1],
                                 "maker_page_facts_report.py: error: invalid arguments; see --help")

    def test_c4_read_only(self):
        # A cached report or an in-place rewrite would touch directory entries or input metadata.
        self.path.write_text(PLAIN_PAGE, encoding="utf-8")
        before = (self.path.read_bytes(), self.path.stat().st_mtime_ns,
                  set(self.root.iterdir()), self.root.stat().st_mtime_ns)
        self.assert_report(self.run_cli(self.options()), 0, "blocks 1", "fact makes yes",
                           "fact since no", "story sentences 1")
        after = (self.path.read_bytes(), self.path.stat().st_mtime_ns,
                 set(self.root.iterdir()), self.root.stat().st_mtime_ns)
        self.assertEqual(after, before)

    def test_c5_no_private_values(self):
        # Scan both channels on success, input refusal, and argv errors that normally echo tokens.
        name, town = "Quill Lane", TOWN
        source = f"{name} makes small-batch fruit jam in a shared kitchen in {town}."
        meta = "A synthetic description canary."
        hidden = "A synthetic hidden canary."
        draft = f"{name} makes small-batch fruit jam."
        self.path.write_text(f"<meta name='description' content='{meta}'><p>{source}</p>"
                             f"<script>{hidden}</script>", encoding="utf-8")
        args = self.options(name=name, town=town)
        success = self.run_cli(args)
        self.assert_report(success, 0, "blocks 2", "fact makes yes", "fact since no",
                           "fact town yes", "story sentences 2")
        usage = self.run_cli(args + [f"--unknown={self.path}", source, name, town, meta, hidden, draft])
        self.assertEqual(usage.returncode, 2)
        self.assertEqual(usage.stdout, "")
        self.assertEqual(usage.stderr.splitlines()[-1],
                         "maker_page_facts_report.py: error: invalid arguments; see --help")
        self.path.write_bytes(self.path.read_bytes() + b"\xff")
        failed = self.run_cli(args)
        self.assert_report(failed, 1, "FAIL not-utf8")
        for result in (success, usage, failed):
            for value in (source, name, town, str(self.path), meta, hidden, draft):
                self.assertNotIn(value, result.stdout)
                self.assertNotIn(value, result.stderr)

    def test_c6_town_page(self):
        # A missing meta block, included script, or unnormalized name changes this report.
        self.assert_report(self.run_page(TOWN_PAGE, town=TOWN, name="  Harbor\t Lane  "), 0,
                           "blocks 3", "fact makes yes", "fact since yes", "fact town yes", "story sentences 2")

    def test_c7_without_town(self):
        # A town cannot be inferred from the page, and a year alone is not a story.
        self.assert_report(self.run_page(TOWN_PAGE), 1, "blocks 3", "fact makes no",
                           "fact since yes", "story none", "FAIL no-story")

    def test_c8_future_year(self):
        # The short pinned sentence is rejected; the longer pair isolates the date cutoff.
        self.assert_report(self.run_page("<p>Harbor Lane was founded in 2030.</p>"), 1,
                           "blocks 1", "fact makes no", "fact since no", "story none", "FAIL no-story")
        page = PLAIN_PAGE + "<p>Harbor Lane was founded in 2030 by a cook.</p>"
        self.assert_report(self.run_page(page), 0, "blocks 2", "fact makes yes",
                           "fact since no", "story sentences 1")
        self.assert_report(self.run_page(page, today="2030-01-01"), 0, "blocks 2", "fact makes yes",
                           "fact since yes", "story sentences 2")


if __name__ == "__main__":
    unittest.main()
