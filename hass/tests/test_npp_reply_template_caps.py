"""Offline CLI contract for the pinned reply template cap check."""

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

from hass import npp
from hass.npp import reply

ROOT = Path(__file__).resolve().parents[2]
SCRIPT = ROOT / "scripts/hass/npp_reply_template_caps.py"
SPEC = importlib.util.spec_from_file_location("npp_reply_template_caps", SCRIPT)
assert SPEC is not None and SPEC.loader is not None
CHECKER = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(CHECKER)
PASS = "PASS npp_reply_template_caps"
FAIL = "FAIL npp_reply_template_caps"


class ReplyTemplateCapsTests(unittest.TestCase):
    def setUp(self):
        self.temp = Path(self.enterContext(TemporaryDirectory()))
        self.replies = {
            "caps": {"question_max_chars": 40, "line_max_sentences": 1, "bracket_max_chars": 40},
            "questions": {"ask": "Which one?"},
            "prompts": {"sample": "Choose one."},
            "guards": {"hold": "Not yet.", "guard_note": "One. Two."},
            "confirm": {"done": "Done."},
            "edits": {"change": "Try again."},
            "brackets": {
                "parts": {"sample": "sample"},
                "compose": {"drop_order": ["sample"], "separator": "; "},
            },
        }

    def capture_main(self):
        out, err = io.StringIO(), io.StringIO()
        with redirect_stdout(out), redirect_stderr(err):
            status = CHECKER.main([])
        return status, out.getvalue(), err.getvalue()

    def fixture_run(self, replies=None):
        path = self.temp / "replies.json"
        path.write_text(json.dumps(self.replies if replies is None else replies), encoding="utf-8")
        with patch.object(npp, "assets", side_effect=lambda: ({}, {}, json.loads(
            path.read_text(encoding="utf-8")))) as load:
            result = self.capture_main()
        load.assert_called_once_with()
        return result

    def cli(self, *args):
        result = subprocess.run([sys.executable, "-B", str(SCRIPT), *args],
                                cwd=self.temp, text=True, capture_output=True, timeout=15)
        return result.returncode, result.stdout, result.stderr

    def assert_run(self, result, rc, trailer, findings=()):
        actual_rc, out, err = result
        self.assertEqual(err, "")
        self.assertEqual(actual_rc, rc, out)
        lines = out.splitlines()
        self.assertEqual(lines[-1:], [trailer])
        self.assertEqual([line for line in lines[:-1] if line.startswith("FAIL ")], list(findings))
        return lines

    def test_c1_full_pass(self):
        # A valid fixture must not be treated as a dry-run error or reported as a finding.
        self.assert_run(self.fixture_run(), 0, PASS)

    def test_c2_findings_trailer(self):
        # Multiple findings must not short-circuit the report or produce multiple trailers.
        self.replies["caps"]["question_max_chars"] = 1
        self.replies["caps"]["bracket_max_chars"] = 1
        self.assert_run(self.fixture_run(), 1, FAIL,
                        ("FAIL question-too-long ask", "FAIL part-too-long sample"))

    def test_c2_1_question_too_long(self):
        # Checking raw braces or rejecting equality in place of overflow misclassifies these.
        self.replies["caps"]["question_max_chars"] = 21
        self.replies["questions"] = {"exact": "{value}?", "long": "A {value}?"}
        self.assert_run(self.fixture_run(), 1, FAIL, ("FAIL question-too-long long",))

    def test_c2_2_guard_not_one_line(self):
        # Don't check the note as a served guard, ignore edits, or replace the repo predicate.
        self.replies["guards"]["hold"] = "Stop. Wait."
        self.replies["edits"]["change"] = "Try\nagain."
        with (patch.object(reply, "guard", wraps=reply.guard) as guard,
              patch.object(reply, "one_line", wraps=reply.one_line) as one_line):
            self.assert_run(self.fixture_run(), 1, FAIL,
                            ("FAIL guard-not-one-line hold", "FAIL guard-not-one-line change"))
        guard.assert_called_once_with(self.replies, "hold")
        one_line.assert_any_call("Stop. Wait.")
        one_line.assert_any_call("Try\nagain.")

    def test_c2_3_part_too_long(self):
        # Counting an already-dropped string, raw braces, or not counting parentheses passes the bad part.
        self.replies["caps"]["bracket_max_chars"] = 21
        self.replies["brackets"]["parts"] = {"exact": "a" * 19, "long": "{value}"}
        self.replies["brackets"]["compose"]["drop_order"] = ["exact", "long"]
        with patch.object(reply, "compose", wraps=reply.compose) as compose:
            lines = self.assert_run(self.fixture_run(), 1, FAIL, ("FAIL part-too-long long",))
        self.assertIn("part exact chars=19", lines)
        self.assertIn("part long chars=20", lines)
        compose.assert_any_call(self.replies, {"exact": {}})
        compose.assert_any_call(self.replies, {"long": {"value": "x" * 20}})

    def test_c2_4_part_unordered(self):
        # Comparing in only one direction misses a missing order entry or a missing template.
        self.replies["brackets"]["compose"]["drop_order"] = ["absent", "absent"]
        with patch.object(reply, "compose", wraps=reply.compose) as compose:
            self.assert_run(self.fixture_run(), 1, FAIL,
                            ("FAIL part-unordered sample", "FAIL part-unordered absent"))
        compose.assert_any_call(self.replies, {"sample": {}})
        compose.assert_any_call(self.replies, {"absent": {}})

    def test_c2_5_check_error(self):
        # A loader exception should not escape, leak its message, or count as clean.
        with patch.object(npp, "assets", side_effect=RuntimeError("synthetic error")) as load:
            result = self.capture_main()
        load.assert_called_once_with()
        self.assertEqual(self.assert_run(result, 1, FAIL, ("FAIL check-error",)),
                         ["FAIL check-error", FAIL])
        # A late repo check error is also not a silent skip.
        with patch.object(reply, "compose", side_effect=RuntimeError("synthetic error")):
            self.assert_run(self.fixture_run(), 1, FAIL, ("FAIL check-error",))

    def test_c3_usage_exit_2(self):
        # Unwanted positionals, flags, help, and a bare separator must be usage errors.
        for arg in ("extra", "--unknown", "--help", "-h", "--"):
            with self.subTest(arg=arg):
                rc, out, err = self.cli(arg)
                self.assertEqual((rc, out), (2, ""))
                self.assertTrue(err.startswith("usage:"), err)
                self.assertEqual(err.splitlines()[-1],
                                 f"npp_reply_template_caps.py: error: unrecognized arguments: {arg}")

    def test_c4_read_only(self):
        # A cache or generated file in either tree would alter the metadata snapshot.
        def snapshot():
            entries = {}
            for tree in (ROOT / "hass", ROOT / "storefront-mockup"):
                for path in (tree, *tree.rglob("*")):
                    info = path.lstat()
                    entries[path.relative_to(ROOT)] = (info.st_size, info.st_mtime_ns)
            return entries

        before = snapshot()
        self.assert_run(self.cli(), 0, PASS)
        self.assertEqual(snapshot(), before)

    def test_c5_output_shape(self):
        # Extra logs, wrong metrics, and counting punctuation in the trailing bracket all break the format.
        self.replies["prompts"]["sample"] = "Choose one. (Optional!)"
        self.replies["caps"]["question_max_chars"] = 1
        self.assertEqual(self.assert_run(self.fixture_run(), 1, FAIL, ("FAIL question-too-long ask",)), [
            "line questions.ask chars=10 sentences=1 one_line=yes",
            "FAIL question-too-long ask",
            "line prompts.sample chars=23 sentences=1 one_line=yes",
            "line guards.hold chars=8 sentences=1 one_line=yes",
            "line guards.guard_note chars=9 sentences=2 one_line=no",
            "line confirm.done chars=5 sentences=1 one_line=yes",
            "line edits.change chars=10 sentences=1 one_line=yes",
            "part sample chars=6",
            FAIL,
        ])

    def test_c6_fixture(self):
        # A realistic pin edit should trigger only the served guard and singleton budget findings.
        _, _, replies = npp.assets()
        replies["guards"]["replaced"] += " Wait."
        replies["caps"]["bracket_max_chars"] = 30
        self.assert_run(self.fixture_run(replies), 1, FAIL, (
            "FAIL guard-not-one-line replaced",
            "FAIL part-too-long maker_left_off",
            "FAIL part-too-long maker_left_off_label",
            "FAIL part-too-long claim_left_off",
        ))

    def test_c7_live_pins(self):
        # Require the real CLI to cover the full current pin inventory, not just a passing trailer.
        lines = self.assert_run(self.cli(), 0, PASS)
        stats = dict(line.split(" ", 2)[1:] for line in lines[:-1])
        _, _, replies = npp.assets()
        groups = ("questions", "prompts", "guards", "confirm", "edits")
        expected_keys = {f"{group}.{key}" for group in groups for key in replies[group]}
        filled_lengths = {"picture_own_photo": 23, "picture_house": 20, "basic_wording": 13,
                          "story_not_found": 21, "maker_left_off": 41,
                          "maker_left_off_label": 47, "claim_left_off": 30}
        self.assertEqual(set(stats), expected_keys | filled_lengths.keys())
        self.assertEqual(len(lines) - 1, len(stats))
        self.assertEqual(stats["questions.ask_identity"], "chars=71 sentences=2 one_line=no")
        self.assertEqual(stats["questions.ask_edit_unclear"], "chars=47 sentences=2 one_line=no")
        for key in replies["questions"].keys() - {"ask_identity", "ask_edit_unclear"}:
            self.assertTrue(stats[f"questions.{key}"].endswith(" sentences=1 one_line=yes"))
        for key in replies["guards"].keys() - {"guard_note"}:
            self.assertTrue(stats[f"guards.{key}"].endswith(" sentences=1 one_line=yes"))
        self.assertEqual(stats["edits.picture_request"], "chars=44 sentences=1 one_line=yes")
        self.assertEqual(stats["guards.guard_note"], "chars=80 sentences=2 one_line=no")
        parts = replies["brackets"]["parts"]
        self.assertEqual({key: len(text) for key, text in parts.items()},
                         dict(filled_lengths, maker_left_off_label=34, claim_left_off=17))
        self.assertCountEqual(replies["brackets"]["compose"]["drop_order"], filled_lengths.keys())
        for key, chars in filled_lengths.items():
            self.assertEqual(stats[key], f"chars={chars}")
