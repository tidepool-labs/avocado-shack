"""Offline CLI contract tests for the S4 wording guard."""

from contextlib import redirect_stderr, redirect_stdout
import importlib.util
import io
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import patch


ROOT = Path(__file__).resolve().parents[2]
SCRIPT = ROOT / "scripts/hass/npp_shop_wording_guard.py"
PASS = "PASS npp_shop_wording_guard"
FAIL = "FAIL npp_shop_wording_guard"


class NppShopWordingGuardTests(unittest.TestCase):
    def setUp(self):
        temporary = tempfile.TemporaryDirectory()
        self.addCleanup(temporary.cleanup)
        self.fixture_dir = Path(temporary.name)
        spec = importlib.util.spec_from_file_location("npp_shop_wording_guard", SCRIPT)
        if spec is None or spec.loader is None:
            self.fail("wording guard has no import loader")
        self.guard = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(self.guard)
        self.research = self.guard.research

    def run_cli(self, *args):
        result = subprocess.run(
            [sys.executable, "-B", str(SCRIPT), *args], cwd=self.fixture_dir,
            capture_output=True, text=True, timeout=10, check=False,
        )
        return result.returncode, result.stdout, result.stderr

    def run_main(self):
        stdout, stderr = io.StringIO(), io.StringIO()
        with redirect_stdout(stdout), redirect_stderr(stderr):
            status = self.guard.main([])
        return status, stdout.getvalue(), stderr.getvalue()

    def assert_trailer(self, result, status, trailer):
        code, stdout, stderr = result
        self.assertEqual(code, status, stdout + stderr)
        self.assertEqual(stderr, "")
        lines = stdout.splitlines()
        self.assertTrue(lines)
        self.assertEqual(lines[-1], trailer)
        return lines[:-1]

    def assert_findings(self, result, expected):
        lines = self.assert_trailer(result, 1, FAIL)
        self.assertEqual([line for line in lines if line.startswith("FAIL ")], expected)
        return lines

    def test_c1_full_pass(self):
        # A good result must survive the real entry point and exit zero.
        self.assert_trailer(self.run_cli(), 0, PASS)

    def test_c2_findings_trailer(self):
        # A later good result must not reset failure or hide an earlier finding.
        with patch.object(self.research, "CONTRARY", ()), patch.object(
            self.research, "OWNER_WORDS", frozenset()
        ):
            self.assert_findings(self.run_main(), [
                *[f"FAIL shop-missed {i}" for i in range(8)],
                *[f"FAIL owner-refused {i}" for i in range(1, 6)],
            ])

    def test_c2_1_shop_missed(self):
        # Losing a single shop case reports its index, not a whole-group error.
        original = self.research._contrary

        def miss_one(page, name):
            if page.blocks == ["The brands we stock include Miners Orchards."]:
                return False
            return original(page, name)

        with patch.object(self.research, "_contrary", side_effect=miss_one):
            self.assert_findings(self.run_main(), ["FAIL shop-missed 4"])

    def test_c2_2_owner_refused(self):
        # A rejected valid owner must be attributed to the positive owner group.
        original = self.research._owner
        with patch.object(self.research, "_owner", side_effect=lambda entity, name: (
            False if entity == "Miners Orchards, Inc." else original(entity, name)
        )):
            self.assert_findings(self.run_main(), ["FAIL owner-refused 5"])

    def test_c2_3_owner_accepted(self):
        # Accidentally allowing a retailer suffix must fail, not go unreported.
        expanded = self.research.OWNER_WORDS | {"grocery"}
        with patch.object(self.research, "OWNER_WORDS", expanded):
            self.assert_findings(self.run_main(), ["FAIL owner-accepted 1"])

    def test_c2_4_check_error(self):
        # Do not swallow an incomplete check or leak exception text to either stream.
        for predicate in ("_contrary", "_owner"):
            with self.subTest(predicate=predicate):
                original = getattr(self.research, predicate)

                def raise_once(value, name):
                    if first_call:
                        first_call.pop()
                        raise RuntimeError("synthetic error detail")
                    return original(value, name)

                first_call = [True]
                with patch.object(self.research, predicate, side_effect=raise_once):
                    lines = self.assert_findings(self.run_main(), ["FAIL check-error"])
                self.assertEqual(len(lines), 17)  # All 16 OWN rows still ran.
                self.assertNotIn("synthetic error detail", "\n".join(lines))

    def test_c3_usage_exit_2(self):
        # Neither ignored arguments nor argparse's default help is an accepted run.
        for argument in ("extra", "--unknown", "--help", "--"):
            with self.subTest(argument=argument):
                code, stdout, stderr = self.run_cli(argument)
                self.assertEqual(code, 2)
                self.assertEqual(stdout, "")  # No stdout trailer on usage errors.
                self.assertTrue(stderr.startswith("usage: "))
                self.assertIn(": error: ", stderr.splitlines()[-1])

    def test_c4_read_only(self):
        # Detect caches, changed contents and additions, including parent metadata.
        def snapshot():
            entries = {}
            for tree in (ROOT / "hass", ROOT / "storefront-mockup"):
                for path in (tree, *tree.rglob("*")):
                    info = path.lstat()
                    entries[path.relative_to(ROOT)] = (info.st_size, info.st_mtime_ns)
            return entries

        before = snapshot()
        self.assert_trailer(self.run_cli(), 0, PASS)
        self.assertEqual(snapshot(), before)

    def test_c5_output_shape(self):
        # No debug text or malformed report rows on success or on a failing run.
        cases = [(0, PASS, self.run_cli())]
        with patch.object(self.research, "OWNER_WORDS", frozenset()):
            cases.append((1, FAIL, self.run_main()))
        for status, trailer, result in cases:
            with self.subTest(status=status):
                lines = self.assert_trailer(result, status, trailer)
                for line in lines:
                    self.assertRegex(line, (
                        r"\A(?:own (?:[0-9]|1[0-5]) contrary=(?:yes|no)|"
                        r"FAIL (?:shop-missed [0-7]|owner-refused [0-5]|"
                        r"owner-accepted [0-4]|check-error))\Z"
                    ))

    def test_c6_fixture(self):
        # Both reports must use the repo predicates rather than cached verdicts.
        with self.subTest(rule="CONTRARY"), patch.object(self.research, "CONTRARY", ()):
            lines = self.assert_findings(self.run_main(), [f"FAIL shop-missed {i}" for i in range(8)])
            self.assertEqual([line for line in lines if line.startswith("own ")],
                             [f"own {i} contrary=no" for i in range(16)])
        with self.subTest(rule="OWNER_WORDS"), patch.object(self.research, "OWNER_WORDS", frozenset()):
            self.assert_findings(self.run_main(), [f"FAIL owner-refused {i}" for i in range(1, 6)])

    def test_c7_live_pins(self):
        # A shifted maker overlap is observable in review but is not a CLI finding.
        lines = self.assert_trailer(self.run_cli(), 0, PASS)
        overlaps = {1, 2, 3, 5, 8, 12}
        self.assertEqual(lines, [
            f"own {i} contrary={'yes' if i in overlaps else 'no'}" for i in range(16)
        ])
