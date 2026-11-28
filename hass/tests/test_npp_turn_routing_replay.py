"""Offline contracts for the acceptance-corpus turn routing replay."""

from contextlib import redirect_stderr, redirect_stdout
import importlib.util
import io
import json
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import Mock, patch

from hass import npp

ROOT = Path(__file__).resolve().parents[2]
SCRIPT = ROOT / "scripts/hass/npp_turn_routing_replay.py"
PASS = "PASS npp_turn_routing_replay"
FAIL = "FAIL npp_turn_routing_replay"

SPEC = importlib.util.spec_from_file_location("npp_turn_routing_replay", SCRIPT)
assert SPEC is not None and SPEC.loader is not None
REPLAY = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(REPLAY)


def record(ident, *texts):
    return json.dumps({"id": ident, "texts": texts}) + "\n"


def snapshot():
    entries = {}
    for tree in (ROOT / "hass", ROOT / "storefront-mockup"):
        for path in (tree, *tree.rglob("*")):
            info = path.lstat()
            entries[path.relative_to(ROOT)] = (info.st_size, info.st_mtime_ns)
    return entries


class TurnRoutingReplayTests(unittest.TestCase):
    def setUp(self):
        temporary = tempfile.TemporaryDirectory()
        self.addCleanup(temporary.cleanup)
        self.root = Path(temporary.name)
        self.messages = self.root / "messages.jsonl"

    def invoke(self, path=None):
        stdout, stderr = io.StringIO(), io.StringIO()
        with (patch.object(REPLAY, "MESSAGES", self.messages if path is None else path),
              redirect_stdout(stdout), redirect_stderr(stderr)):
            code = REPLAY.main([])
        return code, stdout.getvalue(), stderr.getvalue()

    def cli(self, *args):
        result = subprocess.run(
            [sys.executable, "-B", str(SCRIPT), *args], cwd=self.root,
            capture_output=True, text=True, timeout=15,
        )
        return result.returncode, result.stdout, result.stderr

    def assert_run(self, result, code, *lines):
        self.assertEqual(result, (code, "\n".join(lines) + "\n", ""))

    def assert_input_failure(self, reason, path=None):
        self.assert_run(self.invoke(path), 1, f"FAIL {reason}", FAIL)

    def test_c1_full_pass(self):
        # A positive asking count must not be treated as an edit finding.
        self.messages.write_text(record("answer", "yes"), encoding="utf-8")
        self.assert_run(self.invoke(), 0, "turns total=1 asking=1 card_out=0", PASS)

    def test_c2_findings_trailer(self):
        # A completed replay with edits must fail, even when every input was valid.
        self.messages.write_text(record("edit", "change the label"), encoding="utf-8")
        self.assert_run(self.invoke(), 1, "turns total=1 asking=1 card_out=1",
                        "FAIL edit-taken edit-0", FAIL)

    def test_c2_1_assets_unreadable(self):
        # Asset validation exceptions must not escape or echo their detail.
        self.messages.write_text(record("answer", "yes"), encoding="utf-8")
        with patch.object(npp, "assets", side_effect=ValueError("synthetic detail")):
            self.assert_input_failure("assets-unreadable")

    def test_c2_2_input_unsafe(self):
        # Following a link or opening a directory would misclassify the entry.
        self.messages.write_bytes(b" " * 1_048_577)
        symlink = self.root / "link"
        symlink.symlink_to(self.messages)
        dangling = self.root / "dangling"
        dangling.symlink_to(self.root / "never-created")
        for path in (symlink, dangling, self.root):
            with self.subTest(entry=path.name):
                self.assert_input_failure("input-unsafe", path)

    def test_c2_3_input_too_large(self):
        # Exactly 1 MiB is allowed; an oversized invalid input fails before parsing.
        limit = 1_048_576
        self.messages.write_bytes(b" " * limit)
        self.assert_run(self.invoke(), 0, "turns total=0 asking=0 card_out=0", PASS)
        self.messages.write_bytes(b"!" * (limit + 1))
        self.assert_input_failure("input-too-large")

    def test_c2_4_input_unreadable(self):
        # A valid first row must not produce a partial report when a later row fails.
        prefix = record("edit", "change the label").encode("utf-8")
        for bad_line in (b"\xff", b"{", b"[]", b'{"id": 1, "texts": []}',
                         b'{"id": "row", "texts": "no"}',
                         b'{"id": "row", "texts": ["yes", 1]}',
                         b'{"id": "row", "texts": [], "extra": NaN}'):
            with self.subTest(bad_line=bad_line):
                self.messages.write_bytes(prefix + bad_line + b"\n")
                self.assert_input_failure("input-unreadable")
        for method in ("lstat", "read_text"):
            with self.subTest(method=method):
                # Simulate OS failures consistently, including when tests run as root.
                self.messages.write_bytes(prefix)
                path = Mock(spec=Path, wraps=self.messages)
                getattr(path, method).side_effect = PermissionError
                self.assert_input_failure("input-unreadable", path)

    def test_c2_5_edit_taken(self):
        # Findings retain file order, count blank physical lines and use zero-based text indices.
        longest = "a" * 64
        contents = (record("z-last", "question?", "swap the title", "set the label") + " \n"
                    + record("bad\nlabel", "put the label") + record(longest, "change the label")
                    + record(longest + "a", "use the title") + record("a-first", "call it a title"))
        self.messages.write_text(contents, encoding="utf-8")
        self.assert_run(self.invoke(), 1, "turns total=7 asking=6 card_out=6",
                        "FAIL edit-taken z-last-1", "FAIL edit-taken z-last-2",
                        "FAIL edit-taken line3-0", f"FAIL edit-taken {longest}-0",
                        "FAIL edit-taken line5-0", "FAIL edit-taken a-first-0", FAIL)

    def test_c2_6_missing_messages(self):
        # A missing path has no lstat mode and is not an unsafe existing entry.
        self.assert_input_failure("input-unreadable", self.root / "never-created")

    def test_c3_usage_exit_2(self):
        # No inputs or built-in flags may route around the no-argument contract.
        for arg in ("extra", "--unknown", "--help", "-h", "--"):
            with self.subTest(arg=arg):
                code, stdout, stderr = self.cli(arg)
                self.assertEqual(code, 2)
                self.assertEqual(stdout, "")
                self.assertTrue(stderr.startswith("usage: "), stderr)
                self.assertEqual(stderr.splitlines()[-1],
                                 f"{SCRIPT.name}: error: unrecognized arguments: {arg}")

    def test_c4_read_only(self):
        # Catch writes to project trees even when the replay completes with findings.
        before = snapshot()
        code, stdout, stderr = self.cli()
        self.assertEqual(code, 1)
        self.assertEqual(stdout.splitlines()[-1], FAIL)
        self.assertEqual(stderr, "")
        self.assertEqual(snapshot(), before)
        self.assertEqual(list(self.root.iterdir()), [])

    def test_c5_output_shape(self):
        # Unsafe IDs and source text must not appear in diagnostics or extra lines.
        self.messages.write_text(record("redact-me\n", "make synthetic marker"), encoding="utf-8")
        self.assert_run(self.invoke(), 1, "turns total=1 asking=1 card_out=1",
                        "FAIL edit-taken line1-0", FAIL)

    def test_c6_fixture(self):
        # A question to the shop stays unclaimed in both states.
        self.messages.write_text('{"id": "q-1", "texts": ["what time do we close?"]}\n', encoding="utf-8")
        self.assert_run(self.invoke(), 0, "turns total=1 asking=0 card_out=0", PASS)

    def test_c7_live_pins(self):
        # The unpatched corpus pins both counts and the exact would-be edit findings.
        findings = (
            "primary-stock-set-1", "primary-hike-edit-0", "primary-shop-notice-0",
            "primary-page-home-0", "primary-page-about-0", "primary-page-photo-0",
            "primary-specials-add-0", "acc-vague-06-0", "acc-vague-09-0", "acc-vague-10-0",
            "acc-typo-08-0", "acc-multi-05-0", "acc-multi-06-0", "acc-refuse-01-0", "acc-refuse-03-0",
        )
        self.assert_run(self.cli(), 1, "turns total=113 asking=105 card_out=15",
                        *(f"FAIL edit-taken {finding}" for finding in findings), FAIL)
