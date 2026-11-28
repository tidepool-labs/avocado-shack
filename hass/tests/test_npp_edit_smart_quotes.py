"""Contract tests for the offline smart-punctuation diagnostic, not a parser fix."""

from contextlib import redirect_stderr, redirect_stdout
import importlib.util
import io
from pathlib import Path
import subprocess
import sys
from tempfile import TemporaryDirectory
import unittest
from unittest.mock import patch


ROOT = Path(__file__).resolve().parents[2]
SCRIPT = ROOT / "scripts/hass/npp_edit_smart_quotes.py"
SPEC = importlib.util.spec_from_file_location("npp_edit_smart_quotes", SCRIPT)
assert SPEC is not None and SPEC.loader is not None
TOOL = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(TOOL)

PASS = "PASS npp_edit_smart_quotes"
FAIL = "FAIL npp_edit_smart_quotes"
STRAIGHT = ("maker", "name", "maker,makerTown", "supplier", "supplier", "name")
LIVE_CURLY = ("ask_edit_unclear",) * 4 + ("supplier", "name")
TRANSLATE = str.maketrans({'’': "'", '‘': "'", '“': '"', '”': '"'})


def snapshot(root):
    entries = {}
    for path in (root, *root.rglob("*")):
        info = path.lstat()
        entries[path.relative_to(ROOT)] = (info.st_size, info.st_mtime_ns)
    return entries


def normalized(read, grammar, text, finance):
    return read(grammar, text.translate(TRANSLATE), finance)


