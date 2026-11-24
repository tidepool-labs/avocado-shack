"""Fixture-only tests of the offline shortlist replay CLI contract."""

from contextlib import redirect_stderr, redirect_stdout
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

SCRIPT = Path(__file__).resolve().parents[2] / "scripts/hass/router_shortlist_replay.py"
SPEC = importlib.util.spec_from_file_location("router_shortlist_replay", SCRIPT)
assert SPEC is not None and SPEC.loader is not None
replay = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(replay)

PASS = "PASS router_shortlist_replay"
FAIL = "FAIL router_shortlist_replay"


def case(case_id: object = "fixture-1", skill: object = "none", **fields):
    return {"id": case_id, "skill": skill, "texts": ["synthetic fixture"], **fields}


class RouterShortlistReplayTests(unittest.TestCase):
    def setUp(self):
        temporary = tempfile.TemporaryDirectory()
        self.addCleanup(temporary.cleanup)
        self.root = Path(temporary.name).resolve()
        self.cases = self.root / "cases.jsonl"

    def write_cases(self, *rows):
        self.cases.write_text("".join(json.dumps(row) + "\n" for row in rows), encoding="utf-8")

    def cli(self, *args):
        return subprocess.run([sys.executable, "-B", str(SCRIPT), *args], cwd=self.root,
                              text=True, capture_output=True, timeout=15)

    def invoke(self, path=None):
        return self.cli("--cases", str(self.cases if path is None else path))

    def in_process(self):
        out, err = io.StringIO(), io.StringIO()
        with redirect_stdout(out), redirect_stderr(err):
            code = replay.main(["--cases", str(self.cases)])
        return subprocess.CompletedProcess([], code, out.getvalue(), err.getvalue())

    def assert_outcome(self, result, code, trailer):
        self.assertEqual(result.returncode, code, result.stderr)
        self.assertEqual(result.stderr, "")
        lines = result.stdout.splitlines()
        self.assertEqual(lines[-1:], [trailer])
        return lines[:-1]

    def assert_findings(self, result, *expected):
        lines = self.assert_outcome(result, 1, FAIL)
        self.assertEqual([line for line in lines if line.startswith("FAIL ")], list(expected))
        return lines

    def test_c1_full_pass(self):
        # Successful checks must end with the exact PASS trailer and status 0.
        self.write_cases(case("a"), case("b"))
        self.assert_outcome(self.invoke(), 0, PASS)

    def test_c2_findings_trailer(self):
        # A mixed run cannot turn green just because a later check succeeds.
        self.cases.write_text("{\n" + json.dumps(case("first", "no.such.skill")) + "\n"
                              + json.dumps(case("last")) + "\n", encoding="utf-8")
        self.assert_findings(self.invoke(), "FAIL case-invalid 1", "FAIL absent first")

    def test_c2_1_unsafe_input(self):
        # Opening a symlink target or a FIFO instead of refusing could read or block.
        self.write_cases(case())
        link = self.root / "link"
        link.symlink_to(self.cases)
        dangling = self.root / "dangling"
        dangling.symlink_to(self.root / "missing")
        fifo = self.root / "fifo"
        os.mkfifo(fifo)
        for path in (link, dangling, self.root, fifo):
            with self.subTest(kind=path.name):
                self.assertEqual(self.assert_findings(self.invoke(path), "FAIL unsafe-input"),
                                 ["FAIL unsafe-input"])

    def test_c2_2_unreadable_input(self):
        # Neither invalid bytes nor an open-time failure may escape as a traceback.
        self.cases.write_bytes(b"\xff\n")
        self.assert_findings(self.invoke(), "FAIL unreadable-input")
        self.write_cases(case())
        with patch.object(replay.os, "open", side_effect=PermissionError(str(self.cases))):
            self.assert_findings(self.in_process(), "FAIL unreadable-input")

    def test_c2_3_too_large(self):
        # The cap is inclusive and must reject, rather than truncate, the next byte.
        limit = 1024 * 1024
        self.cases.write_bytes(b" " * limit)
        self.assert_outcome(self.invoke(), 0, PASS)
        self.cases.write_bytes(b" " * (limit + 1))
        self.assert_findings(self.invoke(), "FAIL too-large")

    def test_c2_4_too_many_lines(self):
        # Blank physical lines still count; a final newline adds no extra line.
        self.cases.write_bytes(b"\n" * 2000)
        self.assert_outcome(self.invoke(), 0, PASS)
        self.cases.write_bytes(b"\n" * 2000 + b" ")
        self.assert_findings(self.invoke(), "FAIL too-many-lines")

    def test_c2_5_case_invalid(self):
        # Partial validation can let later bad turns/photos pass; blanks retain line positions.
        bad_rows = [[], {}, case(1), case(skill=False), case(texts=[]),
                    case(texts="synthetic"), case(texts=["synthetic", 2]), case(photos=None)]
        self.cases.write_text("\n{\n" + "".join(json.dumps(row) + "\n" for row in bad_rows),
                              encoding="utf-8")
        self.assert_findings(self.invoke(), *(f"FAIL case-invalid {n}" for n in range(2, 11)))

    def test_c2_6_skills_invalid(self):
        # Registry exceptions must fail closed without printing their detail.
        self.write_cases(case())
        with patch.object(replay.hass.skills, "load_skills", side_effect=RuntimeError("synthetic-private")):
            self.assert_findings(self.in_process(), "FAIL skills-invalid")

    def test_c2_7_check_error(self):
        # An expect-none case still has to run the check; exceptions must not be treated as absent.
        self.write_cases(case(), case("later", "no.such.skill"))
        with patch.object(replay.router, "candidates", side_effect=[ValueError("synthetic-private"), []]):
            self.assert_findings(self.in_process(), "FAIL check-error", "FAIL absent later")

    def test_c2_8_absent(self):
        # Ordering must come from the file; routing later turns or ignoring attachment
        # presence changes which synthetic cases are actually absent.
        self.write_cases(case("z", "fixture.skill", texts=["first-a", "later"], photos=[{}]),
                         case("control", "fixture.skill", texts=["first-b", "later"], photos=[]),
                         case("a", "fixture.skill", texts=["first-c", "later"]))

        def shortlist(text, *, attachment, skills):
            absent = {("first-a", True), ("first-c", False)}
            return [] if (text, attachment) in absent else [("fixture.skill", 1)]

        with patch.object(replay.router, "candidates", side_effect=shortlist):
            self.assert_findings(self.in_process(), "FAIL absent z", "FAIL absent a")

    def test_c2_9_absent_id_invalid(self):
        # Matching a prefix or accepting an overlength id would emit unapproved data.
        self.write_cases(*(case(case_id, "no.such.skill") for case_id in
                           ("valid-prefix\nFORGED", "a" * 65, "-start", "")))
        lines = self.assert_findings(self.invoke(), *(["FAIL absent-id-invalid"] * 4))
        self.assertIn("absent 4", lines)

    def test_c3_usage_exit_2(self):
        # Usage errors must not become finding runs or write a status trailer.
        for args in (("--cases",), ("--unknown",)):
            with self.subTest(args=args):
                result = self.cli(*args)
                self.assertEqual(result.returncode, 2)
                self.assertEqual(result.stdout, "")  # No last stdout line for usage errors.
                self.assertTrue(result.stderr.splitlines()[-1].endswith(": error: invalid arguments"))

    def test_c4_read_only(self):
        # Rewriting equal bytes or creating sidecars is still a write.
        self.write_cases(case())
        neighbor = self.root / "neighbor"
        neighbor.write_bytes(b"synthetic neighbor")
        before = {path.name: (path.read_bytes(), path.stat().st_mtime_ns) for path in self.root.iterdir()}
        directory_mtime = self.root.stat().st_mtime_ns
        self.assert_outcome(self.invoke(), 0, PASS)
        self.assertEqual({path.name for path in self.root.iterdir()}, before.keys())
        self.assertEqual({path.name: (path.read_bytes(), path.stat().st_mtime_ns)
                          for path in self.root.iterdir()}, before)
        self.assertEqual(self.root.stat().st_mtime_ns, directory_mtime)

    def test_c5_no_private_values(self):
        # Diagnostics, including argparse's unknown-argument path, must redact planted values.
        text, bad_id = "SYNTHETIC MESSAGE CANARY", "SYNTHETIC ID CANARY"
        self.write_cases(case(bad_id, "no.such.skill", texts=[text]))
        result = self.invoke()
        self.assert_findings(result, "FAIL absent-id-invalid")
        usage = self.cli("--cases", str(self.cases), str(self.cases))
        self.assertEqual((usage.returncode, usage.stdout), (2, ""))
        for private in (text, bad_id, str(self.cases)):
            self.assertNotIn(private, result.stdout + result.stderr + usage.stdout + usage.stderr)

    def test_c6_expect_none(self):
        # Expect-none cases count even if the shortlist is nonempty.
        self.write_cases(case("a"), case("b"))
        with patch.object(replay.router, "candidates", return_value=[("fixture.skill", 1)]):
            self.assertEqual(self.assert_outcome(self.in_process(), 0, PASS),
                             ["cases 2", "rank1 0", "top3 0", "absent 0", "expect-none 2"])

    def test_c7_absent_case(self):
        # An unknown expected skill belongs in the miss total, not a registry error.
        self.write_cases(case("x-1", "no.such.skill"))
        self.assertIn("absent 1", self.assert_findings(self.invoke(), "FAIL absent x-1"))

    def test_c8_live_replay(self):
        # An integration pin on the real loader/router and repo-relative default input.
        lines = self.assert_findings(self.cli(), "FAIL absent primary-social-hike", "FAIL absent acc-vague-06",
                                     "FAIL absent acc-vague-07", "FAIL absent acc-refuse-08",
                                     "FAIL absent acc-turns-04", "FAIL absent acc-turns-06")
        self.assertEqual([line for line in lines if not line.startswith("FAIL ")],
                         ["cases 86", "rank1 65", "top3 8", "absent 6", "expect-none 7"])


if __name__ == "__main__":
    unittest.main()
