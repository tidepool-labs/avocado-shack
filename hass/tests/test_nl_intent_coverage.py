"""Offline CLI contract for the corpus coverage report."""

from contextlib import redirect_stderr, redirect_stdout
import importlib.util
from io import StringIO
import json
from pathlib import Path
import subprocess
import sys
from tempfile import TemporaryDirectory
import unittest
from unittest.mock import patch

from hass import nl_eval

SCRIPT = Path(__file__).resolve().parents[2] / "scripts/hass/nl_intent_coverage.py"
PASS = "PASS nl_intent_coverage"
FAIL = "FAIL nl_intent_coverage"
CANARY = "Synthetic private case marker."


class IntentCoverageTests(unittest.TestCase):
    def setUp(self):
        self.root = Path(self.enterContext(TemporaryDirectory())).resolve()
        self.corpus = self.root / "synthetic-input.jsonl"

    def write_corpus(self, *, counts=None, first_tags=(), second_tags=()):
        by_intent = dict.fromkeys(nl_eval.INTENTS, 2)
        by_intent.update(counts or {})
        by_intent["availability"] += nl_eval.MIN_CASES - sum(by_intent.values())
        intents = [name for name, count in sorted(by_intent.items()) for _ in range(count)]
        rows = [
            dict(id=f"case-{i}", text=CANARY, intent=name, expect={"question": True},
                 ask=True, refuse=False, pending=[])
            for i, name in enumerate(intents)
        ]
        rows[0]["tags"] = list(first_tags)
        rows[1]["tags"] = list(second_tags)
        self.corpus.write_text("".join(json.dumps(row) + "\n" for row in rows), encoding="utf-8")
        return by_intent

    def cli(self, *args):
        return subprocess.run(
            [sys.executable, "-B", str(SCRIPT), *map(str, args)], cwd=self.root,
            capture_output=True, text=True, timeout=10,
        )

    def assert_report(self, result, code, trailer):
        self.assertEqual(result.returncode, code)
        self.assertEqual(result.stderr, "")
        lines = result.stdout.splitlines()
        self.assertEqual(lines[-1:], [trailer])
        return lines[:-1]

    def test_c1_full_pass(self):
        # Off-by-one thresholds, unfiltered tags or an uncapped report break this.
        tags = [f"sample-{i:02d}" for i in range(29)] + ["1" + "a" * 40, "zz-repeat"]
        counts = self.write_corpus(
            first_tags=tags + ["Bad Tag", "a" * 42, "almost-ok\n"],
            second_tags=["zz-repeat", "Bad Tag"],
        )
        lines = self.assert_report(self.cli("--min", 2, "--corpus", self.corpus), 0, PASS)
        self.assertEqual(lines, [
            f"cases {nl_eval.MIN_CASES}", f"intents {len(counts)}",
            *(f"intent {name} {counts[name]}" for name in sorted(counts)),
            "tag zz-repeat 2", *(f"tag {name} 1" for name in sorted(tags[:-1])[:29]),
            "note odd-tag 4",
        ])

    def test_c2_findings_trailer(self):
        # A finding cannot be followed by PASS or return success.
        self.write_corpus(counts={"notes": 1})
        lines = self.assert_report(self.cli("--min", 2, "--corpus", self.corpus), 1, FAIL)
        self.assertEqual([line for line in lines if line.startswith("FAIL ")],
                         ["FAIL thin-intent notes 1"])

    def test_c2_1_unsafe_input(self):
        # Following a symlink would let an otherwise passing corpus through.
        self.write_corpus()
        link = self.root / "linked.jsonl"
        link.symlink_to(self.corpus)
        dangling = self.root / "dangling.jsonl"
        missing = self.root / "missing.jsonl"
        dangling.symlink_to(missing)
        for path in (link, dangling, self.root, missing):
            with self.subTest(kind=path.name):
                self.assertEqual(self.assert_report(self.cli("--min", 1, "--corpus", path), 1, FAIL),
                                 ["FAIL unsafe-input"])

    def test_c2_2_corpus_invalid(self):
        # A readable file is not necessarily a valid scorer corpus.
        self.corpus.write_text("{invalid\n", encoding="utf-8")
        self.assertEqual(self.assert_report(self.cli("--min", 1, "--corpus", self.corpus), 1, FAIL),
                         ["FAIL corpus-invalid"])

    def test_c2_3_thin_intent(self):
        # Iterating only observed intents drops the zero, and frequency order misorders findings.
        self.write_corpus(counts={"notes": 1, "photo": 0, "undo": 1})
        lines = self.assert_report(self.cli("--min", 2, "--corpus", self.corpus), 1, FAIL)
        self.assertIn("intent photo 0", lines)
        self.assertEqual([line for line in lines if line.startswith("FAIL ")], [
            "FAIL thin-intent notes 1", "FAIL thin-intent photo 0", "FAIL thin-intent undo 1",
        ])

    def test_c3_usage_exit_2(self):
        # Argument errors must not be reported as coverage findings or accepted.
        for args in ((), ("--min",), ("--min", "0"), ("--min", "-1"), ("--min", "1.5"),
                     ("--min", "1", "--unknown"), ("--mi", "1")):
            with self.subTest(args=args):
                result = self.cli(*args)
                self.assertEqual(result.returncode, 2)
                self.assertEqual(result.stdout, "")  # No stdout trailer on usage errors.
                self.assertTrue(result.stderr.startswith("usage: nl_intent_coverage.py "))

    def test_c4_read_only(self):
        # A rewrite with identical contents still changes mtime; a sidecar changes the directory.
        self.write_corpus()
        before = (self.corpus.read_bytes(), self.corpus.stat().st_mtime_ns,
                  self.root.stat().st_mtime_ns, set(self.root.iterdir()))
        self.assert_report(self.cli("--min", 2, "--corpus", self.corpus), 0, PASS)
        self.assertEqual((self.corpus.read_bytes(), self.corpus.stat().st_mtime_ns,
                          self.root.stat().st_mtime_ns, set(self.root.iterdir())), before)

    def test_c5_no_private_values(self):
        # Rows, tag rejects, loader exceptions and argparse errors must not echo private values.
        self.write_corpus(first_tags=[CANARY, str(self.corpus)])
        result = self.cli("--min", 2, "--corpus", self.corpus)
        self.assert_report(result, 0, PASS)
        usage = self.cli("--min", self.corpus)
        self.assertEqual((usage.returncode, usage.stdout), (2, ""))

        spec = importlib.util.spec_from_file_location("nl_intent_coverage", SCRIPT)
        assert spec is not None and spec.loader is not None
        script = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(script)
        out, err = StringIO(), StringIO()
        with patch.object(nl_eval, "load_corpus", side_effect=OSError(f"{CANARY} {self.corpus}")), \
                redirect_stdout(out), redirect_stderr(err):
            code = script.main(["--min", "2", "--corpus", str(self.corpus)])
        self.assertEqual((code, out.getvalue().splitlines(), err.getvalue()),
                         (1, ["FAIL corpus-invalid", FAIL], ""))
        for value in (CANARY, str(self.corpus), str(SCRIPT)):
            self.assertNotIn(value, result.stdout + result.stderr + usage.stdout + usage.stderr
                             + out.getvalue() + err.getvalue())

    def test_c6_live_min2(self):
        # The default must load the checked-in corpus even from outside the checkout.
        lines = self.assert_report(self.cli("--min", 2), 0, PASS)
        self.assertEqual(lines[:2], ["cases 357", "intents 22"])

    def test_c7_live_min5(self):
        # Pin the actual marginal intents, not just the number of findings.
        lines = self.assert_report(self.cli("--min", 5), 1, FAIL)
        self.assertEqual([line for line in lines if line.startswith("FAIL ")], [
            "FAIL thin-intent notes 2", "FAIL thin-intent photo 4", "FAIL thin-intent undo 4",
        ])
