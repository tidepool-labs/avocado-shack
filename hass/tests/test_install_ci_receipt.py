"""Fixture-only tests of the offline CI receipt CLI contract."""

from contextlib import redirect_stderr, redirect_stdout
import importlib.util
import io
import json
from pathlib import Path
from tempfile import TemporaryDirectory
import unittest


SCRIPT = Path(__file__).resolve().parents[2] / "scripts/hass/install_ci_receipt.py"
SPEC = importlib.util.spec_from_file_location("install_ci_receipt", SCRIPT)
assert SPEC is not None and SPEC.loader is not None
RECEIPT = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(RECEIPT)
SHA = "a" * 40
OTHER = "b" * 40
OLDER = "2030-01-01T00:00:00Z"
NEWER = "2030-01-01T00:01:00Z"
PRIVATE = "synthetic-private-marker"


def run(name="lint", **overrides):
    return {"name": name, "head_sha": SHA, "status": "completed", "conclusion": "success",
            "completed_at": NEWER, **overrides}


class InstallCiReceiptTests(unittest.TestCase):
    def setUp(self):
        directory = TemporaryDirectory()
        self.addCleanup(directory.cleanup)
        root = Path(directory.name)
        self.checks = root / "checks.json"
        self.required = root / "required.json"

    def invoke(self, *runs, names=("lint",), sha=SHA, total=None):
        self.checks.write_text(json.dumps({"check_runs": runs,
                                           "total_count": len(runs) if total is None else total}),
                               encoding="utf-8")
        self.required.write_text(json.dumps(names), encoding="utf-8")
        return self.invoke_files(sha)

    def invoke_files(self, sha=SHA):
        stdout, stderr = io.StringIO(), io.StringIO()
        with redirect_stdout(stdout), redirect_stderr(stderr):
            code = RECEIPT.main(["--checks", str(self.checks), "--required", str(self.required),
                                 "--sha", sha])
        self.assertEqual(stderr.getvalue(), "")
        self.assertNotIn(PRIVATE, stdout.getvalue())
        return code, stdout.getvalue().splitlines()

    def assert_receipt(self, actual, *lines, passed=False):
        self.assertEqual(actual, (0 if passed else 1,
                                  [*lines, f"{'PASS' if passed else 'FAIL'} install_ci_receipt"]))

    def test_pass_selects_latest_matching_runs_and_required_names_only(self):
        # First/last-in-file or name-only joins pick the wrong run; an API-wide
        # report would also leak the unrelated name and payload fields.
        self.assert_receipt(self.invoke(
            run(private=PRIVATE), run("unit"), run(completed_at=OLDER, conclusion="failure"),
            run(head_sha=OTHER, status="queued", completed_at=None, conclusion=None),
            run(PRIVATE, conclusion="failure"), names=("unit", "lint")),
            "unit success", "lint success", passed=True)

    def test_bad_sha_is_a_finding_not_a_usage_error(self):
        # Matching against raw invalid SHA could misreport wrong-head or accept it.
        for sha in ("", SHA[:-1], SHA.upper(), "g" * 40, SHA + "\n", PRIVATE):
            with self.subTest(sha=sha):
                self.assert_receipt(self.invoke(run(), sha=sha), "FAIL bad-sha")

    def test_bad_json_on_either_input_and_unreadable_file(self):
        # Parser and OS errors must not emit the raw source or a path.
        for target in ("checks", "required"):
            for raw in (None, b'{"synthetic-private-marker":', b'"\xff"'):
                with self.subTest(target=target, raw=raw):
                    self.invoke(run())
                    path = getattr(self, target)
                    if raw is None:
                        path.rename(path.with_name(PRIVATE))
                    else:
                        path.write_bytes(raw)
                    self.assert_receipt(self.invoke_files(), "FAIL bad-json")

    def test_bad_json_for_invalid_shape_or_nonstandard_json(self):
        # Invalid rows/envelopes must not be treated as valid evidence or allow a
        # last-key-wins success; nonprinting names cannot inject receipt lines.
        for target, raw in (
            ("required", '[1]'), ("required", '{}'), ("required", '["lint\\nspoof"]'),
            ("checks", '[]'), ("checks", '{"total_count":false,"check_runs":[]}'),
            ("checks", '{"total_count":1,"check_runs":[{}]}'),
            ("checks", '{"total_count":1,"check_runs":[null]}'),
            ("checks", '{"total_count":0,"total_count":1,"check_runs":[]}'),
            ("checks", '{"total_count":0,"check_runs":[],"ignored":NaN}'),
            ("checks", json.dumps({"total_count": 1, "check_runs": [run(completed_at=None)]})),
            ("checks", json.dumps({"total_count": 1, "check_runs": [run(completed_at=PRIVATE)]})),
        ):
            with self.subTest(target=target, raw=raw):
                self.invoke(run())
                getattr(self, target).write_text(raw, encoding="utf-8")
                self.assert_receipt(self.invoke_files(), "FAIL bad-json")

    def test_empty_required_checks_refuses(self):
        # Without a nonempty-list guard, the check loop can report PASS after
        # evaluating zero required names even though the capture is valid.
        capture = run(private=PRIVATE)
        self.assert_receipt(self.invoke(capture, names=("lint",)), "lint success", passed=True)
        self.assert_receipt(self.invoke(capture, names=()), "FAIL bad-json")

    def test_truncated_even_if_every_required_check_on_this_page_passes(self):
        # Checking only the required names on page one could miss a newer rerun.
        self.assert_receipt(self.invoke(run(), total=2), "FAIL truncated")

    def test_count_larger_than_total_is_refused(self):
        # Protects: a capture certifies only when total_count equals its runs. A one-sided
        # `total > len(runs)` check would print PASS for total_count 0 with a green run.
        self.assert_receipt(self.invoke(run(), total=1), "lint success", passed=True)
        self.assert_receipt(self.invoke(run(), total=0), "FAIL bad-json")
        self.assert_receipt(self.invoke(run(), run("unit"), total=1), "FAIL bad-json")
        self.assert_receipt(self.invoke(run(), total=2), "FAIL truncated")

    def test_missing_check(self):
        # An unrelated success can't satisfy a required name.
        self.assert_receipt(self.invoke(run("unit")), "FAIL missing-check lint")

    def test_wrong_head(self):
        # A green run with the right name but on another SHA doesn't count.
        self.assert_receipt(self.invoke(run(head_sha=OTHER)), "FAIL wrong-head lint")

    def test_not_completed_overrides_a_success_on_the_same_head(self):
        # Filtering out unfinished reruns would leave the completed success.
        self.assert_receipt(self.invoke(run(), run(status="in_progress", completed_at=None,
                                                   conclusion=None)), "FAIL not-completed lint")

    def test_not_success_uses_latest_conclusion_without_echoing_it(self):
        # An earlier green run or a non-failure conclusion cannot pass the gate.
        for conclusion in ("failure", "skipped", "neutral", "cancelled", None, PRIVATE):
            with self.subTest(conclusion=conclusion):
                self.assert_receipt(self.invoke(run(conclusion=conclusion), run(completed_at=OLDER)),
                                    "FAIL not-success lint")

    def test_ambiguous_latest_conclusions_in_either_file_order(self):
        # Tie-breaking by arrival order could arbitrarily declare a pass.
        for runs in ((run(), run(conclusion="failure")), (run(conclusion=None), run())):
            for order in (runs, runs[::-1]):
                with self.subTest(order=order):
                    self.assert_receipt(self.invoke(*order), "FAIL ambiguous lint")

    def test_equal_successes_and_conflicts_at_older_timestamps_do_not_block(self):
        # Treating all duplicates or any historical conflict as ambiguous overblocks.
        self.assert_receipt(self.invoke(run(), run(), run(completed_at=OLDER),
                                        run(completed_at=OLDER, conclusion="failure")),
                            "lint success", passed=True)

    def test_completion_times_are_compared_as_instants(self):
        # A lexicographically greater wall time can be earlier in UTC.
        self.assert_receipt(self.invoke(run(completed_at="2030-01-01T01:00:00+01:00",
                                            conclusion="failure"), run()),
                            "lint success", passed=True)

    def test_reports_all_findings_and_keeps_success_lines(self):
        # A fail-fast or last-result-wins loop would omit lines or report PASS.
        self.assert_receipt(self.invoke(run(), run("unit", head_sha=OTHER),
                                        names=("build", "unit", "lint")),
                            "FAIL missing-check build", "FAIL wrong-head unit", "lint success")

    def test_usage_error_keeps_argparse_exit_2(self):
        # An absent flag is a usage error, unlike a supplied invalid SHA value.
        stdout, stderr = io.StringIO(), io.StringIO()
        with redirect_stdout(stdout), redirect_stderr(stderr), self.assertRaises(SystemExit) as exc:
            RECEIPT.main(["--checks", str(self.checks), "--required", str(self.required)])
        self.assertEqual(exc.exception.code, 2)
        self.assertEqual(stdout.getvalue(), "")
        self.assertIn("usage:", stderr.getvalue())
        self.assertIn("--sha", stderr.getvalue())


if __name__ == "__main__":
    unittest.main()
