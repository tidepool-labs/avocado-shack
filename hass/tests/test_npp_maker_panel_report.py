"""Behavioral contract for the offline NPP maker-panel report."""

from contextlib import redirect_stderr, redirect_stdout
import importlib.util
import io
import json
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import patch


ROOT = Path(__file__).resolve().parents[2]
SCRIPT = ROOT / "scripts/hass/npp_maker_panel_report.py"
PASS = "PASS npp_maker_panel_report"
FAIL = "FAIL npp_maker_panel_report"
STORY_ORDINALS = (1, 2, 3, 4, 5, 6, 9, 11, 12, 13, 14, 15, 16, 17, 19, 24, 26)

spec = importlib.util.spec_from_file_location("npp_maker_panel_report", SCRIPT)
assert spec is not None and spec.loader is not None
report = importlib.util.module_from_spec(spec)
spec.loader.exec_module(report)


def summary(makers, name=0, place=0, story=0, origin=0):
    return [f"makers {makers}", f"unshown-name {name}", f"unshown-place {place}",
            f"unshown-story {story}", f"unshown-origin {origin}"]


class MakerPanelReportTests(unittest.TestCase):
    def setUp(self):
        temporary = tempfile.TemporaryDirectory(dir=ROOT)
        self.addCleanup(temporary.cleanup)
        self.tmp = Path(temporary.name)
        self.makers = self.tmp / "makers.json"

    def write_rows(self, rows):
        self.makers.write_text(json.dumps({"makers": rows}), encoding="utf-8")

    def invoke(self, path=None):
        stdout, stderr = io.StringIO(), io.StringIO()
        with patch.object(report, "MAKERS", path if path is not None else self.makers):
            with redirect_stdout(stdout), redirect_stderr(stderr):
                code = report.main([])
        return code, stdout.getvalue(), stderr.getvalue()

    def subprocess_run(self, *args):
        result = subprocess.run([sys.executable, "-B", str(SCRIPT), *args],
                                cwd=self.tmp, capture_output=True, text=True, timeout=10)
        return result.returncode, result.stdout, result.stderr

    def assert_report(self, result, code, trailer):
        actual_code, stdout, stderr = result
        self.assertEqual(actual_code, code)
        self.assertEqual(stderr, "")
        lines = stdout.splitlines()
        self.assertTrue(lines)
        self.assertEqual(lines[-1], trailer)
        return lines[:-1]

    def test_c1_full_pass(self):
        # Empty/absent text is not a failed predicate, even across multiple rows.
        self.write_rows({"blank": {"name": "", "place": "", "story": ""},
                         "no-story": {"name": "Jam Maker", "place": "Springfield, CA"}})
        with patch.object(report.validate, "_panel_clean", wraps=report.validate._panel_clean) as check:
            lines = self.assert_report(self.invoke(), 0, PASS)
        self.assertEqual(lines, summary(2))
        self.assertNotIn("", [call.args[0] for call in check.call_args_list])

    def test_c2_findings_trailer(self):
        # Multiple findings must produce one failed trailer, not one per maker.
        row = {"name": "Jam Maker", "place": "Springfield, CA", "story": "Certified organic."}
        self.write_rows({"one": row, "two": row})
        lines = self.assert_report(self.invoke(), 1, FAIL)
        self.assertEqual(lines, summary(2, story=2) + ["FAIL panel-unshown 1 story", "FAIL panel-unshown 2 story"])

    def test_c2_1_input_unsafe(self):
        # A valid target must still not be followed; neither may a dangling link.
        self.write_rows({})
        for target in (self.makers, self.tmp / "missing"):
            with self.subTest(target_exists=target.exists()):
                link = self.tmp / ("link-" + target.name)
                link.symlink_to(target)
                lines = self.assert_report(self.invoke(link), 1, FAIL)
                self.assertEqual(lines, ["FAIL input-unsafe makers"])
        lines = self.assert_report(self.invoke(self.tmp), 1, FAIL)
        self.assertEqual(lines, ["FAIL input-unsafe makers"])

    def test_c2_2_input_too_large(self):
        # The size guard must win before invalid UTF-8 or JSON is decoded.
        self.makers.write_bytes(b"\xff" * 11)
        with patch.object(report, "MAKERS_CAP", 10):
            lines = self.assert_report(self.invoke(), 1, FAIL)
        self.assertEqual(lines, ["FAIL input-too-large makers"])

    def test_c2_3_input_unreadable(self):
        # Missing, undecodable, malformed and ill-shaped data fail closed.
        for label, raw in (
            ("missing", None), ("utf8", b"\xff"), ("json", b"{"),
            ("top-level", b"[]"), ("mapping", b'{"makers": []}'),
            ("row", b'{"makers": {"x": []}}'),
            ("required", b'{"makers": {"x": {"place": ""}}}'),
            ("place-type", b'{"makers": {"x": {"name": "", "place": 0}}}'),
            ("story-type", b'{"makers": {"x": {"name": "", "place": "", "story": null}}}'),
            ("url-type", b'{"makers": {"x": {"name": "", "place": "", "url": 1}}}'),
        ):
            with self.subTest(label=label):
                path = self.tmp / (label + ".json")
                if raw is not None:
                    path.write_bytes(raw)
                with patch.object(report.validate, "_panel_clean") as check:
                    lines = self.assert_report(self.invoke(path), 1, FAIL)
                self.assertEqual(lines, ["FAIL input-unreadable makers"])
                check.assert_not_called()

    def test_c2_4_panel_unshown(self):
        # Swapping field order or sorting the maker keys changes the findings.
        self.write_rows({"z": {"story": "Certified organic.", "name": "Organic Jam", "place": ""},
                         "a": {"name": "Test Orchard", "place": "Organic County"}})
        lines = self.assert_report(self.invoke(), 1, FAIL)
        self.assertEqual(lines, summary(2, name=1, place=1, story=1, origin=1) + [
            "FAIL panel-unshown 1 name", "FAIL panel-unshown 1 story",
            "FAIL panel-unshown 2 place", "FAIL origin-unshown 2",
        ])

    def test_c2_5_origin_unshown(self):
        # Check both halves of the origin rule and place origin after field lines.
        self.write_rows({
            "z": {"name": "Jam Maker", "place": "Lineville", "story": "Certified organic."},
            "a": {"name": "Jam Maker", "place": "Placeville", "story": "Certified organic."},
        })
        real_clean = report.validate._panel_clean

        def clean(value):
            if value in {"Based in Lineville", "Placeville"}:
                return False
            return real_clean(value)

        with patch.object(report.validate, "_panel_clean", side_effect=clean):
            lines = self.assert_report(self.invoke(), 1, FAIL)
        self.assertEqual(lines, summary(2, place=1, story=2, origin=2) + [
            "FAIL panel-unshown 1 story", "FAIL origin-unshown 1",
            "FAIL panel-unshown 2 place", "FAIL panel-unshown 2 story", "FAIL origin-unshown 2",
        ])

    def test_c2_6_check_error(self):
        # Exceptions must not become PASS, a traceback or a policy finding.
        self.write_rows({"one": {"name": "Jam Maker", "place": "Springfield, CA"}})
        with patch.object(report.validate, "_panel_clean", side_effect=RuntimeError("fixture marker")):
            lines = self.assert_report(self.invoke(), 1, FAIL)
        self.assertEqual(lines, summary(1) + ["FAIL check-error"])

    def test_c3_usage_exit_2(self):
        # Even argparse's usual help flag and end-of-options marker are arguments.
        for arg in ("--unknown", "extra", "--help", "--", ""):
            with self.subTest(arg=arg):
                code, stdout, stderr = self.subprocess_run(arg)
                self.assertEqual((code, stdout), (2, ""))  # No stdout trailer on usage errors.
                self.assertIn("usage:", stderr)
                self.assertIn("error:", stderr)

    def test_c4_read_only(self):
        # A report must not rewrite catalog files or put caches in either tree.
        def snapshot():
            result = {}
            for tree in (ROOT / "hass", ROOT / "storefront-mockup"):
                for path in (tree, *tree.rglob("*")):
                    info = path.lstat()
                    result[path.relative_to(ROOT)] = (info.st_size, info.st_mtime_ns)
            return result

        before = snapshot()
        self.assert_report(self.subprocess_run(), 1, FAIL)
        self.assertEqual(snapshot(), before)
        self.assertEqual(list(self.tmp.iterdir()), [])

    def test_c5_output_shape(self):
        # Neither accepted text nor a rejected claim or key may leak to either stream.
        self.write_rows({"report-key-marker": {
            "name": "Panel Marker", "place": "Springfield, CA", "story": "Certified organic, story marker.",
            "url": "https://example.org/ignored-marker", "status": "inert-marker",
        }})
        lines = self.assert_report(self.invoke(), 1, FAIL)
        self.assertEqual(lines, summary(1, story=1) + ["FAIL panel-unshown 1 story"])

    def test_c6_fixture_pass(self):
        # A plain one-maker fixture must emit every count, including zeroes.
        self.write_rows({"fixture": {"name": "Test Maker", "place": "Springfield, CA",
                                     "story": "Makes jam in small batches.", "url": "https://example.org/"}})
        lines = self.assert_report(self.invoke(), 0, PASS)
        self.assertEqual(lines, summary(1))

    def test_c7_live_pins(self):
        # Pin the checked-in catalog's counts and ordinal findings, not its text.
        lines = self.assert_report(self.subprocess_run(), 1, FAIL)
        self.assertEqual(lines, summary(26, story=17) + [f"FAIL panel-unshown {n} story" for n in STORY_ORDINALS])
