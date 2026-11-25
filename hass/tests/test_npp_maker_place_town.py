"""Drift guard tests for scripts/hass/npp_maker_place_town.py (fixtures only, no network).

Contract protected: itemstd.classify_place answers 'town' only for 'Town, State';
a region, street address, contact or extra part is never a town. Believable bug each
test catches is named in its comment.
"""

import contextlib
import importlib.util
import io
import os
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile
import unittest
from unittest import mock

ROOT = Path(__file__).resolve().parents[2]
SCRIPT = ROOT / "scripts/hass/npp_maker_place_town.py"

from hass import itemstd  # noqa: E402

_spec = importlib.util.spec_from_file_location("npp_maker_place_town_under_test", SCRIPT)
tool = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(tool)

PASS = "PASS npp_maker_place_town"
FAIL = "FAIL npp_maker_place_town"
C7_LINES = [
    "case 0 place='town'", "case 1 place='other'", "case 2 place='region'", "case 3 place='region'",
    "case 4 place='region'", "case 5 place='region'", "case 6 place='region'", "case 7 place='blank'",
    "case 8 place='blank'", "case 9 place='other'", "case 10 place='town'", "case 11 place='other'",
    "case 12 place='other'", "case 13 place='region'",
]


def run_script(*args):
    return subprocess.run([sys.executable, "-B", str(SCRIPT), *args], cwd=ROOT,
                          capture_output=True, text=True, timeout=30)


def run_main():
    """Run main() in-process; returns (exit code, stdout lines)."""
    out = io.StringIO()
    with contextlib.redirect_stdout(out):
        code = tool.main([])
    return code, out.getvalue().splitlines()


def snapshot():
    result = {}
    for top in ("hass", "storefront-mockup"):
        for path in sorted((ROOT / top).rglob("*")):
            st = path.stat()
            result[str(path.relative_to(ROOT))] = (st.st_size, st.st_mtime_ns)
    return result


def findings(lines):
    return [x for x in lines if x.startswith("FAIL ") and x != FAIL]


