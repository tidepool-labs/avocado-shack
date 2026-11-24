"""Offline contract tests for the label-size stage comparison CLI."""

from contextlib import redirect_stderr, redirect_stdout
import importlib.util
import io
import os
from pathlib import Path
import subprocess
import sys
from tempfile import TemporaryDirectory
import unittest
from unittest.mock import patch


ROOT = Path(__file__).resolve().parents[2]
SCRIPT = ROOT / "scripts/hass/size_text_stage_check.py"
SPEC = importlib.util.spec_from_file_location("size_text_stage_check", SCRIPT)
assert SPEC is not None and SPEC.loader is not None
CHECK = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(CHECK)

PASS = "PASS size_text_stage_check"
FAIL = "FAIL size_text_stage_check"
AGREED = b"12 oz\n16 fl oz\n"


class SizeTextStageCheckTests(unittest.TestCase):
    def setUp(self):
        temporary = TemporaryDirectory(dir=ROOT)
        self.addCleanup(temporary.cleanup)
        self.root = Path(temporary.name)
        self.path = self.root / "synthetic-private-path"

    def run_cli(self, *args):
        return subprocess.run(
            [sys.executable, "-B", str(SCRIPT), *args], cwd=self.root,
            capture_output=True, text=True, timeout=10,
        )

    def sizes(self, data):
        self.path.write_bytes(data)
        return self.run_cli("--sizes", str(self.path))

    def in_process(self, *args):
        out, err = io.StringIO(), io.StringIO()
        with redirect_stdout(out), redirect_stderr(err):
            code = CHECK.main(list(args))
        return subprocess.CompletedProcess(args, code, out.getvalue(), err.getvalue())

    def assert_report(self, result, *, counts=None, finding=None):
        self.assertEqual(result.returncode, 1 if finding else 0)
        self.assertEqual(result.stderr, "")
        lines = result.stdout.splitlines()
        self.assertEqual(lines[-1:], [FAIL if finding else PASS])
        expected = []
        if counts is not None:
            expected.extend(f"{name} {value}" for name, value in zip(
                ("sizes", "both", "s2-only", "s5-only", "neither"), counts, strict=True,
            ))
        if finding:
            expected.append(f"FAIL {finding}")
        self.assertEqual(lines[:-1], expected)

    def test_c1_full_pass(self):
        # Even when the counts are correct, a wrong exit or missing trailer breaks the CLI contract.
        self.assert_report(self.sizes(AGREED), counts=(2, 2, 0, 0, 0))

    def test_c2_findings_trailer(self):
        # Input refusal must have one reason followed by the shared failure trailer, not an early exit.
        self.assert_report(self.run_cli("--sizes", str(self.root)), finding="unsafe-input")

    def test_c2_1_unsafe_input(self):
        # A normal open can follow a symlink or hang opening a FIFO.
        self.path.write_bytes(AGREED)
        link = self.root / "link"
        link.symlink_to(self.path)
        dangling = self.root / "dangling"
        dangling.symlink_to(self.root / "missing-target")
        fifo = self.root / "fifo"
        os.mkfifo(fifo)
        for target in (link, dangling, fifo):
            with self.subTest(kind=target.name):
                self.assert_report(self.run_cli("--sizes", str(target)), finding="unsafe-input")

    def test_c2_2_unreadable_input(self):
        # Do not replace malformed UTF-8 or leak an OS error after stat succeeds.
        self.assert_report(self.sizes(b"12 oz\n\xff"), finding="unreadable-input")
        with patch.object(CHECK, "open", create=True, side_effect=PermissionError(str(self.path))):
            self.assert_report(self.in_process("--sizes", str(self.path)), finding="unreadable-input")

    def test_c2_3_too_large(self):
        # Checking decoded characters would miss multibyte oversize; the limit itself is admitted.
        self.assert_report(self.sizes("é".encode("utf-8") * 8193), finding="too-large")
        self.assert_report(self.sizes(b" " * 16378 + b"12 oz\n"), counts=(1, 1, 0, 0, 0))

    def test_c2_4_too_many_lines(self):
        # Counting only non-blank lines or slicing at the cap would silently accept oversized input.
        self.assert_report(self.sizes(b"\n" * 200 + b"12 oz\n"), finding="too-many-lines")
        self.assert_report(self.sizes(b"\n" * 199 + b"12 oz\n"), counts=(1, 1, 0, 0, 0))

    def test_c2_5_assets_invalid(self):
        # A pin failure must not fall back to unverified assets or print the exception.
        self.path.write_bytes(AGREED)
        for args in (("--examples",), ("--sizes", str(self.path))):
            with self.subTest(mode=args[0]), patch.object(
                CHECK.npp, "assets", side_effect=ValueError("synthetic-private-asset"),
            ):
                self.assert_report(self.in_process(*args), finding="assets-invalid")

    def test_c2_6_check_error(self):
        # An unexpected exception is not a stage rejection; _Failed is a stage rejection.
        self.path.write_bytes(b"12 oz\n")
        with patch.object(CHECK.identify, "_normalize", side_effect=RuntimeError("synthetic-private-error")):
            self.assert_report(self.in_process("--sizes", str(self.path)), finding="check-error")
        with patch.object(CHECK.identify, "_normalize", side_effect=CHECK.interpreter_local._Failed("fixture")):
            self.assert_report(self.in_process("--sizes", str(self.path)),
                               counts=(1, 0, 0, 1, 0), finding="stage-disagree 1")

    def test_c2_7_stage_disagree(self):
        # Neither is agreement; it must count separately and must not add to the finding.
        self.assert_report(self.sizes(b"unknown unit\n6 ct\n"),
                           counts=(2, 0, 0, 1, 1), finding="stage-disagree 1")
        self.assert_report(self.sizes(b"unknown unit\n"), counts=(1, 0, 0, 0, 1))

    def test_c3_usage_exit_2(self):
        # Cardinality and malformed flags must fail at parse time, with no stdout trailer.
        for args in ((), ("--unknown",), ("--sizes",), ("--examples=extra",),
                     ("--examples", "--sizes", str(self.path))):
            with self.subTest(args=args[:1]):
                result = self.run_cli(*args)
                self.assertEqual(result.returncode, 2)
                self.assertEqual(result.stdout, "")
                self.assertIn("usage:", result.stderr)

    def test_c4_read_only(self):
        # A rewrite or transient sidecar changes file or directory metadata even if bytes match.
        self.path.write_bytes(AGREED)
        before = (self.path.read_bytes(), self.path.stat().st_mtime_ns,
                  set(self.root.iterdir()), self.root.stat().st_mtime_ns)
        self.assert_report(self.run_cli("--sizes", str(self.path)), counts=(2, 2, 0, 0, 0))
        after = (self.path.read_bytes(), self.path.stat().st_mtime_ns,
                 set(self.root.iterdir()), self.root.stat().st_mtime_ns)
        self.assertEqual(after, before)

    def test_c5_no_private_values(self):
        # Per-size diagnostics and argparse's default unknown-argument text can disclose input.
        canary = "synthetic-private-size-phrase"
        report = self.sizes(f"12 oz.\n{canary}\n".encode("utf-8"))
        self.assert_report(report, counts=(2, 0, 1, 0, 1), finding="stage-disagree 1")
        usage = self.run_cli("--examples", canary, str(self.path))
        self.assertEqual(usage.returncode, 2)
        self.assertEqual(usage.stdout, "")
        for result in (report, usage):
            for private in (canary, "12 oz.", str(self.path)):
                self.assertTrue(private not in result.stdout + result.stderr, "private value leaked")

    def test_c6_agree(self):
        # A parser that drops whitespace-padded input or the fl oz wording misses a kept size.
        self.assert_report(self.sizes(b"  12 oz\t\r\n\r\n 16 fl oz \r\n"), counts=(2, 2, 0, 0, 0))

    def test_c7_disagree_pins(self):
        # Misusing one stage's matcher for both, or reversing the buckets, changes these totals.
        self.assert_report(self.sizes(b"12 oz\n12 oz.\n6 ct\n"),
                           counts=(3, 1, 1, 1, 0), finding="stage-disagree 2")
        self.assert_report(self.sizes(b"1 1/2 lb\n500 mg\n12 count\n2 pack\n"),
                           counts=(4, 0, 2, 2, 0), finding="stage-disagree 4")

    def test_c8_live_examples(self):
        # Reading every row (including nulls) or misloading the pinned source changes the total.
        self.assert_report(self.run_cli("--examples"), counts=(3, 3, 0, 0, 0))
