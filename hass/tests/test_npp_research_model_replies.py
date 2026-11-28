"""Offline CLI contracts for the S4 model-reply drift guard."""

import contextlib
import importlib.util
import io
import json
from pathlib import Path
import re
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import patch

from hass import npp
from hass.npp import research_hermes


ROOT = Path(__file__).resolve().parents[2]
SCRIPT = ROOT / "scripts/hass/npp_research_model_replies.py"
PASS = "PASS npp_research_model_replies"
FAIL = "FAIL npp_research_model_replies"


def _snapshot():
    result = {}
    for tree in (ROOT / "hass", ROOT / "storefront-mockup"):
        for path in (tree, *tree.rglob("*")):
            stat = path.lstat()
            result[path.relative_to(ROOT)] = (stat.st_size, stat.st_mtime_ns)
    return result


class NppResearchModelRepliesTests(unittest.TestCase):
    def setUp(self):
        spec = importlib.util.spec_from_file_location("npp_research_model_replies", SCRIPT)
        assert spec is not None and spec.loader is not None
        self.tool = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(self.tool)

    def cli(self, *args):
        with tempfile.TemporaryDirectory() as directory:
            return subprocess.run(
                [sys.executable, "-B", str(SCRIPT), *args], cwd=directory,
                capture_output=True, text=True, timeout=10,
            )

    def run_main(self, code, trailer):
        stdout, stderr = io.StringIO(), io.StringIO()
        with contextlib.redirect_stdout(stdout), contextlib.redirect_stderr(stderr):
            result = self.tool.main([])
        self.assertEqual(result, code)
        self.assertEqual(stderr.getvalue(), "")
        lines = stdout.getvalue().splitlines()
        self.assertEqual(lines[-1:], [trailer])
        return lines

    def assert_findings(self, lines, *expected):
        self.assertEqual([line for line in lines[:-1] if line.startswith("FAIL ")], list(expected))

    def test_c1_full_pass(self):
        # A clean CLI run must not accidentally exit nonzero or omit its trailer.
        result = self.cli()
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(result.stdout.splitlines()[-1:], [PASS])

    def test_c2_findings_trailer(self):
        # A finding must affect the process status, not just the diagnostic text.
        with patch.object(research_hermes, "_unique", dict):
            self.run_main(1, FAIL)

    def test_c2_1_unexpected(self):
        # If decoding strips extra fields, or throws instead of rejecting, fail closed.
        unique = research_hermes._unique

        def changed_decoder(pairs):
            if len(pairs) == 2 and pairs[1][0] == "x":
                return dict(pairs[:1])
            if len(pairs) == 2 and pairs[1][0] == "verdict":
                raise RuntimeError("synthetic decoder error")
            return unique(pairs)

        with patch.object(research_hermes, "_unique", changed_decoder):
            lines = self.run_main(1, FAIL)
        self.assertIn('case 1 verify value="supports" calls=1', lines)
        self.assert_findings(lines, "FAIL unexpected-value 1", "FAIL unexpected-other 2", "FAIL check-error")

    def test_c2_2_ok_lost(self):
        # A deny-everything regression must not pass, in either model port.
        unique = research_hermes._unique

        def changed_decoder(pairs):
            value = unique(pairs)
            return {} if value in ({"verdict": "supports"}, {"facts": []}) else value

        with patch.object(research_hermes, "_unique", changed_decoder):
            self.assert_findings(self.run_main(1, FAIL), "FAIL ok-lost 0", "FAIL ok-lost 10")

    def test_c2_3_call_made(self):
        # Simulate a budget regression that costs a call but still returns no verdict.
        verify = research_hermes.Models.verify

        def overspend(model, name, slot, value, quote, seconds):
            if seconds == 3:
                verify(model, name, slot, value, quote, 60)
                return None
            return verify(model, name, slot, value, quote, seconds)

        with patch.object(research_hermes.Models, "verify", overspend):
            lines = self.run_main(1, FAIL)
        self.assertIn("case 9 verify none calls=1", lines)
        self.assert_findings(lines, "FAIL call-made 9")

    def test_c2_4_call_record_keys(self):
        # Logging model text on the parse-error path must not slip through.
        call = research_hermes.Models._call

        def record_text(model, *args):
            try:
                return call(model, *args)
            except ValueError:
                model.calls[-1]["text"] = "synthetic reply"
                raise

        with patch.object(research_hermes.Models, "_call", record_text):
            self.assert_findings(self.run_main(1, FAIL), "FAIL call-record-keys 2", "FAIL call-record-keys 4")

    def test_c2_5_check_error(self):
        # A setup failure must be reported without leaking details or skipping later cases.
        load = npp.assets
        first = True

        def fail_first_load():
            nonlocal first
            if first:
                first = False
                raise RuntimeError("synthetic loader error")
            return load()

        with patch.object(npp, "assets", fail_first_load):
            lines = self.run_main(1, FAIL)
        self.assert_findings(lines, "FAIL check-error")
        self.assertIn('case 11 extract value=["x"] calls=1', lines)

    def test_c3_usage_exit_2(self):
        # No arguments, not even the implicit help flag or end-of-options marker.
        for arg in ("unexpected", "--unknown", "--help", "--", "-"):
            with self.subTest(arg=arg):
                result = self.cli(arg)
                self.assertEqual(result.returncode, 2)
                self.assertEqual(result.stdout, "")
                self.assertIn("error: unrecognized arguments:", result.stderr)

    def test_c4_read_only(self):
        # A new cache or a rewrite of an existing asset would change this snapshot.
        before = _snapshot()
        result = self.cli()
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(result.stdout.splitlines()[-1:], [PASS])
        self.assertEqual(_snapshot(), before)

    def test_c5_output_shape(self):
        # Progress banners, raw replies, or traceback noise would corrupt the report.
        for decoder, code, trailer in ((research_hermes._unique, 0, PASS), (dict, 1, FAIL)):
            with self.subTest(code=code), patch.object(research_hermes, "_unique", decoder):
                lines = self.run_main(code, trailer)
                info = [line for line in lines[:-1] if not line.startswith("FAIL ")]
                self.assertEqual(len(info), 12)
                for line in info:
                    match = re.fullmatch(r"case \d+ (?:verify|extract) (none|valueerror|value=.+) calls=\d+", line)
                    self.assertIsNotNone(match, line)
                    if match and match[1].startswith("value="):
                        json.loads(match[1][len("value="):])
                self.assert_findings(lines, *(["FAIL unexpected-value 2"] if code else []))

    def test_c6_fixture(self):
        # Last-key-wins would turn the duplicate-key fixture into a conflicting verdict.
        with patch.object(research_hermes, "_unique", dict):
            lines = self.run_main(1, FAIL)
        self.assertIn('case 2 verify value="refutes" calls=1', lines)
        self.assert_findings(lines, "FAIL unexpected-value 2")

    def test_c7_live_pins(self):
        # Distinguish rejection, parse error, exhausted budget and accepted extraction.
        self.assertEqual(self.run_main(0, PASS), [
            'case 0 verify value="supports" calls=1',
            'case 1 verify none calls=1',
            'case 2 verify valueerror calls=1',
            'case 3 verify none calls=1',
            'case 4 verify valueerror calls=1',
            'case 5 verify none calls=1',
            'case 6 verify none calls=1',
            'case 7 verify none calls=1',
            'case 8 verify none calls=1',
            'case 9 verify none calls=0',
            'case 10 extract value={"facts": []} calls=1',
            'case 11 extract value=["x"] calls=1',
            PASS,
        ])
