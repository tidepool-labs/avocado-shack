"""Offline acceptance of the synthetic NPP rehearsal, including fault receipts."""

from contextlib import redirect_stderr, redirect_stdout
from functools import partial
import importlib.util
import io
import json
import os
from pathlib import Path
import stat
import subprocess
import sys
from tempfile import TemporaryDirectory
import unittest
from unittest.mock import patch

SCRIPT = Path(__file__).resolve().parents[2] / "scripts/hass/install_rehearsal.py"
SPEC = importlib.util.spec_from_file_location("install_rehearsal", SCRIPT)
assert SPEC is not None and SPEC.loader is not None
REHEARSAL = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(REHEARSAL)
PASSES = ["PASS backup", "PASS edit", "PASS readback", "PASS rollback"]
MARKER = "synthetic-marker"


class InstallRehearsalTests(unittest.TestCase):
    def setUp(self):
        temp = TemporaryDirectory()
        self.addCleanup(temp.cleanup)
        self.root = Path(temp.name)
        self.temp_root = self.root / "tmp"
        self.temp_root.mkdir()
        self.decoy = self.root / "config.json"
        self.decoy.write_text(MARKER)

    def assert_isolated(self):
        self.assertEqual(set(self.root.iterdir()), {self.decoy, self.temp_root})
        self.assertEqual(self.decoy.read_bytes(), MARKER.encode())
        self.assertEqual(list(self.temp_root.iterdir()), [])

    def test_cli_is_deterministic_and_refuses_all_arguments(self):
        # Cwd-based writes, leaked argv, or a stranded temp root break the CLI contract.
        def run(*args):
            result = subprocess.run(
                [sys.executable, "-B", str(SCRIPT), *args], cwd=self.root,
                env={**os.environ, "TMPDIR": str(self.temp_root)},
                capture_output=True, timeout=10,
            )
            self.assert_isolated()
            return result.returncode, result.stdout, result.stderr

        expected = (0, ("\n".join(PASSES) + "\n").encode(), b"")
        self.assertEqual(run(), expected)
        self.assertEqual(run(), expected)
        for arg in (str(self.decoy), "--help", MARKER, ""):
            self.assertEqual(run(arg), (1, b"FAIL arguments: this rehearsal takes no arguments\n", b""))

    def invoke(self):
        out, err = io.StringIO(), io.StringIO()
        with (
            patch.object(REHEARSAL, "TemporaryDirectory", partial(TemporaryDirectory, dir=self.temp_root)),
            redirect_stdout(out), redirect_stderr(err),
        ):
            code = REHEARSAL.main([])
        self.assert_isolated()
        self.assertEqual(err.getvalue(), "")
        self.assertNotIn(MARKER, out.getvalue())
        return code, out.getvalue().splitlines()

    def assert_failed(self, step, reason):
        names = ["backup", "edit", "readback", "rollback", "cleanup"]
        passes = PASSES[:min(names.index(step), 3)]
        self.assertEqual(self.invoke(), (1, [*passes, f"FAIL {step}: {reason}"]))

    def test_same_directory_transactions_preserve_contents_and_mode(self):
        # An in-place overwrite, permissive file or reserialized rollback must fail.
        operations = []
        real_replace = Path.replace

        def observe(stage, target):
            self.assertNotEqual(stage, target)
            self.assertEqual(stage.parent, target.parent)
            self.assertEqual(target.parent.parent, self.temp_root)
            backup = target.with_name("config.before")
            for path in (stage, target, backup):
                self.assertEqual(stat.S_IMODE(path.stat().st_mode), 0o600)
            operations.append((target.read_bytes(), backup.read_bytes(), stage.read_bytes()))
            return real_replace(stage, target)

        with patch.object(Path, "replace", observe):
            self.assertEqual(self.invoke(), (0, PASSES))
        (original, backup, edited), (before_restore, kept_backup, restored) = operations
        self.assertEqual(original, backup)
        baseline = json.loads(original)
        self.assertIs(baseline["settings"]["npp"], False)
        self.assertIs(baseline["settings"]["houseRender"], True)
        self.assertNotIn("photo_polish", baseline["settings"])
        baseline["settings"].update(npp=True, houseRender=True, photo_polish=True)
        self.assertEqual(json.dumps(json.loads(edited), sort_keys=True), json.dumps(baseline, sort_keys=True))
        self.assertEqual(before_restore, edited)
        self.assertEqual(kept_backup, original)
        self.assertEqual(restored, original)

    def test_backup_refuses_bad_copy_or_mode(self):
        # A corrupt copy or a failed chmod must not allow the edit to start.
        with patch.object(REHEARSAL.shutil, "copyfile", lambda _src, dst: dst.write_text(MARKER)):
            self.assert_failed("backup", "backup bytes do not match the fixture")
        real_chmod = Path.chmod
        with patch.object(Path, "chmod", lambda path, _mode: real_chmod(path, 0o644)):
            self.assert_failed("backup", "config and backup must both have mode 0600")

    def test_filesystem_errors_are_attributed_without_echoing_details(self):
        # Distinct I/O boundaries must stop the rehearsal and suppress exception text.
        error = OSError(MARKER)
        real_replace = Path.replace

        def fail_io(*_args, **_kwargs):
            raise error

        def fail_restore(stage, target):
            if stage.name == ".rollback.tmp":
                raise error
            return real_replace(stage, target)

        def fail_cleanup(temp, *_exc):
            temp.cleanup()
            raise error

        for step, owner, name, fault in (
            ("backup", REHEARSAL.shutil, "copyfile", fail_io),
            ("edit", Path, "replace", fail_io),
            ("readback", Path, "read_text", fail_io),
            ("rollback", Path, "replace", fail_restore),
            ("cleanup", TemporaryDirectory, "__exit__", fail_cleanup),
        ):
            with self.subTest(step=step), patch.object(owner, name, fault):
                self.assert_failed(step, "filesystem operation failed")

    def test_edit_rejects_a_replace_that_does_nothing(self):
        # A silently lost replace must not print PASS edit.
        with patch.object(Path, "replace"):
            self.assert_failed("edit", "replace did not change the config")

    def test_disk_readback_rejects_corrupt_or_changed_config(self):
        # Corrupt the real staged output, not the in-memory expected document.
        real_replace = Path.replace
        for fault, reason in (
            (b'{"extension":"synthetic-marker",', "config is not valid unambiguous JSON"),
            (b'{"extension":NaN}', "config is not valid unambiguous JSON"),
            ((b'"npp": true', b'"npp": false, "npp": true'), "config is not valid unambiguous JSON"),
            ((b'"npp": true', b'"npp": 1'), "switches or unrelated values do not match"),
            ((b'"itemIntake": true', b'"itemIntake": 1'), "switches or unrelated values do not match"),
            ((b'"synthetic-marker"', b'"modified"'), "switches or unrelated values do not match"),
            (None, "config does not have mode 0600"),
        ):
            def corrupt(stage, target):
                if fault is None:
                    stage.chmod(0o644)
                else:
                    payload = stage.read_bytes().replace(*fault) if isinstance(fault, tuple) else fault
                    stage.write_bytes(payload)
                return real_replace(stage, target)

            with self.subTest(fault=fault), patch.object(Path, "replace", corrupt):
                self.assert_failed("readback", reason)

    def test_rollback_requires_byte_equality_and_private_mode(self):
        # A blind restore (or a length-only guard) would clobber a same-size edit
        # made after readback. Observe the actual scratch bytes before cleanup.
        real_read_text = Path.read_text
        observed = {}

        def drift_after_readback(path, *args, **kwargs):
            text = real_read_text(path, *args, **kwargs)
            candidate = text.encode("utf-8")
            drift = candidate.replace(MARKER.encode(), b"synthetic-change")
            self.assertEqual(len(drift), len(candidate))
            self.assertNotEqual(drift, candidate)
            path.write_bytes(drift)
            observed.update(path=path, drift=drift)
            return text

        real_exit = TemporaryDirectory.__exit__

        def observe_cleanup(temp, *exc):
            observed["final"] = observed["path"].read_bytes()
            return real_exit(temp, *exc)

        with (
            self.subTest(fault="drift after readback"),
            patch.object(Path, "read_text", drift_after_readback),
            patch.object(TemporaryDirectory, "__exit__", observe_cleanup),
        ):
            self.assert_failed("rollback", "config drifted; restore refused")
            self.assertEqual(observed["final"], observed["drift"])

        # An erroneous refusal result must not hide an overwrite in the built-in trial.
        restore_if_current = REHEARSAL._restore_if_current

        def overwrite_on_refusal(config, candidate, backup):
            if restore_if_current(config, candidate, backup):
                return True
            REHEARSAL.replace(config, ".rollback.tmp", backup.read_bytes())
            return False

        with (
            self.subTest(fault="drift fixture overwritten despite refusal"),
            patch.object(REHEARSAL, "_restore_if_current", overwrite_on_refusal),
        ):
            self.assert_failed("rollback", "drift fixture was not refused and preserved")

        # A whitespace-only change is semantically equal but not an exact restore.
        real_replace = Path.replace
        for wrong_bytes, reason in (
            (True, "restored bytes do not match the original"),
            (False, "config does not have mode 0600"),
        ):
            def corrupt(stage, target):
                if stage.name == ".rollback.tmp":
                    if wrong_bytes:
                        stage.write_bytes(stage.read_bytes() + b"\n")
                    else:
                        stage.chmod(0o644)
                return real_replace(stage, target)

            with self.subTest(reason=reason), patch.object(Path, "replace", corrupt):
                self.assert_failed("rollback", reason)
