"""Fixture-only contract tests for the offline backup receipt."""

from contextlib import redirect_stderr, redirect_stdout
import hashlib
import importlib.util
import io
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import patch


SCRIPT = Path(__file__).resolve().parents[2] / "scripts/hass/install_backup_receipt.py"
SPEC = importlib.util.spec_from_file_location("install_backup_receipt", SCRIPT)
assert SPEC is not None and SPEC.loader is not None
receipt = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(receipt)
PRIVATE = "synthetic-private-marker"
OFF = b'{"settings":{"npp":false},"other":"synthetic-private-marker"}\n'


class InstallBackupReceiptTests(unittest.TestCase):
    def setUp(self):
        temporary = tempfile.TemporaryDirectory()
        self.addCleanup(temporary.cleanup)
        self.root = Path(temporary.name)
        self.root.chmod(0o700)
        self.config = self.root / "source.json"
        self.backup = self.root / "backup.json"
        self.write_pair(OFF)

    def write_pair(self, raw):
        for path in (self.config, self.backup):
            path.write_bytes(raw)
            path.chmod(0o600)

    def args(self, owner_uid=None):
        uid = os.getuid() if owner_uid is None else owner_uid
        return ["--config", str(self.config), "--backup", str(self.backup), "--owner-uid", str(uid)]

    def assert_result(self, result, code, lines):
        actual_code, stdout, stderr = result
        self.assertNotIn(PRIVATE, stdout + stderr)
        self.assertEqual((actual_code, stdout, stderr), (code, "\n".join(lines) + "\n", ""))

    def invoke(self, args):
        with redirect_stdout(io.StringIO()) as stdout, redirect_stderr(io.StringIO()) as stderr:
            code = receipt.main(args)
        return code, stdout.getvalue(), stderr.getvalue()

    def assert_refused(self, *reasons, owner_uid=None):
        lines = [f"FAIL {reason}" for reason in reasons] + ["FAIL install_backup_receipt"]
        self.assert_result(self.invoke(self.args(owner_uid)), 1, lines)

    def assert_inputs_unchanged(self, before, raw):
        self.assertEqual({path.name for path in self.root.iterdir()}, set(before))
        for path in (self.config, self.backup):
            old, new = before[path.name], path.lstat()
            # Reading may update atime; it must not rewrite or replace the files.
            self.assertEqual((new.st_dev, new.st_ino, new.st_mode, new.st_uid, new.st_mtime_ns, new.st_ctime_ns),
                             (old.st_dev, old.st_ino, old.st_mode, old.st_uid, old.st_mtime_ns, old.st_ctime_ns))
            self.assertEqual(path.read_bytes(), raw)

    def test_pass_hashes_exact_backup_bytes_without_changes_or_disclosure(self):
        # Hashing normalized JSON, overwriting a file, or exposing a value breaks the receipt.
        for raw in (OFF, b'{ "settings" : { }, "npp":true }\r\n', b"{}"):
            with self.subTest(raw=raw):
                self.write_pair(raw)
                if raw == b"{}":
                    self.config.chmod(0o640)  # Only the backup has a file-mode requirement.
                before = {path.name: path.stat() for path in self.root.iterdir()}
                cli = subprocess.run([sys.executable, "-B", str(SCRIPT), *self.args()],
                                     cwd=self.root, capture_output=True, text=True, timeout=10)
                self.assert_result((cli.returncode, cli.stdout, cli.stderr), 0,
                                   [f"backup_sha256 {hashlib.sha256(raw).hexdigest()}",
                                    "PASS install_backup_receipt"])
                self.assert_inputs_unchanged(before, raw)

    def test_hardlink_is_not_backup_copy(self):
        # Checking names or bytes alone accepts a hardlink as an independent copy.
        self.backup.unlink()
        os.link(self.config, self.backup)
        before = {path.name: path.stat() for path in self.root.iterdir()}
        cli = subprocess.run([sys.executable, "-B", str(SCRIPT), *self.args()],
                             cwd=self.root, capture_output=True, text=True, timeout=10)
        self.assert_inputs_unchanged(before, OFF)
        self.assert_result((cli.returncode, cli.stdout, cli.stderr), 1,
                           ["FAIL backup-aliases-config", "FAIL install_backup_receipt"])

    def test_refuses_one_byte_difference_even_when_json_is_equal(self):
        self.config.write_bytes(OFF[:-1] + b" ")
        self.assert_refused("bytes-differ")

    def test_checks_exact_file_and_directory_modes(self):
        # A permissive copy or accessible backup directory must fail independently.
        self.backup.chmod(0o640)
        self.assert_refused("backup-mode")
        self.backup.chmod(0o600)
        self.root.chmod(0o755)
        self.assert_refused("backup-dir-mode")

    def test_wrong_owner_is_a_finding_not_an_argparse_error(self):
        for uid in (os.getuid() + 1, -1):
            with self.subTest(uid=uid):
                self.assert_refused("owner", owner_uid=uid)

    def test_refuses_symlink_on_either_side(self):
        # Following a link to the other file could falsely prove equality.
        for path, target in ((self.config, self.backup), (self.backup, self.config)):
            with self.subTest(path=path.name):
                path.unlink()
                path.symlink_to(target)
                self.assert_refused("symlink")
                path.unlink()
                path.write_bytes(OFF)
                path.chmod(0o600)

    def test_refuses_missing_nonregular_and_unreadable_files(self):
        # Unavailable input must not yield a traceback or a digest.
        self.config.unlink()
        self.assert_refused("not-regular")
        self.config.mkdir()
        self.assert_refused("not-regular")
        self.config.rmdir()
        self.write_pair(OFF)
        with patch.object(receipt.os, "open", side_effect=PermissionError(PRIVATE)):
            self.assert_refused("not-regular")

    def test_refuses_duplicate_keys_at_any_depth_without_echoing_them(self):
        for raw in (b'{"synthetic-private-marker":1,"synthetic-private-marker":2}',
                    rb'{"settings":{"npp":true,"\u006epp":false}}',
                    b'{"nested":[{"x":1,"x":2}]}'):
            with self.subTest(raw=raw):
                self.write_pair(raw)
                self.assert_refused("duplicate-key")

    def test_refuses_malformed_json_and_permissive_decoder_extensions(self):
        for raw in (b'{"synthetic-private-marker":}', b'{"other":"\xff"}',
                    OFF.decode().encode("utf-16"), b"[]", b'{"settings":null}',
                    b'{"other":NaN}', b'{"other":Infinity}', b'{"other":-Infinity}'):
            with self.subTest(raw=raw):
                self.write_pair(raw)
                self.assert_refused("bad-json")

    def test_only_literal_false_means_off_when_npp_present(self):
        # Truthiness or equality with False would accept some of these values.
        for value in (b"true", b"0", b"null", b'"false"', b"[]", b"{}"):
            with self.subTest(value=value):
                self.write_pair(b'{"settings":{"npp":' + value + b'}}')
                self.assert_refused("npp-not-off")

    def test_reports_independent_failures_together(self):
        # Returning on the first issue would hide other known failed checks.
        self.backup.write_bytes(b'{"settings":{"npp":true}}')
        self.backup.chmod(0o640)
        self.assert_refused("backup-mode", "bytes-differ", "npp-not-off")

    def test_usage_errors_retain_argparse_exit_2(self):
        # Parser misuse is distinct from a failed file or owner check.
        for args in ([], [*self.args()[:-1], "not-an-int"]):
            with self.subTest(args=args):
                cli = subprocess.run([sys.executable, "-B", str(SCRIPT), *args],
                                     capture_output=True, text=True, timeout=10)
                self.assertEqual((cli.returncode, cli.stdout), (2, ""))
                self.assertIn("usage:", cli.stderr)
                self.assertNotIn("FAIL install_backup_receipt", cli.stderr)
