"""Offline fixture tests for the producers copy checker."""

from contextlib import redirect_stderr, redirect_stdout
import importlib.util
import io
import json
from pathlib import Path
import subprocess
import sys
from tempfile import TemporaryDirectory
import unittest


SCRIPT = Path(__file__).resolve().parents[2] / "scripts/hass/producers_file_check.py"
SPEC = importlib.util.spec_from_file_location("producers_file_check", SCRIPT)
assert SPEC is not None and SPEC.loader is not None
CHECKER = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(CHECKER)

KEY = "z-synthetic-maker-key"
HIDDEN_KEY = "a-synthetic-hidden-key"
UNKNOWN_KEY = "synthetic-unknown-key-canary"
MAKER = {
    "name": "Synthetic Canary Orchard",
    "place": "Canary Testville, California",
    "story": "Synthetic story canary",
    "url": "https://orchard-canary.example.com",
}
PASS = "PASS producers_file_check"
FAIL = "FAIL producers_file_check"


class ProducersFileCheckTests(unittest.TestCase):
    def setUp(self):
        self.root = Path(self.enterContext(TemporaryDirectory())).resolve()
        self.content = self.root / "content-canary"
        self.content.mkdir()
        self.file = self.root / "producers-canary.json"
        self.visible = {KEY: MAKER}
        self.write_makers(self.visible)
        self.write_content("products", {"products": [{
            "id": "synthetic-fruit", "name": "Fixture Fruit", "brand": MAKER["name"],
            "displayBrand": MAKER["name"], "category": "fruit",
            "image": "assets/products/synthetic-fruit.webp", "description": "Fixture fruit.",
            "status": "active", "producerKey": KEY,
        }]})
        self.write_content("community", {
            "club": {"clubName": "Fixture Club", "organizer": "Fixture Organizer",
                     "intendedSender": "fixture@example.com", "emailConnected": False},
            "events": [], "routeIdeas": [],
        })
        self.write_content("store", {
            "name": "Fixture Store", "streetAddress": "Fixture Street", "town": "Testville",
            "hours": ["Monday-Friday 9am-5pm", "Closed Saturday-Sunday"],
        })
        self.write_listed(self.visible)

    def write_content(self, name, body):
        (self.content / f"{name}.json").write_text(
            json.dumps({"schemaVersion": 1, **body}), encoding="utf-8",
        )

    def write_makers(self, makers):
        self.write_content("makers", {"makers": makers})

    def write_listed(self, makers):
        self.file.write_text(json.dumps(makers), encoding="utf-8")

    def add_hidden_maker(self):
        hidden = {**MAKER, "hidden": True}
        # The only active product still references the visible maker.
        self.write_makers({**self.visible, HIDDEN_KEY: hidden})
        return hidden

    def args(self, file=None, content=None):
        return ["--producers", str(file or self.file), "--content", str(content or self.content)]

    def invoke(self, file=None, content=None):
        stdout, stderr = io.StringIO(), io.StringIO()
        with redirect_stdout(stdout), redirect_stderr(stderr):
            code = CHECKER.main(self.args(file, content))
        return code, stdout.getvalue(), stderr.getvalue()

    def cli(self, *args):
        result = subprocess.run([sys.executable, "-B", str(SCRIPT), *args], cwd=self.root,
                                capture_output=True, text=True, timeout=10)
        return result.returncode, result.stdout, result.stderr

    def assert_report(self, result, code, *lines):
        actual_code, stdout, stderr = result
        self.assertEqual(actual_code, code)
        self.assertEqual(stderr, "")
        self.assertEqual(stdout.splitlines(), [*lines, PASS if code == 0 else FAIL])

    def test_c1_full_pass(self):
        # A hidden content-only record must not create a missing-maker finding.
        self.add_hidden_maker()
        self.assert_report(self.cli(*self.args()), 0, "listed 1", "visible 1", "hidden 1")

    def test_c2_1_unsafe_input(self):
        # Following symlinks, accepting a directory as a file, or skipping the size cap.
        file_link = self.root / "linked.json"
        file_link.symlink_to(self.file)
        content_link = self.root / "linked-content"
        content_link.symlink_to(self.content, target_is_directory=True)
        oversized = self.root / "large.json"
        # Pad valid JSON sparsely so ignoring the cap can't give the expected result.
        with oversized.open("wb") as stream:
            stream.write(self.file.read_bytes())
            stream.seek(5_000_000)
            stream.write(b" ")
        for label, file, content in (
            ("file symlink", file_link, self.content),
            ("not regular", self.content, self.content),
            ("oversized", oversized, self.content),
            ("content symlink", self.file, content_link),
            ("not directory", self.file, self.file),
        ):
            with self.subTest(case=label):
                self.assert_report(self.invoke(file, content), 1, "FAIL unsafe-input")

    def test_c2_2_content_invalid(self):
        # Ignoring an unrelated content document or letting the decode failure escape.
        path = self.content / "community.json"
        for raw in (b'{"schemaVersion": 1}', b"\xff"):
            with self.subTest(raw=raw):
                path.write_bytes(raw)
                self.assert_report(self.invoke(), 1, "FAIL content-invalid")

    def test_c2_3_producers_unreadable(self):
        # A permissive loader could accept arbitrary JS, a non-object, or junk bytes.
        for suffix, raw in (
            ("txt", b"{}"), ("json", b"[]"), ("json", b"{} {}"), ("json", b"\xff"),
            ("json", b'{"fixture":NaN}'), ("js", b"const producers=[];"),
            ("js", b"const producers={};\n\n"), ("js", b" const producers={};"),
            ("js", b"const producers={}"), ("js", b"const producers={};\nextra();"),
            ("js", b"const producers= {};"), ("js", b"const producers={} ;"),
        ):
            with self.subTest(suffix=suffix, raw=raw):
                candidate = self.file.with_suffix(f".{suffix}")
                candidate.write_bytes(raw)
                self.assert_report(self.invoke(candidate), 1, "FAIL producers-unreadable")

    def test_c2_4_hidden_maker(self):
        # A hidden key is a distinct finding even when its copied record is current.
        self.write_listed({**self.visible, HIDDEN_KEY: self.add_hidden_maker()})
        self.assert_report(self.invoke(), 1, "listed 2", "visible 1", "hidden 1",
                           "FAIL hidden-maker 1")

    def test_c2_5_maker_missing(self):
        # Iterating only the export could certify an empty copy.
        self.write_listed({})
        self.assert_report(self.invoke(), 1, "listed 0", "visible 1", "hidden 0",
                           "FAIL maker-missing 1")

    def test_c2_6_unknown_maker(self):
        # Extra keys cannot be ignored just because all current visible keys are listed.
        self.write_listed({**self.visible, "synthetic-extra-maker": MAKER})
        self.assert_report(self.invoke(), 1, "listed 2", "visible 1", "hidden 0",
                           "FAIL unknown-maker 1")

    def test_c2_7_maker_differs(self):
        # Count records, not field differences; do not count hidden records here.
        hidden = self.add_hidden_maker()
        changed = {**MAKER, "name": "Synthetic Stale Name", "story": "Synthetic Stale Story",
                   "extra-a": True, "extra-b": True}
        changed.pop("url")
        self.write_listed({KEY: changed, HIDDEN_KEY: {**hidden, "hidden": 1}})
        self.assert_report(self.invoke(), 1, "listed 2", "visible 1", "hidden 1",
                           "differs maker#1 hidden", "differs maker#2 name",
                           "differs maker#2 story", "differs maker#2 url", "differs maker#2 other",
                           "FAIL hidden-maker 1", "FAIL maker-differs 1")
        self.write_listed({KEY: []})
        self.assert_report(self.invoke(), 1, "listed 1", "visible 1", "hidden 1",
                           "differs maker#2 other", "FAIL maker-differs 1")

    def test_c3_usage_exit_2(self):
        # Missing values and unknown flags are usage errors, not findings.
        for args in ((), (*self.args(), "--unknown", str(self.root)),
                     ("--producers", str(self.file), "--content"),
                     ("--prod", str(self.file), "--content", str(self.content))):
            with self.subTest(argument_count=len(args)):
                code, stdout, stderr = self.cli(*args)
                self.assertEqual(code, 2)
                self.assertEqual(stdout, "")  # No last stdout line for a usage error.
                self.assertTrue(stderr.startswith("usage: "))
                self.assertNotIn(str(self.root), stderr)

    def test_c4_read_only(self):
        # An auto-rebuild or scratch output under either input directory is a write.
        def snapshot():
            return {path.relative_to(self.root):
                    (path.stat().st_mtime_ns, path.read_bytes() if path.is_file() else None)
                    for path in [self.root, *self.root.rglob("*")]}

        before = snapshot()
        self.assert_report(self.cli(*self.args()), 0, "listed 1", "visible 1", "hidden 0")
        self.assertEqual(snapshot(), before)

    def test_c5_no_private_values(self):
        # A record dump, a validator traceback, or raw filesystem errors may leak data.
        self.write_listed({KEY: {}})
        differing = self.cli(*self.args())
        self.assert_report(differing, 1, "listed 1", "visible 1", "hidden 0",
                           "differs maker#1 name", "differs maker#1 place",
                           "differs maker#1 story", "differs maker#1 url", "FAIL maker-differs 1")
        self.write_makers({KEY: {**MAKER, "hidden": True}})
        invalid = self.cli(*self.args())
        self.assert_report(invalid, 1, "FAIL content-invalid")
        missing_file = self.root / "missing-canary.json"
        unsafe = self.cli(*self.args(file=missing_file))
        self.assert_report(unsafe, 1, "FAIL unsafe-input")
        for _, stdout, stderr in (differing, invalid, unsafe):
            for value in (KEY, *MAKER.values(), str(self.root), str(self.content),
                          str(self.file), str(missing_file)):
                self.assertNotIn(value, stdout + stderr)

    def test_c6_js_round_trip(self):
        # The exact generated assignment is data, including its optional final newline.
        candidate = self.file.with_suffix(".js")
        for ending in ("", "\n"):
            with self.subTest(ending=ending):
                candidate.write_text("const producers=" + json.dumps(self.visible) + ";" + ending,
                                     encoding="utf-8")
                self.assert_report(self.invoke(candidate), 0, "listed 1", "visible 1", "hidden 0")

    def test_c7_place_differs(self):
        # The ordinal includes the unlisted hidden key, not only listed records.
        self.add_hidden_maker()
        stale_place = "Stale Canary Testville, California"
        self.write_listed({KEY: {**MAKER, "place": stale_place}})
        result = self.invoke()
        self.assert_report(result, 1, "listed 1", "visible 1", "hidden 1",
                           "differs maker#2 place", "FAIL maker-differs 1")
        self.assertNotIn(stale_place, result[1] + result[2])
        self.assertNotIn(MAKER["place"], result[1] + result[2])

    def test_c8_unknown_not_printed(self):
        # Unknown keys have no content ordinal and must not be echoed as diagnostics.
        self.write_listed({**self.visible, UNKNOWN_KEY: MAKER})
        result = self.invoke()
        self.assert_report(result, 1, "listed 2", "visible 1", "hidden 0",
                           "FAIL unknown-maker 1")
        self.assertNotIn(UNKNOWN_KEY, result[1] + result[2])
