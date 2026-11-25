"""Offline acceptance tests for the NPP fact-reply key check (hass.newitem.parse_facts)."""

from contextlib import redirect_stderr, redirect_stdout
import importlib.util
import io
from pathlib import Path
import re
import subprocess
import sys
import unittest
from unittest import mock

ROOT = Path(__file__).resolve().parents[2]
SCRIPT = ROOT / "scripts/hass/npp_fact_reply_keys.py"
SPEC = importlib.util.spec_from_file_location("npp_fact_reply_keys", SCRIPT)
assert SPEC is not None and SPEC.loader is not None
CHECK = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(CHECK)

from hass import newitem  # the script imported the same module object

PASS = "PASS npp_fact_reply_keys"
FAIL = "FAIL npp_fact_reply_keys"
C7_LINES = [
    "case 0 facts={'name': 'Wildflower Honey', 'maker': 'Cedar Row Apiary'}",
    "case 1 facts={}",
    "case 2 facts={}",
    "case 3 facts={}",
    "case 4 facts={'name': 'Honey'}",
    "case 5 facts={'story': 'They keep bees.', 'url': 'https://cedarrow.example'}",
    "case 6 facts={}",
    "case 7 facts={}",
    "case 8 facts={}",
    "case 9 facts={'name': 'Organic Honey'}",
    "case 10 facts={}",
]
SHAPES = (
    re.compile(r"case \d+ facts=\{.*\}"),
    re.compile(r"FAIL (non-fact-read|facts-changed) \d+"),
    re.compile(r"FAIL check-error"),
    re.compile(r"(PASS|FAIL) npp_fact_reply_keys"),
)


def tree_snapshot(*names):
    snapshot = {}
    for name in names:
        for path in sorted((ROOT / name).rglob("*")):
            info = path.stat()
            snapshot[str(path.relative_to(ROOT))] = (info.st_size, info.st_mtime_ns)
    return snapshot


def interleave(lines, findings):
    """Case lines with each case's findings right after it (findings: {case: [text, ...]})."""
    result = []
    for index, line in enumerate(lines):
        result.append(line)
        result.extend(findings.get(index, ()))
    return result


