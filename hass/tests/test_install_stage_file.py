"""Offline fixtures for the stage-file preflight CLI contract."""

from contextlib import redirect_stderr, redirect_stdout
import hashlib
import importlib.util
import io
import os
from pathlib import Path
import subprocess
import sys
from tempfile import TemporaryDirectory
import unittest
from unittest.mock import patch


SCRIPT = Path(__file__).resolve().parents[2] / "scripts/hass/install_stage_file.py"
SPEC = importlib.util.spec_from_file_location("install_stage_file", SCRIPT)
assert SPEC is not None and SPEC.loader is not None
CHECKER = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(CHECKER)
PRIVATE = b"synthetic-private-marker"
DOCUMENT = b'{"key":"' + PRIVATE + b'"}'


class InstallStageFileTests(unittest.TestCase):
    def setUp(self):
        self.root = Path(self.enterContext(TemporaryDirectory())).resolve()
        self.config = self.root / "config.json"
        self.stage = self.root / "stage.json"
        self.uid = os.getuid()
        self.config.write_bytes(PRIVATE)  # Only the stage must be JSON.
        self.stage.write_bytes(DOCUMENT)
        for path in (self.config, self.stage):
            path.chmod(0o600)

    def args(self, uid=None):
        return ["--config", str(self.config), "--stage", str(self.stage),
                "--owner-uid", str(self.uid if uid is None else uid)]

    def assert_result(self, status, stdout, stderr, *findings):
        self.assertNotIn(PRIVATE.decode(), stdout + stderr)
        verdict = "FAIL" if findings else "PASS"
        lines = [*(f"FAIL {reason}" for reason in findings), f"{verdict} install_stage_file"]
        self.assertEqual((status, stdout, stderr), (int(bool(findings)), "\n".join(lines) + "\n", ""))

    def check(self, *findings, uid=None):
        with redirect_stdout(io.StringIO()) as out, redirect_stderr(io.StringIO()) as err:
            status = CHECKER.main(self.args(uid))
        self.assert_result(status, out.getvalue(), err.getvalue(), *findings)

    def test_cli_accepts_adjacent_private_stage_without_replacing_config(self):
        # Requiring JSON in the old config or committing during preflight breaks this.
        before = [path.stat().st_ino for path in (self.config, self.stage)]
        selected = DOCUMENT[:-1] + b', "unrelated": 1 }\r\n'
        changed = selected.replace(b'"unrelated": 1', b'"unrelated": 2')
        digest = hashlib.sha256(selected).hexdigest()
        # Bind the exact bytes (including whitespace); checking only JSON shape or
        # byte length would accept a stage with an unrelated setting changed.
        for raw, options, findings in (
            (selected, [], ()),
            (selected, ["--expect-stage-sha256", digest], ()),
            (changed, ["--expect-stage-sha256", digest], ("stage-sha256-mismatch",)),
        ):
            with self.subTest(expect_digest=bool(options), changed=raw != selected):
                self.stage.write_bytes(raw)
                result = subprocess.run([sys.executable, "-B", str(SCRIPT), *self.args(), *options],
                                        capture_output=True, text=True, timeout=10)
                self.assert_result(result.returncode, result.stdout, result.stderr, *findings)
                self.assertEqual(set(self.root.iterdir()), {self.config, self.stage})
                self.assertEqual([path.stat().st_ino for path in (self.config, self.stage)], before)
                self.assertEqual(self.config.read_bytes(), PRIVATE)
                self.assertEqual(self.stage.read_bytes(), raw)

    def test_compares_physical_parent_identity(self):
        # A textual comparison rejects aliases and a device-only test accepts siblings.
        actual = self.root / "actual"
        actual.mkdir()
        alias = self.root / "alias"
        alias.symlink_to(actual, target_is_directory=True)
        self.config = self.config.rename(actual / self.config.name)
        self.stage = self.stage.rename(alias / self.stage.name)
        self.check()
        self.stage = self.stage.rename(self.root / self.stage.name)
        self.check("other-directory")

    def test_refuses_the_same_name_through_a_parent_alias(self):
        # The same entry need not have the same full argument string.
        alias = self.root / "alias"
        alias.symlink_to(self.root, target_is_directory=True)
        self.config.write_bytes(DOCUMENT)
        for path in (self.config, alias / self.config.name):
            with self.subTest(path=path):
                self.stage = path
                self.check("same-name")

    def test_refuses_hardlinked_stage_but_not_hardlinked_config(self):
        # Link count matters for the staged inode, not for the old config inode.
        (self.root / "config-link").hardlink_to(self.config)
        self.check()
        (self.root / "stage-link").hardlink_to(self.stage)
        self.check("hardlinked")

    def test_refuses_mode_bits_on_either_file(self):
        # A permissions check that tests only 0600's required bits misses extras.
        for path, mode in ((self.config, 0o640), (self.stage, 0o4600)):
            with self.subTest(path=path.name):
                path.chmod(mode)
                self.check("mode")
                path.chmod(0o600)

    def test_refuses_unexpected_owner_on_both_files(self):
        # Checking only the stage or suppressing a second finding loses a result.
        self.check("owner", "owner", uid=self.uid + 1)

    def test_refuses_symlinks_at_either_leaf(self):
        # Following a link to a valid file or testing exists() first loses symlinks.
        for path, target in ((self.config, self.stage), (self.stage, self.root / "missing")):
            with self.subTest(path=path.name):
                path.unlink()
                path.symlink_to(target)
                self.check("symlink")
                path.unlink()
                path.write_bytes(DOCUMENT)
                path.chmod(0o600)

    def test_refuses_non_regular_and_missing_paths(self):
        # Successful stat is not sufficient, and failed stat must not crash.
        self.stage.unlink()
        self.stage.mkdir(mode=0o700)
        self.check("not-regular")
        self.config.unlink()
        self.check("not-regular", "not-regular")

    def test_refuses_unreadable_stage_without_echoing_os_errors(self):
        # Simulate read denial even where the runner would bypass permissions.
        real_open = os.open

        def deny_stage(path, flags):
            if path == str(self.stage):
                raise PermissionError(PRIVATE.decode())
            return real_open(path, flags)

        with patch.object(CHECKER.os, "open", side_effect=deny_stage):
            self.check("bad-json")

    def test_refuses_non_object_invalid_utf8_and_non_json_numbers(self):
        # json.load defaults accept non-objects and non-standard number tokens.
        for raw in (b"[]", b'{' + PRIVATE, b'{"x":"\xff"}',
                    DOCUMENT + b"{}", b"\xef\xbb\xbf" + DOCUMENT,
                    *(b'{"x":' + value + b'}' for value in (b"NaN", b"Infinity", b"-Infinity"))):
            with self.subTest(raw=raw):
                self.stage.write_bytes(raw)
                self.check("bad-json")

    def test_refuses_nested_duplicate_key_without_echoing_it(self):
        # Checking only the root or comparing raw key spellings misses this pair.
        self.stage.write_bytes(b'{"nested":[{"' + PRIVATE + rb'":1,"\u0073' + PRIVATE[1:] + b'":2}]}')
        self.check("duplicate-key")

    def test_argparse_usage_errors_exit_two(self):
        # Missing flags and a non-integer UID are usage errors, not findings.
        for argv in ([], self.args("not-an-int")):
            with self.subTest(argv=argv), redirect_stdout(io.StringIO()) as out, \
                    redirect_stderr(io.StringIO()) as err, self.assertRaises(SystemExit) as exit_info:
                CHECKER.main(argv)
            self.assertEqual(exit_info.exception.code, 2)
            self.assertEqual(out.getvalue(), "")
            self.assertIn("usage:", err.getvalue())
            self.assertNotIn("FAIL", err.getvalue())
