"""Offline contract tests for the stage name drift CLI."""

from contextlib import redirect_stderr, redirect_stdout
import importlib.util
import io
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest

SCRIPT = Path(__file__).resolve().parents[2] / "scripts/hass/stage_name_drift.py"
SPEC = importlib.util.spec_from_file_location("stage_name_drift", SCRIPT)
assert SPEC is not None and SPEC.loader is not None
DRIFT = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(DRIFT)
PASS = "PASS stage_name_drift"
FAIL = "FAIL stage_name_drift"


class StageNameDriftTests(unittest.TestCase):
    def setUp(self):
        temporary = tempfile.TemporaryDirectory()
        self.addCleanup(temporary.cleanup)
        self.root = Path(temporary.name).resolve() / "source-tree"
        self.write("hass/a.py", "self.stage('accepted', x)\n")
        self.write("mac/b.py", "stage('sent', y)\n")

    def write(self, relative, text):
        path = self.root / relative
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(text, encoding="utf-8")
        return path

    def invoke(self, root=None):
        stdout, stderr = io.StringIO(), io.StringIO()
        with redirect_stdout(stdout), redirect_stderr(stderr):
            status = DRIFT.main(["--root", str(self.root if root is None else root)])
        return status, stdout.getvalue(), stderr.getvalue()

    def cli(self, *args):
        result = subprocess.run([sys.executable, "-B", str(SCRIPT), *args],
                                cwd=self.root, capture_output=True, text=True, timeout=15)
        return result.returncode, result.stdout, result.stderr

    def assert_result(self, result, code, trailer):
        status, stdout, stderr = result
        self.assertEqual(status, code)
        self.assertEqual(stderr, "")
        lines = stdout.splitlines()
        self.assertEqual(lines[-1:], [trailer])
        return lines[:-1]

    def test_c1_full_pass(self):
        # Missing ORDER entries are notes; they must not flip the pass status.
        lines = self.assert_result(self.invoke(), 0, PASS)
        self.assertFalse(any(line.startswith("FAIL ") for line in lines))
        notes = [line for line in lines if line.startswith("note ")]
        self.assertEqual(len(notes), 22)
        self.assertEqual(notes[:2], ["note order-not-recorded webhook-in", "note order-not-recorded ack-start"])
        self.assertEqual(notes[-1], "note order-not-recorded bb-send-end")

    def test_c2_findings_trailer(self):
        # Findings must accumulate rather than returning on the first error.
        self.write("hass/a.py", "def\n")
        self.write("mac/b.py", "stage('unlisted-stage', y)\n")
        lines = self.assert_result(self.invoke(), 1, FAIL)
        self.assertEqual([line for line in lines if line.startswith("FAIL ")],
                         ["FAIL source-unreadable", "FAIL stage-not-in-order unlisted-stage"])

    def test_c2_1_unsafe_input(self):
        # Path normalization must not turn a link into a permitted root.
        link = self.root / "link"
        link.symlink_to(self.root, target_is_directory=True)
        for root in (link, self.root / "hass/a.py", self.root / "absent"):
            with self.subTest(root=root.name):
                self.assertEqual(self.assert_result(self.invoke(root), 1, FAIL), ["FAIL unsafe-input"])

    def test_c2_2_source_too_large(self):
        # Over-limit sources each fail before parsing; exactly 1 MiB is allowed.
        size = 1024 * 1024
        self.write("hass/b.py", "#" * size + "\n")
        self.write("mac/c.py", "!" * (size + 1))
        self.write("mac/d.py", "#" * (size - 1) + "\n")
        lines = self.assert_result(self.invoke(), 1, FAIL)
        self.assertEqual([line for line in lines if line.startswith("FAIL ")], ["FAIL source-too-large"] * 2)

    def test_c2_3_source_unreadable(self):
        # Broken syntax and invalid encoding each fail once without stopping the scan.
        self.write("hass/a.py", "class\n")
        path = self.write("hass/b.py", "")
        path.write_bytes(b"\xff\n")
        lines = self.assert_result(self.invoke(), 1, FAIL)
        self.assertEqual([line for line in lines if line.startswith("FAIL ")], ["FAIL source-unreadable"] * 2)
        self.assertIn("stages-recorded 1", lines)

    def test_c2_4_stage_not_in_order(self):
        # Repeated calls and file ordering must not duplicate or reorder findings.
        self.write("hass/z/nested.py", "item.stage('zeta', x)\nstage('alpha', y)\nstage('zeta', y)\n")
        lines = self.assert_result(self.invoke(), 1, FAIL)
        self.assertEqual([line for line in lines if line.startswith("FAIL ")],
                         ["FAIL stage-not-in-order alpha", "FAIL stage-not-in-order zeta"])

    def test_c2_5_stage_name_invalid(self):
        # Full matching must reject newline suffixes, bad starts, and overlong names.
        invalid = ("accepted\n", "0started", "a" * 41)
        self.write("hass/b.py", "".join(f"stage({name!r}, x)\n" for name in (*invalid, invalid[0])))
        lines = self.assert_result(self.invoke(), 1, FAIL)
        self.assertEqual([line for line in lines if line.startswith("FAIL ")], ["FAIL stage-name-invalid"] * 3)

    def test_c3_usage_exit_2(self):
        # CLI syntax errors must not masquerade as scanner findings.
        for args in (("--root",), ("--unknown", str(self.root))):
            with self.subTest(flag=args[0]):
                status, stdout, stderr = self.cli(*args)
                self.assertEqual(status, 2)
                self.assertEqual(stdout, "")  # No stdout trailer on usage errors.
                self.assertTrue(stderr.startswith("usage: "))
                self.assertNotIn(str(self.root), stderr)

    def test_c4_read_only(self):
        # Accidental source execution or cache writes alter the tree snapshot.
        self.write("hass/no_run.py", "raise RuntimeError('not to be imported')\n")

        def snapshot():
            return {p.relative_to(self.root): (p.read_bytes(), p.stat().st_mtime_ns) if p.is_file() else None
                    for p in self.root.rglob("*")}

        before = snapshot()
        self.assert_result(self.cli("--root", str(self.root)), 0, PASS)
        self.assertEqual(snapshot(), before)

    def test_c5_no_private_values(self):
        # Echoing parser warnings, syntax exceptions or invalid labels leaks input.
        invalid = "SYNTHETIC Stage Canary"
        comment = "SYNTHETIC_COMMENT_CANARY"
        bad = self.write("hass/bad.py", f"def  # {comment}\n")
        self.write("mac/b.py", f"stage({invalid!r}, y)\n'\\q'  # {comment}\n")
        result = self.invoke()
        lines = self.assert_result(result, 1, FAIL)
        self.assertIn("FAIL stage-name-invalid", lines)
        self.assertIn("FAIL source-unreadable", lines)
        for canary in (invalid, comment, str(self.root), str(bad)):
            self.assertNotIn(canary, result[1] + result[2])

    def test_c6_fixture_pass(self):
        # Scan both roots, but never descend into hass/tests or follow links.
        self.write("hass/tests/ignored.py", "stage('only-in-tests', x)\n")
        self.write("mac/nested/ignored.txt", "stage('not-python', x)\n")
        self.write("detour/target.py", "stage('link-target', x)\n")
        (self.root / "hass/alias.py").symlink_to(self.root / "detour/target.py")
        (self.root / "mac/detour").symlink_to(self.root / "detour", target_is_directory=True)
        self.write("mac/b.py", "stage('sent', y)\nstage(prefix, x)\nstage(1, x)\n"
                   "stage()\nother('not-stage', x)\nstage(stage='not-positional')\n")
        lines = self.assert_result(self.invoke(), 0, PASS)
        self.assertEqual(lines[:4], ["files 2", "skipped 2", "stages-recorded 2", "order 24"])
        self.assertNotIn("note order-not-recorded sent", lines)
        self.assertNotIn("note order-not-recorded accepted", lines)

    def test_c7_unknown_stage(self):
        # A newly recorded valid name must be visible, not silently discarded.
        self.write("hass/a.py", "self.stage('accepted', x)\nstage('made-up-stage', x)\n")
        lines = self.assert_result(self.invoke(), 1, FAIL)
        self.assertEqual([line for line in lines if line.startswith("FAIL ")], ["FAIL stage-not-in-order made-up-stage"])

    def test_c8_live_drift(self):
        # Default root is the checkout, even when launched from somewhere else.
        lines = self.assert_result(self.cli(), 1, FAIL)
        self.assertEqual(lines, ["files 165", "skipped 0", "stages-recorded 25", "order 24",
                                 "note order-not-recorded sent", "FAIL stage-not-in-order g-send-failed",
                                 "FAIL stage-not-in-order owner-send-failed"])
