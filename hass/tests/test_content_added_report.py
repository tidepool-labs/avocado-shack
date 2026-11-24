"""Contract tests for the counts-only catalog copy report."""

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


SCRIPT = Path(__file__).resolve().parents[2] / "scripts/hass/content_added_report.py"
TODAY = "2040-03-02"
PASS = "PASS content_added_report"
FAIL = "FAIL content_added_report"


def active(**fields):
    return {"status": "active", **fields}


class ContentAddedReportTests(unittest.TestCase):
    def setUp(self):
        temp = tempfile.TemporaryDirectory()
        self.addCleanup(temp.cleanup)
        self.root = Path(temp.name).resolve()
        self.content = self.root / "synthetic-copy"
        self.content.mkdir()
        self.copy_with([])

    def copy_with(self, products):
        for name, payload in (
            ("products", {"products": products}),
            ("makers", {"makers": {}}),
            ("community", {}),
            ("store", {}),
        ):
            (self.content / f"{name}.json").write_text(
                json.dumps({"schemaVersion": 1, **payload}), encoding="utf-8",
            )

    def cli(self, *args):
        return subprocess.run(
            [sys.executable, "-B", str(SCRIPT), *args], cwd=self.root,
            capture_output=True, text=True, timeout=10,
        )

    def run_report(self, *args, content=None):
        return self.cli("--content", str(content or self.content), "--today", TODAY, *args)

    def assert_pass(self, result):
        self.assertEqual(result.returncode, 0)
        self.assertEqual(result.stderr, "")
        lines = result.stdout.splitlines()
        self.assertEqual(lines[-1:], [PASS])
        return lines

    def assert_findings(self, result, *reasons):
        self.assertEqual(result.returncode, 1)
        self.assertEqual(result.stderr, "")
        lines = result.stdout.splitlines()
        self.assertEqual(lines[-1:], [FAIL])
        self.assertEqual([line for line in lines[:-1] if line.startswith("FAIL ")],
                         [f"FAIL {reason}" for reason in reasons])
        return lines

    def test_c1_full_pass(self):
        # C1: catches unsorted/ungrouped days, wrong unit buckets, and near-match photos.
        self.copy_with([
            active(addedOn="2040-03-01", sellingPrice="0.00 each", supplier="Fixture Supply",
                   imageAlt="Fixture photo", image="assets/products/photo-0123456789abcdef.jpg"),
            active(addedOn="2040-02-29", sellingPrice="0.00 per lb",
                   image="assets/products/photo-fedcba9876543210.png"),
            active(addedOn="2040-03-01", imageAlt="Fixture drawing",
                   image="assets/products/photo-0123456789abcdef.jpg.old"),
            active(sellingPrice="0.00", image="assets/products/photo-0123456789abcdeF.jpg"),
            None, ["not a record"],
        ])
        self.assertEqual(self.assert_pass(self.run_report()), [
            "active 4", "added-dated 3", "added-day 2040-02-29 1", "added-day 2040-03-01 2",
            "price-each 1", "price-per-lb 1", "price-plain 1", "supplier 1", "image-alt 2",
            "photo-image 2", "note added-no-price 1", "note added-no-alt 1",
            "note hidden-dated 0", "note malformed 2", PASS,
        ])

    def test_c2_1_unsafe_input(self):
        # C2.1: is_dir() alone would accept a symlink to an otherwise valid copy.
        alias = self.root / "alias"
        alias.symlink_to(self.content, target_is_directory=True)
        for path in (alias, self.content / "store.json", self.root / "missing"):
            with self.subTest(kind=path.name):
                self.assertEqual(self.assert_findings(self.run_report(content=path), "unsafe-input"),
                                 ["FAIL unsafe-input", FAIL])

    def test_c2_2_content_invalid(self):
        # C2.2: a products-only reader would miss bad sibling documents.
        for name, raw in (
            ("makers", b'{"schemaVersion":1,"makers":{},"makers":{}}'),
            ("community", b"\xff"),
            ("store", b'{"schemaVersion":1,'),
            ("products", b'{"schemaVersion":1,"products":null}'),
        ):
            with self.subTest(document=name):
                self.copy_with([])
                (self.content / f"{name}.json").write_bytes(raw)
                self.assertEqual(self.assert_findings(self.run_report(), "content-invalid"),
                                 ["FAIL content-invalid", FAIL])

    def test_c2_3_bad_selling_price(self):
        # C2.3: catches truthiness checks that miss null or accept a noncanonical price.
        self.copy_with([active(sellingPrice=None), active(sellingPrice="00.00 each"), active(),
                        {"status": "hidden", "sellingPrice": False}])
        lines = self.assert_findings(self.run_report(), "bad-selling-price 3")
        for bucket in ("each", "per-lb", "plain"):
            self.assertIn(f"price-{bucket} 0", lines)

    def test_c2_4_bad_added_on(self):
        # C2.4: a regex-only check misses impossible days; truthiness misses null.
        self.copy_with([active(addedOn="2040-02-30"), active(addedOn=None), active()])
        lines = self.assert_findings(self.run_report(), "bad-added-on 2")
        self.assertIn("added-dated 0", lines)
        self.assertFalse(any(line.startswith("added-day ") for line in lines))

    def test_c2_5_added_in_future(self):
        # C2.5: using the wall clock or filtering out future rows would miscount.
        self.copy_with([active(addedOn="2040-03-01"), active(addedOn="2040-03-03")])
        lines = self.assert_findings(self.run_report(), "added-in-future 1")
        self.assertIn("added-dated 2", lines)
        self.assertIn("added-day 2040-03-03 1", lines)

    def test_c3_usage_exit_2(self):
        # C3: prevents treating parser errors as report findings or silently accepting bad dates.
        base = ("--content", str(self.content))
        for args in ((), (*base, "--unknown"), (*base, "--tod", TODAY), (*base, "--since", "2040-02-30"),
                     (*base, "--today", "not-a-date")):
            with self.subTest(args=args):
                result = self.cli(*args)
                self.assertEqual(result.returncode, 2)
                self.assertEqual(result.stdout.splitlines(), [])  # No stdout last line for C3.
                self.assertEqual(result.stderr.splitlines()[-1:],
                                 ["content_added_report.py: error: invalid arguments; see --help"])

    def test_c4_read_only(self):
        # C4: catches rewriting the same bytes, normalization, and new sidecar files/directories.
        self.copy_with([active(addedOn=TODAY)])

        def snapshot():
            return {path.relative_to(self.content): (
                path.stat().st_mtime_ns, path.read_bytes() if path.is_file() else None,
            ) for path in (self.content, *self.content.rglob("*"))}

        before = snapshot()
        self.assert_pass(self.run_report())
        self.assertEqual(snapshot(), before)

    def test_c5_no_private_values(self):
        # C5: catches raw-record, parser-argument and loader-exception output leaks.
        canaries = {
            "id": "synthetic-id-canary", "name": "Synthetic name canary",
            "sellingPrice": "987654.32 each", "supplier": "Synthetic supplier canary",
            "imageAlt": "Synthetic alt canary",
        }
        invalid_price = "synthetic-invalid-price-canary"
        unknown_key = "synthetic-loader-canary"

        def check_streams(result):
            for marker in (*canaries.values(), invalid_price, unknown_key, str(self.content)):
                self.assertNotIn(marker, result.stdout)
                self.assertNotIn(marker, result.stderr)

        self.copy_with([active(addedOn=TODAY, **canaries)])
        result = self.run_report()
        check_streams(result)
        self.assert_pass(result)
        self.copy_with([
            active(**canaries), active(sellingPrice=invalid_price, addedOn="never"),
            active(addedOn="2040-03-03"),
        ])
        result = self.run_report()
        check_streams(result)
        self.assert_findings(result, "bad-selling-price 1", "bad-added-on 1", "added-in-future 1")
        (self.content / "products.json").write_text(json.dumps({
            "schemaVersion": 1, "products": [active(**canaries)], unknown_key: True,
        }), encoding="utf-8")
        result = self.run_report()
        check_streams(result)
        self.assert_findings(result, "content-invalid")
        result = self.run_report("--unknown", str(self.content))
        check_streams(result)
        self.assertEqual(result.returncode, 2)
        self.assertEqual(result.stdout, "")

    def test_c6_since_only_days(self):
        # C6: filtering records early would change coverage or suppress findings.
        self.copy_with([
            active(addedOn="2040-03-01", sellingPrice="0.00 per lb"),
            active(addedOn=TODAY, supplier="Fixture Supply"),
            active(addedOn="2040-02-29", sellingPrice=False),
        ])
        full = self.assert_findings(self.run_report(), "bad-selling-price 1")
        recent = self.assert_findings(self.run_report("--since", TODAY), "bad-selling-price 1")
        self.assertEqual([line for line in recent if line.startswith("added-day ")],
                         ["added-day 2040-03-02 1"])
        self.assertEqual(recent, [line for line in full if line not in (
            "added-day 2040-02-29 1", "added-day 2040-03-01 1",
        )])

    def test_c7_hidden_dated(self):
        # C7: hidden/held records cannot affect coverage, daily totals or findings.
        baseline = self.assert_pass(self.run_report())
        self.copy_with([
            {"status": "hidden", "addedOn": "2040-03-03", "sellingPrice": "0.00 each",
             "supplier": "Fixture Supply", "imageAlt": "Fixture alt",
             "image": "assets/products/photo-0123456789abcdef.jpg"},
            {"status": "held", "addedOn": "invalid", "sellingPrice": None},
            {"status": "hidden"},
        ])
        self.assertEqual(self.assert_pass(self.run_report()), [
            "note hidden-dated 2" if line == "note hidden-dated 0" else line for line in baseline
        ])
        self.assertIn("note hidden-dated 0", baseline)

    def test_c8_today_not_future(self):
        # C8: >= incorrectly refuses same-day listings; date.today() ignores shop time.
        self.copy_with([active(addedOn=TODAY)])
        explicit = self.assert_pass(self.run_report())
        self.assertIn("added-dated 1", explicit)
        self.assertIn("added-day 2040-03-02 1", explicit)
        spec = importlib.util.spec_from_file_location("content_added_report", SCRIPT)
        assert spec is not None and spec.loader is not None
        report = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(report)
        out, err = io.StringIO(), io.StringIO()
        with patch.object(report.content_model, "shop_today", return_value=date.fromisoformat(TODAY)), \
                redirect_stdout(out), redirect_stderr(err):
            code = report.main(["--content", str(self.content)])
        self.assertEqual(code, 0)
        self.assertEqual(err.getvalue(), "")
        self.assertEqual(out.getvalue().splitlines()[-1:], [PASS])
        self.assertEqual(out.getvalue().splitlines(), explicit)
