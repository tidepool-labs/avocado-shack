"""Offline contract tests for the S4 quote-check audit CLI."""

from contextlib import redirect_stderr, redirect_stdout
import importlib.util
import io
import json
from pathlib import Path
import re
import subprocess
import sys
from tempfile import TemporaryDirectory
import unittest
from unittest.mock import patch

import hass.npp


ROOT = Path(__file__).resolve().parents[2]
SCRIPT = ROOT / "scripts/hass/npp_quote_check_reasons.py"
PASS = "PASS npp_quote_check_reasons"
FAIL = "FAIL npp_quote_check_reasons"
NAME_FINDINGS = ["FAIL value-only-in-name 0", "FAIL value-only-in-name 1", "FAIL value-only-in-name 2"]
PINNED_REASONS = (
    "ok",
    "unverified-url",
    "quote-not-in-visible-body-text",
    "negation-past-or-hedge-marker",
    "quote-does-not-name-maker",
    "fragment-without-context",
    "value-not-in-quote",
    "invalid-name",
    "ok",
    "invalid-town",
    "invalid-year",
    "ok",
    "ok",
    "invalid-nature",
    "invalid-product-type",
    "ok",
)


def snapshot():
    state = {}
    for tree in (ROOT / "hass", ROOT / "storefront-mockup"):
        for path in (tree, *tree.rglob("*")):
            stat = path.lstat()
            state[path.relative_to(ROOT)] = (stat.st_size, stat.st_mtime_ns)
    return state


class QuoteCheckReasonsTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        spec = importlib.util.spec_from_file_location("npp_quote_check_reasons", SCRIPT)
        assert spec is not None and spec.loader is not None
        cls.audit = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(cls.audit)

    def setUp(self):
        self.cwd = self.enterContext(TemporaryDirectory())
        self.research = self.audit.research
        self.real_check = self.research._check

    def invoke(self):
        stdout, stderr = io.StringIO(), io.StringIO()
        with redirect_stdout(stdout), redirect_stderr(stderr):
            status = self.audit.main([])
        self.assertEqual(stderr.getvalue(), "")
        return status, stdout.getvalue().splitlines()

    def subprocess(self, *args):
        return subprocess.run([sys.executable, "-B", str(SCRIPT), *args], cwd=self.cwd,
                              capture_output=True, text=True, timeout=10)

    def assert_outcome(self, result, status, trailer):
        code, lines = result
        self.assertEqual(code, status)
        self.assertTrue(lines)
        self.assertEqual(lines[-1], trailer)
        return lines

    def assert_findings(self, result, expected):
        lines = self.assert_outcome(result, 1, FAIL)
        self.assertEqual([line for line in lines[:-1] if line.startswith("FAIL ")], expected)
        return lines

    def reject_name_only(self, row, pages, name, town, schema, markers):
        reason = self.real_check(row, pages, name, town, schema, markers)
        if reason is None and row["slot"] == "nature":
            pattern = rf"(?<![\w-]){re.escape(name)}(?![\w-])"
            remaining = re.sub(pattern, " ", row["quote"], flags=re.IGNORECASE)
            if not self.research._has(remaining, row["value"]):
                return "value-not-in-quote"
        return reason

    def test_c1_full_pass(self):
        # A fixed checker must not retain the baseline's failing verdict.
        with patch.object(self.research, "_check", self.reject_name_only):
            lines = self.assert_outcome(self.invoke(), 0, PASS)
        self.assertEqual([line for line in lines if line.startswith("FAIL ")], [])

    def test_c2_findings_trailer(self):
        # Several findings must not stop later checks or duplicate the trailer.
        def refuse_control(row, *args):
            if row["quote"] == "Etto Farm is a farm.":
                return "value-not-in-quote"
            return self.real_check(row, *args)

        with (patch.object(self.research, "_check", refuse_control),
              patch.object(self.research, "_markers", return_value=re.compile(r"(?!)"))):
            lines = self.assert_findings(self.invoke(), ["FAIL reason-moved 3", *NAME_FINDINGS,
                                                         "FAIL control-refused"])
        self.assertEqual(lines.count(FAIL), 1)

    def test_c2_1_reason_moved(self):
        # Refusing the fragment for its missing value instead is still reason drift.
        def value_first(row, *args):
            reason = self.real_check(row, *args)
            if row["quote"] == "Etto Farm makes" and reason == "fragment-without-context":
                return "value-not-in-quote"
            return reason

        with patch.object(self.research, "_check", value_first):
            lines = self.assert_findings(self.invoke(), ["FAIL reason-moved 5", *NAME_FINDINGS])
        self.assertIn("row 5 reason=value-not-in-quote", lines)

    def test_c2_2_value_only_in_name(self):
        # A refused name-only row is not a finding. Leave two genuine accepts.
        def refuse_market(row, *args):
            if row["quote"] == "Etto Farm sells honey at the market.":
                return self.reject_name_only(row, *args)
            return self.real_check(row, *args)

        with patch.object(self.research, "_check", refuse_market):
            lines = self.assert_findings(self.invoke(), ["FAIL value-only-in-name 0", "FAIL value-only-in-name 2"])
        self.assertIn("name-row 1 reason=value-not-in-quote", lines)

    def test_c2_3_control_refused(self):
        # Rejecting every farm claim would hide the gap but break the standalone control.
        def refuse_farm(row, *args):
            if row["slot"] == "nature" and row["value"] == "farm":
                return "value-not-in-quote"
            return self.reject_name_only(row, *args)

        with patch.object(self.research, "_check", refuse_farm):
            self.assert_findings(self.invoke(), ["FAIL control-refused"])

    def test_c2_4_check_error(self):
        # Neither a failed marker setup nor a throwing checker may silently pass or leak its error.
        for target in ("_markers", "_check"):
            with self.subTest(target=target), patch.object(self.research, target, side_effect=ValueError("fixture error")):
                self.assertEqual(self.assert_findings(self.invoke(), ["FAIL check-error"]),
                                 ["FAIL check-error", FAIL])

    def test_c3_usage_exit_2(self):
        # A positional, unrecognized option, or default argparse help must not run the audit.
        for arg in ("extra", "--unknown", "--help", "-h", "--"):
            with self.subTest(arg=arg):
                result = self.subprocess(arg)
                self.assertEqual((result.returncode, result.stdout), (2, ""))
                self.assertIn("unrecognized arguments: " + arg, result.stderr.splitlines()[-1])

    def test_c4_read_only(self):
        # A cache or receipt written into either source tree must be detectable.
        before = snapshot()
        result = self.subprocess()
        self.assert_outcome((result.returncode, result.stdout.splitlines()), 1, FAIL)
        self.assertEqual(snapshot(), before)

    def test_c5_output_shape(self):
        # Tracebacks, debug chatter or prose around a finding break the CLI format.
        result = self.subprocess()
        lines = self.assert_outcome((result.returncode, result.stdout.splitlines()), 1, FAIL)
        self.assertEqual(result.stderr, "")
        shape = re.compile(
            r"(?:row [0-9]+|name-row [0-9]+) reason=[a-z]+(?:-[a-z]+)*"
            r"|FAIL (?:(?:reason-moved|value-only-in-name) [0-9]+|control-refused|check-error)"
        )
        for line in lines[:-1]:
            self.assertIsNotNone(shape.fullmatch(line), line)

    def test_c6_fixture(self):
        # Constant reason strings or skip-the-check implementations would miss these mutations.
        with patch.object(self.research, "_markers", return_value=re.compile(r"(?!)")):
            lines = self.assert_findings(self.invoke(), ["FAIL reason-moved 3", *NAME_FINDINGS])
        self.assertIn("row 3 reason=ok", lines)
        with patch.object(self.research, "_check", self.reject_name_only):
            lines = self.assert_outcome(self.invoke(), 0, PASS)
        self.assertEqual([line for line in lines if line.startswith("name-row ")], [
            "name-row 0 reason=value-not-in-quote",
            "name-row 1 reason=value-not-in-quote",
            "name-row 2 reason=value-not-in-quote",
        ])

    def test_c7_live_pins(self):
        # Drift, missing rows, or a changed control upset the exact offline baseline receipt.
        lines = self.assert_findings(self.invoke(), NAME_FINDINGS)
        expected = [f"row {i} reason={reason}" for i, reason in enumerate(PINNED_REASONS)]
        for i, finding in enumerate(NAME_FINDINGS):
            expected.extend([f"name-row {i} reason=ok", finding])
        self.assertEqual(lines, [*expected, FAIL])

        # The specified 16 CLI rows omit the last refusal. Pin it directly without adding CLI output.
        _, files, _ = hass.npp.assets()
        schema = json.loads(files["hass-maker-research/facts.schema.json"])
        url = "https://etto.example/"
        quote = "Etto Farm is in Arroyo Grande!"
        page = self.research.Page(url, "2026-11-21", titles=["Etto Farm"], blocks=[quote])
        row = dict(url=url, slot="town", value="Arroyo Grande!", quote=quote)
        reason = self.research._check(row, {url: page}, "Etto Farm", "", schema, self.research._markers(schema))
        self.assertEqual(reason, "invalid-identity-value")
