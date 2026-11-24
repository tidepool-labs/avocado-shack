"""`--min` of the corpus coverage report accepts ASCII digits only (synthetic inputs)."""

import json
from pathlib import Path
import subprocess
import sys
from tempfile import TemporaryDirectory
import unittest

from hass import nl_eval

SCRIPT = Path(__file__).resolve().parents[2] / "scripts/hass/nl_intent_coverage.py"
USAGE = "expected --min with a positive integer and optional --corpus FILE"


class AsciiMinOptionTests(unittest.TestCase):
    def setUp(self):
        self.root = Path(self.enterContext(TemporaryDirectory())).resolve()
        self.corpus = self.root / "synthetic-input.jsonl"
        by_intent = dict.fromkeys(nl_eval.INTENTS, 2)
        by_intent["availability"] += nl_eval.MIN_CASES - sum(by_intent.values())
        rows = [
            dict(id=f"case-{i}", text="Synthetic case.", intent=name, expect={"question": True},
                 ask=True, refuse=False, pending=[])
            for i, name in enumerate(n for n, c in sorted(by_intent.items()) for _ in range(c))
        ]
        self.corpus.write_text("".join(json.dumps(r) + "\n" for r in rows), encoding="utf-8")

    def cli(self, value):
        return subprocess.run(
            [sys.executable, "-B", str(SCRIPT), "--min", value, "--corpus", str(self.corpus)],
            cwd=self.root, capture_output=True, text=True, timeout=10,
        )

    def assert_refused(self, value):
        result = self.cli(value)
        self.assertEqual(result.returncode, 2, value)
        self.assertEqual(result.stdout, "")
        self.assertTrue(result.stderr.strip().endswith(USAGE), value)
        if value:  # the refusal text must not echo the rejected value
            self.assertNotIn(value, result.stderr)

    def test_non_ascii_digits_refused(self):
        # Contract: Unicode decimal digits never set the threshold; int() would read them as 3/0.
        for value in ("\u0663", "\uff13", "\u0660"):
            with self.subTest(value=value):
                self.assert_refused(value)

    def test_ascii_value_unchanged(self):
        # Healthy control: ASCII 3 against the 2-per-intent corpus keeps its recorded verdict.
        result = self.cli("3")
        self.assertEqual(result.returncode, 1)
        self.assertEqual(result.stderr, "")
        lines = result.stdout.splitlines()
        self.assertEqual(lines[-1], "FAIL nl_intent_coverage")
        self.assertIn("FAIL thin-intent notes 2", lines)
        passing = self.cli("2")
        self.assertEqual(passing.returncode, 0)
        self.assertEqual(passing.stdout.splitlines()[-1], "PASS nl_intent_coverage")

    def test_existing_refusals_unchanged(self):
        # Contract: zero, negative, superscript and empty stay refused with the fixed message.
        for value in ("0", "-1", "\u00b2", ""):
            with self.subTest(value=value):
                self.assert_refused(value)
