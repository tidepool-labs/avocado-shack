"""Exercise the offline model-step drift report without calling a mapper or model."""

from contextlib import redirect_stderr, redirect_stdout
import importlib.util
import io
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import patch

from hass import npp, photo_polish

ROOT = Path(__file__).resolve().parents[2]
SCRIPT = ROOT / "scripts/hass/npp_model_step_defaults.py"
PASS = "PASS npp_model_step_defaults"
FAIL = "FAIL npp_model_step_defaults"
DEFAULT = "step = step or {'model': 'fixture-edit', 'effort': 'low', 'timeout_s': 8}"
MAPPER = f"def codex_mapper(transport=None, step=None):\n    {DEFAULT}\n"
PICTURE_LINE = "step picture code=fixture-picture pinned=fixture-picture"


class ModelStepDefaultsTests(unittest.TestCase):
    def setUp(self):
        tmp = tempfile.TemporaryDirectory(dir=ROOT)
        self.addCleanup(tmp.cleanup)
        self.tmp = Path(tmp.name)
        spec = importlib.util.spec_from_file_location("npp_model_step_defaults", SCRIPT)
        assert spec is not None and spec.loader is not None
        self.checker = importlib.util.module_from_spec(spec)
        with patch.object(sys, "path", sys.path.copy()):
            spec.loader.exec_module(self.checker)

    def _fixture(self, source: str | None = MAPPER, *, edit=None, picture="fixture-picture"):
        path = self.tmp / "edits.py"
        if source is not None:
            path.write_bytes(source.encode("utf-8"))
        steps = {"edit_map": {"model": "fixture-edit", "effort": "low", "timeout_s": 8},
                 "picture": {"model": picture}}
        if edit is not None:
            steps["edit_map"].update(edit)
        with (patch.object(self.checker, "EDITS_SOURCE", path),
              patch.object(npp, "assets", return_value=({"steps": steps}, {}, {})),
              patch.object(photo_polish, "MODEL", "fixture-picture")):
            return self._main()

    def _main(self):
        stdout, stderr = io.StringIO(), io.StringIO()
        with redirect_stdout(stdout), redirect_stderr(stderr):
            status = self.checker.main([])
        return status, stdout.getvalue().splitlines(), stderr.getvalue()

    def _cli(self, *args):
        return subprocess.run([sys.executable, "-B", str(SCRIPT), *args],
                              cwd=self.tmp, capture_output=True, text=True, timeout=10)

    def _assert_result(self, result, status, trailer):
        actual_status, lines, stderr = result
        self.assertEqual(actual_status, status, stderr)
        self.assertTrue(lines)
        self.assertEqual(lines[-1], trailer)
        self.assertEqual(stderr, "")
        return lines

    def test_c1_full_pass(self):
        # Agreeing steps pass; a nested helper is not a second mapper default.
        source = MAPPER + f"    def unrelated(step):\n        {DEFAULT}\n"
        lines = self._assert_result(self._fixture(source), 0, PASS)
        self.assertFalse(any(line.startswith("FAIL ") for line in lines))

    def test_c2_findings_trailer(self):
        # Both failures survive one run; neither check short-circuits the other.
        lines = self._assert_result(self._fixture(edit={"effort": "high"}, picture="other"), 1, FAIL)
        self.assertEqual(lines[-3:], ["FAIL edit-map-default-drift effort", "FAIL picture-model-drift", FAIL])

    def test_c2_1_edit_map_default_drift(self):
        # Checking only the model or stopping at the first drift drops findings.
        lines = self._assert_result(
            self._fixture(edit={"model": "other", "effort": "high", "timeout_s": 12}), 1, FAIL,
        )
        self.assertEqual([line for line in lines[:-1] if line.startswith("FAIL ")], [
            "FAIL edit-map-default-drift model",
            "FAIL edit-map-default-drift effort",
            "FAIL edit-map-default-drift timeout_s",
        ])

    def test_c2_2_picture_model_drift(self):
        # Comparing the pin to itself would miss a changed picture model.
        lines = self._assert_result(self._fixture(picture="other"), 1, FAIL)
        self.assertIn("step picture code=fixture-picture pinned=other", lines)
        self.assertEqual([line for line in lines[:-1] if line.startswith("FAIL ")], ["FAIL picture-model-drift"])

    def test_c2_3_default_not_found(self):
        # Do not accept an unrelated fallback, pick the first of two, or guess a nonliteral value.
        for source in (
            f"def other(step):\n    {DEFAULT}\ndef codex_mapper(step):\n    return step\n",
            MAPPER + f"    if transport:\n        {DEFAULT}\n",
            MAPPER.replace("'timeout_s': 8", "'timeout_s': timeout()"),
        ):
            with self.subTest(source=source):
                lines = self._assert_result(self._fixture(source), 1, FAIL)
                self.assertEqual(lines, [PICTURE_LINE, "FAIL default-not-found", FAIL])

    def test_c2_4_parse_error(self):
        # A read failure and a syntax failure must both be reported, not traceback or pass.
        for source in (None, "def codex_mapper(:\n    pass\n"):
            with self.subTest(source=source):
                lines = self._assert_result(self._fixture(source), 1, FAIL)
                self.assertEqual(lines, [PICTURE_LINE, "FAIL parse-error", FAIL])

    def test_c3_usage_exit_2(self):
        # Ignoring extra args or leaving a help route would bypass the zero-argument contract.
        for arg in ("extra", "--unknown", "--help", "--"):
            with self.subTest(arg=arg):
                result = self._cli(arg)
                self.assertEqual(result.returncode, 2, result.stderr)
                self.assertEqual(result.stdout, "")
                self.assertTrue(result.stderr.startswith("usage: "))
                self.assertEqual(result.stderr.splitlines()[-1],
                                 f"{SCRIPT.name}: error: unrecognized arguments: {arg}")

    def test_c4_read_only(self):
        # A diagnostic must not write cache files or refresh the pins or site.
        def snapshot():
            entries = {}
            for name in ("hass", "storefront-mockup"):
                root = ROOT / name
                for path in (root, *root.rglob("*")):
                    info = path.lstat()
                    entries[path.relative_to(ROOT)] = (info.st_size, info.st_mtime_ns)
            return entries

        before = snapshot()
        result = self._cli()
        self.assertEqual(snapshot(), before)
        self._assert_result((result.returncode, result.stdout.splitlines(), result.stderr), 0, PASS)

    def test_c5_output_shape(self):
        # Trace/debug lines or unlabeled warnings would break consumers of the report.
        lines = self._assert_result(self._fixture(edit={"effort": "high"}), 1, FAIL)
        self.assertEqual(lines, [
            "step edit_map default=fixture-edit/low/8 pinned=fixture-edit/high/8",
            PICTURE_LINE, "FAIL edit-map-default-drift effort", FAIL,
        ])

    def test_c6_fixture(self):
        # The tool must use the asset loader's pin (not a cached or separately read JSON copy).
        pins, files, replies = npp.assets()
        pins["steps"]["edit_map"]["timeout_s"] = 9
        with patch.object(npp, "assets", return_value=(pins, files, replies)):
            lines = self._assert_result(self._main(), 1, FAIL)
        self.assertEqual([line for line in lines[:-1] if line.startswith("FAIL ")], [
            "FAIL edit-map-default-drift timeout_s",
        ])

    def test_c7_live_pins(self):
        # The actual checked-in sources, not the test fixtures, must agree on these route IDs.
        result = self._cli()
        lines = self._assert_result((result.returncode, result.stdout.splitlines(), result.stderr), 0, PASS)
        self.assertEqual(lines, [
            "step edit_map default=gpt-6.2-sol/low/8 pinned=gpt-6.2-sol/low/8",
            "step picture code=openai-codex:gpt-image-2-high pinned=openai-codex:gpt-image-2-high",
            PASS,
        ])


if __name__ == "__main__":
    unittest.main()
