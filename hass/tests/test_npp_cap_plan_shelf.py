"""Offline contract tests for the cap shelf and kind report."""

from contextlib import redirect_stderr, redirect_stdout
import importlib.util
from io import StringIO
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import patch

from hass.npp import missing, stages
from hass.npp.job import Plan

ROOT = Path(__file__).resolve().parents[2]
SCRIPT = ROOT / "scripts/hass/npp_cap_plan_shelf.py"
FAIL = "FAIL npp_cap_plan_shelf"
PASS = "PASS npp_cap_plan_shelf"


def ready(kind, category):
    return Plan(listing={"kind": kind, "category": category}), "card"


class CapPlanShelfTests(unittest.TestCase):
    def setUp(self):
        temp = tempfile.TemporaryDirectory(dir=ROOT)
        self.addCleanup(temp.cleanup)
        self.temp = Path(temp.name)
        spec = importlib.util.spec_from_file_location("npp_cap_plan_shelf", SCRIPT)
        assert spec is not None and spec.loader is not None
        self.script = importlib.util.module_from_spec(spec)
        with patch.object(sys, "path", sys.path.copy()):
            spec.loader.exec_module(self.script)

    def cli(self, *args):
        return subprocess.run(
            [sys.executable, "-B", str(SCRIPT), *args], cwd=self.temp,
            env={**os.environ, "TMPDIR": str(self.temp)}, capture_output=True,
            text=True, timeout=15,
        )

    def invoke(self):
        stdout, stderr = StringIO(), StringIO()
        with redirect_stdout(stdout), redirect_stderr(stderr):
            code = self.script.main([])
        self.assertEqual(stderr.getvalue(), "")
        return code, stdout.getvalue().splitlines()

    def with_cap(self, *results):
        with patch.object(stages.ProductionStages, "cap", side_effect=results):
            return self.invoke()

    def assert_findings(self, run, *expected):
        code, lines = run
        self.assertEqual(code, 1)
        self.assertEqual(lines[-1], FAIL)
        self.assertEqual([line for line in lines[:-1] if line.startswith("FAIL ")], list(expected))
        return lines

    def test_c1_full_pass(self):
        # A valid food pair and a defaulted mug must not turn into a blanket FAIL.
        food, mug = ready("food", "pantry"), ready("non-food", "general")
        code, lines = self.with_cap(food, food, mug)
        self.assertEqual(code, 0)
        self.assertEqual(lines[-1], PASS)
        self.assertFalse(any(line.startswith("FAIL ") for line in lines))

    def test_c2_findings_trailer(self):
        # Reporting several findings must still produce a single failing trailer.
        lines = self.assert_findings(
            self.with_cap(ready("non-food", "general"), ready("food", "pantry"), Plan()),
            "FAIL cap-food-as-nonfood 0", "FAIL cap-food-general 0", "FAIL cap-not-ready 2",
        )
        self.assertEqual(lines.count(FAIL), 1)

    def test_c2_1_cap_food_as_nonfood(self):
        # A correct shelf alone does not excuse the wrong food kind.
        wrong, mug = ready("non-food", "pantry"), ready("non-food", "general")
        self.assert_findings(self.with_cap(wrong, wrong, mug),
                             "FAIL cap-food-as-nonfood 0", "FAIL cap-food-as-nonfood 1")

    def test_c2_2_cap_food_general(self):
        # A correct food kind alone does not excuse the wrong shelf.
        wrong, mug = ready("food", "general"), ready("non-food", "general")
        self.assert_findings(self.with_cap(wrong, wrong, mug),
                             "FAIL cap-food-general 0", "FAIL cap-food-general 1")

    def test_c2_3_cap_not_ready(self):
        # A plan asking questions isn't a listing, even though cap returned a plan.
        question = Plan(questions=(("identity", "What is it?"),))
        lines = self.assert_findings(self.with_cap(question, ready("food", "pantry"), None),
                                     "FAIL cap-not-ready 0", "FAIL cap-not-ready 2")
        for i in (0, 2):
            self.assertIn(f"cap {i} ready=no kind=none category=none", lines)

    def test_c2_4_check_error(self):
        # Exceptions must fail closed without echoing their detail or duplicating the error.
        error = RuntimeError("synthetic exception detail")
        lines = self.assert_findings(self.with_cap(error, error, ready("non-food", "general")),
                                     "FAIL check-error")
        self.assertNotIn(str(error), "\n".join(lines))
        self.assertIn("cap 2 ready=yes kind=non-food category=general", lines)

    def test_c3_usage_exit_2(self):
        # Even argparse's help switch and the end-of-options delimiter are arguments.
        for arg in ("positional", "--unknown", "--help", "--"):
            with self.subTest(arg=arg):
                run = self.cli(arg)
                self.assertEqual(run.returncode, 2)
                self.assertEqual(run.stdout, "")
                self.assertTrue(run.stderr.startswith("usage: "))
                self.assertTrue(run.stderr.splitlines()[-1].endswith(f"unrecognized arguments: {arg}"))

    def test_c4_read_only(self):
        # A new sidecar, touched input, or cache directory in either tree is a write.
        def snapshot():
            state = {}
            for tree in (ROOT / "hass", ROOT / "storefront-mockup"):
                for path in (tree, *tree.rglob("*")):
                    info = path.lstat()
                    state[path.relative_to(ROOT)] = (info.st_size, info.st_mtime_ns)
            return state

        before = snapshot()
        run = self.cli()
        self.assertEqual(run.returncode, 1)
        self.assertEqual(run.stdout.splitlines()[-1], FAIL)
        self.assertEqual(snapshot(), before)

    def test_c5_output_shape(self):
        # A debug line, raw listing field, or unexpected stderr would break the report protocol.
        run = self.cli()
        self.assertEqual(run.returncode, 1)
        self.assertEqual(run.stderr, "")
        lines = run.stdout.splitlines()
        self.assertEqual(lines[-1], FAIL)
        for line in lines[:-1]:
            self.assertRegex(line, r"\A(?:cap [0-2] ready=(?:yes|no) kind=[a-z][a-z0-9_-]*"
                                   r" category=[a-z][a-z0-9_-]*|cap defaults kind_default_category=[0-9]+"
                                   r"|FAIL cap-food-(?:as-nonfood|general) [01]"
                                   r"|FAIL cap-not-ready [0-2]|FAIL check-error)\Z")

    def test_c6_fixture(self):
        # The real planner must propagate the decision's shelf; don't stub start_plan.
        def pantry(_self, _reading, *, owner_item, price, **_kwargs):
            return missing.Decision(True, owner_item, "pantry", price, missing.Maker("absent"), (), (), ())

        with patch.object(missing.MissingInfo, "decide", pantry):
            lines = self.assert_findings(self.invoke(), "FAIL cap-food-as-nonfood 0", "FAIL cap-food-as-nonfood 1")
        for i in (0, 1):
            self.assertIn(f"cap {i} ready=yes kind=non-food category=pantry", lines)

    def test_c7_live_pins(self):
        # Pin the current offline observation, including order, not a desired production policy.
        run = self.cli()
        self.assertEqual(run.returncode, 1)
        self.assertEqual(run.stdout.splitlines(), [
            "cap 0 ready=yes kind=non-food category=general",
            "cap 1 ready=yes kind=non-food category=general",
            "cap 2 ready=yes kind=non-food category=general",
            "cap defaults kind_default_category=4",
            "FAIL cap-food-as-nonfood 0",
            "FAIL cap-food-general 0",
            "FAIL cap-food-as-nonfood 1",
            "FAIL cap-food-general 1",
            FAIL,
        ])
