"""Offline CLI contract tests for the argument wording check."""

from contextlib import contextmanager, redirect_stderr, redirect_stdout
import importlib.util
import io
from pathlib import Path
import subprocess
import sys
from tempfile import TemporaryDirectory
import unittest
from unittest.mock import patch

from hass import field_words, ops
from hass.ops import Arg, Op


SCRIPT = Path(__file__).resolve().parents[2] / "scripts/hass/field_words_voice_check.py"
PASS = "PASS field_words_voice_check"
FAIL = "FAIL field_words_voice_check"
GAP_WORDS = {
    "clearProduct": "remove the product",
    "labelText": "the words on the label",
    "ownerText": "your wording",
    "restock_on": "the day it comes back",
    "sellingPrice": "the selling price",
    "showNew": "whether to show it as new",
    "withProducts": "include the products",
}


@contextmanager
def sample_registry(*arg_tables):
    registry = {}
    for index, args in enumerate(arg_tables):
        name = f"sample{index}"
        registry[name] = Op(name, args, lambda *_: None)
    with patch.object(ops, "load_registry", return_value=registry), patch.dict(field_words.FIELD_WORDS, clear=True):
        yield


class FieldWordsVoiceCheckTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        spec = importlib.util.spec_from_file_location("field_words_voice_check", SCRIPT)
        assert spec is not None and spec.loader is not None
        cls.cli = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(cls.cli)

    def run_main(self, status, trailer):
        stdout, stderr = io.StringIO(), io.StringIO()
        with redirect_stdout(stdout), redirect_stderr(stderr):
            code = self.cli.main([])
        lines = stdout.getvalue().splitlines()
        self.assertEqual(code, status)
        self.assertEqual(lines[-1:], [trailer])
        self.assertEqual(stderr.getvalue(), "")
        return lines

    def test_c1_full_pass(self):
        # A wording entry fixes a raw code name; an unworded plain name and unused keys aren't findings.
        with sample_registry({
            "sampleName": Arg("text"), "color": Arg("text"),
        }), patch.dict(field_words.FIELD_WORDS, {
            "sampleName": "the name", "unusedWord": "the wording",
        }):
            self.assertEqual(self.run_main(0, PASS), [
                "args 2", "worded 1", "unworded 1", "note unused-entry unusedWord", "note odd-name 0", PASS,
            ])

    def test_c2_findings_trailer(self):
        # A run must continue after either kind of voice finding, not exit on the first or collapse distinct names.
        with sample_registry({
            "other_name!": Arg("text"), "sampleName": Arg("text"), "odd_name!": Arg("text"),
        }, {"odd_name!": Arg("text")}):
            self.assertEqual(self.run_main(1, FAIL), [
                "args 3", "worded 0", "unworded 3", "note odd-name 2",
                "FAIL voice-name-invalid", "FAIL voice-name-invalid", "FAIL voice sampleName required", FAIL,
            ])

    def test_c2_1_voice(self):
        # Last-op-wins aggregation would lose a required use; per-op checks would repeat it.
        with sample_registry({
            "sampleName": Arg("text"), "extra_name": Arg("text", required=False),
        }, {"sampleName": Arg("text", required=False)}):
            self.assertEqual(self.run_main(1, FAIL), [
                "args 2", "worded 0", "unworded 2", "note odd-name 0",
                "FAIL voice extra_name optional", "FAIL voice sampleName required", FAIL,
            ])

    def test_c2_2_registry_error(self):
        # A loader exception must not leak its message or masquerade as an empty passing registry.
        with patch.object(ops, "load_registry", side_effect=ValueError("synthetic-loader-canary")):
            self.assertEqual(self.run_main(1, FAIL), ["FAIL registry-error", FAIL])

    def test_c2_3_voice_name_invalid(self):
        # A redacted finding alone must still fail; neither the argument nor the rule should be echoed.
        canary = "odd_name!"
        with sample_registry({canary: Arg("text")}):
            lines = self.run_main(1, FAIL)
        self.assertEqual(lines, ["args 1", "worded 0", "unworded 1", "note odd-name 1",
                                 "FAIL voice-name-invalid", FAIL])
        self.assertNotIn(PASS, lines)
        self.assertNotIn(canary, "\n".join(lines))

    def test_c3_usage_exit_2(self):
        # Unknown options are parser errors, not a registry run and not a checker finding.
        result = subprocess.run([sys.executable, "-B", str(SCRIPT), "--unknown"],
                                capture_output=True, text=True, timeout=10)
        self.assertEqual(result.returncode, 2)
        self.assertEqual(result.stdout, "")
        self.assertTrue(result.stderr.startswith("usage:"))
        self.assertTrue(result.stderr.splitlines()[-1].endswith("error: unrecognized arguments: --unknown"))

    def test_c4_read_only(self):
        # Running the real entry point from an empty cwd must not leave a report or cache there.
        with TemporaryDirectory(dir=Path.cwd()) as folder:
            result = subprocess.run([sys.executable, "-B", str(SCRIPT)], cwd=folder,
                                    capture_output=True, text=True, timeout=10)
            self.assertEqual(result.returncode, 1)
            self.assertEqual(result.stdout.splitlines()[-1:], [FAIL])
            self.assertEqual(result.stderr, "")
            self.assertEqual(list(Path(folder).iterdir()), [])

    def test_c5_no_private_values(self):
        # A regex end anchor alone can accept a trailing newline; neither outcome may reveal the raw name.
        for stem, status, trailer, findings in (
            ("syntheticquiet", 0, PASS, []),
            ("synthetic_loud", 1, FAIL, ["FAIL voice-name-invalid"]),
        ):
            with self.subTest(status=status), sample_registry({stem + "\n": Arg("text")}):
                lines = self.run_main(status, trailer)
                self.assertEqual(lines, ["args 1", "worded 0", "unworded 1", "note odd-name 1",
                                         *findings, trailer])
                self.assertNotIn(stem, "\n".join(lines))

    def test_c6_patched_pass(self):
        # The real gaps must be fixable by owner wording alone, with no registry changes.
        with patch.dict(field_words.FIELD_WORDS, GAP_WORDS):
            self.assertEqual(self.run_main(0, PASS), [
                "args 84", "worded 49", "unworded 35", "note odd-name 0", PASS,
            ])

    def test_c7_live_gap(self):
        # Pin the whole gap, including order and optionality, so a changed inventory can't drift silently.
        self.assertEqual(self.run_main(1, FAIL), [
            "args 84", "worded 42", "unworded 42", "note odd-name 0",
            *[f"FAIL voice {name} optional" for name in sorted(GAP_WORDS)], FAIL,
        ])


if __name__ == "__main__":
    unittest.main()
