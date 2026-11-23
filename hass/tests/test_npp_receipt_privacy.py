"""Exercise the offline receipt scanner against synthetic copies only."""

import json
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest


SCRIPT = Path(__file__).resolve().parents[2] / "scripts/hass/npp_receipt_privacy.py"
PASS = "PASS npp_receipt_privacy"
FAIL = "FAIL npp_receipt_privacy"


class NppReceiptPrivacyTests(unittest.TestCase):
    def setUp(self):
        temporary = tempfile.TemporaryDirectory()
        self.addCleanup(temporary.cleanup)
        self.media = Path(temporary.name).resolve()
        self.npp = self.media / "npp"

    def job(self, name):
        job = self.npp / name
        job.mkdir(parents=True)
        return job

    def receipt(self, name, document):
        return self.raw_receipt(name, json.dumps(document).encode())

    def raw_receipt(self, name, raw):
        path = self.job(name) / "receipt.json"
        path.write_bytes(raw)
        return path

    def invoke(self, *args):
        return subprocess.run(
            [sys.executable, "-B", str(SCRIPT), *args], cwd=self.media,
            capture_output=True, text=True, timeout=10,
        )

    def assert_report(self, code, receipts, clean, *findings):
        result = self.invoke("--media", str(self.media))
        expected = [f"receipts {receipts}", f"clean {clean}", *findings, FAIL if code else PASS]
        self.assertEqual(result.returncode, code)
        self.assertTrue(result.stdout == "\n".join(expected) + "\n", "unexpected scan report")
        self.assertTrue(result.stderr == "", "unexpected scan stderr")

    def test_c1_full_pass(self):
        # Prefix matching or traversing symlinks would admit out-of-scope receipts.
        self.receipt("a001", {"summary": "fixture"})
        self.receipt("a002ffffeeee", {"has_cost": False})
        self.receipt("a003-extra", {"cost": None})
        self.receipt("ABCDEF", {"cost": None})
        self.receipt("a004000000abc", {"cost": None})
        self.job("a005")  # No receipt in a valid job folder yet.
        (self.npp / "a006").write_text("not a folder", encoding="utf-8")
        (self.npp / "a007").symlink_to(self.npp / "a003-extra", target_is_directory=True)
        self.assert_report(0, 2, 2)

    def test_c2_1_no_npp_dir(self):
        # A missing directory must not be mistaken for a clean empty copy.
        self.assert_report(1, 0, 0, "FAIL no-npp-dir")
        other = self.media / "other"
        other.mkdir()
        self.npp.symlink_to(other, target_is_directory=True)
        self.assert_report(1, 0, 0, "FAIL no-npp-dir")
        self.npp.rename(self.media / "alias")
        self.npp.write_bytes(b"fixture")
        self.assert_report(1, 0, 0, "FAIL no-npp-dir")

    def test_c2_2_unreadable_receipt(self):
        # A plain JSON read would accept the linked and oversized inputs.
        self.raw_receipt("a001", b'{"fixture":')
        self.receipt("a002", [])
        self.raw_receipt("a003", b"{}" + b" " * (256 << 10))
        good = self.receipt("a004", {})
        (self.job("a005") / "receipt.json").symlink_to(good)
        (self.job("a006") / "receipt.json").mkdir()
        (self.job("a007") / "receipt.json").symlink_to(self.media / "missing")
        self.assert_report(1, 7, 1, "FAIL unreadable-receipt 6")

    def test_c2_3_private_key(self):
        # Each spelling at depth independently adds one receipt, not one hit per key.
        for index, key in enumerate(("CoSt", "Quantity", "QTY", "Private_Cost", "PRIVATE_QUANTITY")):
            self.receipt(f"{index:04x}", {"nested": [{key: None}, {key: False}]})
        self.receipt("a001", {"cost_basis": None, "summary": "cost quantity qty"})
        self.assert_report(1, 6, 1, "FAIL private-key 5")

    def test_c2_4_has_cost_not_bool(self):
        # Truthiness, top-level-only checks and last-key-wins decoding miss these.
        for index, value in enumerate((None, [], {}, "true", 0, 1)):
            self.receipt(f"{index:04x}", {"nested": [{"has_cost": value}] * 2})
        self.raw_receipt("a001", b'{"has_cost":null,"has_cost":true}')
        self.receipt("a002", {"has_cost": False, "nested": [{"has_cost": True}]})
        self.assert_report(1, 8, 1, "FAIL has-cost-not-bool 7")

    def test_c2_5_pattern_hits(self):
        # All approved patterns apply to string values; duplicates count once per receipt.
        examples = {
            "email": "fixture@example.invalid",
            "phone": "202-555-0100",  # Reserved fictional number.
            "pem": "-----BEGIN FIXTURE",
            "aws": "AKIA" + "0" * 16,
            "github": "ghp_" + "0" * 20,
            "key": "sk-" + "0" * 20,
            "slack": "xoxb-fixture",
            "home": "/" + "home/fixture-only",
            "loopback": "127.0.0.1",
            "database": "fixture.sqlite3",
            "chat": "iMessage;-;fixture",
        }
        for index, value in enumerate(examples.values()):
            self.receipt(f"{index:04x}", {"nested": [[f"before {value} after", value]]})
        self.receipt("a001", {value: None for value in examples.values()})  # Keys are not string values.
        self.receipt("a002", {"number": 2025550100})  # A non-string must not be screened.
        self.raw_receipt("a003", b'{"note":"fixture@example.invalid","note":"safe"}')
        self.assert_report(1, 14, 2, *(f"FAIL pattern-{name} {2 if name == 'email' else 1}"
                                      for name in examples))

    def test_c3_usage_exit_2(self):
        # Parser errors keep argparse's own usage/exit path without echoing arguments.
        for args in ((), ("--media",), ("--media", str(self.media), "--unknown", str(self.media))):
            with self.subTest(case=len(args)):
                result = self.invoke(*args)
                self.assertEqual(result.returncode, 2)
                self.assertEqual(result.stdout, "")
                self.assertTrue(result.stderr.startswith("usage: "))
                self.assertTrue(result.stderr.splitlines()[-1] ==
                                "npp_receipt_privacy.py: error: invalid arguments; use --media DIR")
                self.assertFalse(str(self.media) in result.stderr)

    def test_c4_read_only(self):
        # Even on failure, rewriting a receipt or dropping a sidecar is forbidden.
        self.receipt("a001", {"has_cost": True})
        bad = self.raw_receipt("a002", b'{"private_quantity":null}\n')
        bad.with_name("card-fixture.png").write_bytes(b"synthetic artifact")

        def snapshot():
            return {path.relative_to(self.media): (path.stat().st_mtime_ns,
                    path.read_bytes() if path.is_file() else None)
                    for path in (self.media, *self.media.rglob("*"))}

        before = snapshot()
        self.assert_report(1, 2, 1, "FAIL private-key 1")
        self.assertEqual(snapshot(), before)

    def test_c5_no_private_values(self):
        # Reject tracebacks, verbose findings, and excerpts from malformed receipts.
        job = "fe12ab34cd56"
        key = "synthetic-key-path-marker"
        values = {"message": "synthetic-message-marker", "chat": "iMessage;-;fixture-chat-marker",
                  "sender": "fixture-sender@example.invalid", "job_id": job, "digest": "ab" * 32}
        good = self.receipt(job, {key: values, "qty": None, "has_cost": "synthetic-flag-marker"})
        malformed = self.raw_receipt("ab89cdef", b'{"malformed-canary": "unfinished')
        canaries = (*values.values(), key, "synthetic-flag-marker", "malformed-canary",
                    str(self.media), str(good), str(malformed), malformed.parent.name)
        result = self.invoke("--media", str(self.media))
        self.assertEqual(result.returncode, 1)
        output = result.stdout + result.stderr
        self.assertFalse(any(value in output for value in canaries), "scan leaked a fixture canary")
        self.assertEqual(result.stdout.splitlines(), ["receipts 2", "clean 0",
                         "FAIL unreadable-receipt 1", "FAIL private-key 1", "FAIL has-cost-not-bool 1",
                         "FAIL pattern-email 1", "FAIL pattern-chat 1", FAIL])
        self.assertEqual(result.stderr, "")

    def test_c6_clean_receipt_passes(self):
        # The cost-presence boolean and role word aren't themselves private findings.
        self.receipt("a001", {"has_cost": True, "approver": "owner"})
        self.assert_report(0, 1, 1)
