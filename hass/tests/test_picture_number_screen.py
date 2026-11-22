"""Fixture-only tests for the offline picture-number replay CLI."""

from contextlib import redirect_stdout
import importlib.util
import io
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import patch


SCRIPT = Path(__file__).resolve().parents[2] / "scripts/hass/picture_number_screen.py"
PASS = "PASS picture_number_screen"
FAIL = "FAIL picture_number_screen"
PINNED = (
    ("Harbor Lane Jam 12 oz", "Harbor Lane Jam 12 oz", ["12 oz"], "clean"),
    ("Harbor Lane Jam 12 oz", "Harbor Lane Jam", ["12 oz"], "clean"),
    ("Jam $4.99", "Jam", [], "money"),
    ("Jam", "Jam", [], "clean"),
    (None, "Jam", [], "picture-unreadable"),
    ("Jam 3", "Jam 3", [], "clean"),
    ("Jam about 3", "Jam about 3", ["3"], "number-unclear"),
)
CLEAN_ROW = b'{"read":"Jam","source_read":"Jam"}'


def pinned_bytes(rows):
    return b"\n".join(json.dumps(dict(read=read, source_read=source, label_words=labels)).encode()
                      for read, source, labels, _ in rows)


class PictureNumberScreenTests(unittest.TestCase):
    def setUp(self):
        temporary = tempfile.TemporaryDirectory()
        self.addCleanup(temporary.cleanup)
        self.root = Path(temporary.name).resolve()
        self.reads = self.root / "reads.jsonl"

    def run_cli(self, *args):
        return subprocess.run([sys.executable, "-B", str(SCRIPT), *args], cwd=self.root,
                              capture_output=True, text=True, timeout=10)

    def replay(self, data):
        self.reads.write_bytes(data)
        return self.run_cli("--reads", str(self.reads))

    def assert_result(self, result, code, expected):
        self.assertEqual(result.returncode, code, result.stderr)
        self.assertEqual(result.stderr, "")
        self.assertEqual(result.stdout, "\n".join(expected) + "\n")

    def assert_refused(self, result, reason):
        self.assert_result(result, 1, [f"FAIL {reason}", FAIL])

    def test_c1_full_pass(self):
        # Blank lines are skipped, not replayed or used to renumber physical lines.
        result = self.replay(b"\n \t\n" + CLEAN_ROW + b"\r\n\n" + CLEAN_ROW)
        self.assert_result(result, 0, ["line 3 clean", "line 5 clean", "reads 2", "count clean 2", PASS])

    def test_c2_findings_trailer(self):
        # A finding must not use a PASS trailer or a successful process status.
        self.assert_refused(self.run_cli("--reads", str(self.reads)), "unsafe-input")

    def test_c2_1_unsafe_input(self):
        # A link to valid input must not pass; a FIFO must not block the read.
        self.reads.write_bytes(CLEAN_ROW)
        symlink = self.root / "link.jsonl"
        symlink.symlink_to(self.reads)
        fifo = self.root / "pipe"
        os.mkfifo(fifo)
        for path in (symlink, self.root, fifo):
            with self.subTest(kind=path.name):
                self.assert_refused(self.run_cli("--reads", str(path)), "unsafe-input")

    def test_c2_2_too_large(self):
        # A clean prefix must not pass if an oversized tail would be truncated.
        data = CLEAN_ROW.ljust(1_000_000)
        self.assert_result(self.replay(data), 0, ["line 1 clean", "reads 1", "count clean 1", PASS])
        self.assert_refused(self.replay(data + b" "), "too-large")

    def test_c2_3_not_utf8(self):
        # Decode the whole file before emitting any result, even with a valid prefix.
        self.assert_refused(self.replay(CLEAN_ROW + b"\n\xff"), "not-utf8")

    def test_c2_4_too_many_lines(self):
        # The limit is inclusive and counts only non-blank lines.
        data = (CLEAN_ROW + b"\n\n") * 2000
        expected = [f"line {k} clean" for k in range(1, 4000, 2)]
        self.assert_result(self.replay(data), 0, [*expected, "reads 2000", "count clean 2000", PASS])
        self.assert_refused(self.replay(data + CLEAN_ROW), "too-many-lines")

    def test_c2_5_not_clean(self):
        # Malformed rows are counted, must not abort replay, and never reach the checker.
        malformed = (
            b'{"read":}', b'{} trailing', b'[]', b'null', b'"text"', b'0', b'true',
            b'{"label_words":null}', b'{"label_words":{}}', b'{"label_words":"word"}',
            b'{"label_words":0}', b'{"label_words":false}', b'{"read":NaN}',
        )
        n = len(malformed)
        result = self.replay(b"\n".join((*malformed, CLEAN_ROW)))
        self.assert_result(result, 1, [
            *(f"line {k} malformed" for k in range(1, n + 1)), f"line {n + 1} clean",
            f"reads {n + 1}", f"count malformed {n}", "count clean 1", f"FAIL not-clean {n}", FAIL,
        ])

    def test_c3_usage_exit_2(self):
        # Usage errors cannot be confused with findings or emit a stdout trailer.
        self.reads.write_bytes(CLEAN_ROW)
        for args in ((), ("--reads",), ("--reads", str(self.reads), "--unknown")):
            with self.subTest(argc=len(args)):
                result = self.run_cli(*args)
                self.assertEqual(result.returncode, 2)
                self.assertEqual(result.stdout, "")
                self.assertEqual(result.stderr.splitlines()[-1],
                                 "picture_number_screen.py: error: expected --reads FILE")
                self.assertTrue(result.stderr.startswith("usage:"))

    def test_c4_read_only(self):
        # Catch an identical rewrite, an adjacent sidecar, or a transient directory entry.
        self.reads.write_bytes(CLEAN_ROW)
        file_mtime = self.reads.stat().st_mtime_ns
        dir_mtime = self.root.stat().st_mtime_ns
        before = set(self.root.iterdir())
        self.assert_result(self.run_cli("--reads", str(self.reads)), 0,
                           ["line 1 clean", "reads 1", "count clean 1", PASS])
        self.assertEqual(self.reads.read_bytes(), CLEAN_ROW)
        self.assertEqual(self.reads.stat().st_mtime_ns, file_mtime)
        self.assertEqual(self.root.stat().st_mtime_ns, dir_mtime)
        self.assertEqual(set(self.root.iterdir()), before)

    def test_c5_no_private_values(self):
        # Neither data errors nor argv/OS diagnostics can echo private inputs.
        read, source, label = "fixture-read-canary", "fixture-source-canary", "fixture-label-canary"
        data = json.dumps(dict(read=read, source_read=source, label_words=[label])).encode()
        normal = self.replay(data + b"\n{" + read.encode())
        self.assert_result(normal, 1, ["line 1 clean", "line 2 malformed", "reads 2", "count clean 1",
                                       "count malformed 1", "FAIL not-clean 1", FAIL])
        missing_path = self.root / "missing.jsonl"
        missing = self.run_cli("--reads", str(missing_path))
        self.assert_refused(missing, "unsafe-input")
        usage = self.run_cli("--reads", str(self.reads), str(missing_path))
        self.assertEqual((usage.returncode, usage.stdout), (2, ""))
        self.assertEqual(usage.stderr.splitlines()[-1],
                         "picture_number_screen.py: error: expected --reads FILE")
        for result in (normal, missing, usage):
            for marker in (read, source, label, str(self.root)):
                self.assertFalse(marker in result.stdout + result.stderr, "private value echoed")

    def test_c6_clean_rows(self):
        # Passing unchanged labels and readable digits must not be treated as findings.
        clean = [row for row in PINNED if row[-1] == "clean"]
        self.assert_result(self.replay(pinned_bytes(clean)), 0,
                           ["line 1 clean", "line 2 clean", "line 3 clean", "line 4 clean",
                            "reads 4", "count clean 4", PASS])

    def test_c7_pinned_rows(self):
        # Real checker reasons must remain distinct and in input order, not collapsed.
        self.assert_result(self.replay(pinned_bytes(PINNED)), 1, [
            *(f"line {k} {row[-1]}" for k, row in enumerate(PINNED, 1)),
            "reads 7", "count clean 4", "count money 1", "count picture-unreadable 1",
            "count number-unclear 1", "FAIL not-clean 3", FAIL,
        ])

    def test_unprintable_checker_reasons_are_other(self):
        # A prefix match or unconditional echo can print a free-text checker result.
        spec = importlib.util.spec_from_file_location("picture_number_screen", SCRIPT)
        assert spec is not None and spec.loader is not None
        script = importlib.util.module_from_spec(spec)
        old_path = sys.path[:]
        self.addCleanup(sys.path.__setitem__, slice(None), old_path)
        spec.loader.exec_module(script)
        self.reads.write_bytes(b"\n".join([CLEAN_ROW] * 5))
        output = io.StringIO()
        with patch.object(script, "picture_problem", side_effect=[
            "a" * 30, "a" * 31, "money\n", "Fixture text", "",
        ]), redirect_stdout(output):
            code = script.main(["--reads", str(self.reads)])
        self.assertEqual(code, 1)
        self.assertEqual(output.getvalue().splitlines(), [
            "line 1 " + "a" * 30, "line 2 other", "line 3 other", "line 4 other", "line 5 other",
            "reads 5", "count " + "a" * 30 + " 1", "count other 4", "FAIL not-clean 5", FAIL,
        ])


if __name__ == "__main__":
    unittest.main()
