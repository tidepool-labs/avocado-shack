"""Offline contract tests for the counts-only maker story checker."""

from contextlib import redirect_stderr, redirect_stdout
import importlib.util
import io
import json
from pathlib import Path
import shutil
import subprocess
import sys
from tempfile import TemporaryDirectory
import unittest
from unittest.mock import patch


ROOT = Path(__file__).resolve().parents[2]
CONTENT = ROOT / "hass" / "content"
SCRIPT = ROOT / "scripts" / "hass" / "maker_story_check.py"
SPEC = importlib.util.spec_from_file_location("maker_story_check", SCRIPT)
assert SPEC is not None and SPEC.loader is not None
CHECK = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(CHECK)

PASS = "PASS maker_story_check"
FAIL = "FAIL maker_story_check"
PLAIN = "Apples grow on the hill."
REWORD = "They grow apples on the hill."
VOICE = "A selection of apples grows on the hill."


def cli(*args):
    result = subprocess.run([sys.executable, "-B", str(SCRIPT), *args],
                            capture_output=True, text=True, timeout=10)
    return result.returncode, result.stdout, result.stderr


class MakerStoryCheckTests(unittest.TestCase):
    def setUp(self):
        self.root = Path(self.enterContext(TemporaryDirectory()))
        self.content = self.root / "content"
        self.content.mkdir()
        for source in CONTENT.glob("*.json"):
            shutil.copyfile(source, self.content / source.name)
        self.maker_file = self.content / "makers.json"
        self.document = json.loads(self.maker_file.read_text(encoding="utf-8"))
        self.rows = [row for _, row in sorted(self.document["makers"].items())]
        for row in self.rows:
            row["story"] = PLAIN
        self.save()

    def save(self):
        self.maker_file.write_text(json.dumps(self.document), encoding="utf-8")

    def run_fixture(self):
        return cli("--content", str(self.content))

    def run_in_process(self):
        stdout, stderr = io.StringIO(), io.StringIO()
        with redirect_stdout(stdout), redirect_stderr(stderr):
            code = CHECK.main(["--content", str(self.content)])
        return code, stdout.getvalue(), stderr.getvalue()

    def assert_report(self, result, code, trailer, *findings, voice=0, reworded=0,
                      over=0, fallback=0, total=None):
        actual_code, stdout, stderr = result
        self.assertEqual(actual_code, code)
        self.assertEqual(stderr, "")
        counts = [f"makers {len(self.rows) if total is None else total}",
                  f"voice-problems {voice}", f"reworded {reworded}",
                  f"over-limit {over}", f"fallback-problems {fallback}"]
        self.assertEqual(stdout.splitlines(), [*counts, *findings, trailer])

    def assert_refused(self, result, reason):
        code, stdout, stderr = result
        self.assertEqual(code, 1)
        self.assertEqual(stdout.splitlines(), [f"FAIL {reason}", FAIL])
        self.assertEqual(stderr, "")

    def test_c1_full_pass(self):
        # A clean report must finish with the success trailer, not just counts.
        self.assert_report(self.run_fixture(), 0, PASS)

    def test_c2_findings_trailer(self):
        # Do not return after the first finding or reorder/drop findings.
        self.rows[0].update(story="Selection " + "a" * 400 + ".", name="Selection Farm")
        self.save()
        self.assert_report(self.run_fixture(), 1, FAIL, "FAIL story-voice 1",
                           "FAIL story-over-limit 1", "FAIL fallback-voice 1",
                           voice=1, over=1, fallback=1)

    def test_c2_1_unsafe_input(self):
        # A symlink to an otherwise valid directory must not be followed.
        link = self.root / "linked"
        link.symlink_to(self.content, target_is_directory=True)
        for path in (link, self.maker_file, self.root / "missing"):
            with self.subTest(kind=path.name):
                self.assert_refused(cli("--content", str(path)), "unsafe-input")

    def test_c2_2_content_invalid(self):
        # A broken JSON input must not produce a traceback or partial report.
        self.maker_file.write_text("{", encoding="utf-8")
        self.assert_refused(self.run_fixture(), "content-invalid")

    def test_c2_3_check_error(self):
        # An exception in any checker must not be mistaken for a clean result.
        for module, function in ((CHECK.voice, "check"), (CHECK.makers, "story_words"),
                                 (CHECK.makers, "fallback_story")):
            with self.subTest(function=function):
                with patch.object(module, function, side_effect=RuntimeError("Hidden detail")):
                    self.assert_refused(self.run_in_process(), "check-error")

    def test_c2_4_story_voice(self):
        # Count affected stories, not the number of voice phrases they trigger.
        self.rows[0]["story"] = "A selection appears in the catalog."
        self.save()
        self.assert_report(self.run_fixture(), 1, FAIL, "FAIL story-voice 1", voice=1)

    def test_c2_5_story_over_limit(self):
        # Exactly 400 characters fits; 401 exceeds the separate story ceiling.
        self.rows[0]["story"] = "A" * 399 + "."
        self.rows[1]["story"] = "B" * 400 + "."
        self.save()
        self.assert_report(self.run_fixture(), 1, FAIL, "FAIL story-over-limit 1", over=1)

    def test_c2_6_fallback_voice(self):
        # Voice-check the generated fallback even when the stored story is clean.
        self.rows[0].update(name="Willow Tern Farm", place="Pebble Hollow")
        self.save()
        check = CHECK.voice.check

        def flagged_fallback(text):
            if text == "Willow Tern Farm is based in Pebble Hollow.":
                return ["Synthetic finding"]
            return check(text)

        with patch.object(CHECK.voice, "check", side_effect=flagged_fallback):
            self.assert_report(self.run_in_process(), 1, FAIL, "FAIL fallback-voice 1", fallback=1)

    def test_c3_usage_exit_2(self):
        # A missing flag value or unknown flag is a usage error, not a finding.
        for args in (("--content",), ("--unexpected",)):
            with self.subTest(args=args):
                code, stdout, stderr = cli(*args)
                self.assertEqual((code, stdout), (2, ""))
                self.assertTrue(stderr.startswith("usage:"))

    def test_c4_read_only(self):
        # Rewriting/reformatting input or creating a report beside it is forbidden.
        def snapshot():
            return {p.relative_to(self.content): (p.stat().st_mtime_ns,
                                                  p.read_bytes() if p.is_file() else None)
                    for p in (self.content, *self.content.rglob("*"))}

        before = snapshot()
        self.assert_report(self.run_fixture(), 0, PASS)
        self.assertEqual(snapshot(), before)

    def test_c5_no_private_values(self):
        # Neither the finding text nor argparse diagnostics may disclose values.
        name, story, place = "Mallow Juniper Farm", "The selection is by the blue shed.", "Flint Hollow"
        path = str(self.content.absolute())
        self.rows[0].update(name=name, story=story, place=place)
        self.save()
        report = self.run_fixture()
        self.assert_report(report, 1, FAIL, "FAIL story-voice 1", voice=1)
        usage = cli("--content", path, path)
        self.assertEqual(usage[:2], (2, ""))
        for private in (name, story, place, path, "the word 'selection'"):
            self.assertTrue(all(private not in out for result in (report, usage) for out in result[1:]))

    def test_c6_clean_makers(self):
        # A maker named in their own plain story need not be reworded.
        self.rows[0].update(name="Birch Finch Farm", story="Birch Finch Farm grows apples.")
        self.save()
        self.assert_report(self.run_fixture(), 0, PASS, reworded=0)

    def test_c7_reword_and_voice(self):
        # Editorial changes are advisory; a real voice problem is not.
        self.rows[0]["story"] = REWORD
        self.save()
        self.assert_report(self.run_fixture(), 0, PASS, reworded=1)
        self.rows[0]["story"] = VOICE
        self.save()
        self.assert_report(self.run_fixture(), 1, FAIL, "FAIL story-voice 1", voice=1)

    def test_c8_live_makers(self):
        # No --content uses the checked-in catalog, not the passing fixture.
        self.assert_report(cli(), 1, FAIL, "FAIL story-voice 1", total=26, voice=1, reworded=4)
