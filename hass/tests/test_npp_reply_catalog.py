"""Fixture-only behavioral tests for the reply catalog CLI."""

import json
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest


ROOT = Path(__file__).resolve().parents[2]
SCRIPT = ROOT / "scripts/hass/npp_reply_catalog.py"
ASSET = ROOT / "hass/npp/assets/hass-npp-reply/reply-templates.json"
PASS = "PASS npp_reply_catalog"
FAIL = "FAIL npp_reply_catalog"


def fixture(**overrides):
    return {
        "questions": {}, "prompts": {}, "brackets": {}, "guards": {}, "confirm": {}, "edits": {},
        "existing": {}, "never_say": [], "caps": {}, **overrides,
    }


class ReplyCatalogTests(unittest.TestCase):
    def setUp(self):
        temp = tempfile.TemporaryDirectory()
        self.addCleanup(temp.cleanup)
        self.root = Path(temp.name)
        self.source = self.root / "fixture.json"
        self.out = self.root / "review.md"

    def invoke(self, *args):
        return subprocess.run([sys.executable, "-B", str(SCRIPT), *args], cwd=self.root,
                              capture_output=True, text=True, encoding="utf-8", timeout=10)

    def run_catalog(self, *, source=None, out=None):
        return self.invoke("--templates", str(source or self.source), "--out", str(out or self.out))

    def write_fixture(self, **overrides):
        self.source.write_text(json.dumps(fixture(**overrides)), encoding="utf-8")

    def assert_status(self, result, status, last):
        self.assertEqual(result.returncode, status)
        self.assertEqual(result.stdout.splitlines()[-1:], [last])
        self.assertEqual(result.stderr, "")

    def assert_findings(self, result, *reasons):
        self.assert_status(result, 1, FAIL)
        self.assertEqual(result.stdout.splitlines(), [*(f"FAIL {reason}" for reason in reasons), FAIL])

    def test_c1_full_pass(self):
        # Dropping nested leaves, counting Markdown escapes, or formatting existing text breaks this page.
        self.write_fixture(
            questions={"z_last": "é|*\nGo", "a_first": "Ask {maker}"},
            prompts={"ready": "Tag {code}-{n}"},
            brackets={"parts": {"z": "{brand}", "a": "{claim}"},
                      "compose": {"open": "(", "drop_order": ["not a template {ignored}"]}},
            guards={"hold": "Wait."}, confirm={"posted": "{url}"}, edits={"source": "{name}"},
            existing={"retake": "Don't copy me {missing}"}, caps={"note": "not a template"},
        )
        result = self.run_catalog()
        self.assert_status(result, 0, PASS)
        self.assertEqual(result.stdout.splitlines(), ["templates 9", "rendered 9", "written yes", PASS])
        rows = self.out.read_text(encoding="utf-8").splitlines()[4:]
        self.assertEqual(rows, [
            r"| questions | a\_first | Ask Example Maker | 17 |",
            r"| questions | z\_last | é\|\*<br>Go | 6 |",
            "| prompts | ready | Tag 4ed1-2 | 10 |",
            "| brackets | compose.open | ( | 1 |",
            "| brackets | parts.a | example claim | 13 |",
            "| brackets | parts.z | Example Brand | 13 |",
            "| guards | hold | Wait. | 5 |",
            "| confirm | posted | https://theavocadoman.com/?item=example#market | 46 |",
            "| edits | source | Example Source | 14 |",
            "| existing | retake | existing | — |",
        ])

    def test_c2_1_templates_unreadable(self):
        # Following a symlink, using lossy decoding, or accepting a partial asset is not a valid read.
        self.assert_findings(self.run_catalog(), "templates-unreadable")
        alt = self.root / "link.json"
        self.write_fixture()
        alt.symlink_to(self.source)
        self.assert_findings(self.run_catalog(source=alt), "templates-unreadable")
        missing = fixture()
        del missing["edits"]
        for raw in (b"\xff", b"{broken", b"[]", json.dumps(missing).encode(),
                    json.dumps(fixture(never_say="not a list")).encode()):
            with self.subTest(raw=raw):
                self.source.write_bytes(raw)
                self.assert_findings(self.run_catalog(), "templates-unreadable")
                self.assertFalse(self.out.exists())

    def test_c2_2_out_exists(self):
        # A normal write can replace a prior report or follow a dangling symlink.
        self.write_fixture()
        self.out.write_bytes(b"prior report")
        before = self.out.stat().st_mtime_ns
        self.assert_findings(self.run_catalog(), "out-exists")
        self.assertEqual((self.out.read_bytes(), self.out.stat().st_mtime_ns), (b"prior report", before))
        dangling = self.root / "dangling.md"
        target = self.root / "absent.md"
        dangling.symlink_to(target)
        self.assert_findings(self.run_catalog(out=dangling), "out-exists")
        self.assertTrue(dangling.is_symlink())
        self.assertFalse(target.exists())

    def test_c2_3_out_parent(self):
        # Auto-creating parents or raising a traceback bypasses the named finding.
        self.write_fixture()
        absent = self.root / "missing"
        self.assert_findings(self.run_catalog(out=absent / "review.md"), "out-parent")
        self.assertFalse(absent.exists())
        self.assert_findings(self.run_catalog(out=self.source / "review.md"), "out-parent")

    def test_c2_4_unknown_placeholder(self):
        # A formatter can stop at the first unknown or count a repeated name twice.
        self.write_fixture(brackets={"parts": {"item": "{first} {code} {other} {first}"}})
        self.assert_findings(self.run_catalog(), "unknown-placeholder brackets.parts.item first",
                             "unknown-placeholder brackets.parts.item other")
        self.assertFalse(self.out.exists())

    def test_c2_5_never_say(self):
        # A source-only scan misses phrases with substituted text; multiple matches are one finding per row.
        self.write_fixture(prompts={"ready": "Show {maker} now"}, guards={"hold": "{unknown}"},
                           never_say=["sHoW EXAMPLE MAKER", "NOW"])
        self.assert_findings(self.run_catalog(), "never-say prompts.ready", "unknown-placeholder guards.hold unknown")
        self.assertFalse(self.out.exists())

    def test_c3_usage_exit_2(self):
        # Usage errors should not masquerade as catalog findings or write a report.
        for args in ((), ("--out",), ("--out", str(self.out), "--unknown")):
            with self.subTest(args=args):
                result = self.invoke(*args)
                self.assertEqual(result.returncode, 2)
                self.assertEqual(result.stdout, "")
                self.assertTrue(result.stderr.startswith("usage: npp_reply_catalog.py"))
                self.assertEqual(result.stderr.splitlines()[-1],
                                 "npp_reply_catalog.py: error: invalid arguments; see --help")
                self.assertEqual(list(self.root.iterdir()), [])

    def test_c4_read_only(self):
        # Check mtimes as well as bytes to catch rewriting an unchanged fixture.
        self.write_fixture(edits={"reply": "Sample {code}"})
        before = (self.source.read_bytes(), self.source.stat().st_mtime_ns)
        baseline = set(self.root.rglob("*"))
        result = self.run_catalog()
        self.assert_status(result, 0, PASS)
        self.assertEqual(set(self.root.rglob("*")), baseline | {self.out})
        self.assertEqual((self.source.read_bytes(), self.source.stat().st_mtime_ns), before)
        original_page = (self.out.read_bytes(), self.out.stat().st_mtime_ns)

        self.write_fixture(edits={"reply": "{unknown}"})
        before = (self.source.read_bytes(), self.source.stat().st_mtime_ns)
        self.assert_findings(self.run_catalog(out=self.root / "refused.md"), "unknown-placeholder edits.reply unknown")
        self.assertEqual(set(self.root.rglob("*")), baseline | {self.out})
        self.assertEqual((self.source.read_bytes(), self.source.stat().st_mtime_ns), before)
        self.assertEqual((self.out.read_bytes(), self.out.stat().st_mtime_ns), original_page)

    def test_c5_no_private_values(self):
        # Catch echoed payloads, JSON/OS tracebacks, and argparse's argument echo.
        canaries = ("fixture-private-chat", "fixture-private-sender", "fixture-private-message",
                    "fixture-full-identifier-abcdef", "deadbeef" * 8)
        self.write_fixture(guards={"hold": " ".join(canaries)})
        passed = self.run_catalog()
        self.assert_status(passed, 0, PASS)
        self.write_fixture(guards={"hold": " ".join(canaries)}, never_say=[canaries[2]])
        finding = self.run_catalog(out=self.root / "other.md")
        self.assert_findings(finding, "never-say guards.hold")
        self.source.write_text("{" + " ".join(canaries), encoding="utf-8")
        malformed = self.run_catalog(out=self.root / "other.md")
        self.assert_findings(malformed, "templates-unreadable")
        usage = self.invoke("--out", str(self.out), str(self.source), *canaries)
        self.assertEqual(usage.returncode, 2)
        self.assertEqual(usage.stdout, "")
        self.assertEqual(usage.stderr.splitlines()[-1],
                         "npp_reply_catalog.py: error: invalid arguments; see --help")
        for result in (passed, finding, malformed, usage):
            for canary in (*canaries, str(self.root.absolute())):
                self.assertFalse(canary in result.stdout or canary in result.stderr, "CLI leaked a canary")

    def test_c6_shipped_asset_passes(self):
        # Use the default input and count object-string leaves separately from the renderer.
        data = json.loads(ASSET.read_text(encoding="utf-8"))
        pending = [data[s] for s in ("questions", "prompts", "brackets", "guards", "confirm", "edits")]
        count = 0
        while pending:
            value = pending.pop()
            if isinstance(value, dict):
                pending.extend(value.values())
            elif isinstance(value, str):
                count += 1
        result = self.invoke("--out", str(self.out))
        self.assert_status(result, 0, PASS)
        self.assertEqual(result.stdout.splitlines(), [f"templates {count}", f"rendered {count}", "written yes", PASS])
        rows = self.out.read_text(encoding="utf-8").splitlines()[4:]
        self.assertEqual(len(rows), count + len(data["existing"]))
        self.assertEqual(sum(row.startswith("| existing |") for row in rows), len(data["existing"]))
