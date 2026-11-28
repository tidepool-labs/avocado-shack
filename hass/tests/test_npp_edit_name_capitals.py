"""Offline checks for the S10 name-capitals diagnostic (not a casing fix)."""

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
SCRIPT = ROOT / "scripts/hass/npp_edit_name_capitals.py"
PASS = "PASS npp_edit_name_capitals"
FAIL = "FAIL npp_edit_name_capitals"


def snapshot():
    entries = {}
    for tree in (ROOT / "hass", ROOT / "storefront-mockup"):
        for path in (tree, *tree.rglob("*")):
            info = path.lstat()
            entries[path.relative_to(ROOT)] = (info.st_size, info.st_mtime_ns)
    return entries


class NppEditNameCapitalsTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        spec = importlib.util.spec_from_file_location("npp_edit_name_capitals", SCRIPT)
        if spec is None or spec.loader is None:
            raise ImportError("could not load the name-capitals diagnostic")
        cls.tool = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(cls.tool)

    def invoke(self, *args):
        with TemporaryDirectory() as directory:
            return subprocess.run(
                [sys.executable, "-B", str(SCRIPT), *args], cwd=directory,
                capture_output=True, text=True, timeout=10,
            )

    def run_main(self):
        stdout, stderr = io.StringIO(), io.StringIO()
        with redirect_stdout(stdout), redirect_stderr(stderr):
            code = self.tool.main([])
        return subprocess.CompletedProcess([], code, stdout.getvalue(), stderr.getvalue())

    def assert_run(self, result, code, trailer):
        self.assertEqual(result.returncode, code, result.stderr)
        self.assertEqual(result.stderr, "")
        lines = result.stdout.splitlines()
        self.assertEqual(lines[-1:], [trailer])
        return lines[:-1]

    def run_cases(self, *cases):
        with patch.object(self.tool, "CASES", cases):
            return self.run_main()

    def test_c1_full_pass(self):
        # A clean edit must not inherit a failing exit or trailer from the baseline.
        result = self.run_cases(("from Joe's Honey", "supplier"))
        self.assertEqual(self.assert_run(result, 0, PASS), ['case 0 supplier "Joe\'s Honey"'])

    def test_c2_findings_trailer(self):
        # Mixed findings must not stop the loop or produce a successful trailer.
        result = self.run_cases(("made by joe's farm", "maker"), ("made by miners", "makerTown"))
        self.assertEqual(self.assert_run(result, 1, FAIL), [
            'case 0 maker "Joe\'S Farm"', "FAIL capital-after-apostrophe 0",
            "case 1 makerTown None", "FAIL no-patch 1",
        ])

    def test_c2_1_capital_after_apostrophe(self):
        # Both apostrophes count; a capital starting a normal name segment doesn't.
        named = self.tool.edits._named

        def curly(value):
            return named(value).replace("'", "’")

        for apostrophe, normalize in (("'", named), ("’", curly)):
            with self.subTest(apostrophe=apostrophe), patch.object(self.tool.edits, "_named", normalize):
                result = self.run_cases(
                    ("made by joe's farm", "maker"), ("made by o'neill farm", "maker"),
                )
                self.assertEqual(self.assert_run(result, 1, FAIL), [
                    f"case 0 maker {f'Joe{apostrophe}S Farm'!r}", "FAIL capital-after-apostrophe 0",
                    f"case 1 maker {f'O{apostrophe}Neill Farm'!r}",
                ])

    def test_c2_2_no_patch(self):
        # Patching the maker alone must not count as patching the requested town.
        result = self.run_cases(("made by miners", "makerTown"))
        self.assertEqual(self.assert_run(result, 1, FAIL), ["case 0 makerTown None", "FAIL no-patch 0"])

    def test_c2_3_check_error(self):
        # Neither startup nor per-case failures should dump a traceback or claim PASS.
        for module, name in ((self.tool.hass.npp, "assets"), (self.tool.edits, "read")):
            with self.subTest(call=name), patch.object(module, name, side_effect=RuntimeError("synthetic detail")):
                result = self.run_cases(("from Joe's Honey", "supplier"))
                self.assertEqual(self.assert_run(result, 1, FAIL), ["FAIL check-error"])

    def test_c3_usage_exit_2(self):
        # argparse normally accepts -- and help; this check accepts no arguments at all.
        for arg in ("extra", "--unknown", "--help", "--", ""):
            with self.subTest(arg=arg):
                result = self.invoke(arg)
                self.assertEqual(result.returncode, 2)
                self.assertEqual(result.stdout, "")
                self.assertTrue(result.stderr.startswith("usage:"), result.stderr)
                self.assertIn("error:", result.stderr.splitlines()[-1])

    def test_c4_read_only(self):
        # Catch new sidecars or rewrites, including ones that leave file sizes unchanged.
        before = snapshot()
        result = self.invoke()
        self.assertEqual(snapshot(), before)
        self.assert_run(result, 1, FAIL)

    def test_c5_output_shape(self):
        # Extra progress text or diagnostics must not leak into either output stream.
        lines = self.assert_run(self.invoke(), 1, FAIL)
        for line in lines:
            self.assertRegex(line, r"^(?:case [0-5] (?:supplier|maker|makerTown) (?:['\"].*['\"]|None)"
                                   r"|FAIL (?:capital-after-apostrophe [0-5]|no-patch [0-5]|check-error))$")
        self.assertEqual(sum(line.startswith("case ") for line in lines), 6)

    def test_c6_fixture(self):
        # A run must use the reader's actual patch values, not replay pinned findings.
        def word_initials(value):
            text = " ".join(self.tool.edits._unquote(value).split())
            return " ".join(word[0].upper() + word[1:] for word in text.split()) if text.islower() else text

        with patch.object(self.tool.edits, "_named", word_initials):
            result = self.run_main()
        self.assertEqual(self.assert_run(result, 0, PASS), [
            'case 0 supplier "Joe\'s Honey"',
            'case 1 maker "Joe\'s Farm"',
            'case 2 makerTown "O\'brien\'s Corner"',
            'case 3 maker "O\'neill Farm"',
            'case 4 supplier "Joe\'s Honey"',
            "case 5 makerTown 'St. Helena'",
        ])

    def test_c7_live_pins(self):
        # Pin the unchanged reader's six values and the exact order of the three findings.
        self.assertEqual(self.assert_run(self.invoke(), 1, FAIL), [
            'case 0 supplier "Joe\'S Honey"', "FAIL capital-after-apostrophe 0",
            'case 1 maker "Joe\'S Farm"', "FAIL capital-after-apostrophe 1",
            'case 2 makerTown "O\'Brien\'S Corner"', "FAIL capital-after-apostrophe 2",
            'case 3 maker "O\'Neill Farm"',
            'case 4 supplier "Joe\'s Honey"',
            "case 5 makerTown 'St. Helena'",
        ])
