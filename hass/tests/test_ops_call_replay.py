"""Fixture-only acceptance tests for replaying recorded Hass arguments."""

import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest

from hass.ops import check_args, load_registry


SCRIPT = Path(__file__).resolve().parents[2] / "scripts/hass/ops_call_replay.py"
OP = "product.set_availability"
OK = {"id": "photo-product-001", "available": "yes"}
IMAGE = "assets/products/replay-example.webp"
PASS = "PASS ops_call_replay"
FAIL = "FAIL ops_call_replay"


class OpsCallReplayTests(unittest.TestCase):
    def setUp(self):
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        self.root = Path(tmp.name).resolve()
        self.calls = self.root / "calls.jsonl"
        self.content = self.root / "content"
        self.content.mkdir()
        fixtures = {
            "products": {"products": [{
                "id": OK["id"], "name": "Test Oats", "brand": "Test Brand",
                "displayBrand": "Test Brand", "category": "pantry",
                "image": "assets/products/photo-product-001.webp",
                "description": "Rolled oats.", "status": "active", "producerKey": "harbor-lane",
            }]},
            "makers": {"makers": {"harbor-lane": {
                "name": "Harbor Lane", "place": "Testville, California", "story": "A test maker.",
            }}},
            "store": {
                "name": "Test Store", "streetAddress": "Example Street", "town": "Testville",
                "hours": ["Monday-Friday 9am-5pm", "Closed Saturday-Sunday"],
            },
            "community": {"club": {
                "clubName": "Test Club", "organizer": "Test Organizer",
                "intendedSender": "club@example.com", "emailConnected": False,
            }, "events": [], "routeIdeas": []},
        }
        for name, data in fixtures.items():
            (self.content / f"{name}.json").write_text(
                json.dumps({"schemaVersion": 1, **data}), encoding="utf-8",
            )

    @staticmethod
    def call(args=OK, op=OP):
        return json.dumps({"op": op, "args": args}) + "\n"

    def cli(self, *options):
        return subprocess.run(
            [sys.executable, "-B", str(SCRIPT), *map(str, options)], cwd=self.root,
            capture_output=True, text=True, timeout=10,
        )

    def replay(self, raw=None, *, calls=None, content=None):
        if raw is not None:
            self.calls.write_bytes(raw.encode("utf-8") if isinstance(raw, str) else raw)
        return self.cli("--calls", calls or self.calls, "--content", content or self.content)

    def assert_report(self, result, code, trailer, *lines):
        self.assertEqual(result.returncode, code, result.stderr)
        self.assertEqual(result.stderr, "")
        self.assertEqual(result.stdout, "\n".join((*lines, trailer)) + "\n")

    def test_c1_full_pass(self):
        # Blank lines must not inflate totals or change the physical line numbers.
        self.assert_report(self.replay(" \t\n" + self.call() + "\n" + self.call()), 0, PASS,
                           "line 2 ok", "line 4 ok", "calls 2", "ok 2", "refused 0")
        self.assert_report(self.replay(" \n\t\n"), 0, PASS, "calls 0", "ok 0", "refused 0")

    def test_c2_findings_trailer(self):
        # An unreadable path must fail before any report rows, not escape as an exception.
        self.assert_report(self.replay(), 1, FAIL, "FAIL unsafe-input")

    def test_c2_1_unsafe_input(self):
        # Followed symlinks would pass the same kind checks as the positive fixtures.
        self.calls.write_text(self.call(), encoding="utf-8")
        file_link = self.root / "calls-link"
        file_link.symlink_to(self.calls)
        dir_link = self.root / "content-link"
        dir_link.symlink_to(self.content, target_is_directory=True)
        fifo = self.root / "calls-fifo"
        os.mkfifo(fifo)
        for calls, content in ((file_link, self.content), (fifo, self.content),
                               (self.content, self.content), (self.calls, dir_link),
                               (self.calls, self.calls)):
            with self.subTest(calls=calls.name, content=content.name):
                self.assert_report(self.replay(calls=calls, content=content), 1, FAIL, "FAIL unsafe-input")
        outside = self.root / "makers-copy.json"
        (self.content / "makers.json").rename(outside)
        (self.content / "makers.json").symlink_to(outside)
        self.assert_report(self.replay(), 1, FAIL, "FAIL unsafe-input")

    def test_c2_2_too_large(self):
        # A valid prefix plus padding catches truncation and the inclusive byte limit.
        raw = self.call().encode("utf-8").ljust(1_000_000)
        self.assert_report(self.replay(raw), 0, PASS, "line 1 ok", "calls 1", "ok 1", "refused 0")
        self.assert_report(self.replay(raw + b" "), 1, FAIL, "FAIL too-large")
        store = self.content / "store.json"
        store.write_bytes(store.read_bytes().ljust(1_000_001))
        self.assert_report(self.replay(self.call()), 1, FAIL, "FAIL too-large")

    def test_c2_3_not_utf8(self):
        # Valid rows before the bad byte must not be reported as a partial replay.
        self.assert_report(self.replay(self.call().encode("utf-8") + b"\xff"), 1, FAIL, "FAIL not-utf8")

    def test_c2_4_content_invalid(self):
        # Both a decoded but invalid schema and a decode failure bar replay.
        store = self.content / "store.json"
        for raw in (b'{"schemaVersion": 1, "store": {}}', b"\xff"):
            with self.subTest(raw=raw):
                store.write_bytes(raw)
                self.assert_report(self.replay(self.call()), 1, FAIL, "FAIL content-invalid")

    def test_c2_5_too_many_lines(self):
        # The 2000th nonblank line must run; the 2001st can't be cut off.
        raw = self.call() * 2000 + "\n"
        self.assert_report(self.replay(raw), 0, PASS,
                           *(f"line {k} ok" for k in range(1, 2001)), "calls 2000", "ok 2000", "refused 0")
        self.assert_report(self.replay(raw + self.call()), 1, FAIL, "FAIL too-many-lines")

    def test_c2_6_refused(self):
        # Distinct malformed shapes and unknown ops all contribute to the refusal count.
        raw = self.call(op="synthetic.unknown") + '{\n[]\n{}\n{"op":4}\n'
        self.assert_report(self.replay(raw), 1, FAIL, "line 1 unknown-op", "line 2 malformed",
                           "line 3 malformed", "line 4 malformed", "line 5 malformed",
                           "calls 5", "ok 0", "refused 5", "FAIL refused 5")

    def test_c3_usage_exit_2(self):
        # Usage errors must not become input findings or echo an absolute argument.
        self.calls.write_text(self.call(), encoding="utf-8")
        for options in (("--content", self.content), ("--calls", "--content", self.content),
                        ("--calls", self.calls, "--content", self.content, "--unknown", self.root)):
            with self.subTest(options=options):
                result = self.cli(*options)
                self.assertEqual(result.returncode, 2)
                self.assertEqual(result.stdout, "")  # No last stdout line for C3.
                self.assertEqual(result.stderr.splitlines()[-1],
                                 "ops_call_replay: error: expected --calls FILE and --content DIR")

    def test_c4_read_only(self):
        # Detect rewrites (even identical bytes) and new entries under either input directory.
        self.calls.write_text(self.call(), encoding="utf-8")

        def snapshot():
            return {path.relative_to(self.root): (path.stat().st_mtime_ns,
                    path.read_bytes() if path.is_file() else None) for path in self.root.rglob("*")}

        before = snapshot()
        self.assert_report(self.replay(), 0, PASS, "line 1 ok", "calls 1", "ok 1", "refused 0")
        self.assertEqual(snapshot(), before)

    def test_c5_no_private_values(self):
        # A raw parse/validation error or echo could leak argument, op or path text.
        value, op = "synthetic-private-argument", "synthetic.private-operation"
        raw = self.call({"available": value, value: value}) + self.call(op=op) + str(self.calls) + "\n"
        result = self.replay(raw)
        self.assert_report(result, 1, FAIL, "line 1 problems 2 missing 1", "line 2 unknown-op",
                           "line 3 malformed", "calls 3", "ok 0", "refused 3", "FAIL refused 3")
        for canary in (value, op, str(self.calls), str(self.content)):
            self.assertNotIn(canary, result.stdout + result.stderr)
        self.assert_report(self.replay(content=self.root / "private-input-path"), 1, FAIL, "FAIL unsafe-input")

    def test_c6_ok_call(self):
        # An exact known-good call must not be refused even without a site directory.
        self.assert_report(self.replay(self.call()), 0, PASS, "line 1 ok", "calls 1", "ok 1", "refused 0")

    def test_c7_pinned_calls(self):
        # Count the real checker results: problems and missing arguments are independent.
        raw = "".join(self.call(args) for args in (
            OK, {"id": "x", "available": "maybe"}, {"available": "yes"},
            {"id": "BAD ID", "available": "yes", "zzz": 1}, [],
        ))
        self.assert_report(self.replay(raw), 1, FAIL, "line 1 ok", "line 2 problems 1 missing 0",
                           "line 3 problems 0 missing 1", "line 4 problems 2 missing 0",
                           "line 5 problems 1 missing 0", "calls 5", "ok 1", "refused 4", "FAIL refused 4")

    def test_offline_image_arguments_check_syntax_without_site_files(self):
        # Valid syntax used to raise Path(None); skipping the whole image check would let row 2 pass.
        raw = "".join(self.call({"id": OK["id"], "image": image}, op="product.edit")
                      for image in (IMAGE, "assets/other/replay-example.webp"))
        self.assert_report(self.replay(raw), 1, FAIL, "line 1 ok", "line 2 problems 1 missing 0",
                           "calls 2", "ok 1", "refused 1", "FAIL refused 1")

    def test_check_args_still_refuses_missing_image_with_site_dir(self):
        # The same real op still requires the file when given a site directory.
        site = self.root / "site"
        site.mkdir()
        op = load_registry()["product.edit"]
        args = {"id": OK["id"], "image": IMAGE}
        self.assertEqual(check_args(op, args, {}, site),
                         (["product.edit.image: image file does not exist"], []))
