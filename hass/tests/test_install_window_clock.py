"""Fixture-only tests of the install window clock's CLI contract."""

from contextlib import redirect_stderr, redirect_stdout
import importlib.util
from io import StringIO
import json
from pathlib import Path
from tempfile import TemporaryDirectory
import unittest


SCRIPT = Path(__file__).resolve().parents[2] / "scripts/hass/install_window_clock.py"
SPEC = importlib.util.spec_from_file_location("install_window_clock", SCRIPT)
assert SPEC is not None and SPEC.loader is not None
CLOCK = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(CLOCK)
PRIVATE = "synthetic-private-marker"


def stamp(clock):
    return f"2000-01-01T{clock}Z"


def row(step, event, clock):
    return {"step": step, "event": event, "at": stamp(clock)}


class InstallWindowClockTests(unittest.TestCase):
    def setUp(self):
        tmp = TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        self.root = Path(tmp.name)
        self.log = self.root / f"{PRIVATE}.jsonl"

    def invoke(self, args):
        stdout, stderr = StringIO(), StringIO()
        with redirect_stdout(stdout), redirect_stderr(stderr):
            try:
                code = CLOCK.main(args)
            except SystemExit as exc:
                code = exc.code
        self.assertNotIn(PRIVATE, stdout.getvalue() + stderr.getvalue())
        return code, stdout.getvalue(), stderr.getvalue()

    def check(self, rows, *, summaries=(), failures=(), now=stamp("01:00:00")):
        raw = None
        if rows is not None:
            raw = b"".join((item if isinstance(item, bytes) else json.dumps(item).encode())
                           + b"\n" for item in rows)
            self.log.write_bytes(raw)
        code, output, errors = self.invoke(["--log", str(self.log), "--now", now])
        expected = [*summaries, *(f"FAIL {reason}" for reason in failures),
                    ("FAIL" if failures else "PASS") + " install_window_clock"]
        self.assertEqual((code, output, errors), (int(bool(failures)), "\n".join(expected) + "\n", ""))
        if raw is not None:
            self.assertEqual(self.log.read_bytes(), raw)
        self.assertEqual(set(self.root.iterdir()), {self.log} if raw is not None else set())

    def test_serial_log_at_exact_budgets(self):
        # A >= check, listing budget copied from switch, or rejecting touching intervals breaks this.
        rows = [row("switch", "start", "00:00:00"), row("switch", "end", "00:30:00"),
                row("listing-1", "start", "00:30:00"), row("listing-1", "end", "00:39:34"),
                row("listing-2", "start", "00:40:00"), row("listing-2", "end", "00:50:00"),
                row("listing-3", "start", "00:50:00"), row("listing-3", "end", "00:51:02")]
        rows[0]["note"] = PRIVATE
        self.check(rows, summaries=("switch 30:00 ok", "listing-1 09:34 ok",
                                    "listing-2 10:00 ok", "listing-3 01:02 ok"))

    def test_switch_one_second_over(self):
        # Minute-only comparisons would incorrectly pass this switch.
        self.check([row("switch", "start", "00:00:00"), row("switch", "end", "00:30:01")],
                   summaries=("switch 30:01 over",), failures=("over switch",))

    def test_switch_fraction_over_is_not_rounded_down_for_verdict(self):
        # Comparing the displayed whole seconds instead of elapsed time hides this overrun.
        self.check([row("switch", "start", "00:00:00"), row("switch", "end", "00:30:00.001")],
                   summaries=("switch 30:00 over",), failures=("over switch",))

    def test_open_listing_uses_supplied_now_and_listing_budget(self):
        # Using wall time or testing the budget only on closed intervals would miss one of these.
        rows = [row("switch", "start", "00:00:00"), row("switch", "end", "00:20:00"),
                row("listing-1", "start", "00:30:00")]
        for clock, expected, failures in (
            ("00:40:00", "listing-1 10:00 open", ()),
            ("00:40:01", "listing-1 10:01 over", ("over listing-1",)),
        ):
            with self.subTest(clock=clock):
                self.check(rows, summaries=("switch 20:00 ok", expected),
                           failures=failures, now=stamp(clock))

    def test_bad_json_reports_each_malformed_record_and_resumes(self):
        # Stopping on bad UTF-8 or accepting an invalid event silently loses findings.
        self.check([PRIVATE.encode(), b"\xff", row("switch", PRIVATE, "00:00:00"),
                    row("switch", "start", "00:59:59")],
                   summaries=("switch 00:01 open",), failures=("bad-json",) * 3)

    def test_unreadable_log_is_bad_json_without_path(self):
        # Letting the open error through would leak the path and omit the final verdict.
        self.check(None, failures=("bad-json",))

    def test_bad_event_time(self):
        # A string suffix alone does not validate a UTC ISO timestamp.
        self.check([{"step": "switch", "event": "start", "at": PRIVATE + "Z"}],
                   failures=("bad-time",))

        # Both endpoints must already have been observed at --now. Using --now
        # only to measure open steps lets a short future-ending interval pass.
        started = row("switch", "start", "00:55:00")
        future_start = row("switch", "start", "01:01:00")
        for case, rows in (
            ("future-end-only", [started, row("switch", "end", "01:00:00.001")]),
            ("future-closed", [future_start, row("switch", "end", "01:02:00")]),
            ("future-open", [future_start]),
        ):
            with self.subTest(case=case):
                self.check(rows, failures=("bad-time",))
        self.check([started, row("switch", "end", "01:00:00")],
                   summaries=("switch 05:00 ok",))
        self.check([started], summaries=("switch 05:00 open",))

    def test_bad_now_is_a_finding_not_a_usage_error(self):
        # Validating --now in argparse would incorrectly exit 2.
        self.check([], now=PRIVATE, failures=("bad-time",))

    def test_unknown_step(self):
        # Printing arbitrary step names would leak input and admit work outside the kit.
        self.check([row(PRIVATE, "start", "00:00:00")], failures=("unknown-step",))

    def test_duplicate_events_do_not_replace_the_first_event(self):
        # Last-write-wins would hide time and suppress a duplicate finding.
        self.check([row("switch", "start", "00:00:00"), row("switch", "start", "00:05:00"),
                    row("switch", "end", "00:20:00"), row("switch", "end", "00:21:00")],
                   summaries=("switch 20:00 ok",), failures=("duplicate-event", "duplicate-event"))

    def test_end_without_start(self):
        # Skipping steps without a start must not lose evidence of an orphan end.
        self.check([row("switch", "end", "00:00:00")], failures=("end-without-start",))

    def test_end_before_start(self):
        # Pairing events in file order alone would accept a backwards clock interval.
        self.check([row("switch", "start", "00:05:00"), row("switch", "end", "00:00:00")],
                   summaries=("switch 00:00 ok",), failures=("end-before-start",))

    def test_out_of_order(self):
        # Sorting each interval independently would miss the skipped listing.
        self.check([row("switch", "start", "00:00:00"), row("switch", "end", "00:20:00"),
                    row("listing-2", "start", "00:59:00")],
                   summaries=("switch 20:00 ok", "listing-2 01:00 open"),
                   failures=("out-of-order listing-2",))

    def test_overlap_with_closed_or_open_predecessor(self):
        # Checking start order alone would let listing 1 start during the switch.
        base = [row("switch", "start", "00:15:00"), row("listing-1", "start", "00:29:00"),
                row("listing-1", "end", "00:30:00")]
        for closed in (False, True):
            with self.subTest(closed=closed):
                rows = base + [row("switch", "end", "00:30:00")] if closed else base
                switch = "switch 15:00 ok" if closed else "switch 15:00 open"
                self.check(rows, now=stamp("00:30:00"), summaries=(switch, "listing-1 01:00 ok"),
                           failures=("overlap listing-1",))

    def test_argparse_usage_error(self):
        # Real usage errors must be separate from verdicts and must not echo argv data.
        code, output, errors = self.invoke(["--log", str(self.log), "--now", stamp("00:00:00"), PRIVATE])
        self.assertEqual((code, output), (2, ""))
        self.assertTrue(errors.startswith("usage: "))


if __name__ == "__main__":
    unittest.main()
