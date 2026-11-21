"""Offline contract tests for the label case coverage CLI."""

import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest

from hass.content_model import CATEGORIES

SCRIPT = Path(__file__).resolve().parents[2] / "scripts/hass/label_case_coverage.py"
PASS = "PASS label_case_coverage"
FAIL = "FAIL label_case_coverage"


def rows_for(categories):
    return [
        {"id": f"fixture-{i}", "photo": f"fixture-{i}.jpg",
         "expected": {"name": "Fixture product", "brand": "Fixture brand", "category": category}}
        for i, category in enumerate(categories)
    ]


class LabelCaseCoverageTests(unittest.TestCase):
    def setUp(self):
        temp = tempfile.TemporaryDirectory()
        self.addCleanup(temp.cleanup)
        self.root = Path(temp.name).resolve()
        self.cases = self.root / "cases.jsonl"

    def write_cases(self, rows):
        self.cases.write_text("".join(json.dumps(row) + "\n" for row in rows), encoding="utf-8")

    def run_cli(self, *args):
        return subprocess.run(
            [sys.executable, "-B", str(SCRIPT), *args], cwd=self.root,
            capture_output=True, text=True, timeout=10,
        )

    def run_cases(self, minimum=1):
        return self.run_cli("--min", str(minimum), "--cases", str(self.cases))

    def assert_report(self, result, code, trailer):
        self.assertEqual(result.returncode, code)
        self.assertEqual(result.stderr, "")
        lines = result.stdout.splitlines()
        self.assertEqual(lines[-1:], [trailer])
        return lines

    def test_c1_full_pass(self):
        # A strict > threshold or treating out-of-catalog values as findings would fail.
        rows = rows_for(CATEGORIES * 2 + ("fixture-unknown", None))
        rows[-1]["expected"].update(name=None, brand=None)
        self.write_cases(rows)
        lines = self.assert_report(self.run_cases(minimum=2), 0, PASS)
        self.assertEqual(lines[-3:], [
            "note other-category 2",
            f"fields name {len(rows)} brand {len(rows)} category {len(rows)}",
            PASS,
        ])
        self.assertFalse(any(line.startswith("FAIL ") for line in lines))

    def test_c2_findings_trailer(self):
        # An empty but parseable case file must report all gaps, not silently pass.
        self.write_cases([])
        lines = self.assert_report(self.run_cases(), 1, FAIL)
        self.assertEqual(lines[0], "cases 0")
        self.assertEqual([line for line in lines if line.startswith("FAIL ")], [
            *(f"FAIL thin-category {category} 0" for category in CATEGORIES), FAIL,
        ])

    def test_c2_1_unsafe_input(self):
        # is_file alone follows links; opening a FIFO instead of rejecting can block.
        self.write_cases(rows_for(CATEGORIES))
        link = self.root / "alias.jsonl"
        link.symlink_to(self.cases)
        dangling = self.root / "dangling.jsonl"
        dangling.symlink_to(self.root / "missing.jsonl")
        fifo = self.root / "pipe"
        os.mkfifo(fifo)
        for path in (link, dangling, fifo, self.root, self.root / "missing.jsonl"):
            with self.subTest(kind=path.name):
                result = self.run_cli("--min", "1", "--cases", str(path))
                self.assertEqual(self.assert_report(result, 1, FAIL), ["FAIL unsafe-input", FAIL])

    def test_c2_2_cases_invalid(self):
        # A malformed final row must stop the report rather than leave partial counts.
        self.write_cases(rows_for(CATEGORIES))
        with self.cases.open("ab") as stream:
            stream.write(b"{\n")
        self.assertEqual(self.assert_report(self.run_cases(), 1, FAIL), ["FAIL cases-invalid", FAIL])

    def test_c2_3_thin_category(self):
        # Mixed 0/1/2 counts catch omitted zeroes, >= instead of <, and sorted output.
        self.write_cases(rows_for(("fruit", "bread", "fruit")))
        lines = self.assert_report(self.run_cases(minimum=2), 1, FAIL)
        self.assertEqual([line for line in lines if line.startswith("FAIL ")], [
            *(f"FAIL thin-category {category} {int(category == 'bread')}"
              for category in CATEGORIES if category != "fruit"), FAIL,
        ])

    def test_c3_usage_exit_2(self):
        # Usage errors must stay with argparse, not become a coverage result.
        for args in ((), ("--min", "0"), ("--min", "-1"), ("--min", "1.5"),
                     ("--min", "word"), ("--min", "1", "--unknown")):
            with self.subTest(args=args):
                result = self.run_cli(*args)
                self.assertEqual(result.returncode, 2)
                self.assertEqual(result.stdout, "")  # No trailer on usage errors.
                self.assertTrue(result.stderr.startswith("usage:"))

    def test_c4_read_only(self):
        # Even a same-byte rewrite changes mtime; sidecars change the directory.
        self.write_cases(rows_for(CATEGORIES))
        before = (self.cases.read_bytes(), self.cases.stat().st_mtime_ns,
                  set(self.root.iterdir()), self.root.stat().st_mtime_ns)
        self.assert_report(self.run_cases(), 0, PASS)
        after = (self.cases.read_bytes(), self.cases.stat().st_mtime_ns,
                 set(self.root.iterdir()), self.root.stat().st_mtime_ns)
        self.assertEqual(after, before)

    def test_c5_no_private_values(self):
        # Row dumps, unknown category values, and parser diagnostics can all leak.
        row = {"id": "private-id", "photo": "private-photo.jpg", "expected": {
            "name": "private-name", "brand": "private-brand", "category": "private-category",
        }}
        self.write_cases(rows_for(CATEGORIES) + [row])
        valid = self.run_cases()
        self.assert_report(valid, 0, PASS)
        self.write_cases([row, row])  # Duplicate IDs go through the loader's error path.
        invalid = self.run_cases()
        self.assert_report(invalid, 1, FAIL)
        usage = self.run_cli("--min", "1", "--unknown", str(self.cases))
        self.assertEqual((usage.returncode, usage.stdout), (2, ""))
        for result in (valid, invalid, usage):
            for canary in (row["id"], row["photo"], *row["expected"].values(), str(self.cases)):
                self.assertFalse(canary in result.stdout or canary in result.stderr, "private value leaked")

    def test_c6_full_cover(self):
        # One case per category catches off-by-one, missing categories, and wrong field totals.
        self.write_cases(rows_for(CATEGORIES))
        lines = self.assert_report(self.run_cases(), 0, PASS)
        count = len(CATEGORIES)
        self.assertEqual(lines, [
            f"cases {count}", *(f"category {category} 1" for category in CATEGORIES),
            "note other-category 0", f"fields name {count} brand {count} category {count}", PASS,
        ])

    def test_c7_live_gaps(self):
        # Pin the checked-in baseline and catch a CLI default path pointing elsewhere.
        lines = self.assert_report(self.run_cli("--min", "1"), 1, FAIL)
        self.assertEqual(lines[0], "cases 10")
        self.assertIn("category fruit 3", lines)
        self.assertEqual([line for line in lines if line.startswith("FAIL ")], [
            "FAIL thin-category flowers 0", "FAIL thin-category general 0", FAIL,
        ])


if __name__ == "__main__":
    unittest.main()
