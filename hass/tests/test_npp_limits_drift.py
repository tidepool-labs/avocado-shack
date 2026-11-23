"""Fixture-only CLI tests for the NPP catalog length comparison."""

import json
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest


ROOT = Path(__file__).resolve().parents[2]
SCRIPT = ROOT / "scripts/hass/npp_limits_drift.py"
LIMITS = ROOT / "hass/npp/assets/hass-gallery-style/limits.json"
PASS = "PASS npp_limits_drift"
FAIL = "FAIL npp_limits_drift"


class NppLimitsDriftTests(unittest.TestCase):
    def setUp(self):
        temporary = tempfile.TemporaryDirectory()
        self.addCleanup(temporary.cleanup)
        self.root = Path(temporary.name).resolve()
        # Check the reported baseline against the committed asset, not a second copy.
        self.baseline = json.loads(LIMITS.read_text(encoding="utf-8"))["fields"]

    def write(self, directory, key, rows):
        (directory / f"{key}.json").write_text(json.dumps({key: rows}), encoding="utf-8")

    def catalog(self, products, makers, directory=None):
        directory = self.root if directory is None else directory
        self.write(directory, "products", products)
        self.write(directory, "makers", makers)

    def cli(self, *args):
        return subprocess.run(
            [sys.executable, "-B", str(SCRIPT), *args],
            cwd=self.root, capture_output=True, text=True, timeout=10,
        )

    def run_catalog(self, directory=None):
        return self.cli("--content", str(self.root if directory is None else directory))

    def assert_outcome(self, result, code, last, findings=()):
        self.assertEqual(result.returncode, code, result.stderr)
        self.assertEqual(result.stderr, "")
        lines = result.stdout.splitlines()
        self.assertTrue(lines)
        self.assertEqual(lines[-1], last)
        self.assertEqual([line for line in lines[:-1] if line.startswith("FAIL ")], list(findings))
        return lines

    def field_lines(self, key, chars, words):
        return [
            f"field {key} chars-p90 {self.baseline[key]['chars']['p90']} {chars}",
            f"field {key} words-p90 {self.baseline[key]['words']['p90']} {words}",
        ]

    def test_c1_full_pass(self):
        # Baseline disagreement and copy above the soft target are not findings.
        self.catalog([{"status": "active", "name": "Pear", "description": "x" * 180,
                       "imageAlt": "Two pears", "producerKey": "maker-a"}],
                     {"maker-a": {"story": "A tiny tale"}})
        lines = self.assert_outcome(self.run_catalog(), 0, PASS)
        self.assertCountEqual(lines[:-1], [
            "records 1",
            *self.field_lines("name", 4, 1),
            *self.field_lines("description", 180, 1),
            *self.field_lines("image_alt", 9, 2),
            *self.field_lines("maker_story", 11, 3),
        ])

    def test_c2_1_unreadable(self):
        # Missing files, symlinks and decoding/envelope errors must not look like empty data.
        for key, valid, wrong_container in (("products", [], {}), ("makers", {}, [])):
            for case in ("missing", "symlink", "dangling", "directory", "utf8", "syntax",
                         "non-json-number", "root", "wrong-key", "container", "row"):
                with self.subTest(file=key, case=case):
                    directory = self.root / f"{key}-{case}"
                    directory.mkdir()
                    other = "makers" if key == "products" else "products"
                    self.write(directory, other, {} if other == "makers" else [])
                    path = directory / f"{key}.json"
                    if case in ("symlink", "dangling"):
                        target = directory / "target.json"
                        if case == "symlink":
                            target.write_text(json.dumps({key: valid}), encoding="utf-8")
                        path.symlink_to(target)
                    elif case == "directory":
                        path.mkdir()
                    elif case != "missing":
                        raw = {
                            "utf8": b'"\xff"', "syntax": b"{", "root": b"[]",
                            "wrong-key": b"{}", "container": json.dumps({key: wrong_container}).encode(),
                            "non-json-number": json.dumps({key: valid, "extra": float("nan")}).encode(),
                            "row": json.dumps({key: [0] if key == "products" else {"a": 0}}).encode(),
                        }[case]
                        path.write_bytes(raw)
                    self.assert_outcome(self.run_catalog(directory), 1, FAIL, (f"FAIL unreadable {key}",))
        self.assert_outcome(self.run_catalog(), 1, FAIL,
                            ("FAIL unreadable products", "FAIL unreadable makers"))

    def test_c2_2_over_hard_max(self):
        # Check each finding alone and together. Deduplicate keys, not identical stories.
        hard = json.loads(LIMITS.read_text(encoding="utf-8"))["limits"]
        desc_max = hard["description"]["hard_max_chars"]
        story_max = hard["maker_story"]["hard_max_chars"]
        for desc_over, story_over in ((True, False), (False, True), (True, True)):
            with self.subTest(desc_over=desc_over, story_over=story_over):
                self.catalog([
                    {"status": "active", "producerKey": key, "description": "é" * length}
                    for key, length in (("a", desc_max + desc_over), ("a", desc_max + 2 * desc_over),
                                        ("b", desc_max), ("c", desc_max))
                ], {key: {"story": "é" * (story_max + (story_over if key != "c" else 0))}
                    for key in ("a", "b", "c")})
                findings = []
                if desc_over:
                    findings.append("FAIL over-hard-max description 2")
                if story_over:
                    findings.append("FAIL over-hard-max maker_story 2")
                self.assert_outcome(self.run_catalog(), 1, FAIL, findings)

    def test_c3_usage_exit_2(self):
        # Usage failures must not be converted to catalog findings.
        for args in ((), ("--content",), ("--content", str(self.root), "--unknown")):
            with self.subTest(argc=len(args)):
                result = self.cli(*args)
                self.assertEqual(result.returncode, 2)
                self.assertEqual(result.stdout, "")  # No last stdout line on a usage error.
                self.assertTrue(result.stderr.startswith("usage:"))
                self.assertEqual(result.stderr.splitlines()[-1],
                                 "npp_limits_drift.py: error: invalid arguments; provide --content DIR")

    def test_c4_read_only(self):
        # A writer could preserve JSON meaning while rewriting bytes or adding a sidecar.
        self.catalog([], {})
        files = sorted(self.root.iterdir())
        before = [(path.read_bytes(), path.stat().st_mtime_ns) for path in files]
        dir_mtime = self.root.stat().st_mtime_ns
        self.assert_outcome(self.run_catalog(), 0, PASS)
        self.assertEqual(sorted(self.root.iterdir()), files)
        self.assertEqual([(path.read_bytes(), path.stat().st_mtime_ns) for path in files], before)
        self.assertEqual(self.root.stat().st_mtime_ns, dir_mtime)

    def test_c5_no_private_values(self):
        # Scan success, input failure and usage output, including argparse's echoed arguments.
        product = {"status": "active", "id": "synthetic-record-canary",
                   "producerKey": "synthetic-maker-canary", "description": "synthetic copy canary",
                   "message": "synthetic message canary", "chat": "synthetic-chat-canary",
                   "sender": "synthetic-sender-canary", "digest": "a7" * 32}
        story = "synthetic story canary"
        self.catalog([product], {product["producerKey"]: {"story": story}})
        good = self.run_catalog()
        (self.root / "products.json").write_bytes(json.dumps(product).encode() + b"!")
        bad = self.run_catalog()
        usage = self.cli("--content", str(self.root), str(self.root / "unexpected"))
        canaries = [value for key, value in product.items() if key != "status"] + [story, str(self.root)]
        for result in (good, bad, usage):
            for canary in canaries:
                self.assertNotIn(canary, result.stdout)
                self.assertNotIn(canary, result.stderr)
        self.assert_outcome(good, 0, PASS)
        self.assert_outcome(bad, 1, FAIL, ("FAIL unreadable products",))
        self.assertEqual((usage.returncode, usage.stdout), (2, ""))

    def test_c6_p90_nearest_rank(self):
        # The ninth of ten text values is 17 chars / 9 words; blanks must not shift that rank.
        products = [{"status": "active", "name": " ".join(["é"] * n)} for n in range(10, 0, -1)]
        products += [{"status": "active", "name": value} for value in ("", " \t", None)] * 4
        self.catalog(products, {})
        lines = self.assert_outcome(self.run_catalog(), 0, PASS)
        self.assertIn("records 22", lines)
        for line in self.field_lines("name", 17, 9) + self.field_lines("maker_story", 0, 0):
            self.assertIn(line, lines)

    def test_c7_inactive_ignored(self):
        # An inactive product or an unreferenced maker would inflate the p90 and trigger findings.
        self.catalog([
            {"status": "active", "producerKey": "a", "name": "Fig", "description": "A fig", "imageAlt": "Fig"},
            {"status": "inactive", "producerKey": "b", "name": "x" * 999,
             "description": "x" * 999, "imageAlt": "x" * 999},
            {"producerKey": "b", "description": "x" * 999},
        ], {"a": {"story": "A tale"}, "b": {"story": "x" * 999}, "c": {"story": "x" * 999}})
        lines = self.assert_outcome(self.run_catalog(), 0, PASS)
        self.assertCountEqual(lines[:-1], [
            "records 1",
            *self.field_lines("name", 3, 1),
            *self.field_lines("description", 5, 2),
            *self.field_lines("image_alt", 3, 1),
            *self.field_lines("maker_story", 6, 2),
        ])
