"""AVB-04 transaction tests: real temporary Git runtime, fake service boundary.

No live services, host configuration, credentials or records are opened.
"""
import contextlib
from collections.abc import Callable
import io
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import time
import unittest
from unittest.mock import patch

from hass import runtime_release as release


class FixtureRelease(release.Release):
    """Keep actual Git/file operations; simulate ONLY external service/test tools."""
    def __init__(self, args, failures=()):
        super().__init__(args)
        self.failures = list(failures)
        self.calls = []
        self.active = True
        self.restarts = "0"
        self.health_state = "inactive"
        self.pending_hook: Callable[[str], None] | None = None
        self.pending_output = ("outbox_unsent 0\nrelay_unacked 0\ncard_receipt_pending 0\n"
                               "inbound_pending 0\nPASS install_pending_work")
        self.pending_commands = []
        self.checkouts = []

    def command(self, label, argv, cwd=None, timeout=60, codes=(0,), *, strip=True):
        self.calls.append(label)
        if self.pending_hook:
            self.pending_hook(label)
        if self.failures and label == self.failures[0]:
            self.failures.pop(0)
            if label == "stop":
                self.active = False  # partial stop still requires rollback
            raise release.Refused(label)
        if str(argv[0]) == "git":
            if argv[3:5] == ["checkout", "--detach"]:
                self.checkouts.append(argv[-1])
            return super().command(label, argv, cwd=cwd, timeout=timeout, codes=codes, strip=strip)
        if label == "stop":
            self.active = False
        elif label == "start":
            self.active = True
        elif label == "unit-state":
            return "active" if self.active else "inactive"
        elif label == "restart-count":
            return self.restarts
        elif label == "health-idle":
            return self.health_state
        elif label in ("backup-timer",):
            return "active"
        elif label == "backup-result":
            return "success"
        elif label == "selftest":
            return "HASS-SELFTEST fixture pass=10 warn=0 fail=0 skip=1"
        elif label == "inbox":
            return '{"pending": 0}'
        elif label == "pending-work":
            if self.active or self.health_state != "inactive":
                raise AssertionError("pending work read before quiescence")
            self.pending_commands.append(argv)
            return self.pending_output.strip() if strip else self.pending_output
        elif label == "host-check":
            if json.loads(release.private_read(self.a.host))["runtimeCommit"] != self.git("rev-parse", "HEAD"):
                raise release.Refused("host-check")
        return ""


class TransactionTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory(prefix="release-")
        self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name).resolve()
        self.rt = self.root / "runtime"
        self.rt.mkdir()
        self.git("init", "-q")
        self.git("config", "user.name", "Fixture")
        self.git("config", "user.email", "fixture@example.invalid")
        (self.rt / "version.txt").write_text("old\n")
        self.git("add", "version.txt")
        self.git("commit", "-q", "-s", "-m", "old")
        self.old = self.git("rev-parse", "HEAD")
        (self.rt / "version.txt").write_text("new\n")
        self.git("commit", "-q", "-s", "-a", "-m", "new")
        self.new = self.git("rev-parse", "HEAD")
        self.git("update-ref", "refs/remotes/origin/main", self.new)
        self.git("checkout", "-q", "--detach", self.old)
        self.host = self.root / "host.json"
        self.state = self.root / "state" / "state"
        self.state.mkdir(parents=True)
        for path in (self.state / "inbox.sqlite3", self.state / "conversation.sqlite3", self.root / "relay.sqlite3"):
            release.private_write(path, b"fixture store")
        self.before = (json.dumps({"runtimeCommit": self.old, "approvals": "hold", "secretFile": "NEVER-OPEN",
                                   "state": str(self.state), "interpreter": {"model": "fixture"}}) + "\n").encode()
        release.private_write(self.host, self.before)
        self.args = release.arguments(["--runtime", str(self.rt), "--host", str(self.host),
            "--state-root", str(self.root / "state"), "--receipts", str(self.root / "receipts"),
            "--python", sys.executable, "--target", self.new, "--expected-old", self.old, "--apply", "--attended"])
        self.out = io.StringIO()
        self.addCleanup(patch.stopall)
        patch("sys.stdin.isatty", return_value=True).start()
        patch("hass.runtime_release.time.sleep").start()

    def git(self, *args):
        return subprocess.check_output(["git", "-C", str(self.rt), *args], stderr=subprocess.DEVNULL, text=True).strip()

    def run_release(self, failures=()):
        obj = FixtureRelease(self.args, failures)
        with contextlib.redirect_stdout(self.out):
            code = obj.run()
        return obj, code

    def phase(self, obj):
        return json.loads(release.private_read(obj.run_dir / "receipt.json"))["phase"]

    def assert_old(self):
        self.assertEqual(self.git("rev-parse", "HEAD"), self.old)
        self.assertEqual(release.private_read(self.host), self.before)
        self.assertEqual((self.rt / "version.txt").read_text(), "old\n")

    def test_success_real_git_and_pin_only(self):
        obj, code = self.run_release()
        self.assertEqual(code, 0)
        self.assertEqual(self.phase(obj), "released")
        self.assertEqual(self.git("rev-parse", "HEAD"), self.new)
        expected = json.loads(self.before)
        expected["runtimeCommit"] = self.new
        self.assertEqual(json.loads(release.private_read(self.host)), expected)
        self.assertEqual(release.private_read(obj.run_dir / "host.before"), self.before)
        self.assertTrue(obj.active)
        self.assertFalse(obj.stage.exists())
        self.assertLess(obj.calls.index("tests"), obj.calls.index("stop"))
        self.assertLess(obj.calls.index("backup-result"), obj.calls.index("stop"))
        # Clean release must use the actual host/store roles, not a copied relay
        # beside the editor state. Fixture command rejects any active reader.
        command, = obj.pending_commands
        self.assertEqual(Path(command[2]).name, "install_pending_work.py")
        self.assertEqual(command[3:], ["--complete", "--inbox", self.state / "inbox.sqlite3",
                         "--conversation", self.state / "conversation.sqlite3",
                         "--relay", self.host.parent / "relay.sqlite3"])
        self.assertLess(obj.calls.index("health-idle"), obj.calls.index("pending-work"))
        self.assertEqual(obj.checkouts, [self.new])
        self.assertEqual((obj.run_dir / "host.before").stat().st_mode & 0o777, 0o600)
        self.assertNotIn("NEVER-OPEN", self.out.getvalue())
        self.assertNotIn("NEVER-OPEN", (obj.run_dir / "receipt.json").read_text())

    def test_default_plan_opens_no_private_files_or_services(self):
        self.args.apply = False
        self.host.unlink()
        obj, code = self.run_release()
        self.assertEqual(code, 0)
        self.assertTrue(all(c in ("git", "detached") for c in obj.calls))
        self.assertFalse(self.args.receipts.exists())
        self.assertIn("plan-only", self.out.getvalue())

    def test_non_tty_refuses_before_any_service(self):
        with patch("sys.stdin.isatty", return_value=False):
            with self.assertRaisesRegex(release.Refused, "attended"):
                self.run_release()
        self.assert_old()
        self.assertFalse(self.args.receipts.exists())

    def test_missing_attended_refuses(self):
        self.args.attended = False
        with self.assertRaisesRegex(release.Refused, "attended"):
            self.run_release()
        self.assert_old()

    def test_pre_stop_failures_never_switch_or_stop(self):
        for label in ("selftest", "host-check", "inbox", "acceptance", "tests", "backup", "backup-result"):
            with self.subTest(label=label):
                obj, code = self.run_release([label])
                self.assertEqual(code, 1)
                self.assertNotIn("stop", obj.calls)
                self.assert_old()

    def test_partial_stop_failure_rolls_back(self):
        obj, code = self.run_release(["stop"])
        self.assertEqual(code, 1)
        self.assertEqual(self.phase(obj), "rolled-back")
        self.assert_old()
        self.assertTrue(obj.active)
        self.assertEqual(obj.checkouts, [])

    def test_late_pending_refuses_without_writes_and_recovers_original_services(self):
        # The active inbox baseline is empty. A late relay/outbox refusal must
        # not switch, or rewrite already-correct host bytes as "rollback".
        for scenario in ("checker-exit", "partial", "decorated-pass", "missing-counter", "repeated-counter", "pending-receipt"):
            with self.subTest(scenario=scenario):
                obj = FixtureRelease(self.args, ["pending-work"] if scenario == "checker-exit" else [])
                if scenario == "partial":
                    obj.pending_output = obj.pending_output.replace("PASS", "PARTIAL PASS")
                elif scenario == "decorated-pass":
                    obj.pending_output += " \n"
                elif scenario == "missing-counter":
                    obj.pending_output = obj.pending_output.replace("relay_unacked 0\n", "")
                elif scenario == "repeated-counter":
                    obj.pending_output = obj.pending_output.replace("relay_unacked 0", "outbox_unsent 0")
                elif scenario == "pending-receipt":
                    obj.pending_output = obj.pending_output.replace("card_receipt_pending 0", "card_receipt_pending 1")
                write = release.private_write
                def deny_host_replacement(path, data):
                    if path == self.host:
                        self.fail("a refusal attempted to replace the host file")
                    write(path, data)
                identity = self.host.stat().st_ino
                with patch.object(release, "private_write", side_effect=deny_host_replacement) as writes, \
                        contextlib.redirect_stdout(self.out):
                    self.assertEqual(obj.run(), 1)
                self.assertNotIn(self.host, [call.args[0] for call in writes.call_args_list])
                self.assertEqual(obj.checkouts, [])
                self.assertEqual(self.phase(obj), "rolled-back")
                self.assertEqual(self.host.stat().st_ino, identity)
                self.assert_old()
                self.assertTrue(obj.active)
                assert obj.pending is not None
                self.assertFalse(obj.pending.exists())

    def test_inbox_baseline_cannot_use_a_different_state_root(self):
        self.args.state_root = self.root / "stale"
        obj, code = self.run_release()
        self.assertEqual(code, 1)
        self.assertNotIn("inbox", obj.calls)
        self.assertNotIn("stop", obj.calls)
        self.assert_old()

    def test_wrong_or_aliased_store_refuses_before_checker_open(self):
        # A clean stale relay with the same basename is not the effective one.
        relay = self.host.parent / "relay.sqlite3"
        relay.rename(self.state / relay.name)
        obj, code = self.run_release()
        self.assertEqual((code, obj.pending_commands, obj.checkouts), (1, [], []))
        self.assertTrue(obj.active)
        os.link(self.state / "inbox.sqlite3", relay)
        obj, code = self.run_release()
        self.assertEqual((code, obj.pending_commands, obj.checkouts), (1, [], []))
        self.assert_old()
        self.assertTrue(obj.active)

    def test_prewrite_recovery_that_cannot_restart_retains_marker(self):
        obj, code = self.run_release(["pending-work", "start"])
        self.assertEqual(code, 2)
        self.assertEqual(self.phase(obj), "rollback-failed")
        self.assertEqual(obj.checkouts, [])
        self.assertFalse(obj.active)
        assert obj.pending is not None
        self.assertTrue(obj.pending.exists())
        self.assert_old()

    def test_drift_during_stopped_checker_is_not_overwritten_or_restarted(self):
        obj = FixtureRelease(self.args)
        drift = self.before.replace(b'"hold"', b'"private"')
        def hook(label):
            if label == "pending-work":
                release.private_write(self.host, drift)
        obj.pending_hook = hook
        with contextlib.redirect_stdout(self.out):
            self.assertEqual(obj.run(), 2)
        self.assertEqual(obj.checkouts, [])
        self.assertEqual(release.private_read(self.host), drift)
        self.assertNotIn("start", obj.calls)
        self.assertFalse(obj.active)
        self.assertEqual(self.phase(obj), "rollback-failed")

    def test_start_failure_restores_bytes_head_and_services(self):
        obj, code = self.run_release(["start"])
        self.assertEqual(code, 1)
        self.assertEqual(self.phase(obj), "rolled-back")
        self.assertEqual(obj.checkouts, [self.new, self.old])
        self.assert_old()
        self.assertTrue(obj.active)

    def add_target_with_new_files(self):
        """A target that also adds files (one nested), so a partial checkout can leave untracked files."""
        self.git("checkout", "-q", "--detach", self.new)
        (self.rt / "added.txt").write_text("added\n")
        (self.rt / "pkg" / "deep").mkdir(parents=True)
        (self.rt / "pkg" / "deep" / "mod.py").write_text("x = 1\n")
        self.git("add", "added.txt", "pkg/deep/mod.py")
        self.git("commit", "-q", "-s", "-m", "newer")
        target = self.git("rev-parse", "HEAD")
        self.git("update-ref", "refs/remotes/origin/main", target)
        self.git("checkout", "-q", "--detach", self.old)
        self.args.target = target
        return target

    def interrupted_checkout(self, foreign=None, target=None, partial=None):
        """Checkout child killed part-way: some target bytes written, HEAD still old, index lock left."""
        target = target or self.add_target_with_new_files()
        test = self

        def default_partial():
            (test.rt / "version.txt").write_text("new\n")
            (test.rt / "pkg" / "deep").mkdir(parents=True)
            (test.rt / "pkg" / "deep" / "mod.py").write_text("x =")

        class Interrupted(FixtureRelease):
            def command(self, label, argv, cwd=None, timeout=60, codes=(0,), *, strip=True):
                if str(argv[0]) == "git" and argv[3:] == ["checkout", "--detach", target]:
                    self.checkouts.append(target)
                    (partial or default_partial)()
                    (Path(test.git("rev-parse", "--absolute-git-dir")) / "index.lock").write_bytes(b"")
                    if foreign:
                        (test.rt / foreign).write_text("operator file\n")
                    raise KeyboardInterrupt
                return super().command(label, argv, cwd=cwd, timeout=timeout, codes=codes, strip=strip)

        obj = Interrupted(self.args)
        with contextlib.redirect_stdout(self.out):
            code = obj.run()
        return obj, code, target

    def ignored_target_file(self):
        """Old ignores build/; target force-tracks build/gen.txt. Re-pins old/host to the ignoring commit."""
        (self.rt / ".gitignore").write_text("build/\n")
        self.git("add", ".gitignore")
        self.git("commit", "-q", "-s", "-m", "ignore build")
        self.old = self.git("rev-parse", "HEAD")
        (self.rt / "build").mkdir()
        (self.rt / "build" / "gen.txt").write_text("generated\n")
        self.git("add", "-f", "build/gen.txt")
        self.git("commit", "-q", "-s", "-m", "track generated file")
        target = self.git("rev-parse", "HEAD")
        self.git("update-ref", "refs/remotes/origin/main", target)
        self.git("checkout", "-q", "--detach", self.old)
        self.assertFalse((self.rt / "build").exists())
        self.before = self.before.replace(json.loads(self.before)["runtimeCommit"].encode(), self.old.encode())
        release.private_write(self.host, self.before)
        self.args.expected_old, self.args.target = self.old, target
        return target

    def test_interrupted_checkout_removes_ignored_target_only_file(self):
        target = self.ignored_target_file()
        def partial():
            (self.rt / "build").mkdir()
            (self.rt / "build" / "gen.txt").write_text("gene")
        obj, code, _ = self.interrupted_checkout(target=target, partial=partial)
        self.assertEqual(code, 1)
        self.assertEqual(self.phase(obj), "rolled-back")
        self.assertEqual(obj.checkouts, [target, self.old])
        self.assert_old()
        self.assertFalse((self.rt / "build").exists())
        self.assertEqual(self.git("status", "--porcelain", "--ignored", "--untracked-files=all"), "")
        self.assertTrue(obj.active)

    def test_preexisting_ignored_file_at_target_path_refuses_before_checkout(self):
        self.ignored_target_file()
        (self.rt / "build").mkdir()
        (self.rt / "build" / "gen.txt").write_text("operator build output\n")
        obj, code = self.run_release()
        self.assertEqual(code, 1)
        self.assertEqual(obj.checkouts, [])
        self.assertEqual(self.phase(obj), "rolled-back")
        self.assertEqual((self.rt / "build" / "gen.txt").read_text(), "operator build output\n")
        self.assert_old()
        self.assertTrue(obj.active)

    def test_preexisting_index_lock_refuses_before_checkout_and_is_kept(self):
        lock = Path(self.git("rev-parse", "--absolute-git-dir")) / "index.lock"
        obj = FixtureRelease(self.args)
        def hook(label):
            if label == "pending-work":
                obj.pending_hook = None
                lock.write_bytes(b"")  # another Git process appears while services are stopped
        obj.pending_hook = hook
        with contextlib.redirect_stdout(self.out):
            self.assertEqual(obj.run(), 1)
        self.assertEqual(obj.checkouts, [])
        self.assertTrue(lock.exists())
        self.assertEqual(self.phase(obj), "rolled-back")
        self.assert_old()

    def test_interrupted_checkout_recovers_old_head_and_files(self):
        obj, code, target = self.interrupted_checkout()
        self.assertEqual(code, 1)
        self.assertEqual(self.phase(obj), "rolled-back")
        self.assertEqual(obj.checkouts, [target, self.old])
        self.assert_old()
        self.assertEqual(self.git("status", "--porcelain", "--untracked-files=all"), "")
        self.assertFalse((self.rt / "added.txt").exists())
        self.assertFalse((self.rt / "pkg").exists())
        self.assertFalse((Path(self.git("rev-parse", "--absolute-git-dir")) / "index.lock").exists())
        self.assertTrue(obj.active)
        assert obj.pending is not None
        self.assertFalse(obj.pending.exists())

    def test_interrupted_checkout_with_foreign_change_is_left_stopped(self):
        obj, code, _ = self.interrupted_checkout(foreign="operator-notes.txt")
        self.assertEqual(code, 2)
        self.assertEqual(self.phase(obj), "rollback-failed")
        self.assertEqual((self.rt / "operator-notes.txt").read_text(), "operator file\n")
        # Refused before any recovery checkout: partial bytes stay for the operator.
        self.assertEqual((self.rt / "version.txt").read_text(), "new\n")
        self.assertEqual(release.private_read(self.host), self.before)
        self.assertFalse(obj.active)
        assert obj.pending is not None
        self.assertTrue(obj.pending.exists())

    def test_completed_checkout_with_owned_edit_still_recovers(self):
        target = self.add_target_with_new_files()
        obj = FixtureRelease(self.args)
        def hook(label):
            if label == "start":
                obj.pending_hook = None
                (self.rt / "pkg" / "deep" / "mod.py").write_text("half-written\n")
                raise release.Refused("start")
        obj.pending_hook = hook
        with contextlib.redirect_stdout(self.out):
            self.assertEqual(obj.run(), 1)
        self.assertEqual(obj.checkouts, [target, self.old])
        self.assertEqual(self.phase(obj), "rolled-back")
        self.assert_old()
        self.assertFalse((self.rt / "pkg").exists())
        self.assertEqual(self.git("status", "--porcelain", "--untracked-files=all"), "")

    def test_post_switch_validation_failure_restores(self):
        for failure in ("selftest", "host-check"):
            with self.subTest(failure=failure):
                obj = FixtureRelease(self.args)
                seen = 0
                def hook(label):
                    nonlocal seen
                    if label == failure:
                        seen += 1
                        if seen == 2:
                            raise release.Refused(failure)
                obj.pending_hook = hook
                with contextlib.redirect_stdout(self.out):
                    self.assertEqual(obj.run(), 1)
                self.assertEqual(self.phase(obj), "rolled-back")
                self.assert_old()

    def test_interrupt_during_start_rolls_back(self):
        obj = FixtureRelease(self.args)
        def hook(label):
            if label == "start":
                obj.pending_hook = None
                raise KeyboardInterrupt
        obj.pending_hook = hook
        with contextlib.redirect_stdout(self.out):
            self.assertEqual(obj.run(), 1)
        self.assertEqual(self.phase(obj), "rolled-back")
        self.assert_old()

    def test_rollback_failure_is_not_success(self):
        obj, code = self.run_release(["start", "stop"])
        self.assertEqual(code, 2)
        self.assertEqual(self.phase(obj), "rollback-failed")
        self.assertFalse(obj.active)
        self.args.expected_old, self.args.target = self.new, self.old
        with self.assertRaisesRegex(release.Refused, "unfinished-release"):
            self.run_release()

    def test_host_edit_is_not_overwritten(self):
        obj = FixtureRelease(self.args)
        changed = self.before.replace(b'"hold"', b'"private"')
        def hook(label):
            if label == "stop":
                obj.pending_hook = None
                release.private_write(self.host, changed)
        obj.pending_hook = hook
        with contextlib.redirect_stdout(self.out):
            self.assertEqual(obj.run(), 2)
        self.assertEqual(release.private_read(self.host), changed)
        self.assertFalse(obj.active)
        self.assertEqual(self.phase(obj), "rollback-failed")

    def test_dirty_runtime_refused_without_changes(self):
        (self.rt / "untracked").write_text("keep")
        with self.assertRaisesRegex(release.Refused, "runtime-identity"):
            self.run_release()
        self.assertEqual((self.rt / "untracked").read_text(), "keep")
        self.assert_old()

    def test_wrong_expected_head_refused(self):
        self.args.expected_old = "a" * 40
        with self.assertRaisesRegex(release.Refused, "runtime-identity"):
            self.run_release()
        self.assert_old()

    def test_branch_runtime_refused(self):
        self.git("checkout", "-q", "-b", "do-not-detach")
        with self.assertRaisesRegex(release.Refused, "not-detached"):
            self.run_release()
        self.assertEqual(self.git("symbolic-ref", "--short", "HEAD"), "do-not-detach")

    def test_target_not_on_main_refused(self):
        self.git("update-ref", "refs/remotes/origin/main", self.old)
        with self.assertRaises(release.Refused):
            self.run_release()
        self.assert_old()

    def test_noop_refused(self):
        self.args.target = self.old
        with self.assertRaisesRegex(release.Refused, "no-move"):
            self.run_release()

    def test_host_pin_mismatch_no_service_stop(self):
        release.private_write(self.host, self.before.replace(self.old.encode(), self.new.encode()))
        obj, code = self.run_release()
        self.assertEqual(code, 1)
        self.assertNotIn("stop", obj.calls)

    def test_shared_receipt_lock_refuses(self):
        self.args.receipts.mkdir(mode=0o700)
        lock_path = Path(self.git("rev-parse", "--absolute-git-dir")) / "runtime-release.lock"
        with open(lock_path, "wb") as lock:
            release.fcntl.flock(lock, release.fcntl.LOCK_EX | release.fcntl.LOCK_NB)
            with self.assertRaisesRegex(release.Refused, "locked"):
                self.run_release()
        self.assert_old()

    def test_pending_marker_blocks_alternate_receipt_root(self):
        pending = Path(self.git("rev-parse", "--absolute-git-dir")) / "runtime-release.pending"
        release.private_write(pending, b"interrupted-run\n")
        self.args.receipts = self.root / "alternate"
        with self.assertRaisesRegex(release.Refused, "unfinished-release"):
            self.run_release()
        self.assert_old()

    def test_inbox_nonzero_or_invalid_report_refuses(self):
        for report in ('{"pending":1}', '{"pending":false}', '{}', '[]', 'not JSON'):
            with self.subTest(report=report):
                obj = FixtureRelease(self.args)
                command = obj.command
                def with_report(label, argv, **kwargs):
                    return report if label == "inbox" else command(label, argv, **kwargs)
                with patch.object(obj, "command", side_effect=with_report), contextlib.redirect_stdout(self.out):
                    self.assertEqual(obj.run(), 1)
                self.assertNotIn("stop", obj.calls)
                self.assert_old()

    def test_selftest_missing_or_failed_summary_refuses(self):
        for output in ('', 'HASS-SELFTEST x pass=1 warn=0 fail=1 skip=0',
                       'HASS-SELFTEST x pass=1 warn=0 fail=0 skip=0\nbad tail'):
            with self.subTest(output=output):
                obj = FixtureRelease(self.args)
                command = obj.command
                def with_output(label, argv, **kwargs):
                    return output if label == "selftest" else command(label, argv, **kwargs)
                with patch.object(obj, "command", side_effect=with_output), contextlib.redirect_stdout(self.out):
                    self.assertEqual(obj.run(), 1)
                self.assertNotIn("stop", obj.calls)
                self.assert_old()

    def test_receipt_mode_refuses(self):
        self.args.receipts.mkdir(mode=0o755)
        self.args.receipts.chmod(0o755)
        with self.assertRaisesRegex(release.Refused, "receipt-directory"):
            self.run_release()

    def test_active_health_service_prevents_switch(self):
        obj = FixtureRelease(self.args)
        obj.health_state = "active"
        with contextlib.redirect_stdout(self.out):
            self.assertEqual(obj.run(), 2)
        self.assert_old()
        self.assertFalse(obj.active)

    def test_time_budget_reserves_rollback(self):
        obj = FixtureRelease(self.args)
        def hook(label):
            if label == "backup-result":
                obj.deadline = time.monotonic() + 10
        obj.pending_hook = hook
        with contextlib.redirect_stdout(self.out):
            self.assertEqual(obj.run(), 1)
        self.assertNotIn("stop", obj.calls)
        self.assert_old()

    def timed_staging(self, acceptance, tests, work_seconds=0, fail_start=False):
        """Virtual staging children still go through the production timeout guard."""
        clock = [100.0]
        real_popen = subprocess.Popen
        budgets = []
        recovery = []
        with patch("hass.runtime_release.time.monotonic", side_effect=lambda: clock[0]):
            obj = FixtureRelease(self.args)
        fixture_command = obj.command

        class StageChild:
            pid = 123456789  # killpg is mocked; never signal a real process
            returncode = 0

            def __init__(self, duration):
                self.duration = duration

            def communicate(self, timeout=None):
                if timeout is not None:
                    budgets.append(timeout)
                    clock[0] += min(self.duration, timeout)
                    if self.duration > timeout:
                        raise subprocess.TimeoutExpired("fixture-stage", timeout)
                return "", ""

        def popen(argv, **kwargs):
            if argv[-1] in ("hass/acceptance.py", "hass/tests/run_parallel.py"):
                return StageChild(acceptance if argv[-1] == "hass/acceptance.py" else tests)
            return real_popen(argv, **kwargs)

        def command(label, argv, cwd=None, timeout=60, codes=(0,), *, strip=True):
            if label in ("acceptance", "tests"):
                obj.calls.append(label)
                return release.Release.command(obj, label, argv, cwd=cwd, timeout=timeout, codes=codes, strip=strip)
            if label == "backup-result":
                clock[0] += work_seconds
            if label == "start" and fail_start and not obj.rollback_mode:
                raise release.Refused("start")
            if label == "stop" and obj.rollback_mode:
                recovery.append(obj.deadline - clock[0])
            return fixture_command(label, argv, cwd=cwd, timeout=timeout, codes=codes, strip=strip)

        obj.command = command
        with patch("hass.runtime_release.time.monotonic", side_effect=lambda: clock[0]), \
                patch("hass.runtime_release.subprocess.Popen", side_effect=popen), \
                patch("hass.runtime_release.os.killpg") as killpg, \
                contextlib.redirect_stdout(self.out):
            code = obj.run()
        return obj, code, budgets, recovery, killpg

    def test_1000_second_staging_has_own_shared_budget(self):
        budget = release.STAGING_BUDGET_SECONDS
        obj, code, budgets, _, killpg = self.timed_staging(130, 870)
        self.assertEqual(code, 0)
        self.assertEqual(budgets, [budget, budget - 130])
        self.assertEqual(self.phase(obj), "released")
        killpg.assert_not_called()

    def test_measured_host_staging_fits_shared_budget(self):
        # H74: on this host acceptance.py took 971 s and run_parallel.py 1944 s, 2915 s in total
        # (corrected runner, service venv, Node 22, six shards). The old 1800 s cap refused before backup.
        self.assertEqual(release.STAGING_BUDGET_SECONDS, 5400)
        acceptance, tests = 971, 1944
        self.assertGreaterEqual(release.STAGING_BUDGET_SECONDS, int(1.5 * (acceptance + tests)))
        obj, code, budgets, _, killpg = self.timed_staging(acceptance, tests)
        self.assertEqual(code, 0)
        self.assertEqual(budgets, [release.STAGING_BUDGET_SECONDS, release.STAGING_BUDGET_SECONDS - acceptance])
        self.assertEqual(self.phase(obj), "released")
        killpg.assert_not_called()

    def test_staging_timeout_refuses_before_downtime(self):
        budget = release.STAGING_BUDGET_SECONDS
        for acceptance, tests in ((budget + 1, 0), (130, budget - 129), (1049, budget - 1048)):
            with self.subTest(acceptance=acceptance, tests=tests):
                obj, code, budgets, _, killpg = self.timed_staging(acceptance, tests)
                self.assertEqual(budgets[0], budget)
                self.assertEqual(code, 1)
                self.assertNotIn("stop", obj.calls)
                self.assertNotIn("backup", obj.calls)
                self.assertTrue(obj.active)
                self.assert_old()
                killpg.assert_called_once_with(123456789, release.signal.SIGKILL)

    def test_staging_does_not_enlarge_switch_or_recovery_budget(self):
        obj, code, _, _, _ = self.timed_staging(130, 870, work_seconds=721)
        self.assertEqual(code, 1)
        self.assertIn("insufficient-switch-budget", self.out.getvalue())
        self.assertNotIn("stop", obj.calls)
        self.assert_old()
        # Exactly 180 seconds remaining still admits switching; failure then gets
        # a fresh 180-second recovery budget, not the staging or normal budget.
        obj, code, _, recovery, _ = self.timed_staging(130, 870, work_seconds=720, fail_start=True)
        self.assertEqual(code, 1)
        self.assertEqual(recovery, [180])
        self.assertEqual(self.phase(obj), "rolled-back")
        self.assert_old()

    def test_real_cli_plan(self):
        argv = [sys.executable, str(Path(release.__file__).resolve()), "--target", self.new,
                "--expected-old", self.old, "--runtime", str(self.rt)]
        result = subprocess.run(argv, capture_output=True, text=True)
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(json.loads(result.stdout)["result"], "plan-only")
        self.assert_old()


