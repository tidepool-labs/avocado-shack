"""Contract tests for the offline S3 question-cap report."""

from contextlib import redirect_stderr, redirect_stdout
from dataclasses import replace
import importlib.util
import io
from pathlib import Path
import re
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import patch

from hass.npp.missing import MissingInfo


ROOT = Path(__file__).resolve().parents[2]
SCRIPT = ROOT / "scripts/hass/npp_question_cap_fit.py"
SPEC = importlib.util.spec_from_file_location("npp_question_cap_fit", SCRIPT)
assert SPEC is not None and SPEC.loader is not None
qcap = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(qcap)
PASS = "PASS npp_question_cap_fit"
FAIL = "FAIL npp_question_cap_fit"
ROW = re.compile(r"qcap (.+) questions=([0-9]+) chars=([0-9]+) ids=(-|\w+(?:,\w+)*)")


def run_main():
    out, err = io.StringIO(), io.StringIO()
    with redirect_stdout(out), redirect_stderr(err):
        code = qcap.main([])
    return subprocess.CompletedProcess([], code, out.getvalue(), err.getvalue())


def run_cli(*args):
    with tempfile.TemporaryDirectory() as cwd:
        return subprocess.run([sys.executable, "-B", str(SCRIPT), *args], cwd=cwd,
                              capture_output=True, text=True, timeout=10)


def snapshot():
    files = {}
    for tree in (ROOT / "hass", ROOT / "storefront-mockup"):
        for path in (tree, *tree.rglob("*")):
            stat = path.lstat()
            files[path.relative_to(ROOT)] = (stat.st_size, stat.st_mtime_ns)
    return files


def rows(result):
    return {m[1]: (int(m[2]), int(m[3]), m[4]) for line in result.stdout.splitlines()
            if (m := ROW.fullmatch(line))}


