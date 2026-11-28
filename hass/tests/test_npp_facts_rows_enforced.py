"""Offline behavior and live-pin tests for the maker-fact row drift guard."""

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
from hass.npp import research


ROOT = Path(__file__).resolve().parents[2]
SCRIPT = ROOT / "scripts/hass/npp_facts_rows_enforced.py"
ASSET = "hass-maker-research/facts.schema.json"
PASS = "PASS npp_facts_rows_enforced"
FAIL = "FAIL npp_facts_rows_enforced"
SUMMARY = "facts sites=16 refused=16"
ROW = {"slot": "makes", "value": "honey", "url": "https://ettofarm.example/",
       "quote": "Etto Farm makes honey."}


def one(**delta):
    return {"facts": [ROW | delta]}


# Pin independent inputs, not the guard's generator. The original 13 rejection
# cases are unchanged; the three other string fields also get type witnesses.
PROBES = {
    "top.additionalProperties": one() | {"id": 0},
    "facts.type": {"facts": ROW},
    "facts.maxItems": {"facts": [ROW] * 13},
    "items.additionalProperties": one(id=0),
    "items.required": {"facts": [{k: v for k, v in ROW.items() if k != "quote"}]},
    "slot.enum": one(slot="phone"),
    "slot.type": one(slot=1),
    "value.minLength": one(value=""),
    "value.maxLength": one(value="x" * 81),
    "value.type": one(value=1),
    "url.minLength": one(url="x" * 7),
    "url.maxLength": one(url="x" * 201),
    "url.type": one(url=1),
    "quote.minLength": one(quote="xx"),
    "quote.maxLength": one(quote="x" * 301),
    "quote.type": one(quote=1),
}


def field_specs(schema):
    return schema["properties"]["facts"]["items"]["properties"]


