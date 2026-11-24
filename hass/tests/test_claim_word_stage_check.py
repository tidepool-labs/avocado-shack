"""Offline acceptance tests for the S2/S5 claim agreement CLI."""

from contextlib import redirect_stderr, redirect_stdout
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
SCRIPT = ROOT / "scripts/hass/claim_word_stage_check.py"
SPEC = importlib.util.spec_from_file_location("claim_word_stage_check", SCRIPT)
assert SPEC is not None and SPEC.loader is not None
CHECK = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(CHECK)

PASS = "PASS claim_word_stage_check"
FAIL = "FAIL claim_word_stage_check"
AGREE = b"Organic\njam\n"
DISAGREE = b"Organic\nOrganics\nFarm\njam\n"
CANARY = "syntheticCanaryWord"


class ClaimWordStageCheckTests(unittest.TestCase):
    def setUp(self):
        temporary = tempfile.TemporaryDirectory()
        self.addCleanup(temporary.cleanup)
        self.root = Path(temporary.name).resolve()
        self.words = self.root / "fixture-words.txt"
        self.content = self.root / "fixture-catalog"

    def cli(self, *args):
        result = subprocess.run([sys.executable, "-B", str(SCRIPT), *map(str, args)],
                                cwd=self.root, capture_output=True, text=True, timeout=10)
        return result.returncode, result.stdout, result.stderr

    def main(self, *args):
        out, err = io.StringIO(), io.StringIO()
        with redirect_stdout(out), redirect_stderr(err):
            code = CHECK.main(list(map(str, args)))
        return code, out.getvalue(), err.getvalue()

    def assert_result(self, result, code, trailer, lines=None):
        actual_code, stdout, stderr = result
        self.assertEqual(actual_code, code)
        self.assertEqual(stderr, "")
        self.assertEqual(stdout.splitlines()[-1], trailer)
        if lines is not None:
            self.assertEqual(stdout.splitlines(), [*lines, trailer])

    def assert_failure(self, result, reason):
        self.assert_result(result, 1, FAIL, [f"FAIL {reason}"])

    def test_c1_full_pass(self):
        # A successful CLI run must deliver the status to both shell and stdout.
        self.words.write_bytes(AGREE)
        self.assert_result(self.cli("--words", self.words), 0, PASS)

    def test_c2_findings_trailer(self):
        # A load refusal must not return early before the common failure trailer.
        self.content.mkdir()
        self.assert_failure(self.cli("--content", self.content), "content-invalid")

    def test_c2_1_unsafe_input(self):
        # Path predicates that follow links would accept both linked inputs.
        self.words.write_bytes(AGREE)
        self.content.mkdir()
        linked_file = self.root / "file-link"
        linked_file.symlink_to(self.words)
        linked_dir = self.root / "directory-link"
        linked_dir.symlink_to(self.content, target_is_directory=True)
        missing = self.root / "missing"
        for option, path in (("--words", linked_file), ("--words", self.content),
                             ("--words", missing), ("--content", linked_dir),
                             ("--content", self.words), ("--content", missing)):
            with self.subTest(option=option, fixture=path.name):
                self.assert_failure(self.main(option, path), "unsafe-input")

    def test_c2_2_unreadable_input(self):
        # Opening a regular file can fail; decoding must not replace invalid bytes.
        self.words.write_bytes(b"jam\n\xff\n")
        self.assert_failure(self.main("--words", self.words), "unreadable-input")
        with patch.object(Path, "open", side_effect=PermissionError(CANARY)):
            self.assert_failure(self.main("--words", self.words), "unreadable-input")

    def test_c2_3_too_large(self):
        # A character limit or truncation would accept this oversized UTF-8 input.
        limit = 32 * 1024
        self.words.write_bytes("\u2003".encode() * (limit // 3 + 1))
        self.assert_failure(self.main("--words", self.words), "too-large")
        self.words.write_bytes(b" " * limit)
        self.assert_result(self.main("--words", self.words), 0, PASS)

    def test_c2_4_too_many_lines(self):
        # The limit applies before dropping blank lines, even with CRLF input.
        self.words.write_bytes(b"\r\n" * 1000 + b"jam\r\n")
        self.assert_failure(self.main("--words", self.words), "too-many-lines")
        self.words.write_bytes(b"\r\n" * 999 + b"jam\r\n")
        self.assert_result(self.main("--words", self.words), 0, PASS)

    def test_c2_5_content_invalid(self):
        # Non-I/O loader exceptions still get the same sanitized reason.
        self.content.mkdir()
        with patch.object(CHECK.content_model, "load_content", side_effect=RuntimeError(CANARY)):
            self.assert_failure(self.main("--content", self.content), "content-invalid")

    def test_c2_6_check_error(self):
        # Neither predicate may silently skip or print partial totals after an error.
        self.words.write_bytes(AGREE)
        for module, check in ((CHECK.label_reader, "is_claim"),
                              (CHECK.product_claims, "drop_copy_claims")):
            with self.subTest(check=check), patch.object(module, check, side_effect=RuntimeError(CANARY)):
                self.assert_failure(self.main("--words", self.words), "check-error")

    def test_c2_7_stage_disagree(self):
        # Disagreement in either direction alone is a finding, not just a counter.
        for raw, s2, s5 in ((b"Organics\n", 1, 0), (b"Farm\n", 0, 1)):
            with self.subTest(s2_only=s2):
                self.words.write_bytes(raw)
                self.assert_result(self.main("--words", self.words), 1, FAIL, [
                    "words 1", "both 0", f"s2-only {s2}", f"s5-only {s5}", "neither 0",
                    "FAIL stage-disagree 1",
                ])

    def test_c3_usage_exit_2(self):
        # Mode selection and missing values are argparse errors, not findings.
        for args in ((), ("--unknown",), ("--words",), ("--content",),
                     ("--words", self.words, "--content", self.content)):
            with self.subTest(option=args[0] if args else None):
                code, stdout, stderr = self.cli(*args)
                self.assertEqual(code, 2)
                self.assertEqual(stdout, "")  # No last stdout line on usage errors.
                self.assertTrue(stderr.startswith("usage: "))

    def test_c4_read_only(self):
        # A report must not normalize inputs in place or generate files beside them.
        self.words.write_bytes(b" Organic \n\n jam \n")
        self.content.mkdir()
        documents = {
            "products": {"products": [
                {"status": "active", "name": "Organic 123 jam"},
                {"status": "active", "name": "jam Jam O’Jam O'Jam jam-like"},
                {"status": "held", "name": "Farm"},
            ]},
            "makers": {"makers": {}},
            "community": {},
            "store": {},
        }
        for name, document in documents.items():
            (self.content / f"{name}.json").write_text(
                json.dumps({"schemaVersion": 1, **document}), encoding="utf-8")

        def snapshot():
            return {p.relative_to(self.root): (p.read_bytes(), p.stat().st_mtime_ns)
                    if p.is_file() else None for p in self.root.rglob("*")}

        before = snapshot()
        self.assert_result(self.cli("--words", self.words), 0, PASS, [
            "words 2", "both 1", "s2-only 0", "s5-only 0", "neither 1",
        ])
        self.assert_result(self.cli("--content", self.content), 0, PASS, [
            "words 6", "both 1", "s2-only 0", "s5-only 0", "neither 5",
        ])
        self.assertEqual(snapshot(), before)

    def test_c5_no_private_values(self):
        # A detailed report, exception string, or raw argparse error could leak values.
        self.words.write_text(f"{CANARY}\nFarm\n", encoding="utf-8")
        self.content.mkdir()
        (self.content / "products.json").write_text(CANARY, encoding="utf-8")
        finding = self.cli("--words", self.words)
        invalid = self.cli("--content", self.content)
        usage = self.cli("--words", self.words, self.content, CANARY)
        with patch.object(CHECK.label_reader, "is_claim", side_effect=RuntimeError(f"{CANARY} {self.words}")):
            check_error = self.main("--words", self.words)
        self.assert_result(finding, 1, FAIL)
        self.assert_failure(invalid, "content-invalid")
        self.assert_failure(check_error, "check-error")
        self.assertEqual(usage[:2], (2, ""))
        for _, stdout, stderr in (finding, invalid, check_error, usage):
            for private in (CANARY, str(self.words), str(self.content)):
                self.assertNotIn(private, stdout + stderr)

    def test_c6_agree(self):
        # Successful inputs still publish all four buckets (including zeros).
        self.words.write_bytes(AGREE)
        self.assert_result(self.main("--words", self.words), 0, PASS, [
            "words 2", "both 1", "s2-only 0", "s5-only 0", "neither 1",
        ])

    def test_c7_disagree(self):
        # Mixed decisions must be counted separately and then added for the finding.
        self.words.write_bytes(DISAGREE)
        self.assert_result(self.main("--words", self.words), 1, FAIL, [
            "words 4", "both 1", "s2-only 1", "s5-only 1", "neither 1",
            "FAIL stage-disagree 2",
        ])

    def test_c8_live_words(self):
        # Pin the checked-in catalog; a rule or active-name change may move this baseline.
        self.assert_result(self.cli("--content", ROOT / "hass/content"), 1, FAIL, [
            "words 289", "both 2", "s2-only 1", "s5-only 1", "neither 285",
            "FAIL stage-disagree 2",
        ])
