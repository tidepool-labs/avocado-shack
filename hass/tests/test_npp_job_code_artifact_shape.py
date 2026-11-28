"""Offline contract tests for the listing-code artifact audit."""

from contextlib import redirect_stderr, redirect_stdout
import importlib.util
import io
from pathlib import Path
import re
import subprocess
import sys
from tempfile import TemporaryDirectory
import unittest
from unittest.mock import patch

from hass.npp import receipt

ROOT = Path(__file__).resolve().parents[2]
SCRIPT = ROOT / "scripts/hass/npp_job_code_artifact_shape.py"
PASS = "PASS npp_job_code_artifact_shape"
FAIL = "FAIL npp_job_code_artifact_shape"
SPEC = importlib.util.spec_from_file_location(SCRIPT.stem, SCRIPT)
assert SPEC is not None and SPEC.loader is not None
AUDIT = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(AUDIT)


def run_main():
    stdout, stderr = io.StringIO(), io.StringIO()
    with redirect_stdout(stdout), redirect_stderr(stderr):
        status = AUDIT.main([])
    return status, stdout.getvalue(), stderr.getvalue()


def run_cli(*args, cwd=ROOT):
    result = subprocess.run([sys.executable, "-B", str(SCRIPT), *args], cwd=cwd,
                            capture_output=True, text=True, timeout=10)
    return result.returncode, result.stdout, result.stderr


def snapshot():
    entries = {}
    for name in ("hass", "storefront-mockup"):
        tree = ROOT / name
        for path in (tree, *tree.rglob("*")):
            info = path.lstat()
            entries[path.relative_to(ROOT)] = (info.st_size, info.st_mtime_ns)
    return entries


def code_source(*iterators):
    return "class Conversation:\n    def _code(self, digest):\n" + "".join(
        f"        for size in {iterator}:\n            if digest[:size]:\n                return digest[:size]\n"
        for iterator in iterators
    )


