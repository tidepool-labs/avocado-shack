"""Offline CLI and mutation tests for the question-closure drift guard."""

from contextlib import redirect_stderr, redirect_stdout
import importlib.util
import io
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import patch


ROOT = Path(__file__).resolve().parents[2]
SCRIPT = ROOT / "scripts/hass/npp_card_closes_questions.py"
PASS = "PASS npp_card_closes_questions"
FAIL = "FAIL npp_card_closes_questions"
PINNED = (
    "case 0 category:answered:- duplicate:open:- item:answered:p-card maker:expired:- "
    "near_maker:open:- selling_price:answered:p-card selling_price:answered:p-card",
    "case 1 category:answered:- duplicate:open:- item:open:- maker:expired:- "
    "near_maker:open:- selling_price:answered:p-card selling_price:answered:p-card",
    "case 2 category:answered:- duplicate:open:- item:open:- maker:expired:- "
    "near_maker:open:- selling_price:open:- selling_price:open:-",
    "case 3 category:answered:- duplicate:open:- item:answered:p-card maker:expired:- "
    "near_maker:open:- selling_price:answered:p-card selling_price:answered:p-card",
)


def load_script():
    spec = importlib.util.spec_from_file_location("npp_card_closes_questions", SCRIPT)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    with patch.object(sys, "path", sys.path.copy()):
        spec.loader.exec_module(module)
    return module


def close_owner_and_more(jobs, jid):
    jobs.db.execute("UPDATE npp_questions SET state='answered' WHERE job_id=? AND state='open'", (jid,))


def close_other(jobs):
    jobs.db.execute("UPDATE npp_questions SET state='answered' WHERE job_id='c3d4'")


def snapshot():
    entries = {}
    for name in ("hass", "storefront-mockup"):
        tree = ROOT / name
        for path in (tree, *tree.rglob("*")):
            stat = path.lstat()
            entries[path.relative_to(ROOT)] = (stat.st_size, stat.st_mtime_ns)
    return entries