class PrimitiveTests(unittest.TestCase):
    def test_bad_commit_literal_refused(self):
        for value in ("HEAD", "a" * 39, "A" * 40, "a" * 40 + "\n", "--help"):
            with self.subTest(value=value), contextlib.redirect_stderr(io.StringIO()), self.assertRaises(SystemExit):
                release.arguments(["--target", value, "--expected-old", "b" * 40])

    def test_host_duplicates_and_nonfinite_refused(self):
        for data in (b'{"runtimeCommit":"a","runtimeCommit":"a"}', b'{"runtimeCommit":"a","x":NaN}'):
            with self.assertRaises(release.Refused):
                release.host_pin(data, "a", "b")

    def test_private_reader_refuses_symlink_and_mode(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "host"
            path.write_text("do-not-expose")
            path.chmod(0o644)
            with self.assertRaises(release.Refused):
                release.private_read(path)
            path.chmod(0o600)
            link = Path(tmp) / "link"
            link.symlink_to(path)
            with self.assertRaises(OSError):
                release.private_read(link)
            self.assertEqual(release.private_read(path), b"do-not-expose")

    def test_real_command_failure_does_not_expose_output(self):
        args = release.arguments(["--target", "a" * 40, "--expected-old", "b" * 40])
        obj = release.Release(args)
        with tempfile.TemporaryDirectory() as tmp:
            script = Path(tmp) / "fail.py"
            script.write_text('import sys\nprint("PRIVATE-SENTINEL")\nsys.exit(1)\n')
            with self.assertRaisesRegex(release.Refused, "probe") as exc:
                obj.command("probe", [sys.executable, script])
            self.assertNotIn("PRIVATE-SENTINEL", str(exc.exception))

    def test_failed_or_inconsistent_unit_query_never_proves_state(self):
        args = release.arguments(["--target", "a" * 40, "--expected-old", "b" * 40])
        for active, text, code in ((True, "active", 3), (False, "inactive", 0), (True, "inactive", 0)):
            with self.subTest(active=active, text=text, code=code), tempfile.TemporaryDirectory() as tmp:
                script = Path(tmp) / "unit.py"
                script.write_text(f'import sys\nprint({text!r})\nsys.exit({code})\n')
                obj = release.Release(args)
                command = obj.command
                def query(label, argv, **kwargs):
                    self.assertEqual(label, "unit-state")  # never invoke a live systemctl
                    return command(label, [sys.executable, script], **kwargs)
                obj.command = query
                with self.assertRaisesRegex(release.Refused, "unit-state"):
                    obj.units(active)

    def test_real_command_timeout(self):
        args = release.arguments(["--target", "a" * 40, "--expected-old", "b" * 40])
        obj = release.Release(args)
        with tempfile.TemporaryDirectory() as tmp:
            script = Path(tmp) / "wait.py"
            script.write_text('import time\ntime.sleep(60)\n')
            with self.assertRaisesRegex(release.Refused, "probe-timeout"):
                obj.command("probe", [sys.executable, script], timeout=0.05)


if __name__ == "__main__":
    unittest.main()
