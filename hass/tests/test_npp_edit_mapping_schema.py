"""Offline contract tests for the S10 edit-mapping drift check."""

from contextlib import redirect_stderr, redirect_stdout
import copy
import importlib.util
import io
from pathlib import Path
import subprocess
import sys
from tempfile import TemporaryDirectory
import unittest
from unittest.mock import patch


ROOT = Path(__file__).resolve().parents[2]
SCRIPT = ROOT / "scripts/hass/npp_edit_mapping_schema.py"
PASS = "PASS npp_edit_mapping_schema"
FAIL = "FAIL npp_edit_mapping_schema"
PINS = "pins maxItems=4 maxLength=80 fields=9 ask_ids=6"


class EditMappingSchemaTests(unittest.TestCase):
    def setUp(self):
        self.scratch = self.enterContext(TemporaryDirectory())
        spec = importlib.util.spec_from_file_location(SCRIPT.stem, SCRIPT)
        if spec is None or spec.loader is None:
            raise ImportError(f"Cannot load {SCRIPT.name}")
        self.tool = importlib.util.module_from_spec(spec)
        with patch.object(sys, "path", sys.path.copy()):
            spec.loader.exec_module(self.tool)

    def cli(self, *args):
        return subprocess.run([sys.executable, "-B", str(SCRIPT), *args],
                              cwd=self.scratch, capture_output=True, text=True, timeout=10)

    def run_main(self):
        stdout, stderr = io.StringIO(), io.StringIO()
        with redirect_stdout(stdout), redirect_stderr(stderr):
            code = self.tool.main([])
        self.assertEqual(stderr.getvalue(), "")
        return code, stdout.getvalue().splitlines()

    def assert_findings(self, result, *expected):
        code, lines = result
        self.assertEqual(code, 1)
        self.assertEqual(lines[-1], FAIL)
        self.assertEqual([line for line in lines[:-1] if line.startswith("FAIL ")], list(expected))
        return lines

    def field_enum(self, schema):
        return schema["properties"]["patches"]["items"]["properties"]["field"]["enum"]

    def test_c1_full_pass(self):
        # A good run must return success, not just print successful case lines.
        code, lines = self.run_main()
        self.assertEqual(code, 0)
        self.assertEqual(lines[-1], PASS)

    def test_c2_findings_trailer(self):
        # One real schema change causes two findings; neither should suppress the other.
        grammar = self.tool.edits.Grammar(self.tool.hass.npp.assets()[1])
        self.field_enum(grammar.schema).append("photo")
        with patch.object(self.tool.edits, "Grammar", return_value=grammar):
            result = self.run_main()
        lines = self.assert_findings(result, "FAIL verdict 9", "FAIL schema-drift")
        self.assertIn("case 9 accepted", lines)
        self.assertEqual(lines[-3], "pins maxItems=4 maxLength=80 fields=10 ask_ids=6")

    def test_c2_1_verdict(self):
        # An exception on a normally refused case is a finding, not a refusal or a crash.
        real_check = self.tool.edits.valid_mapping

        def throw_on_list(doc, schema):
            if doc == []:
                raise RuntimeError("synthetic validator exception")
            return real_check(doc, schema)

        with patch.object(self.tool.edits, "valid_mapping", side_effect=throw_on_list):
            result = self.run_main()
        lines = self.assert_findings(result, "FAIL verdict 15")
        self.assertNotIn("case 15 refused", lines)
        self.assertIn("case 16 refused", lines)
        self.assertEqual(lines[-2], PINS)

    def test_c2_2_schema_drift(self):
        # A pin may move without any case flipping: do not infer pin health from verdicts.
        grammar = self.tool.edits.Grammar(self.tool.hass.npp.assets()[1])
        self.field_enum(grammar.schema).remove("add_note")
        with patch.object(self.tool.edits, "Grammar", return_value=grammar):
            result = self.run_main()
        lines = self.assert_findings(result, "FAIL schema-drift")
        self.assertEqual(lines[-3], "pins maxItems=4 maxLength=80 fields=8 ask_ids=6")

    def test_c2_3_check_error(self):
        # Asset loader failure must not leak a traceback or silently skip the check.
        with patch.object(self.tool.hass.npp, "assets", side_effect=RuntimeError("synthetic loader exception")):
            result = self.run_main()
        self.assertEqual(self.assert_findings(result, "FAIL check-error"), ["FAIL check-error", FAIL])

    def test_c3_usage_exit_2(self):
        # No optional help/flags, positional arguments or bare separator are admitted.
        for arg in ("extra", "--unknown", "--help", "-h", "--"):
            with self.subTest(arg=arg):
                result = self.cli(arg)
                self.assertEqual(result.returncode, 2)
                self.assertEqual(result.stdout, "")
                self.assertEqual(result.stderr.splitlines()[-1],
                                 f"{SCRIPT.name}: error: unrecognized arguments: {arg}")

    def test_c4_read_only(self):
        # Catch new outputs, rewritten files, or directory changes under either tree.
        def snapshot():
            entries = {}
            for tree in (ROOT / "hass", ROOT / "storefront-mockup"):
                for path in (tree, *tree.rglob("*")):
                    stat = path.lstat()
                    entries[path.relative_to(ROOT)] = (stat.st_size, stat.st_mtime_ns)
            return entries

        before = snapshot()
        result = self.cli()
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(result.stdout.splitlines()[-1], PASS)
        self.assertEqual(snapshot(), before)

    def test_c5_output_shape(self):
        # Extra status text, blank rows, and stderr chatter break the CLI's output protocol.
        result = self.cli()
        self.assertEqual(result.returncode, 0)
        self.assertEqual(result.stderr, "")
        lines = result.stdout.splitlines()
        self.assertEqual(lines[-1], PASS)
        self.assertEqual(len(lines), 19)
        for i, line in enumerate(lines[:17]):
            self.assertRegex(line, rf"^case {i} (accepted|refused)$")
        self.assertRegex(lines[-2], r"^pins maxItems=\d+ maxLength=\d+ fields=\d+ ask_ids=\d+$")

    def test_c6_fixture(self):
        # Give only the real validator a looser schema; the reported pins must stay live.
        real_check = self.tool.edits.valid_mapping

        def with_extra_patch(doc, schema):
            relaxed = copy.deepcopy(schema)
            relaxed["properties"]["patches"]["maxItems"] = 5
            return real_check(doc, relaxed)

        with patch.object(self.tool.edits, "valid_mapping", side_effect=with_extra_patch):
            result = self.run_main()
        lines = self.assert_findings(result, "FAIL verdict 5")
        self.assertEqual(lines[5:7], ["case 5 accepted", "FAIL verdict 5"])
        self.assertEqual(lines[-2], PINS)

    def test_c7_live_pins(self):
        # Use an independent oracle; changed verdicts or pins on main cannot redefine success.
        result = self.cli()
        self.assertEqual(result.returncode, 0, result.stderr)
        accepted = {0, 1, 6, 8, 13}
        lines = [f"case {i} {'accepted' if i in accepted else 'refused'}" for i in range(17)]
        self.assertEqual(result.stdout.splitlines(), [*lines, PINS, PASS])
