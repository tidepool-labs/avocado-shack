"""Offline CLI contract for the footerless S4 About-page observations."""

from contextlib import redirect_stderr, redirect_stdout
import importlib.util
from io import StringIO
from pathlib import Path
import re
import subprocess
import sys
from tempfile import TemporaryDirectory
import unittest
from unittest.mock import patch


ROOT = Path(__file__).resolve().parents[2]
SCRIPT = ROOT / "scripts/hass/npp_about_page_paths.py"
PASS = "PASS npp_about_page_paths"
FAIL = "FAIL npp_about_page_paths"
REFUSAL = "not-the-makers-own-site"
ABOUT_WITH_SUFFIXES = r"(?:^|/)(?:about(?:-us)?|(?:our|the)-story|who-we-are)(?:\.html?)?/?$"
WIDER_ABOUT = re.compile(ABOUT_WITH_SUFFIXES, re.I)


class AboutPagePathsTests(unittest.TestCase):
    def setUp(self):
        self.temp = Path(self.enterContext(TemporaryDirectory()))
        spec = importlib.util.spec_from_file_location("npp_about_page_paths", SCRIPT)
        assert spec is not None and spec.loader is not None
        self.tool = importlib.util.module_from_spec(spec)
        with patch.object(sys, "path", sys.path.copy()):
            spec.loader.exec_module(self.tool)

    def run_main(self, code, trailer):
        stdout, stderr = StringIO(), StringIO()
        with redirect_stdout(stdout), redirect_stderr(stderr):
            actual = self.tool.main([])
        self.assertEqual(actual, code, stdout.getvalue())
        self.assertEqual(stderr.getvalue(), "")
        lines = stdout.getvalue().splitlines()
        self.assertEqual(lines[-1:], [trailer])
        return lines[:-1]

    def invoke(self, *args):
        return subprocess.run(
            [sys.executable, "-B", str(SCRIPT), *args], cwd=self.temp,
            capture_output=True, text=True, timeout=10,
        )

    def live_lines(self, result):
        self.assertEqual(result.returncode, 1, result.stderr)
        self.assertEqual(result.stderr, "")
        lines = result.stdout.splitlines()
        self.assertEqual(lines[-1:], [FAIL])
        return lines[:-1]

    def test_c1_full_pass(self):
        # A valid matrix must not fail or omit a page/ownership check.
        research = self.tool.research
        with (patch.object(research, "ABOUT", WIDER_ABOUT),
              patch.object(research, "parse_page", wraps=research.parse_page) as parse,
              patch.object(research, "_own_site", wraps=research._own_site) as own):
            lines = self.run_main(0, PASS)
        self.assertEqual(len(lines), 14)
        self.assertEqual(parse.call_count, 28)
        self.assertEqual(own.call_count, 14)

    def test_c2_findings_trailer(self):
        # Findings of different kinds accumulate in path order and fail the run.
        with patch.object(self.tool.research, "ABOUT", re.compile(r"/contact$")):
            lines = self.run_main(1, FAIL)
        self.assertEqual(
            [line for line in lines if line.startswith("FAIL ")],
            [f"FAIL about-page-refused {i}" for i in range(12)]
            + ["FAIL control-accepted 13"],
        )

    def test_c2_1_about_page_refused(self):
        # A recorded About link cannot make an ownership refusal pass.
        research = self.tool.research
        real_own_site = research._own_site

        def refuse_one(page, *args):
            reason = real_own_site(page, *args)
            return "town-unconfirmed" if page.url.endswith("/about.htm") else reason

        with (patch.object(research, "ABOUT", WIDER_ABOUT),
              patch.object(research, "_own_site", side_effect=refuse_one)):
            lines = self.run_main(1, FAIL)
        self.assertIn("path 10 own=town-unconfirmed link=yes", lines)
        self.assertEqual([line for line in lines if line.startswith("FAIL ")],
                         ["FAIL about-page-refused 10"])

    def test_c2_2_control_accepted(self):
        # Accepting even one control is not a pass when the About cases all work.
        with patch.object(self.tool.research, "ABOUT", re.compile(ABOUT_WITH_SUFFIXES + r"|/contact$", re.I)):
            lines = self.run_main(1, FAIL)
        self.assertIn("path 13 own=official link=yes", lines)
        self.assertEqual([line for line in lines if line.startswith("FAIL ")],
                         ["FAIL control-accepted 13"])

    def test_c2_3_check_error(self):
        # A broken check is neither a silent skip nor a reason to leak exception text.
        research = self.tool.research
        for name, call in (("parse_page", 1), ("parse_page", 2), ("_own_site", 1)):
            with self.subTest(name=name, call=call):
                real = getattr(research, name)
                with (patch.object(research, "ABOUT", WIDER_ABOUT),
                      patch.object(research, name) as checked):
                    def fail_once(*args):
                        if checked.call_count == call:
                            raise ValueError("synthetic exception detail")
                        return real(*args)

                    checked.side_effect = fail_once
                    lines = self.run_main(1, FAIL)
                self.assertEqual(lines[0], "FAIL check-error")
                self.assertEqual(len(lines), 14)
                self.assertEqual(lines[-1], f"path 13 own={REFUSAL} link=no")
                self.assertEqual([line for line in lines if line.startswith("FAIL ")],
                                 ["FAIL check-error"])
                self.assertNotIn("synthetic exception detail", "\n".join(lines))

    def test_c3_usage_exit_2(self):
        # An argument must not be treated as help, ignored, or run the audit.
        for arg in ("extra", "--unknown", "--help", "--"):
            with self.subTest(arg=arg):
                result = self.invoke(arg)
                self.assertEqual(result.returncode, 2)
                self.assertEqual(result.stdout, "")
                self.assertTrue(result.stderr.startswith("usage: "))
                self.assertEqual(result.stderr.splitlines()[-1],
                                 f"npp_about_page_paths.py: error: unrecognized arguments: {arg}")

    def test_c4_read_only(self):
        # Rewriting even the same bytes or adding artifacts must change this snapshot.
        def snapshot():
            entries = {}
            for name in ("hass", "storefront-mockup"):
                tree = ROOT / name
                for entry in (tree, *tree.rglob("*")):
                    stat = entry.lstat()
                    entries[entry.relative_to(ROOT)] = (stat.st_size, stat.st_mtime_ns)
            return entries

        before = snapshot()
        result = self.invoke()
        self.assertEqual(snapshot(), before)
        self.live_lines(result)

    def test_c5_output_shape(self):
        # Uncontracted progress messages, blank lines or diagnostics break consumers.
        lines = self.live_lines(self.invoke())
        shape = re.compile(r"(?:path (?:[0-9]|1[0-3]) own=[a-z-]+ link=(?:yes|no)"
                           r"|FAIL about-page-refused (?:[0-9]|1[01])"
                           r"|FAIL control-accepted 1[23]|FAIL check-error)")
        for line in lines:
            self.assertIsNotNone(shape.fullmatch(line), line)

    def test_c6_fixture(self):
        # Both observations must react to the real parser/ownership regex seam.
        with patch.object(self.tool.research, "ABOUT", WIDER_ABOUT):
            lines = self.run_main(0, PASS)
        self.assertEqual(lines, [f"path {i} own=official link=yes" for i in range(12)]
                         + [f"path {i} own={REFUSAL} link=no" for i in (12, 13)])
        with patch.object(self.tool.research, "ABOUT", re.compile(r"(?!)")):
            lines = self.run_main(1, FAIL)
        expected = []
        for i in range(14):
            expected.append(f"path {i} own={REFUSAL} link=no")
            if i < 12:
                expected.append(f"FAIL about-page-refused {i}")
        self.assertEqual(lines, expected)

    def test_c7_live_pins(self):
        # Unpatched main sees only the four measured suffix refusals, in order.
        self.assertEqual(self.tool.PATHS, (
            "/about", "/about/", "/about-us", "/our-story", "/who-we-are", "/pages/about",
            "/en/about/", "/About", "/about.html", "/about-us.html", "/about.htm",
            "/our-story.html", "/", "/contact",
        ))
        expected = [f"path {i} own=official link=yes" for i in range(8)]
        for i in range(8, 14):
            expected.append(f"path {i} own={REFUSAL} link=no")
            if i < 12:
                expected.append(f"FAIL about-page-refused {i}")
        self.assertEqual(self.live_lines(self.invoke()), expected)