class QuestionCapFitTests(unittest.TestCase):
    def assert_trailer(self, result, code, trailer):
        self.assertEqual(result.returncode, code, result.stdout + result.stderr)
        self.assertEqual(result.stderr, "")
        self.assertEqual(result.stdout.splitlines()[-1], trailer)

    def assert_findings(self, result, *expected):
        self.assert_trailer(result, 1, FAIL)
        self.assertEqual([line for line in result.stdout.splitlines()[:-1]
                          if line.startswith("FAIL")], list(expected))

    def change_decisions(self, transform):
        # The real S3 runs first; alter its return only at the checker boundary
        # to exercise states the current S3 cap enforcement cannot return.
        original = MissingInfo.decide

        def decide(instance, **inputs):
            return transform(original(instance, **inputs), inputs)

        with patch.object(MissingInfo, "decide", decide):
            return run_main()

    def test_c1_full_pass(self):
        # A successful main() must propagate its zero status through the CLI.
        self.assert_trailer(run_cli(), 0, PASS)

    def test_c2_findings_trailer(self):
        # Multiple breaches must not be collapsed, reordered or end in PASS.
        def breaches(decision, inputs):
            if not inputs:
                return replace(decision, questions=(("identity", "x" * 160),) * 3)
            if inputs == {"owner_item": "Wildflower Honey"}:
                return replace(decision, questions=())
            return decision

        self.assert_findings(self.change_decisions(breaches), "FAIL over-count nothing",
                             "FAIL over-chars nothing", "FAIL silent-stall item-no-price")

    def test_c2_1_over_count(self):
        # The count check must catch a third short question independently of length.
        result = self.change_decisions(lambda d, args: d if args else replace(
            d, questions=(("identity", "x"),) * 3))
        self.assert_findings(result, "FAIL over-count nothing")

    def test_c2_2_over_chars(self):
        # Two sentences can exceed the cap by the single joining space alone.
        result = self.change_decisions(lambda d, args: d if args else replace(
            d, questions=(("identity", "é" * 80), ("selling_price", "x" * 80))))
        self.assert_findings(result, "FAIL over-chars nothing")
        self.assertEqual(rows(result)["nothing"], (2, 161, "identity,selling_price"))

    def test_c2_3_silent_stall(self):
        # No questions is not a pass while S3 still needs first-ask information.
        result = self.change_decisions(lambda d, args: d if args else replace(d, questions=()))
        self.assert_findings(result, "FAIL silent-stall nothing")
        self.assertEqual(rows(result)["nothing"], (0, 0, "-"))

    def test_c2_4_check_error(self):
        # Broken inputs/decisions must fail closed without exposing the exception.
        for target, attr in ((qcap.npp, "assets"), (qcap, "load_content"), (MissingInfo, "decide")):
            with self.subTest(boundary=attr), patch.object(
                target, attr, side_effect=ValueError("fixture exception details")
            ) as broken:
                result = run_main()
                broken.assert_called_once()
                self.assertEqual(result.stdout.splitlines(), ["FAIL check-error", FAIL])
                self.assert_findings(result, "FAIL check-error")

    def test_c3_usage_exit_2(self):
        # Stray arguments must not run an audit (even help or a bare separator).
        for arg in ("extra", "--unknown", "--help", "--"):
            with self.subTest(arg=arg):
                result = run_cli(arg)
                self.assertEqual(result.returncode, 2)
                self.assertEqual(result.stdout, "")  # no trailer on usage errors
                self.assertTrue(result.stderr.startswith("usage: "))
                self.assertIn("error:", result.stderr.splitlines()[-1])

    def test_c4_read_only(self):
        # No caches, artifacts or in-place rewrites in either repo input tree.
        before = snapshot()
        self.assert_trailer(run_cli(), 0, PASS)
        self.assertEqual(snapshot(), before)

    def test_c5_output_shape(self):
        # Incidental logs, empty rows or moving the summary violate the CLI grammar.
        result = run_main()
        self.assert_trailer(result, 0, PASS)
        lines = result.stdout.splitlines()
        self.assertRegex(lines[-2], r"\Aqcap near-max chars=[0-9]+\Z")
        self.assertEqual(len(rows(result)), len(lines) - 2)

    def test_c6_fixture(self):
        # Share the lower cap with real S3: it suppresses the long second ask,
        # but an exact-100 reply must still fit and the pins must not be changed.
        pins, files, replies = qcap.npp.assets()
        lowered = replies | {"caps": replies["caps"] | {"question_max_chars": 100}}
        with patch.object(qcap.npp, "assets", return_value=(pins, files, lowered)):
            result = run_main()
            # A future S3 regression might return a 101-character ask anyway.
            # The reporter must compare it to 100, not the original 160.
            oversize = self.change_decisions(lambda d, args: d if args else replace(
                d, questions=(("identity", "x" * 101),)))
        measured = rows(result)
        self.assertEqual((result.returncode, result.stdout.splitlines()[-1], result.stderr),
                         (0, PASS, ""))
        self.assertEqual([line for line in result.stdout.splitlines() if line.startswith("FAIL ")],
                         [f"FAIL over-chars {label}" for label, (_, chars, _) in measured.items()
                          if chars > 100])
        self.assertEqual(measured["near Stepladder"], (2, 100, "selling_price,near_maker"))
        self.assertEqual(measured["near Joebella / Avocado Shack"], (1, 53, "selling_price"))
        self.assert_findings(oversize, "FAIL over-chars nothing")
        self.assertEqual(rows(oversize)["nothing"], (1, 101, "identity"))
        restored = run_main()
        self.assert_trailer(restored, 0, PASS)
        self.assertEqual(rows(restored)["near Joebella / Avocado Shack"],
                         (2, 114, "selling_price,near_maker"))

    def test_c7_live_pins(self):
        # A capped decision can drop a second question yet look under budget;
        # pin the actual IDs across all makers, not just the maximum length.
        catalog = qcap.load_content(ROOT / "hass/content")
        makers = [key for key, maker in catalog.makers.items() if not maker.get("hidden")]
        self.assertEqual((len(catalog.active_products()), len(catalog.products),
                          len(makers), len(catalog.makers)), (170, 172, 26, 26))
        states = []
        original = MissingInfo.decide

        def record(instance, **inputs):
            decision = original(instance, **inputs)
            if inputs.get("owner_texts"):
                states.append((decision.maker.state, decision.maker.key))
            return decision

        with patch.object(MissingInfo, "decide", record):
            result = run_main()
        self.assert_trailer(result, 0, PASS)
        expected = {
            "nothing": (1, 71, "identity"),
            "item-no-price": (1, 53, "selling_price"),
            "price-no-unit": (1, 29, "price_unit"),
            "unit-no-price": (1, 25, "selling_price"),
            "dup-no-price": (2, 118, "selling_price,duplicate"),
            "dup-priced": (1, 64, "duplicate"),
        }
        measured = rows(result)
        self.assertEqual(list(measured), [*expected, *(f"near {key}" for key in makers)])
        for label, row in expected.items():
            self.assertEqual(measured[label], row, label)
        self.assertEqual(states, [("absent", None) if key == "Massa Organics" else ("near", key)
                                  for key in makers])
        for key in makers:
            count, _, ids = measured[f"near {key}"]
            wanted = (1, "selling_price") if key == "Massa Organics" else (2, "selling_price,near_maker")
            self.assertEqual((count, ids), wanted, key)
        self.assertEqual(max((measured[f"near {key}"][1], key) for key in makers),
                         (114, "Joebella / Avocado Shack"))
        self.assertEqual(result.stdout.splitlines()[-2], "qcap near-max chars=114")