class NppFactsRowsEnforcedTests(unittest.TestCase):
    def setUp(self):
        temporary = TemporaryDirectory()
        self.addCleanup(temporary.cleanup)
        self.directory = Path(temporary.name)
        spec = importlib.util.spec_from_file_location("npp_facts_rows_enforced", SCRIPT)
        assert spec is not None and spec.loader is not None
        self.tool = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(self.tool)

    def cli(self, *args):
        return subprocess.run([sys.executable, "-B", str(SCRIPT), *args],
                              cwd=self.directory, capture_output=True, text=True, timeout=10)

    def in_process(self):
        out, err = io.StringIO(), io.StringIO()
        with redirect_stdout(out), redirect_stderr(err):
            code = self.tool.main([])
        return code, out.getvalue().splitlines(), err.getvalue()

    def assert_run(self, result, code, trailer, *lines):
        actual, stdout, stderr = result
        self.assertEqual(actual, code)
        self.assertEqual(stderr, "")
        self.assertEqual(stdout[-1:], [trailer])
        self.assertEqual(stdout[:-1], list(lines))

    def patch_schema(self, **overrides):
        pins, files, replies = npp.assets()
        schema = json.loads(files[ASSET])
        for field, spec in overrides.items():
            field_specs(schema)[field].update(spec)
        fixture = self.directory / "facts.schema.json"
        fixture.write_text(json.dumps(schema), encoding="utf-8")
        return patch.object(npp, "assets", side_effect=lambda: (
            pins, files | {ASSET: fixture.read_bytes()}, replies))

    def test_c1_full_pass(self):
        # The absolute CLI path must work without the repo as the working directory.
        result = self.cli()
        self.assert_run((result.returncode, result.stdout.splitlines(), result.stderr),
                        0, PASS, SUMMARY)

    def test_c2_findings_trailer(self):
        # A later refusal must neither discard earlier findings nor end in PASS.
        with patch.object(research, "_rows", side_effect=lambda result, schema: (
            [] if result in (PROBES["value.maxLength"], PROBES["quote.maxLength"])
            else None)):
            self.assert_run(self.in_process(), 1, FAIL, "FAIL base-refused", "FAIL limit-refused",
                            "FAIL not-enforced value.maxLength", "FAIL not-enforced quote.maxLength",
                            "facts sites=16 refused=14")

    def test_c2_1_not_enforced(self):
        # Non-None means kept, even for a falsey return value.
        original = research._rows
        with patch.object(research, "_rows", side_effect=lambda result, schema: (
            [] if result == PROBES["value.maxLength"] else original(result, schema))):
            self.assert_run(self.in_process(), 1, FAIL, "FAIL not-enforced value.maxLength",
                            "facts sites=16 refused=15")

    def test_c2_2_limit_refused(self):
        # Off-by-one at the accepted boundary, not at the overflow case.
        original = research._rows
        with patch.object(research, "_rows", side_effect=lambda result, schema: (
            None if result == {"facts": [ROW] * 12} else original(result, schema))):
            self.assert_run(self.in_process(), 1, FAIL, "FAIL limit-refused", SUMMARY)

    def test_c2_3_unknown_keyword(self):
        # Ignoring unfamiliar field constraints—or reporting per field—is wrong.
        with self.patch_schema(value={"pattern": "^h"}, quote={"pattern": "^Etto"}):
            self.assert_run(self.in_process(), 1, FAIL, "FAIL unknown-keyword pattern", SUMMARY)

    def test_c2_4_base_refused(self):
        # Even with an accepted limit and all the intended refusals, ROW must keep.
        original = research._rows
        with patch.object(research, "_rows", side_effect=lambda result, schema: (
            None if result == one() else original(result, schema))):
            self.assert_run(self.in_process(), 1, FAIL, "FAIL base-refused", SUMMARY)

    def test_c2_5_check_error(self):
        # Both loader and checker errors fail closed, without exception text.
        error = RuntimeError("synthetic error detail")
        for module, name, summary in ((npp, "assets", "facts sites=0 refused=0"),
                                      (research, "_rows", "facts sites=16 refused=0")):
            with self.subTest(name=name), patch.object(module, name, side_effect=error) as failure:
                self.assert_run(self.in_process(), 1, FAIL, "FAIL check-error", summary)
                failure.assert_called()

    def test_c3_usage_exit_2(self):
        # No option, including help or the end-of-options marker, runs the check.
        for option in ("positional", "--unknown", "--help", "--"):
            with self.subTest(option=option):
                result = self.cli(option)
                self.assertEqual(result.returncode, 2)
                self.assertEqual(result.stdout, "")  # No trailer on usage errors.
                self.assertIn("usage:", result.stderr)

    def test_c4_read_only(self):
        # A CLI that writes a receipt or modifies an input must not pass unnoticed.
        def snapshot():
            entries = {}
            for directory in (ROOT / "hass", ROOT / "storefront-mockup", self.directory):
                for path in (directory, *directory.rglob("*")):
                    info = path.lstat()
                    entries[path] = info.st_size, info.st_mtime_ns
            return entries

        before = snapshot()
        result = self.cli()
        self.assert_run((result.returncode, result.stdout.splitlines(), result.stderr),
                        0, PASS, SUMMARY)
        self.assertEqual(snapshot(), before)

    def test_c5_output_shape(self):
        # Findings use the stdout protocol, not logging or incidental debug text.
        with self.patch_schema(value={"pattern": "^h"}, quote={"maxLength": 20}):
            self.assert_run(self.in_process(), 1, FAIL, "FAIL base-refused",
                            "FAIL unknown-keyword pattern", SUMMARY)

    def test_c6_fixture(self):
        # A tighter pin invalidates only the original control. It must not mask
        # broken witnesses or turn the adapted limit control into a false refusal.
        with self.patch_schema(quote={"maxLength": 20}), patch.object(
            research, "_rows", wraps=research._rows,
        ) as rows:
            self.assert_run(self.in_process(), 1, FAIL, "FAIL base-refused", SUMMARY)
            self.assertTrue(any(
                result == one(quote="x" * 21) and field_specs(schema)["quote"]["maxLength"] == 20
                for result, schema in (call.args for call in rows.call_args_list)
            ))
        with patch.object(research, "_rows", side_effect=lambda result, schema: result):
            self.assert_run(self.in_process(), 1, FAIL,
                            *(f"FAIL not-enforced {rule}" for rule in PROBES),
                            "facts sites=16 refused=0")

    def test_c7_live_pins(self):
        # A constant verdict, a skipped probe or a stale boundary cannot reproduce
        # the observations from the actual pinned schema and checker calls.
        _, files, _ = npp.assets()
        schema = json.loads(files[ASSET])
        self.assertEqual(schema["properties"]["facts"]["maxItems"], 12)
        original = research._rows
        calls = []

        def observe(result, schema):
            actual = original(result, schema)
            calls.append((result, schema, actual is None))
            return actual

        with patch.object(research, "_rows", side_effect=observe):
            self.assert_run(self.in_process(), 0, PASS, SUMMARY)
        expected = [one(), {"facts": [ROW] * 12}, *PROBES.values()]
        self.assertEqual([result for result, _, _ in calls], expected)
        self.assertEqual([refused for _, _, refused in calls], [False, False] + [True] * 16)
        slot_type_schema = json.loads(files[ASSET])
        field_specs(slot_type_schema)["slot"]["enum"].append(1)
        for result, received_schema, _ in calls:
            self.assertEqual(received_schema, slot_type_schema if result == one(slot=1) else schema)
