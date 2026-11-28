"""Offline contract for the intake date drift guard."""

from contextlib import redirect_stderr, redirect_stdout
import datetime
import importlib.util
import io
from pathlib import Path
import subprocess
import sys
import unittest
from unittest.mock import call, patch


ROOT = Path(__file__).resolve().parents[2]
SCRIPT = ROOT / "scripts/hass/npp_intake_parse_day.py"
SPEC = importlib.util.spec_from_file_location("npp_intake_parse_day", SCRIPT)
assert SPEC is not None and SPEC.loader is not None
CHECK = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(CHECK)

PASS = "PASS npp_intake_parse_day"
FAIL = "FAIL npp_intake_parse_day"
LIVE_LINES = [
    "case 0 day='2026-11-21'",
    "case 1 day='2026-11-22'",
    "case 2 day='2026-11-20'",
    "case 3 day='2026-12-12'",
    "case 4 day='2026-12-20'",
    "case 5 day='2025-12-20'",
    "case 6 day='2027-01-03'",
    "case 7 day='2026-01-03'",
    "case 8 day='2027-11-02'",
    "case 9 day='2026-11-02'",
    "case 10 day='2027-12-20'",
    "case 11 day='2027-03-20'",
    "case 12 day=None",
    "case 13 day=None",
    "case 14 day=None",
]
PAST_IGNORED = {5: "2026-12-20", 7: "2027-01-03", 9: "2027-11-02"}
MONTH_FINDINGS = [f"FAIL day-changed {i}" for i in (4, 5, 6, 7, 11)]


def cli(*args):
    return subprocess.run(
        [sys.executable, "-B", str(SCRIPT), *args],
        cwd=ROOT, capture_output=True, text=True, timeout=10,
    )


def snapshot():
    entries = {}
    for name in ("hass", "storefront-mockup"):
        tree = ROOT / name
        for path in (tree, *tree.rglob("*")):
            info = path.lstat()
            entries[path.relative_to(ROOT)] = (info.st_size, info.st_mtime_ns)
    return entries


