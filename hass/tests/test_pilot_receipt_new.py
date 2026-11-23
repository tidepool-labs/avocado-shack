"""Offline fixture tests for the private pilot receipt creator."""

from contextlib import redirect_stderr, redirect_stdout
import errno
import hashlib
import importlib.util
import io
import json
import os
from pathlib import Path
import stat
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import patch


SCRIPT = Path(__file__).resolve().parents[2] / "scripts/hass/pilot_receipt_new.py"
SPEC = importlib.util.spec_from_file_location("pilot_receipt_new", SCRIPT)
assert SPEC is not None and SPEC.loader is not None
CREATOR = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(CREATOR)
MARKER = "synthetic-private-marker"


class PilotReceiptNewTests(unittest.TestCase):
    def setUp(self):
        temporary = tempfile.TemporaryDirectory(prefix=f"{MARKER}-")
        self.addCleanup(temporary.cleanup)
        self.root = Path(temporary.name).resolve()
        self.out = self.root / "receipt.json"

    def cli(self, *args, umask=-1, cwd=None):
        result = subprocess.run([sys.executable, "-B", str(SCRIPT), *args],
                                cwd=self.root if cwd is None else cwd,
                                capture_output=True, text=True, timeout=10, umask=umask)
        return result.returncode, result.stdout, result.stderr

    def create(self, path, *, cwd=None):
        return self.cli("--listing", "1", "--out", str(path), cwd=cwd)

    def assert_refused(self, result, reason):
        self.assertEqual(result, (1, "", f"error: {reason}\n"))

    def test_blank_shape_permissions_and_output_for_each_listing(self):
        # Missing checklist keys, premature verdicts, umask drift or extra output fail here.
        def unique_object(pairs):
            result = {}
            for key, value in pairs:
                self.assertNotIn(key, result)
                result[key] = value
            return result

        for listing, umask in ((1, 0o000), (2, 0o777), (3, 0o022)):
            with self.subTest(listing=listing):
                path = self.out.name if listing == 1 else str(self.out)
                status, stdout, stderr = self.cli("--listing", str(listing), "--out", path,
                                                  umask=umask)
                self.assertEqual((status, stderr), (0, ""))
                data = self.out.read_bytes()
                self.assertEqual(json.loads(data.decode("utf-8"), object_pairs_hook=unique_object), {
                    "schema": "hass-pilot-receipt/1",
                    "listing": listing,
                    "segments": [],
                    "versions": [],
                    "approval": None,
                    "publish": None,
                    "privacy": {"text": None, "dom": None, "picture": None},
                    "provenance": None,
                    "stops": [],
                    "elapsed_seconds": None,
                })
                self.assertEqual(stat.S_IMODE(self.out.stat().st_mode), 0o600)
                self.assertEqual(stdout, f"{self.out.name} {hashlib.sha256(data).hexdigest()[:12]}\n")
                self.assertEqual(list(self.root.iterdir()), [self.out])
                self.out.unlink()

    def test_existing_file_remains_unchanged(self):
        # A non-exclusive open can truncate an earlier receipt.
        existing = self.root / f"{MARKER}.json"
        existing.write_text(MARKER, encoding="utf-8")
        self.assert_refused(self.create(existing), "output already exists (including symlinks)")
        self.assertEqual(existing.read_text(encoding="utf-8"), MARKER)
        self.assertEqual(list(self.root.iterdir()), [existing])

    def test_existing_and_dangling_symlink_are_not_followed(self):
        # An existence check that follows links can miss a dangling symlink.
        target = self.root / f"{MARKER}.json"
        target.write_text(MARKER, encoding="utf-8")
        self.out.symlink_to(target)
        for present in (True, False):
            with self.subTest(present=present):
                self.assert_refused(self.create(self.out), "output already exists (including symlinks)")
                self.assertEqual(self.out.readlink(), target)
                if present:
                    self.assertEqual(target.read_text(encoding="utf-8"), MARKER)
                    target.unlink()
                self.assertEqual(list(self.root.iterdir()), [self.out])

    def test_parent_must_be_an_existing_symlink_free_directory(self):
        # Following a parent alias could create a receipt at an unintended location.
        regular = self.root / "regular"
        regular.write_text(MARKER, encoding="utf-8")
        real = self.root / "actual"
        real.mkdir(mode=0o700)
        alias = self.root / "alias"
        alias.symlink_to(real, target_is_directory=True)
        for parent in (regular, self.root / "missing", alias):
            with self.subTest(parent=parent.name):
                self.assert_refused(self.create(parent / self.out.name),
                                    "output parent must be an existing symlink-free directory")
        self.assertEqual(regular.read_text(encoding="utf-8"), MARKER)
        self.assertEqual(list(real.iterdir()), [])
        self.assertEqual(set(self.root.iterdir()), {regular, real, alias})

    def test_any_group_or_other_permission_refuses_creation(self):
        # Checking only group read, or only other write, misses other access bits.
        directory = self.root / "not-private"
        directory.mkdir()
        for bit in (0o001, 0o002, 0o004, 0o010, 0o020, 0o040):
            with self.subTest(bit=oct(bit)):
                directory.chmod(0o700 | bit)
                self.assert_refused(self.create(directory / self.out.name),
                                    "output parent allows group or other access")
                self.assertEqual(list(directory.iterdir()), [])

    def test_worktree_destinations_are_refused_without_echo(self):
        # A mode-0700 leaf isn't private enough inside Git. Checking only for
        # directories or starting at cwd would miss the relative linked worktree.
        for marker_type in ("directory", "linked file"):
            worktree = self.root / marker_type
            worktree.mkdir(mode=0o700)
            private = worktree / MARKER
            private.mkdir(mode=0o700)
            marker = worktree / ".git"
            if marker_type == "directory":
                marker.mkdir()
            else:
                marker.write_text("gitdir: synthetic\n", encoding="utf-8")
            for path, cwd, dest in (
                (worktree / "direct.json", self.root, worktree / "direct.json"),
                (private / "absolute.json", self.root, private / "absolute.json"),
                ("relative.json", private, private / "relative.json"),
            ):
                with self.subTest(marker_type=marker_type, path=dest.name):
                    self.assertEqual((self.create(path, cwd=cwd), dest.exists()),
                                     ((1, "", "error: output must be outside Git worktrees\n"), False))

    def test_invalid_arguments_are_refused_without_echo(self):
        # Default argparse errors echo arguments and exit 2; listing 4 must not write.
        for listing in ("4", MARKER):
            self.assert_refused(self.cli("--listing", listing, "--out", str(self.out)),
                                "listing must be 1, 2 or 3")
        for args in (("--listing", "1"), ("--listing", "1", "--out"),
                     ("--listing", "1", "--out", str(self.out), MARKER)):
            self.assert_refused(self.cli(*args), "expected --listing N and --out PATH")
        for path in ("", f"{self.root}/", f"{self.root}/.", f"{self.root}/..", f"{MARKER}\n"):
            self.assert_refused(self.create(path), "output path must name a new file with a printable basename")
        self.assertEqual(list(self.root.iterdir()), [])
        # Normalizing away an actual parent traversal would silently permit a write.
        child = self.root / MARKER
        child.mkdir(mode=0o700)
        result = self.create(f"{child.name}/../{self.out.name}")
        self.assertEqual((result, list(self.root.iterdir())),
                         ((1, "", "error: output parent must not contain '..'\n"), [child]))

    def test_help_shows_required_options(self):
        # Help is an informational command, not a failed receipt write.
        status, stdout, stderr = self.cli("--help")
        self.assertEqual((status, stderr), (0, ""))
        self.assertIn("--listing N", stdout)
        self.assertIn("--out PATH", stdout)
        self.assertEqual(list(self.root.iterdir()), [])

    def run_main(self, path):
        stdout, stderr = io.StringIO(), io.StringIO()
        with redirect_stdout(stdout), redirect_stderr(stderr):
            status = CREATOR.main(["--listing", "1", "--out", str(path)])
        return status, stdout.getvalue(), stderr.getvalue()

    def test_filesystem_errors_do_not_leak_paths_or_leave_files(self):
        # Passing exception text to stderr would expose private filesystem details.
        denied = OSError(errno.EACCES, MARKER, str(self.out))
        with patch.object(CREATOR.os, "fstat", side_effect=denied):
            self.assert_refused(self.run_main(self.out), "could not inspect output parent")
        self.assert_refused(self.run_main(self.root / (MARKER * 20)), "could not create receipt")
        self.assert_refused(self.run_main(self.root / f"{MARKER}\0" / self.out.name),
                            "receipt filesystem operation failed")
        self.assertEqual(list(self.root.iterdir()), [])

    def test_partial_write_followed_by_failure_removes_new_file(self):
        # A disk error after creation must not leave an incomplete receipt or print its digest.
        write = os.write
        calls = []

        def fail_after_prefix(fd, data):
            calls.append(len(data))
            if len(calls) == 1:
                return write(fd, data[:1])
            raise OSError(errno.ENOSPC, MARKER, str(self.out))

        with patch.object(CREATOR.os, "write", side_effect=fail_after_prefix):
            self.assert_refused(self.run_main(self.out), "could not write receipt")
        self.assertEqual(calls[1:], [calls[0] - 1])
        self.assertEqual(list(self.root.iterdir()), [])
