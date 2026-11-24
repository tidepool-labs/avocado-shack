"""CLI acceptance for the read-only rollback byte checks."""

import hashlib
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest


SCRIPT = Path(__file__).resolve().parents[2] / "scripts/hass/install_rollback_proof.py"
ORIGINAL = b'{"fixture": "off", "marker": "synthetic-private-value"}\n'
CANDIDATE = ORIGINAL.replace(b'"off"', b'"on"')
ORIGINAL_SHA = hashlib.sha256(ORIGINAL).hexdigest()
CANDIDATE_SHA = hashlib.sha256(CANDIDATE).hexdigest()


class InstallRollbackProofTests(unittest.TestCase):
    def setUp(self):
        self.root = Path(self.enterContext(tempfile.TemporaryDirectory())).resolve()
        self.current = self.root / "current.json"
        self.backup = self.root / "backup.json"
        self.restored = self.root / "restored.json"
        self.current.write_bytes(CANDIDATE)
        self.backup.write_bytes(ORIGINAL)
        self.restored.write_bytes(ORIGINAL)

    def check_cli(self, status, message, *args):
        result = subprocess.run([sys.executable, "-B", str(SCRIPT), *map(str, args)],
                                cwd=self.root, capture_output=True, text=True, timeout=5)
        self.assertEqual(result.returncode, status, result)
        self.assertIn(message, result.stderr if status else result.stdout)
        output = result.stdout + result.stderr
        self.assertIn("does not prove off-state or service health", output)
        self.assertNotIn("synthetic-private-value", output)
        self.assertNotIn(str(self.root), output)

    def pre(self, path, digest=CANDIDATE_SHA):
        return ("pre", "--current", path, "--candidate-sha", digest)

    def post(self, restored=None, backup=None):
        return ("post", "--restored", restored or self.restored,
                "--backup", backup or self.backup, "--original-sha", ORIGINAL_SHA)

    def test_matching_digests_pass_without_changing_files(self):
        # Valid input must pass without rewriting or replacing the fixtures.
        paths = (self.current, self.backup, self.restored)
        before = [(p.stat().st_ino, p.stat().st_mtime_ns, p.read_bytes()) for p in paths]
        self.check_cli(0, "PASS pre", *self.pre(self.current.name, CANDIDATE_SHA.upper()))
        self.check_cli(0, "PASS post", *self.post())
        self.assertEqual(before, [(p.stat().st_ino, p.stat().st_mtime_ns, p.read_bytes())
                                  for p in paths])
        self.assertEqual(set(self.root.iterdir()), set(paths))

    def test_pre_refuses_current_drift(self):
        # Even the original config is drift if the recorded candidate is expected.
        self.current.write_bytes(ORIGINAL)
        self.check_cli(1, "current digest mismatch", *self.pre(self.current))
        self.assertEqual(self.current.read_bytes(), ORIGINAL)

    def test_post_refuses_edited_backup_even_when_both_files_agree(self):
        # Comparing the two files alone would accept a restoration from an edited backup.
        self.backup.write_bytes(CANDIDATE)
        self.restored.write_bytes(CANDIDATE)
        self.check_cli(1, "backup digest mismatch", *self.post())
        self.assertEqual(self.backup.read_bytes(), CANDIDATE)
        self.assertEqual(self.restored.read_bytes(), CANDIDATE)

    def test_post_needs_distinct_restored_inode(self):
        # A digest-only or pathname-only check can mistake a hardlink for a
        # separate restore readback, even though it rereads the backup itself.
        alias = self.root / "backup-alias.json"
        alias.hardlink_to(self.backup)
        for path in (self.backup, alias):
            with self.subTest(path=path.name):
                self.check_cli(1, "backup and restored must be distinct files",
                               *self.post(restored=path))
        self.check_cli(0, "PASS post", *self.post())

    def test_post_refuses_semantically_equal_but_different_bytes(self):
        # A JSON comparison would accept the missing newline.
        changed = ORIGINAL.rstrip(b"\n")
        self.assertEqual(json.loads(changed), json.loads(ORIGINAL))
        self.restored.write_bytes(changed)
        self.check_cli(1, "restored digest mismatch", *self.post())
        self.assertEqual(self.restored.read_bytes(), changed)

    def test_refuses_symlinks_in_each_role_and_parent(self):
        # Each link points to exactly the bytes that would otherwise pass.
        for role, path, command in (
            ("current", self.current, self.pre),
            ("restored", self.restored, self.post),
            ("backup", self.backup, lambda link: self.post(backup=link)),
        ):
            with self.subTest(role=role):
                link = self.root / f"{role}.link"
                link.symlink_to(path)
                self.check_cli(1, f"cannot read {role}", *command(link))
                self.assertTrue(link.is_symlink())
        alias = self.root / "alias"
        alias.symlink_to(self.root, target_is_directory=True)
        self.check_cli(1, "cannot read current", *self.pre(alias / self.current.name))
        self.check_cli(1, "cannot read restored", *self.post(alias / self.restored.name))
        self.check_cli(1, "cannot read backup", *self.post(backup=alias / self.backup.name))

    def test_refuses_missing_or_non_regular_input(self):
        # An unreadable path must fail closed; a FIFO must not block the operator.
        fifo = self.root / "fifo"
        os.mkfifo(fifo)
        for path in (self.root / "absent", self.root, fifo):
            with self.subTest(path=path.name):
                self.check_cli(1, "cannot read current", *self.pre(path))

    def test_invalid_digest_is_not_echoed(self):
        # Pasting a non-digest into the flag must not disclose the argument.
        self.check_cli(2, "64-digit hexadecimal SHA-256", *self.pre(
            self.current, "synthetic-private-value"))
