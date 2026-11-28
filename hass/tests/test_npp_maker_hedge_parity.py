"""Offline contract tests for the maker hedge parity CLI."""

from contextlib import redirect_stderr, redirect_stdout
import importlib.util
import io
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import DEFAULT, patch


ROOT = Path(__file__).resolve().parents[2]
SCRIPT = ROOT / "scripts/hass/npp_maker_hedge_parity.py"
PASS = "PASS npp_maker_hedge_parity"
FAIL = "FAIL npp_maker_hedge_parity"
PLAIN = "made by Etto Farm"
MAYBE = "made by maybe Etto Farm"
PERHAPS = "made by perhaps Etto Farm"
OR = "made by Etto Farm or Bee Farm"


def load_script():
    spec = importlib.util.spec_from_file_location(SCRIPT.stem, SCRIPT)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    with patch.object(sys, "path", sys.path.copy()):
        spec.loader.exec_module(module)
    return module


def snapshot():
    entries = {}
    for tree in (ROOT / "hass", ROOT / "storefront-mockup"):
        for path in (tree, *tree.rglob("*")):
            info = path.lstat()
            entries[path.relative_to(ROOT)] = (info.st_size, info.st_mtime_ns)
    return entries


class MakerHedgeParityTests(unittest.TestCase):
    def run_cli(self, *args):
        with tempfile.TemporaryDirectory() as cwd:
            return subprocess.run(
                [sys.executable, "-B", str(SCRIPT), *args],
                cwd=cwd, capture_output=True, text=True, timeout=10,
            )

    def run_main(self, module, wordings):
        out, err = io.StringIO(), io.StringIO()
        with patch.object(module, "WORDINGS", wordings), redirect_stdout(out), redirect_stderr(err):
            code = module.main([])
        self.assertEqual(err.getvalue(), "")
        return code, out.getvalue().splitlines()

    def test_c1_full_pass(self):
        # An unconditional failure would make even a plain, agreed maker fail.
        code, lines = self.run_main(load_script(), (PLAIN,))
        self.assertEqual(code, 0)
        self.assertEqual(lines[-1], PASS)

    def test_c2_findings_trailer(self):
        # Printing a finding without making the overall run fail misleads callers.
        code, lines = self.run_main(load_script(), (PERHAPS, PLAIN))
        self.assertEqual(code, 1)
        self.assertEqual(lines[-1], FAIL)
        self.assertEqual([line for line in lines[:-1] if line.startswith("FAIL ")],
                         ["FAIL hedge-split 01"])

    def test_c2_1_hedge_split(self):
        # A one-sided comparison, early break or reordering loses a split.
        code, lines = self.run_main(load_script(), (PERHAPS, MAYBE, OR))
        self.assertEqual(code, 1)
        self.assertEqual(lines[-1], FAIL)
        self.assertEqual(lines[:-1], [
            "maker 01 s3=none s10=patch",
            "FAIL hedge-split 01",
            "maker 02 s3=none s10=ask",
            "maker 03 s3=kept s10=ask",
            "FAIL hedge-split 03",
        ])

    def test_c2_2_check_error(self):
        # Either reader can fail: no exception detail, no silent skip, no early stop.
        module = load_script()
        for reader, name in ((module.missing, "_owner_maker"), (module.edits, "read")):
            with self.subTest(reader=name):
                original = getattr(reader, name)
                with patch.object(reader, name, wraps=original, side_effect=[
                    ValueError("synthetic exception detail"), DEFAULT,
                ]):
                    code, lines = self.run_main(module, (MAYBE, PLAIN))
                self.assertEqual(code, 1)
                self.assertEqual(lines[-1], FAIL)
                self.assertEqual(lines[:-1], ["FAIL check-error", "maker 02 s3=kept s10=patch"])

    def test_c3_usage_exit_2(self):
        # Do not ignore argv or permit argparse's default help success path.
        for arg in ("unexpected", "--unknown", "--help", "--"):
            with self.subTest(arg=arg):
                result = self.run_cli(arg)
                self.assertEqual(result.returncode, 2)
                self.assertEqual(result.stdout, "")  # No stdout line or trailer.
                self.assertEqual(result.stderr.splitlines()[-1],
                                 f"{SCRIPT.name}: error: unrecognized arguments: {arg}")

    def test_c4_read_only(self):
        # An accidental report/cache write into either source tree changes its snapshot.
        before = snapshot()
        result = self.run_cli()
        self.assertEqual(result.returncode, 1)
        self.assertEqual(result.stdout.splitlines()[-1], FAIL)
        self.assertEqual(snapshot(), before)

    def test_c5_output_shape(self):
        # Never log the wording, the maker value or any extra diagnostics.
        result = self.run_cli()
        lines = result.stdout.splitlines()
        self.assertEqual(result.returncode, 1)
        self.assertEqual(lines[-1], FAIL)
        self.assertEqual(result.stderr, "")
        for line in lines[:-1]:
            self.assertRegex(line, r"\A(?:maker [0-9]{2} s3=(?:kept|none) s10=(?:patch|ask)"
                                   r"|FAIL hedge-split [0-9]{2}|FAIL check-error)\Z")

    def test_c6_fixture(self):
        # The same code must use the patched corpus and distinguish both agreement states.
        code, lines = self.run_main(load_script(), (PLAIN, MAYBE))
        self.assertEqual(code, 0)
        self.assertEqual(lines[-1], PASS)
        self.assertEqual(lines[:-1], ["maker 01 s3=kept s10=patch", "maker 02 s3=none s10=ask"])

    def test_c7_live_pins(self):
        # A change to the fixed corpus or either merged reader can move these pins.
        result = self.run_cli()
        lines = result.stdout.splitlines()
        self.assertEqual(result.returncode, 1)
        self.assertEqual(lines[-1], FAIL)
        makers = [line for line in lines if line.startswith("maker ")]
        self.assertEqual(len(makers), 12)
        self.assertEqual(makers[3], "maker 04 s3=none s10=patch")
        self.assertEqual(makers[5], "maker 06 s3=kept s10=ask")
        self.assertEqual([line for line in lines[:-1] if line.startswith("FAIL ")], [
            "FAIL hedge-split 02", "FAIL hedge-split 04", "FAIL hedge-split 06", "FAIL hedge-split 07",
            "FAIL hedge-split 08", "FAIL hedge-split 09", "FAIL hedge-split 10", "FAIL hedge-split 12",
        ])
