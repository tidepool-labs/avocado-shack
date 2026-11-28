"""Offline CLI contract for comparing NPP stage reserves and pins."""

from contextlib import redirect_stderr, redirect_stdout
import hashlib
import importlib.util
import io
import json
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import patch

import hass.npp as npp


REPO = Path(__file__).resolve().parents[2]
SCRIPT = REPO / "scripts/hass/npp_stage_time_budgets.py"
PASS = "PASS npp_stage_time_budgets"
FAIL = "FAIL npp_stage_time_budgets"
LIVE_BUDGETS = [
    "budget research pin=40 sources=40",
    "budget slack code=26 pinned=26",
    "budget cap pin=100 guard=100",
    "budget polish timeout=90 hard=75",
]
STAGES_TEXT = """\
class ProductionStages:
    def _research(self, work):
        return self._remaining(work) - self.pinned[0]['steps']['copy_select']['timeout_s'] - 10

    def _picture(self, work):
        return min(self._remaining(work) - 26, 75)

    def render_listing(self, work):
        return None if self._remaining(work) < 26 else self.selector
"""
GUARD_TEXT = """\
def assets():
    if pins['segment']['cap_s'] != 100:
        raise ValueError('invalid NPP segment cap')
"""


def snapshot():
    result = {}
    for name in ("hass", "storefront-mockup"):
        root = REPO / name
        for path in (root, *root.rglob("*")):
            stat = path.lstat()
            result[path.relative_to(REPO)] = (stat.st_size, stat.st_mtime_ns)
    return result


