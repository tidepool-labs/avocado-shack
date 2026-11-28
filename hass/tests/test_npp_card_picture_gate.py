"""Offline CLI and drift-detection contracts for the card picture gate."""

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

from hass import npp
from hass.npp import job, receipt


ROOT = Path(__file__).resolve().parents[2]
SCRIPT = ROOT / "scripts/hass/npp_card_picture_gate.py"
PASS = "PASS npp_card_picture_gate"
FAIL = "FAIL npp_card_picture_gate"


def snapshot():
    entries = {}
    for name in ("hass", "storefront-mockup"):
        tree = ROOT / name
        for path in (tree, *tree.rglob("*")):
            stat = path.lstat()
            entries[path.relative_to(ROOT)] = (stat.st_size, stat.st_mtime_ns)
    return entries


class CardPictureGateTests(unittest.TestCase):
    def setUp(self):
        self.tmp = self.enterContext(TemporaryDirectory())
        spec = importlib.util.spec_from_file_location("npp_card_picture_gate", SCRIPT)
        assert spec is not None and spec.loader is not None
        self.script = importlib.util.module_from_spec(spec)
        # The script adds its checkout to sys.path; don't leave it there for other tests.
        with patch.object(sys, "path", list(sys.path)):
            spec.loader.exec_module(self.script)

    def cli(self, *args):
        return subprocess.run(
            [sys.executable, "-B", str(SCRIPT), *args], cwd=self.tmp,
            env={**os.environ, "TMPDIR": self.tmp}, capture_output=True, text=True, timeout=20,
        )

    def run_main(self):
        out, err = io.StringIO(), io.StringIO()
        with patch("tempfile.tempdir", self.tmp), redirect_stdout(out), redirect_stderr(err):
            code = self.script.main([])
        self.assertEqual(err.getvalue(), "")
        return code, out.getvalue().splitlines()

    def writer_failure(self):
        with patch.object(receipt.Artifacts, "write_card", side_effect=OSError("fixture write failure")):
            return self.run_main()

    def test_c1_full_pass(self):
        # Running from another cwd must still load the repo and finish with exit zero.
        result = self.cli()
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(result.stdout.splitlines()[-1], PASS)
        self.assertEqual(result.stderr, "")

    def test_c2_findings_trailer(self):
        # A finding must propagate through the actual entry point to the process status.
        driver = Path(self.tmp) / "writer_failure.py"
        driver.write_text(
            "import runpy\nimport sys\nfrom unittest.mock import patch\n"
            "sys.path.insert(0, sys.argv[1])\nfrom hass.npp import receipt\n"
            "target = sys.argv[2]\nsys.argv = [target]\n"
            "with patch.object(receipt.Artifacts, 'write_card', side_effect=OSError):\n"
            "    runpy.run_path(target, run_name='__main__')\n",
            encoding="utf-8",
        )
        result = subprocess.run(
            [sys.executable, "-B", str(driver), str(ROOT), str(SCRIPT)], cwd=self.tmp,
            env={**os.environ, "TMPDIR": self.tmp}, capture_output=True, text=True, timeout=20,
        )
        lines = result.stdout.splitlines()
        self.assertEqual(result.returncode, 1, result.stderr)
        self.assertEqual(result.stderr, "")
        self.assertEqual(lines[-1], FAIL)
        self.assertEqual(lines.count(FAIL), 1)
        self.assertIn("FAIL gate-changed 0", lines[:-1])
        self.assertNotIn(PASS, lines)

    def test_c2_1_card_without_picture_match(self):
        # Repairing the mutable draft during finish must not erase the input mismatch.
        finish = job.Jobs.finish

        def repair_then_finish(jobs, job_row, segment, version, card, now):
            card.draft["assets"] = {card.image_path: "sha256:" + card.image_sha256}
            return finish(jobs, job_row, segment, version, card, now)

        with patch.object(job.Jobs, "finish", repair_then_finish):
            code, lines = self.run_main()
        self.assertEqual(code, 1)
        self.assertEqual(lines[-1], FAIL)
        self.assertEqual([line for line in lines[:-1] if line.startswith("FAIL ")], [
            "FAIL card-without-picture-match 3", "FAIL gate-changed 3",
        ])
        self.assertIn("case 3 outcome=card version=queued job=working attach=1 note=no", lines)

    def test_c2_2_gate_changed(self):
        # Report a finding for each changed observed line, not for unchanged refusals.
        code, lines = self.writer_failure()
        self.assertEqual(code, 1)
        self.assertEqual(lines[-1], FAIL)
        observed = [line for line in lines if line.startswith("case ")]
        changes = [f"FAIL gate-changed {i}" for i, (got, want) in enumerate(
            zip(observed, self.script.EXPECTED, strict=True)) if got != want]
        self.assertTrue(changes)
        self.assertEqual([line for line in lines[:-1] if line.startswith("FAIL ")], changes)

    def test_c2_3_check_error(self):
        # An unexpected repo failure is not a passing skip or an exception-text leak.
        with patch.object(npp, "assets", side_effect=RuntimeError("fixture exception detail")):
            code, lines = self.run_main()
        self.assertEqual(code, 1)
        self.assertEqual(lines, ["FAIL check-error", FAIL])

    def test_c3_usage_exit_2(self):
        # No help or option terminator escape hatch: every argument is a usage error.
        for argument in ("positional", "--unexpected", "--help", "--"):
            with self.subTest(argument=argument):
                result = self.cli(argument)
                self.assertEqual(result.returncode, 2)
                self.assertEqual(result.stdout, "")  # No last stdout line on usage errors.
                self.assertTrue(result.stderr.startswith("usage: "))
                self.assertIn("error:", result.stderr.splitlines()[-1])

    def test_c4_read_only(self):
        # Catch writes to the source/media trees instead of the isolated fixture root.
        before = snapshot()
        result = self.cli()
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(result.stdout.splitlines()[-1], PASS)
        self.assertEqual(snapshot(), before)
        self.assertEqual(list(Path(self.tmp).iterdir()), [])

    def test_c5_output_shape(self):
        # A debug print, traceback or artifact path would violate the CLI vocabulary.
        result = self.cli()
        self.assertEqual(result.stderr, "")
        for code, lines, expected_code, trailer in (
            (result.returncode, result.stdout.splitlines(), 0, PASS),
            (*self.writer_failure(), 1, FAIL),
        ):
            self.assertEqual(code, expected_code)
            self.assertEqual(lines[-1], trailer)
            for line in lines[:-1]:
                self.assertRegex(line, r"^(?:case \d+ outcome=[\w-]+ version=[\w-]+ job=[\w-]+ "
                                       r"attach=\d+ note=(?:yes|no)|"
                                       r"FAIL (?:card-without-picture-match \d+|gate-changed \d+|check-error))$")

    def test_c6_fixture(self):
        # A failed card write must not queue any of the previously eligible cards.
        code, lines = self.writer_failure()
        self.assertEqual(code, 1)
        self.assertEqual(lines[-1], FAIL)
        self.assertEqual([line for line in lines[:-1] if line.startswith("FAIL ")], [
            "FAIL gate-changed 0", "FAIL gate-changed 5", "FAIL gate-changed 6",
            "FAIL gate-changed 9", "FAIL gate-changed 10", "FAIL gate-changed 12",
        ])
        self.assertEqual([line for line in lines if line.startswith("case ")], [
            f"case {i} outcome=render-failed version=superseded job=editing attach=0 note=no"
            for i in range(13)
        ])

    def test_c7_live_pins(self):
        # Observe the real finish gate; chat, photo replacement, draft, storage,
        # persistence and note drift must remain visible even if EXPECTED is edited.
        code, lines = self.run_main()
        self.assertEqual(code, 0)
        self.assertEqual(lines, [
            "case 0 outcome=card version=queued job=working attach=1 note=no",
            "case 1 outcome=render-failed version=superseded job=editing attach=0 note=no",
            "case 2 outcome=render-failed version=superseded job=editing attach=0 note=no",
            "case 3 outcome=render-failed version=superseded job=editing attach=0 note=no",
            "case 4 outcome=render-failed version=superseded job=editing attach=0 note=no",
            "case 5 outcome=card version=queued job=working attach=1 note=no",
            "case 6 outcome=card version=queued job=working attach=1 note=no",
            "case 7 outcome=render-failed version=superseded job=editing attach=0 note=no",
            "case 8 outcome=render-failed version=superseded job=editing attach=0 note=no",
            "case 9 outcome=card version=queued job=working attach=1 note=yes",
            "case 10 outcome=card version=queued job=working attach=1 note=no",
            "case 11 outcome=render-failed version=superseded job=editing attach=0 note=no",
            "case 12 outcome=card version=queued job=working attach=1 note=no",
            PASS,
        ])
