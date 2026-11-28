"""Offline CLI contract for the maker-site allowlist comparison."""

from contextlib import redirect_stderr, redirect_stdout
import importlib.util
import io
import json
from pathlib import Path
import subprocess
import sys
from tempfile import TemporaryDirectory
import unittest
from unittest.mock import patch


ROOT = Path(__file__).resolve().parents[2]
SCRIPT = ROOT / "scripts/hass/npp_allowlist_rule_parity.py"
PASS = "PASS npp_allowlist_rule_parity"
FAIL = "FAIL npp_allowlist_rule_parity"


def snapshot():
    result = {}
    for tree_name in ("hass", "storefront-mockup"):
        tree = ROOT / tree_name
        for path in (tree, *tree.rglob("*")):
            info = path.lstat()
            result[path.relative_to(ROOT)] = (info.st_size, info.st_mtime_ns)
    return result


class AllowlistRuleParityTests(unittest.TestCase):
    def setUp(self):
        scratch = TemporaryDirectory()
        self.addCleanup(scratch.cleanup)
        self.scratch = Path(scratch.name)
        spec = importlib.util.spec_from_file_location("allowlist_parity_fixture", SCRIPT)
        assert spec is not None and spec.loader is not None
        self.parity = importlib.util.module_from_spec(spec)
        with patch.object(sys, "path", sys.path.copy()):
            spec.loader.exec_module(self.parity)

    def cli(self, *args):
        return subprocess.run([sys.executable, "-B", str(SCRIPT), *args], cwd=self.scratch,
                              capture_output=True, text=True, timeout=15)

    def run_main(self, code, trailer):
        stdout, stderr = io.StringIO(), io.StringIO()
        with redirect_stdout(stdout), redirect_stderr(stderr):
            status = self.parity.main([])
        self.assertEqual(status, code, stdout.getvalue() + stderr.getvalue())
        self.assertEqual(stderr.getvalue(), "")
        lines = stdout.getvalue().splitlines()
        self.assertEqual(lines[-1], trailer)
        return lines

    def with_live_entries(self, *makers):
        pins, files, replies = self.parity.npp.assets()
        source = self.scratch / "sources.json"
        sources = json.loads(files[self.parity.SOURCES])
        entries = [dict(maker=maker, domain=f"fixture-{i}.example", added_by="G", reviewed_in="fixture-review")
                   for i, maker in enumerate(makers)]
        source.write_text(json.dumps({**sources, "allowlist": entries}), encoding="utf-8")
        pinned = pins, {**files, self.parity.SOURCES: source.read_bytes()}, replies
        return patch.object(self.parity.npp, "assets", return_value=pinned)

    def test_c1_full_pass(self):
        # A zero-finding run must not inherit the unpatched dual-domain failure status.
        # Two entries for the same domain leave both real selectors a single choice.
        cases = list(self.parity.CASES)
        cases[3] = [cases[3][0], cases[3][0].copy()]
        with patch.object(self.parity, "CASES", cases), self.with_live_entries():
            self.assertEqual(self.run_main(0, PASS), [
                "allowlist live_entries=0", "allowlist cases=8 disagree=0", PASS,
            ])

    def test_c2_findings_trailer(self):
        # An unfolded name plus the dual-domain mismatch still yields one final FAIL trailer.
        with self.with_live_entries("Etto Farm"):
            lines = self.run_main(1, FAIL)
        self.assertEqual(lines.count(FAIL), 1)
        self.assertEqual([line for line in lines[:-1] if line.startswith("FAIL ")],
                         ["FAIL live-entry-unfolded", "FAIL rule-disagree 3"])

    def test_c2_1_rule_disagree(self):
        # A stage silently returning no URL for a valid single entry adds index 0.
        original = self.parity.stages.ProductionStages._research

        def skip_single(port, *args):
            if port.sources["allowlist"] == self.parity.CASES[0]:
                return ()
            return original(port, *args)

        with patch.object(self.parity.stages.ProductionStages, "_research", skip_single), self.with_live_entries():
            lines = self.run_main(1, FAIL)
        self.assertEqual([line for line in lines if line.startswith("FAIL rule-disagree ")],
                         ["FAIL rule-disagree 0", "FAIL rule-disagree 3"])
        self.assertIn("allowlist cases=8 disagree=2", lines)

    def test_c2_2_live_entry_unfolded(self):
        # Checking lowercase alone accepts an accented maker that claims.fold changes.
        with self.with_live_entries("café farm", "cafe farm"):
            lines = self.run_main(1, FAIL)
        self.assertIn("allowlist live_entries=2", lines)
        self.assertEqual(lines.count("FAIL live-entry-unfolded"), 1)

    def test_c2_3_check_error(self):
        # Even repeated exceptions produce one text-free finding without skipping
        # later cases or counting an incomplete comparison as a disagreement.
        for module, method in ((self.parity.stages.ProductionStages, "_research"),
                               (self.parity.research, "research")):
            original = getattr(module, method)
            for failing_calls in (1, 2, 8):
                with self.subTest(method=method, failing_calls=failing_calls):
                    def raise_on_prefix(*args, **kwargs):
                        if recorder.call_count <= failing_calls:
                            raise RuntimeError("fixture exception detail")
                        return original(*args, **kwargs)

                    with patch.object(module, method, autospec=True, side_effect=raise_on_prefix) as recorder, self.with_live_entries():
                        lines = self.run_main(1, FAIL)
                    expected = ["allowlist live_entries=0", "FAIL check-error"]
                    if failing_calls == 8:
                        expected.append("allowlist cases=8 disagree=0")
                    else:
                        expected.extend(["FAIL rule-disagree 3", "allowlist cases=8 disagree=1"])
                    self.assertEqual(lines, [*expected, FAIL])
                    self.assertEqual(recorder.call_count, 8)

    def test_c3_usage_exit_2(self):
        # Reject positionals, unknown flags and argparse's otherwise implicit help flag.
        for argument in ("fixture", "--unknown", "--help", "--"):
            with self.subTest(argument=argument):
                result = self.cli(argument)
                self.assertEqual(result.returncode, 2)
                self.assertEqual(result.stdout, "")
                self.assertTrue(result.stderr.startswith("usage:"))
                self.assertEqual(result.stderr.splitlines()[-1],
                                 f"npp_allowlist_rule_parity: error: unrecognized arguments: {argument}")

    def test_c4_read_only(self):
        # Catch side effects such as caches or reports in either tree, even on a finding.
        before = snapshot()
        result = self.cli()
        self.assertEqual(result.returncode, 1, result.stderr)
        self.assertEqual(result.stdout.splitlines()[-1], FAIL)
        self.assertEqual(snapshot(), before)

    def test_c5_output_shape(self):
        # The closed output grammar disallows debug lines, URLs and exception details.
        result = self.cli()
        self.assertEqual(result.returncode, 1)
        self.assertEqual(result.stderr, "")
        for line in result.stdout.splitlines():
            self.assertRegex(line, r"^(?:allowlist live_entries=[0-9]+|allowlist cases=8 disagree=[0-8]|"
                                   r"FAIL (?:rule-disagree [0-7]|live-entry-unfolded|check-error)|"
                                   r"(?:PASS|FAIL) npp_allowlist_rule_parity)$")
        self.assertEqual(result.stdout.splitlines()[-1], FAIL)

    def test_c6_fixture(self):
        # Simulate stage-only loss of the reviewed_in guard, not a different URL algorithm.
        original = self.parity.stages.ProductionStages._research

        def ignore_review(port, *args):
            port.sources = {"allowlist": [{**entry, "reviewed_in": "fixture-review"}
                                         for entry in port.sources["allowlist"]]}
            return original(port, *args)

        with patch.object(self.parity.stages.ProductionStages, "_research", ignore_review), self.with_live_entries():
            lines = self.run_main(1, FAIL)
        self.assertEqual([line for line in lines if line.startswith("FAIL rule-disagree ")],
                         ["FAIL rule-disagree 2", "FAIL rule-disagree 3"])
        self.assertIn("allowlist cases=8 disagree=2", lines)

    def test_c7_live_pins(self):
        # Changes to the pinned asset count or the real comparison require re-measurement.
        result = self.cli()
        self.assertEqual(result.returncode, 1, result.stderr)
        self.assertEqual(result.stdout.splitlines(), [
            "allowlist live_entries=0", "FAIL rule-disagree 3", "allowlist cases=8 disagree=1", FAIL,
        ])


if __name__ == "__main__":
    unittest.main()
