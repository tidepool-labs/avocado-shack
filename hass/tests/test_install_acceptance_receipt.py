"""Synthetic captures for the saved-receipt reader, not acceptance-run tests."""

from contextlib import redirect_stderr, redirect_stdout
import hashlib
import io
import json
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest

from hass.acceptance import ALL_IDS
from scripts.hass import install_acceptance_receipt as receipt


SHA = "ab" * 20
NOTE = "synthetic-private-note"
PASS_ROW = {"id": "H01", "result": "pass", "tests": 3, "failures": 0, "note": ""}
UNCOVERED = {"id": "H07", "result": "not covered", "tests": 0, "failures": 0, "note": NOTE}
SUMMARY = {"ids": 2, "pass": 1, "fail": 0, "not covered": 1}


def capture(rows=(PASS_ROW, UNCOVERED), summary=SUMMARY):
    return "".join(json.dumps(record) + "\n" for record in (*rows, {"summary": summary})).encode()


def metadata(stdout, **changes):
    return json.dumps({"stdout_sha256": hashlib.sha256(stdout).hexdigest(),
                       "runtime_sha": SHA, "exit_status": 0, **changes}).encode()


class AcceptanceReceiptTests(unittest.TestCase):
    def validate(self, stdout, **changes):
        return receipt.validate(stdout, metadata(stdout, **changes), SHA)

    def test_full_receipt_requires_producer_roster(self):
        # Rehashing a selected run preserves consistency, and swapping an ID
        # preserves even the full count; neither proves the producer's full roster.
        rows = [{**(UNCOVERED if ident == UNCOVERED["id"] else PASS_ROW), "id": ident}
                for ident in ALL_IDS]
        summary = {**SUMMARY, "ids": len(rows), "pass": len(rows) - 1}
        full = capture(rows=rows, summary=summary)
        selected_summary = {**SUMMARY, "ids": 1, "not covered": 0}
        selected = capture(rows=(PASS_ROW,), summary=selected_summary)
        unknown_id = next(f"H{i:02d}" for i in range(100) if f"H{i:02d}" not in ALL_IDS)
        substituted = capture(rows=[{**rows[0], "id": unknown_id}, *rows[1:]], summary=summary)

        with tempfile.TemporaryDirectory() as directory:
            stdout_file = Path(directory) / "stdout"
            meta_file = Path(directory) / "metadata"
            command = [sys.executable, "-B", str(Path(receipt.__file__).resolve()),
                       "--stdout", str(stdout_file), "--metadata", str(meta_file),
                       "--expected-runtime-sha", SHA]
            for name, saved, require_full, expected in (
                ("full", full, True, {"summary": summary, "not_covered_ids": ["H07"],
                                      "full_roster": True}),
                ("selected", selected, True, None),
                ("substituted", substituted, True, None),
                ("default", selected, False, {"summary": selected_summary, "not_covered_ids": []}),
            ):
                with self.subTest(case=name):
                    meta = metadata(saved)
                    stdout_file.write_bytes(saved)
                    meta_file.write_bytes(meta)
                    result = subprocess.run(command + (["--require-full-roster"] if require_full else []),
                                            cwd=directory, capture_output=True, text=True, timeout=10)
                    self.assertNotIn(NOTE, result.stdout + result.stderr)
                    self.assertNotIn(SHA, result.stdout + result.stderr)
                    self.assertEqual(stdout_file.read_bytes(), saved)
                    self.assertEqual(meta_file.read_bytes(), meta)
                    if expected is None:
                        self.assertEqual(result.returncode, 1, result.stderr)
                        self.assertEqual(result.stdout, "")
                        self.assertIn("full producer H ID roster", result.stderr)
                    else:
                        self.assertEqual(result.returncode, 0, result.stderr)
                        self.assertEqual(result.stderr, "")
                        self.assertEqual(json.loads(result.stdout), {
                            "status": "consistent (capture not authenticated)", **expected,
                        })

    def test_unknown_producer_id_is_refused(self):
        # Protects: a receipt can only cite cases the producer can emit (it exits 2
        # on H99). Believable bug: shape-only H<digits> validation passes H99.
        unknown_id = next(f"H{i:02d}" for i in range(100) if f"H{i:02d}" not in ALL_IDS)
        selected = {**PASS_ROW, "id": ALL_IDS[-1]}  # genuine selected run, no full roster
        summary = {**SUMMARY, "ids": 1, "not covered": 0}
        self.assertEqual(self.validate(capture(rows=(selected,), summary=summary)),
                         {"summary": summary, "not_covered_ids": []})
        bogus = capture(rows=({**PASS_ROW, "id": unknown_id},), summary=summary)
        with self.assertRaisesRegex(receipt.ReceiptError, "outside the producer"):
            self.validate(bogus)
        with self.assertRaisesRegex(receipt.ReceiptError, "full producer H ID roster"):
            receipt.validate(bogus, metadata(bogus), SHA, require_full_roster=True)

    def test_checks_exact_saved_bytes_and_full_runtime_sha(self):
        # Parsed JSON equality and a common SHA prefix are not sufficient bindings.
        saved = capture()
        meta = metadata(saved)
        for output, expected, reason in (
            (saved.replace(b'"id": ', b'"id":  ', 1), SHA, "SHA-256"),
            (saved, SHA[:-1] + "c", "does not match"),
            (saved, SHA[:12], "full 40-hex"),
        ):
            with self.subTest(reason=reason), self.assertRaisesRegex(receipt.ReceiptError, reason):
                receipt.validate(output, meta, expected)
        self.assertEqual(receipt.validate(saved, meta, SHA.upper())["summary"], SUMMARY)

    def test_metadata_fields_must_be_present_and_well_typed(self):
        # No defaults, duplicate-key overrides or Python bool/number coercion.
        saved = capture()
        fields = json.loads(metadata(saved))
        cases = [b"[]", b"{", b"\xff", metadata(saved)[:-1] + b', "exit_status": 0}']
        cases += [json.dumps({k: v for k, v in fields.items() if k != key}).encode()
                  for key in fields]
        cases += [metadata(saved, exit_status=value) for value in (False, 0.0, "0", None, 1)]
        cases += [metadata(saved, stdout_sha256="g" * 64), metadata(saved, runtime_sha=SHA[:12])]
        for i, meta in enumerate(cases):
            with self.subTest(case=i), self.assertRaises(receipt.ReceiptError):
                receipt.validate(saved, meta, SHA)

    def test_summary_counts_are_literal_integers_and_match_rows(self):
        # A plausible summary can hide failed, missing, or reclassified evidence.
        cases = [("fail", v) for v in (False, 0.0, "0", None, 1)]
        cases += [("pass", True), ("not covered", 1.0), ("ids", "2"), ("ids", -1),
                  ("ids", 3), ("pass", 2), ("not covered", 0)]
        for key, value in cases:
            with self.subTest(key=key, value=value), self.assertRaises(receipt.ReceiptError):
                self.validate(capture(summary={**SUMMARY, key: value}))
        with self.assertRaises(receipt.ReceiptError):
            self.validate(capture(summary={"ids": 2, "pass": 1, "not covered": 1}))

    def test_summary_must_be_one_final_json_record(self):
        # Finding a green line somewhere in stdout is not enough.
        saved = capture()
        cases = (b"", b"fail 0\n", b"\xff" + saved,
                 saved + b"unexpected output\n", saved + b"{}\n", saved + b"\n",
                 saved + saved.splitlines()[-1] + b"\n", b"log before rows\n" + saved,
                 saved.replace(b'"fail": 0', b'"fail": 1, "fail": 0'),
                 capture(rows=(), summary=dict.fromkeys(SUMMARY, 0)))
        for i, output in enumerate(cases):
            with self.subTest(case=i), self.assertRaises(receipt.ReceiptError):
                self.validate(output)

    def test_rows_cannot_pad_or_contradict_the_summary(self):
        # A hash-matching capture must still reject dishonest counts and row contents.
        cases = (
            (PASS_ROW, {**UNCOVERED, "id": "H01"}),
            (PASS_ROW, {**UNCOVERED, "id": NOTE}),
            (PASS_ROW, {**UNCOVERED, "result": []}),
            (PASS_ROW, {**UNCOVERED, "tests": 1}),
            ({**PASS_ROW, "tests": 0}, UNCOVERED),
            ({**PASS_ROW, "tests": True}, UNCOVERED),
            ({**PASS_ROW, "failures": False}, UNCOVERED),
            ({**PASS_ROW, "failures": 1}, UNCOVERED),
            ({**PASS_ROW, "result": "fail", "failures": 1}, UNCOVERED),
            (PASS_ROW, ["not covered"]),
        )
        for i, rows in enumerate(cases):
            with self.subTest(case=i), self.assertRaises(receipt.ReceiptError):
                self.validate(capture(rows=rows))

    def test_uncovered_only_is_consistent_not_a_pass(self):
        # Exit zero from a selected uncovered ID is valid evidence of zero passes.
        summary = {"ids": 1, "pass": 0, "fail": 0, "not covered": 1}
        result = self.validate(capture(rows=(UNCOVERED,), summary=summary))
        self.assertEqual(result, {"summary": summary, "not_covered_ids": ["H07"]})

    def test_cli_reads_files_and_reports_only_redacted_evidence(self):
        # The attended CLI must neither leak captured values nor report success on refusal.
        with tempfile.TemporaryDirectory() as directory:
            saved = capture()
            stdout_file = Path(directory) / "stdout"
            meta_file = Path(directory) / "metadata"
            stdout_file.write_bytes(saved)
            argv = ["--stdout", str(stdout_file), "--metadata", str(meta_file),
                    "--expected-runtime-sha", SHA]
            for meta, code in ((metadata(saved), 0), (metadata(saved, runtime_sha=NOTE), 1),
                               (None, 1)):
                with self.subTest(code=code, missing=meta is None):
                    if meta is None:
                        meta_file.unlink()
                    else:
                        meta_file.write_bytes(meta)
                    out, err = io.StringIO(), io.StringIO()
                    with redirect_stdout(out), redirect_stderr(err):
                        self.assertEqual(receipt.main(argv), code)
                    self.assertNotIn(NOTE, out.getvalue() + err.getvalue())
                    self.assertNotIn(SHA, out.getvalue() + err.getvalue())
                    self.assertEqual(stdout_file.read_bytes(), saved)
                    if meta is not None:
                        self.assertEqual(meta_file.read_bytes(), meta)
                    if code == 0:
                        self.assertEqual(err.getvalue(), "")
                        self.assertEqual(json.loads(out.getvalue()), {
                            "status": "consistent (capture not authenticated)",
                            "summary": SUMMARY, "not_covered_ids": ["H07"],
                        })
                    else:
                        self.assertEqual(out.getvalue(), "")
                        self.assertIn("Receipt refused", err.getvalue())
