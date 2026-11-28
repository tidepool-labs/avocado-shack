"""Offline contract tests for the NPP question-cap drift guard."""

from contextlib import nullcontext, redirect_stderr, redirect_stdout
import importlib.util
import io
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import patch

REPO = Path(__file__).resolve().parents[2]
SCRIPT = REPO / "scripts/hass/npp_ask_cap_agreement.py"
PASS = "PASS npp_ask_cap_agreement"
FAIL = "FAIL npp_ask_cap_agreement"
LIVE = ["cap job=2 rules=2", "questions caps=2 rules=2", PASS]
COUNT = 'store.one("SELECT COUNT(*) FROM npp_questions WHERE qid=?", qid)[0]'


def finish(*expressions):
    body = "\n".join(f"        if {expr}:\n            pass" for expr in expressions)
    return f"class Jobs:\n    def finish(self):\n{body}\n"


class NppAskCapAgreementTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        spec = importlib.util.spec_from_file_location("npp_ask_cap_agreement", SCRIPT)
        if spec is None or spec.loader is None:
            raise ImportError("could not load the ask-cap checker")
        cls.checker = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(cls.checker)

    def invoke(self, *args):
        with tempfile.TemporaryDirectory() as tmp:
            return subprocess.run(
                [sys.executable, "-B", str(SCRIPT), *args], cwd=tmp,
                capture_output=True, text=True, timeout=15,
            )

    def invoke_fixture(self, source, *, reply_cap=None):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "job.py"
            if source is not None:
                path.write_text(source, encoding="utf-8")
            out, err = io.StringIO(), io.StringIO()
            assets_override = nullcontext()
            if reply_cap is not None:
                pins, files, replies = self.checker.npp.assets()
                caps = dict(replies["caps"], max_questions_per_reply=reply_cap)
                assets_override = patch.object(self.checker.npp, "assets", return_value=(
                    pins, files, dict(replies, caps=caps),
                ))

            with (patch.object(self.checker, "JOB_PATH", path),
                  assets_override,
                  redirect_stdout(out), redirect_stderr(err)):
                code = self.checker.main([])
            return code, out.getvalue().splitlines(), err.getvalue()

    def test_c1_full_pass(self):
        # The CLI must expose a successful main() as a zero process exit and PASS.
        result = self.invoke()
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(result.stdout.splitlines()[-1:], [PASS])

    def test_c2_findings_trailer(self):
        # An early return or a single-condition verdict can hide the second drift.
        self.assertEqual(self.invoke_fixture(finish(f"{COUNT} < 3"), reply_cap=4), (
            1, ["cap job=3 rules=2", "questions caps=4 rules=2",
                "FAIL ask-cap-drift", "FAIL question-cap-drift", FAIL], "",
        ))

    def test_c2_1_ask_cap_drift(self):
        # A runner-only cap edit must be detected in either direction.
        for cap in (1, 3):
            with self.subTest(cap=cap):
                self.assertEqual(self.invoke_fixture(finish(f"{COUNT} < {cap}")), (
                    1, [f"cap job={cap} rules=2", "questions caps=2 rules=2",
                        "FAIL ask-cap-drift", FAIL], "",
                ))

    def test_c2_2_question_cap_drift(self):
        # Matching ask counts must not mask a different reply cap.
        self.assertEqual(self.invoke_fixture(finish(f"{COUNT} < 2"), reply_cap=1), (
            1, ["cap job=2 rules=2", "questions caps=1 rules=2",
                "FAIL question-cap-drift", FAIL], "",
        ))

    def test_c2_3_cap_unreadable(self):
        # Missing and ambiguous matches must not fall back to the pinned rule.
        cases = {
            "missing file": None,
            "syntax error": "class Jobs:\n",
            "wrong class": finish(f"{COUNT} < 2").replace("class Jobs", "class Other"),
            "wrong method": finish(f"{COUNT} < 2").replace("def finish", "def other"),
            "wrong SQL": finish(f"{COUNT} < 2").replace("npp_questions", "other_table"),
            "wrong left operand": finish('rows[0] < 2'),
            "wrong operator": finish(f"{COUNT} <= 2"),
            "chain": finish(f"{COUNT} < 2 < 3"),
            "boolean": finish(f"{COUNT} < True"),
            "multiple identical matches": finish(f"{COUNT} < 2", f"{COUNT} < 2"),
        }
        for case, source in cases.items():
            with self.subTest(case=case):
                self.assertEqual(self.invoke_fixture(source), (
                    1, ["questions caps=2 rules=2", "FAIL cap-unreadable", FAIL], "",
                ))
        self.assertEqual(self.invoke_fixture(None, reply_cap=3), (
            1, ["questions caps=3 rules=2", "FAIL cap-unreadable",
                "FAIL question-cap-drift", FAIL], "",
        ))

    def test_c3_usage_exit_2(self):
        # Stray tokens (including argparse defaults) must not run the check.
        for token in ("extra", "--unknown", "--help", "-h", "--"):
            with self.subTest(token=token):
                result = self.invoke(token)
                self.assertEqual(result.returncode, 2)
                self.assertEqual(result.stdout, "")
                self.assertIn("usage:", result.stderr)
                self.assertIn("error:", result.stderr)

    def test_c4_read_only(self):
        # Catch sidecars and rewrites, including same-size rewrites via mtimes.
        def snapshot():
            items = {}
            for name in ("hass", "storefront-mockup"):
                root = REPO / name
                for path in (root, *root.rglob("*")):
                    info = path.lstat()
                    items[path.relative_to(REPO)] = (info.st_size, info.st_mtime_ns)
            return items

        before = snapshot()
        result = self.invoke()
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(result.stdout.splitlines()[-1:], [PASS])
        self.assertEqual(snapshot(), before)

    def test_c5_output_shape(self):
        # Extra debug output or pin-loader tracebacks would corrupt the report.
        result = self.invoke()
        self.assertEqual(result.returncode, 0)
        self.assertEqual(result.stdout, "\n".join(LIVE) + "\n")
        self.assertEqual(result.stderr, "")
        with patch.object(self.checker.npp, "assets", side_effect=ValueError("bad pin")):
            out, err = io.StringIO(), io.StringIO()
            with redirect_stdout(out), redirect_stderr(err):
                self.assertEqual(self.checker.main([]), 1)
            self.assertEqual(out.getvalue(), f"FAIL cap-unreadable\n{FAIL}\n")
            self.assertEqual(err.getvalue(), "")

    def test_c6_fixture(self):
        # Ignore decoys outside Jobs.finish; do not execute the fixture module.
        source = (f"raise RuntimeError('AST only')\n{COUNT} < 1\n"
                  + finish(f"{COUNT} < 2", f"{COUNT} <= 7")
                  + f"    def other(self):\n        return {COUNT} < 3\n")
        self.assertEqual(self.invoke_fixture(source), (0, LIVE, ""))

    def test_c7_live_pins(self):
        # The unpatched default must read the real source and pinned asset bytes.
        out, err = io.StringIO(), io.StringIO()
        with redirect_stdout(out), redirect_stderr(err):
            self.assertEqual(self.checker.main([]), 0)
        self.assertEqual(out.getvalue().splitlines(), LIVE)
        self.assertEqual(err.getvalue(), "")
