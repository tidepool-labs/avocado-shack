"""Offline contract tests for the hike event state report."""

from contextlib import redirect_stderr, redirect_stdout
from datetime import date
import importlib.util
from io import StringIO
import json
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import patch


SCRIPT = Path(__file__).resolve().parents[2] / "scripts/hass/events_state_report.py"
SPEC = importlib.util.spec_from_file_location("events_state_report", SCRIPT)
assert SPEC is not None and SPEC.loader is not None
report = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(report)

TODAY = "2026-11-21"
PASS = "PASS events_state_report"
FAIL = "FAIL events_state_report"
TITLE = "Synthetic title canary"
MEETING = "Synthetic meeting canary"
RECAP = "Synthetic recap canary"
BAD_ID = "Synthetic ID canary\nstale injected 90"


def event(event_id, starts_at, status="scheduled", **fields):
    return {"id": event_id, "title": TITLE, "startsAt": starts_at,
            "timezone": "America/Los_Angeles", "status": status, **fields}


class EventsStateReportTests(unittest.TestCase):
    def setUp(self):
        temporary = tempfile.TemporaryDirectory()
        self.addCleanup(temporary.cleanup)
        self.root = Path(temporary.name).resolve()
        self.content = self.root / "synthetic-input-canary"
        self.content.mkdir()

    def write_content(self, *events):
        documents = {
            "products": {"products": [{
                "id": "test-fruit", "name": "Test Fruit", "brand": "Test Maker",
                "displayBrand": "Test Maker", "category": "fruit",
                "image": "assets/products/test-fruit.webp", "description": "Fixture fruit.",
                "status": "active", "producerKey": "test-maker",
            }]},
            "makers": {"makers": {"test-maker": {
                "name": "Test Maker", "place": "Testville, California", "story": "Fixture maker.",
            }}},
            "community": {"club": {"clubName": "Test Club", "organizer": "Test Organizer",
                                   "intendedSender": "Test Sender", "emailConnected": False},
                          "events": events, "routeIdeas": []},
            "store": {"name": "Test Store", "streetAddress": "Example Lane", "town": "Testville",
                      "hours": ["Monday-Friday 9am-5pm", "Closed Saturday-Sunday"]},
        }
        for name, document in documents.items():
            (self.content / f"{name}.json").write_text(
                json.dumps({"schemaVersion": 1, **document}), encoding="utf-8",
            )

    def cli(self, *args):
        return subprocess.run([sys.executable, "-B", str(SCRIPT), *args], cwd=self.root,
                              capture_output=True, text=True, timeout=10)

    def run_report(self, *, content=None, today=TODAY):
        return self.cli("--content", str(content or self.content), "--today", today)

    def assert_report(self, result, code, last_line):
        self.assertEqual(result.returncode, code, result.stderr)
        self.assertEqual(result.stderr, "")
        lines = result.stdout.splitlines()
        self.assertTrue(lines)
        self.assertEqual(lines[-1], last_line)
        return lines

    def test_c1_full_pass(self):
        # An empty, valid copy still needs all totals and the pass marker.
        self.write_content()
        lines = self.assert_report(self.run_report(), 0, PASS)
        self.assertEqual(lines, ["events 0", "scheduled 0", "completed 0", "cancelled 0",
                                 "note completed-no-recap 0", "note cancelled-no-note 0",
                                 "note rsvp-no-capacity 0", PASS])

    def test_c2_1_unsafe_input(self):
        # is_dir alone would accept a symlink to a valid directory.
        self.write_content()
        alias = self.root / "alias"
        alias.symlink_to(self.content, target_is_directory=True)
        for path in (alias, self.content / "community.json", self.root / "missing"):
            with self.subTest(kind=path.name):
                lines = self.assert_report(self.run_report(content=path), 1, FAIL)
                self.assertEqual(lines, ["FAIL unsafe-input", FAIL])

    def test_c2_2_content_invalid(self):
        # An invalid schema, invalid JSON, invalid UTF-8, and an incomplete copy
        # all have the same fixed output; no traceback or loader detail escapes.
        for payload in (b'{"schemaVersion": 2}', b'{', b'\xff'):
            with self.subTest(payload=payload):
                self.write_content()
                (self.content / "community.json").write_bytes(payload)
                lines = self.assert_report(self.run_report(), 1, FAIL)
                self.assertEqual(lines, ["FAIL content-invalid", FAIL])
        lines = self.assert_report(self.run_report(content=self.root), 1, FAIL)
        self.assertEqual(lines, ["FAIL content-invalid", FAIL])

    def test_c2_3_stale_scheduled(self):
        # Both starts are late enough to land on the next UTC day. ID order
        # differs from input/date order, and an upcoming hike must not count.
        self.write_content(event("z-hike", "2026-07-18T23:45:00-07:00"),
                           event("a-hike", "2026-07-19T23:45:00-07:00"),
                           event("future-hike", "2026-07-21T09:00:00-07:00"))
        lines = self.assert_report(self.run_report(today="2026-07-20"), 1, FAIL)
        self.assertEqual(lines, ["events 3", "scheduled 3", "completed 0", "cancelled 0",
                                 "stale a-hike 1", "stale z-hike 2", "note completed-no-recap 0",
                                 "note cancelled-no-note 0", "note rsvp-no-capacity 0",
                                 "FAIL stale-scheduled 2", FAIL])

    def test_c3_usage_exit_2(self):
        # Misuse must not be reported as a finding or fall through to the loader.
        self.write_content()
        content = ("--content", str(self.content))
        for args in ((), (*content, "--bogus"), (*content, "--today", "2026-02-30")):
            with self.subTest(args=args):
                result = self.cli(*args)
                self.assertEqual(result.returncode, 2)
                self.assertEqual(result.stdout, "")
                self.assertEqual(result.stderr.splitlines()[-1],
                                 "events_state_report.py: error: invalid arguments (see --help)")

    def test_c4_read_only(self):
        # A future auto-close implementation must not rewrite data or add a sidecar.
        self.write_content(event("past-hike", "2026-11-20T09:00:00-08:00"))

        def snapshot():
            return {p.relative_to(self.content): (p.stat().st_mtime_ns,
                                                   p.read_bytes() if p.is_file() else None)
                    for p in (self.content, *self.content.rglob("*"))}

        before = snapshot()
        lines = self.assert_report(self.run_report(), 1, FAIL)
        self.assertIn("FAIL stale-scheduled 1", lines)
        self.assertEqual(snapshot(), before)

    def test_c5_no_private_values(self):
        # A report dump, raw validator message, or argparse argument echo leaks data.
        self.write_content(event("past-hike", "2026-11-20T09:00:00-08:00",
                                 rsvpEnabled=True, meetingPoint=MEETING),
                           event("closed-hike", "2026-11-19T09:00:00-08:00",
                                 "completed", recap=RECAP))
        finding = self.run_report()
        self.assertIn("stale past-hike 1", self.assert_report(finding, 1, FAIL))
        self.write_content(event(BAD_ID, "2026-11-20T09:00:00-08:00"))
        invalid = self.run_report()
        self.assertEqual(self.assert_report(invalid, 1, FAIL), ["FAIL content-invalid", FAIL])
        usage = self.cli("--content", str(self.content), str(self.content))
        self.assertEqual((usage.returncode, usage.stdout), (2, ""))
        for result in (finding, invalid, usage):
            for canary in (TITLE, MEETING, RECAP, BAD_ID.splitlines()[0], str(self.content)):
                self.assertNotIn(canary, result.stdout)
                self.assertNotIn(canary, result.stderr)

    def test_c6_today_not_stale(self):
        # Do not use <= or the current instant; the report uses Pacific dates.
        self.write_content(event("today-hike", "2026-11-21T00:00:00-08:00"))
        lines = self.assert_report(self.run_report(), 0, PASS)
        self.assertIn("scheduled 1", lines)
        self.assertFalse(any(line.startswith("stale ") for line in lines))

    def test_c7_completed_not_stale(self):
        # Comparing dates before filtering status would flag a completed hike.
        self.write_content(event("closed-hike", "2026-11-19T09:00:00-08:00",
                                 "completed", recap=RECAP))
        lines = self.assert_report(self.run_report(), 0, PASS)
        self.assertIn("completed 1", lines)
        self.assertFalse(any(line.startswith("stale ") for line in lines))

    def test_c8_notes_informational(self):
        # Count only the matching status/absence pairs, without failing the run.
        past, today = "2026-11-19T09:00:00-08:00", "2026-11-21T23:45:00-08:00"
        self.write_content(event("done-missing", past, "completed"),
                           event("done-with-text", past, "completed", recap=RECAP),
                           event("cancel-missing", past, "cancelled", rsvpEnabled=True,
                                 meetingPoint=MEETING),
                           event("cancel-with-text", past, "cancelled", cancelNote="Test closure"),
                           event("open-missing", today, rsvpEnabled=True, meetingPoint=MEETING),
                           event("open-with-cap", today, rsvpEnabled=True, meetingPoint=MEETING,
                                 capacity=7),
                           event("open-no-rsvp", today, rsvpEnabled=False))
        lines = self.assert_report(self.run_report(), 0, PASS)
        self.assertEqual(lines, ["events 7", "scheduled 3", "completed 2", "cancelled 2",
                                 "note completed-no-recap 1", "note cancelled-no-note 1",
                                 "note rsvp-no-capacity 1", PASS])

    def test_default_shop_date(self):
        # A system date instead of the shop clock would not flag this fixture.
        self.write_content(event("past-hike", "2099-01-01T09:00:00-08:00"))
        with patch.object(report.content_model, "shop_today", return_value=date(2099, 1, 2)):
            out, err = StringIO(), StringIO()
            with redirect_stdout(out), redirect_stderr(err):
                code = report.main(["--content", str(self.content)])
        self.assertEqual((code, err.getvalue()), (1, ""))
        self.assertEqual(out.getvalue().splitlines()[-3:],
                         ["note rsvp-no-capacity 0", "FAIL stale-scheduled 1", FAIL])
        self.assertIn("stale past-hike 1", out.getvalue().splitlines())

    def test_invalid_id_output_guard(self):
        # Today's validator rejects invalid IDs. Simulate a future permissive
        # validator to prove that the formatter still suppresses unsafe IDs.
        self.write_content(event("past-hike", "2026-11-20T09:00:00-08:00"),
                           event("today-hike", "2026-11-21T09:00:00-08:00"))
        loaded = report.content_model.load_and_validate(self.content, None)
        loaded.community["events"][0]["id"] = BAD_ID
        loaded.community["events"][1]["id"] = "another-id\n"
        with patch.object(report.content_model, "load_and_validate", return_value=loaded):
            out, err = StringIO(), StringIO()
            with redirect_stdout(out), redirect_stderr(err):
                code = report.main(["--content", str(self.content), "--today", TODAY])
        self.assertEqual((code, err.getvalue()), (1, ""))
        self.assertEqual(out.getvalue().splitlines(), [
            "events 2", "scheduled 2", "completed 0", "cancelled 0", "note completed-no-recap 0",
            "note cancelled-no-note 0", "note rsvp-no-capacity 0", "note invalid-id 2",
            "FAIL stale-scheduled 1", FAIL,
        ])