class NppJobCodeArtifactShapeTests(unittest.TestCase):
    def assert_run(self, result, status, trailer):
        actual_status, stdout, stderr = result
        self.assertEqual(stderr, "")
        self.assertEqual(actual_status, status)
        lines = stdout.splitlines()
        self.assertEqual(lines[-1:], [trailer])
        return lines

    def test_c1_full_pass(self):
        # A checkout-relative import that depended on cwd would break CLI use.
        with TemporaryDirectory() as tmp:
            self.assert_run(run_cli(cwd=Path(tmp)), 0, PASS)

    def test_c2_findings_trailer(self):
        # A late refusal must change the aggregate status and final verdict.
        with patch.object(receipt, "JOB_RE", r"[0-9a-f]{4,10}"):
            lines = self.assert_run(run_main(), 1, FAIL)
        self.assertEqual([line for line in lines[:-1] if line.startswith("FAIL ")],
                         ["FAIL code-refused 12"])

    def test_c2_1_code_refused(self):
        # A writer refusal must not skip the receipt, and a dispatch refusal
        # must count even when the write worked. Neither can count twice.
        write_card = receipt.Artifacts.write_card
        read_artifact = receipt.read_artifact

        def fail_card(artifacts, code, png):
            if len(code) == 4:
                raise ValueError("synthetic card refusal")
            return write_card(artifacts, code, png)

        def fail_receipt(path):
            if path.name == "receipt.json" and len(path.parent.name) == 6:
                raise ValueError("synthetic receipt refusal")
            return read_artifact(path)

        with (patch.object(receipt.Artifacts, "write_card", fail_card),
              patch.object(receipt, "read_artifact", fail_receipt)):
            lines = self.assert_run(run_main(), 1, FAIL)
        self.assertEqual(lines[1:5], ["code size=4 card=refused receipt=ok",
                                      "FAIL code-refused 4",
                                      "code size=6 card=ok receipt=refused",
                                      "FAIL code-refused 6"])
        self.assertEqual([line for line in lines[:-1] if line.startswith("FAIL ")],
                         ["FAIL code-refused 4", "FAIL code-refused 6"])

    def test_c2_2_sizes_not_found(self):
        # Missing, ambiguous or unusable ranges must not fall back to old pins.
        with TemporaryDirectory() as tmp:
            source = Path(tmp) / "conversation.py"
            for iterators in (("(4, 6)",), ("range(4, 13, 2)", "range(1, 5, 1)"),
                              ("range(start, 13, 2)",), ("range(4, 13, 0)",),
                              ("range(8, 4, 2)",), ("range(4, 15, 2)",)):
                with self.subTest(iterators=iterators):
                    source.write_text(code_source(*iterators), encoding="utf-8")
                    with patch.object(AUDIT, "SOURCE", source):
                        lines = self.assert_run(run_main(), 1, FAIL)
                    self.assertEqual(lines, ["FAIL sizes-not-found", FAIL])

    def test_c2_3_parse_error(self):
        # No traceback (or source excerpt) for missing, invalid or undecodable source.
        with TemporaryDirectory() as tmp:
            source = Path(tmp) / "conversation.py"
            with patch.object(AUDIT, "SOURCE", source):
                for raw in (None, b"class Conversation(:\n", b"\xff"):
                    with self.subTest(raw=raw):
                        if raw is not None:
                            source.write_bytes(raw)
                        lines = self.assert_run(run_main(), 1, FAIL)
                        self.assertEqual(lines, ["FAIL parse-error", FAIL])

    def test_c2_4_check_error(self):
        # An I/O fault must not be mislabeled as code refusal or leak its detail.
        with patch.object(receipt.Artifacts, "write_receipt", side_effect=OSError("fixture-detail")):
            lines = self.assert_run(run_main(), 1, FAIL)
        self.assertEqual(lines, ["codes sizes=4,6,8,10,12", "FAIL check-error", FAIL])

    def test_c3_usage_exit_2(self):
        # No accepted arguments, including argparse's usual help flag.
        for arg in ("fixture", "--unknown", "--help", "--"):
            with self.subTest(arg=arg):
                status, stdout, stderr = run_cli(arg)
                self.assertEqual(status, 2)
                self.assertEqual(stdout, "")  # There is no stdout trailer for usage errors.
                self.assertEqual(stderr.splitlines()[-1],
                                 f"{SCRIPT.name}: error: unrecognized arguments: {arg}")

    def test_c4_read_only(self):
        # Using a repo-relative artifact root could pollute the Hass or site tree.
        before = snapshot()
        self.assert_run(run_cli(), 0, PASS)
        self.assertEqual(snapshot(), before)

    def test_c5_output_shape(self):
        # Debug lines or exception details must not escape into the report.
        def broken_read(path):
            if path.name == "receipt.json":
                raise RuntimeError("fixture-detail")
            raise ValueError("fixture-card-refused")

        with patch.object(receipt, "read_artifact", broken_read):
            lines = self.assert_run(run_main(), 1, FAIL)
        self.assertRegex(lines[0], r"^codes sizes=\d+(?:,\d+)*$")
        self.assertEqual(lines[1:], ["FAIL code-refused 4", "FAIL check-error", FAIL])
        with patch.object(receipt, "JOB_RE", r"[0-9a-f]{4,8}"):
            lines = self.assert_run(run_main(), 1, FAIL)
        self.assertRegex(lines[0], r"^codes sizes=\d+(?:,\d+)*$")
        for line in lines[1:-1]:
            self.assertRegex(line, r"^(?:code size=\d+ card=(?:ok|refused) "
                                   r"receipt=(?:ok|refused)|FAIL code-refused \d+)$")

    def test_c6_fixture(self):
        # A narrower job ID gate must refuse both artifacts for both longer codes.
        with patch.object(receipt, "JOB_RE", re.compile(r"[0-9a-f]{4,8}")):
            lines = self.assert_run(run_main(), 1, FAIL)
        self.assertEqual(lines[-5:], ["code size=10 card=refused receipt=refused",
                                      "FAIL code-refused 10",
                                      "code size=12 card=refused receipt=refused",
                                      "FAIL code-refused 12", FAIL])

    def test_c7_live_pins(self):
        # Pin the measured producer lengths and each real artifact round trip.
        lines = self.assert_run(run_main(), 0, PASS)
        self.assertEqual(lines, ["codes sizes=4,6,8,10,12", *(
            f"code size={n} card=ok receipt=ok" for n in (4, 6, 8, 10, 12)
        ), PASS])

    def test_alternate_range_is_exercised(self):
        # A hardcoded set of sizes could pass main while missing a producer change.
        with TemporaryDirectory() as tmp:
            source = Path(tmp) / "conversation.py"
            source.write_text(code_source("range(11, 4, -3)"), encoding="utf-8")
            with patch.object(AUDIT, "SOURCE", source):
                lines = self.assert_run(run_main(), 0, PASS)
        self.assertEqual(lines, ["codes sizes=11,8,5", *(
            f"code size={n} card=ok receipt=ok" for n in (11, 8, 5)
        ), PASS])
