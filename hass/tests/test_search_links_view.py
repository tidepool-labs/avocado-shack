"""Fixture-only CLI contract for the saved search link counts."""

from contextlib import redirect_stderr, redirect_stdout
import importlib.util
import io
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import patch


SCRIPT = Path(__file__).resolve().parents[2] / "scripts/hass/search_links_view.py"
SPEC = importlib.util.spec_from_file_location("search_links_view", SCRIPT)
assert SPEC is not None and SPEC.loader is not None
VIEW = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(VIEW)

GOOD = b'<a class="result__a" href="https://example.org/about">About</a>'
FIXTURE = b'''<a class="featured result__a" href="https://example.org/about">About</a>
<a class="result__a" href="//duckduckgo.com/l/?uddg=https%3A%2F%2Fexample.net%2Fshop">Shop</a>
<a class="result__a" href="https://duckduckgo.com/l/?uddg=https%3A%2F%2Fexample.net%2Fshop">Duplicate</a>
<a class="result__a" href="http://example.com/">HTTP</a>
<a class="result__a" href="https://example.com/?q=1">Query</a>
<a class="result__aside" href="https://example.com/about">Other class</a>'''
PASS = "PASS search_links_view"
FAIL = "FAIL search_links_view"


class SearchLinksViewTests(unittest.TestCase):
    def setUp(self):
        temporary = tempfile.TemporaryDirectory()
        self.addCleanup(temporary.cleanup)
        self.root = Path(temporary.name).resolve()
        self.page = self.root / "saved-page.html"

    def cli(self, *args):
        return subprocess.run(
            [sys.executable, "-B", str(SCRIPT), *args],
            cwd=self.root, capture_output=True, text=True, timeout=10,
        )

    def run_page(self, path=None, limit="10"):
        return self.cli("--page", str(path or self.page), "--limit", limit)

    def run_main(self):
        stdout, stderr = io.StringIO(), io.StringIO()
        with redirect_stdout(stdout), redirect_stderr(stderr):
            code = VIEW.main(["--page", str(self.page), "--limit", "10"])
        return subprocess.CompletedProcess([], code, stdout.getvalue(), stderr.getvalue())

    def assert_trailer(self, result, code, trailer):
        self.assertEqual(result.returncode, code)
        self.assertEqual(result.stderr, "")
        lines = result.stdout.splitlines()
        self.assertTrue(lines)
        self.assertEqual(lines[-1], trailer)
        return lines[:-1]

    def assert_finding(self, result, reason, *info):
        self.assertEqual(self.assert_trailer(result, 1, FAIL), [*info, f"FAIL {reason}"])

    def test_c1_full_pass(self):
        # A valid saved page (including malformed UTF-8) must get a PASS trailer.
        self.page.write_bytes(b"\xff" + GOOD)
        self.assert_trailer(self.run_page(), 0, PASS)

    def test_c2_findings_trailer(self):
        # A generic finding needs both the reason line and the failure trailer.
        self.assert_finding(self.run_page(), "unreadable-input")

    def test_c2_1_unsafe_input(self):
        # Do not follow file symlinks, open a directory, or hang reading a FIFO.
        self.page.write_bytes(GOOD)
        link = self.root / "alias.html"
        link.symlink_to(self.page)
        fifo = self.root / "pipe"
        os.mkfifo(fifo)
        for path in (link, self.root, fifo):
            with self.subTest(kind=path.name):
                self.assert_finding(self.run_page(path), "unsafe-input")

    def test_c2_2_unreadable_input(self):
        # A regular file can pass the metadata check but fail to open.
        self.page.write_bytes(GOOD)
        with patch.object(VIEW.os, "open", side_effect=PermissionError(str(self.page))) as open_file:
            result = self.run_main()
        open_file.assert_called_once()
        self.assert_finding(result, "unreadable-input")

    def test_c2_3_too_large(self):
        # A file at the cap is allowed; a file one byte over must not be parsed.
        cap = 2 * 1024 * 1024
        with self.page.open("wb") as stream:
            stream.write(GOOD)
            stream.truncate(cap)
        self.assert_trailer(self.run_page(), 0, PASS)
        with self.page.open("ab") as stream:
            stream.write(b" ")
        self.assert_finding(self.run_page(), "too-large")

    def test_c2_4_parse_error(self):
        # A parser failure must not leak exception text or print partial counts.
        self.page.write_bytes(GOOD)
        with patch.object(VIEW.research_hermes, "_Links") as parser:
            parser.return_value.feed.side_effect = ValueError("synthetic parser detail")
            self.assert_finding(self.run_main(), "parse-error")
        parser.assert_called_once_with(10)

    def test_c2_5_no_links(self):
        # Seeing a result anchor is not sufficient if NPP rejects its URL.
        self.page.write_bytes(b'<a class="result__a" href="http://example.org/about">About</a>')
        self.assert_finding(self.run_page(), "no-links", "anchors 1", "kept 0", "dropped 1", "hosts 0")

    def test_c3_usage_exit_2(self):
        # Usage errors should not reach the findings path or print on stdout.
        for args in ((), ("--page", str(self.page)), ("--limit", "10"),
                     ("--page", str(self.page), "--limit", "1", "--unknown"),
                     *(("--page", str(self.page), "--limit", value)
                       for value in ("0", "51", "1.5"))):
            with self.subTest(args=args):
                result = self.cli(*args)
                self.assertEqual(result.returncode, 2)
                self.assertEqual(result.stdout, "")
                self.assertTrue(result.stderr.startswith("usage:"))

    def test_c4_read_only(self):
        # Even a transient write to the input directory can change its mtime.
        fixtures = self.root / "input"
        fixtures.mkdir()
        page = fixtures / self.page.name
        page.write_bytes(GOOD)
        before = (page.read_bytes(), page.stat().st_mtime_ns, fixtures.stat().st_mtime_ns)
        self.assert_trailer(self.run_page(page), 0, PASS)
        self.assertEqual((page.read_bytes(), page.stat().st_mtime_ns, fixtures.stat().st_mtime_ns), before)
        self.assertEqual(list(fixtures.iterdir()), [page])

    def test_c5_no_private_values(self):
        # Debug output could leak markup, parsed URLs, or arguments on a usage error.
        host = "canary.example.org"
        text = "planted-anchor-canary"
        self.page.write_text(
            f'<a class="result__a" href="https://{host}/one">{text}</a>'
            f'<a class="result__a" href="https://{host}/two">{text}</a>', encoding="utf-8",
        )
        success = self.run_page(limit="50")
        self.assertEqual(self.assert_trailer(success, 0, PASS),
                         ["anchors 2", "kept 2", "dropped 0", "hosts 1"])
        usage = self.cli("--page", str(self.page), "--limit", str(self.page))
        self.assertEqual((usage.returncode, usage.stdout), (2, ""))
        for result in (success, usage):
            for canary in (host, text, str(self.page)):
                self.assertNotIn(canary, result.stdout + result.stderr)

    def test_c6_fixture_page(self):
        # Redirect unwrapping, deduplication, URL filtering and class matching all affect the totals.
        self.page.write_bytes(FIXTURE)
        self.assertEqual(self.assert_trailer(self.run_page(), 0, PASS),
                         ["anchors 5", "kept 2", "dropped 3", "hosts 2"])

    def test_c7_limit(self):
        # The keep limit must not cap the independent result-anchor tally.
        self.page.write_bytes(FIXTURE)
        self.assertEqual(self.assert_trailer(self.run_page(limit="1"), 0, PASS),
                         ["anchors 5", "kept 1", "dropped 4", "hosts 1"])

    def test_c8_no_links(self):
        # A valid link of another class does not count as a search result.
        self.page.write_bytes(b'<a class="other" href="https://example.org/about">About</a>')
        self.assert_finding(self.run_page(), "no-links", "anchors 0", "kept 0", "dropped 0", "hosts 0")
