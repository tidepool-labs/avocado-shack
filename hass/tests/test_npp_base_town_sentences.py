"""Offline behavioral contract for the opt-in S4 base-town diagnostic."""

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
SCRIPT = ROOT / "scripts/hass/npp_base_town_sentences.py"
PASS = "PASS npp_base_town_sentences"
FAIL = "FAIL npp_base_town_sentences"
WRONG = "different-base-town"
NON_BASE = (" in October", " in California", " in Sacramento", " in San Luis Obispo")


def load_script():
    spec = importlib.util.spec_from_file_location(SCRIPT.stem, SCRIPT)
    if spec is None or spec.loader is None:
        raise ImportError(f"Cannot load {SCRIPT.name}")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def snapshot():
    entries = {}
    for tree in (ROOT / "hass", ROOT / "storefront-mockup"):
        for path in (tree, *tree.rglob("*")):
            stat = path.lstat()
            entries[path.relative_to(ROOT)] = (stat.st_size, stat.st_mtime_ns)
    return entries


class NppBaseTownSentencesTests(unittest.TestCase):
    def setUp(self):
        self.cwd = self.enterContext(TemporaryDirectory())
        self.script = load_script()

    def cli(self, *args):
        return subprocess.run(
            [sys.executable, "-B", str(SCRIPT), *args], cwd=self.cwd,
            capture_output=True, text=True, timeout=10,
        )

    def run_main(self):
        stdout, stderr = io.StringIO(), io.StringIO()
        with redirect_stdout(stdout), redirect_stderr(stderr):
            status = self.script.main([])
        self.assertEqual(stderr.getvalue(), "")
        return status, stdout.getvalue().splitlines()

    def run_with_split(self, *, remove=NON_BASE, accept_based_control=False):
        maker_site = self.script.research.maker_site
        split = maker_site._split

        def fixture_split(block):
            sentences = []
            for sentence in split(block):
                for phrase in remove:
                    sentence = sentence.replace(phrase, "")
                if accept_based_control:
                    sentence = sentence.replace("is based in Paso Robles", "is based in Arroyo Grande")
                sentences.append(sentence)
            return sentences

        with patch.object(maker_site, "_split", side_effect=fixture_split):
            return self.run_main()

    def test_c1_full_pass(self):
        # A successful run must not retain a failing status or finding.
        status, lines = self.run_with_split()
        self.assertEqual((status, lines[-1]), (0, PASS))
        self.assertFalse(any(line.startswith("FAIL ") for line in lines))

    def test_c2_findings_trailer(self):
        # An accepted wrong-town control must not overwrite an earlier refusal.
        status, lines = self.run_with_split(remove=NON_BASE[1:], accept_based_control=True)
        self.assertEqual((status, lines[-1]), (1, FAIL))
        self.assertEqual([line for line in lines[:-1] if line.startswith("FAIL ")],
                         ["FAIL town-refused 0", "FAIL other-town-accepted 0"])

    def test_c2_1_town_refused(self):
        # One refused own page must emit one finding at the correct index.
        status, lines = self.run_with_split(remove=NON_BASE[:2] + NON_BASE[3:])
        self.assertEqual((status, lines[-1]), (1, FAIL))
        self.assertEqual([line for line in lines[:-1] if line.startswith("FAIL ")],
                         ["FAIL town-refused 2"])
        self.assertIn(f"own 2 reason={WRONG}", lines)

    def test_c2_2_other_town_accepted(self):
        # Accepted OTHER is a finding even though all OWN cases are official.
        status, lines = self.run_with_split(accept_based_control=True)
        self.assertEqual((status, lines[-1]), (1, FAIL))
        self.assertEqual([line for line in lines[:-1] if line.startswith("FAIL ")],
                         ["FAIL other-town-accepted 0"])
        self.assertIn("other 0 reason=official", lines)
        self.assertIn(f"other 1 reason={WRONG}", lines)

    def test_c2_3_check_error(self):
        # One thrown check must be reported without its message or skipping the rest.
        research = self.script.research
        own_site = research._own_site

        def check(page, name, town, markers):
            if page.blocks[0] == "Miners Orchards picks apples in October.":
                raise ValueError("synthetic exception text")
            return own_site(page, name, town, markers)

        with patch.object(research, "_own_site", side_effect=check) as called:
            status, lines = self.run_with_split()
        self.assertEqual((status, lines[-1]), (1, FAIL))
        self.assertEqual(lines[0], "FAIL check-error")
        self.assertEqual([line for line in lines[:-1] if line.startswith("FAIL ")],
                         ["FAIL check-error"])
        self.assertEqual(called.call_count, 8)
        self.assertNotIn("synthetic exception text", "\n".join(lines))

    def test_c3_usage_exit_2(self):
        # A positional or flag must fail in argparse, before any fixture output.
        for arg in ("unexpected", "--unknown", "--help"):
            with self.subTest(arg=arg):
                result = self.cli(arg)
                self.assertEqual((result.returncode, result.stdout), (2, ""))
                self.assertEqual(result.stderr.splitlines()[-1],
                                 f"{SCRIPT.name}: error: unrecognized arguments: {arg}")

    def test_c4_read_only(self):
        # A dump or cache under either repo tree would change the snapshot.
        before = snapshot()
        result = self.cli()
        self.assertEqual((result.returncode, result.stdout.splitlines()[-1]), (1, FAIL))
        self.assertEqual(snapshot(), before)

    def test_c5_output_shape(self):
        # Debug text, a traceback or an extra blank line is not part of the CLI.
        result = self.cli()
        lines = result.stdout.splitlines()
        self.assertEqual((result.returncode, lines[-1]), (1, FAIL))
        self.assertEqual(result.stderr, "")
        for line in lines[:-1]:
            self.assertRegex(line, r"\A(?:(?:own|other) [0-9]+ reason=[a-z-]+|"
                                   r"FAIL (?:(?:town-refused|other-town-accepted) [0-9]+|check-error))\Z")

    def test_c6_fixture(self):
        # If the runner bypasses the repo splitter, removing the phrases has no effect.
        status, lines = self.run_with_split()
        self.assertEqual((status, lines[-1]), (0, PASS))
        self.assertEqual(lines, [f"own {i} reason=official" for i in range(6)] +
                         [f"other 0 reason={WRONG}", f"other 1 reason={WRONG}", PASS])

    def test_c7_live_pins(self):
        # Pin the unmodified repo's four false refusals, not the desired S4 behavior.
        result = self.cli()
        lines = result.stdout.splitlines()
        self.assertEqual((result.returncode, lines[-1]), (1, FAIL))
        expected = []
        for i in range(4):
            expected.extend((f"own {i} reason={WRONG}", f"FAIL town-refused {i}"))
        expected.extend(("own 4 reason=official", "own 5 reason=official",
                         f"other 0 reason={WRONG}", f"other 1 reason={WRONG}", FAIL))
        self.assertEqual(lines, expected)


if __name__ == "__main__":
    unittest.main()
