"""Offline CLI and fault-injection tests for the S2 schema drift guard."""

from contextlib import ExitStack, redirect_stderr, redirect_stdout
from copy import deepcopy
import importlib.util
import io
import json
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import patch

from hass import npp
from hass.npp import identify


ROOT = Path(__file__).resolve().parents[2]
SCRIPT = ROOT / "scripts/hass/npp_identify_schema_enforced.py"
ASSET = identify.ASSET + "identify.schema.json"
SPEC = importlib.util.spec_from_file_location(SCRIPT.stem, SCRIPT)
assert SPEC is not None and SPEC.loader is not None
CHECK = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(CHECK)
PASS = "PASS npp_identify_schema_enforced"
FAIL = "FAIL npp_identify_schema_enforced"
KEYWORDS = "additionalProperties,enum,maxItems,maxLength,maximum,minLength,minimum,required,type"


def snapshot():
    entries = {}
    for tree in (ROOT / "hass", ROOT / "storefront-mockup"):
        for path in (tree, *tree.rglob("*")):
            info = path.lstat()
            entries[path.relative_to(ROOT)] = (info.st_size, info.st_mtime_ns)
    return entries


def ignore_max_length():
    valid = identify._valid

    def without_max_length(value, schema):
        # _valid recurses through its module global, so this also strips item rules.
        return valid(value, {key: val for key, val in schema.items() if key != "maxLength"})

    return patch.object(identify, "_valid", side_effect=without_max_length)


