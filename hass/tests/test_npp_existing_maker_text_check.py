"""Contract tests for the offline existing-maker S7 replay."""

from collections import Counter
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
SCRIPT = ROOT / "scripts/hass/npp_existing_maker_text_check.py"
PASS = "PASS npp_existing_maker_text_check"
FAIL = "FAIL npp_existing_maker_text_check"
BASIC = {"name": "Test Maker", "place": "Springfield, CA"}

spec = importlib.util.spec_from_file_location("npp_existing_maker_text_check", SCRIPT)
assert spec is not None and spec.loader is not None
check = importlib.util.module_from_spec(spec)
spec.loader.exec_module(check)


class ExistingMakerTextCheckTests(unittest.TestCase):
    def setUp(self):
        temporary = tempfile.TemporaryDirectory()
        self.addCleanup(temporary.cleanup)
        self.root = Path(temporary.name)
        self.source = self.root / "fixture.json"

    def fixture(self, makers):
        self.source.write_text(json.dumps({"makers": makers}), encoding="utf-8")

    def assert_report(self, code, stdout, stderr, expected_code, trailer):
        self.assertEqual(code, expected_code)
        self.assertEqual(stderr, "")
        lines = stdout.splitlines()
        self.assertTrue(lines)
        self.assertEqual(lines[-1], trailer)
        return lines[:-1]

    def run_fixture(self, code, *lines, source=None):
        out, err = io.StringIO(), io.StringIO()
        with (patch.object(check, "MAKERS", source or self.source),
              redirect_stdout(out), redirect_stderr(err)):
            actual = check.main([])
        self.assertEqual(self.assert_report(actual, out.getvalue(), err.getvalue(),
                                           code, PASS if code == 0 else FAIL), list(lines))

    def cli(self, *args):
        return subprocess.run([sys.executable, "-B", str(SCRIPT), *args],
                              cwd=self.root, capture_output=True, text=True, timeout=10)

    def test_c1_full_pass(self):
        # Optional fields aren't required; non-string metadata isn't screened or counted.
        self.fixture({"fixture-a": dict(BASIC, metadata=42)})
        self.run_fixture(0, "makers 1", "values 2")

    def test_c2_findings_trailer(self):
        # An early hit must not stop the scan or be overwritten by the final clean record.
        self.fixture({"fixture-a": dict(BASIC, url="https://example.org/12"),
                      "fixture-b": dict(BASIC, url="https://example.org/34"),
                      "fixture-c": BASIC})
        self.run_fixture(1, "makers 3", "values 8", "FAIL maker-text 1 url unsupported-number",
                         "FAIL maker-text 2 url unsupported-number")

    def test_c2_1_input_unsafe(self):
        # Opening before checking the mode could follow a symlink or read a directory.
        self.fixture({"fixture-a": BASIC})
        alias = self.root / "alias.json"
        alias.symlink_to(self.source)
        for source in (alias, self.root):
            with self.subTest(kind=source.name):
                self.run_fixture(1, "FAIL input-unsafe makers", source=source)

    def test_c2_2_input_too_large(self):
        # Size refusal takes precedence even when the bytes are not JSON.
        self.source.write_bytes(b"x" * 17)
        with patch.object(check, "MAKERS_CAP", 16):
            self.run_fixture(1, "FAIL input-too-large makers")

    def test_c2_3_input_unreadable(self):
        # These inputs must not produce counts, partial findings, or parser diagnostics.
        for kind, raw in (
            ("missing", None), ("utf8", b"\xff"), ("json", b"{"),
            ("non-json-constant", b'{"makers":{},"extra":NaN}'),
            ("root", b"[]"), ("makers", b'{"makers":[]}'),
            ("record", b'{"makers":{"fixture-a":[]}}'),
            ("required", b'{"makers":{"fixture-a":{"name":"Test Maker"}}}'),
            ("optional", json.dumps({"makers": {"fixture-a": dict(BASIC, story=None)}}).encode()),
        ):
            with self.subTest(kind=kind):
                if raw is not None:
                    self.source.write_bytes(raw)
                self.run_fixture(1, "FAIL input-unreadable makers")

    def test_c2_4_maker_text(self):
        # Sorting records/fields, screening digits in stories or preferring the number verdict breaks this.
        self.fixture({"fixture-z": {"url": "https://example.org/12", "place": "District 12",
                                    "story": "Founded in 2001.", "name": "Test Maker"},
                      "fixture-a": dict(BASIC, story="Email shop12@example.org.")})
        self.run_fixture(1, "makers 2", "values 7", "FAIL maker-text 1 url unsupported-number",
                         "FAIL maker-text 1 place unsupported-number", "FAIL maker-text 2 story contact")

    def test_c2_5_field_invalid(self):
        # Arbitrary string fields are checked; only a failing unknown key gets a redacted finding.
        self.fixture({"fixture-a": dict(BASIC, **{"extra\nmarker": "District 12", "clear": "Jam"})})
        self.run_fixture(1, "makers 1", "values 4", "FAIL field-invalid")

    def test_c2_6_reason_invalid(self):
        # Invalid detector results must neither leak nor become a pass via truthiness.
        self.fixture({"fixture-a": BASIC})
        for reason in ("extra\nmarker", "", "a" * 42, 3):
            with self.subTest(reason=reason), patch.object(check.private_numbers, "problem", return_value=reason):
                self.run_fixture(1, "makers 1", "values 2", "FAIL reason-invalid", "FAIL reason-invalid")

    def test_c2_7_check_error(self):
        # An exception from either detector must not leak its message or hide later results.
        self.fixture({"fixture-a": dict(BASIC, url="https://example.org/12")})
        for module, name in ((check.validate, "_contact"), (check.private_numbers, "problem")):
            detector = getattr(module, name)

            def fail_once(value, *args, **kwargs):
                if value == BASIC["name"]:
                    raise RuntimeError("synthetic diagnostic marker")
                return detector(value, *args, **kwargs)

            with self.subTest(detector=name), patch.object(module, name, side_effect=fail_once):
                self.run_fixture(1, "makers 1", "values 3", "FAIL check-error",
                                 "FAIL maker-text 1 url unsupported-number")

    def test_c3_usage_exit_2(self):
        # Argparse's default help and bare delimiter must not escape the strict no-args contract.
        for arg in ("--unknown", "catalog.json", "--help", "--"):
            with self.subTest(arg=arg):
                result = self.cli(arg)
                self.assertEqual((result.returncode, result.stdout), (2, ""))
                self.assertIn("usage:", result.stderr)
                self.assertEqual(result.stderr.splitlines()[-1],
                                 f"{SCRIPT.name}: error: no arguments accepted")

    def test_c4_read_only(self):
        # Catch catalog/cache writes and new paths in either source tree.
        def snapshot():
            state = {}
            for name in ("hass", "storefront-mockup"):
                tree = ROOT / name
                for path in (tree, *tree.rglob("*")):
                    info = path.lstat()
                    state[path.relative_to(ROOT)] = (info.st_size, info.st_mtime_ns)
            return state

        before = snapshot()
        result = self.cli()
        self.assert_report(result.returncode, result.stdout, result.stderr, 1, FAIL)
        self.assertEqual(snapshot(), before)

    def test_c5_output_shape(self):
        # Exact lines exclude maker IDs, field contents, and diagnostic output on both streams.
        self.fixture({"hidden-fixture-id": dict(BASIC, url="https://example.org/12",
                                               **{"hidden-fixture-key": "District 12"})})
        self.run_fixture(1, "makers 1", "values 4", "FAIL maker-text 1 url unsupported-number",
                         "FAIL field-invalid")

    def test_c6_fixture_pass(self):
        # A normal four-field maker including a URL must not be falsely flagged.
        self.fixture({"fixture-a": dict(BASIC, story="Makes jam in small batches.",
                                        url="https://example.org/")})
        self.run_fixture(0, "makers 1", "values 4")

    def test_c7_live_pins(self):
        # Detect drift in either the checked-in catalog or the inherited S7 verdicts.
        result = self.cli()
        lines = self.assert_report(result.returncode, result.stdout, result.stderr, 1, FAIL)
        self.assertEqual(lines[:2], ["makers 26", "values 104"])
        self.assertEqual(len(lines[2:]), 5)
        for line in lines[2:]:
            self.assertRegex(line, r"^FAIL maker-text [1-9][0-9]* (story number-unclear|url unsupported-number)$")
        self.assertEqual(Counter(line.split(" ", 3)[-1] for line in lines[2:]),
                         {"story number-unclear": 4, "url unsupported-number": 1})
