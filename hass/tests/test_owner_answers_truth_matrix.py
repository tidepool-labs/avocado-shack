"""Behavioural contract for the offline owner-answer matrix report."""

from collections import Counter
from contextlib import redirect_stderr, redirect_stdout
from datetime import datetime
import importlib.util
from io import StringIO
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import patch

from hass import owner_answers


SCRIPT = Path(__file__).resolve().parents[2] / "scripts/hass/owner_answers_truth_matrix.py"
NOW = "2030-01-04T12:00:00+05:30"
PASS = "PASS owner_answers_truth_matrix"
FAIL = "FAIL owner_answers_truth_matrix"
LIE = "Done. It is on the website now."


class OwnerAnswersTruthMatrixTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        spec = importlib.util.spec_from_file_location(SCRIPT.stem, SCRIPT)
        if spec is None or spec.loader is None:
            raise ImportError("could not load the truth matrix script")
        cls.matrix = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(cls.matrix)

    def run_main(self):
        stdout, stderr = StringIO(), StringIO()
        with redirect_stdout(stdout), redirect_stderr(stderr):
            code = self.matrix.main(["--now", NOW])
        return code, stdout.getvalue(), stderr.getvalue()

    def run_cli(self, *args, cwd=None):
        return subprocess.run([sys.executable, "-B", str(SCRIPT), *args],
                              cwd=cwd, capture_output=True, text=True, timeout=10)

    def assert_verdict(self, result, code, trailer):
        status, stdout, stderr = result
        self.assertEqual(status, code)
        self.assertEqual(stderr, "")
        lines = stdout.splitlines()
        self.assertEqual(lines[-1:], [trailer])
        return lines

    def assert_findings(self, result, expected):
        lines = self.assert_verdict(result, 1, FAIL)
        self.assertEqual([line for line in lines[:-1] if line.startswith("FAIL ")], expected)
        return lines

    def replace_answer(self, state, install_state, replacement):
        original = owner_answers.did_it_work

        def answer(change, install, now):
            if change["state"] == state and (install or {}).get("state") == install_state:
                if isinstance(replacement, Exception):
                    raise replacement
                return replacement
            return original(change, install, now)

        return patch.object(owner_answers, "did_it_work", side_effect=answer)

    def test_c1_full_pass(self):
        # A clean run must not emit findings or exit with a failure status.
        result = self.run_cli("--now", NOW)
        lines = self.assert_verdict((result.returncode, result.stdout, result.stderr), 0, PASS)
        self.assertFalse(any(line.startswith("FAIL ") for line in lines))

    def test_c2_findings_trailer(self):
        # No early return after the first finding, and no PASS after the summary.
        with self.replace_answer("proposed", None, f"{LIE} The server is busy."):
            lines = self.assert_findings(self.run_main(), [
                "FAIL false-live proposed none",
                "FAIL false-success proposed none",
                "FAIL voice proposed none",
            ])
        self.assertEqual(lines[-2], "rows 44")

    def test_c2_1_false_live(self):
        # A saved draft with no install may claim saved, but not live.
        with self.replace_answer("applied", None, LIE):
            self.assert_findings(self.run_main(), ["FAIL false-live applied none"])

    def test_c2_2_missing_live(self):
        # Checking only false positives would miss a confirmed install described as merely saved.
        with self.replace_answer("verified", "installed", "It's saved."):
            self.assert_findings(self.run_main(), ["FAIL missing-live verified installed"])

    def test_c2_3_false_success(self):
        # A "saved" claim can be false even though it never claims to be on the website.
        for state, install, label in (("proposed", None, "none"), ("applied", "failed", "failed")):
            with self.subTest(state=state, install=install):
                with self.replace_answer(state, install, "It's saved."):
                    self.assert_findings(self.run_main(), [f"FAIL false-success {state} {label}"])

    def test_c2_4_voice(self):
        # A jargon-only violation must fail even without an honesty violation.
        with self.replace_answer("proposed", None, "The server is busy."):
            lines = self.assert_findings(self.run_main(), ["FAIL voice proposed none"])
        self.assertIn("row proposed none live no success no voice broken", lines)

    def test_c2_5_answer_error(self):
        # A thrown answer must not silently disappear, abort the matrix, or leak its payload.
        marker = "synthetic exception detail"
        with self.replace_answer("applied", "installed", ValueError(marker)):
            result = self.run_main()
        lines = self.assert_findings(result, ["FAIL answer-error applied installed"])
        self.assertIn("row applied installed live no success no voice broken", lines)
        self.assertIn("row bogus odd live no success no voice ok", lines)
        self.assertEqual(lines[-2], "rows 44")
        self.assertNotIn(marker, result[1] + result[2])

    def test_c3_usage_exit_2(self):
        # Missing, extra, and malformed arguments belong to argparse, not the report.
        for args, error in (
            ((), "the following arguments are required: --now"),
            (("--now", NOW, "--unknown"), "unrecognized arguments: --unknown"),
            (("--now", "unreadable"), "argument --now: expected an ISO time with a UTC offset"),
            (("--now", "2030-01-04T12:00:00"), "argument --now: expected an ISO time with a UTC offset"),
            (("--now", "0001-01-01T00:00:00Z"), "--now must allow an install time one hour earlier"),
        ):
            with self.subTest(args=args):
                result = self.run_cli(*args)
                self.assertEqual(result.returncode, 2)
                self.assertEqual(result.stdout, "")  # No last stdout line on usage errors.
                self.assertTrue(result.stderr.startswith("usage: "))
                self.assertEqual(result.stderr.splitlines()[-1:], [f"{SCRIPT.name}: error: {error}"])

    def test_c4_read_only(self):
        # Running outside the checkout must not need or leave any local state.
        with tempfile.TemporaryDirectory() as directory:
            result = self.run_cli("--now", NOW, cwd=directory)
            self.assert_verdict((result.returncode, result.stdout, result.stderr), 0, PASS)
            self.assertEqual(list(Path(directory).iterdir()), [])

    def test_c5_no_private_values(self):
        # Catch a debug print of either the full reply or the draft summary.
        answers = []
        original = owner_answers.did_it_work

        def record_answer(*args):
            answer = original(*args)
            answers.append(answer)
            return answer

        with patch.object(owner_answers, "did_it_work", side_effect=record_answer):
            result = self.run_main()
        self.assert_verdict(result, 0, PASS)
        self.assertTrue(any("Honey jar" in answer for answer in answers))
        emitted = result[1] + result[2]
        for private in (*answers, "Honey jar"):
            self.assertNotIn(private, emitted)

    def test_c6_merged_matrix(self):
        # An aggregate count alone would miss duplicated states or swapped live rows.
        with patch.object(owner_answers, "did_it_work", wraps=owner_answers.did_it_work) as answer:
            lines = self.assert_verdict(self.run_main(), 0, PASS)
        installs = {
            "none": None,
            "installed": {"state": "installed", "installed_at": "2030-01-04T11:00:00+05:30"},
            "failed": {"state": "failed", "reason": "write failed"},
            "odd": {"state": "weird"},
        }
        pairs = [(state, label) for state in (*owner_answers.KNOWN, None, "bogus") for label in installs]
        expected_calls = [({"state": state, "summary": "Honey jar", "reason": ""}, installs[label],
                           datetime.fromisoformat(NOW)) for state, label in pairs]
        self.assertCountEqual([call.args for call in answer.call_args_list], expected_calls)
        self.assertEqual(lines[-2], "rows 44")
        self.assertEqual(len(lines[:-2]), 44)
        actual = Counter()
        live, success = set(), set()
        for line in lines[:-2]:
            self.assertRegex(line, r"^row \S+ \S+ live (yes|no) success (yes|no) voice ok$")
            _, state, label, _, live_flag, _, success_flag, _, _ = line.split()
            actual[state, label] += 1
            if live_flag == "yes":
                live.add((state, label))
            if success_flag == "yes":
                success.add((state, label))
        self.assertEqual(actual, Counter(("none" if state is None else state, label) for state, label in pairs))
        # Both source bases have two SAVED states and one installed case per state.
        self.assertEqual(live, {("applied", "installed"), ("verified", "installed")})
        self.assertLessEqual(success, {(state, label) for state in ("applied", "verified")
                                       for label in installs if label != "failed"})

    def test_c7_patched_lie(self):
        # An always-live reply must be caught through the actual imported answer entry point.
        with patch.object(owner_answers, "did_it_work", return_value=LIE):
            result = self.run_main()
        lines = self.assert_verdict(result, 1, FAIL)
        self.assertEqual(lines.count("FAIL false-live proposed none"), 1)
        self.assertNotIn(LIE, result[1] + result[2])


if __name__ == "__main__":
    unittest.main()
