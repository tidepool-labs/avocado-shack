"""Offline contract tests for the maker words drift guard."""

from contextlib import redirect_stderr, redirect_stdout
import importlib.util
import io
from pathlib import Path
import re
import subprocess
import sys
import unittest
from unittest.mock import call, patch


ROOT = Path(__file__).resolve().parents[2]
SCRIPT = ROOT / "scripts/hass/npp_maker_words_hidden.py"
PASS = "PASS npp_maker_words_hidden"
FAIL = "FAIL npp_maker_words_hidden"
NO_RELATIONS = re.compile(r"(?!x)x(?P<name>)(?P<place>)")
LIVE_LINES = [
    "case 0 maker='cedar-row' relations=[('Cedar Row Apiary', None)]",
    "case 1 maker=None relations=[('Old Mill Bakery', None)]",
    "case 2 maker=None relations=[]",
    "case 3 maker='harbor-lane-farm-west' relations=[('Harbor Lane Farm West', 'Ventura, CA')]",
    "case 4 maker='harbor' relations=[('Harbor Lane Farm', None)]",
    "case 5 maker=None relations=[('Juniper Ridge', 'Ojai, CA')]",
    "case 6 maker=None relations=[('Bluebird & Co', None)]",
    "case 7 maker=None relations=[]",
    "case 8 maker=None relations=[]",
]


def snapshot():
    entries = {}
    for tree in (ROOT / "hass", ROOT / "storefront-mockup"):
        for path in (tree, *tree.rglob("*")):
            stat = path.lstat()
            entries[path.relative_to(ROOT)] = (stat.st_size, stat.st_mtime_ns)
    return entries


class MakerWordsHiddenTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        spec = importlib.util.spec_from_file_location("npp_maker_words_hidden", SCRIPT)
        if spec is None or spec.loader is None:
            raise ImportError(f"Cannot load {SCRIPT.name}")
        cls.tool = importlib.util.module_from_spec(spec)
        with patch.object(sys, "path", sys.path.copy()):
            spec.loader.exec_module(cls.tool)

    def cli(self, *args):
        return subprocess.run(
            [sys.executable, "-B", str(SCRIPT), *args],
            cwd=ROOT.parent, capture_output=True, text=True, timeout=10,
        )

    def run_main(self, exit_code, trailer):
        stdout, stderr = io.StringIO(), io.StringIO()
        with redirect_stdout(stdout), redirect_stderr(stderr):
            result = self.tool.main([])
        lines = stdout.getvalue().splitlines()
        self.assertEqual(result, exit_code)
        self.assertEqual(stderr.getvalue(), "")
        self.assertTrue(lines)
        self.assertEqual(lines[-1], trailer)
        return lines

    def test_c1_full_pass(self):
        # A broken standalone import or forgotten sys.exit fails the CLI contract.
        result = self.cli()
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(result.stdout.splitlines()[-1], PASS)

    def test_c2_findings_trailer(self):
        # An early mismatch must survive subsequent clean cases, including the last.
        real_relations = self.tool.newitem.maker_relations

        def change_first(text):
            return [] if text == "new honey from Cedar Row Apiary" else real_relations(text)

        with patch.object(self.tool.newitem, "maker_relations", change_first):
            lines = self.run_main(1, FAIL)
        self.assertEqual(lines, ["case 0 maker='cedar-row' relations=[]",
                                 "FAIL maker-changed 0", *LIVE_LINES[1:], FAIL])

    def test_c2_1_hidden_maker_found(self):
        # Dropping the visibility filter exposes both a name and a key match.
        def ignore_hidden(message, makers):
            hits = [(len(m["name"]), k) for k, m in makers.items()
                    if self.tool.newitem._has(message, k)
                    or self.tool.newitem._has(message, m["name"])]
            return max(hits)[1] if hits else None

        with patch.object(self.tool.newitem, "find_maker", ignore_hidden):
            lines = self.run_main(1, FAIL)
        self.assertEqual(lines, [
            LIVE_LINES[0],
            "case 1 maker='old-mill' relations=[('Old Mill Bakery', None)]",
            "FAIL hidden-maker-found 1", "FAIL maker-changed 1",
            "case 2 maker='old-mill' relations=[]",
            "FAIL hidden-maker-found 2", "FAIL maker-changed 2",
            *LIVE_LINES[3:], FAIL,
        ])

    def test_c2_2_maker_changed(self):
        # Comparing only maker keys would miss drift in the relation field.
        with patch.object(self.tool.newitem, "NEW_MAKER_RE", NO_RELATIONS):
            lines = self.run_main(1, FAIL)
        self.assertEqual(lines[:3], ["case 0 maker='cedar-row' relations=[]",
                                     "FAIL maker-changed 0",
                                     "case 1 maker=None relations=[]"])

    def test_c2_3_check_error(self):
        # Neither reader's exception may leak diagnostics or allow later cases.
        for name in ("find_maker", "maker_relations"):
            with self.subTest(name=name):
                with patch.object(self.tool.newitem, name,
                                  side_effect=RuntimeError("synthetic exception")) as broken:
                    lines = self.run_main(1, FAIL)
                    broken.assert_called_once()
                self.assertEqual(lines, ["FAIL check-error", FAIL])

    def test_c3_usage_exit_2(self):
        # The CLI takes no arguments, including argparse's default help flags.
        for arg in ("extra", "--unknown", "--help", "-h", "--"):
            with self.subTest(arg=arg):
                result = self.cli(arg)
                self.assertEqual(result.returncode, 2)
                self.assertEqual(result.stdout, "")
                self.assertIn("usage:", result.stderr)
                self.assertTrue(result.stderr.splitlines()[-1].startswith(
                    "npp_maker_words_hidden.py: error: unrecognized arguments:"))

    def test_c4_read_only(self):
        # Creating even an empty cache or rewriting unchanged data alters metadata.
        before = snapshot()
        result = self.cli()
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(result.stdout.splitlines()[-1], PASS)
        self.assertEqual(snapshot(), before)

    def test_c5_output_shape(self):
        # An added log, banner or blank line violates the stdout/stderr interface.
        result = self.cli()
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(result.stderr, "")
        *rows, trailer = result.stdout.splitlines()
        self.assertEqual(trailer, PASS)
        self.assertEqual(len(rows), 9)
        for i, row in enumerate(rows):
            self.assertRegex(row, rf"^case {i} maker=(?:None|'[^']+') relations=\[.*\]$")

    def test_c6_fixture(self):
        # Disabling the real phrase grammar must affect only the six phrase rows.
        with patch.object(self.tool.newitem, "NEW_MAKER_RE", NO_RELATIONS):
            lines = self.run_main(1, FAIL)
        self.assertEqual([line for line in lines[:-1] if line.startswith("FAIL")], [
            "FAIL maker-changed 0", "FAIL maker-changed 1", "FAIL maker-changed 3",
            "FAIL maker-changed 4", "FAIL maker-changed 5", "FAIL maker-changed 6",
        ])

    def test_c7_live_pins(self):
        # These measured rows catch visible longest-name, phrase and place drift.
        # Wrap the actual readers so constant output cannot satisfy this check.
        newitem = self.tool.newitem
        with patch.object(newitem, "find_maker", wraps=newitem.find_maker) as find, \
             patch.object(newitem, "maker_relations", wraps=newitem.maker_relations) as relations:
            lines = self.run_main(0, PASS)
        self.assertEqual(lines, [*LIVE_LINES, PASS])
        self.assertEqual(find.call_args_list, [call(text, self.tool.MAKERS) for text in self.tool.CASES])
        self.assertEqual(relations.call_args_list, [call(text) for text in self.tool.CASES])


if __name__ == "__main__":
    unittest.main()
