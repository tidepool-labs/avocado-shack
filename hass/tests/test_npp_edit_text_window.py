"""Offline CLI contract tests for the synthetic NPP text-window replays."""

from contextlib import redirect_stderr, redirect_stdout
import dataclasses
import importlib.util
import io
import json
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[2]
SCRIPT = ROOT / "scripts/hass/npp_edit_text_window.py"
WINDOW = "window turns=8 total=8000"
PASS = "PASS npp_edit_text_window"
FAIL = "FAIL npp_edit_text_window"
PATCHES = ["edit ninth=patch", "edit after_long=patch"]
QUESTIONS = ["edit ninth=ask_edit_unclear", "edit after_long=ask_edit_unclear"]
FINDINGS = ["FAIL ninth-text-lost", "FAIL long-text-shift"]


def snapshot():
    entries = {}
    for tree in (ROOT / "hass", ROOT / "storefront-mockup"):
        for path in (tree, *tree.rglob("*")):
            info = path.lstat()
            entries[path.relative_to(ROOT)] = (info.st_size, info.st_mtime_ns)
    return entries


class NppEditTextWindowTests(unittest.TestCase):
    def setUp(self):
        temporary = tempfile.TemporaryDirectory()
        self.addCleanup(temporary.cleanup)
        self.root = Path(temporary.name)
        spec = importlib.util.spec_from_file_location("npp_edit_text_window", SCRIPT)
        assert spec is not None and spec.loader is not None
        self.script = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(self.script)
        self.real_edit = self.script.reply.Stages.edit

    def cli(self, *args):
        return subprocess.run(
            [sys.executable, "-B", str(SCRIPT), *args], cwd=self.root,
            capture_output=True, text=True, timeout=10,
        )

    def run_main(self, code, trailer):
        stdout, stderr = io.StringIO(), io.StringIO()
        with redirect_stdout(stdout), redirect_stderr(stderr):
            status = self.script.main([])
        return self.assert_run(status, stdout.getvalue(), stderr.getvalue(), code, trailer)

    def assert_run(self, status, stdout, stderr, code, trailer):
        self.assertEqual(status, code, stdout + stderr)
        self.assertEqual(stderr, "")
        lines = stdout.splitlines()
        self.assertEqual(lines[-1:], [trailer])
        return lines

    def assert_cli(self, result):
        return self.assert_run(result.returncode, result.stdout, result.stderr, 1, FAIL)

    def with_corrected_index(self, stage, work):
        # Each replay appends exactly one new text. The cap discarded old texts,
        # so the number of *retained* old texts is the retained length minus one.
        parent = json.loads(work.parent["listing_json"])
        parent[self.script.reply.SEEN] = len(work.request["texts"]) - 1
        adjusted = dataclasses.replace(work, parent={"listing_json": json.dumps(parent)})
        return self.real_edit(stage, adjusted)

    def test_c1_full_pass(self):
        # A hardwired failure trailer/exit would reject two successful edits.
        renamed = self.script.job.Plan(listing={"name": "Sage Honey"}, patch={"name": "Sage Honey"})
        with patch.object(self.script.reply.Stages, "edit", return_value=renamed):
            self.assertEqual(self.run_main(0, PASS), [WINDOW, *PATCHES, PASS])

    def test_c2_findings_trailer(self):
        # A patch for the wrong name is not success; report both findings, then fail.
        wrong = self.script.job.Plan(listing={"name": "Clover Honey"}, patch={"name": "Clover Honey"})
        with patch.object(self.script.reply.Stages, "edit", return_value=wrong):
            self.assertEqual(self.run_main(1, FAIL), [WINDOW, *PATCHES, *FINDINGS, FAIL])

    def test_c2_1_ninth_text_lost(self):
        # Swapping the two reason mappings mislabels the ninth-only loss.
        def edit(stage, work):
            if len(work.request["texts"]) == 8:
                return self.real_edit(stage, work)
            return self.with_corrected_index(stage, work)

        with patch.object(self.script.reply.Stages, "edit", edit):
            self.assertEqual(self.run_main(1, FAIL), [WINDOW, QUESTIONS[0], PATCHES[1], FINDINGS[0], FAIL])

    def test_c2_2_long_text_shift(self):
        # Checking only the turn cap would miss a loss from the character cap.
        def edit(stage, work):
            if len(work.request["texts"]) == 3:
                return self.real_edit(stage, work)
            return self.with_corrected_index(stage, work)

        with patch.object(self.script.reply.Stages, "edit", edit):
            self.assertEqual(self.run_main(1, FAIL), [WINDOW, PATCHES[0], QUESTIONS[1], FINDINGS[1], FAIL])

    def test_c2_3_turns_unread(self):
        # Neither a comment nor a turns keyword on an unrelated put supplies the cap.
        source = self.root / "job.py"
        source.write_text(
            "class Jobs:\n"
            "    def input(self):\n"
            "        # self.c.requests.put(turns=8)\n"
            "        self.c.requests.put(texts=[])\n"
            "        self.c.other.put(turns=8)\n",
            encoding="utf-8",
        )
        with patch.object(self.script.job, "__file__", str(source)):
            self.assertEqual(self.run_main(1, FAIL), ["FAIL turns-unread", FAIL])

    def test_c2_4_check_error(self):
        # Swallowing an exception would pass an unrun check; echoing it leaks text.
        for owner, name in ((self.script.openreq, "bound_texts"), (self.script.reply.Stages, "edit")):
            with self.subTest(name=name), patch.object(owner, name, side_effect=ValueError("fixture-only text")):
                self.assertEqual(self.run_main(1, FAIL), [WINDOW, "FAIL check-error", FAIL])

    def test_c3_usage_exit_2(self):
        # Accepting a positional argument or a default help flag breaks the no-arg CLI.
        for arg in ("unexpected", "--unknown", "--help", "--"):
            with self.subTest(arg=arg):
                result = self.cli(arg)
                self.assertEqual(result.returncode, 2)
                self.assertEqual(result.stdout, "")  # No last stdout line on usage errors.
                self.assertTrue(result.stderr.startswith("usage: "))
                self.assertEqual(result.stderr.splitlines()[-1],
                                 f"{SCRIPT.name}: error: unrecognized arguments: {arg}")

    def test_c4_read_only(self):
        # A replay accidentally entering the persistence path can leave new or changed files.
        before = snapshot()
        self.assert_cli(self.cli())
        self.assertEqual(snapshot(), before)
        self.assertEqual(list(self.root.iterdir()), [])

    def test_c5_output_shape(self):
        # Printing the question tuple, rather than its ID, would disclose the sentence.
        plan = self.script.job.Plan(questions=(("ask_edit_unclear", "fixture-only text\nsecond line"),))
        with patch.object(self.script.reply.Stages, "edit", return_value=plan):
            self.assertEqual(self.run_main(1, FAIL), [WINDOW, *QUESTIONS, *FINDINGS, FAIL])

    def test_c6_fixture(self):
        # Both correct edits must get through, not just the replay under one window.
        received = []

        def edit(stage, work):
            received.append((json.loads(work.parent["listing_json"])[self.script.reply.SEEN], work.request["texts"]))
            return self.with_corrected_index(stage, work)

        with patch.object(self.script.reply.Stages, "edit", edit):
            self.assertEqual(self.run_main(0, PASS), [WINDOW, *PATCHES, PASS])
        self.assertEqual(received, [
            (8, [f"call it Clover Honey {i}" for i in range(1, 8)] + ["call it Sage Honey"]),
            (3, ["x" * 3990, "y" * 3990, "call it Sage Honey"]),
        ])

    def test_c7_live_pins(self):
        # Pin the observed cap and findings so a change in the real stages is visible.
        self.assertEqual(self.assert_cli(self.cli()), [WINDOW, *QUESTIONS, *FINDINGS, FAIL])


if __name__ == "__main__":
    unittest.main()
