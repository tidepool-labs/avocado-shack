"""Contract tests for the offline NPP version-row checker."""

from contextlib import redirect_stderr, redirect_stdout
import hashlib
import importlib.util
import io
import json
import os
from pathlib import Path
import subprocess
import sys
from tempfile import TemporaryDirectory
from types import SimpleNamespace
import unittest
from unittest.mock import patch


REPO = Path(__file__).resolve().parents[2]
SCRIPT = REPO / "scripts/hass/npp_version_freeze_rows.py"
PASS = "PASS npp_version_freeze_rows"
FAIL = "FAIL npp_version_freeze_rows"
PINS = [
    'case 0 n=1 parent=None listing={"a":"fixture","b":1} patch={} state=building current=1',
    'case 1 n=2 parent=1 listing={"name":"Fig Jam"} patch={"name":"Fig Jam"} state=building current=2',
    r'case 2 n=1 parent=None listing={"name":"Caf\u00e9 Jam"} patch={} state=building current=1',
    'case 3 error=ValueError rows=0 current=None',
    'case 4 n=3 parent=2 listing={"a":[3,1],"z":{"a":2,"b":1}} patch={"z":{"b":1}} state=building current=3',
]


def snapshot():
    entries = {}
    for tree in (REPO / "hass", REPO / "storefront-mockup"):
        for path in (tree, *tree.rglob("*")):
            st = path.lstat()
            entries[path.relative_to(REPO)] = (st.st_size, st.st_mtime_ns)
    return entries


class NppVersionFreezeRowsTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        spec = importlib.util.spec_from_file_location("npp_version_freeze_rows", SCRIPT)
        assert spec is not None and spec.loader is not None
        cls.tool = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(cls.tool)

    def cli(self, *args):
        # Run away from the repository so the CLI must locate its own imports.
        with TemporaryDirectory() as directory:
            return subprocess.run(
                [sys.executable, "-B", str(SCRIPT), *args], cwd=directory,
                env={**os.environ, "TMPDIR": directory},
                capture_output=True, text=True, timeout=10, check=False,
            )

    def run_main(self, status, trailer):
        stdout, stderr = io.StringIO(), io.StringIO()
        with redirect_stdout(stdout), redirect_stderr(stderr):
            actual_status = self.tool.main([])
        self.assertEqual(actual_status, status, stdout.getvalue() + stderr.getvalue())
        self.assertEqual(stderr.getvalue(), "")
        lines = stdout.getvalue().splitlines()
        self.assertEqual(lines[-1:], [trailer])
        return lines[:-1]

    def test_c1_full_pass(self):
        # The entrypoint might not propagate main's status or print its final verdict.
        result = self.cli()
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(result.stdout.splitlines()[-1:], [PASS])

    def test_c2_findings_trailer(self):
        # A finding must fail the run without suppressing the second finding or later cases.
        with (patch.object(self.tool.job, "hashlib", SimpleNamespace(sha256=hashlib.md5)),
              patch.object(self.tool.job, "dump", json.dumps)):
            body = self.run_main(1, FAIL)
        self.assertEqual([line for line in body if line.startswith("FAIL ")], [
            "FAIL sha-mismatch 0", "FAIL freeze-changed 0",
            "FAIL sha-mismatch 1", "FAIL freeze-changed 1",
            "FAIL sha-mismatch 2", "FAIL freeze-changed 2",
            "FAIL sha-mismatch 3", "FAIL freeze-changed 3",
            "FAIL sha-mismatch 4", "FAIL freeze-changed 4",
        ])

    def test_c2_1_sha_mismatch(self):
        # The checker must hash the stored text independently of the producer's digest.
        with patch.object(self.tool.job, "hashlib", SimpleNamespace(sha256=hashlib.md5)):
            body = self.run_main(1, FAIL)
        self.assertEqual(body, [
            PINS[0], "FAIL sha-mismatch 0", PINS[1], "FAIL sha-mismatch 1",
            PINS[2], "FAIL sha-mismatch 2", PINS[3], PINS[4], "FAIL sha-mismatch 4",
        ])

    def test_c2_2_freeze_changed(self):
        # Syntactically valid JSON with changed bytes must fail, even with a matching digest.
        with patch.object(self.tool.job, "dump", json.dumps):
            body = self.run_main(1, FAIL)
        self.assertEqual([line for line in body if line.startswith("FAIL ")],
                         [f"FAIL freeze-changed {i}" for i in range(5)])

    def test_c2_3_check_error(self):
        # An asset-read exception must not become a traceback, a leak, or success.
        with patch.object(self.tool.npp, "assets", side_effect=RuntimeError("fixture detail")):
            self.assertEqual(self.run_main(1, FAIL), ["FAIL check-error"])

    def test_c3_usage_exit_2(self):
        # A positional, an unknown flag, and argparse's usual help flag aren't admitted.
        for args in (("fixture",), ("--unknown",), ("--help",), ("--",)):
            with self.subTest(args=args):
                result = self.cli(*args)
                self.assertEqual(result.returncode, 2)
                self.assertEqual(result.stdout, "")
                self.assertEqual(result.stderr.splitlines()[-1:], [
                    f"{SCRIPT.name}: error: unrecognized arguments: {args[0]}",
                ])

    def test_c4_read_only(self):
        # An accidental state file or rewrite must not survive the fixture-only run.
        before = snapshot()
        result = self.cli()
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(result.stdout.splitlines()[-1:], [PASS])
        self.assertEqual(snapshot(), before)

    def test_c5_output_shape(self):
        # No diagnostic noise or extra blank lines are part of the report protocol.
        result = self.cli()
        self.assertEqual(result.returncode, 0)
        self.assertEqual(result.stderr, "")
        self.assertEqual(result.stdout, "\n".join([*PINS, PASS]) + "\n")

    def test_c6_fixture(self):
        # Default JSON admits NaN and stops pinning compact, sorted bytes.
        with patch.object(self.tool.job, "dump", json.dumps):
            body = self.run_main(1, FAIL)
        self.assertEqual(body, [
            'case 0 n=1 parent=None listing={"b": 1, "a": "fixture"} patch={} state=building current=1',
            "FAIL freeze-changed 0",
            'case 1 n=2 parent=1 listing={"name": "Fig Jam"} patch={"name": "Fig Jam"} state=building current=2',
            "FAIL freeze-changed 1",
            r'case 2 n=1 parent=None listing={"name": "Caf\u00e9 Jam"} patch={} state=building current=1',
            "FAIL freeze-changed 2",
            'case 3 n=1 parent=None listing={"price": NaN} patch={} state=building current=1',
            "FAIL freeze-changed 3",
            'case 4 n=3 parent=2 listing={"z": {"b": 1, "a": 2}, "a": [3, 1]} '
            'patch={"z": {"b": 1}} state=building current=3',
            "FAIL freeze-changed 4",
        ])

    def test_c7_live_pins(self):
        # Independent literals catch drift in persisted parent/version/JSON and partial NaN writes.
        self.assertEqual(self.run_main(0, PASS), PINS)
