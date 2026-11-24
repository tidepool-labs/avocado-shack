"""Exercise the offline report CLI with synthetic content copies only."""

from contextlib import redirect_stderr, redirect_stdout
from datetime import date
import importlib.util
import io
import json
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import patch


SCRIPT = Path(__file__).resolve().parents[2] / "scripts/hass/content_availability_report.py"
TODAY = "2030-06-15"
PASS = "PASS content_availability_report"
FAIL = "FAIL content_availability_report"


def product(word, day=TODAY, **fields):
    return {"status": "active", "available": word, "available_on": day, **fields}


class ContentAvailabilityReportTests(unittest.TestCase):
    def setUp(self):
        temporary = tempfile.TemporaryDirectory()
        self.addCleanup(temporary.cleanup)
        self.root = Path(temporary.name).resolve()
        self.content = self.root / "synthetic-content-copy"
        self.content.mkdir()

    def write_doc(self, name, **fields):
        (self.content / f"{name}.json").write_text(
            json.dumps({"schemaVersion": 1, **fields}), encoding="utf-8",
        )

    def fixture(self, products, *, checked: str | None = TODAY, **store):
        if checked is not None:
            store["selection_checked_on"] = checked
        self.write_doc("products", products=products)
        self.write_doc("makers", makers={})
        self.write_doc("community")
        self.write_doc("store", **store)

    def cli(self, *args):
        return subprocess.run([sys.executable, "-B", str(SCRIPT), *args], cwd=self.root,
                              capture_output=True, text=True, timeout=10)

    def run_report(self, path=None):
        return self.cli("--content", str(self.content if path is None else path), "--today", TODAY)

    def assert_report(self, result, code=0, reasons=()):
        self.assertEqual(result.returncode, code, result.stderr)
        self.assertEqual(result.stderr, "")
        lines = result.stdout.splitlines()
        self.assertTrue(lines)
        self.assertEqual(lines[-1], PASS if code == 0 else FAIL)
        self.assertEqual([line for line in lines[:-1] if line.startswith("FAIL ")], list(reasons))
        return lines

    def test_c1_full_pass(self):
        # Exact normal report: tallying an inactive or malformed row as active changes it.
        self.fixture([
            product("yes", restock_on=TODAY), product("limited"), product("no"),
            {"status": "active"}, product("yes", status="hidden", restock_on=TODAY),
            product("no", status="held", restock_on=TODAY), None, ["not an object"],
        ], checked="2030-06-14")
        self.assertEqual(self.assert_report(self.run_report()), [
            "checked-on 1 days", "active 4", "state yes 1", "state limited 1", "state no 1",
            "last-confirmed 0", "no-word 1", "restock-set 1", "note restock-passed 0",
            "note restock-not-sold-out 1", "note restock-inactive 2", "note malformed 2", PASS,
        ])

    def test_c2_1_unsafe_input(self):
        # A directory symlink passes is_dir() alone; files and missing inputs also fail here.
        self.fixture([])
        link = self.root / "linked-copy"
        link.symlink_to(self.content, target_is_directory=True)
        for path in (link, self.content / "store.json", self.root / "missing-copy"):
            with self.subTest(case=path.name):
                lines = self.assert_report(self.run_report(path), 1, ("FAIL unsafe-input",))
                self.assertEqual(lines, ["FAIL unsafe-input", FAIL])

    def test_c2_2_content_invalid(self):
        # An invalid fourth document catches loaders that look only at the products.
        for raw in (b'{"schemaVersion":2}', b'{"schemaVersion":1,', b'\xff'):
            with self.subTest(raw=raw):
                self.fixture([])
                (self.content / "store.json").write_bytes(raw)
                lines = self.assert_report(self.run_report(), 1, ("FAIL content-invalid",))
                self.assertEqual(lines, ["FAIL content-invalid", FAIL])

    def test_c2_3_bad_available(self):
        # Check invalid values even on hidden rows; absence is allowed, null is not.
        self.fixture([product("unknown"), product([], status="hidden"), product(None),
                      {"status": "active"}, product("yes")])
        self.assert_report(self.run_report(), 1, ("FAIL bad-available 3",))

    def test_c2_4_bad_restock_day(self):
        # Shape alone would accept the non-leap date; falsey values must not be ignored.
        self.fixture([product("no", restock_on="2030-02-29"),
                      product("no", status="held", restock_on=None),
                      product("no", restock_on=""), product("no", restock_on=TODAY),
                      product("no")])
        self.assert_report(self.run_report(), 1, ("FAIL bad-restock-day 3",))

    def test_c3_usage_exit_2(self):
        # Usage errors must not become report findings or print a verdict.
        for args in ((), ("--content", str(self.content), "--unknown"),
                     ("--content", str(self.content), "--today", "2030-02-29")):
            with self.subTest(args=args):
                result = self.cli(*args)
                self.assertEqual(result.returncode, 2)
                self.assertEqual(result.stdout, "")  # No last stdout line for a usage error.
                self.assertIn("usage:", result.stderr)

    def test_c4_read_only(self):
        # A caching sidecar or byte-identical rewrite must still be detectable.
        self.fixture([product("no", restock_on="2030-06-14")])

        def snapshot():
            return {p.relative_to(self.content): (p.stat().st_mtime_ns,
                    p.read_bytes() if p.is_file() else None)
                    for p in (self.content, *self.content.rglob("*"))}

        before = snapshot()
        self.assert_report(self.run_report())
        self.assertEqual(snapshot(), before)

    def test_c5_no_private_values(self):
        # Catch leaks from successful reporting, findings, loader diagnostics and usage errors.
        name, phone = "Synthetic Product Canary", "2025550147"
        found = product("yes", name=name)
        self.fixture([found, product("limited", "2030-06-06"), product("limited"), product("no")],
                     checked="2030-06-06", phone=phone)
        success = self.run_report()
        self.assert_report(success)

        self.fixture([product(name, name=name, restock_on=phone)], phone=phone)
        findings = self.run_report()
        self.assert_report(findings, 1, ("FAIL bad-available 1", "FAIL bad-restock-day 1"))

        self.write_doc("products", products=[found], **{name: phone})
        invalid = self.run_report()
        self.assert_report(invalid, 1, ("FAIL content-invalid",))

        usage = self.cli("--content", str(self.content), "--today", str(self.content))
        self.assertEqual((usage.returncode, usage.stdout), (2, ""))
        for result in (success, findings, invalid, usage):
            for canary in (name, phone, "(202) 555-0147", "Available today", "Limited", "Sold out",
                           "Last confirmed Thursday, June 6", str(self.content)):
                self.assertNotIn(canary, result.stdout + result.stderr)

    def test_c6_stale_word(self):
        # Eight days is stale; seven days still counts even with a stale full check.
        self.fixture([product("yes", "2030-06-07"), product("limited", "2030-06-08")],
                     checked="2030-06-07")
        lines = self.assert_report(self.run_report())
        for line in ("checked-on 8 days", "note selection-stale", "active 2",
                     "last-confirmed 1", "state yes 0", "state limited 1", "state no 0", "no-word 0"):
            self.assertIn(line, lines)

    def test_c7_no_check(self):
        # A dated word alone must not bypass the first full check requirement.
        self.fixture([product("yes"), {"status": "active"}], checked=None)
        lines = self.assert_report(self.run_report())
        for line in ("checked-on none", "active 2", "no-word 2", "last-confirmed 0",
                     "state yes 0", "state limited 0", "state no 0"):
            self.assertIn(line, lines)
        self.assertNotIn("note selection-stale", lines)

    def test_c8_restock_passed_note(self):
        # An inclusive comparison would count today's restock; a finding would fail the run.
        self.fixture([product("no", restock_on="2030-06-14"), product("no", restock_on=TODAY),
                      product("no", restock_on="2030-06-16"), product("yes", restock_on="2030-06-14")])
        lines = self.assert_report(self.run_report())
        for line in ("state no 3", "restock-set 4", "note restock-passed 1", "note restock-not-sold-out 1"):
            self.assertIn(line, lines)

    def test_default_today_uses_shop_day(self):
        # Using the host's local date instead would misdate the report near midnight.
        self.fixture([product("yes")])
        spec = importlib.util.spec_from_file_location("content_availability_report", SCRIPT)
        assert spec is not None and spec.loader is not None
        report = importlib.util.module_from_spec(spec)
        with patch.object(sys, "path", sys.path.copy()):
            spec.loader.exec_module(report)
        out, err = io.StringIO(), io.StringIO()
        with patch.object(report.content_model, "shop_today", return_value=date.fromisoformat(TODAY)), \
                redirect_stdout(out), redirect_stderr(err):
            code = report.main(["--content", str(self.content)])
        result = subprocess.CompletedProcess([], code, out.getvalue(), err.getvalue())
        lines = self.assert_report(result)
        self.assertIn("checked-on 0 days", lines)
        self.assertIn("state yes 1", lines)
