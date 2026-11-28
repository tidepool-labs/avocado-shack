"""Offline CLI and fixture coverage for the ready-prompt parity report."""

from contextlib import redirect_stderr, redirect_stdout
import importlib.util
from io import StringIO
from itertools import combinations
from pathlib import Path
import re
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import patch

from hass.npp import reply

ROOT = Path(__file__).resolve().parents[2]
SCRIPT = ROOT / "scripts/hass/npp_ready_line_parity.py"
JOB = ROOT / "hass/npp/job.py"
PASS = "PASS npp_ready_line_parity"
FAIL = "FAIL npp_ready_line_parity"
SUMMARY = "ready subsets=24 mismatched=0"
SHAPE = "ready inline_shape=yes"

SPEC = importlib.util.spec_from_file_location("npp_ready_line_parity", SCRIPT)
assert SPEC is not None and SPEC.loader is not None
audit = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(audit)


class ReadyLineParityTests(unittest.TestCase):
    def setUp(self):
        fixture = tempfile.TemporaryDirectory()
        self.addCleanup(fixture.cleanup)
        self.fixture = Path(fixture.name)

    def cli(self, *args):
        run = subprocess.run([sys.executable, "-B", str(SCRIPT), *args], cwd=self.fixture,
                             capture_output=True, text=True, timeout=15)
        return run.returncode, run.stdout.splitlines(), run.stderr

    def in_process(self):
        out, err = StringIO(), StringIO()
        with redirect_stdout(out), redirect_stderr(err):
            code = audit.main([])
        return code, out.getvalue().splitlines(), err.getvalue()

    def assert_report(self, run, exit_code, trailer):
        code, lines, err = run
        self.assertEqual(err, "")
        self.assertEqual(code, exit_code, lines)
        self.assertTrue(lines)
        self.assertEqual(lines[-1], trailer)
        return lines

    def test_c1_full_pass(self):
        # A cwd-dependent import or nonzero success status breaks the CLI.
        self.assert_report(self.cli(), 0, PASS)

    def test_c2_findings_trailer(self):
        # Independent checks must both run and leave one terminal FAIL marker.
        source = self.fixture / "job.py"
        source.write_text("class Jobs: pass\n", encoding="utf-8")
        build = reply.ready_line

        def change_empty(replies, code, n, parts):
            return build(replies, code, n, parts) + ("" if parts else " ")

        with patch.object(audit, "JOB_SOURCE", source), patch.object(reply, "ready_line", change_empty):
            lines = self.assert_report(self.in_process(), 1, FAIL)
        self.assertEqual(lines, ["ready subsets=24 mismatched=1", "FAIL ready-mismatch 0",
                                 "ready inline_shape=no", "FAIL inline-shape-changed", FAIL])

    def test_c2_1_ready_mismatch(self):
        # Compare bytes, not stripped text or note counts; report only the index.
        build = reply.ready_line

        def change_house_with_all_parts(replies, code, n, parts):
            original = build(replies, code, n, parts)
            return original + " synthetic-marker" if "picture_house" in parts and len(parts) == 4 else original

        with patch.object(reply, "ready_line", change_house_with_all_parts):
            lines = self.assert_report(self.in_process(), 1, FAIL)
        self.assertEqual(lines, ["ready subsets=24 mismatched=1", "FAIL ready-mismatch 23", SHAPE, FAIL])

    def test_c2_2_inline_shape_changed(self):
        # A key scan would accept altered comparisons, suffix bytes or a duplicate builder.
        raw = JOB.read_text(encoding="utf-8")
        anchor = '            if card_path is not None:\n                text = '
        start = raw.index(anchor)
        end = raw.index('                self.db.execute(', start)
        duplicate = raw[:start] + raw[start:end] + raw[start:]
        source = self.fixture / "job.py"
        for label, changed in (
            ("duplicate", duplicate),
            ("comparison", raw.replace('<= self.replies["caps"]["bracket_max_chars"]',
                                       '< self.replies["caps"]["bracket_max_chars"]', 1)),
            ("suffix", raw.replace('f" ({result.note})"', 'f" [{result.note}]"', 1)),
        ):
            with self.subTest(label=label):
                self.assertNotEqual(raw, changed)
                source.write_text(changed, encoding="utf-8")
                with patch.object(audit, "JOB_SOURCE", source):
                    lines = self.assert_report(self.in_process(), 1, FAIL)
                self.assertEqual(lines, [SUMMARY, "ready inline_shape=no", "FAIL inline-shape-changed", FAIL])

    def test_c2_3_parse_error(self):
        # Missing, undecodable and invalid source are not ordinary shape drift.
        malformed = self.fixture / "malformed.py"
        malformed.write_text("def synthetic(\n", encoding="utf-8")
        non_utf8 = self.fixture / "undecodable.py"
        non_utf8.write_bytes(b"\xff")
        for source in (self.fixture / "missing.py", malformed, non_utf8):
            with self.subTest(source=source.name), patch.object(audit, "JOB_SOURCE", source):
                lines = self.assert_report(self.in_process(), 1, FAIL)
                self.assertEqual(lines, [SUMMARY, "ready inline_shape=no", "FAIL parse-error", FAIL])

    def test_c2_4_check_error(self):
        # A composer exception cannot leak exception text or produce a PASS.
        with patch.object(reply, "compose", side_effect=ValueError("synthetic-marker")):
            lines = self.assert_report(self.in_process(), 1, FAIL)
        self.assertEqual(lines, [SUMMARY, "FAIL check-error", SHAPE, FAIL])

    def test_c3_usage_exit_2(self):
        # Positional arguments, unknown flags and default help must not run the check.
        for arg in ("extra", "--unknown", "--help", "-h", "--"):
            with self.subTest(arg=arg):
                code, lines, err = self.cli(arg)
                self.assertEqual(code, 2)
                self.assertEqual(lines, [])  # Usage errors have no stdout trailer.
                self.assertTrue(err.startswith("usage:"), err)
                self.assertIn("error: unrecognized arguments:", err)

    def test_c4_read_only(self):
        # Detect rewritten outputs, cache creation and transient files at either tree.
        def snapshot():
            state = {}
            for tree in (ROOT / "hass", ROOT / "storefront-mockup"):
                for path in (tree, *tree.rglob("*")):
                    st = path.lstat()
                    state[path.relative_to(ROOT)] = (st.st_size, st.st_mtime_ns)
            return state

        before = snapshot()
        self.assert_report(self.cli(), 0, PASS)
        self.assertEqual(snapshot(), before)

    def test_c5_output_shape(self):
        # Reject extra diagnostics, raw prompt text, or stderr on ordinary runs.
        accepted = re.compile(r"ready subsets=[0-9]+ mismatched=[0-9]+|ready inline_shape=(yes|no)"
                              r"|FAIL (ready-mismatch [0-9]+|inline-shape-changed|parse-error|check-error)"
                              r"|(PASS|FAIL) npp_ready_line_parity")
        self.assertTrue(all(accepted.fullmatch(line) for line in self.assert_report(self.cli(), 0, PASS)))
        with patch.object(audit.npp, "assets", side_effect=ValueError("synthetic-marker")):
            lines = self.assert_report(self.in_process(), 1, FAIL)
        self.assertTrue(all(accepted.fullmatch(line) for line in lines), lines)

    def test_c6_fixture(self):
        # A low cap alone is not a finding; an overlong note must still be caught.
        replies = audit.npp.assets()[2]
        with patch.dict(replies["caps"], bracket_max_chars=10), patch.object(audit.npp, "assets") as load:
            load.return_value = (None, None, replies)
            self.assertEqual(self.assert_report(self.in_process(), 0, PASS), [SUMMARY, SHAPE, PASS])
            compose = reply.compose
            with patch.object(reply, "compose",
                              side_effect=lambda r, p: compose(r, p) if p else "x" * 9):
                lines = self.assert_report(self.in_process(), 1, FAIL)
            self.assertEqual(lines, ["ready subsets=24 mismatched=1", "FAIL ready-mismatch 0", SHAPE, FAIL])

        build = reply.ready_line
        with patch.object(reply, "ready_line", side_effect=lambda *args: build(*args) + " ") as ready:
            lines = self.assert_report(self.in_process(), 1, FAIL)
        self.assertEqual(lines, ["ready subsets=24 mismatched=24",
                                 *(f"FAIL ready-mismatch {i}" for i in range(24)), SHAPE, FAIL])
        # A repeated subset can keep the count at 24 while skipping a real card variant.
        optional = ("basic_wording", "story_not_found", "maker_left_off")
        expected = {frozenset(picture + others)
                    for picture in ((), ("picture_own_photo",), ("picture_house",))
                    for size in range(4) for others in combinations(optional, size)}
        self.assertEqual({frozenset(call.args[3]) for call in ready.call_args_list}, expected)

    def test_c7_live_pins(self):
        # Use the checked-in assets and source; a skipped subset or guard changes the receipt.
        self.assertEqual(self.assert_report(self.cli(), 0, PASS), [SUMMARY, SHAPE, PASS])


if __name__ == "__main__":
    unittest.main()
