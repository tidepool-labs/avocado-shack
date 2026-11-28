"""Offline CLI contracts for the shelf vocabulary check."""

from contextlib import redirect_stderr, redirect_stdout
import importlib.util
import io
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import call, patch

from hass import content_model
from hass.skills import kinds


ROOT = Path(__file__).resolve().parents[2]
SCRIPT = ROOT / "scripts/hass/shelf_words_check.py"
SPEC = importlib.util.spec_from_file_location("shelf_words_check", SCRIPT)
assert SPEC is not None and SPEC.loader is not None
CHECK = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(CHECK)
PASS = "PASS shelf_words_check"
FAIL = "FAIL shelf_words_check"


def snapshot_hass():
    tree = ROOT / "hass"
    snapshot = {}
    for path in (tree, *tree.rglob("*")):
        info = path.lstat()
        snapshot[path.relative_to(tree)] = (info.st_size, info.st_mtime_ns)
    return snapshot


class ShelfWordsCheckTests(unittest.TestCase):
    def setUp(self):
        self.labels = {key: key.title() for key in content_model.CATEGORIES}

    def run_main(self, *, labels=None):
        stdout, stderr = io.StringIO(), io.StringIO()
        with patch.object(content_model, "SHELF_LABELS", self.labels if labels is None else labels):
            with redirect_stdout(stdout), redirect_stderr(stderr):
                code = CHECK.main([])
        return code, stdout.getvalue(), stderr.getvalue()

    def run_cli(self, cwd, *args):
        result = subprocess.run(
            [sys.executable, "-B", str(SCRIPT), *args], cwd=cwd,
            capture_output=True, text=True, timeout=10,
        )
        return result.returncode, result.stdout, result.stderr

    def assert_report(self, result, code, trailer):
        actual_code, stdout, stderr = result
        self.assertEqual(actual_code, code, stderr)
        self.assertEqual(stderr, "")
        lines = stdout.splitlines()
        self.assertTrue(lines)
        self.assertEqual(lines[-1], trailer)
        return lines

    def test_c1_full_pass(self):
        # A successful report must exit zero without any finding lines.
        lines = self.assert_report(self.run_main(), 0, PASS)
        count = len(self.labels)
        self.assertEqual(lines, [f"categories {count}", f"probes {2 * count}", f"read {2 * count}", PASS])

    def test_c2_findings_trailer(self):
        # Multiple findings must not suppress or repeat the failure trailer.
        self.labels["fruit"] = "Fruit zulu"
        self.labels["dairy"] = "Dairy alpha"
        lines = self.assert_report(self.run_main(), 1, FAIL)
        self.assertEqual(lines[3:], ["FAIL shelf-word-unread fruit zulu", "FAIL shelf-word-unread dairy alpha", FAIL])

    def test_c2_1_check_error(self):
        # A resolver exception must not leak its message or stop later probes.
        shelf = kinds.shelf

        def fail_one(probe):
            if probe == "Fruit":
                raise RuntimeError("synthetic exception text")
            return shelf(probe)

        with patch.object(kinds, "shelf", side_effect=fail_one):
            lines = self.assert_report(self.run_main(), 1, FAIL)
        self.assertEqual(lines[2:], [f"read {2 * len(self.labels) - 1}", "FAIL check-error", FAIL])

    def test_c2_2_label_unread(self):
        # A label resolving to the wrong shelf must report the key, not the label.
        self.labels["fruit"] = "Eggs"
        lines = self.assert_report(self.run_main(), 1, FAIL)
        self.assertEqual(lines[3:], ["FAIL shelf-label-unread fruit", "FAIL shelf-word-unread fruit Eggs", FAIL])

    def test_c2_3_word_unread(self):
        # Don't skip the key probe or sort the extra words before reporting them.
        self.labels["fruit"] = "Fruit zulu Alpha"
        shelf = kinds.shelf
        with patch.object(kinds, "shelf", side_effect=lambda probe: shelf("eggs" if probe == "fruit" else probe)):
            lines = self.assert_report(self.run_main(), 1, FAIL)
        self.assertEqual(lines[3:], [
            "FAIL shelf-word-unread fruit fruit", "FAIL shelf-word-unread fruit zulu",
            "FAIL shelf-word-unread fruit Alpha", FAIL,
        ])

    def test_c2_4_word_invalid(self):
        # A long token must never leak into the report; 40 letters remain printable.
        valid, invalid = "Z" * 40, "X" * 41
        self.labels["fruit"] = f"Fruit {valid} {invalid}"
        lines = self.assert_report(self.run_main(), 1, FAIL)
        self.assertEqual(lines[3:], [f"FAIL shelf-word-unread fruit {valid}", "FAIL word-invalid", FAIL])

    def test_c3_usage_exit_2(self):
        # Even implicit argparse help or an end-of-options token is an argument.
        with tempfile.TemporaryDirectory() as cwd:
            for arg in ("extra", "--unknown", "--help", "-h", "--", ""):
                with self.subTest(arg=arg):
                    code, stdout, stderr = self.run_cli(cwd, arg)
                    self.assertEqual(code, 2)
                    self.assertEqual(stdout, "")  # No stdout trailer on usage errors.
                    self.assertIn("usage:", stderr)

    def test_c4_read_only(self):
        # Catch caches or reports written to the checkout or working directory.
        with tempfile.TemporaryDirectory() as cwd:
            before = snapshot_hass()
            self.assert_report(self.run_cli(cwd), 1, FAIL)
            self.assertEqual(snapshot_hass(), before)
            self.assertEqual(list(Path(cwd).iterdir()), [])

    def test_c5_output_shape(self):
        # Mixed findings must not include labels, resolver replies or debug output.
        self.labels["fruit"] = "Eggs zulu"
        lines = self.assert_report(self.run_main(), 1, FAIL)
        for line in lines:
            self.assertRegex(line, r"\A(?:(?:categories|probes|read) [0-9]+|"
                                  r"FAIL shelf-label-unread [A-Za-z]{1,40}|"
                                  r"FAIL shelf-word-unread [A-Za-z]{1,40} [A-Za-z]{1,40}|"
                                  r"FAIL (?:check-error|word-invalid|shelf_words_check))\Z")

    def test_c6_patched_pass(self):
        # Read both the key and the newly patched label exactly once, in category order.
        with patch.object(kinds, "shelf", wraps=kinds.shelf) as shelf:
            self.assert_report(self.run_main(), 0, PASS)
        self.assertEqual(shelf.call_args_list, [
            probe for key, label in self.labels.items() for probe in (call(key), call(label))
        ])

    def test_c7_live_words(self):
        # Pin the measured checkout gap, not an assumed list of aliases.
        with tempfile.TemporaryDirectory() as cwd:
            lines = self.assert_report(self.run_cli(cwd), 1, FAIL)
        self.assertEqual(lines, [
            "categories 10", "probes 22", "read 20", "FAIL shelf-word-unread dairy cheese",
            "FAIL shelf-word-unread drinks coffee", FAIL,
        ])
