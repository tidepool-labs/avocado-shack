"""Offline CLI contract and measured S4 footer-markup baseline."""

from contextlib import redirect_stderr, redirect_stdout
import importlib.util
import io
from pathlib import Path
import re
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import patch

from hass.npp import research

ROOT = Path(__file__).resolve().parents[2]
SCRIPT = ROOT / "scripts/hass/npp_footer_markup_forms.py"
SPEC = importlib.util.spec_from_file_location("npp_footer_markup_forms", SCRIPT)
assert SPEC is not None and SPEC.loader is not None
TOOL = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(TOOL)
PASS = "PASS npp_footer_markup_forms"
FAIL = "FAIL npp_footer_markup_forms"
VISIBLE = (0, 1, 2, 3, 4, 11, 13)
REFUSAL = "not-the-makers-own-site"


def footer_data(self, data):
    """Counterfactual: visible footer text goes to the footer, not to a block."""
    if self.stack and self.stack[-1][1] == "footer":
        for tag, region, text in reversed(self.stack):
            if tag == "footer" and region == "footer":
                text.append(data)
                return
    ORIGINAL_DATA(self, data)


ORIGINAL_DATA = research._Visible.handle_data


def tree_snapshot():
    snapshot = {}
    for name in ("hass", "storefront-mockup"):
        tree = ROOT / name
        for path in (tree, *tree.rglob("*")):
            info = path.lstat()
            snapshot[path.relative_to(ROOT)] = (info.st_size, info.st_mtime_ns)
    return snapshot


