"""Offline CLI contract for checking the pinned photo-read examples."""

from contextlib import redirect_stderr, redirect_stdout
import importlib.util
import io
import json
from pathlib import Path
import subprocess
import sys
from tempfile import TemporaryDirectory
import unittest
from unittest.mock import patch

from hass import npp
from hass.npp import identify

ROOT = Path(__file__).resolve().parents[2]
SCRIPT = ROOT / "scripts/hass/npp_identify_example_check.py"
EXAMPLES = "hass-product-identify/examples.json"
PASS = "PASS npp_identify_example_check"
FAIL = "FAIL npp_identify_example_check"

spec = importlib.util.spec_from_file_location("npp_identify_example_check", SCRIPT)
assert spec is not None and spec.loader is not None
checker = importlib.util.module_from_spec(spec)
spec.loader.exec_module(checker)


class IdentifyExampleCheckTests(unittest.TestCase):
    def fixture(self, *positions):
        pins, files, replies = npp.assets()
        examples = json.loads(files[EXAMPLES])["examples"]
        return pins, files, replies, [examples[i - 1] for i in positions]

    def run_fixture(self, fixture):
        pins, files, replies, examples = fixture
        with TemporaryDirectory() as temp:
            sample = Path(temp) / "examples.json"
            sample.write_text(json.dumps({"examples": examples}), encoding="utf-8")
            files = {**files, EXAMPLES: sample.read_bytes()}
            with patch.object(npp, "assets", return_value=(pins, files, replies)):
                return self.run_main()

    def run_main(self):
        stdout, stderr = io.StringIO(), io.StringIO()
        with redirect_stdout(stdout), redirect_stderr(stderr):
            code = checker.main([])
        return code, stdout.getvalue(), stderr.getvalue()

    def run_cli(self, *args):
        with TemporaryDirectory() as temp:
            run = subprocess.run([sys.executable, "-B", str(SCRIPT), *args],
                                 cwd=temp, capture_output=True, text=True, timeout=20)
        return run.returncode, run.stdout, run.stderr

    def assert_run(self, run, code, trailer):
        status, stdout, stderr = run
        self.assertEqual(status, code, stderr)
        self.assertEqual(stderr, "")
        lines = stdout.splitlines()
        self.assertEqual(lines[-1], trailer)
        return lines[:-1]

    def test_c1_full_pass(self):
        # An informational retitle must not flip a full pass to a failure.
        self.assertEqual(self.assert_run(self.run_fixture(self.fixture(1)), 0, PASS),
                         ["example 01 changed=item", "retitle 01"])

    def test_c2_findings_trailer(self):
        # Neither a later clean example nor a finding mid-run should end the check early.
        lines = self.assert_run(self.run_fixture(self.fixture(5, 6)), 1, FAIL)
        self.assertEqual(lines, ["example 01 changed=confidence",
                                 "FAIL example-confidence 01 item", "example 02 changed=none"])

    def test_c2_1_assets_unreadable(self):
        # Asset exceptions must fail closed and omit the underlying diagnostic.
        with patch.object(npp, "assets", side_effect=ValueError("synthetic diagnostic")):
            self.assertEqual(self.assert_run(self.run_main(), 1, FAIL),
                             ["FAIL assets-unreadable"])

    def test_c2_2_example_confidence(self):
        # Both scores must be reported in name order, not the JSON's insertion order.
        fixture = self.fixture(6)
        fixture[3][0]["output"]["confidence"].update(item=0.4, brand=0.2)
        self.assertEqual(self.assert_run(self.run_fixture(fixture), 1, FAIL),
                         ["example 01 changed=confidence", "FAIL example-confidence 01 brand",
                          "FAIL example-confidence 01 item"])

    def test_c2_3_example_rewritten(self):
        # Changing the item to null is not a retitle; other rewritten keys also fail.
        fixture = self.fixture(6)
        fixture[3][0]["output"].update(item="Synthetic Item", size_text="invalid unit")
        self.assertEqual(self.assert_run(self.run_fixture(fixture), 1, FAIL),
                         ["example 01 changed=item,size_text", "FAIL example-rewritten 01 item",
                          "FAIL example-rewritten 01 size_text"])

    def test_c2_4_check_error(self):
        # Report the failing position once, suppress details, and finish the next example.
        normalize = identify._normalize

        def fail_first(raw, schema):
            if raw["is_product"]:
                raise ValueError("synthetic diagnostic")
            return normalize(raw, schema)

        with patch.object(identify, "_normalize", side_effect=fail_first):
            lines = self.assert_run(self.run_fixture(self.fixture(4, 6)), 1, FAIL)
        self.assertEqual(lines, ["FAIL check-error 01", "example 02 changed=none"])

    def test_c3_usage_exit_2(self):
        # Unknown arguments, including argparse's usual special options, are not accepted.
        for arg in ("positional", "--unknown", "--help", "--"):
            with self.subTest(arg=arg):
                code, stdout, stderr = self.run_cli(arg)
                self.assertEqual(code, 2)
                self.assertEqual(stdout, "")
                self.assertTrue(stderr.startswith("usage: "))
                self.assertEqual(stderr.splitlines()[-1],
                                 f"{SCRIPT.name}: error: unrecognized arguments: {arg}")

    def test_c4_read_only(self):
        # Detect bytecode, generated output, or accidental asset rewrites in these trees.
        def snapshot():
            entries = {}
            for name in ("hass", "storefront-mockup"):
                tree = ROOT / name
                for path in (tree, *tree.rglob("*")):
                    info = path.lstat()
                    entries[path.relative_to(ROOT)] = (info.st_size, info.st_mtime_ns)
            return entries

        before = snapshot()
        self.assert_run(self.run_cli(), 1, FAIL)
        self.assertEqual(snapshot(), before)

    def test_c5_output_shape(self):
        # Findings must not include values, debug lines, blank lines, or stderr text.
        lines = self.assert_run(self.run_cli(), 1, FAIL)
        for line in lines:
            self.assertRegex(line, r"\A(?:example \d{2} changed=(?:[a-z_]+,)*[a-z_]+"
                                   r"|retitle \d{2}|FAIL example-confidence \d{2} [a-z_]+)\Z")

    def test_c6_fixture(self):
        # Filtering the inputs must neither retain old indices nor introduce changes.
        self.assertEqual(self.assert_run(self.run_fixture(self.fixture(4, 6)), 0, PASS),
                         ["example 01 changed=none", "example 02 changed=none"])

    def test_c7_live_pins(self):
        # Pin the measured asset output so lost examples or findings cannot go unnoticed.
        self.assertEqual(self.assert_run(self.run_cli(), 1, FAIL), [
            "example 01 changed=item", "retitle 01",
            "example 02 changed=item", "retitle 02",
            "example 03 changed=confidence,item", "FAIL example-confidence 03 brand", "retitle 03",
            "example 04 changed=none",
            "example 05 changed=confidence", "FAIL example-confidence 05 item",
            "example 06 changed=none",
        ])
