"""Offline contract tests for the NPP code-line drift guard."""

from contextlib import redirect_stderr, redirect_stdout
import importlib.util
import io
from pathlib import Path
import subprocess
import sys
from tempfile import TemporaryDirectory
import unittest
from unittest.mock import patch

from hass import npp, voice
from hass.npp import job, missing, picture

ROOT = Path(__file__).resolve().parents[2]
SCRIPT = ROOT / "scripts/hass/npp_code_lines_check.py"
PASS = "PASS npp_code_lines_check"
FAIL = "FAIL npp_code_lines_check"
LIVE_LINES = [
    "line expired chars=65 sentences=2",
    "line duplicate chars=64 sentences=2",
    "line note-raw chars=23 sentences=0",
    "line note-house chars=20 sentences=0",
]


class NppCodeLinesCheckTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        spec = importlib.util.spec_from_file_location("npp_code_lines_check", SCRIPT)
        assert spec is not None and spec.loader is not None
        cls.checker = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(cls.checker)

    def invoke(self):
        stdout, stderr = io.StringIO(), io.StringIO()
        with redirect_stdout(stdout), redirect_stderr(stderr):
            status = self.checker.main([])
        self.assertEqual(stderr.getvalue(), "")
        return status, stdout.getvalue().splitlines()

    def cli(self, *args):
        with TemporaryDirectory(dir=ROOT) as cwd:
            return subprocess.run([sys.executable, "-B", str(SCRIPT), *args],
                                  cwd=cwd, capture_output=True, text=True, timeout=10)

    def assert_findings(self, result, *findings):
        status, lines = result
        self.assertEqual(status, 1)
        self.assertEqual(lines[4:], [*(f"FAIL {finding}" for finding in findings), FAIL])

    def test_c1_full_pass(self):
        # A clean CLI run must exit successfully, even from outside the checkout.
        result = self.cli()
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(result.stdout.splitlines()[-1], PASS)

    def test_c2_findings_trailer(self):
        # A first-failure return or regrouping by rule would lose this sequence.
        notes = {"raw": "picture: 2nd pick", "house": "picture: cabin style"}
        pins, files, templates = npp.assets()
        templates = {**templates, "caps": {"question_max_chars": 8}}
        with (patch.object(job, "EXPIRED", "Try option 2."),
              patch.object(missing, "DUPLICATE", "Would you add one?"),
              patch.object(picture, "_NOTES", notes),
              patch.object(npp, "assets", return_value=(pins, files, templates)),
              patch.object(voice, "check", return_value=["synthetic rule"])):
            result = self.invoke()
        self.assert_findings(result, "voice expired", "digit expired", "voice duplicate",
                             "voice note-raw", "digit note-raw", "voice note-house",
                             "too-long duplicate", "note-drift raw", "note-drift house")

    def test_c2_1_assets_unreadable(self):
        # A bad pinned asset must not leak exception text or produce a false pass.
        with patch.object(npp, "assets", side_effect=ValueError("synthetic asset detail")):
            result = self.invoke()
        self.assert_findings(result, "assets-unreadable")
        self.assertEqual(result[1][:4], LIVE_LINES)

    def test_c2_2_voice(self):
        # The real voice rules must see the current constant, not an imported copy.
        with patch.object(job, "EXPIRED", "Please check the database."):
            result = self.invoke()
        self.assert_findings(result, "voice expired")

    def test_c2_3_digit(self):
        # ASCII-only matching misses a decimal digit; isdigit also rejects superscripts.
        for text, found in (("Try option \u0662.", True), ("Try option \u00b2.", False)):
            with self.subTest(text=text), patch.object(job, "EXPIRED", text):
                result = self.invoke()
                if found:
                    self.assert_findings(result, "digit expired")
                else:
                    self.assertEqual((result[0], result[1][-1]), (0, PASS))

    def test_c2_4_too_long(self):
        # At the cap is legal; checking only voice would miss the over-cap case.
        cap = npp.assets()[2]["caps"]["question_max_chars"]
        for length in (cap, cap + 1):
            with self.subTest(length=length), patch.object(missing, "DUPLICATE", "A" * length):
                result = self.invoke()
                if length == cap:
                    self.assertEqual((result[0], result[1][-1]), (0, PASS))
                else:
                    self.assert_findings(result, "too-long duplicate")

    def test_c2_5_note_drift(self):
        # A template-only edit must be caught for each exact key, even when code is unchanged.
        pins, files, templates = npp.assets()
        for variant, key in (("raw", "picture_own_photo"), ("house", "picture_house")):
            parts = {**templates["brackets"]["parts"], key: "picture: another view"}
            edited = {**templates, "brackets": {**templates["brackets"], "parts": parts}}
            with self.subTest(variant=variant), patch.object(npp, "assets", return_value=(pins, files, edited)):
                self.assert_findings(self.invoke(), f"note-drift {variant}")

    def test_c3_usage_exit_2(self):
        # An ignored argument or automatically supported help flag violates the no-args interface.
        for arg in ("extra", "--unknown", "--help", "--"):
            with self.subTest(arg=arg):
                result = self.cli(arg)
                self.assertEqual(result.returncode, 2)
                self.assertEqual(result.stdout, "")
                self.assertIn("error: unrecognized arguments:", result.stderr.splitlines()[-1])

    def test_c4_read_only(self):
        # Even a write that preserves size must not change a source tree's mtime.
        def snapshot():
            entries = {}
            for name in ("hass", "storefront-mockup"):
                tree = ROOT / name
                for path in (tree, *tree.rglob("*")):
                    info = path.lstat()
                    entries[path.relative_to(ROOT)] = (info.st_size, info.st_mtime_ns)
            return entries

        before = snapshot()
        result = self.cli()
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(result.stdout.splitlines()[-1], PASS)
        self.assertEqual(snapshot(), before)

    def test_c5_output_shape(self):
        # Findings must not echo rule details or raw lines; punctuation inside a word is not a sentence.
        with patch.object(job, "EXPIRED", "See sample.txt. Then wait!\tOkay?"):
            status, lines = self.invoke()
        self.assertEqual(status, 1)
        self.assertEqual(lines, ["line expired chars=32 sentences=3", *LIVE_LINES[1:],
                                 "FAIL voice expired", FAIL])

    def test_c6_fixture(self):
        # A missing word in the raw note must not pass or be blamed on the house note.
        notes = {"raw": "picture: own photo", "house": "picture: house style"}
        with patch.object(picture, "_NOTES", notes):
            self.assert_findings(self.invoke(), "note-drift raw")

    def test_c7_live_pins(self):
        # A voice-safe source edit can still change the measured live baseline.
        result = self.cli()
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(result.stderr, "")
        self.assertEqual(result.stdout, "\n".join([*LIVE_LINES, PASS]) + "\n")