class FooterMarkupFormsTests(unittest.TestCase):
    def run_main(self):
        stdout, stderr = io.StringIO(), io.StringIO()
        with redirect_stdout(stdout), redirect_stderr(stderr):
            status = TOOL.main([])
        return status, stdout.getvalue(), stderr.getvalue()

    def run_cli(self, *args):
        with tempfile.TemporaryDirectory() as temporary:
            run = subprocess.run(
                [sys.executable, "-B", str(SCRIPT), *args], cwd=temporary,
                capture_output=True, text=True, timeout=10,
            )
        return run.returncode, run.stdout, run.stderr

    def assert_report(self, run, status, trailer):
        code, stdout, stderr = run
        self.assertEqual(code, status, stderr)
        self.assertEqual(stderr, "")
        lines = stdout.splitlines()
        self.assertTrue(lines, "missing report")
        self.assertEqual(lines[-1], trailer)
        return lines[:-1]

    def assert_findings(self, run, expected):
        lines = self.assert_report(run, 1, FAIL)
        self.assertEqual([line for line in lines if line.startswith("FAIL ")], expected)
        return lines

    def test_c1_full_pass(self):
        # Repaired parsing must not report a stale failure or stop before the controls.
        with patch.object(research._Visible, "handle_data", footer_data):
            lines = self.assert_report(self.run_main(), 0, PASS)
        self.assertEqual([int(line.split()[1]) for line in lines], list(range(14)))

    def test_c2_findings_trailer(self):
        # Distinct findings must accumulate in form order, not abort or return success.
        parse = research.parse_page

        def mixed(url, retrieved, html):
            html = html.replace("<footer>&copy;", "<footer>Published in")
            html = html.replace('<footer class="hidden">', '<footer>')
            return parse(url, retrieved, html)

        with patch.object(research, "parse_page", side_effect=mixed):
            lines = self.assert_findings(self.run_main(), [
                "FAIL footer-refused 0", "FAIL footer-text-lost 1",
                "FAIL footer-text-lost 3", "FAIL footer-text-lost 4",
                "FAIL footer-text-lost 11", "FAIL hidden-footer-accepted",
            ])
        self.assertEqual(lines[-1], "form 13 reason=official owner-lines=1")

    def test_c2_1_footer_text_lost(self):
        # A nonempty footer containing only nav text still lost the maker line.
        with patch.object(research._Visible, "handle_data", footer_data):
            parse = research.parse_page

            def nav_only(url, retrieved, html):
                if "<nav>" in html:
                    html = html.replace("<p>&copy; 2024 Miners Orchards.</p>", "")
                return parse(url, retrieved, html)

            with patch.object(research, "parse_page", side_effect=nav_only):
                lines = self.assert_findings(self.run_main(), ["FAIL footer-text-lost 11"])
        self.assertIn(f"form 11 reason={REFUSAL} owner-lines=1", lines)

    def test_c2_2_footer_refused(self):
        # Text with the maker name but without a copyright marker is seen, not accepted.
        parse = research.parse_page

        def without_marker(url, retrieved, html):
            return parse(url, retrieved, html.replace("<footer>&copy;", "<footer>Published in"))

        with (patch.object(research._Visible, "handle_data", footer_data),
              patch.object(research, "parse_page", side_effect=without_marker)):
            lines = self.assert_findings(self.run_main(), ["FAIL footer-refused 0"])
        self.assertIn(f"form 0 reason={REFUSAL} owner-lines=1", lines)

    def test_c2_3_hidden_footer_accepted(self):
        # Simulate lost hidden-class handling using the real parser and classifier.
        start = research._Visible.handle_starttag

        def ignoring_hidden(self, tag, attrs):
            return start(self, tag, [pair for pair in attrs if pair != ("class", "hidden")])

        with (patch.object(research._Visible, "handle_data", footer_data),
              patch.object(research._Visible, "handle_starttag", ignoring_hidden)):
            lines = self.assert_findings(self.run_main(), ["FAIL hidden-footer-accepted"])
        self.assertIn("form 12 reason=official owner-lines=1", lines)

    def test_c2_4_check_error(self):
        # Either boundary can raise: surface the failure without exception text and keep checking.
        for name in ("parse_page", "_own_site"):
            with self.subTest(name=name):
                real = getattr(research, name)

                def fail_first(*args):
                    if boundary.call_count == 1:
                        raise ValueError("synthetic diagnostic detail")
                    return real(*args)

                with (patch.object(research._Visible, "handle_data", footer_data),
                      patch.object(research, name, side_effect=fail_first) as boundary):
                    lines = self.assert_findings(self.run_main(), ["FAIL check-error"])
                self.assertEqual(boundary.call_count, 14)
                self.assertEqual(lines[0], "FAIL check-error")
                self.assertEqual(lines[1:], [line for line in lines if line.startswith("form ")])
                self.assertEqual([int(line.split()[1]) for line in lines[1:]], list(range(1, 14)))

    def test_c3_usage_exit_2(self):
        # Neither a stray argument nor a flag (including implicit help) may run the checks.
        for arg in ("fixture.html", "--unknown", "--help", "-h", "--"):
            with self.subTest(arg=arg):
                code, stdout, stderr = self.run_cli(arg)
                self.assertEqual(code, 2)
                self.assertEqual(stdout, "")
                self.assertEqual(stderr.splitlines()[-1],
                                 f"{SCRIPT.name}: error: unrecognized arguments: {arg}")

    def test_c4_read_only(self):
        # A persisted report or a write to pinned inputs would change the tree snapshot.
        before = tree_snapshot()
        self.assert_report(self.run_cli(), 1, FAIL)
        self.assertEqual(tree_snapshot(), before)

    def test_c5_output_shape(self):
        # Preserve the machine-readable grammar: no banners, warnings or extra rows.
        lines = self.assert_report(self.run_cli(), 1, FAIL)
        forms = []
        for line in lines:
            form = re.fullmatch(r"form ([0-9]+) reason=[a-z-]+ owner-lines=[0-9]+", line)
            if form:
                forms.append(int(form[1]))
            else:
                self.assertRegex(line, r"\AFAIL (?:footer-(?:text-lost|refused) [0-9]+|"
                                       r"hidden-footer-accepted|check-error)\Z")
        self.assertEqual(forms, list(range(14)))

    def test_c6_fixture(self):
        # Detect both directions at the parser seam, without stubbing the site verdict.
        end = research._Visible.handle_endtag

        def no_ownership(self, tag):
            end(self, tag)
            self.page.ownership.clear()

        with patch.object(research._Visible, "handle_data", footer_data):
            self.assert_report(self.run_main(), 0, PASS)
        with patch.object(research._Visible, "handle_endtag", no_ownership):
            lines = self.assert_findings(self.run_main(), [f"FAIL footer-text-lost {i}" for i in VISIBLE])
        self.assertEqual(lines[:2], [f"form 0 reason={REFUSAL} owner-lines=0", "FAIL footer-text-lost 0"])

    def test_c7_live_pins(self):
        # An S4 parser change must move this measured baseline, not a mocked result.
        parse = research.parse_page
        pages = []

        def observe(*args):
            page = parse(*args)
            pages.append(page)
            return page

        with patch.object(research, "parse_page", side_effect=observe):
            lines = self.assert_report(self.run_main(), 1, FAIL)
        expected = []
        for i in range(14):
            reason = "official" if i in (0, 2, 13) else REFUSAL
            count = 1 if i in (0, 2, 11, 13) else 0
            expected.append(f"form {i} reason={reason} owner-lines={count}")
            if i in (1, 3, 4, 11):
                expected.append(f"FAIL footer-text-lost {i}")
        self.assertEqual(lines, expected)
        self.assertEqual(len(pages), 14)
        self.assertEqual(pages[11].ownership, ["Home"])


if __name__ == "__main__":
    unittest.main()