class NppStageTimeBudgetsTests(unittest.TestCase):
    def setUp(self):
        temporary = tempfile.TemporaryDirectory()
        self.addCleanup(temporary.cleanup)
        self.root = Path(temporary.name)
        spec = importlib.util.spec_from_file_location("npp_stage_time_budgets", SCRIPT)
        assert spec is not None and spec.loader is not None
        self.tool = importlib.util.module_from_spec(spec)
        with patch.object(sys, "path", sys.path.copy()):
            spec.loader.exec_module(self.tool)

    def fixture(self, *, pin=40, sources=40, copy_timeout=16, cap=100,
                stages=STAGES_TEXT, guard=GUARD_TEXT):
        folder = self.root / "hass/npp"
        folder.mkdir(parents=True, exist_ok=True)
        if stages is not None:
            (folder / "stages.py").write_text(stages, encoding="utf-8")
        (folder / "__init__.py").write_text(guard, encoding="utf-8")
        setattr(self.tool, "REPO", self.root)
        pins = {"steps": {"research_extract": {"stage_budget_s": pin},
                          "copy_select": {"timeout_s": copy_timeout},
                          "picture": {"hard_s": 75}}, "segment": {"cap_s": cap}}
        files = {"hass-maker-research/sources.json":
                 json.dumps({"fetch": {"stage_budget_seconds": sources}}).encode()}
        return pins, files, {}

    def invoke(self):
        out, err = io.StringIO(), io.StringIO()
        with redirect_stdout(out), redirect_stderr(err):
            code = self.tool.main([])
        return code, out.getvalue(), err.getvalue()

    def run_fixture(self, **kwargs):
        with patch.object(npp, "assets", return_value=self.fixture(**kwargs)):
            return self.invoke()

    def cli(self, *args):
        result = subprocess.run([sys.executable, "-B", str(SCRIPT), *args],
                                cwd=self.root, capture_output=True, text=True, timeout=10)
        return result.returncode, result.stdout, result.stderr

    def assert_report(self, result, expected_code, *findings):
        code, out, err = result
        self.assertEqual(code, expected_code)
        self.assertEqual(err, "")
        lines = out.splitlines()
        self.assertEqual(lines[-1:], [PASS if expected_code == 0 else FAIL])
        self.assertEqual([line for line in lines[:-1] if line.startswith("FAIL ")],
                         [f"FAIL {reason}" for reason in findings])
        return lines

    def test_c1_full_pass(self):
        # A healthy synthetic card budget must not be refused just because values moved.
        self.assert_report(self.run_fixture(pin=42, sources=42), 0)

    def test_c2_findings_trailer(self):
        # A first-failure return would lose the other findings and their order.
        self.assert_report(self.run_fixture(pin=75, sources=74, copy_timeout=17, cap=99), 1,
                           "research-budget-drift", "slack-drift", "cap-guard-drift", "budget-overrun")

    def test_c2_1_research_budget_drift(self):
        # Editing only the effective sources budget must be caught too.
        self.assert_report(self.run_fixture(sources=39), 1, "research-budget-drift")

    def test_c2_2_slack_drift(self):
        # Each reserve, the research allowance and the timeout must matter independently.
        for changes in (
            {"stages": STAGES_TEXT.replace("- 26", "- 25")},
            {"stages": STAGES_TEXT.replace("< 26", "< 25")},
            {"stages": STAGES_TEXT.replace("- 10", "- 11")},
            {"copy_timeout": 15},
        ):
            with self.subTest(changes=changes):
                self.assert_report(self.run_fixture(**changes), 1, "slack-drift")

    def test_c2_3_cap_guard_drift(self):
        # Read the guard literal, not a baked-in 100, and classify the real loader's refusal.
        self.assert_report(self.run_fixture(guard=GUARD_TEXT.replace("100", "101")), 1,
                           "cap-guard-drift")
        pins, files, _ = self.fixture(cap=99)
        files[npp.REPLIES] = b"{}"
        pins["assets"] = {name: hashlib.sha256(data).hexdigest() for name, data in files.items()}
        folder = self.root / "hass/npp"
        (folder / "pins.json").write_text(json.dumps(pins), encoding="utf-8")
        for name, data in files.items():
            path = folder / "assets" / name
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_bytes(data)
        with patch.object(npp, "ROOT", folder):
            self.assert_report(self.invoke(), 1, "cap-guard-drift")

    def test_c2_4_budget_overrun(self):
        # The sum must count the full reserve, and equality with the cap is allowed.
        self.assert_report(self.run_fixture(pin=74, sources=74), 0)
        self.assert_report(self.run_fixture(pin=75, sources=75), 1, "budget-overrun")
        self.assert_report(self.run_fixture(pin=74, sources=75), 1,
                           "research-budget-drift", "budget-overrun")

    def test_c2_5_constant_not_found(self):
        # Picking the first match or accepting bool as int can hide ambiguous/missing code.
        for changes, file in (
            ({"stages": STAGES_TEXT.replace("< 26", "< True")}, "hass/npp/stages.py"),
            ({"stages": STAGES_TEXT.replace("- 10", "")}, "hass/npp/stages.py"),
            ({"stages": STAGES_TEXT.replace("min(self._remaining(work) - 26, 75)",
                                           "min(self._remaining(work) - 26, self._remaining(work) - 25)")},
             "hass/npp/stages.py"),
            ({"guard": GUARD_TEXT + GUARD_TEXT}, "hass/npp/__init__.py"),
            ({"guard": "def assets():\n    pass\n"}, "hass/npp/__init__.py"),
        ):
            with self.subTest(changes=changes):
                self.assert_report(self.run_fixture(**changes), 1, f"constant-not-found {file}")

    def test_c2_6_parse_error(self):
        # File I/O and invalid Python/JSON must not become tracebacks or a silent skip.
        self.assert_report(self.run_fixture(stages=None), 1, "parse-error")
        self.assert_report(self.run_fixture(guard="def assets(:\n"), 1, "parse-error")
        pins, files, replies = self.fixture()
        files["hass-maker-research/sources.json"] = b"{"
        with patch.object(npp, "assets", return_value=(pins, files, replies)):
            self.assert_report(self.invoke(), 1, "parse-error")

    def test_c3_usage_exit_2(self):
        # Even help flags and a bare end-of-options marker are outside this interface.
        for arg in ("extra", "--unknown", "-h", "--help", "--"):
            with self.subTest(arg=arg):
                code, out, err = self.cli(arg)
                self.assertEqual(code, 2)
                self.assertEqual(out.splitlines(), [])  # no stdout trailer for argparse errors
                self.assertTrue(err.startswith("usage:"))
                self.assertIn("error:", err.splitlines()[-1])

    def test_c4_read_only(self):
        # A cache or refreshed artifact would change a path, size or mtime in these trees.
        before = snapshot()
        self.assert_report(self.cli(), 0)
        self.assertEqual(snapshot(), before)

    def test_c5_output_shape(self):
        # Refuse debug noise and reordering even on a run with additive findings.
        result = self.run_fixture(sources=41, cap=99)
        self.assert_report(result, 1, "research-budget-drift", "cap-guard-drift")
        self.assertEqual(result[1], "\n".join([
            "budget research pin=40 sources=41",
            "budget slack code=26 pinned=26",
            "budget cap pin=99 guard=100",
            "budget polish timeout=90 hard=75",
            "FAIL research-budget-drift", "FAIL cap-guard-drift", FAIL, "",
        ]))

    def test_c6_fixture(self):
        # Replace just the nominated pin, leaving live sources and the source sites intact.
        pins, files, replies = npp.assets()
        pins["steps"]["research_extract"]["stage_budget_s"] = 41
        with patch.object(npp, "assets", return_value=(pins, files, replies)):
            lines = self.assert_report(self.invoke(), 1, "research-budget-drift")
        self.assertEqual(lines[0], "budget research pin=41 sources=40")

    def test_c7_live_pins(self):
        # No asset mocks: catch real repository drift, but do not treat polish as a finding.
        result = self.cli()
        self.assert_report(result, 0)
        self.assertEqual(result[1], "\n".join([*LIVE_BUDGETS, PASS, ""]))


if __name__ == "__main__":
    unittest.main()
