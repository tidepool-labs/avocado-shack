"""Offline CLI contract for the S10 edit-to-render field check."""

from contextlib import redirect_stderr, redirect_stdout
import importlib.util
import io
from pathlib import Path
import subprocess
import sys
from tempfile import TemporaryDirectory
from textwrap import dedent, indent
import unittest
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[2]
SCRIPT = ROOT / "scripts/hass/npp_edit_field_reach.py"
SPEC = importlib.util.spec_from_file_location("npp_edit_field_reach", SCRIPT)
assert SPEC is not None and SPEC.loader is not None
CHECK = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(CHECK)

PASS = "PASS npp_edit_field_reach"
FAIL = "FAIL npp_edit_field_reach"
FIELDS = ("category", "maker", "makerTown", "name", "priceUnit", "rewrite", "sellingPrice", "supplier")
ALL_READ = '''\
class ProductionStages:
    def render_listing(self, listing):
        listing['category'], listing.get('name', None), listing['rewrite']
        self._picture(listing)
        self._candidate(listing=listing)

    def _picture(self, listing):
        listing['sellingPrice'], listing['priceUnit']

    def _candidate(self, listing):
        listing.get('supplier'), listing.get('maker'), listing['makerTown']
'''


class NppEditFieldReachTests(unittest.TestCase):
    def fixture_run(self, source=ALL_READ):
        with TemporaryDirectory(dir=ROOT) as directory:
            stages = Path(directory) / "stages.py"
            if source is not None:
                stages.write_text(source, encoding="utf-8")
            with patch.object(CHECK, "STAGES_PATH", stages):
                out, err = io.StringIO(), io.StringIO()
                with redirect_stdout(out), redirect_stderr(err):
                    code = CHECK.main([])
        return code, out.getvalue().splitlines(), err.getvalue()

    def cli_run(self, *args):
        return subprocess.run([sys.executable, "-B", str(SCRIPT), *args], cwd=ROOT,
                              capture_output=True, text=True, timeout=15)

    def assert_outcome(self, run, expected_code, trailer):
        code, lines, stderr = run
        self.assertEqual(code, expected_code)
        self.assertEqual(stderr, "")
        self.assertTrue(lines)
        self.assertEqual(lines[-1], trailer)
        return lines[:-1]

    def test_c1_full_pass(self):
        # A fully covered fixture must not inherit the live source's failing exit or trailer.
        self.assert_outcome(self.fixture_run(), 0, PASS)

    def test_c2_findings_trailer(self):
        # Independent findings must not short-circuit one another or leave a success status.
        source = ALL_READ.replace("listing['rewrite']", "listing[variable]") + "        consume(listing)\n"
        lines = self.assert_outcome(self.fixture_run(source), 1, FAIL)
        self.assertCountEqual([line for line in lines if line.startswith("FAIL ")], [
            "FAIL dynamic-read", "FAIL listing-escapes consume", "FAIL unread-field rewrite",
        ])

    def test_c2_1_unread_field(self):
        # Reads in other methods/classes cannot mask omissions from the three render methods.
        source = ALL_READ.replace("listing['rewrite']", "None").replace("listing['makerTown']", "None")
        source += "\n    def unrelated(self, listing):\n        listing['makerTown']\n\n"
        source += dedent('''\
            class Other:
                def render_listing(self, listing):
                    listing['rewrite']
            ''')
        lines = self.assert_outcome(self.fixture_run(source), 1, FAIL)
        self.assertEqual([line for line in lines if line.startswith("FAIL ")],
                         ["FAIL unread-field makerTown", "FAIL unread-field rewrite"])
        self.assertIn("field makerTown read=no", lines)
        self.assertIn("field rewrite read=no", lines)

    def test_c2_2_parse_error(self):
        # Unavailable, invalid, incomplete or empty render evidence cannot yield field lines or PASS.
        methods = ("render_listing", "_picture", "_candidate")
        cases = {
            "missing-file": None,
            "syntax": "class ProductionStages(",
            "missing-class": ALL_READ.replace("ProductionStages", "OtherStages"),
            "no-read-fields": "class ProductionStages:\n" + "".join(
                f"    def {method}(self, listing): pass\n" for method in methods),
        }
        for method in methods:
            cases[f"missing-{method}"] = ALL_READ.replace(f"def {method}(", "def unrelated(")
        for case, source in cases.items():
            with self.subTest(case=case):
                lines = self.assert_outcome(self.fixture_run(source), 1, FAIL)
                self.assertEqual(lines, ["FAIL parse-error"])

    def test_c2_3_dynamic_read(self):
        # Each syntax can hide a key; multiple opaque reads still produce one finding.
        for suffix in ("listing[key]", "listing.get(key, None)", "listing[0]; listing.get(key)"):
            with self.subTest(expression=suffix):
                lines = self.assert_outcome(self.fixture_run(ALL_READ + f"        {suffix}\n"), 1, FAIL)
                self.assertEqual([line for line in lines if line.startswith("FAIL ")], ["FAIL dynamic-read"])

    def test_c2_4_listing_escapes(self):
        # Match the whole callee, check keyword arguments, and order calls by source (not AST walk order).
        source = ALL_READ.replace("        self._picture(listing)", indent(dedent('''\
            if condition:
                tools._picture(listing)
            forward(item=listing)
            self._picture(listing)
            '''), "        ").rstrip())
        source += "        self.forward(listing, item=listing)\n"
        lines = self.assert_outcome(self.fixture_run(source), 1, FAIL)
        self.assertEqual([line for line in lines if line.startswith("FAIL ")], [
            "FAIL listing-escapes tools._picture", "FAIL listing-escapes forward", "FAIL listing-escapes self.forward",
        ])

    def test_c2_5_check_error(self):
        # A failed edit read must be refused without leaking its exception text.
        with patch.object(CHECK.edits, "read", side_effect=RuntimeError("synthetic private detail")) as read:
            lines = self.assert_outcome(self.fixture_run(), 1, FAIL)
        read.assert_called_once()
        self.assertEqual(lines, ["FAIL check-error"])

    def test_c3_usage_exit_2(self):
        # Option parsing must not silently run the audit, even for argparse's usual help option.
        for arg in ("unexpected", "--unknown", "--help", "--"):
            with self.subTest(arg=arg):
                result = self.cli_run(arg)
                self.assertEqual(result.returncode, 2)
                self.assertEqual(result.stdout, "")
                self.assertIn("error: unrecognized arguments:", result.stderr.splitlines()[-1])

    def test_c4_read_only(self):
        # Catch cache, report or other writes into either repo tree, including added filenames.
        def snapshot():
            entries = {}
            for name in ("hass", "storefront-mockup"):
                root = ROOT / name
                for path in (root, *root.rglob("*")):
                    info = path.lstat()
                    entries[path.relative_to(ROOT)] = (info.st_size, info.st_mtime_ns)
            return entries

        before = snapshot()
        result = self.cli_run()
        self.assert_outcome((result.returncode, result.stdout.splitlines(), result.stderr), 1, FAIL)
        self.assertEqual(snapshot(), before)

    def test_c5_output_shape(self):
        # Debug/progress output, leaked values, and noisy imports break the CLI's machine-readable output.
        result = self.cli_run()
        lines = self.assert_outcome((result.returncode, result.stdout.splitlines(), result.stderr), 1, FAIL)
        for line in lines:
            self.assertRegex(line, r"^(field [A-Za-z_]\w* read=(yes|no)|FAIL unread-field [A-Za-z_]\w*)$")

    def test_c6_fixture(self):
        # Both lookup syntaxes and all three methods must count, without importing or running the fixture.
        lines = self.assert_outcome(self.fixture_run("raise AssertionError\n" + ALL_READ), 0, PASS)
        self.assertEqual(lines, [f"field {field} read=yes" for field in FIELDS])

    def test_c7_live_pins(self):
        # Measure the default repo source against actual checked grammar bytes, not hard-coded fixture reach.
        result = self.cli_run()
        lines = self.assert_outcome((result.returncode, result.stdout.splitlines(), result.stderr), 1, FAIL)
        self.assertEqual(lines, [
            "field category read=yes",
            "field maker read=yes",
            "field makerTown read=no",
            "field name read=yes",
            "field priceUnit read=yes",
            "field rewrite read=no",
            "field sellingPrice read=yes",
            "field supplier read=yes",
            "FAIL unread-field makerTown",
            "FAIL unread-field rewrite",
        ])
