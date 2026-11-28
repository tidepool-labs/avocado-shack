"""Offline contract tests for the NPP job-state routing checker."""

from contextlib import redirect_stderr, redirect_stdout
import importlib.util
from io import StringIO
from pathlib import Path
import subprocess
import sys
from tempfile import TemporaryDirectory
import unittest
from unittest.mock import patch


ROOT = Path(__file__).resolve().parents[2]
SCRIPT = ROOT / "scripts/hass/npp_job_state_routing.py"
PASS = "PASS npp_job_state_routing"
FAIL = "FAIL npp_job_state_routing"


def snapshot():
    entries = {}
    for tree in (ROOT / "hass", ROOT / "storefront-mockup"):
        for path in (tree, *tree.rglob("*")):
            info = path.lstat()
            entries[path.relative_to(ROOT)] = (info.st_size, info.st_mtime_ns)
    return entries


class NppJobStateRoutingTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        spec = importlib.util.spec_from_file_location("npp_job_state_routing", SCRIPT)
        if spec is None or spec.loader is None:
            raise ImportError("cannot load the job-state routing checker")
        cls.checker = importlib.util.module_from_spec(spec)
        with patch.object(sys, "path", sys.path.copy()):
            spec.loader.exec_module(cls.checker)

    def invoke(self, exit_code, trailer):
        stdout, stderr = StringIO(), StringIO()
        with redirect_stdout(stdout), redirect_stderr(stderr):
            result = self.checker.main([])
        self.assertEqual(result, exit_code)
        self.assertEqual(stderr.getvalue(), "")
        lines = stdout.getvalue().splitlines()
        self.assertEqual(lines[-1:], [trailer])
        return lines[:-1]

    def fixture(self, active, question, edit, exit_code, trailer):
        with (
            patch.object(self.checker.job, "ACTIVE", active),
            patch.object(self.checker.reply, "QUESTION_STATES", question),
            patch.object(self.checker.reply, "EDIT_STATES", edit),
        ):
            return self.invoke(exit_code, trailer)

    def cli(self, *args):
        with TemporaryDirectory(dir=ROOT) as directory:
            return subprocess.run(
                [sys.executable, "-B", str(SCRIPT), *args],
                cwd=directory, capture_output=True, text=True, timeout=10,
            )

    def test_c1_full_pass(self):
        # Unrouted states are informational and stay in SQL-list order.
        self.assertEqual(
            self.fixture("'spare_z','asking','editing','spare_a'", ("asking",), ("editing",), 0, PASS),
            ["states active=4 question=1 edit=1", "unrouted spare_z", "unrouted spare_a"],
        )

    def test_c2_findings_trailer(self):
        # A first-finding shortcut would miss overlap or omit the final status.
        self.assertEqual(
            self.fixture("'asking','retake'", ("asking", "closed"), ("asking",), 1, FAIL),
            ["states active=2 question=2 edit=1", "FAIL routed-inactive closed",
             "FAIL state-overlap asking", "unrouted retake"],
        )

    def test_c2_1_active_unreadable(self):
        # Extracting quoted tokens without a full match can bless malformed SQL lists.
        for raw in (None, ("asking",), "", "'asking', 'editing'", "'asking',", "'Asking'", "'asking'\n"):
            with self.subTest(raw=raw):
                self.assertEqual(
                    self.fixture(raw, ("asking",), ("asking", "closed"), 1, FAIL),
                    ["FAIL active-unreadable"],
                )

    def test_c2_2_routed_inactive(self):
        # Checking only one tuple or sorting the findings changes the report.
        self.assertEqual(
            self.fixture("'asking'", ("closed_z", "closed_b", "asking"), ("closed_a",), 1, FAIL),
            ["states active=1 question=3 edit=1", "FAIL routed-inactive closed_z",
             "FAIL routed-inactive closed_b", "FAIL routed-inactive closed_a"],
        )

    def test_c2_3_state_overlap(self):
        # Both tuples can be individually active yet route a state ambiguously.
        self.assertEqual(
            self.fixture("'asking','editing'", ("editing", "asking"), ("asking", "editing"), 1, FAIL),
            ["states active=2 question=2 edit=2", "FAIL state-overlap editing", "FAIL state-overlap asking"],
        )

    def test_c3_usage_exit_2(self):
        # Default help and ignored extra args would break the no-arguments CLI.
        for arg in ("extra", "--unknown", "--help", "-h", "--"):
            with self.subTest(arg=arg):
                result = self.cli(arg)
                self.assertEqual(result.returncode, 2)
                self.assertEqual(result.stdout, "")
                self.assertTrue(result.stderr.startswith("usage: "))
                self.assertEqual(result.stderr.splitlines()[-1], f"{SCRIPT.name}: error: unrecognized arguments: {arg}")

    def test_c4_read_only(self):
        # A subprocess catches import-time writes the cached module could hide.
        before = snapshot()
        result = self.cli()
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(result.stdout.splitlines()[-1:], [PASS])
        self.assertEqual(snapshot(), before)

    def test_c5_output_shape(self):
        # The real entry point must not emit import chatter or extra diagnostics.
        result = self.cli()
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(result.stderr, "")
        self.assertRegex(
            result.stdout,
            r"\Astates active=[0-9]+ question=[0-9]+ edit=[0-9]+\n(?:unrouted [a-z_]+\n)*"
            r"PASS npp_job_state_routing\n\Z",
        )

    def test_c6_fixture(self):
        # A plausible terminal state added only to the edit tuple is one finding.
        with patch.object(self.checker.reply, "EDIT_STATES", ("working", "card_out", "editing", "published")):
            lines = self.invoke(1, FAIL)
        self.assertEqual(
            lines, ["states active=5 question=1 edit=4", "FAIL routed-inactive published", "unrouted retake"],
        )

    def test_c7_live_pins(self):
        # Changes to the checked-in routing table must update the measured pin.
        self.assertEqual(self.invoke(0, PASS), ["states active=5 question=1 edit=3", "unrouted retake"])
