"""Offline contract tests for the counts-only NPP duplicate replay."""

from contextlib import redirect_stderr, redirect_stdout
import importlib.util
import io
import json
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import call, patch

ROOT = Path(__file__).resolve().parents[2]
SCRIPT = ROOT / "scripts/hass/npp_duplicate_variants.py"
PASS = "PASS npp_duplicate_variants"
FAIL = "FAIL npp_duplicate_variants"
KINDS = ("exact", "upper", "double-space", "plural", "the", "no-apostrophe")
LIVE_REPORT = [
    "tried exact 170", "caught exact 170",
    "tried upper 170", "caught upper 170",
    "tried double-space 136", "caught double-space 136",
    "tried plural 170", "caught plural 0",
    "tried the 170", "caught the 0",
    "tried no-apostrophe 10", "caught no-apostrophe 0",
    "FAIL variant-missed plural 170",
    "FAIL variant-missed the 170",
    "FAIL variant-missed no-apostrophe 10",
    FAIL,
]


def _product(name, status="active"):
    return {"id": "fixture-" + name, "name": name, "status": status}


def _report(tried, caught):
    return [line for kind, n, hits in zip(KINDS, tried, caught)
            for line in (f"tried {kind} {n}", f"caught {kind} {hits}")]


class DuplicateVariantsTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        spec = importlib.util.spec_from_file_location("npp_duplicate_variants", SCRIPT)
        assert spec is not None and spec.loader is not None
        cls.tool = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(cls.tool)

    def setUp(self):
        self.directory = Path(self.enterContext(tempfile.TemporaryDirectory(dir=ROOT)))
        self.products = self.directory / "products.json"
        self.makers = self.directory / "makers.json"
        self.write_products(_product("Pebble"))
        self.makers.write_text('{"makers": {}}', encoding="utf-8")
        self.enterContext(patch.multiple(self.tool, PRODUCTS=self.products, MAKERS=self.makers))

    def write_products(self, *records):
        self.products.write_text(json.dumps({"products": records}), encoding="utf-8")

    def assert_run(self, code, lines):
        stdout, stderr = io.StringIO(), io.StringIO()
        with redirect_stdout(stdout), redirect_stderr(stderr):
            result = self.tool.main([])
        self.assertEqual(result, code)
        self.assertEqual(stdout.getvalue(), "\n".join(lines) + "\n")
        self.assertEqual(stderr.getvalue(), "")

    def cli(self, *args):
        return subprocess.run([sys.executable, "-B", str(SCRIPT), *args], cwd=self.directory,
                              capture_output=True, text=True, timeout=30)

    def test_c1_full_pass(self):
        # The real rule can match non-active records; filtering the matcher inputs would fail.
        self.write_products(_product("Pebble"), _product("Pebbles", "inactive"),
                            _product("the Pebble", "inactive"))
        self.assert_run(0, _report((1, 1, 0, 1, 1, 0), (1, 1, 0, 1, 1, 0)) + [PASS])

    def test_c2_findings_trailer(self):
        # A maker-only collision must not be counted as a catalog hit or exit successfully.
        self.makers.write_text(json.dumps({"makers": {
            "Pebbles": {"name": "the Pebble", "place": "Fixture"},
        }}), encoding="utf-8")
        self.assert_run(1, _report((1, 1, 0, 1, 1, 0), (1, 1, 0, 0, 0, 0)) + [
            "FAIL variant-missed plural 1", "FAIL variant-missed the 1", FAIL,
        ])

    def test_c2_1_input_unsafe(self):
        # A symlink pointing to valid JSON is still unsafe, as is a directory.
        directory = self.directory / "not-a-file"
        directory.mkdir()
        for name in ("products", "makers"):
            symlink = self.directory / f"{name}.link"
            symlink.symlink_to(getattr(self, name))
            for path in (symlink, directory):
                with self.subTest(name=name, path=path.name), patch.object(self.tool, name.upper(), path):
                    self.assert_run(1, [f"FAIL input-unsafe {name}", FAIL])

    def test_c2_2_input_too_large(self):
        # The cap is enforced before JSON parsing even when an oversized file is malformed.
        oversized = self.directory / "oversized.json"
        oversized.write_bytes(b"?" * 101)
        with patch.object(self.tool, "INPUT_CAP", 100):
            for name in ("products", "makers"):
                with self.subTest(name=name), patch.object(self.tool, name.upper(), oversized):
                    self.assert_run(1, [f"FAIL input-too-large {name}", FAIL])

    def test_c2_3_input_unreadable(self):
        # Missing, decoding, parse and shape errors must stop before any matcher call.
        broken = self.directory / "broken.json"
        for name, wrong_shape in (
            ("products", b'{"products":[{"id":"fixture","name":"Pebble","status":1}]}'),
            ("makers", b'{"makers":{"fixture":{"name":"Pebble","place":"Fixture","url":1}}}'),
        ):
            for label, raw in (("missing", None), ("utf8", b"\xff"),
                               ("json", b"{"), ("shape", wrong_shape)):
                with self.subTest(name=name, error=label), patch.object(
                    self.tool, name.upper(), self.directory / "absent.json" if raw is None else broken
                ), patch.object(self.tool.missing, "_duplicates") as check:
                    if raw is not None:
                        broken.write_bytes(raw)
                    self.assert_run(1, [f"FAIL input-unreadable {name}", FAIL])
                    check.assert_not_called()

    def test_c2_4_variant_missed(self):
        # Mixed counts catch reporting 'tried' instead of 'tried minus caught' and wrong ordering.
        self.write_products(_product("Pebble"), _product("Stones"), _product("Pebbles", "inactive"))
        self.assert_run(1, _report((2, 2, 0, 2, 2, 0), (2, 2, 0, 1, 0, 0)) + [
            "FAIL variant-missed plural 1", "FAIL variant-missed the 2", FAIL,
        ])

    def test_c2_5_check_error(self):
        # A late matcher exception must not become a miss, a partial report, or a traceback.
        with patch.object(self.tool.missing, "_duplicates",
                          side_effect=[("catalog",), RuntimeError("synthetic diagnostic marker")]) as check:
            self.assert_run(1, ["FAIL check-error", FAIL])
            self.assertEqual(check.call_count, 2)

    def test_c3_usage_exit_2(self):
        # Even conventional help and the option separator are not admitted arguments.
        for arg in ("unexpected", "--bogus", "--help", "-h", "--", ""):
            with self.subTest(arg=arg):
                result = self.cli(arg)
                self.assertEqual(result.returncode, 2)
                self.assertEqual(result.stdout, "")
                self.assertTrue(result.stderr.startswith("usage:"))
                self.assertIn("error: unrecognized arguments:", result.stderr)

    def test_c4_read_only(self):
        # A check that updates catalog or storefront files must not pass unnoticed.
        def snapshot():
            state = {}
            for tree in (ROOT / "hass", ROOT / "storefront-mockup"):
                for path in (tree, *tree.rglob("*")):
                    metadata = path.lstat()
                    state[path.relative_to(ROOT)] = (metadata.st_size, metadata.st_mtime_ns)
            return state

        before = snapshot()
        result = self.cli()
        self.assertEqual(result.returncode, 1)
        self.assertEqual(result.stdout.splitlines()[-1], FAIL)
        self.assertEqual(result.stderr, "")
        self.assertEqual(snapshot(), before)
        self.assertEqual(set(self.directory.iterdir()), {self.makers, self.products})

    def test_c5_output_shape(self):
        # A name containing a newline cannot forge a finding or escape the counts-only format.
        self.write_products(_product("Synthetic\nFAIL fake marker"))
        self.assert_run(1, _report((1, 1, 1, 1, 1, 0), (1, 1, 1, 0, 0, 0)) + [
            "FAIL variant-missed plural 1", "FAIL variant-missed the 1", FAIL,
        ])

    def test_c6_fixture_pass(self):
        # Record exact calls to pin product order, literal transforms and unfiltered matcher data.
        products = [_product("Jun's Fir’s Tips"), _product("Bud"), _product("Skip", "Active")]
        makers = {"fixture": {"name": "Fixture", "place": "Somewhere", "story": "Inert"}}
        self.write_products(*products)
        self.makers.write_text(json.dumps({"makers": makers}), encoding="utf-8")
        totals = (2, 2, 1, 2, 2, 1)
        with patch.object(self.tool.missing, "_duplicates", return_value=("catalog",)) as check:
            self.assert_run(0, _report(totals, totals) + [PASS])
        self.assertEqual(check.call_args_list, [
            call(variant, products, makers, None) for variant in (
                "Jun's Fir’s Tips", "JUN'S FIR’S TIPS", "Jun's  Fir’s Tips", "Jun's Fir’s Tip",
                "the Jun's Fir’s Tips", "Juns Firs Tips", "Bud", "BUD", "Buds", "the Bud",
            )
        ])

    def test_c7_live_pins(self):
        # Pin the unpatched catalog result, not a reconstructed matcher or active-only subset.
        result = self.cli()
        self.assertEqual(result.returncode, 1)
        self.assertEqual(result.stdout, "\n".join(LIVE_REPORT) + "\n")
        self.assertEqual(result.stderr, "")


if __name__ == "__main__":
    unittest.main()
