"""Offline CLI contract for the NPP one-option drift check."""

from contextlib import redirect_stderr, redirect_stdout
import importlib.util
import io
from pathlib import Path
import subprocess
import sys
import unittest
from unittest.mock import patch

from hass.skills import openreq


ROOT = Path(__file__).resolve().parents[2]
SCRIPT = ROOT / "scripts/hass/npp_pick_one_option.py"
PASS = "PASS npp_pick_one_option"
FAIL = "FAIL npp_pick_one_option"
LIVE_LINES = (
    "case 0 pick='p-honey-2'",
    "case 1 pick='p-honey-2'",
    "case 2 pick='p-jam-1'",
    "case 3 pick='p-honey-2'",
    "case 4 pick=None",
    "case 5 pick=None",
    "case 6 pick=None",
    "case 7 pick=None",
    "case 8 pick=None",
    "case 9 pick=None",
    "case 10 pick=None",
    "case 11 pick=None",
)


def _first_word(text):
    return [w for w in (text or '').lower().split() if w not in openreq.FILLER][:1]


def _snapshot():
    snapshot = {}
    for name in ("hass", "storefront-mockup"):
        tree = ROOT / name
        for path in (tree, *tree.rglob("*")):
            stat = path.lstat()
            snapshot[path.relative_to(ROOT)] = (stat.st_size, stat.st_mtime_ns)
    return snapshot


class NppPickOneOptionTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        spec = importlib.util.spec_from_file_location("npp_pick_one_option", SCRIPT)
        if spec is None or spec.loader is None:
            raise ImportError("could not load npp_pick_one_option")
        cls.tool = importlib.util.module_from_spec(spec)
        with patch.object(sys, "path", sys.path.copy()):
            spec.loader.exec_module(cls.tool)

    def _cli(self, *args):
        return subprocess.run(
            [sys.executable, "-B", str(SCRIPT), *args], cwd=SCRIPT.parent,
            capture_output=True, text=True, timeout=10,
        )

    def _run(self, code, trailer):
        out, err = io.StringIO(), io.StringIO()
        with redirect_stdout(out), redirect_stderr(err):
            result = self.tool.main([])
        self.assertEqual(result, code)
        self.assertEqual(err.getvalue(), "")
        lines = out.getvalue().splitlines()
        self.assertEqual(lines[-1:], [trailer])
        return lines[:-1]

    def test_c1_full_pass(self):
        # A clean run must not be reported as a failure by the CLI.
        result = self._cli()
        self.assertEqual(result.returncode, 0)
        self.assertEqual(result.stdout.splitlines()[-1:], [PASS])

    def test_c2_findings_trailer(self):
        # Batching findings at the end or reversing the two for case 9 fails.
        with patch.object(openreq, "_tokens", _first_word):
            lines = self._run(1, FAIL)
        self.assertEqual(lines, [
            *LIVE_LINES[:2], "case 2 pick=None", "FAIL pick-changed 2",
            *LIVE_LINES[3:9], "case 9 pick='p-honey-1'",
            "FAIL unclear-pick-chosen 9", "FAIL pick-changed 9", *LIVE_LINES[10:],
        ])

    def test_c2_1_unclear_pick_chosen(self):
        # Reporting only pin drift would hide the unsafe pick classification.
        with patch.object(openreq, "_tokens", _first_word):
            lines = self._run(1, FAIL)
        self.assertEqual([line for line in lines if line.startswith("FAIL ")], [
            "FAIL pick-changed 2", "FAIL unclear-pick-chosen 9", "FAIL pick-changed 9",
        ])

    def test_c2_2_pick_changed(self):
        # A check of MUST_NONE alone misses the loss of a valid ordinal pick.
        with patch.object(openreq, "ORDINALS", {}):
            lines = self._run(1, FAIL)
        self.assertEqual(lines, [
            LIVE_LINES[0], "case 1 pick=None", "FAIL pick-changed 1", *LIVE_LINES[2:],
        ])

    def test_c2_3_check_error(self):
        # A late exception must be sanitized and stop the loop, not skip a case.
        pick = openreq.pick_candidate

        def fail_on_second(text, ask):
            if text == "the second one":
                raise RuntimeError("synthetic internal detail")
            return pick(text, ask)

        with patch.object(openreq, "pick_candidate", side_effect=fail_on_second) as call:
            lines = self._run(1, FAIL)
        self.assertEqual(call.call_count, 2)
        self.assertEqual(lines, [LIVE_LINES[0], "FAIL check-error"])

    def test_c3_usage_exit_2(self):
        # Ignoring argv or enabling argparse's default help breaks no-argument use.
        for arg in ("extra", "--unknown", "-h", "--help", "--"):
            with self.subTest(arg=arg):
                result = self._cli(arg)
                self.assertEqual(result.returncode, 2)
                self.assertEqual(result.stdout, "")
                self.assertEqual(result.stderr.splitlines()[-1:], [
                    f"{SCRIPT.name}: error: unrecognized arguments: {arg}",
                ])

    def test_c4_read_only(self):
        # A cache or report written into either tree would change its snapshot.
        before = _snapshot()
        result = self._cli()
        self.assertEqual(result.returncode, 0)
        self.assertEqual(result.stdout.splitlines()[-1:], [PASS])
        self.assertEqual(_snapshot(), before)

    def test_c5_output_shape(self):
        # A banner, debug line, or stderr diagnostic would break report consumers.
        result = self._cli()
        self.assertEqual(result.returncode, 0)
        self.assertEqual(result.stderr, "")
        lines = result.stdout.splitlines()
        self.assertEqual(lines[-1:], [PASS])
        for line in lines[:-1]:
            self.assertRegex(line, r"^case (?:[0-9]|1[01]) pick=(?:None|'[^']+')$")

    def test_c6_fixture(self):
        # Clearing the ordinal mapping should change exactly one case, not numeric picks.
        with patch.object(openreq, "ORDINALS", {}):
            lines = self._run(1, FAIL)
        self.assertEqual([line for line in lines if line.startswith("FAIL ")], [
            "FAIL pick-changed 1",
        ])

    def test_c7_live_pins(self):
        # A baked transcript or a skipped repo call is not a live pin check.
        with patch.object(openreq, "pick_candidate", wraps=openreq.pick_candidate) as pick:
            lines = self._run(0, PASS)
        self.assertEqual([call.args for call in pick.call_args_list], self.tool.CASES)
        self.assertEqual(lines, list(LIVE_LINES))


if __name__ == "__main__":
    unittest.main()
