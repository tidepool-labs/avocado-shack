"""Fixture-only tests for the store hours report CLI contract."""

from contextlib import redirect_stderr, redirect_stdout
import importlib.util
from io import StringIO
import json
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest


SCRIPT = Path(__file__).resolve().parents[2] / "scripts/hass/store_hours_report.py"
SPEC = importlib.util.spec_from_file_location("store_hours_report", SCRIPT)
assert SPEC is not None and SPEC.loader is not None
REPORT = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(REPORT)
PASS = "PASS store_hours_report"
FAIL = "FAIL store_hours_report"
PASS_COUNTS = ["lines 2", "open 6", "closed 1", "unnamed 0"]
STORE_NAME = "Synthetic Name Canary"
STORE_ADDRESS = "Synthetic Address Canary"
BAD_HOURS = "Synthetic Hours Canary"


class StoreHoursReportTests(unittest.TestCase):
    def setUp(self):
        temporary = tempfile.TemporaryDirectory()
        self.addCleanup(temporary.cleanup)
        self.root = Path(temporary.name).resolve()
        self.content = self.root / "synthetic-content-canary"
        self.content.mkdir()

    def write_content(self, hours=None):
        documents = {
            "makers": {"makers": {"test-maker": {
                "name": "Fixture Maker", "place": "Testville, California", "story": "A fixture maker.",
            }}},
            "products": {"products": [{
                "id": "test-fruit", "name": "Fixture Fruit", "brand": "Fixture Maker",
                "displayBrand": "Fixture Maker", "category": "fruit",
                "image": "assets/products/test-fruit.webp", "description": "A fixture fruit.",
                "status": "active", "producerKey": "test-maker",
            }]},
            "community": {"club": {
                "clubName": "Fixture Club", "organizer": "Fixture Organizer",
                "intendedSender": "Fixture Sender", "emailConnected": False,
            }, "events": [], "routeIdeas": []},
            "store": {"name": STORE_NAME, "streetAddress": STORE_ADDRESS, "town": "Testville",
                      "hours": ["Monday-Saturday 9am-5pm", "Closed Sunday"] if hours is None else hours},
        }
        for name, document in documents.items():
            (self.content / f"{name}.json").write_text(
                json.dumps({"schemaVersion": 1, **document}, ensure_ascii=False), encoding="utf-8",
            )

    def invoke(self, *args):
        stdout, stderr = StringIO(), StringIO()
        with redirect_stdout(stdout), redirect_stderr(stderr):
            try:
                code = REPORT.main(list(args))
            except SystemExit as exc:
                code = exc.code
        return code, stdout.getvalue(), stderr.getvalue()

    def report(self, path=None):
        return self.invoke("--content", str(self.content if path is None else path))

    def assert_report(self, result, code, lines):
        self.assertEqual(result, (code, "\n".join(lines) + "\n", ""))

    def test_c1_full_pass(self):
        # The file CLI must import Hass outside the repo and count days, not lines.
        self.write_content()
        result = subprocess.run(
            [sys.executable, "-B", str(SCRIPT), "--content", str(self.content)],
            cwd=self.root, capture_output=True, text=True, timeout=10,
        )
        self.assert_report((result.returncode, result.stdout, result.stderr), 0, [*PASS_COUNTS, PASS])

    def test_c2_1_unsafe_input(self):
        # A directory symlink otherwise reads successfully; other non-directories must not reach validation.
        self.write_content()
        alias = self.root / "alias"
        alias.symlink_to(self.content, target_is_directory=True)
        for path in (alias, self.content / "store.json", self.root / "absent"):
            with self.subTest(kind=path.name):
                self.assert_report(self.report(path), 1, ["FAIL unsafe-input", FAIL])

    def test_c2_2_content_invalid(self):
        # Do not bypass validation or let JSON/UTF-8 exceptions escape.
        for replacement in (None, b"{", b"\xff"):
            with self.subTest(replacement=replacement):
                self.write_content([] if replacement is None else None)
                if replacement is not None:
                    (self.content / "store.json").write_bytes(replacement)
                self.assert_report(self.report(), 1, ["FAIL content-invalid", FAIL])

    def test_c2_3_hours_unreadable(self):
        # Validation alone would pass; the CLI must report all errors and no partial counts.
        self.write_content(["Mon 9-5", "Tuesday 9am-5pm", "Fri 9-5"])
        self.assert_report(self.report(), 1, [
            "lines 3", "unreadable line 1", "unreadable line 3", "FAIL hours-unreadable 2", FAIL,
        ])

    def test_c3_usage_exit_2(self):
        # Parse failures must not be conflated with content findings or write stdout.
        for args in ((), ("--content",), ("--content", str(self.content), "--unknown")):
            with self.subTest(args=args):
                code, stdout, stderr = self.invoke(*args)
                self.assertEqual((code, stdout), (2, ""))  # No last stdout line for usage errors.
                self.assertTrue(stderr.startswith("usage:"))
                self.assertEqual(stderr.splitlines()[-1],
                                 "store_hours_report.py: error: invalid arguments; see --help")

    def test_c4_read_only(self):
        # A write-back of identical JSON changes mtimes; a sidecar changes the tree.
        def snapshot():
            return {p.relative_to(self.content): (p.stat().st_mtime_ns, p.read_bytes() if p.is_file() else None)
                    for p in (self.content, *self.content.rglob("*"))}

        for hours, code, lines in (
            (None, 0, [*PASS_COUNTS, PASS]),
            ([BAD_HOURS], 1, ["lines 1", "unreadable line 1", "FAIL hours-unreadable 1", FAIL]),
        ):
            with self.subTest(code=code):
                self.write_content(hours)
                before = snapshot()
                self.assert_report(self.report(), code, lines)
                self.assertEqual(snapshot(), before)

    def test_c5_no_private_values(self):
        # Raw parser errors, loader exceptions, or argv diagnostics can expose private inputs.
        self.write_content([BAD_HOURS])
        unreadable = self.report()
        (self.content / "store.json").rename(self.content / "not-store.json")
        invalid = self.report()
        usage = self.invoke("--content", str(self.content), str(self.root / "extra-path-canary"))
        for (code, stdout, stderr), exit_code, last in (
            (unreadable, 1, FAIL), (invalid, 1, FAIL), (usage, 2, ""),
        ):
            for canary in (BAD_HOURS, STORE_NAME, STORE_ADDRESS, str(self.root), str(self.content)):
                self.assertNotIn(canary, stdout)
                self.assertNotIn(canary, stderr)
            self.assertEqual(code, exit_code)
            self.assertEqual(stdout.splitlines()[-1] if stdout else "", last)

    def test_c6_en_dash_reads(self):
        # An ASCII-only precheck would reject punctuation the site accepts.
        self.write_content(["Monday–Friday 9am–5pm", "Closed Saturday–Sunday"])
        self.assert_report(self.report(), 0, ["lines 2", "open 5", "closed 2", "unnamed 0", PASS])

    def test_c7_day_twice(self):
        # A last-write-wins merge would silently accept the repeated day.
        self.write_content(["Monday 9am-5pm", "Monday 10am-4pm"])
        self.assert_report(self.report(), 1, ["lines 2", "unreadable line 2", "FAIL hours-unreadable 1", FAIL])

    def test_c8_unnamed_informational(self):
        # Omitted days are not closed, and neither omission nor no opening is a failure.
        self.write_content(["Closed Monday"])
        self.assert_report(self.report(), 0, [
            "lines 1", "open 0", "closed 1", "unnamed 6", "note unnamed Tuesday", "note unnamed Wednesday",
            "note unnamed Thursday", "note unnamed Friday", "note unnamed Saturday", "note unnamed Sunday",
            "note no-open-day", PASS,
        ])