class NppMakerPlaceTownTests(unittest.TestCase):
    def test_c1_full_pass(self):
        # A tool that exits non-zero or drops the trailer on a clean main would fail here.
        result = run_script()
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(result.stdout.splitlines()[-1], PASS)

    def test_c2_findings_trailer(self):
        # Findings must print after their case line, exit 1, and end with the FAIL trailer.
        with mock.patch.object(itemstd, "_REGION_NAMES", frozenset()):
            code, lines = run_main()
        self.assertEqual(code, 1)
        self.assertEqual(lines[-1], FAIL)
        self.assertEqual(lines.index("FAIL region-read-as-town 3"), lines.index("case 3 place='town'") + 1)
        self.assertEqual(lines.index("FAIL place-changed 3"), lines.index("FAIL region-read-as-town 3") + 1)

    def test_c2_1_region_read_as_town(self):
        # If region names stop matching, 'Central Coast, CA' and 'Napa Valley, CA' read as towns.
        with mock.patch.object(itemstd, "_REGION_NAMES", frozenset()):
            code, lines = run_main()
        self.assertEqual(code, 1)
        self.assertEqual(findings(lines), [
            "FAIL place-changed 2", "FAIL region-read-as-town 3", "FAIL place-changed 3",
            "FAIL place-changed 4", "FAIL region-read-as-town 13", "FAIL place-changed 13"])
        self.assertEqual(lines[-1], FAIL)

    def test_c2_2_place_changed(self):
        # Any pinned answer moving (here 'County' no longer a region) must be reported.
        with mock.patch.object(itemstd, "_REGION_SUFFIXES", ()):
            code, lines = run_main()
        self.assertEqual(code, 1)
        self.assertIn("FAIL place-changed 6", lines)
        self.assertEqual(lines[-1], FAIL)

    def test_c2_3_check_error(self):
        # A raising repo call must be a named FAIL once, stop the run, and never a traceback.
        with mock.patch.object(itemstd, "classify_place", side_effect=RuntimeError("boom")):
            code, lines = run_main()
        self.assertEqual(code, 1)
        self.assertEqual(lines, ["FAIL check-error", FAIL])

    def test_c2_3_check_error_stops_midway(self):
        # No further case is checked after the error: cases before it print, none after.
        real = itemstd.classify_place
        calls = []

        def flaky(place):
            calls.append(place)
            if len(calls) == 3:
                raise RuntimeError("boom")
            return real(place)

        with mock.patch.object(itemstd, "classify_place", side_effect=flaky):
            code, lines = run_main()
        self.assertEqual(code, 1)
        self.assertEqual(len(calls), 3)
        self.assertEqual(lines, C7_LINES[:2] + ["FAIL check-error", FAIL])

    def test_c3_usage_exit_2(self):
        # A stray argument must stay argparse's exit 2 with nothing on stdout.
        for args in (("extra",), ("--nope",)):
            with self.subTest(args=args):
                result = run_script(*args)
                self.assertEqual(result.returncode, 2)
                self.assertEqual(result.stdout, "")

    def test_c4_read_only(self):
        # A run that writes a file (cache, report) under hass/ or storefront-mockup/ would change this.
        before = snapshot()
        result = run_script()
        after = snapshot()
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(result.stdout.splitlines()[-1], PASS)
        self.assertEqual(before, after)

    def test_c4_1_no_bytecode_without_dash_B(self):
        # A plain `python3 script` run (no -B, no PYTHONDONTWRITEBYTECODE) must not leave
        # hass/__pycache__ behind. Runs a tmp copy so a pre-existing cache cannot mask it.
        env = {k: v for k, v in os.environ.items() if k != "PYTHONDONTWRITEBYTECODE"}
        with tempfile.TemporaryDirectory() as tmp:
            tmp = Path(tmp)
            for rel in ("hass/__init__.py", "hass/itemstd.py", "hass/voice.py", "hass/style/item-standard.json", "scripts/hass/npp_maker_place_town.py"):
                (tmp / rel).parent.mkdir(parents=True, exist_ok=True)
                shutil.copy(ROOT / rel, tmp / rel)
            result = subprocess.run([sys.executable, str(tmp / "scripts/hass/npp_maker_place_town.py")],
                                    cwd=tmp, env=env, capture_output=True, text=True, timeout=30)
            self.assertEqual(result.returncode, 0, result.stderr)
            self.assertEqual(result.stdout.splitlines()[-1], PASS)
            self.assertEqual(sorted(str(p.relative_to(tmp)) for p in tmp.rglob("__pycache__")), [])

    def test_c5_output_shape(self):
        # Only case lines, the named FAIL forms and the trailer may appear; stderr stays empty.
        result = run_script()
        self.assertEqual(result.returncode, 0)
        self.assertEqual(result.stderr, "")
        lines = result.stdout.splitlines()
        self.assertEqual(lines[-1], PASS)
        for line in lines[:-1]:
            self.assertRegex(line, r"^case \d+ place='(town|region|blank|other)'$")
        with mock.patch.object(itemstd, "_REGION_NAMES", frozenset()):
            code, bad = run_main()
        self.assertEqual(code, 1)
        for line in bad[:-1]:
            self.assertRegex(line, r"^(case \d+ place='[a-z]+'|FAIL (region-read-as-town|place-changed) \d+)$")
        self.assertEqual(bad[-1], FAIL)

    def test_c6_fixture(self):
        # If the ' county' suffix stops matching, 'Ventura County, CA' reads as a town.
        with mock.patch.object(itemstd, "_REGION_SUFFIXES", ()):
            code, lines = run_main()
        self.assertEqual(code, 1)
        self.assertEqual(findings(lines), ["FAIL region-read-as-town 6", "FAIL place-changed 6"])
        self.assertEqual(lines[-1], FAIL)

    def test_c7_live_pins(self):
        # Pins the measured classify_place answers; a changed rule or region list shows here.
        result = run_script()
        self.assertEqual(result.returncode, 0, result.stderr)
        lines = result.stdout.splitlines()
        self.assertEqual(lines[:-1], C7_LINES)
        self.assertEqual(lines[-1], PASS)
        self.assertEqual(tool.EXPECTED, tuple(C7_LINES))
        self.assertEqual(tool.MUST_NOT_TOWN, (2, 3, 4, 5, 6, 9, 12, 13))
        # The pin comes from the repo function itself, not a constant in the tool.
        self.assertEqual([itemstd.classify_place(p) for p in tool.CASES],
                         [x.split("=", 1)[1].strip("'") for x in C7_LINES])


if __name__ == "__main__":
    unittest.main()
