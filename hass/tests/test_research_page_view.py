"""Fixture-only tests at the saved-page CLI boundary."""

from contextlib import redirect_stderr, redirect_stdout
import importlib.util
from io import StringIO
import os
from pathlib import Path
import re
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import patch


SCRIPT = Path(__file__).resolve().parents[2] / "scripts/hass/research_page_view.py"
SPEC = importlib.util.spec_from_file_location("research_page_view", SCRIPT)
assert SPEC is not None and SPEC.loader is not None
VIEW = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(VIEW)

PASS = "PASS research_page_view"
FAIL = "FAIL research_page_view"
URL = "https://www.example.com/fixture-maker-canary/"
VISIBLE = "<p>Fixture Maker makes jam.</p>"
ZERO_COUNTS = ["titles 0", "ownership 0", "blocks 0", "about 0",
               "about-same-site 0", "about-other-site 0"]


class ResearchPageViewTests(unittest.TestCase):
    def setUp(self):
        temporary = tempfile.TemporaryDirectory()
        self.addCleanup(temporary.cleanup)
        self.root = Path(temporary.name).resolve()
        self.html = self.root / "fixture-input-canary.html"

    def invoke(self, *args):
        return subprocess.run([sys.executable, "-B", str(SCRIPT), *args],
                              cwd=self.root, text=True, capture_output=True, timeout=10)

    def options(self, path=None, url=URL, retrieved="2024-02-29"):
        return ("--html", str(self.html if path is None else path), "--url", url,
                "--retrieved", retrieved)

    def saved(self, markup, *, url=URL):
        self.html.write_bytes(markup.encode("utf-8"))
        return self.invoke(*self.options(url=url))

    def assert_outcome(self, result, status, trailer):
        self.assertEqual(result.returncode, status, result.stderr)
        self.assertEqual(result.stderr, "")
        lines = result.stdout.splitlines()
        self.assertTrue(lines)
        self.assertEqual(lines[-1], trailer)
        return lines[:-1]

    def assert_findings(self, result, *reasons):
        lines = self.assert_outcome(result, 1, FAIL)
        self.assertEqual([line for line in lines if line.startswith("FAIL ")],
                         [f"FAIL {reason}" for reason in reasons])
        self.assertNotIn(PASS, lines)
        return [line for line in lines if not line.startswith("FAIL ")]

    def test_c1_full_pass(self):
        # A wrapper that approximates the result but omits or moves PASS fails.
        lines = self.assert_outcome(self.saved(VISIBLE), 0, PASS)
        self.assertEqual(lines, ["titles 0", "ownership 0", "blocks 1", "about 0",
                                 "about-same-site 0", "about-other-site 0"])

    def test_c2_findings_trailer(self):
        # Independent checks must not short-circuit or lose the final failure.
        self.html.write_bytes(b"\xff")
        self.assertEqual(self.assert_findings(self.invoke(*self.options(url="not a URL")),
                                             "bad-url", "not-utf8"), [])

    def test_c2_1_unsafe_input(self):
        # Following symlinks or opening a FIFO as a normal file is unsafe.
        self.html.write_text(VISIBLE, encoding="utf-8")
        alias = self.root / "alias.html"
        alias.symlink_to(self.html)
        dangling = self.root / "dangling.html"
        dangling.symlink_to(self.root / "missing.html")
        fifo = self.root / "input.fifo"
        os.mkfifo(fifo)
        for path in (alias, dangling, self.root, fifo, self.root / "missing.html"):
            with self.subTest(name=path.name):
                self.assertEqual(self.assert_findings(self.invoke(*self.options(path=path)),
                                                     "unsafe-input"), [])

    def test_c2_2_too_large(self):
        # Count bytes, not characters; never report success on a truncated page.
        prefix = VISIBLE.encode("utf-8")
        remaining = VIEW.maker_site.MAX_BYTES - len(prefix)
        exact = prefix + b"\xc3\xa9" * (remaining // 2) + b" " * (remaining % 2)
        self.html.write_bytes(exact)
        self.assert_outcome(self.invoke(*self.options()), 0, PASS)
        self.html.write_bytes(exact + b" ")
        self.assertEqual(self.assert_findings(self.invoke(*self.options()), "too-large"), [])

    def test_c2_3_not_utf8(self):
        # Replacement decoding would keep the visible block and wrongly pass.
        self.html.write_bytes(VISIBLE.encode() + b"\xff")
        self.assertEqual(self.assert_findings(self.invoke(*self.options()), "not-utf8"), [])

    def test_c2_4_bad_url(self):
        # Reject even with good HTML; valid-looking URL syntax alone is insufficient.
        for url in ("https://fixture-address.local/", "http://example.com/", "https://[broken/about"):
            with self.subTest(url=url):
                self.assertEqual(self.assert_findings(self.saved(VISIBLE, url=url), "bad-url"), [])

    def test_c2_5_no_blocks(self):
        # A title, footer, and about link are not themselves citable blocks.
        result = self.saved('<head><title>Fixture Maker</title></head>'
                            '<a href="/about">About</a><footer>Fixture Maker LLC</footer>')
        self.assertEqual(self.assert_findings(result, "no-blocks"),
                         ["titles 1", "ownership 1", "blocks 0", "about 1",
                          "about-same-site 1", "about-other-site 0"])

    def test_c3_usage_exit_2(self):
        # Do not turn argparse usage errors into ordinary findings or echo argv.
        self.html.write_text(VISIBLE, encoding="utf-8")
        cases = [
            self.options()[:-2],
            (*self.options(), "--unknown", str(self.html)),
            (*self.options(), f"--help={self.html}"),
            *[self.options(retrieved=bad)
              for bad in ("2024-2-09", "20230229", "2023-02-29", "2024-W01-1", str(self.html))],
        ]
        for args in cases:
            with self.subTest(value=args[-1]):
                result = self.invoke(*args)
                self.assertEqual(result.returncode, 2)
                self.assertEqual(result.stdout, "")  # No last stdout line.
                self.assertTrue(result.stderr.startswith("usage: "))
                self.assertEqual(result.stderr.splitlines()[-1],
                                 f"{SCRIPT.name}: error: invalid arguments; see --help")
                self.assertNotIn(str(self.html), result.stderr)

    def test_c4_read_only(self):
        # Detect even transient sidecars and same-bytes rewrites.
        raw = (VISIBLE + "\r\n").encode("utf-8")
        self.html.write_bytes(raw)
        original_ns = self.html.stat().st_mtime_ns
        directory_ns = self.root.stat().st_mtime_ns
        self.assert_outcome(self.invoke(*self.options()), 0, PASS)
        self.assertEqual(self.html.read_bytes(), raw)
        self.assertEqual(self.html.stat().st_mtime_ns, original_ns)
        self.assertEqual(set(self.root.iterdir()), {self.html})
        self.assertEqual(self.root.stat().st_mtime_ns, directory_ns)

    def test_c5_no_private_values(self):
        # Exact counts expose leakage into the parser view even if raw text is
        # never printed. Distinct sentinels also catch raw output on failures.
        hidden = ['div hidden', 'div inert', 'div aria-hidden="TRUE"',
                  'div class="hidden"', 'div class="d-none"', 'div class="sr-only"',
                  'div class="visually-hidden"', 'div style="display: none"',
                  'div style="visibility: hidden"', 'div style="opacity: 0"',
                  'form', 'aside', 'template', 'noscript', 'svg', 'button',
                  'dialog', 'details', 'iframe', 'style', 'script']
        fixture = ('<head><title>fixture-title-canary</title>'
                   '<meta name="description" content="fixture-description-canary">'
                   '<meta property="og:description" content="fixture-og-description-canary"></head>'
                   '<p>fixture-visible-canary</p><footer>fixture-owner-canary</footer>'
                   '<a href="/fixture-public-link-canary/about">public link</a>')
        for index, tag in enumerate(hidden):
            closing_tag = tag.split()[0]
            fixture += (f'<{tag}><p>fixture-hidden-{index}-canary</p>'
                        f'<a href="/fixture-hidden-link-{index}-canary/about">link</a></{closing_tag}>')
        result = self.saved(fixture)
        self.assertEqual(self.assert_outcome(result, 0, PASS),
                         ["titles 1", "ownership 1", "blocks 1", "about 1",
                          "about-same-site 1", "about-other-site 0"])
        canaries = (*re.findall(r"fixture-[\w-]+-canary", fixture), URL, str(self.html))
        for value in canaries:
            self.assertNotIn(value, result.stdout + result.stderr)

        with patch.object(VIEW, "open_without_following", side_effect=PermissionError(str(self.html))):
            # A missing read permission must not leak the path or print PASS.
            stdout, stderr = StringIO(), StringIO()
            with redirect_stdout(stdout), redirect_stderr(stderr):
                status = VIEW.main(self.options())
        result = subprocess.CompletedProcess([], status, stdout.getvalue(), stderr.getvalue())
        self.assertEqual(self.assert_findings(result, "unsafe-input"), [])
        for value in canaries:
            self.assertNotIn(value, result.stdout + result.stderr)

    def test_c6_pinned_page(self):
        # Do not infer ownership or substitute a generic HTML text extractor.
        result = self.saved('<head><title>Harbor Lane</title>'
                            '<meta name="description" content="Not a block"></head>'
                            '<p>Harbor Lane makes jam.</p><div hidden><p>Hidden block</p></div>'
                            '<a href="/about">About</a><a href="https://other.com/about">Other</a>'
                            '<footer>Harbor Lane LLC owns and operates this site.</footer>'
                            '<script>Ignored script</script>', url="https://harborlane.com/")
        self.assertEqual(self.assert_outcome(result, 0, PASS),
                         ["titles 1", "ownership 1", "blocks 1", "about 2",
                          "about-same-site 1", "about-other-site 1"])

    def test_c7_script_only(self):
        # Script text must not rescue a page with no static visible blocks.
        result = self.saved('<script>const fixture = "<p>Not a block</p>";</script>')
        self.assertEqual(self.assert_findings(result, "no-blocks"), ZERO_COUNTS)

    def test_about_host_matching(self):
        # Strip one www. alias; don't collapse other subdomains or compare ports.
        result = self.saved(VISIBLE + '<a href="//example.com:443/about">Alias</a>'
                            '<a href="https://shop.example.com/about-us">Subdomain</a>'
                            '<a href="https://[broken/about">No host</a>')
        self.assertEqual(self.assert_outcome(result, 0, PASS),
                         ["titles 0", "ownership 0", "blocks 1", "about 3",
                          "about-same-site 1", "about-other-site 2"])

    def test_parser_refusal(self):
        # A parser rejection must stay private and not certify a partial parse.
        result = self.saved(VISIBLE + "<div>" * 129 + "fixture-nesting-canary")
        self.assertEqual(self.assert_findings(result, "unsafe-input"), [])


if __name__ == "__main__":
    unittest.main()
