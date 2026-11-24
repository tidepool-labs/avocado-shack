"""Synthetic fixtures for the metadata-only install check."""

from contextlib import redirect_stderr, redirect_stdout
import io
import os
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from scripts.hass import install_config_attributes as attrs


class InstallConfigAttributesTests(unittest.TestCase):
    def setUp(self):
        # The harness's TMPDIR may itself be a symlink. Only intentional links
        # inside this synthetic fixture should trip the path checks.
        self.root = Path(self.enterContext(tempfile.TemporaryDirectory())).resolve()
        self.source_dir = self.root / "source"
        self.source_dir.mkdir()
        self.config = self.source_dir / "fixture-config"
        self.backup_dir = self.root / "backup"
        self.backup_dir.mkdir(mode=0o700)
        self.backup = self.backup_dir / "fixture-new"
        self.make_file(self.config)
        self.uid = os.getuid()

    def make_file(self, path, mode=0o600):
        os.close(os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL, mode))

    def run_check(self, **overrides):
        args = {
            "config": self.config, "backup": self.backup,
            "service-uid": self.uid, "backup-dir-uid": self.uid,
        }
        args.update(overrides)
        argv = [arg for key, value in args.items() for arg in (f"--{key}", str(value))]
        out, err = io.StringIO(), io.StringIO()
        with redirect_stdout(out), redirect_stderr(err):
            try:
                code = attrs.main(argv)
            except SystemExit as exc:
                code = exc.code
        return code, out.getvalue(), err.getvalue()

    def assert_refused(self, label, **overrides):
        self.assertEqual(self.run_check(**overrides), (1, f"FAIL {label}\n", ""))

    def test_valid_snapshot_never_opens_or_changes_fixtures(self):
        # An open-based check, backup probe, or permission repair violates this contract.
        self.source_dir.chmod(0o700)
        fixtures = self.config, self.source_dir, self.backup_dir
        before = tuple(path.stat() for path in fixtures)
        with (patch("builtins.open", side_effect=AssertionError("open")),
              patch("io.open", side_effect=AssertionError("io.open")),
              patch("os.open", side_effect=AssertionError("os.open")),
              patch("os.chmod", side_effect=AssertionError("chmod"))):
            code, out, err = self.run_check()
            self.assertEqual((code, err), (0, ""))
            self.assertEqual(out, "PASS config-attributes; metadata snapshot only, not safe against concurrent changes\n")
            # A fresh leaf and 0700 mode alone would admit a backup beside the config.
            self.assert_refused("backup-directory-same-as-config", backup=self.source_dir / self.backup.name)
        self.assertEqual(tuple(path.stat() for path in fixtures), before)
        self.assertEqual(list(self.source_dir.iterdir()), [self.config])
        self.assertEqual(list(self.backup_dir.iterdir()), [])

    def test_expected_owners_are_independent(self):
        # Using the current UID instead of either supplied UID would accept that mismatch.
        self.assert_refused("config-owner", **{"service-uid": self.uid + 1})
        self.assert_refused("backup-directory-owner", **{"backup-dir-uid": self.uid + 1})

    def test_modes_are_exact_including_special_bits(self):
        # Masks that only check required bits or ignore special bits would pass extras.
        for mode in (0o400, 0o4600):
            with self.subTest(config_mode=oct(mode)):
                config = self.source_dir / str(mode)
                self.make_file(config, mode)
                self.assert_refused("config-mode", config=config)
        for mode in (0o500, 0o1700):
            with self.subTest(backup_mode=oct(mode)):
                directory = self.root / str(mode)
                directory.mkdir(mode=mode)
                self.assert_refused("backup-directory-mode", backup=directory / "new")

    def test_config_leaf_must_be_regular_not_a_link(self):
        # Following the symlink would make it look like the valid config.
        link = self.root / "source-link"
        link.symlink_to(self.config)
        fifo = self.root / "source-fifo"
        os.mkfifo(fifo, mode=0o600)
        for invalid in (link, fifo, self.backup_dir, self.backup):
            with self.subTest(kind=invalid.name):
                self.assert_refused("config-file", config=invalid)

    def test_links_in_either_parent_chain_are_refused(self):
        # Checking only the two leaves would miss symlinked directories above them.
        link = self.root / "directory-link"
        link.symlink_to(self.root, target_is_directory=True)
        self.assert_refused("config-path", config=link / self.source_dir.name / self.config.name)
        self.assert_refused("backup-path", backup=link / self.backup_dir.name / self.backup.name)
        direct_link = self.root / "backup-directory-link"
        direct_link.symlink_to(self.backup_dir, target_is_directory=True)
        self.assert_refused("backup-directory", backup=direct_link / self.backup.name)

    def test_missing_or_nondirectory_backup_parent_is_not_a_fresh_leaf(self):
        # A flat exists() check cannot distinguish a missing directory from an absent leaf.
        self.assert_refused("backup-directory", backup=self.root / "missing" / "new")
        self.assert_refused("backup-directory", backup=self.config / "new")

    def test_every_occupied_backup_leaf_is_refused(self):
        # exists() alone would miss the dangling symlink; is_file() would miss special entries.
        fifo, link, directory = (self.backup_dir / name for name in ("fifo", "link", "directory"))
        self.make_file(self.backup)
        os.mkfifo(fifo, mode=0o600)
        link.symlink_to(self.backup_dir / "missing")
        directory.mkdir()
        for path in (self.backup, fifo, link, directory):
            with self.subTest(kind=path.name):
                self.assert_refused("backup-entry-exists", backup=path)

    def test_failed_backup_lookup_is_not_a_fresh_leaf_and_is_redacted(self):
        # Permission errors must not be treated as absence or expose supplied paths.
        lstat = Path.lstat

        def denied(path):
            if path == self.backup:
                raise PermissionError("fixture-private-error", str(path))
            return lstat(path)

        with patch.object(Path, "lstat", denied):
            self.assert_refused("backup-entry-unchecked")

    def test_path_spelling_is_checked_before_normalization(self):
        # Normalization could discard an unchecked component or a directory-only suffix.
        self.assert_refused("config-path", config=f"{self.source_dir}/./{self.config.name}")
        self.assert_refused("config-path", config="relative-config")
        self.assert_refused("backup-path", backup=f"{self.root}/unused/../backup/new")
        self.assert_refused("backup-path", backup=f"{self.backup}/")
        self.assert_refused("backup-path", backup=f"{self.backup_dir}//new")

    def test_malformed_uid_does_not_echo_argument(self):
        # Default argparse errors would echo arbitrary supplied values.
        for uid in ("fixture-private-token", "-1"):
            with self.subTest(uid=uid):
                self.assertEqual(self.run_check(**{"service-uid": uid}), (2, "", "FAIL arguments\n"))
