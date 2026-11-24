"""Offline fixtures for the install receipt metadata CLI."""

from contextlib import redirect_stderr, redirect_stdout
import importlib.util
import io
import os
from pathlib import Path
import stat
import tempfile
import unittest
from unittest.mock import patch


SCRIPT = Path(__file__).resolve().parents[2] / "scripts/hass/install_private_files.py"
SPEC = importlib.util.spec_from_file_location("install_private_files", SCRIPT)
assert SPEC is not None and SPEC.loader is not None
CHECKER = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(CHECKER)
PRIVATE_NAME = "synthetic-private-name"
PRIVATE_BYTES = b"synthetic-private-content"


class InstallPrivateFilesTests(unittest.TestCase):
    def setUp(self):
        temporary = tempfile.TemporaryDirectory()
        self.addCleanup(temporary.cleanup)
        # A test runner may give TMPDIR an alias, which is not part of the fixture.
        self.root = Path(temporary.name).resolve()
        self.receipt = self.root / PRIVATE_NAME
        self.receipt.write_bytes(PRIVATE_BYTES)
        self.receipt.chmod(0o600)
        self.backup = self.root / "backup"
        self.backup.mkdir()
        self.backup.chmod(0o700)
        self.uid = self.receipt.stat().st_uid

    def invoke(self, args):
        out, err = io.StringIO(), io.StringIO()
        with redirect_stdout(out), redirect_stderr(err):
            try:
                code = CHECKER.main([str(arg) for arg in args])
            except SystemExit as exc:
                code = exc.code
        combined = out.getvalue() + err.getvalue()
        for value in (str(self.root), PRIVATE_NAME, PRIVATE_BYTES.decode()):
            self.assertNotIn(value, combined)
        return code, out.getvalue().splitlines(), err.getvalue()

    def check(self, *args, lines=(), reasons=(), uid=None):
        code, output, err = self.invoke(("--owner-uid", self.uid if uid is None else uid, *args))
        self.assertEqual(err, "")
        final = "FAIL" if reasons else "PASS"
        self.assertEqual(code, int(bool(reasons)))
        self.assertEqual(output, [*lines, *(f"FAIL {r}" for r in reasons),
                                  f"{final} install_private_files"])

    def test_owner_only_paths_pass_without_opening_contents(self):
        # Opening a receipt, even without echoing it, would violate metadata-only operation.
        unexpected = AssertionError("unexpected file open")
        with (patch("builtins.open", side_effect=unexpected),
              patch("io.open", side_effect=unexpected),
              patch("os.open", side_effect=unexpected)):
            self.check("--dir", self.backup, "--file", self.receipt,
                       "--file", self.receipt, lines=("file[0] ok", "file[1] ok", "dir[0] ok"))
        self.assertEqual(self.receipt.read_bytes(), PRIVATE_BYTES)

    def test_no_paths_is_a_finding_not_a_usage_error(self):
        # An empty invocation must not pass vacuously or exit 2.
        self.check(reasons=("no-paths",))

    def test_usage_errors_do_not_echo_arguments(self):
        # Argparse normally exposes invalid values and unknown path-shaped tokens.
        for args in (("--file", self.receipt), ("--owner-uid", PRIVATE_NAME),
                     ("--owner-uid", self.uid, self.receipt)):
            with self.subTest(args=args):
                code, output, err = self.invoke(args)
                self.assertEqual((code, output), (2, []))
                self.assertTrue(err.startswith("usage:"))

    def test_path_and_type_findings(self):
        # Relative/missing/malformed paths and wrong types cannot count as successes.
        for kind, path, reason in (
            ("--file", self.receipt.name, "not-absolute"),
            ("--file", self.root / "absent", "missing"),
            ("--file", str(self.receipt) + "\0", "missing"),
            ("--file", self.backup, "not-regular"),
            ("--file", str(self.receipt) + "/", "not-regular"),
            ("--dir", self.receipt, "not-dir"),
        ):
            with self.subTest(kind=kind, reason=reason):
                self.check(kind, path, reasons=(reason,))

    def test_symlink_components_are_rejected_before_normalization(self):
        # Leaf-only lstat or lexical normalization can hide a symlink.
        alias = self.root / "alias"
        alias.symlink_to(self.backup, target_is_directory=True)
        link = self.root / "dangling"
        link.symlink_to(self.root / "absent")
        self.check("--file", alias / ".." / self.receipt.name, reasons=("symlink",))
        self.check("--file", link, reasons=("symlink",))
        self.check("--dir", alias, reasons=("symlink",))

        # A healthy destination must not pass under another spelling: filtering
        # separators or normalizing dot segments can hide an ambiguous input.
        self.check("--file", self.receipt, "--dir", self.backup,
                   "--dir", f"{self.backup}/", lines=("file[0] ok", "dir[0] ok", "dir[1] ok"))
        for kind, spelling in (
            ("--file", f"{self.backup}/../{self.receipt.name}"),
            ("--file", f"{self.root}/./{self.receipt.name}"),
            ("--file", f"{self.root}//{self.receipt.name}"),
            ("--file", f"/{self.receipt}"),
            ("--dir", f"{self.backup}/."),
            ("--dir", f"{self.backup}//"),
        ):
            with self.subTest(kind=kind, spelling=spelling):
                self.check(kind, spelling, reasons=("non-canonical",))

    def test_hardlinks_and_all_independent_findings(self):
        # Reporting only the first finding would hide the bad mode or owner.
        os.link(self.receipt, self.root / "other-link")
        self.receipt.chmod(0o640)
        self.check("--file", self.receipt, uid=self.uid + 1,
                   reasons=("hardlinked", "mode", "owner"))
        self.assertEqual(stat.S_IMODE(self.receipt.stat().st_mode), 0o640)

    def test_mode_must_match_exactly(self):
        # Checking only group/other bits misses special bits and wrong owner bits.
        for mode in (0o640, 0o4600, 0o400):
            self.receipt.chmod(mode)
            self.check("--file", self.receipt, reasons=("mode",))
            self.assertEqual(stat.S_IMODE(self.receipt.stat().st_mode), mode)
        self.backup.chmod(0o750)
        self.check("--dir", self.backup, reasons=("mode",))
        self.assertEqual(stat.S_IMODE(self.backup.stat().st_mode), 0o750)

    def test_wrong_owner_for_each_path_kind(self):
        # Comparing to the running UID instead of the requested UID would pass.
        self.check("--file", self.receipt, "--dir", self.backup, uid=self.uid + 1,
                   reasons=("owner", "owner"))

    def test_git_marker_of_any_type_rejects_descendants_and_root(self):
        # Linked worktrees use a file; exists() would miss a dangling marker.
        marker = self.root / ".git"
        nested = self.backup / "nested"
        self.receipt.rename(nested)
        for marker_kind in ("dir", "file", "symlink"):
            with self.subTest(marker_kind=marker_kind):
                if marker_kind == "dir":
                    marker.mkdir()
                elif marker_kind == "file":
                    marker.touch()
                else:
                    marker.symlink_to(self.root / "absent")
                self.check("--file", nested, "--dir", self.root,
                           reasons=("inside-git", "inside-git"))
                marker.rmdir() if marker_kind == "dir" else marker.unlink()

    def test_unreadable_git_probe_fails_closed(self):
        # A failed lookup must not be treated like a confirmed absent marker.
        real_lstat = os.lstat

        def lstat(path, *args, **kwargs):
            if Path(path) == self.root / ".git":
                raise PermissionError(PRIVATE_NAME)
            return real_lstat(path, *args, **kwargs)

        with patch("os.lstat", side_effect=lstat):
            self.check("--file", self.receipt, reasons=("missing",))

    def test_mixed_checks_keep_success_positions_but_fail_overall(self):
        # A bad first item must not hide later results or renumber successes.
        code, out, err = self.invoke(("--owner-uid", self.uid, "--file", "relative",
                                      "--file", self.receipt, "--dir", self.backup))
        self.assertEqual((code, out, err), (1, ["FAIL not-absolute", "file[1] ok",
                                              "dir[0] ok", "FAIL install_private_files"], ""))


if __name__ == "__main__":
    unittest.main()
