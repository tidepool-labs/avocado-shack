"""Fixture-only tests for the private digest ledger CLI."""

from contextlib import redirect_stderr, redirect_stdout
import hashlib
import importlib.util
import io
import json
from pathlib import Path
import stat
import subprocess
import sys
from tempfile import TemporaryDirectory
import unittest


SCRIPT = Path(__file__).resolve().parents[2] / "scripts/hass/install_digest_ledger.py"
SPEC = importlib.util.spec_from_file_location("install_digest_ledger", SCRIPT)
assert SPEC is not None and SPEC.loader is not None
LEDGER = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(LEDGER)
AT = "2030-01-02T03:04:05Z"
PAYLOAD = b"synthetic-private-fixture\x00"
PASS = "PASS install_digest_ledger\n"
FAIL = "FAIL install_digest_ledger\n"


class InstallDigestLedgerTests(unittest.TestCase):
    def setUp(self):
        temp = TemporaryDirectory()
        self.addCleanup(temp.cleanup)
        self.root = Path(temp.name).resolve()
        self.root.chmod(0o700)
        self.source = self.root / "source.bin"
        self.path = self.root / "ledger.jsonl"
        self.source.write_bytes(PAYLOAD)

    def args(self, command, label="candidate", source=None, at=AT):
        args = [command, "--ledger", str(self.path), "--label", label,
                "--file", str(self.source if source is None else source)]
        return args + ["--at", at] if command == "record" else args

    def invoke(self, command, **kwargs):
        out, err = io.StringIO(), io.StringIO()
        with redirect_stdout(out), redirect_stderr(err):
            status = LEDGER.main(self.args(command, **kwargs))
        output = out.getvalue()
        self.assertEqual(err.getvalue(), "")
        self.assertNotIn("synthetic-private-fixture", output)
        self.assertNotIn(str(self.root), output)
        return status, output

    def entry(self, label="candidate", payload=PAYLOAD, at=AT):
        return {"label": label, "sha256": hashlib.sha256(payload).hexdigest(),
                "size": len(payload), "at": at}

    def seed(self, raw=None):
        if raw is None:
            raw = (json.dumps(self.entry()) + "\n").encode()
        self.path.write_bytes(raw)
        self.path.chmod(0o600)
        return raw

    def assert_refused(self, reason, command, **kwargs):
        before = self.path.read_bytes() if self.path.is_file() else None
        names = set(self.root.iterdir())
        self.assertEqual(self.invoke(command, **kwargs), (1, f"FAIL {reason}\n" + FAIL))
        self.assertEqual(set(self.root.iterdir()), names)
        if before is not None:
            self.assertEqual(self.path.read_bytes(), before)

    def assert_match(self, label="candidate", payload=PAYLOAD):
        before = self.path.read_bytes()
        mtime = self.path.stat().st_mtime_ns
        names = set(self.root.iterdir())
        prefix = hashlib.sha256(payload).hexdigest()[:12]
        self.assertEqual(self.invoke("check", label=label), (0, f"MATCH {label} {prefix}\n" + PASS))
        self.assertEqual(self.path.read_bytes(), before)
        self.assertEqual(self.path.stat().st_mtime_ns, mtime)
        self.assertEqual(set(self.root.iterdir()), names)
        self.assertEqual(self.source.read_bytes(), payload)

    def test_creates_only_private_jsonl_and_checks_without_writing(self):
        # Pin actual argv execution and exact mode even if umask masks owner bits.
        result = subprocess.run([sys.executable, "-B", str(SCRIPT), *self.args("record")],
                                capture_output=True, text=True, timeout=10, umask=0o777)
        self.assertEqual((result.returncode, result.stdout, result.stderr), (0, PASS, ""))
        self.assertEqual(set(self.root.iterdir()), {self.source, self.path})
        self.assertEqual(stat.S_IMODE(self.path.stat().st_mode), 0o600)
        raw = self.path.read_bytes()
        self.assertTrue(raw.endswith(b"\n"))
        self.assertEqual([json.loads(line) for line in raw.splitlines()], [self.entry()])
        self.assert_match()

    def test_same_size_edit_drifts_and_last_entry_wins_in_append_order(self):
        # Catch size-only comparisons or selecting by timestamp/first match/global last.
        first = self.seed()
        changed = PAYLOAD[:-1] + b"!"
        self.source.write_bytes(changed)
        self.assert_refused("drift", "check")
        older = "2030-01-01T03:04:05.125Z"
        self.assertEqual(self.invoke("record", at=older), (0, PASS))
        self.source.write_bytes(PAYLOAD)
        self.assertEqual(self.invoke("record", label="backup"), (0, PASS))
        raw = self.path.read_bytes()
        self.assertTrue(raw.startswith(first))
        self.assertEqual([json.loads(line) for line in raw.splitlines()],
                         [self.entry(), self.entry(payload=changed, at=older), self.entry("backup")])
        self.assert_refused("drift", "check")
        self.assert_match("backup")
        self.source.write_bytes(changed)
        self.assert_match(payload=changed)

    def test_latest_receipt_size_must_match(self):
        # A digest-only check would accept this latest row despite its wrong size.
        good = self.seed()
        self.assert_match()
        wrong_size = self.entry() | {"size": len(PAYLOAD) + 1}
        self.seed(good + (json.dumps(wrong_size) + "\n").encode())
        mtime = self.path.stat().st_mtime_ns
        self.assert_refused("drift", "check")
        self.assertEqual(self.path.stat().st_mtime_ns, mtime)
        self.assertEqual(self.source.read_bytes(), PAYLOAD)

    def test_bad_label(self):
        # Invalid CLI values must be findings, not argparse usage errors or writes.
        self.seed()
        for label in ("", "UPPER", "a_b", "x" * 33, "x\n"):
            with self.subTest(label=label):
                self.assert_refused("bad-label", "record", label=label)
                self.assert_refused("bad-label", "check", label=label)

    def test_bad_time(self):
        # Checking only a Z suffix would accept impossible dates or an extra offset.
        self.seed()
        for at in ("2030-01-02T03:04:05+00:00", "2030-01-02", "2030-01-02Z",
                   "2030-02-30T03:04:05Z", "2030-01-02T03:04:05+01:00Z"):
            with self.subTest(at=at):
                self.assert_refused("bad-time", "record", at=at)

    def test_symlink_ledger(self):
        # A mode-0600 target is not a license to follow the link, even for check.
        target = self.root / "target.jsonl"
        raw = self.seed()
        self.path.rename(target)
        self.path.symlink_to(target)
        for command in ("record", "check"):
            self.assert_refused("ledger-symlink", command)
            self.assertEqual(self.path.readlink(), target)
            self.assertEqual(target.read_bytes(), raw)
        target.unlink()
        self.assert_refused("ledger-symlink", "record")

    def test_bad_ledger_mode(self):
        # Privacy includes refusing a readable but overly permissive ledger.
        self.seed()
        self.path.chmod(0o644)
        for command in ("record", "check"):
            self.assert_refused("ledger-mode", command)
            self.assertEqual(stat.S_IMODE(self.path.stat().st_mode), 0o644)

    def test_bad_parent_mode(self):
        # A safe existing leaf does not excuse a public parent or permit creation.
        self.seed()
        self.root.chmod(0o755)
        for command in ("record", "check"):
            self.assert_refused("ledger-dir-mode", command)
        self.path.unlink()
        self.assert_refused("ledger-dir-mode", "record")

    def test_bad_ledger(self):
        # No matching line may hide malformed JSON, encoding, or field shape.
        good = self.seed()
        for bad in (b"synthetic-private-fixture\n", b"\xff\n", b"\n", b"[]\n", b"{}\n",
                    json.dumps(self.entry() | {"size": True}).encode(),
                    json.dumps(self.entry() | {"size": -1}).encode(),
                    json.dumps(self.entry() | {"sha256": "no-digest"}).encode(),
                    json.dumps(self.entry() | {"label": "_"}).encode(),
                    json.dumps(self.entry() | {"at": "missing-time"}).encode(),
                    json.dumps(self.entry() | {"extra": 0}).encode(),
                    json.dumps(self.entry()).encode()[:-1] + b',"size":1}'):
            with self.subTest(bad=bad):
                self.seed(good + bad)
                for command in ("record", "check"):
                    self.assert_refused("bad-ledger", command)

    def test_no_entry_does_not_create_or_use_another_label(self):
        self.assert_refused("no-entry", "check")
        self.seed()
        self.assert_refused("no-entry", "check", label="unknown")

    def test_not_regular_and_unreadable_input(self):
        # Directories and missing source paths must not be hashed or trigger creation.
        self.assert_refused("not-regular", "record", source=self.root)
        self.seed()
        for source in (self.root, self.root / "absent"):
            for command in ("record", "check"):
                self.assert_refused("not-regular", command, source=source)

    def test_missing_required_option_is_argparse_usage_error(self):
        # An omitted --at is usage, unlike a supplied but invalid timestamp.
        out, err = io.StringIO(), io.StringIO()
        with redirect_stdout(out), redirect_stderr(err), self.assertRaises(SystemExit) as raised:
            LEDGER.main(self.args("record")[:-2])
        self.assertEqual(raised.exception.code, 2)
        self.assertEqual(out.getvalue(), "")
        self.assertIn("usage:", err.getvalue())
        self.assertIn("--at", err.getvalue())
        self.assertFalse(self.path.exists())


if __name__ == "__main__":
    unittest.main()
