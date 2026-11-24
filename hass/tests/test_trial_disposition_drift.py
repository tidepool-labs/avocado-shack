"""Offline CLI contracts for the trial disposition drift report."""

from contextlib import redirect_stderr, redirect_stdout
import importlib.util
from io import StringIO
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import patch


ROOT = Path(__file__).resolve().parents[2]
SCRIPT = ROOT / "scripts/hass/trial_disposition_drift.py"
PASS = "PASS trial_disposition_drift"
FAIL = "FAIL trial_disposition_drift"
COUNTED = "disposition = 'approved'\nf(disposition='status')\n"


class TrialDispositionDriftTests(unittest.TestCase):
    def setUp(self):
        temporary = tempfile.TemporaryDirectory()
        self.addCleanup(temporary.cleanup)
        self.root = Path(temporary.name).resolve()
        self.source = self.root / "source.py"

    def run_cli(self, *args):
        return subprocess.run(
            [sys.executable, "-B", str(SCRIPT), *args], cwd=self.root,
            capture_output=True, text=True, timeout=10,
        )

    def run_source(self, source):
        self.source.write_bytes(source if isinstance(source, bytes) else source.encode())
        return self.run_cli("--source", str(self.source))

    def assert_report(self, result, code, trailer):
        self.assertEqual(result.returncode, code, result.stderr)
        self.assertEqual(result.stderr, "")
        lines = result.stdout.splitlines()
        self.assertTrue(lines)
        self.assertEqual(lines[-1], trailer)
        return lines

    def assert_input_failure(self, result, reason):
        self.assertEqual(self.assert_report(result, 1, FAIL), [f"FAIL {reason}", FAIL])

    def test_c1_full_pass(self):
        # A clean scan must finish with a single success trailer and no findings.
        lines = self.assert_report(self.run_source(COUNTED), 0, PASS)
        self.assertEqual(lines.count(PASS), 1)
        self.assertFalse(any(line.startswith("FAIL ") for line in lines))

    def test_c2_findings_trailer(self):
        # A conforming drift finding must not end in the normal success trailer.
        lines = self.assert_report(self.run_source("disposition = 'till-draft'"), 1, FAIL)
        self.assertEqual(lines[-2:], ["FAIL uncounted till-draft", FAIL])
        self.assertEqual(lines.count(FAIL), 1)

    def test_c2_1_unsafe_input(self):
        # A valid target behind a symlink must not be accepted; FIFOs must not block.
        self.source.write_text(COUNTED, encoding="utf-8")
        link = self.root / "link.py"
        link.symlink_to(self.source)
        dangling = self.root / "dangling.py"
        dangling.symlink_to(self.root / "missing.py")
        fifo = self.root / "pipe.py"
        os.mkfifo(fifo)
        for path in (link, dangling, self.root, fifo):
            with self.subTest(kind=path.name):
                self.assert_input_failure(self.run_cli("--source", str(path)), "unsafe-input")

    def test_c2_2_unreadable_input(self):
        # Missing bytes and undecodable bytes are read failures, not syntax findings.
        self.assert_input_failure(self.run_cli("--source", str(self.source)), "unreadable-input")
        self.assert_input_failure(self.run_source(b"# \xff\n"), "unreadable-input")

        # Exercise an open denial on a regular file even if the test runs as root.
        spec = importlib.util.spec_from_file_location("trial_disposition_drift", SCRIPT)
        if spec is None or spec.loader is None:
            self.fail("could not load the checker")
        module = importlib.util.module_from_spec(spec)
        with patch.object(sys, "path", sys.path.copy()):
            spec.loader.exec_module(module)
        stdout, stderr = StringIO(), StringIO()
        with (patch.object(module.os, "open", side_effect=PermissionError),
              redirect_stdout(stdout), redirect_stderr(stderr)):
            code = module.main(["--source", str(self.source)])
        self.assert_input_failure(
            subprocess.CompletedProcess([], code, stdout.getvalue(), stderr.getvalue()),
            "unreadable-input",
        )

    def test_c2_3_too_large(self):
        # Off-by-one admission would refuse a file exactly at the byte cap.
        source = b"#" + b" " * (2 * 1024 * 1024 - 1)
        self.assert_report(self.run_source(source), 0, PASS)
        self.assert_input_failure(self.run_source(source + b"\n"), "too-large")

    def test_c2_4_source_unparsable(self):
        # A broken assignment must not be skipped or scanned as plain text.
        self.assert_input_failure(self.run_source("disposition = ("), "source-unparsable")

    def test_c2_5_uncounted(self):
        # Findings are sorted and distinct, and the explicit 'other' bucket is exempt.
        lines = self.assert_report(self.run_source(
            "disposition = 'zeta' or 'alpha' or 'zeta' or 'other'\n"
        ), 1, FAIL)
        self.assertEqual(lines, ["values 3", "dynamic 0", "nonconforming 0", "bucket other 3",
                                 "FAIL uncounted alpha", "FAIL uncounted zeta", FAIL])
        self.assert_report(self.run_source("disposition = 'other'"), 0, PASS)

    def test_c3_usage_exit_2(self):
        # Usage errors must stay argparse errors rather than become scan findings.
        for args in (("--source",), ("--unknown",)):
            with self.subTest(args=args):
                result = self.run_cli(*args)
                self.assertEqual(result.returncode, 2)
                self.assertEqual(result.stdout, "")
                self.assertIn("usage:", result.stderr)

    def test_c4_read_only(self):
        # Even an identical-byte rewrite or a sidecar would violate read-only use.
        self.source.write_text(COUNTED, encoding="utf-8")
        before = (self.source.read_bytes(), self.source.stat().st_mtime_ns,
                  self.root.stat().st_mtime_ns, set(self.root.iterdir()))
        self.assert_report(self.run_cli("--source", str(self.source)), 0, PASS)
        self.assertEqual((self.source.read_bytes(), self.source.stat().st_mtime_ns,
                          self.root.stat().st_mtime_ns, set(self.root.iterdir())), before)

    def test_c5_no_private_values(self):
        # Neither reports nor parser/usage diagnostics may echo planted input text.
        value = "Synthetic private value!"
        comment = "Synthetic private comment!"
        good = self.run_source(f"# {comment}\ndisposition = {value!r}\n")
        self.assertIn("nonconforming 1", self.assert_report(good, 0, PASS))
        invalid = self.run_source(f"disposition = {value!r} ]  # {comment}\n")
        self.assert_input_failure(invalid, "source-unparsable")
        usage = self.run_cli("--unknown", str(self.source))
        self.assertEqual((usage.returncode, usage.stdout), (2, ""))
        for result in (good, invalid, usage):
            for canary in (value, comment, str(self.source)):
                self.assertNotIn(canary, result.stdout + result.stderr)

    def test_c6_counted(self):
        # Commands must be mapped to their summary bucket, not printed as drift.
        lines = self.assert_report(self.run_source(COUNTED), 0, PASS)
        self.assertEqual(lines, ["values 2", "dynamic 0", "nonconforming 0",
                                 "bucket approved 1", "bucket commands 1", PASS])

    def test_c7_uncounted(self):
        # Both ternary branches and a disposition stored in a dict must be seen.
        lines = self.assert_report(self.run_source(
            COUNTED + "disposition = 'till-draft' if x else 'paused'\n"
            "d = {'disposition': 'made-up'}\n"
        ), 1, FAIL)
        self.assertEqual(lines, ["values 5", "dynamic 0", "nonconforming 0", "bucket approved 1",
                                 "bucket commands 1", "bucket other 2", "bucket paused 1",
                                 "FAIL uncounted made-up", "FAIL uncounted till-draft", FAIL])

    def test_c8_live_drift(self):
        # Default repo source, even from another cwd; do not import or execute it.
        lines = self.assert_report(self.run_cli(), 1, FAIL)
        self.assertEqual(lines, [
            "values 10", "dynamic 13", "nonconforming 0", "bucket commands 1",
            "bucket no-target 1", "bucket other 7", "bucket paused 1",
            "FAIL uncounted cancelled", "FAIL uncounted till-approved", "FAIL uncounted till-cancelled",
            "FAIL uncounted till-draft", "FAIL uncounted till-read", "FAIL uncounted till-undo",
            "FAIL uncounted till-write-refused", FAIL,
        ])

    def test_expression_walk_only_follows_specified_leaves(self):
        # Extra syntax shapes must not mine dict keys, selection keys or opaque calls.
        lines = self.assert_report(self.run_source(
            "disposition: str\n"
            "alias = disposition = 'status'\n"
            "disposition: str = {'skip-key': 'photo-refused:empty', 'skip-also': 'status'}"
            ".get('skip-selector', name or compute('skip-opaque'))\n"
            "f(disposition='approved' if 'skip-condition' else 'near-approval')\n"
            "disposition = 'Private!' or 'Private!'\n"
        ), 0, PASS)
        self.assertEqual(lines, ["values 4", "dynamic 2", "nonconforming 2", "bucket approved 1",
                                 "bucket commands 1", "bucket near-approval 1", "bucket photo-refused 1", PASS])
