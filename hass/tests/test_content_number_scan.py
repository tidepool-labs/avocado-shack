"""Fixture-only acceptance tests for the catalog number screen."""

import json
from pathlib import Path
import subprocess
import sys
from tempfile import TemporaryDirectory
import unittest


SCRIPT = Path(__file__).resolve().parents[2] / "scripts/hass/content_number_scan.py"
PASS = "PASS content_number_scan"
FAIL = "FAIL content_number_scan"


def product(product_id, **fields):
    return {"id": product_id, "status": "active", **fields}


class ContentNumberScanTests(unittest.TestCase):
    def setUp(self):
        temporary = TemporaryDirectory()
        self.addCleanup(temporary.cleanup)
        self.root = Path(temporary.name).resolve()
        self.content = self.root / "catalog-copy"
        self.content.mkdir()
        self.private = self.root / "amounts.txt"
        self.write_content()

    def write_content(self, *products):
        for name, data in (
            ("products", {"products": products}),
            ("makers", {"makers": {}}),
            ("community", {}),
            ("store", {}),
        ):
            (self.content / f"{name}.json").write_text(
                json.dumps({"schemaVersion": 1, **data}), encoding="utf-8",
            )

    def invoke(self, *args):
        return subprocess.run(
            [sys.executable, "-B", str(SCRIPT), *map(str, args)],
            cwd=self.root, capture_output=True, text=True, timeout=10,
        )

    def scan(self, *args):
        return self.invoke("--content", self.content, *args)

    def assert_report(self, result, code, *lines):
        self.assertEqual(result.returncode, code, result.stderr)
        self.assertEqual(result.stderr, "")
        self.assertEqual(result.stdout, "\n".join(lines) + "\n")

    def test_c1_full_pass(self):
        # Don't scan non-string fields, hidden/held listings, or the separate public price.
        self.write_content(
            product("fixture-a", name="Figs", description="", brand=None,
                    imageAlt=["9 dollars"], sellingPrice="9.87 each"),
            product("fixture-b", name="Eggs", status="hidden", description="9 dollars"),
            product("fixture-c", status="held", brand="9 dollars"),
            {"name": "9 dollars"}, ["9 dollars"], None, "9 dollars",
        )
        self.assert_report(self.scan(), 0, "active 1", "fields 2", "note malformed 3", PASS)

    def test_c2_1_unsafe_input(self):
        # Path.is_dir/is_file alone would accept symlinks to otherwise valid inputs.
        self.private.write_text("7\n", encoding="utf-8")
        dir_link = self.root / "dir-link"
        dir_link.symlink_to(self.content, target_is_directory=True)
        file_link = self.root / "file-link"
        file_link.symlink_to(self.private)
        missing = self.root / "missing"
        for option, paths in (("--content", (dir_link, self.private, missing)),
                              ("--private-file", (file_link, self.content, missing))):
            for path in paths:
                with self.subTest(option=option, leaf=path.name):
                    args = (option, path)
                    result = self.invoke(*args) if option == "--content" else self.scan(*args)
                    self.assert_report(result, 1, "FAIL unsafe-input", FAIL)

    def test_c2_2_content_invalid(self):
        # A products-only reader can pass despite invalid sibling JSON/schema or encoding.
        for filename, data in (
            ("makers.json", b"{"),
            ("community.json", b'{"schemaVersion":2}'),
            ("store.json", b"\xff"),
            ("products.json", b'{"schemaVersion":1,"products":null}'),
        ):
            with self.subTest(file=filename):
                self.write_content()
                (self.content / filename).write_bytes(data)
                self.assert_report(self.scan(), 1, "FAIL content-invalid", FAIL)

    def test_c2_3_bad_private_file(self):
        # Silently skipping bad lines or accepting Decimal NaN/Infinity hides bad input.
        for raw in (b"7\nnot-an-amount\n", b"NaN\n", b"-Infinity\n", b"\xff\n"):
            with self.subTest(raw=raw):
                self.private.write_bytes(raw)
                result = self.scan("--private-file", self.private)
                self.assert_report(result, 1, "FAIL bad-private-file", FAIL)

    def test_c2_4_money_in_text(self):
        # Count fields, not individual price tokens, and sort by ID then field.
        self.write_content(
            product("fixture-z", name="$8 or 9 dollars"),
            product("fixture-a", name="USD offer", brand="Euro € offer"),
        )
        self.assert_report(self.scan(), 1, "active 2", "fields 3", "reason money 3",
                           "money fixture-a brand", "money fixture-a name", "money fixture-z name",
                           "FAIL money-in-text 3", FAIL)

    def test_c2_5_private_number(self):
        # Scanning description alone misses alternate labels; independent checks can
        # also double-report a field or override the screen's money/unclear precedence.
        self.private.write_text("\n 24.0 \n\n24.00\n", encoding="utf-8")
        self.write_content(
            product("fixture-z", displayBrand="Two dozen", imageAlt="24 examples"),
            product("fixture-a", description="About 24 examples", displayBrand="24",
                    name="24 dollars"),
        )
        self.assert_report(self.scan("--private-file", self.private), 1,
                           "active 2", "fields 5", "reason money 1", "reason number-unclear 1",
                           "reason private-number 3", "number fixture-a description number-unclear",
                           "money fixture-a name", "FAIL money-in-text 1",
                           "private fixture-a displayBrand", "private fixture-z displayBrand",
                           "private fixture-z imageAlt", "FAIL private-number 3", FAIL)

    def test_c3_usage_exit_2(self):
        # Usage errors must not become report findings or exit 1.
        for args in ((), ("--content", self.content, "--unexpected", self.private),
                     ("--content", self.content, "--private-file")):
            with self.subTest(argument_count=len(args)):
                result = self.invoke(*args)
                self.assertEqual(result.returncode, 2)
                self.assertEqual(result.stdout, "")  # No last report line for C3.
                self.assertIn("usage:", result.stderr)
                self.assertNotIn(str(self.private), result.stderr)
                self.assertNotIn(str(self.content), result.stderr)

    def test_c4_read_only(self):
        # Detect writes even when original file contents are restored before exit.
        self.write_content(product("fixture-a", name="Figs"))
        self.private.write_text("782193\n", encoding="utf-8")

        def snapshot():
            return {path: (path.stat().st_mtime_ns, path.read_bytes() if path.is_file() else None)
                    for path in (self.root, *self.root.rglob("*"))}

        before = snapshot()
        self.assert_report(self.scan("--private-file", self.private), 0, "active 1", "fields 1", PASS)
        self.assertEqual(snapshot(), before)

    def test_c5_no_private_values(self):
        # Raw text, amounts, invalid IDs, or underlying loader exceptions can leak data.
        price = "9374.81"
        amount = "782193"
        description = f"Synthetic listing: {price} a jar."
        self.private.write_text(amount + "\n", encoding="utf-8")
        self.write_content(product("fixture-a", description=description),
                           product(f"{self.private}\n{amount}", name=f"Box of {amount} figs"))
        result = self.scan("--private-file", self.private)
        self.assert_report(result, 1, "active 2", "fields 2", "reason money 1", "reason private-number 1",
                           "money fixture-a description", "FAIL money-in-text 1", "private - name",
                           "FAIL private-number 1", FAIL)
        (self.content / "products.json").write_text(
            json.dumps({"schemaVersion": 1, "products": [], description: amount}), encoding="utf-8",
        )
        invalid = self.scan("--private-file", self.private)
        self.assert_report(invalid, 1, "FAIL content-invalid", FAIL)
        for run in (result, invalid):
            for canary in (amount, description, price, str(self.content), str(self.private)):
                self.assertNotIn(canary, run.stdout + run.stderr)

    def test_c6_probe_cases(self):
        # The actual screen catches a bare money amount but does not ban spelled-out counts.
        self.write_content(product("fixture-a", description="Only 3.99 a jar."),
                           product("fixture-b", description="Two dozen eggs."))
        self.assert_report(self.scan(), 1, "active 2", "fields 2", "reason money 1",
                           "money fixture-a description", "FAIL money-in-text 1", FAIL)

    def test_c7_digits_note(self):
        # Notes are sorted across reason types and never fail the scan on their own.
        self.write_content(product("fixture-z", name="About four kinds"),
                           product("fixture-a", description="Est. 1952 in the valley.",
                                   brand="About two kinds"))
        self.assert_report(self.scan(), 0, "active 2", "fields 3", "reason number-unclear 2",
                           "reason unsupported-number 1", "number fixture-a brand number-unclear",
                           "number fixture-a description unsupported-number",
                           "number fixture-z name number-unclear", PASS)

    def test_c8_decimal_match(self):
        # Exact Decimal equality, not string equality, promotes the digit note to a finding.
        self.write_content(product("fixture-a", description="A box of 12 figs."))
        self.assert_report(self.scan(), 0, "active 1", "fields 1", "reason unsupported-number 1",
                           "number fixture-a description unsupported-number", PASS)
        self.private.write_text("12.00\n", encoding="utf-8")
        self.assert_report(self.scan("--private-file", self.private), 1, "active 1", "fields 1",
                           "reason private-number 1", "private fixture-a description",
                           "FAIL private-number 1", FAIL)
