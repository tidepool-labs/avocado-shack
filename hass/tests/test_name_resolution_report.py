"""Offline CLI contracts for the Hass full-name audit."""

from contextlib import redirect_stderr, redirect_stdout
import importlib.util
import io
import json
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import patch

from hass import content_model

SCRIPT = Path(__file__).resolve().parents[2] / "scripts/hass/name_resolution_report.py"
SPEC = importlib.util.spec_from_file_location("name_resolution_report", SCRIPT)
assert SPEC is not None and SPEC.loader is not None
report = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(report)

PASS = "PASS name_resolution_report"
FAIL = "FAIL name_resolution_report"
PRODUCT_NAME = "SyntheticProductCanary"
MAKER_NAME = "SyntheticMakerCanary"


def product(number, name, status="active"):
    row: dict[str, object] = dict(
        id=f"fixture-{number:02d}", name=name, status=status, brand="Sample Brand",
        displayBrand="Sample Display", category="pantry", producerKey=None,
        image="assets/products/sample.webp", description="Synthetic fixture description.",
    )
    if status == "held":
        row["hold"] = {"reason": "Synthetic review note.", "source": "https://example.test/fixture"}
    return row


class NameResolutionReportTests(unittest.TestCase):
    def setUp(self):
        temp = tempfile.TemporaryDirectory()
        self.addCleanup(temp.cleanup)
        self.root = Path(temp.name).resolve()
        self.content = self.root / "sample-content-canary"
        self.content.mkdir()
        for source in content_model.CONTENT_DIR.glob("*.json"):
            shutil.copy2(source, self.content / source.name)

    def rewrite(self, section, value):
        path = self.content / f"{section}.json"
        document = json.loads(path.read_text(encoding="utf-8"))
        document[section] = value
        path.write_text(json.dumps(document), encoding="utf-8")

    def distinct(self):
        self.rewrite("products", [product(1, PRODUCT_NAME), product(2, "Silver Crisp"),
                                  product(3, "Archive Wafer", "hidden")])
        self.rewrite("makers", {"fixture-maker": {"name": MAKER_NAME, "place": "Sample Town"}})

    def contained(self):
        self.distinct()
        self.rewrite("products", [product(1, "Honey"), product(2, "Honey butter")])

    def capped(self):
        self.distinct()
        variants = [product(n, f"Zeta Wafer Variant {n:02d}", {1: "held", 2: "hidden"}.get(n, "active"))
                    for n in range(1, 11)]
        self.rewrite("products", [*variants, product(11, "Zeta Wafer")])

    def hide_maker(self):
        self.rewrite("makers", {"fixture-maker": {"name": MAKER_NAME, "place": "Sample Town", "hidden": True}})

    def cli(self, *args):
        return subprocess.run([sys.executable, "-B", str(SCRIPT), *args], cwd=self.root,
                              capture_output=True, text=True, timeout=15)

    def fixture_cli(self, path=None):
        return self.cli("--content", str(self.content if path is None else path))

    def assert_report(self, result, code, trailer, *findings):
        self.assertEqual(result.returncode, code)
        self.assertEqual(result.stderr, "")
        lines = result.stdout.splitlines()
        self.assertTrue(lines)
        self.assertEqual(lines[-1], trailer)
        self.assertEqual([line for line in lines[:-1] if line.startswith("FAIL ")], list(findings))
        self.assertNotIn(PASS if code else FAIL, lines)
        return lines

    def test_c1_full_pass(self):
        # A clean fixture must not be treated as a finding or omit its trailer.
        self.distinct()
        self.assert_report(self.fixture_cli(), 0, PASS)

    def test_c2_findings_trailer(self):
        # An early return after the first finding would hide other findings.
        self.capped()
        self.hide_maker()
        self.assert_report(self.fixture_cli(), 1, FAIL, "FAIL ambiguous-products 1",
                           "FAIL unresolved-products 1", "FAIL unresolved-makers 1")

    def test_c2_1_unsafe_input(self):
        # A symlink to loadable content must be refused just like non-directories.
        alias = self.root / "content-alias"
        alias.symlink_to(self.content, target_is_directory=True)
        for path in (alias, self.content / "products.json", self.root / "absent"):
            with self.subTest(entry=path.name):
                self.assert_report(self.fixture_cli(path), 1, FAIL, "FAIL unsafe-input")

    def test_c2_2_content_invalid(self):
        # Loader failure must be distinct from a lookup failure or usage error.
        (self.content / "products.json").write_text("{invalid fixture", encoding="utf-8")
        lines = self.assert_report(self.fixture_cli(), 1, FAIL, "FAIL content-invalid")
        self.assertEqual(lines, ["FAIL content-invalid", FAIL])

    def test_c2_3_check_error(self):
        # Catch resolver exceptions and reject an unverifiable raw-cap check after a real `several`.
        self.contained()

        def invoke():
            stdout, stderr = io.StringIO(), io.StringIO()
            with redirect_stdout(stdout), redirect_stderr(stderr):
                code = report.main(["--content", str(self.content)])
            result = subprocess.CompletedProcess([], code, stdout.getvalue(), stderr.getvalue())
            lines = self.assert_report(result, 1, FAIL, "FAIL check-error")
            self.assertEqual(lines, ["FAIL check-error", FAIL])

        for resolver in ("product_ref", "maker_ref"):
            with self.subTest(resolver=resolver), patch.object(
                report.kinds, resolver, side_effect=RuntimeError(PRODUCT_NAME)
            ):
                invoke()

        lookup = report.catalog.lookup
        failed_raw_checks = (
            RuntimeError(PRODUCT_NAME), {"match": "fixture-01"}, {},
            {"candidates": ()}, {"candidates": [None]}, {"candidates": []},
        )
        for bad_raw in failed_raw_checks:
            with self.subTest(raw=type(bad_raw).__name__), patch.object(report.catalog, "lookup") as mock_lookup:
                # The first call is from product_ref; only the report's repeat is broken.
                def side_effect(*args, **kwargs):
                    if mock_lookup.call_count == 1:
                        return lookup(*args, **kwargs)
                    if isinstance(bad_raw, Exception):
                        raise bad_raw
                    return bad_raw

                mock_lookup.side_effect = side_effect
                invoke()
                self.assertEqual(mock_lookup.call_count, 2)

    def test_c2_4_ambiguous_products(self):
        # Offered choices are still ambiguous when the target itself is offered.
        self.contained()
        self.assert_report(self.fixture_cli(), 1, FAIL, "FAIL ambiguous-products 1")

    def test_c2_5_unresolved_products(self):
        # An apostrophe-only name folds to no query, not to several choices.
        self.distinct()
        self.rewrite("products", [product(1, "'")])
        lines = self.assert_report(self.fixture_cli(), 1, FAIL, "FAIL unresolved-products 1")
        self.assertIn("product other 1", lines)
        self.assertIn("product not-offered 0", lines)

    def test_c2_6_unresolved_makers(self):
        # Skipping hidden makers would silently clear this finding.
        self.distinct()
        self.hide_maker()
        lines = self.assert_report(self.fixture_cli(), 1, FAIL, "FAIL unresolved-makers 1")
        self.assertIn("makers 1", lines)
        self.assertIn("maker other 1", lines)

    def test_c3_usage_exit_2(self):
        # Parser errors must not be turned into report findings or echo argv values.
        for args in (("--content",), ("--unknown", str(self.content))):
            with self.subTest(option=args[0]):
                result = self.cli(*args)
                self.assertEqual(result.returncode, 2)
                self.assertEqual(result.stdout, "")  # No stdout trailer on usage errors.
                self.assertEqual(result.stderr.splitlines()[-1],
                                 "name_resolution_report.py: error: invalid arguments")
                self.assertNotIn(str(self.content), result.stderr)

    def test_c4_read_only(self):
        # Reformatting even byte-identical JSON or creating a sidecar violates read-only.
        self.distinct()

        def snapshot():
            return {path.relative_to(self.content): (path.stat().st_mtime_ns,
                    path.read_bytes() if path.is_file() else None)
                    for path in (self.content, *self.content.rglob("*"))}

        before = snapshot()
        self.assert_report(self.fixture_cli(), 0, PASS)
        self.assertEqual(snapshot(), before)

    def test_c5_no_private_values(self):
        # Per-record reports, resolver questions and path diagnostics can leak fixture values.
        self.distinct()
        self.rewrite("products", [product(1, PRODUCT_NAME), product(2, f"{PRODUCT_NAME} Wafer")])
        self.hide_maker()
        result = self.fixture_cli()
        for secret in (PRODUCT_NAME, MAKER_NAME, "fixture-01", "fixture-maker", str(self.root), str(self.content)):
            self.assertFalse(secret in result.stdout or secret in result.stderr, "private value leaked")
        self.assert_report(result, 1, FAIL, "FAIL ambiguous-products 1", "FAIL unresolved-makers 1")

    def test_c6_distinct_names(self):
        # Counting hidden products or omitting maker resolution would corrupt the clean totals.
        self.distinct()
        self.assertEqual(self.assert_report(self.fixture_cli(), 0, PASS), [
            "products 2", "product one 2", "product several 0", "product several-at-cap 0",
            "product not-offered 0", "product other 0", "makers 1", "maker one 1", "maker other 0", PASS,
        ])

    def test_c7_contained_name(self):
        # Exact-only matching or reversing the substring check misses the shorter query.
        self.contained()
        lines = self.assert_report(self.fixture_cli(), 1, FAIL, "FAIL ambiguous-products 1")
        self.assertIn("product one 1", lines)
        self.assertIn("product several 1", lines)
        self.assertIn("product several-at-cap 0", lines)

    def test_c8_live_names(self):
        # Pin the report against committed content and the CLI's default-path wiring.
        self.assertEqual(self.assert_report(self.cli(), 1, FAIL, "FAIL ambiguous-products 13"), [
            "products 170", "product one 157", "product several 13", "product several-at-cap 1",
            "product not-offered 0", "product other 0", "makers 26", "maker one 26", "maker other 0",
            "FAIL ambiguous-products 13", FAIL,
        ])

    def test_c9_pre_filter_cap(self):
        # Ten raw hits, eight offered: counting filtered ids would miss the cap.
        self.capped()
        lines = self.assert_report(self.fixture_cli(), 1, FAIL, "FAIL ambiguous-products 1",
                                   "FAIL unresolved-products 1")
        self.assertIn("products 9", lines)
        self.assertIn("product one 8", lines)
        self.assertIn("product several 1", lines)
        self.assertIn("product several-at-cap 1", lines)
        self.assertIn("product not-offered 1", lines)