class CardClosesQuestionsTests(unittest.TestCase):
    def setUp(self):
        self.script = load_script()
        self.jobs = self.script.job.Jobs
        self.tmp = self.enterContext(tempfile.TemporaryDirectory())

    def cli(self, *args):
        return subprocess.run(
            [sys.executable, "-B", str(SCRIPT), *args], cwd=self.tmp,
            env={**os.environ, "TMPDIR": self.tmp}, capture_output=True, text=True, timeout=10,
        )

    def invoke(self):
        out, err = io.StringIO(), io.StringIO()
        with redirect_stdout(out), redirect_stderr(err), patch.object(tempfile, "tempdir", self.tmp):
            code = self.script.main([])
        return subprocess.CompletedProcess([], code, out.getvalue(), err.getvalue())

    def assert_result(self, result, code, trailer):
        self.assertEqual(result.returncode, code, result.stderr)
        self.assertEqual(result.stderr, "")
        lines = result.stdout.splitlines()
        self.assertEqual(lines[-1:], [trailer])
        return lines[:-1]

    def findings(self, result):
        lines = self.assert_result(result, 1, FAIL)
        return [line for line in lines if line.startswith("FAIL ")]

    def ignore_still_open(self):
        original = self.jobs.answer_questions

        def mutated(jobs, jid, pid, now, still_open):
            return original(jobs, jid, pid, now, ())

        return patch.object(self.jobs, "answer_questions", mutated)

    def test_c1_full_pass(self):
        # A completed successful CLI run must not fall through to the failure status.
        self.assert_result(self.cli(), 0, PASS)

    def test_c2_findings_trailer(self):
        # Multiple simultaneous findings must accumulate in case/check order, not short-circuit.
        original = self.jobs.answer_questions

        def mutated(jobs, jid, pid, now, still_open):
            original(jobs, jid, pid, now, still_open)
            close_owner_and_more(jobs, jid)
            close_other(jobs)

        with patch.object(self.jobs, "answer_questions", mutated):
            lines = self.assert_result(self.invoke(), 1, FAIL)
        expected = []
        for i, pin in enumerate(PINNED):
            changed = pin.replace(":open:-", ":answered:-")
            expected.extend((changed, f"FAIL owner-ask-closed {i}", f"FAIL other-job-touched {i}",
                             f"FAIL question-changed {i}"))
        self.assertEqual(lines, expected)

    def test_c2_1_owner_ask_closed(self):
        # Generic closure must never satisfy the two owner-only asks.
        original = self.jobs.answer_questions

        def mutated(jobs, jid, pid, now, still_open):
            original(jobs, jid, pid, now, still_open)
            close_owner_and_more(jobs, jid)

        with patch.object(self.jobs, "answer_questions", mutated):
            result = self.invoke()
        self.assertEqual(self.findings(result), [
            f"FAIL {reason} {i}" for i in range(4) for reason in ("owner-ask-closed", "question-changed")
        ])

    def test_c2_2_other_job_touched(self):
        # Losing job scoping can close a different listing's price question.
        original = self.jobs.answer_questions

        def mutated(jobs, jid, pid, now, still_open):
            original(jobs, jid, pid, now, still_open)
            close_other(jobs)

        with patch.object(self.jobs, "answer_questions", mutated):
            result = self.invoke()
        self.assertEqual(self.findings(result), [f"FAIL other-job-touched {i}" for i in range(4)])

    def test_c2_3_question_changed(self):
        # Dropping still_open changes ordinary questions without tripping either safety check.
        with self.ignore_still_open():
            result = self.invoke()
        self.assertEqual(self.findings(result), ["FAIL question-changed 1", "FAIL question-changed 2"])

    def test_c2_4_check_error(self):
        # An unreadable asset must fail closed without leaking the exception's text.
        with patch.object(self.script.hass.npp, "assets", side_effect=RuntimeError("synthetic detail")):
            result = self.invoke()
        self.assertEqual(self.assert_result(result, 1, FAIL), ["FAIL check-error"])

    def test_c3_usage_exit_2(self):
        # Even argparse's implicit help and end-of-options inputs aren't part of this CLI.
        for arg in ("extra", "--unknown", "--help", "--"):
            with self.subTest(arg=arg):
                result = self.cli(arg)
                self.assertEqual(result.returncode, 2)
                self.assertEqual(result.stdout, "")
                self.assertTrue(result.stderr.startswith("usage: "))
                self.assertIn("error:", result.stderr.splitlines()[-1])

    def test_c4_read_only(self):
        # A file-backed fixture or stray write must not leave state in either source tree.
        before = snapshot()
        result = self.cli()
        after = snapshot()
        self.assert_result(result, 0, PASS)
        self.assertEqual(after, before)
        self.assertEqual(list(Path(self.tmp).iterdir()), [])

    def test_c5_output_shape(self):
        # Extra debug prints, blank lines, or diagnostics would break the successful CLI receipt.
        result = self.cli()
        lines = self.assert_result(result, 0, PASS)
        self.assertEqual(len(lines), 4)
        row = r"[a-z_]+:[a-z_]+:[a-z-]+"
        for i, line in enumerate(lines):
            self.assertRegex(line, rf"^case {i} {row}(?: {row})*$")
        self.assertEqual(result.stdout, "\n".join([*lines, PASS, ""]))

    def test_c6_fixture(self):
        # The empty tuple should make the real method produce the same states as case 0 in every case.
        with self.ignore_still_open():
            result = self.invoke()
        case_tail = PINNED[0].split(" ", 2)[2]
        self.assertEqual(self.assert_result(result, 1, FAIL), [
            f"case 0 {case_tail}", f"case 1 {case_tail}", "FAIL question-changed 1",
            f"case 2 {case_tail}", "FAIL question-changed 2", f"case 3 {case_tail}",
        ])

    def test_c7_live_pins(self):
        # Both repeated price rows and the pre-answered/expired rows are part of the independent pin.
        lines = self.assert_result(self.invoke(), 0, PASS)
        self.assertEqual(tuple(lines), PINNED)
        self.assertEqual(self.script.EXPECTED, PINNED)