class NppEditSmartQuotesTests(unittest.TestCase):
    def cli(self, *args):
        with TemporaryDirectory() as directory:
            return subprocess.run(
                [sys.executable, "-B", str(SCRIPT), *args], cwd=directory,
                text=True, capture_output=True, timeout=10,
            )

    def invoke(self):
        stdout, stderr = io.StringIO(), io.StringIO()
        with redirect_stdout(stdout), redirect_stderr(stderr):
            code = TOOL.main([])
        self.assertEqual(stderr.getvalue(), "")
        return code, stdout.getvalue().splitlines()

    def assert_result(self, code, lines, status, trailer):
        self.assertEqual(code, status, lines)
        self.assertEqual(lines[-1:], [trailer])

    def test_c1_full_pass(self):
        # Matching field names still pass when a patched value differs.
        read = TOOL.edits.read

        def different_value(grammar, text, finance):
            if text == "made by joe’s farm":
                text = "made by another farm"
            return normalized(read, grammar, text, finance)

        with patch.object(TOOL.edits, "read", side_effect=different_value) as called:
            code, lines = self.invoke()
        self.assert_result(code, lines, 0, PASS)
        self.assertEqual(called.call_count, 12)
        self.assertEqual(len(lines), 7)
        self.assertEqual(lines[0], "case 0 straight=maker curly=maker")

    def test_c2_findings_trailer(self):
        # Matched controls after the last finding must not reset a failing run.
        result = self.cli()
        lines = result.stdout.splitlines()
        self.assert_result(result.returncode, lines, 1, FAIL)
        self.assertEqual(lines[-2], "case 5 straight=name curly=name")
        self.assertEqual(result.stderr, "")

    def test_c2_1_curly_not_read(self):
        # Equal sets in a different order still differ; a straight reply isn't a baseline patch.
        read = TOOL.edits.read

        def changed_read(grammar, text, finance):
            if text == "made by joe's farm":
                text = "use my photo"
            result = normalized(read, grammar, text, finance)
            if text == "made by miners, o’brien":
                return TOOL.edits.Edit(patch=result.patch[::-1])
            return result

        with patch.object(TOOL.edits, "read", side_effect=changed_read):
            code, lines = self.invoke()
        self.assert_result(code, lines, 1, FAIL)
        self.assertEqual(lines[0], "case 0 straight=picture_request curly=maker")
        self.assertEqual(lines[2:4], [
            "case 2 straight=maker,makerTown curly=makerTown,maker",
            "FAIL curly-not-read 2",
        ])
        self.assertEqual([line for line in lines[:-1] if line.startswith("FAIL")],
                         ["FAIL curly-not-read 2"])

    def test_c2_2_check_error(self):
        # No traceback/exception text and no silent skipping when a call fails.
        for owner, name in ((TOOL.hass.npp, "assets"), (TOOL.edits, "Grammar")):
            with self.subTest(name=name):
                with patch.object(owner, name, side_effect=RuntimeError("fixture detail")) as called:
                    code, lines = self.invoke()
                called.assert_called_once()
                self.assert_result(code, lines, 1, FAIL)
                self.assertEqual(lines, ["FAIL check-error", FAIL])

        read = TOOL.edits.read

        def broken_read(grammar, text, finance):
            if text == "made by joe's farm":
                raise RuntimeError("fixture detail")
            return normalized(read, grammar, text, finance)

        with patch.object(TOOL.edits, "read", side_effect=broken_read) as called:
            code, lines = self.invoke()
        self.assert_result(code, lines, 1, FAIL)
        self.assertEqual(called.call_count, 12)
        self.assertEqual(lines[0], "FAIL check-error")
        self.assertEqual(lines[-2], "case 5 straight=name curly=name")
        self.assertEqual([line for line in lines[:-1] if line.startswith("FAIL")],
                         ["FAIL check-error"])
        self.assertNotIn("fixture detail", "\n".join(lines))

    def test_c3_usage_exit_2(self):
        # No switches, including argparse's usual implicit help and separator.
        for arg in ("unexpected", "--unknown", "--help", "--"):
            with self.subTest(arg=arg):
                result = self.cli(arg)
                self.assert_result(result.returncode, result.stderr.splitlines(), 2,
                                   "npp_edit_smart_quotes.py: error: unrecognized arguments")
                self.assertTrue(result.stderr.startswith("usage: "))
                self.assertEqual(result.stdout, "")

    def test_c4_read_only(self):
        # Catch generated files and in-place changes even if stdout is correct.
        trees = (ROOT / "hass", ROOT / "storefront-mockup")
        before = [snapshot(tree) for tree in trees]
        result = self.cli()
        self.assert_result(result.returncode, result.stdout.splitlines(), 1, FAIL)
        self.assertEqual([snapshot(tree) for tree in trees], before)

    def test_c5_output_shape(self):
        # Catch debug logs, malformed rows, duplicate trailers and stray stderr.
        result = self.cli()
        lines = result.stdout.splitlines()
        self.assert_result(result.returncode, lines, 1, FAIL)
        self.assertEqual(len(lines), 11)
        for line in lines[:-1]:
            self.assertRegex(line, r"^(case [0-5] straight=\w+(,\w+)* curly=\w+(,\w+)*"
                                   r"|FAIL curly-not-read [0-5]|FAIL check-error)$")
        self.assertEqual(result.stderr, "")

    def test_c6_fixture(self):
        # Translate input before the real reader, rather than invent its decisions.
        read = TOOL.edits.read
        with patch.object(TOOL.edits, "read", side_effect=lambda *args: normalized(read, *args)):
            code, lines = self.invoke()
        self.assert_result(code, lines, 0, PASS)
        self.assertEqual(lines, [
            *(f"case {i} straight={fields} curly={fields}" for i, fields in enumerate(STRAIGHT)),
            PASS,
        ])

    def test_c7_live_pins(self):
        # Real pinned parser results: four known findings and two double-quote controls.
        result = self.cli()
        lines = result.stdout.splitlines()
        self.assert_result(result.returncode, lines, 1, FAIL)
        expected = []
        for i, (straight, curly) in enumerate(zip(STRAIGHT, LIVE_CURLY)):
            expected.append(f"case {i} straight={straight} curly={curly}")
            if i < 4:
                expected.append(f"FAIL curly-not-read {i}")
        self.assertEqual(lines, [*expected, FAIL])
        self.assertEqual(result.stderr, "")
