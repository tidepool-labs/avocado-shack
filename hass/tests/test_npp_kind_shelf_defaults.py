"""Offline CLI contract tests for the NPP kind/shelf/default drift guard."""

from contextlib import contextmanager, redirect_stderr, redirect_stdout
import importlib.util
import io
import json
from pathlib import Path
import subprocess
import sys
from tempfile import TemporaryDirectory
import unittest
from unittest.mock import patch

from hass import content_model, npp
from hass.npp import copy

ROOT = Path(__file__).resolve().parents[2]
SCRIPT = ROOT / "scripts/hass/npp_kind_shelf_defaults.py"
MISSING = "hass-missing-info/missing-info.json"
COPY = "hass-listing-copy/copy-templates.json"
PASS = "PASS npp_kind_shelf_defaults"
FAIL = "FAIL npp_kind_shelf_defaults"
KIND_LINE = ("kinds identify=drink,food,fresh,non-food defaults=drink,food,fresh,non-food "
             "copy=drink,food,fresh,non-food")
SPEC = importlib.util.spec_from_file_location(SCRIPT.stem, SCRIPT)
assert SPEC is not None and SPEC.loader is not None
CHECK = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(CHECK)


class KindShelfDefaultsTests(unittest.TestCase):
    def cli(self, *args, cwd=None):
        return subprocess.run([sys.executable, "-B", str(SCRIPT), *args],
                              cwd=cwd, capture_output=True, text=True, timeout=10)

    def in_process(self):
        stdout, stderr = io.StringIO(), io.StringIO()
        with redirect_stdout(stdout), redirect_stderr(stderr):
            code = CHECK.main([])
        return subprocess.CompletedProcess([], code, stdout.getvalue(), stderr.getvalue())

    @contextmanager
    def fixture(self, name, edit):
        pins, files, replies = npp.assets()
        document = json.loads(files[name])
        edit(document)
        with TemporaryDirectory() as directory:
            path = Path(directory) / Path(name).name
            path.write_text(json.dumps(document), encoding="utf-8")
            # Substitute only the checked-byte payload; never edit the asset or its pin.
            with patch.object(npp, "assets", return_value=(pins, {**files, name: path.read_bytes()}, replies)):
                yield

    def assert_result(self, result, code, trailer, *findings):
        self.assertEqual(result.returncode, code, result.stderr or result.stdout)
        self.assertEqual(result.stderr, "")
        lines = result.stdout.splitlines()
        self.assertEqual(lines[-1:], [trailer])
        self.assertEqual([line for line in lines[:-1] if line.startswith("FAIL ")], list(findings))
        return lines

    def test_c1_full_pass(self):
        # Invocation by path must work even when the repository is not the cwd.
        with TemporaryDirectory() as directory:
            self.assert_result(self.cli(cwd=directory), 0, PASS)

    def test_c2_findings_trailer(self):
        # Multiple findings are retained, and the process-facing exit must not be 0.
        def edit(doc):
            doc["defaults"]["description"]["food"].extend(["fixture-missing", "desc-drink-default"])
        with self.fixture(COPY, edit):
            self.assert_result(self.in_process(), 1, FAIL, "FAIL rung-missing food fixture-missing",
                               "FAIL rung-ineligible food desc-drink-default")

    def test_c2_1_kind_sets_differ(self):
        # A newly rejected kind must be noticed even when both JSON lists agree.
        write = copy.Writer.write

        def narrowed(writer, ctx, select):
            if ctx.kind != "drink":
                return write(writer, ctx, select)

        with patch.object(copy.Writer, "write", autospec=True, side_effect=narrowed) as probe:
            lines = self.assert_result(self.in_process(), 1, FAIL, "FAIL kind-sets-differ")
        self.assertEqual(lines[0], KIND_LINE.replace("copy=drink,", "copy="))
        self.assertEqual([(call.args[1].kind, call.args[1].category) for call in probe.call_args_list], [
            ("drink", "drinks"), ("food", "pantry"), ("fresh", "fruit"),
            ("non-food", "general"), ("tool", "pantry"),
        ])

    def test_c2_2_shelf_unknown(self):
        # An unknown default shelf both trips the website check and blocks Writer's callback.
        with self.fixture(MISSING, lambda doc: doc["kind_default_category"].update(drink="fixture-shelf")):
            self.assert_result(self.in_process(), 1, FAIL, "FAIL kind-sets-differ", "FAIL shelf-unknown drink")
        # Dropping a shelf from the canonical site vocabulary must not be masked by a local list.
        shelves = tuple(shelf for shelf in content_model.CATEGORIES if shelf != "drinks")
        with patch.object(content_model, "CATEGORIES", shelves):
            self.assert_result(self.in_process(), 1, FAIL, "FAIL shelf-unknown drink")

    def test_c2_3_rung_missing(self):
        # Existence alone is insufficient: a valid template for another field is unusable.
        def edit(doc):
            doc["defaults"]["description"]["food"] = ["fixture-missing", "desc-food-default"]
            next(row for row in doc["templates"] if row["id"] == "desc-food-default")["field"] = "name"
        with self.fixture(COPY, edit):
            lines = self.assert_result(self.in_process(), 1, FAIL, "FAIL rung-missing food fixture-missing",
                                       "FAIL rung-missing food desc-food-default")
        self.assertIn("kind food shelf=pantry rungs=0/2", lines)

    def test_c2_4_rung_ineligible(self):
        # Kind-only eligibility would miss both flower placement and raw-variant drift.
        def edit(doc):
            doc["defaults"]["description"]["flowers"][0] = "desc-fresh-default"
            next(row for row in doc["templates"] if row["id"] == "desc-food-default")["variants"] = ["house"]
        with self.fixture(COPY, edit):
            lines = self.assert_result(self.in_process(), 1, FAIL, "FAIL rung-ineligible flowers desc-fresh-default",
                                       "FAIL rung-ineligible food desc-food-default")
        self.assertIn("kind flowers shelf=flowers rungs=1/2", lines)
        self.assertIn("kind food shelf=pantry rungs=1/2", lines)

    def test_c2_5_check_error(self):
        # A read exception is neither a traceback nor a successful empty check.
        with patch.object(npp, "assets", side_effect=OSError("fixture read failed")):
            lines = self.assert_result(self.in_process(), 1, FAIL, "FAIL check-error")
        self.assertEqual(lines, ["FAIL check-error", FAIL])
        # No listed rung means no default description, not vacuous eligibility.
        for edit in (lambda rows: rows.pop("flowers"), lambda rows: rows.update(food=[])):
            with self.fixture(COPY, lambda doc: edit(doc["defaults"]["description"])):
                self.assert_result(self.in_process(), 1, FAIL, "FAIL check-error")

    def test_c3_usage_exit_2(self):
        # argparse's implicit help and end-of-options behavior must not bypass no-args enforcement.
        for arg in ("fixture", "--unknown", "--help", "--"):
            with self.subTest(arg=arg):
                result = self.cli(arg)
                self.assertEqual(result.returncode, 2)
                self.assertEqual(result.stdout, "")
                self.assertTrue(result.stderr.startswith("usage:"), result.stderr)

    def test_c4_read_only(self):
        # A checker that materializes or rewrites projections must fail this snapshot.
        def snapshot():
            result = {}
            for tree in (ROOT / "hass", ROOT / "storefront-mockup"):
                for path in (tree, *tree.rglob("*")):
                    stat = path.lstat()
                    result[path.relative_to(ROOT)] = (stat.st_size, stat.st_mtime_ns)
            return result
        before = snapshot()
        with TemporaryDirectory() as directory:
            self.assert_result(self.cli(cwd=directory), 0, PASS)
        self.assertEqual(snapshot(), before)

    def test_c5_output_shape(self):
        # Debug output or printing raw asset text would break the line protocol.
        for broken in (False, True):
            with self.subTest(broken=broken):
                if broken:
                    def edit(doc):
                        doc["defaults"]["description"]["food"][0] = "fixture-missing"
                    with self.fixture(COPY, edit):
                        lines = self.assert_result(self.in_process(), 1, FAIL, "FAIL rung-missing food fixture-missing")
                else:
                    lines = self.assert_result(self.cli(), 0, PASS)
                self.assertRegex(lines[0], r"^kinds identify=[a-z,-]+ defaults=[a-z,-]+ copy=[a-z,-]+$")
                for line in lines[1:-1 - int(broken)]:
                    self.assertRegex(line, r"^kind [a-z-]+ shelf=[a-z-]+ rungs=\d+/\d+$")

    def test_c6_fixture(self):
        # An identify kind with no default shelf can't be hidden by skipping it.
        with self.fixture(MISSING, lambda doc: doc["kind_default_category"].pop("fresh")):
            lines = self.assert_result(self.in_process(), 1, FAIL, "FAIL kind-sets-differ")
        self.assertEqual(lines[0], "kinds identify=drink,food,fresh,non-food defaults=drink,food,non-food "
                                   "copy=drink,food,non-food")
        self.assert_result(self.in_process(), 0, PASS)

    def test_c7_live_pins(self):
        # With no replacement assets, both the summary and the measured fallback IDs stay pinned.
        lines = self.assert_result(self.cli(), 0, PASS)
        self.assertEqual(lines, [KIND_LINE, "kind drink shelf=drinks rungs=2/2", "kind flowers shelf=flowers rungs=2/2",
                                 "kind food shelf=pantry rungs=2/2", "kind fresh shelf=fruit rungs=2/2",
                                 "kind non-food shelf=general rungs=2/2", PASS])
        _, files, _ = npp.assets()
        self.assertEqual(json.loads(files[COPY])["defaults"]["description"], {
            "drink": ["desc-drink-default", "desc-default-short"],
            "flowers": ["desc-flowers-default", "desc-default-short"],
            "food": ["desc-food-default", "desc-default-short"],
            "fresh": ["desc-fresh-default", "desc-default-short"],
            "non-food": ["desc-nonfood-default", "desc-default-short"],
        })