class IdentifySchemaEnforcedTests(unittest.TestCase):
    def setUp(self):
        work = tempfile.TemporaryDirectory(dir=ROOT.parent)
        self.addCleanup(work.cleanup)
        self.work = Path(work.name)

    def cli(self, *argv):
        return subprocess.run([sys.executable, "-B", str(SCRIPT), *argv], cwd=self.work,
                              text=True, capture_output=True, timeout=10)

    def in_process(self, *patches):
        out, err = io.StringIO(), io.StringIO()
        with ExitStack() as stack:
            stack.enter_context(redirect_stdout(out))
            stack.enter_context(redirect_stderr(err))
            for change in patches:
                stack.enter_context(change)
            code = CHECK.main([])
        return subprocess.CompletedProcess([], code, out.getvalue(), err.getvalue())

    def schema_fixture(self, edit):
        pins, files, replies = npp.assets()
        fixture = self.work / "identify.schema.json"
        schema = json.loads(files[ASSET])
        edit(schema)
        fixture.write_text(json.dumps(schema), encoding="utf-8")
        return patch.object(npp, "assets", return_value=(pins, {**files, ASSET: fixture.read_bytes()}, replies))

    def assert_exit(self, result, code, trailer):
        self.assertEqual(result.returncode, code, result.stderr)
        self.assertEqual(result.stderr, "")
        lines = result.stdout.splitlines()
        self.assertEqual(lines[-1:], [trailer])
        return lines

    def assert_findings(self, result, findings):
        lines = self.assert_exit(result, 1, FAIL)
        self.assertEqual([line for line in lines[:-1] if line.startswith("FAIL ")], findings)
        return lines

    def test_c1_full_pass(self):
        # The bare CLI must work outside the repo and audit all measured sites.
        lines = self.assert_exit(self.cli(), 0, PASS)
        self.assertEqual(lines, [f"schema keywords={KEYWORDS}", "schema sites=43 refused=43", PASS])

    def test_c2_findings_trailer(self):
        # Do not stop at the first unknown rule or accidentally print PASS.
        def add_unknowns(schema):
            schema["properties"]["item"]["pattern"] = "^H"
            schema["properties"]["label_words"]["minItems"] = 0

        self.assert_findings(self.in_process(self.schema_fixture(add_unknowns)),
                             ["FAIL unknown-keyword pattern", "FAIL unknown-keyword minItems"])

    def test_c2_1_unknown_keyword(self):
        # Report a repeated keyword once, even in both an item and a property schema.
        def add_pattern_twice(schema):
            props = schema["properties"]
            props["item"]["pattern"] = "^H"
            props["label_words"]["items"]["pattern"] = "^x"
            props["brand_on_label"]["description"] = "fixture annotation"

        lines = self.assert_findings(self.in_process(self.schema_fixture(add_pattern_twice)),
                                     ["FAIL unknown-keyword pattern"])
        self.assertIn("schema sites=45 refused=43", lines)

    def test_c2_2_not_enforced(self):
        # Widen only the 12-item limit, so exactly that site's witness is accepted.
        valid = identify._valid

        def widen_label_limit(value, schema):
            if schema.get("maxItems") == 12:
                schema = {**schema, "maxItems": 13}
            return valid(value, schema)

        lines = self.assert_findings(self.in_process(patch.object(identify, "_valid", side_effect=widen_label_limit)),
                                     ["FAIL not-enforced $.label_words maxItems"])
        self.assertIn("schema sites=43 refused=42", lines)

        # An enum can otherwise reject the wrong type even with a broken type check.
        def allow_boolean_for_string(value, schema):
            if schema.get("type") == "string" and value is True:
                schema = {**schema, "type": ["string", "boolean"]}
            return valid(value, schema)

        self.assert_findings(self.in_process(patch.object(identify, "_valid", side_effect=allow_boolean_for_string)),
                             ["FAIL not-enforced $.kind type", "FAIL not-enforced $.label_words[0] type",
                              "FAIL not-enforced $.visible_claims[0] type"])

    def test_c2_3_base_refused(self):
        # An invalid control must not be counted as evidence that mutations work.
        validator = patch.object(identify, "_valid", return_value=False)
        with validator as called:
            result = self.in_process()
        self.assertEqual(self.assert_findings(result, ["FAIL base-refused"]), ["FAIL base-refused", FAIL])
        called.assert_called_once()
        self.assertEqual(called.call_args.args[0], CHECK.BASE)

    def test_c2_4_check_error(self):
        # Both errors must be classified without leaking exception text or a traceback.
        for module, name in ((npp, "assets"), (identify, "_valid")):
            with self.subTest(name=name):
                failure = patch.object(module, name, side_effect=ValueError("fixture exception text"))
                self.assertEqual(self.assert_findings(self.in_process(failure), ["FAIL check-error"]),
                                 ["FAIL check-error", FAIL])

    def test_c3_usage_exit_2(self):
        # Argparse normally accepts help and a bare separator; neither is an admitted argument.
        for arg in ("extra", "--unexpected", "--help", "--"):
            with self.subTest(arg=arg):
                result = self.cli(arg)
                self.assertEqual((result.returncode, result.stdout), (2, ""))
                self.assertTrue(result.stderr.startswith("usage:"))
                self.assertRegex(result.stderr.splitlines()[-1], r"\.py: error: .+")

    def test_c4_read_only(self):
        # A report write or import cache must not alter either monitored source tree.
        before = snapshot()
        self.assert_exit(self.cli(), 0, PASS)
        self.assertEqual(snapshot(), before)
        self.assertEqual(list(self.work.iterdir()), [])

    def test_c5_output_shape(self):
        # No noisy trace or stderr even when findings and both information lines coexist.
        def add_pattern(schema):
            schema["properties"]["item"]["pattern"] = "^H"

        lines = self.assert_exit(self.in_process(self.schema_fixture(add_pattern), ignore_max_length()), 1, FAIL)
        self.assertEqual(len(lines), 9)
        for line in lines[:-1]:
            self.assertRegex(line, r"^(schema keywords=[a-zA-Z,]+|schema sites=\d+ refused=\d+|"
                                   r"FAIL unknown-keyword \w+|FAIL not-enforced \$\S* \w+)$")

    def test_c6_fixture(self):
        # Losing _valid's length check must expose every nullable and array-item site.
        fixture = self.in_process(ignore_max_length())
        paths = ("$.item", "$.brand_on_label", "$.size_text", "$.label_words[0]", "$.visible_claims[0]")
        lines = self.assert_findings(fixture, [f"FAIL not-enforced {path} maxLength" for path in paths])
        self.assertIn("schema sites=43 refused=38", lines)

        def add_pattern(schema):
            schema["properties"]["item"]["pattern"] = "^H"

        self.assert_findings(self.in_process(self.schema_fixture(add_pattern)), ["FAIL unknown-keyword pattern"])

    def test_c7_live_pins(self):
        # The real validator, not a mock or the audit's witness builder, refuses these pinned examples.
        schema = json.loads(npp.assets()[1][ASSET])
        self.assertIs(identify._valid(CHECK.BASE, schema), True)
        mutations = (
            {"is_product": 1}, {"kind": "tool"}, {"item": "x" * 81}, {"brand_on_label": "x" * 61},
            {"size_text": "x" * 31}, {"label_words": ["x"] * 13}, {"label_words": [""]},
            {"label_words": ["x" * 41]}, {"visible_claims": ["x"] * 9}, {"category_guess": "toys"},
            {"has_person_or_screen": None}, {"extra": None},
            *({"confidence": {**CHECK.BASE["confidence"], "item": value}} for value in (1.5, -0.1, True)),
            {"confidence": {**CHECK.BASE["confidence"], "extra": 0.5}},
        )
        answers = [{**deepcopy(CHECK.BASE), **change} for change in mutations]
        missing_kind = deepcopy(CHECK.BASE)
        del missing_kind["kind"]
        missing_size = deepcopy(CHECK.BASE)
        del missing_size["confidence"]["size"]
        for index, answer in enumerate([*answers, missing_kind, missing_size]):
            with self.subTest(case=index):
                self.assertIs(identify._valid(answer, schema), False)
        self.assert_exit(self.in_process(), 0, PASS)


if __name__ == "__main__":
    unittest.main()
