"""Numbered CLI contracts for the offline S3 maker phrase replay."""

from contextlib import redirect_stderr, redirect_stdout
import importlib.util
import io
import json
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import call, patch

ROOT = Path(__file__).resolve().parents[2]
SCRIPT = ROOT / "scripts/hass/npp_maker_phrase_replay.py"
SPEC = importlib.util.spec_from_file_location("npp_maker_phrase_replay", SCRIPT)
assert SPEC is not None and SPEC.loader is not None
replay = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(replay)

PASS = "PASS npp_maker_phrase_replay"
FAIL = "FAIL npp_maker_phrase_replay"


class MakerPhraseReplayTests(unittest.TestCase):
    def setUp(self):
        temporary = tempfile.TemporaryDirectory()
        self.addCleanup(temporary.cleanup)
        self.root = Path(temporary.name)
        self.catalog = self.root / "makers.json"

    def write_makers(self, makers):
        self.catalog.write_text(json.dumps({"makers": makers}), encoding="utf-8")

    def bloom(self):
        makers = {"Bloom": {"name": "Bloom", "place": "Test Town"}}
        self.write_makers(makers)
        return makers

    def invoke(self, code, trailer, *, path=None):
        stdout, stderr = io.StringIO(), io.StringIO()
        with patch.object(replay, "MAKERS", path or self.catalog), redirect_stdout(stdout), redirect_stderr(stderr):
            result = replay.main([])
        return self.assert_result(result, stdout.getvalue(), stderr.getvalue(), code, trailer)

    def cli(self, *args):
        return subprocess.run([sys.executable, "-B", str(SCRIPT), *args], cwd=self.root,
                              capture_output=True, text=True, timeout=15)

    def assert_result(self, result, stdout, stderr, code, trailer):
        self.assertEqual(result, code)
        self.assertEqual(stderr, "")
        lines = stdout.splitlines()
        self.assertTrue(lines, "missing status trailer")
        self.assertEqual(lines[-1], trailer)
        return lines

    def assert_findings(self, lines, *expected):
        self.assertEqual([line for line in lines[:-1] if line.startswith("FAIL ")], list(expected))

    def assert_input_failure(self, reason, *, path=None):
        # Bad data must stop before any replay or partial counts.
        with patch.object(replay.missing, "_maker") as maker:
            self.assertEqual(self.invoke(1, FAIL, path=path), [f"FAIL {reason} makers", FAIL])
        maker.assert_not_called()

    def test_c1_full_pass(self):
        # A clean run must succeed even when there are zero phrases to replay.
        self.write_makers({})
        self.assertEqual(self.invoke(0, PASS), [
            "tried key 0", "tried name 0", "tried lower 0", "tried the 0", "tried plural 0",
            "tried no-apostrophe 0", "tried ascii 0", PASS,
        ])

    def test_c2_findings_trailer(self):
        # The failure trailer must follow all findings, not just the first kind.
        self.bloom()
        with patch.object(replay.missing, "_maker", side_effect=[
            replay.missing.Maker(s) for s in ("ambiguous", "known", "known", "new", "new")
        ]):
            lines = self.invoke(1, FAIL)
        self.assert_findings(lines, "FAIL maker-phrase-ambiguous key 1",
                             "FAIL maker-phrase-research the 1", "FAIL maker-phrase-research plural 1")

    def test_c2_1_input_unsafe(self):
        # A valid target is still unsafe if reached through a symlink.
        self.bloom()
        link = self.root / "alias.json"
        link.symlink_to(self.catalog)
        for path in (link, self.root):
            with self.subTest(path=path.name):
                self.assert_input_failure("input-unsafe", path=path)

    def test_c2_2_input_too_large(self):
        # Oversize takes precedence over errors in the contents.
        self.catalog.write_bytes(b"not-json")
        with patch.object(replay, "MAKERS_CAP", 7):
            self.assert_input_failure("input-too-large")

    def test_c2_3_input_unreadable(self):
        # Missing, undecodable, invalid and malformed inputs share one safe reason.
        with self.subTest(case="missing"):
            self.assert_input_failure("input-unreadable")
        for case, raw in (
            ("utf8", b"\xff"), ("json", b"{"), ("non-json number", b'{"makers":{},"ignored":NaN}'),
            ("outer", b"[]"), ("makers", b'{"makers":[]}'),
            ("record", b'{"makers":{"Bloom":[]}}'),
            ("name", b'{"makers":{"Bloom":{"name":0,"place":"Test Town"}}}'),
            ("place", b'{"makers":{"Bloom":{"name":"Bloom"}}}'),
            ("story", b'{"makers":{"Bloom":{"name":"Bloom","place":"Test Town","story":0}}}'),
            ("url", b'{"makers":{"Bloom":{"name":"Bloom","place":"Test Town","url":null}}}'),
        ):
            with self.subTest(case=case):
                self.catalog.write_bytes(raw)
                self.assert_input_failure("input-unreadable")

    def test_c2_4_maker_phrase_research(self):
        # `new` must aggregate by kind, not print one finding per phrase.
        self.write_makers({"Bloom": {"name": "Bloom", "place": ""}, "Stem": {"name": "Stem", "place": ""}})
        with patch.object(replay.missing, "_maker", return_value=replay.missing.Maker("new")):
            lines = self.invoke(1, FAIL)
        self.assert_findings(lines, "FAIL maker-phrase-research key 2", "FAIL maker-phrase-research name 2",
                             "FAIL maker-phrase-research lower 2", "FAIL maker-phrase-research the 2",
                             "FAIL maker-phrase-research plural 2")

    def test_c2_5_maker_phrase_ambiguous(self):
        # A duplicate exact match must not be treated as a benign near match.
        self.write_makers({"stem": {"name": "Bloom", "place": ""}, "bloom": {"name": "Bloom", "place": ""}})
        lines = self.invoke(1, FAIL)
        self.assert_findings(lines, "FAIL maker-phrase-ambiguous key 1", "FAIL maker-phrase-ambiguous name 2",
                             "FAIL maker-phrase-ambiguous lower 2", "FAIL maker-phrase-research the 2",
                             "FAIL maker-phrase-ambiguous plural 2")

    def test_c2_6_state_invalid(self):
        # Reject invalid states as data, even a valid prefix followed by a newline.
        self.bloom()
        for state in ("near\n", "Nested Text", "x" * 21, "", None):
            with self.subTest(state=state), patch.object(replay.missing, "_maker", return_value=replay.missing.Maker(state)):
                lines = self.invoke(1, FAIL)
                self.assert_findings(lines, "FAIL state-invalid")
                self.assertFalse(any(line.startswith("state ") for line in lines))

    def test_c2_7_check_error(self):
        # An exception is neither successful coverage nor safe diagnostic text.
        self.bloom()
        with patch.object(replay.missing, "_maker", side_effect=RuntimeError("synthetic marker")):
            lines = self.invoke(1, FAIL)
        self.assert_findings(lines, "FAIL check-error")
        self.assertNotIn("synthetic marker", "\n".join(lines))

    def test_c3_usage_exit_2(self):
        # No argument, including argparse's implicit help flag, is accepted.
        for args in (("--unknown",), ("extra",), ("--help",), ("-h",), ("--",)):
            with self.subTest(args=args):
                result = self.cli(*args)
                self.assertEqual(result.returncode, 2)
                self.assertEqual(result.stdout, "")  # no last stdout line for usage errors
                self.assertTrue(result.stderr.startswith("usage: "))

    def test_c4_read_only(self):
        # A report might accidentally regenerate derived files or write a cache.
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
        self.assert_result(result.returncode, result.stdout, result.stderr, 1, FAIL)
        self.assertEqual(snapshot(), before)
        self.assertEqual(list(self.root.iterdir()), [])

    def test_c5_output_shape(self):
        # Reversed insertion order and distinct spellings catch order, transform,
        # or disclosure regressions; state order is sorted, not first seen.
        makers = {"z-key": {"name": "Néb'ula’s", "place": ""}, "a-key": {"name": "Sprig", "place": ""}}
        self.write_makers(makers)
        states = ["near"] * 5 + ["known"] * 7
        with patch.object(replay.missing, "_maker", side_effect=map(replay.missing.Maker, states)) as maker:
            lines = self.invoke(0, PASS)
        expected_phrases = [
            "a-key", "Sprig", "sprig", "the Sprig", "Sprigs", "z-key", "Néb'ula’s", "néb'ula’s",
            "the Néb'ula’s", "Néb'ula’", "Nébulas", "Neb'ula’s",
        ]
        evidence = {"brand_on_label": None, "confidence": {"brand": 0.0}}
        self.assertEqual(maker.call_args_list, [call(phrase, evidence, makers) for phrase in expected_phrases])
        self.assertEqual(lines, [
            "tried key 2", "state key known 1", "state key near 1",
            "tried name 2", "state name known 1", "state name near 1",
            "tried lower 2", "state lower known 1", "state lower near 1",
            "tried the 2", "state the known 1", "state the near 1",
            "tried plural 2", "state plural known 1", "state plural near 1",
            "tried no-apostrophe 1", "state no-apostrophe known 1",
            "tried ascii 1", "state ascii known 1", PASS,
        ])

    def test_c6_fixture_pass(self):
        # All-known results from a nonempty catalog must pass without skipping any kind.
        self.bloom()
        with patch.object(replay.missing, "_maker", return_value=replay.missing.Maker("known")):
            self.assertEqual(self.invoke(0, PASS), [
                "tried key 1", "state key known 1", "tried name 1", "state name known 1",
                "tried lower 1", "state lower known 1", "tried the 1", "state the known 1",
                "tried plural 1", "state plural known 1", "tried no-apostrophe 0", "tried ascii 0", PASS,
            ])

    def test_c7_live_pins(self):
        # The shipped catalog and real resolver anchor this baseline, not a mock.
        result = self.cli()
        self.assertEqual(self.assert_result(result.returncode, result.stdout, result.stderr, 1, FAIL), [
            "tried key 26", "state key known 26", "tried name 26", "state name known 26",
            "tried lower 26", "state lower known 26", "tried the 26", "state the new 26",
            "tried plural 26", "state plural near 26", "tried no-apostrophe 4", "state no-apostrophe near 4",
            "tried ascii 0", "FAIL maker-phrase-research the 26", FAIL,
        ])


if __name__ == "__main__":
    unittest.main()
