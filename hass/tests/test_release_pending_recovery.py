"""Offline CLI contract for reporting (not recovering) an interrupted release."""

from contextlib import redirect_stderr, redirect_stdout
import importlib.util
import io
import json
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest


SCRIPT = Path(__file__).resolve().parents[2] / "scripts/hass/release_pending_recovery.py"
PASS = "PASS release_pending_recovery"
FAIL = "FAIL release_pending_recovery"
STOP = "FAIL pending-marker"
RUN = "run run-fixture"
PHASE = "phase switching"
OLD = "old 0123456789ab"
TARGET = "target fedcba987654"
HOST = "host-before 0600"


class ReleasePendingRecoveryTests(unittest.TestCase):
    def setUp(self):
        temporary = tempfile.TemporaryDirectory()
        self.addCleanup(temporary.cleanup)
        self.root = Path(temporary.name).resolve()
        self.runtime = self.root / "runtime-fixture"
        self.git_dir = self.root / "metadata-fixture"
        self.receipts = self.root / "receipts-fixture"
        self.receipts.mkdir()
        # A .git pointer file catches implementations that assume .git is a directory.
        subprocess.run(
            ["git", "init", "--quiet", "--template=", "--separate-git-dir",
             str(self.git_dir), str(self.runtime)],
            cwd=self.root, check=True, capture_output=True, timeout=10,
        )
        self.marker = self.git_dir / "runtime-release.pending"
        self.run_dir = self.receipts / "run-fixture"
        self.receipt = self.run_dir / "receipt.json"
        self.host = self.run_dir / "host.before"
        self.document = {
            "runtime": str(self.runtime),
            "phase": "switching", "old": "0123456789abcdef" * 2 + "01234567",
            "target": "fedcba9876543210" * 2 + "fedcba98",
        }

    def mark(self, path):
        self.marker.write_text(f"{path}\n", encoding="utf-8")

    def make_run(self):
        self.run_dir.mkdir()
        self.mark(self.run_dir)

    def write_receipt(self):
        self.receipt.write_text(json.dumps(self.document), encoding="utf-8")

    def write_host(self, data=b"synthetic host bytes"):
        self.host.write_bytes(data)
        self.host.chmod(0o600)

    def args(self, runtime=None, receipts=None):
        return ["--runtime", str(runtime or self.runtime),
                "--receipts", str(receipts or self.receipts)]

    def invoke(self, *args):
        return subprocess.run(
            [sys.executable, "-B", str(SCRIPT), *(args or self.args())],
            cwd=self.root, capture_output=True, text=True, timeout=10,
        )

    def assert_report(self, result, code, *lines):
        self.assertEqual(result.returncode, code, result.stderr)
        self.assertEqual(result.stdout, "\n".join((*lines, PASS if code == 0 else FAIL, "")))
        self.assertEqual(result.stderr, "")

    def test_c1_full_pass(self):
        # No marker is a pass, not a missing-receipt or missing-root error.
        result = self.invoke(*self.args(receipts=self.root / "absent"))
        self.assert_report(result, 0, "ok no-pending")

    def test_c2_1_not_git(self):
        # An ordinary directory must fail Git discovery; a file isn't a runtime either.
        for path in (self.receipts, self.runtime / ".git", self.root / "absent"):
            with self.subTest(path=path.name):
                self.assert_report(self.invoke(*self.args(runtime=path)), 1, "FAIL not-git")

    def test_c2_2_pending_marker(self):
        # A dangling symlink is still an entry and must never be treated as absent.
        self.marker.symlink_to(self.root / "absent")
        self.assert_report(self.invoke(), 1, STOP, "FAIL marker-unreadable")

    def test_c2_3_marker_unreadable(self):
        # A reader that strips or picks the first line may accept a truncated marker.
        for raw in (b"", b"/first", b"/first\n\n", b"/first\n/second\n", b"/bad-\xff\n"):
            with self.subTest(raw=raw):
                self.marker.write_bytes(raw)
                self.assert_report(self.invoke(), 1, STOP, "FAIL marker-unreadable")
        self.marker.unlink()
        self.marker.mkdir()
        self.assert_report(self.invoke(), 1, STOP, "FAIL marker-unreadable")

    def test_c2_4_run_outside_receipts(self):
        # Prefix checks alone would follow nested names or links out of the root.
        escaped = self.root / "run-escaped"
        escaped.mkdir()
        self.run_dir.symlink_to(escaped, target_is_directory=True)
        for path in (escaped, self.receipts / "nested" / "run-fixture",
                     self.receipts / "not-a-run", self.run_dir, Path("run-relative")):
            with self.subTest(path=path.name):
                self.mark(path)
                self.assert_report(self.invoke(), 1, STOP, "FAIL run-outside-receipts")

    def test_c2_5_run_missing(self):
        # Don't report individual missing files under an absent run directory.
        self.mark(self.run_dir)
        self.assert_report(self.invoke(), 1, STOP, RUN, "FAIL run-missing")

    def test_c2_6_receipt_missing(self):
        # A symlink to otherwise valid JSON isn't a regular receipt entry.
        self.make_run()
        self.write_host()
        self.assert_report(self.invoke(), 1, STOP, RUN, "FAIL receipt-missing", HOST)
        decoy = self.root / "decoy.json"
        decoy.write_text(json.dumps(self.document), encoding="utf-8")
        self.receipt.symlink_to(decoy)
        self.assert_report(self.invoke(), 1, STOP, RUN, "FAIL receipt-missing", HOST)

    def test_c2_7_receipt_malformed(self):
        # JSON syntax, shape, and each typed field are independent requirements.
        self.make_run()
        self.write_host()
        cases: list[tuple[bytes, tuple[str, ...]]] = [(b"{", ()), (b"[]", ())]
        for key, value, survivors in (("phase", 0, (OLD, TARGET)),
                                      ("old", "A" * 40, (PHASE, TARGET)),
                                      ("target", "a" * 39, (PHASE, OLD))):
            cases.append((json.dumps(dict(self.document, **{key: value})).encode(), survivors))
        for raw, survivors in cases:
            with self.subTest(raw=raw):
                self.receipt.write_bytes(raw)
                self.assert_report(self.invoke(), 1, STOP, RUN, "FAIL receipt-malformed",
                                   *survivors, HOST)

    def test_c2_8_host_before_missing(self):
        # A receipt failure must not short-circuit the separate host check.
        self.make_run()
        self.assert_report(self.invoke(), 1, STOP, RUN, "FAIL receipt-missing",
                           "FAIL host-before-missing")

    def test_c2_9_host_before_mode(self):
        # 0644 and a symlink to a 0600 file both fail the exact entry-type/mode check.
        self.make_run()
        self.write_receipt()
        self.write_host()
        self.host.chmod(0o644)
        self.assert_report(self.invoke(), 1, STOP, RUN, PHASE, OLD, TARGET, "FAIL host-before-mode")
        decoy = self.root / "decoy-host"
        self.host.rename(decoy)
        decoy.chmod(0o600)
        self.host.symlink_to(decoy)
        self.assert_report(self.invoke(), 1, STOP, RUN, PHASE, OLD, TARGET, "FAIL host-before-mode")

    def test_c3_usage_exit_2(self):
        # Parser errors don't become report findings, successful reports, or path leaks.
        for args in (self.args()[:2], self.args() + ["--unknown", str(self.root)],
                     ["--runtime", "--receipts", str(self.receipts)]):
            with self.subTest(args=args):
                result = self.invoke(*args)
                self.assertEqual(result.returncode, 2)
                self.assertEqual(result.stdout, "")  # No last stdout line for usage errors.
                self.assertTrue(result.stderr.startswith("usage:"))
                self.assertNotIn(str(self.root), result.stderr)

    def test_c4_read_only(self):
        # A cleanup, replacement, or incidental write changes this complete input snapshot.
        self.make_run()
        self.write_receipt()
        self.write_host()

        def snapshot():
            return {p.relative_to(self.root): (p.read_bytes(), p.stat().st_mtime_ns)
                    if p.is_file() else None for p in self.root.rglob("*")}

        before = snapshot()
        spec = importlib.util.spec_from_file_location("release_pending_recovery", SCRIPT)
        assert spec is not None and spec.loader is not None
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)
        stdout, stderr = io.StringIO(), io.StringIO()
        with redirect_stdout(stdout), redirect_stderr(stderr):
            code = module.main(self.args())
        result = subprocess.CompletedProcess([], code, stdout.getvalue(), stderr.getvalue())
        self.assert_report(result, 1, STOP, RUN, PHASE, OLD, TARGET, HOST)
        self.assertEqual(snapshot(), before)

    def test_c5_no_private_values(self):
        # Raw JSON dumps, Git errors, full hashes, or path echoes expose these canaries.
        self.make_run()
        self.document.update(
            host=str(self.root / "original-host-fixture"),
            chat="fixture-chat-canary", sender="fixture-sender-canary",
        )
        self.write_receipt()
        message = "synthetic message canary"
        self.write_host(message.encode())
        canaries = (message, *(value for key, value in self.document.items() if key != "phase"),
                    str(self.root), str(self.receipts), str(self.git_dir), str(self.run_dir))
        result = self.invoke()
        self.assert_report(result, 1, STOP, RUN, PHASE, OLD, TARGET, HOST)
        bad_git = self.invoke(*self.args(runtime=self.receipts))
        self.assert_report(bad_git, 1, "FAIL not-git")
        streams = result.stdout + result.stderr + bad_git.stdout + bad_git.stderr
        for value in canaries:
            self.assertNotIn(value, streams)

    def test_c6_valid_run_still_stops(self):
        # Valid inputs are informational, not permission to retry or recover.
        self.make_run()
        self.write_receipt()
        self.write_host()
        alias = self.root / "receipts-alias"
        alias.symlink_to(self.receipts, target_is_directory=True)
        runtime_alias = self.root / "runtime-alias"
        runtime_alias.symlink_to(self.runtime, target_is_directory=True)
        args = self.args(runtime=runtime_alias, receipts=alias)
        self.assert_report(self.invoke(*args), 1, STOP, RUN, PHASE, OLD, TARGET, HOST)

        # Containment in the receipts root is not checkout identity. Trusting
        # containment alone would show another checkout's rollback SHAs.
        for identity in (str(self.root / "other-runtime"), str(self.git_dir), None):
            with self.subTest(identity=identity):
                if identity is None:
                    self.document.pop("runtime")
                else:
                    self.document["runtime"] = identity
                self.write_receipt()
                self.assert_report(self.invoke(*args), 1, STOP, RUN,
                                   "FAIL receipt-runtime-mismatch", HOST)


if __name__ == "__main__":
    unittest.main()
