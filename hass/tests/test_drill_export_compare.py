"""Fixture-only CLI contract for the restore drill's transcript comparison."""

import hashlib
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest


SCRIPT = Path(__file__).resolve().parents[2] / "scripts/hass/drill_export_compare.py"
PASS = "PASS drill_export_compare"
FAIL = "FAIL drill_export_compare"


class DrillExportCompareTests(unittest.TestCase):
    def setUp(self):
        temporary = tempfile.TemporaryDirectory()
        self.addCleanup(temporary.cleanup)
        self.root = Path(temporary.name).resolve()
        self.backup = self.root / "backup" / "export.jsonl"
        self.restored = self.root / "restored" / "export.jsonl"
        for path in (self.backup, self.restored):
            path.parent.mkdir()
        self.options = ("--backup-export", str(self.backup),
                        "--restored-export", str(self.restored))

    def write_exports(self, backup, restored):
        self.backup.write_bytes(backup)
        self.restored.write_bytes(restored)

    def invoke(self, *options):
        return subprocess.run(
            [sys.executable, "-B", str(SCRIPT), *options], cwd=self.root,
            capture_output=True, text=True, timeout=10,
        )

    def assert_result(self, code, backup_count, restored_count, *tail):
        result = self.invoke(*self.options)
        self.assertEqual(result.returncode, code, result.stderr)
        self.assertEqual(result.stderr, "")
        self.assertEqual(result.stdout.splitlines(), [
            f"count backup {backup_count}", f"count restored {restored_count}", *tail,
        ])
        return result

    def test_c1_full_pass(self):
        # Detect hashing raw/terminated bytes or reordering the records.
        data = b'{"id":2}\n{"id":1}\n'
        self.write_exports(data, data)
        prefix = hashlib.sha256(data[:-1]).hexdigest()[:12]
        self.assert_result(0, 2, 2, f"digest {prefix}", PASS)

    def test_c2_1_no_file(self):
        # Both a missing path and a directory must produce role-specific findings.
        self.restored.mkdir()
        self.assert_result(1, 0, 0, "FAIL no-file backup", "FAIL no-file restored", FAIL)

    def test_c2_2_bad_line(self):
        # Report physical line numbers even across blanks, with one finding per file.
        self.write_exports(b'\n{"id":1}\n[]\nnull\n', b'{"id":1}\n{"text":"\xff"}\n{\n')
        self.assert_result(1, 1, 1, "FAIL bad-line backup 3", "FAIL bad-line restored 2", FAIL)
        self.write_exports(b'{"id":1}\n{\n', b'{"id":1}\n{"id":NaN}\n')
        self.assert_result(1, 1, 1, "FAIL bad-line backup 2", "FAIL bad-line restored 2", FAIL)

        # Last-key-wins decoding would discard the first value and falsely pass.
        clean = b'{"meta":[{"nested-canary":"same"}]}\n'
        duplicate = b'{"meta":[{"nested-canary":"different","nested-canary":"same"}]}\n'
        for role, backup, restored, counts in (
            ("backup", duplicate, clean, (0, 1)),
            ("restored", clean, duplicate, (1, 0)),
        ):
            with self.subTest(role=role):
                self.write_exports(backup, restored)
                self.assert_result(1, *counts, f"FAIL bad-line {role} 1", FAIL)

    def test_c2_3_empty(self):
        # Two blank exports must not pass just because their canonical lists agree.
        self.write_exports(b"", b" \t\r\n\n")
        self.assert_result(1, 0, 0, "FAIL empty", FAIL)

    def test_c2_4_count_mismatch(self):
        # Zip alone would accept the matching prefix and miss the extra row.
        self.write_exports(b'{"id":1}\n', b'{"id":1}\n{"id":2}\n')
        self.assert_result(1, 1, 2, "FAIL count-mismatch", FAIL)

    def test_c2_5_first_diff(self):
        # Comparing as a set would miss reordered rows; only the first diff is reported.
        self.write_exports(b'{"id":1}\n{"id":2}\n{"id":3}\n',
                           b'{"id":1}\n{"id":3}\n{"id":2}\n')
        self.assert_result(1, 3, 3, "FAIL first-diff 2", FAIL)

    def test_c3_usage_exit_2(self):
        # Invalid CLI syntax must not look like a completed comparison.
        for options in (self.options[:2], self.options + ("--unknown",), self.options[:-1]):
            with self.subTest(options=options):
                result = self.invoke(*options)
                self.assertEqual(result.returncode, 2)
                self.assertEqual(result.stdout, "")  # No final stdout line for C3.
                self.assertTrue(result.stderr.startswith("usage:"))

    def test_c4_read_only(self):
        # Detect both in-place canonicalization and persistent scratch files.
        raw = b' { "id": 1 }\n'
        self.write_exports(raw, raw)
        stamp = 1_234_567_890_123_456_789
        inputs = (self.backup, self.restored)
        for path in inputs:
            os.utime(path, ns=(stamp, stamp))
        before = [(path.stat().st_mtime_ns, path.parent.stat().st_mtime_ns) for path in inputs]
        prefix = hashlib.sha256(b'{"id":1}').hexdigest()[:12]
        self.assert_result(0, 1, 1, f"digest {prefix}", PASS)
        for path, (mtime, directory_mtime) in zip(inputs, before):
            self.assertEqual(path.read_bytes(), raw)
            self.assertEqual(path.stat().st_mtime_ns, mtime)
            self.assertEqual(path.parent.stat().st_mtime_ns, directory_mtime)
            self.assertEqual(set(path.parent.iterdir()), {path})

    def test_c5_no_private_values(self):
        # A raw diff, parser diagnostic or expanded digest could leak private values.
        record = {"chat": "fixture-chat-canary", "sender": "fixture-sender-canary",
                  "text": "fixture-text-canary", "provider_id": "fixture-full-id-canary",
                  "attachment_digest": hashlib.sha256(b"fixture attachment").hexdigest()}
        raw = json.dumps(record, sort_keys=True, separators=(",", ":")).encode()
        digest = hashlib.sha256(raw).hexdigest()
        canaries = (*record.values(), digest, str(self.backup), str(self.restored))

        def assert_private(result):
            for canary in canaries:
                self.assertNotIn(canary, result.stdout)
                self.assertNotIn(canary, result.stderr)

        self.write_exports(raw, raw)
        assert_private(self.assert_result(0, 1, 1, f"digest {digest[:12]}", PASS))
        self.restored.write_bytes(raw.replace(b"fixture-text", b"fixture-alt"))
        assert_private(self.assert_result(1, 1, 1, "FAIL first-diff 1", FAIL))
        self.restored.write_bytes(raw[:-1])
        assert_private(self.assert_result(1, 1, 0, "FAIL bad-line restored 1", FAIL))
        result = self.invoke(*self.options, "--unknown", str(self.backup), record["text"])
        self.assertEqual(result.returncode, 2)
        self.assertEqual(result.stdout, "")
        assert_private(result)

    def test_c6_canonical_equal(self):
        # Raw bytes differ in whitespace, nested key order and Unicode spelling.
        self.write_exports(b'\n {"text":"\\u00e9", "meta":{"z":2,"a":1}} \r\n',
                           '{ "meta": {"a": 1, "z": 2}, "text": "é" }'.encode("utf-8"))
        canonical = b'{"meta":{"a":1,"z":2},"text":"\\u00e9"}'
        self.assert_result(0, 1, 1, f"digest {hashlib.sha256(canonical).hexdigest()[:12]}", PASS)
