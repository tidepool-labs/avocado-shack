"""Fixture-only contract checks at the pilot caption CLI boundary."""

from pathlib import Path
import subprocess
import sys
import tempfile
import unittest


SCRIPT = Path(__file__).resolve().parents[2] / "scripts/hass/pilot_caption_precheck.py"
PASS = "PASS pilot_caption_precheck"
FAIL = "FAIL pilot_caption_precheck"


class PilotCaptionPrecheckTests(unittest.TestCase):
    def setUp(self):
        self.root = Path(self.enterContext(tempfile.TemporaryDirectory()))
        self.source = self.root / "caption-file.txt"

    def invoke(self, *args):
        return subprocess.run(
            [sys.executable, "-B", str(SCRIPT), *args], cwd=self.root,
            capture_output=True, text=True, timeout=10,
        )

    def check(self, *args, source=None):
        return self.invoke("--captions", str(self.source if source is None else source), *args)

    def write_caption_file(self, text):
        self.source.write_text(text, encoding="utf-8")

    def assert_result(self, result, code, last):
        self.assertEqual(result.returncode, code)
        self.assertEqual(result.stdout.splitlines()[-1:], [last])
        self.assertEqual(result.stderr, "")
        return result.stdout.splitlines()[:-1]

    def test_c1_full_pass(self):
        # Bare typed prices are photo-specific. Blank lines must not count toward the limit or index.
        self.write_caption_file(" \n" + "\ufffc$728.46 each\n\n" * 20)
        lines = self.assert_result(self.check("--expect-card"), 0, PASS)
        self.assertEqual(lines, [
            f"caption {index} {fact}"
            for index in range(1, 21)
            for fact in ("price yes", "unit each", "cost no", "quantity no", "path card")
        ])

    def test_c2_1_unreadable(self):
        # Do not follow a readable symlink, silently replace bad UTF-8, or pass an empty batch.
        self.source.write_bytes(b"sell $712.83 each\n")
        alias = self.root / "alias"
        alias.symlink_to(self.source)
        invalid = self.root / "invalid"
        invalid.write_bytes(b"sell $712.83 each\n\xff")
        blank = self.root / "blank"
        blank.write_text("\n \t\n", encoding="utf-8")
        empty = self.root / "empty"
        empty.touch()
        for label, path in (
            ("missing", self.root / "absent"), ("symlink", alias),
            ("invalid utf8", invalid), ("whitespace", blank), ("empty", empty),
            ("directory", self.root),
        ):
            with self.subTest(label=label):
                lines = self.assert_result(self.check(source=path), 1, FAIL)
                self.assertEqual(lines, ["FAIL unreadable"])

    def test_c2_2_too_many(self):
        # A truncated batch could pass while silently omitting a pilot caption.
        self.write_caption_file("fixture sample\n\n" * 21)
        lines = self.assert_result(self.check("--expect-card"), 1, FAIL)
        self.assertEqual(lines, ["FAIL too-many"])

    def test_c2_3_would_ask(self):
        # Report every ask, including a parsed price with unresolved finance and a price conflict.
        self.write_caption_file(
            "fixture sample\n\nsell $712.83 each\n"
            "sell $728.46 each; cost unknown\n"
            "sell $728.46 each; sell $713.64 each\n"
        )
        lines = self.assert_result(self.check("--expect-card"), 1, FAIL)
        self.assertEqual([line for line in lines if line.startswith("FAIL ")], [
            "FAIL would-ask 1", "FAIL would-ask 3", "FAIL would-ask 4",
        ])
        self.assertIn("caption 2 path card", lines)
        self.assertIn("caption 3 price yes", lines)
        self.assertIn("caption 3 path ask", lines)
        self.assertIn("caption 4 price no", lines)
        self.assertIn("caption 4 path ask", lines)

    def test_c3_usage_exit_2(self):
        # Missing/invalid CLI syntax is argparse usage, not an unreadable-file finding.
        self.write_caption_file("sell $712.83 each\n")
        for args in ((), ("--captions",), ("--captions", str(self.source), "--unknown")):
            with self.subTest(args=args):
                result = self.invoke(*args)
                self.assertEqual(result.returncode, 2)
                self.assertEqual(result.stdout, "")  # No last stdout line on usage errors.
                self.assertTrue(result.stderr.startswith("usage: "))
                self.assertEqual(result.stderr.splitlines()[-1],
                                 "pilot_caption_precheck: error: invalid arguments; see --help")

    def test_c4_read_only(self):
        # Normalization must stay in memory and reports must not create sidecars.
        self.source.write_bytes(" \r\nfixture café; sell $712.83 each\r\n".encode())
        before = self.source.read_bytes(), self.source.stat().st_mtime_ns
        entries = set(self.root.rglob("*"))
        self.assert_result(self.check("--expect-card"), 0, PASS)
        self.assertEqual((self.source.read_bytes(), self.source.stat().st_mtime_ns), before)
        self.assertEqual(set(self.root.rglob("*")), entries)

    def test_c5_no_private_values(self):
        # Watch success, refusal and usage streams for raw captions, answers, paths and debug metadata.
        markers = (
            "fixture-message-ember", "fixture-chat-willow", "fixture-sender-petal",
            "fixture-id-aurora", "cafe" * 16,
        )
        caption = "; ".join((*markers, "have 71365 items", "paid $713.64", "sell $728.46 each"))
        self.write_caption_file(caption)
        valid = self.check("--expect-card")
        self.assertEqual(self.assert_result(valid, 0, PASS), [
            "caption 1 price yes", "caption 1 unit each", "caption 1 cost yes",
            "caption 1 quantity yes", "caption 1 path card",
        ])
        missing_path = self.root / "missing-canary"
        missing = self.check(source=missing_path)
        self.assert_result(missing, 1, FAIL)
        usage = self.invoke("--captions", str(self.source), str(missing_path), markers[0])
        self.assertEqual((usage.returncode, usage.stdout), (2, ""))
        oversized_count = "73462" * 1000
        self.write_caption_file(f"{markers[0]}; {oversized_count} lb in stock\n")
        refused = self.check("--expect-card")
        self.assertIn("FAIL would-ask 1", self.assert_result(refused, 1, FAIL))
        for outcome in (valid, missing, usage, refused):
            streams = outcome.stdout + outcome.stderr
            for canary in (*markers, caption, "71365", "713.64", "728.46", "73462", str(self.root)):
                self.assertFalse(canary in streams, "private canary leaked")

    def test_c6_ask_is_informational(self):
        # A missing price isn't a finding unless the operator asks for card-only checks.
        self.write_caption_file("fixture sample\n")
        lines = self.assert_result(self.check(), 0, PASS)
        self.assertEqual(lines, ["caption 1 price no", "caption 1 unit none", "caption 1 cost no",
                                 "caption 1 quantity no", "caption 1 path ask"])

    def test_c7_mixed_caption(self):
        # Don't confuse selling price with private cost, or drop an explicitly zero stock count.
        self.write_caption_file("paid $713.64; have 0 lb; sell for $728.46 per lb\n")
        lines = self.assert_result(self.check("--expect-card"), 0, PASS)
        self.assertEqual(lines, ["caption 1 price yes", "caption 1 unit per-lb", "caption 1 cost yes",
                                 "caption 1 quantity yes", "caption 1 path card"])
