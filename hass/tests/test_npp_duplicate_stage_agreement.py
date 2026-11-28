"""Offline CLI contract for the NPP/editor duplicate comparison."""

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
SCRIPT = ROOT / "scripts/hass/npp_duplicate_stage_agreement.py"
SPEC = importlib.util.spec_from_file_location(SCRIPT.stem, SCRIPT)
assert SPEC is not None and SPEC.loader is not None
report = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(report)
PASS = "PASS npp_duplicate_stage_agreement"
FAIL = "FAIL npp_duplicate_stage_agreement"


def product(key, name, status="active", brand="Fixture Brand"):
    return dict(id=key, name=name, status=status, brand=brand)


def snapshot():
    result = {}
    for root in (ROOT / "hass", ROOT / "storefront-mockup"):
        for path in (root, *root.rglob("*")):
            metadata = path.lstat()
            result[path.relative_to(ROOT)] = (metadata.st_size, metadata.st_mtime_ns)
    return result


class NppDuplicateStageAgreementTests(unittest.TestCase):
    def setUp(self):
        temporary = tempfile.TemporaryDirectory(dir=ROOT.parent)
        self.addCleanup(temporary.cleanup)
        self.directory = Path(temporary.name)
        self.products = self.directory / "products.json"
        self.makers = self.directory / "makers.json"
        self.write_products()
        self.makers.write_text(json.dumps({"makers": {
            "fixture": {"name": "Fixture Brand", "place": "Test Town"},
        }}), encoding="utf-8")

    def write_products(self, *records):
        self.products.write_text(json.dumps({"products": records}), encoding="utf-8")

    def invoke(self, *, products=None, makers=None):
        stdout, stderr = io.StringIO(), io.StringIO()
        with patch.multiple(report, PRODUCTS=products or self.products, MAKERS=makers or self.makers), \
                redirect_stdout(stdout), redirect_stderr(stderr):
            code = report.main([])
        self.assertEqual(stderr.getvalue(), "")
        return code, stdout.getvalue().splitlines()

    def cli(self, *args):
        return subprocess.run([sys.executable, "-B", str(SCRIPT), *args],
                              cwd=self.directory, capture_output=True, text=True, timeout=15)

    def assert_outcome(self, result, code, trailer):
        actual, lines = result
        self.assertEqual(actual, code)
        self.assertTrue(lines)
        self.assertEqual(lines[-1], trailer)
        return lines[:-1]

    def assert_finding(self, reason, **inputs):
        self.assertEqual(self.assert_outcome(self.invoke(**inputs), 1, FAIL), [f"FAIL {reason}"])

    def assert_cli_outcome(self, result, code, trailer):
        self.assertEqual(result.stderr, "")
        return self.assert_outcome((result.returncode, result.stdout.splitlines()), code, trailer)

    def test_c1_full_pass(self):
        # Zero eligible names must still report all three variants and a PASS.
        self.assertEqual(self.assert_outcome(self.invoke(), 0, PASS),
                         ["records 0", "agree exact 0", "agree upper 0", "agree double-space 0"])

    def test_c2_findings_trailer(self):
        # A real held-product disagreement is report-level failure, not a success with a warning.
        self.write_products(product("fixture-a", "Sample", "held"))
        lines = self.assert_outcome(self.invoke(), 1, FAIL)
        self.assertEqual([line for line in lines if line.startswith("FAIL ")], [
            "FAIL stage-disagree held exact s3-no editor-yes 1",
            "FAIL stage-disagree held upper s3-no editor-yes 1",
        ])

    def test_c2_1_input_unsafe(self):
        # A valid target must not make its alias safe; directories are not inputs either.
        for name in ("products", "makers"):
            for kind in ("symlink", "directory"):
                with self.subTest(name=name, kind=kind):
                    unsafe = self.directory / f"{name}-{kind}"
                    if kind == "symlink":
                        unsafe.symlink_to(getattr(self, name))
                    else:
                        unsafe.mkdir()
                    self.assert_finding(f"input-unsafe {name}", **{name: unsafe})

    def test_c2_2_input_too_large(self):
        # Size refusal precedes JSON parsing and applies to both sources.
        oversized = self.directory / "oversized.json"
        oversized.write_bytes(b"not json")
        with patch.object(report, "INPUT_CAP", 7):
            self.assert_finding("input-too-large products", products=oversized)
        with patch.object(report, "INPUT_CAP", self.products.stat().st_size):
            # Products exactly at the cap are allowed through to the makers check.
            self.assert_finding("input-too-large makers")

    def test_c2_3_input_unreadable(self):
        # Missing/corrupt inputs must not fall back to empty catalogs or expose input text.
        self.write_products(product("fixture-a", "Sample"))
        wrong_shapes = {
            "products": [b'[]', b'{"products":{}}', b'{"products":[{}]}',
                         b'{"products":[{"id":"fixture","name":"Sample","status":"active","brand":0}]}'],
            "makers": [b'[]', b'{"makers":[]}', b'{"makers":{"fixture":{"name":"Sample"}}}',
                       b'{"makers":{"fixture":{"name":"Sample","place":"Test Town","story":null}}}',
                       b'{"makers":{"fixture":{"name":"Sample","place":"Test Town","url":0}}}'],
        }
        with patch.object(report.missing, "_duplicates") as s3, patch.object(report.catalog, "_twin") as editor:
            for name, shapes in wrong_shapes.items():
                bad = self.directory / f"bad-{name}.json"
                cases = [("missing", None), ("invalid UTF-8", b'"\xff"'), ("invalid JSON", b"{"),
                         *(("wrong shape", raw) for raw in shapes)]
                for case, raw in cases:
                    with self.subTest(name=name, case=case, raw=raw):
                        if raw is not None:
                            bad.write_bytes(raw)
                        self.assert_finding(f"input-unreadable {name}", **{name: bad})
            self.assert_finding("input-unreadable products", products=self.directory / "absent",
                                makers=self.directory / "also-absent")
            s3.assert_not_called()
            editor.assert_not_called()

    def test_c2_4_stage_disagree(self):
        # Both mismatch directions, all status buckets, aggregation, and variant/status order.
        self.write_products(product("fixture-o", "Other Test", "unlisted", "Refuse"),
                            product("fixture-h1", "Held Test One", "held", "Refuse"),
                            product("fixture-h2", "Held Test Two", "held", "Refuse"),
                            product("fixture-z", "Hidden", "hidden", "Allow"),
                            product("fixture-a", "Active Test", "active", "Allow"))
        observed = []

        def s3(name, records, makers, clover):
            observed.append(name)
            self.assertEqual(len(records), 5)
            self.assertEqual(makers, {"fixture": {"name": "Fixture Brand", "place": "Test Town"}})
            self.assertIsNone(clover)
            return ("catalog",) if name.casefold().startswith(("active", "hidden")) else ("makers",)

        def editor(content, name, brand):
            self.assertEqual(len(content.products), 5)
            return {} if brand == "Refuse" else None

        with patch.object(report.missing, "_duplicates", side_effect=s3), \
                patch.object(report.catalog, "_twin", side_effect=editor) as twin:
            lines = self.assert_outcome(self.invoke(), 1, FAIL)
        self.assertEqual(observed, [
            "Other Test", "OTHER TEST", "Other  Test",
            "Held Test One", "HELD TEST ONE", "Held  Test One",
            "Held Test Two", "HELD TEST TWO", "Held  Test Two",
            "Hidden", "HIDDEN", "Active Test", "ACTIVE TEST", "Active  Test",
        ])
        self.assertEqual([call.args[1:] for call in twin.call_args_list],
                         list(zip(observed, ["Refuse"] * 9 + ["Allow"] * 5)))
        self.assertEqual(lines, ["records 5", "agree exact 0", "agree upper 0", "agree double-space 0", *[
            f"FAIL stage-disagree {status} {variant} {direction} {count}"
            for variant in ("exact", "upper", "double-space")
            for status, direction, count in (
                ("active", "s3-yes editor-no", 1), ("held", "s3-no editor-yes", 2),
                ("hidden", "s3-yes editor-no", 1), ("other", "s3-no editor-yes", 1),
            ) if (variant, status) != ("double-space", "hidden")
        ]])

    def test_c2_5_check_error(self):
        # Exceptions from either stage must not leak details or certify a partial comparison.
        self.write_products(product("fixture-a", "Sample"))
        for module, name in ((report.missing, "_duplicates"), (report.catalog, "_twin")):
            with self.subTest(stage=name), patch.object(module, name, side_effect=RuntimeError("fixture detail")):
                self.assert_finding("check-error")

    def test_c3_usage_exit_2(self):
        # No argument is admitted, including conventional help and a bare separator.
        for arg in ("extra", "--unknown", "--help", "-h", "--", ""):
            with self.subTest(arg=arg):
                result = self.cli(arg)
                self.assertEqual(result.returncode, 2)
                self.assertEqual(result.stdout, "")
                self.assertIn("error: unrecognized arguments:", result.stderr.splitlines()[-1])

    def test_c4_read_only(self):
        # CLI reads must not generate or rewrite repo artifacts, including bytecode.
        before = snapshot()
        self.assert_cli_outcome(self.cli(), 1, FAIL)
        self.assertEqual(snapshot(), before)

    def test_c5_output_shape(self):
        # Unknown status and product fields (including newlines) must never become report text.
        self.write_products(product("fixture-redact", "", "unlisted\nsynthetic status"))
        self.assertEqual(self.assert_outcome(self.invoke(), 1, FAIL), [
            "records 1", "agree exact 0", "agree upper 0", "agree double-space 0",
            "FAIL stage-disagree other exact s3-no editor-yes 1",
            "FAIL stage-disagree other upper s3-no editor-yes 1",
        ])

    def test_c6_fixture_pass(self):
        # Injected named products, not the checked-in file or a held-only comparison, drive counts.
        self.write_products(product("fixture-a", "Sample Biscuit"), product("fixture-b", "Sampleberry"))
        self.assertEqual(self.assert_outcome(self.invoke(), 0, PASS),
                         ["records 2", "agree exact 2", "agree upper 2", "agree double-space 1"])

    def test_c7_live_pins(self):
        # The unpatched CLI still finds the checked-in held mismatches, not just fixture failures.
        self.assertEqual(self.assert_cli_outcome(self.cli(), 1, FAIL), [
            "records 172", "agree exact 170", "agree upper 170", "agree double-space 136",
            "FAIL stage-disagree held exact s3-no editor-yes 2",
            "FAIL stage-disagree held upper s3-no editor-yes 2",
            "FAIL stage-disagree held double-space s3-no editor-yes 2",
        ])
