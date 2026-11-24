"""Fixture-only tests at the saved-capture checker's CLI boundary."""

from contextlib import redirect_stderr, redirect_stdout
import importlib.util
import io
from pathlib import Path
from tempfile import TemporaryDirectory
import unittest


SCRIPT = Path(__file__).resolve().parents[2] / "scripts/hass/install_service_restart.py"
SPEC = importlib.util.spec_from_file_location("install_service_restart", SCRIPT)
assert SPEC is not None and SPEC.loader is not None
CHECKER = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(CHECKER)

SERVICE = "fixture-worker.service"
TIMER = "fixture-worker.timer"
MARKER = "synthetic-private-marker"


def service(*, restarts=0, pid=27, start=101, active="active", sub="running"):
    return (f"Id={SERVICE}\nActiveState={active}\nSubState={sub}\nNRestarts={restarts}\n"
            f"MainPID={pid}\nExecMainStartTimestampMonotonic={start}\n")


def timer(sub="waiting"):
    return f"ActiveState=active\nId={TIMER}\nSubState={sub}\n"


class InstallServiceRestartTests(unittest.TestCase):
    def setUp(self):
        work = TemporaryDirectory()
        self.addCleanup(work.cleanup)
        self.first = Path(work.name) / f"{MARKER}-first"
        self.second = Path(work.name) / f"{MARKER}-second"

    def invoke(self, first, second, *, options=None):
        for path, capture in ((self.first, first), (self.second, second)):
            path.unlink(missing_ok=True)
            if capture is not None:
                path.write_bytes(capture.encode() if isinstance(capture, str) else capture)
        if options is None:
            options = ["--installed-mono", "100", "--unit", SERVICE]
        stdout, stderr = io.StringIO(), io.StringIO()
        with redirect_stdout(stdout), redirect_stderr(stderr):
            try:
                code = CHECKER.main(["--first", str(self.first), "--second", str(self.second), *options])
            except SystemExit as exc:
                code = exc.code
        self.assertNotIn(MARKER, stdout.getvalue() + stderr.getvalue())
        self.assertNotIn("Traceback", stderr.getvalue())
        return code, stdout.getvalue().splitlines(), stderr.getvalue()

    def assert_findings(self, result, *findings):
        self.assertEqual(result, (1, [*findings, "FAIL install_service_restart"], ""))

    def test_pass_matches_ids_not_file_order_and_ignores_timer_worker_fields(self):
        # A positional join, absolute restart count, or timer PID check would fail.
        worker = service(restarts=2)
        first = worker + "\n" + timer() + "MainPID=\nNRestarts=\n"
        second = timer() + "\n" + worker
        self.assertEqual(self.invoke(first, second, options=[
            "--installed-mono", "100", "--unit", SERVICE, "--unit", TIMER,
        ]), (0, [f"{SERVICE} ok", f"{TIMER} ok", "PASS install_service_restart"], ""))

    def test_service_restart_pid_and_freshness_checks_are_independent(self):
        # Comparing only liveness, or checking freshness on only one side, masks these.
        cases = (
            (service(), service(restarts=1), "restarted"),
            (service(), service(pid=28), "pid-changed"),
            (service(start=99), service(), "stale-start"),
            (service(), service(start=100), "stale-start"),
        )
        for first, second, reason in cases:
            with self.subTest(reason=reason, first=first, second=second):
                self.assert_findings(self.invoke(first, second), f"FAIL {reason} {SERVICE}")

    def test_changed_main_start_time_is_refused(self):
        # Protects: no intervening restart. Believable bug: comparing each capture only to the
        # cutoff, so 101 then 102 (same PID and NRestarts, both after 100) passes.
        self.assert_findings(self.invoke(service(start=101), service(start=102)),
                             f"FAIL start-changed {SERVICE}")
        self.assertEqual(self.invoke(service(start=101), service(start=101)),
                         (0, [f"{SERVICE} ok", "PASS install_service_restart"], ""))

    def test_active_service_requires_positive_pid(self):
        # Same-PID and freshness checks alone let two zero PIDs pass.
        for first_pid, second_pid in ((0, 0), (0, 27), (27, 0)):
            with self.subTest(first_pid=first_pid, second_pid=second_pid):
                findings = [f"FAIL missing-process {SERVICE}"]
                if first_pid != second_pid:
                    findings.append(f"FAIL pid-changed {SERVICE}")
                self.assert_findings(self.invoke(service(pid=first_pid), service(pid=second_pid)),
                                     *findings)

    def test_inactive_or_wrong_substate_in_either_capture_fails(self):
        # ActiveState alone (or testing just the later capture) is insufficient.
        self.assert_findings(self.invoke(service(active="inactive"), service()),
                             f"FAIL not-active {SERVICE}")
        self.assert_findings(self.invoke(service(), service(sub="exited")),
                             f"FAIL not-active {SERVICE}")
        self.assert_findings(self.invoke(timer(), timer("running"), options=[
            "--installed-mono", "100", "--unit", TIMER,
        ]), f"FAIL not-active {TIMER}")

    def test_missing_and_duplicate_units_cannot_stand_in_for_a_unique_match(self):
        # Last-entry-wins indexing or dropping unmatched rows could make these pass.
        for capture, reason in ((timer(), "missing-unit"),
                                (service() + "\n" + service(), "duplicate-unit")):
            for first, second in ((capture, service()), (service(), capture)):
                with self.subTest(reason=reason, first=first, second=second):
                    self.assert_findings(self.invoke(first, second), f"FAIL {reason} {SERVICE}")

    def test_reports_each_finding_and_a_separate_passing_unit(self):
        # Returning on the first failure hides distinct evidence and the timer result.
        self.assert_findings(self.invoke(
            service() + "\n" + timer(), service(restarts=1, pid=28) + "\n" + timer(),
            options=["--installed-mono", "100", "--unit", SERVICE, "--unit", TIMER],
        ), f"FAIL restarted {SERVICE}", f"FAIL pid-changed {SERVICE}", f"{TIMER} ok")

    def test_unreadable_and_malformed_inputs_fail_without_echoing_values(self):
        # Raw exceptions or dumping fields expose private path/capture values.
        # Permissive defaults would let a truncated or ambiguous block pass.
        cases = (
            None, b"\xff", "", service(pid=-1),
            service().replace("Monotonic=101", f"Monotonic={MARKER}"),
            service() + f"MainPID={MARKER}\n", service().replace(f"Id={SERVICE}\n", ""),
            service().replace("NRestarts=0\n", ""), service() + f"{MARKER}\n",
        )
        for capture in cases:
            with self.subTest(capture=capture):
                self.assert_findings(self.invoke(service(), capture), "FAIL bad-capture")
        self.assert_findings(self.invoke(None, b"\xff"), "FAIL bad-capture", "FAIL bad-capture")

    def test_invalid_check_inputs_are_findings_not_usage_errors(self):
        # Invalid names must not be echoed or treated as unsupported passing units.
        for cutoff, unit in (("-1", SERVICE), ("100", MARKER + ".socket"),
                             ("100", MARKER + "\n.service")):
            with self.subTest(cutoff=cutoff, unit=unit):
                self.assert_findings(self.invoke(service(), service(), options=[
                    "--installed-mono", cutoff, "--unit", unit,
                ]), "FAIL bad-capture")
        self.assert_findings(self.invoke(service(), service(), options=[
            "--installed-mono", "100", "--unit", SERVICE, "--unit", SERVICE,
        ]), f"FAIL duplicate-unit {SERVICE}")

    def test_usage_error_is_argparse_exit_two_without_a_verdict(self):
        # A malformed invocation must not get a capture verdict or leak argv data.
        for options in ([], ["--installed-mono", MARKER, "--unit", SERVICE]):
            with self.subTest(options=options):
                code, lines, error = self.invoke(None, None, options=options)
                self.assertEqual((code, lines), (2, []))
                self.assertIn("usage:", error)