class NppFactReplyKeysTests(unittest.TestCase):
    def cli(self, *args):
        result = subprocess.run([sys.executable, "-B", str(SCRIPT), *args], cwd=ROOT,
                                capture_output=True, text=True, timeout=30)
        return result.returncode, result.stdout, result.stderr

    def main(self):
        out, err = io.StringIO(), io.StringIO()
        with redirect_stdout(out), redirect_stderr(err):
            code = CHECK.main([])
        self.assertEqual(err.getvalue(), "")
        return code, out.getvalue().splitlines()

    def assert_findings(self, patcher, findings):
        """Run main() under patcher; the FAIL lines must be exactly `findings`, then the trailer, exit 1."""
        with patcher:
            code, lines = self.main()
        self.assertEqual(code, 1)
        self.assertEqual(lines[-1], FAIL)
        self.assertEqual([x for x in lines if x.startswith("FAIL ")], [*findings, FAIL])
        return lines

    def test_c1_full_pass(self):
        # Believable bug: parse_facts starts keeping extra keys or padded text, or the
        # script exits 0 without the exact PASS trailer.
        code, stdout, stderr = self.cli()
        self.assertEqual((code, stderr), (0, ""))
        self.assertEqual(stdout.splitlines()[-1], PASS)

    def test_c2_findings_trailer(self):
        # A finding must exit 1 with the exact FAIL trailer, never PASS.
        lines = self.assert_findings(mock.patch.object(newitem, "FACT_KEYS", ("name",)),
                                     ["FAIL facts-changed 0", "FAIL facts-changed 5"])
        self.assertNotIn(PASS, lines)
        # Each finding sits right after its own case line, in case order.
        self.assertEqual(lines[lines.index("FAIL facts-changed 0") - 1][:7], "case 0 ")
        self.assertEqual(lines[lines.index("FAIL facts-changed 5") - 1][:7], "case 5 ")

    def test_c2_1_non_fact_read(self):
        # Believable bug: parse_facts passes a slipped-in extra key through to the draft facts.
        patcher = mock.patch.object(newitem, "FACT_KEYS", newitem.FACT_KEYS + ("secret",))
        lines = self.assert_findings(patcher, ["FAIL non-fact-read 4", "FAIL facts-changed 4"])
        self.assertEqual(lines[4], "case 4 facts={'name': 'Honey', 'secret': 'x'}")
        self.assertEqual(lines[5:7], ["FAIL non-fact-read 4", "FAIL facts-changed 4"])
        # A value that is not a plain stripped non-empty string is a non-fact-read too.
        real = newitem.parse_facts
        for bad in (" Honey ", "", 7, ["Honey"], True):
            with self.subTest(bad=bad):
                def parse(raw, bad=bad):
                    got = real(raw)
                    return {**got, "name": bad} if "Wildflower" in (raw or "") else got
                lines = self.assert_findings(
                    mock.patch.object(newitem, "parse_facts", parse),
                    ["FAIL non-fact-read 0", "FAIL facts-changed 0"])
                self.assertEqual(lines[1:3], ["FAIL non-fact-read 0", "FAIL facts-changed 0"])

    def test_c2_2_facts_changed(self):
        # Believable bug: a drift in what parse_facts keeps (here, fewer keys) goes unnoticed.
        self.assert_findings(mock.patch.object(newitem, "FACT_KEYS", ("name",)),
                             ["FAIL facts-changed 0", "FAIL facts-changed 5"])
        self.assertEqual(CHECK.EXPECTED, C7_LINES)

    def test_c2_3_check_error(self):
        # A repo call that raises is a named FAIL (no exception text), once, and stops the run.
        real, calls = newitem.parse_facts, []

        def parse(raw):
            calls.append(raw)
            if len(calls) == 3:
                raise RuntimeError("private-detail")
            return real(raw)

        with mock.patch.object(newitem, "parse_facts", parse):
            code, lines = self.main()
        self.assertEqual(code, 1)
        self.assertEqual(lines, [*C7_LINES[:2], "FAIL check-error", FAIL])
        self.assertEqual(len(calls), 3)
        with mock.patch.object(newitem, "parse_facts", side_effect=RuntimeError("private-detail")):
            code, lines = self.main()
        self.assertEqual((code, lines), (1, ["FAIL check-error", FAIL]))

    def test_c3_usage_exit_2(self):
        for args in (["extra"], ["--nope"], ["--help=x"]):
            with self.subTest(args=args):
                code, stdout, stderr = self.cli(*args)
                self.assertEqual((code, stdout), (2, ""))
                self.assertIn("usage:", stderr)

    def test_c4_read_only(self):
        # Believable bug: the check writes a cache, report or bytecode into the repo.
        before = tree_snapshot("hass", "storefront-mockup")
        self.assertTrue(before)
        code, stdout, stderr = self.cli()
        self.assertEqual((code, stderr), (0, ""))
        self.assertEqual(stdout.splitlines()[-1], PASS)
        self.assertEqual(tree_snapshot("hass", "storefront-mockup"), before)

    def test_c5_output_shape(self):
        code, stdout, stderr = self.cli()
        self.assertEqual((code, stderr), (0, ""))
        runs = [stdout.splitlines()]
        with mock.patch.object(newitem, "FACT_KEYS", newitem.FACT_KEYS + ("secret",)):
            runs.append(self.main()[1])
        with mock.patch.object(newitem, "parse_facts", side_effect=RuntimeError("x")):
            runs.append(self.main()[1])
        for lines in runs:
            self.assertTrue(lines)
            for line in lines:
                with self.subTest(line=line):
                    self.assertTrue(any(shape.fullmatch(line) for shape in SHAPES), line)

    def test_c6_fixture(self):
        with mock.patch.object(newitem, "FACT_KEYS", ("name",)):
            code, lines = self.main()
        self.assertEqual(code, 1)
        self.assertEqual([x for x in lines if x.startswith("FAIL ")],
                         ["FAIL facts-changed 0", "FAIL facts-changed 5", FAIL])
        self.assertEqual(lines[-1], FAIL)
        self.assertEqual(lines, interleave([
            "case 0 facts={'name': 'Wildflower Honey'}", *C7_LINES[1:5], "case 5 facts={}",
            *C7_LINES[6:]], {0: ["FAIL facts-changed 0"], 5: ["FAIL facts-changed 5"]}) + [FAIL])

    def test_c7_live_pins(self):
        # Pins what parse_facts answers today, including case 9 (a repeated key keeps the LAST value)
        # and the 100000-deep nesting that the decoder rejects with RecursionError.
        self.assertEqual(CHECK.KEYS, newitem.FACT_KEYS)
        real, seen = newitem.parse_facts, []

        def spy(raw):
            seen.append(raw)
            return real(raw)

        with mock.patch.object(newitem, "parse_facts", spy):
            code, lines = self.main()
        self.assertEqual((code, lines), (0, [*C7_LINES, PASS]))
        # The repo function itself ran on every raw reply, including None and the deep string.
        self.assertEqual(len(seen), 11)
        self.assertEqual(seen[7], "[" * 100000)
        self.assertIsNone(seen[8])
        self.assertEqual(seen[9], '{"name": "Honey", "name": "Organic Honey"}')
        code, stdout, stderr = self.cli()
        self.assertEqual((code, stdout.splitlines(), stderr), (0, [*C7_LINES, PASS], ""))


if __name__ == "__main__":
    unittest.main()
