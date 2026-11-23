"""Contract tests for the offline route idea date checker."""

import contextlib
import importlib.util
import io
import json
from pathlib import Path
import subprocess
import sys
import tempfile
from types import SimpleNamespace
import unittest
from unittest.mock import patch


SCRIPT = Path(__file__).resolve().parents[2] / "scripts/hass/route_idea_dates.py"
PASS = "PASS route_idea_dates"
FAIL = "FAIL route_idea_dates"


def route(idea_id="fixture-route", **overrides):
    return {
        "id": idea_id, "title": "Ridge walk", "place": "Testville", "character": "Quiet",
        "distance": "One mile", "difficulty": "Easy", "elevation": "Minimal",
        "elevationLabel": "Elevation gain", "duration": "One hour", "routeType": "Loop",
        "terrain": "Gravel", "description": "A walk along the ridge.",
        "sourceUrl": "https://example.com/routes", "sourceName": "Trail guide",
        "status": "idea", "rsvpEnabled": False, **overrides,
    }


class RouteIdeaDatesTests(unittest.TestCase):
    def setUp(self):
        temp = tempfile.TemporaryDirectory()
        self.addCleanup(temp.cleanup)
        self.root = Path(temp.name).resolve()
        self.copy = self.root / "synthetic-private-input-path"
        self.copy.mkdir()

    def fixture(self, *ideas):
        docs = {
            "makers": {"makers": {"fixture-maker": {
                "name": "Fixture Maker", "place": "Testville, California", "story": "Grows fruit.",
            }}},
            "products": {"products": [{
                "id": "fixture-fruit", "name": "Fixture Fruit", "brand": "Fixture Maker",
                "displayBrand": "Fixture Maker", "category": "fruit", "producerKey": "fixture-maker",
                "image": "assets/products/fixture-fruit.webp", "description": "Fresh fruit.",
                "status": "active",
            }]},
            "store": {
                "name": "Fixture Store", "streetAddress": "1 Example Street", "town": "Testville",
                "hours": ["Monday-Friday 9am-5pm", "Closed Saturday-Sunday"],
            },
            "community": {"club": {
                "clubName": "Fixture Club", "organizer": "Fixture Organizer",
                "intendedSender": "fixture@example.test", "emailConnected": False,
            }, "events": [], "routeIdeas": ideas},
        }
        for name, doc in docs.items():
            (self.copy / f"{name}.json").write_text(
                json.dumps({"schemaVersion": 1, **doc}), encoding="utf-8",
            )

    def cli(self, *args):
        return subprocess.run(
            [sys.executable, "-B", str(SCRIPT), *args], cwd=self.root,
            capture_output=True, text=True, timeout=10,
        )

    def check(self, code, last, path=None):
        result = self.cli("--content", str(self.copy if path is None else path))
        self.assertEqual(result.returncode, code, result.stderr)
        lines = result.stdout.splitlines()
        self.assertEqual(lines[-1:], [last])
        return result, lines

    def test_c1_full_pass(self):
        # A valid copy must pass from a working directory outside the checkout, with no images.
        self.fixture(route())
        result, lines = self.check(0, PASS)
        self.assertEqual(result.stderr, "")
        self.assertEqual(lines, ["ideas 1", "hidden 0", "note dated-hidden 0", "note weekday 0",
                                 "note invalid-id 0", PASS])

    def test_c2_1_unsafe_input(self):
        # Following a symlink would incorrectly pass a copy that otherwise validates.
        self.fixture()
        alias = self.root / "alias"
        alias.symlink_to(self.copy, target_is_directory=True)
        for path in (alias, self.copy / "store.json", self.root / "missing", ""):
            with self.subTest(path=path):
                result, lines = self.check(1, FAIL, path)
                self.assertEqual(lines, ["FAIL unsafe-input", FAIL])
                self.assertEqual(result.stderr, "")

    def test_c2_2_content_invalid(self):
        # Reading only community.json, or leaking a decode exception, would miss these refusals.
        for bad_store in (b'{"schemaVersion": 1}', b'{', b'\xff'):
            with self.subTest(bad_store=bad_store):
                self.fixture(route())
                (self.copy / "store.json").write_bytes(bad_store)
                result, lines = self.check(1, FAIL)
                self.assertEqual(lines, ["FAIL content-invalid", FAIL])
                self.assertEqual(result.stderr, "")

    def test_c2_3_dated_idea(self):
        # Reverse the input order and repeat dates in one field to catch unsorted or duplicate output.
        self.fixture(
            route("z-route", title="Walk MARCH 3", description="2026-03-03 or 2026-03-04"),
            route("a-route", sourceName="Guide revised 31 dec.", terrain="Gravel on Mar. 3rd"),
        )
        _, lines = self.check(1, FAIL)
        self.assertEqual(lines, [
            "ideas 2", "hidden 0", "note dated-hidden 0", "note weekday 0", "note invalid-id 0",
            "dated a-route sourceName", "dated a-route terrain", "dated z-route description",
            "dated z-route title", "FAIL dated-idea 2", FAIL,
        ])

    def test_c3_usage_exit_2(self):
        # Do not turn argparse errors into checker findings or echo extra path arguments.
        for args in ((), ("--content",), ("--content", str(self.copy), "--unknown", str(self.copy))):
            with self.subTest(args=args):
                result = self.cli(*args)
                self.assertEqual(result.returncode, 2)
                self.assertEqual(result.stdout, "")  # No last line for C3.
                self.assertIn("usage:", result.stderr)
                self.assertNotIn(str(self.copy), result.stderr)

    def test_c4_read_only(self):
        # A rewrite with identical bytes would still change file mtime; sidecars change the tree.
        self.fixture(route())

        def snapshot():
            return {
                p.relative_to(self.copy): (p.stat().st_mtime_ns, p.read_bytes() if p.is_file() else None)
                for p in (self.copy, *self.copy.rglob("*"))
            }

        before = snapshot()
        self.check(0, PASS)
        self.assertEqual(snapshot(), before)

    def test_c5_no_private_values(self):
        # Print only safe identifiers and field names, never matches or loader diagnostics.
        title = "Synthetic private title canary"
        date = "March 13"
        description = f"Synthetic private description canary {date}"
        private_id = "Synthetic private invalid ID"
        self.fixture(route(title=title, description=description))
        dated, lines = self.check(1, FAIL)
        self.assertIn("FAIL dated-idea 1", lines)
        self.fixture(route(private_id, title=title, description=description))
        invalid, lines = self.check(1, FAIL)
        self.assertEqual(lines, ["FAIL content-invalid", FAIL])
        for result in (dated, invalid):
            for value in (title, description, date, private_id, str(self.copy)):
                self.assertNotIn(value, result.stdout)
                self.assertNotIn(value, result.stderr)

    def test_c6_not_dates(self):
        # Distances, a modal verb, out-of-range days, non-words and excluded fields aren't dates.
        self.fixture(route(
            "2026-03-03", distance="1/2 mile", description="May be muddy",
            terrain="NotMarch 3, March 32, 0 March, 3 Marching, x2026-03-03",
            sourceUrl="https://example.com/Monday/2026-03-03",
        ))
        _, lines = self.check(0, PASS)
        self.assertFalse(any(line.startswith("dated ") for line in lines))
        self.assertIn("note weekday 0", lines)

    def test_c7_hidden_informational(self):
        # Two dated fields on one hidden idea count as one note, never a finding.
        self.fixture(route(), route("quiet-route", status="hidden", title="April 1st", description="2 May"))
        _, lines = self.check(0, PASS)
        self.assertEqual(lines, ["ideas 1", "hidden 1", "note dated-hidden 1", "note weekday 0",
                                 "note invalid-id 0", PASS])

    def test_c8_weekday_informational(self):
        # Count case-insensitive whole words (including repeats), not the prefix of a plural.
        self.fixture(route(description="mOnDaY or Monday, not Mondays."),
                     route("quiet-route", status="hidden", terrain="Sunday gravel"))
        _, lines = self.check(0, PASS)
        self.assertIn("note weekday 3", lines)

    def test_invalid_id_is_counted_without_echo_if_loader_returns_one(self):
        # The real loader already rejects malformed IDs. Simulate a relaxed loader
        # to prove the output check still suppresses the ID without hiding the finding.
        private_id = "synthetic-id\nPRIVATE"
        self.fixture()
        spec = importlib.util.spec_from_file_location("route_idea_dates", SCRIPT)
        assert spec is not None and spec.loader is not None
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)
        content = SimpleNamespace(community={"routeIdeas": [route(private_id, title="Mar. 3rd")]})
        stdout, stderr = io.StringIO(), io.StringIO()
        with patch.object(module.content_model, "load_and_validate", return_value=content), \
                contextlib.redirect_stdout(stdout), contextlib.redirect_stderr(stderr):
            self.assertEqual(module.main(["--content", str(self.copy)]), 1)
        self.assertEqual(stdout.getvalue().splitlines(), [
            "ideas 1", "hidden 0", "note dated-hidden 0", "note weekday 0", "note invalid-id 1",
            "FAIL dated-idea 1", FAIL,
        ])
        self.assertEqual(stderr.getvalue(), "")