class IntakeParseDayTests(unittest.TestCase):
    def run_check(self, expected_code, trailer):
        stdout, stderr = io.StringIO(), io.StringIO()
        with redirect_stdout(stdout), redirect_stderr(stderr):
            code = CHECK.main([])
        lines = stdout.getvalue().splitlines()
        self.assertEqual(code, expected_code)
        self.assertEqual(lines[-1:], [trailer])
        self.assertEqual(stderr.getvalue(), "")
        return lines[:-1]

    def ignore_past(self):
        original = CHECK.item_intake.parse_day

        def parse_day(text, today, *, past):
            return original(text, today, past=False)

        return patch.object(CHECK.item_intake, "parse_day", parse_day)

    def test_c1_full_pass(self):
        # The real CLI must propagate success and finish with the PASS trailer.
        result = cli()
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(result.stdout.splitlines()[-1:], [PASS])

    def test_c2_findings_trailer(self):
        # Buffering or reordering findings would detach them from their case.
        with self.ignore_past():
            lines = self.run_check(1, FAIL)
        expected = []
        for i, line in enumerate(LIVE_LINES):
            if i in PAST_IGNORED:
                expected.extend((f"case {i} day={PAST_IGNORED[i]!r}",
                                 f"FAIL wrong-side-day {i}", f"FAIL day-changed {i}"))
            else:
                expected.append(line)
        self.assertEqual(lines, expected)

    def test_c2_1_wrong_side_day(self):
        # Treating a bought day like a best-by day must trip the direction check.
        with self.ignore_past():
            lines = self.run_check(1, FAIL)
        self.assertEqual([line for line in lines if line.startswith("FAIL ")], [
            "FAIL wrong-side-day 5", "FAIL day-changed 5",
            "FAIL wrong-side-day 7", "FAIL day-changed 7",
            "FAIL wrong-side-day 9", "FAIL day-changed 9",
        ])

        # The reverse failure matters too: a best-by day must not roll backward.
        original = CHECK.item_intake.parse_day

        def parse_day(text, today, *, past):
            return original(text, today, past=past or text == "11/02")

        with patch.object(CHECK.item_intake, "parse_day", parse_day):
            lines = self.run_check(1, FAIL)
        self.assertEqual([line for line in lines if line.startswith("FAIL ")], [
            "FAIL wrong-side-day 8", "FAIL day-changed 8",
        ])

    def test_c2_2_day_changed(self):
        # Losing a date entirely is a finding even without a wrong-side date.
        with patch.object(CHECK.item_intake, "MONTHS", {}):
            lines = self.run_check(1, FAIL)
        self.assertEqual([line for line in lines if line.startswith("FAIL ")], MONTH_FINDINGS)
        self.assertEqual([line for line in lines if line.startswith("case ")], [
            f"case {i} day=None" if i in (4, 5, 6, 7, 11) else line
            for i, line in enumerate(LIVE_LINES)
        ])

    def test_c2_3_check_error(self):
        # Mid-run errors must neither leak details nor let later cases run.
        original = CHECK.item_intake.parse_day
        today = datetime.date(2026, 11, 21)

        def parse_day(text, today, *, past):
            if text == "tomorrow":
                raise RuntimeError("synthetic error detail")
            return original(text, today, past=past)

        with patch.object(CHECK.item_intake, "parse_day", side_effect=parse_day) as parse:
            lines = self.run_check(1, FAIL)
        self.assertEqual(lines, [LIVE_LINES[0], "FAIL check-error"])
        self.assertEqual(parse.call_args_list, [
            call("today", today, past=False), call("tomorrow", today, past=False),
        ])

    def test_c3_usage_exit_2(self):
        # A no-options tool must reject extras, including argparse's usual help flags.
        for arg in ("extra", "--unknown", "-h", "--help", "--"):
            with self.subTest(arg=arg):
                result = cli(arg)
                self.assertEqual(result.returncode, 2)
                self.assertEqual(result.stdout, "")  # There is no stdout trailer.
                self.assertTrue(result.stderr.startswith("usage: "))
                self.assertEqual(result.stderr.splitlines()[-1],
                                 f"{SCRIPT.name}: error: unrecognized arguments: {arg}")

    def test_c4_read_only(self):
        # The CLI must not save reports or mutate either checked tree.
        before = snapshot()
        result = cli()
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(result.stdout.splitlines()[-1:], [PASS])
        self.assertEqual(snapshot(), before)

    def test_c5_output_shape(self):
        # Extra stdout chatter or stderr warnings would contaminate the report.
        result = cli()
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(result.stderr, "")
        lines = result.stdout.splitlines()
        self.assertEqual(lines[-1:], [PASS])
        self.assertEqual(len(lines), 16)
        for i, line in enumerate(lines[:-1]):
            self.assertRegex(line, rf"\Acase {i} day=(?:None|'[0-9]{{4}}-[0-9]{{2}}-[0-9]{{2}}')\Z")

    def test_c6_fixture(self):
        # Removing named months must not alter relative or numeric-date cases.
        with patch.object(CHECK.item_intake, "MONTHS", {}):
            lines = self.run_check(1, FAIL)
        expected = []
        for i, line in enumerate(LIVE_LINES):
            finding = f"FAIL day-changed {i}"
            expected.extend((f"case {i} day=None", finding) if finding in MONTH_FINDINGS else (line,))
        self.assertEqual(lines, expected)

    def test_c7_live_pins(self):
        # Static answers would match the golden output but never exercise the parser.
        with patch.object(CHECK.item_intake, "parse_day", wraps=CHECK.item_intake.parse_day) as parse:
            lines = self.run_check(0, PASS)
        self.assertEqual(lines, LIVE_LINES)
        self.assertEqual(parse.call_args_list, [
            call(text, datetime.date(2026, 11, 21), past=past) for text, past in CHECK.CASES
        ])
