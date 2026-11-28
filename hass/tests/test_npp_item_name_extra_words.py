"""Offline contract tests for the S3 item-name diagnostic."""

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
SCRIPT = ROOT / "scripts/hass/npp_item_name_extra_words.py"
PASS = "PASS npp_item_name_extra_words"
FAIL = "FAIL npp_item_name_extra_words"
LIVE_ITEMS = (
    "Honey", "Honey.", "Honey!", "A Jar Of Honey", "Honey From Miners",
    "Wildflower Honey", "Apple Butter",
)


def tree_snapshot():
    snapshot = {}
    for tree in (ROOT / "hass", ROOT / "storefront-mockup"):
        for path in (tree, *tree.rglob("*")):
            stat = path.lstat()
            snapshot[path.relative_to(ROOT)] = (stat.st_size, stat.st_mtime_ns)
    return snapshot


class ItemNameExtraWordsTests(unittest.TestCase):
    def setUp(self):
        spec = importlib.util.spec_from_file_location(SCRIPT.stem, SCRIPT)
        assert spec is not None and spec.loader is not None
        self.tool = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(self.tool)

    def run_cli(self, *args):
        with TemporaryDirectory(dir=ROOT) as directory:
            return subprocess.run(
                [sys.executable, "-B", str(SCRIPT), *args], cwd=directory,
                capture_output=True, text=True, timeout=10,
            )

    def run_main(self):
        out, err = io.StringIO(), io.StringIO()
        with redirect_stdout(out), redirect_stderr(err):
            code = self.tool.main([])
        self.assertEqual(err.getvalue(), "")
        return code, out.getvalue().splitlines()

    def assert_run(self, code, trailer, findings):
        actual_code, lines = self.run_main()
        self.assertEqual(actual_code, code)
        self.assertEqual(lines[-1], trailer)
        self.assertEqual([line for line in lines[:-1] if line.startswith("FAIL ")], findings)
        return lines

    def replay_texts(self, *texts):
        captures = iter(texts)
        owner_item = self.tool.job.owner_item
        return patch.object(self.tool.job, "owner_item", side_effect=lambda _: owner_item(next(captures)))

    def test_c1_full_pass(self):
        # A fixed baseline result or an unconditional failure cannot pass clean inputs.
        with self.replay_texts(*(["It's alfalfa fromage"] * 7)) as owner:
            lines = self.assert_run(0, PASS, [])
        self.assertEqual(lines, [*(f"case {i} item=Alfalfa Fromage" for i in range(7)), PASS])
        self.assertEqual([call.args[0] for call in owner.call_args_list], list(self.tool.TEXTS))

    def test_c2_findings_trailer(self):
        # A failed row must set the exit status and report every finding, not just the first.
        with self.replay_texts("It's a pear from a grove.", *(["It's pear"] * 6)):
            self.assert_run(1, FAIL, [
                "FAIL trailing-punctuation 0", "FAIL article-kept 0", "FAIL from-kept 0",
            ])

    def test_c2_1_trailing_punctuation(self):
        # Missing '?' or flagging an interior mark rather than a suffix breaks this.
        with self.replay_texts("It's pear?", "It's pear.", "It's pear!", "It's St. Pear",
                               *(["It's pear"] * 3)):
            self.assert_run(1, FAIL, [f"FAIL trailing-punctuation {i}" for i in range(3)])

    def test_c2_2_article_kept(self):
        # Lowercase-only matching, missing articles, or prefixes instead of words break this.
        with self.replay_texts("It's A Pear", "It's aN Apple", "It's tHe Pear", "It's Anise",
                               "It's Pear The Tart", "It's Apple", "It's Theobroma"):
            self.assert_run(1, FAIL, [f"FAIL article-kept {i}" for i in range(3)])

    def test_c2_3_from_kept(self):
        # Mixed case must match a whole word, not a prefix or only a particular maker.
        with self.replay_texts("It's Pear fRoM A Grove", "It's Fromage", *(["It's pear"] * 5)):
            self.assert_run(1, FAIL, ["FAIL from-kept 0"])

    def test_c2_4_no_item(self):
        # A parser miss must be reported, not treated as a clean or skipped case.
        with self.replay_texts("Unrecognized wording", *(["It's pear"] * 6)):
            lines = self.assert_run(1, FAIL, ["FAIL no-item 0"])
        self.assertIn("case 0 item=None", lines)
        self.assertIn("case 6 item=Pear", lines)

    def test_c2_5_check_error(self):
        # A bypassed repo call, leaked exception text, or uncaught error breaks this.
        for target, name in (
            (self.tool.hass.npp, "assets"), (self.tool.missing, "MissingInfo"),
            (self.tool.missing.MissingInfo, "decide"), (self.tool.job, "owner_item"),
        ):
            with self.subTest(call=name), patch.object(target, name, side_effect=RuntimeError("fixture")):
                self.assertEqual(self.assert_run(1, FAIL, ["FAIL check-error"]), ["FAIL check-error", FAIL])

    def test_c3_usage_exit_2(self):
        # No argument, including default argparse help or a bare '--', may be accepted.
        for arg in ("honey", "--unknown", "--help", "--"):
            with self.subTest(arg=arg):
                result = self.run_cli(arg)
                self.assertEqual(result.returncode, 2)
                self.assertEqual(result.stdout, "")
                self.assertTrue(result.stderr.startswith("usage: "))
                reason = "no arguments accepted" if arg == "--" else f"unrecognized arguments: {arg}"
                self.assertEqual(result.stderr.splitlines()[-1], f"{SCRIPT.name}: error: {reason}")

    def test_c4_read_only(self):
        # An incidental cache or asset rewrite would change the tracked tree metadata.
        before = tree_snapshot()
        result = self.run_cli()
        self.assertEqual(result.returncode, 1)
        self.assertEqual(result.stdout.splitlines()[-1], FAIL)
        self.assertEqual(tree_snapshot(), before)

    def test_c5_output_shape(self):
        # Debug output, blank lines, or exception prose would violate the line protocol.
        result = self.run_cli()
        self.assertEqual(result.returncode, 1)
        self.assertEqual(result.stderr, "")
        lines = result.stdout.splitlines()
        self.assertEqual(lines[-1], FAIL)
        cases = []
        for line in lines[:-1]:
            self.assertRegex(
                line, r"\A(?:case [0-6] item=.+|FAIL check-error|"
                r"FAIL (?:trailing-punctuation|article-kept|from-kept|no-item) [0-6])\Z",
            )
            if line.startswith("case "):
                cases.append(line.split(" item=", 1)[0])
        self.assertEqual(cases, [f"case {i}" for i in range(7)])

    def test_c6_fixture(self):
        # Pin the findings left when only the real capture's punctuation is removed.
        owner_item = self.tool.job.owner_item

        def strip_suffix(text):
            item = owner_item(text)
            return None if item is None else item.rstrip(".!?")

        with patch.object(self.tool.job, "owner_item", side_effect=strip_suffix):
            lines = self.assert_run(1, FAIL, ["FAIL article-kept 3", "FAIL from-kept 4"])
        self.assertIn("case 1 item=Honey", lines)
        self.assertIn("case 2 item=Honey", lines)

    def test_c7_live_pins(self):
        # A changed S3 projection or reordered finding must be visible in the baseline.
        result = self.run_cli()
        self.assertEqual(result.returncode, 1)
        self.assertEqual(result.stderr, "")
        self.assertEqual(result.stdout.splitlines(), [
            f"case 0 item={LIVE_ITEMS[0]}",
            f"case 1 item={LIVE_ITEMS[1]}", "FAIL trailing-punctuation 1",
            f"case 2 item={LIVE_ITEMS[2]}", "FAIL trailing-punctuation 2",
            f"case 3 item={LIVE_ITEMS[3]}", "FAIL article-kept 3",
            f"case 4 item={LIVE_ITEMS[4]}", "FAIL from-kept 4",
            f"case 5 item={LIVE_ITEMS[5]}",
            f"case 6 item={LIVE_ITEMS[6]}",
            FAIL,
        ])
