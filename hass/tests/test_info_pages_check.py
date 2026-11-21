"""Fixture-only CLI tests for the offline info-page report."""

import json
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile
import unittest


ROOT = Path(__file__).resolve().parents[2]
SCRIPT = ROOT / "scripts/hass/info_pages_check.py"
TEMPLATES = ROOT / "hass/templates"
TITLE = "Synthetic Title Canary"
PARAGRAPH = "Synthetic paragraph canary for the about page."
PRODUCT = "Synthetic Product Canary"


class InfoPagesCheckTests(unittest.TestCase):
    def setUp(self):
        temporary = tempfile.TemporaryDirectory()
        self.addCleanup(temporary.cleanup)
        self.root = Path(temporary.name).resolve()
        self.content = self.root / "content-canary"
        self.content.mkdir()
        self.templates = self.root / "templates-canary"
        self.store = {"schemaVersion": 1, "name": "Fixture Shop", "streetAddress": "Example Lane",
                      "town": "Testville", "hours": ["Monday-Friday 9am-5pm", "Closed Saturday-Sunday"]}
        self.write_json("store", self.store)
        self.write_json("makers", {"schemaVersion": 1, "makers": {
            "fixture-maker": {"name": "Fixture Maker", "place": "Testville, California",
                              "story": "A synthetic grower used only in this fixture."},
        }})
        self.write_json("products", {"schemaVersion": 1, "products": [
            {"id": "fixture-fruit", "name": PRODUCT, "brand": "Fixture Brand",
             "displayBrand": "Fixture Brand", "category": "fruit",
             "image": "assets/products/fixture-fruit.webp", "description": "Synthetic fruit fixture.",
             "status": "active", "producerKey": "fixture-maker"},
        ]})
        self.write_json("community", {"schemaVersion": 1, "club": {
            "clubName": "Fixture Club", "organizer": "Fixture Organizer",
            "intendedSender": "sender@example.invalid", "emailConnected": False,
        }, "events": [], "routeIdeas": []})

    def write_json(self, name, data):
        (self.content / f"{name}.json").write_text(json.dumps(data), encoding="utf-8")

    def show_about(self):
        self.store["pageAbout"] = {"shown": True, "title": TITLE, "intro": "", "paragraphs": [PARAGRAPH]}
        self.write_json("store", self.store)

    def copy_templates(self):
        shutil.copytree(TEMPLATES, self.templates)

    def replace(self, name, old, new):
        path = self.templates / name
        text = path.read_text(encoding="utf-8")
        self.assertIn(old, text)
        path.write_text(text.replace(old, new, 1), encoding="utf-8")

    def run_cli(self, *args):
        return subprocess.run([sys.executable, "-B", str(SCRIPT), *map(str, args)], cwd=self.root,
                              capture_output=True, text=True, timeout=10, check=False)

    def invoke(self, *, content=None, templates=None):
        return self.run_cli("--content", content if content is not None else self.content,
                            "--templates", templates if templates is not None else self.templates,
                            "--today", "2026-01-15")

    def assert_pass(self, result):
        self.assertEqual(result.returncode, 0)
        self.assertEqual(result.stderr, "")
        lines = result.stdout.splitlines()
        self.assertEqual(lines[-1:], ["PASS info_pages_check"])
        self.assertFalse(any(line.startswith("FAIL ") for line in lines))
        return lines

    def assert_findings(self, result, *reasons):
        self.assertEqual(result.returncode, 1)
        self.assertEqual(result.stderr, "")
        lines = result.stdout.splitlines()
        self.assertEqual(lines[-1:], ["FAIL info_pages_check"])
        self.assertEqual([line for line in lines[:-1] if line.startswith("FAIL ")],
                         [f"FAIL {reason}" for reason in reasons])
        return lines

    def test_c1_full_pass(self):
        # An absent store page field still renders hidden and is counted, not skipped.
        self.assertEqual(self.assert_pass(self.invoke(templates=TEMPLATES)), [
            "page about hidden", "page getting-here hidden", "page policies hidden", "page faq hidden",
            "shown 0 of 4", "PASS info_pages_check",
        ])

    def test_c2_1_unsafe_input(self):
        # is_dir() alone would follow a symlink to a valid fixture directory.
        self.copy_templates()
        for kind, original in (("content", self.content), ("templates", self.templates)):
            alias = self.root / f"{kind}-alias"
            alias.symlink_to(original, target_is_directory=True)
            for invalid in (alias, self.content / "store.json", self.root / "absent"):
                with self.subTest(argument=kind, invalid=invalid.name):
                    lines = self.assert_findings(self.invoke(**{kind: invalid}), "unsafe-input")
                    self.assertEqual(lines, ["FAIL unsafe-input", "FAIL info_pages_check"])

    def test_c2_2_content_invalid(self):
        # Invalid schema, malformed JSON and invalid UTF-8 must stop before render.
        for raw in (b'{"schemaVersion": 1}', b'{', b'\xff'):
            with self.subTest(raw=raw):
                (self.content / "store.json").write_bytes(raw)
                lines = self.assert_findings(self.invoke(templates=TEMPLATES), "content-invalid")
                self.assertEqual(lines, ["FAIL content-invalid", "FAIL info_pages_check"])

    def test_c2_3_render_failed(self):
        # Both an unresolved template slot and an unreadable required template fail closed.
        self.copy_templates()
        self.replace("index.html", "</head>", "{{unknown.slot}}</head>")
        for defect in ("slot", "missing-template"):
            with self.subTest(defect=defect):
                if defect == "missing-template":
                    (self.templates / "index.html").rename(self.templates / "unused.html")
                lines = self.assert_findings(self.invoke(), "render-failed")
                self.assertEqual(lines, ["FAIL render-failed", "FAIL info_pages_check"])

    def test_c2_4_shown_noindex(self):
        # A static robots directive can hide shown pages even with their navigation intact.
        self.show_about()
        self.store["pageFaq"] = {"shown": True, "title": "Fixture FAQ", "entries": []}
        self.write_json("store", self.store)
        self.copy_templates()
        self.replace("info/index.html", "{{info.robots}}", '<meta name="robots" content="noindex">')
        self.assert_findings(self.invoke(), "shown-noindex 2")

    def test_c2_5_hidden_indexable(self):
        # Moving noindex into a comment silently makes the hidden pages indexable.
        self.copy_templates()
        self.replace("info/index.html", "{{info.robots}}", "<!-- {{info.robots}} -->")
        self.replace("hike/index.html", "</footer>", '<a href="/about/">Fixture link</a></footer>')
        self.assert_findings(self.invoke(), "hidden-indexable 4", "footer-hidden-link 1")

    def test_c2_6_footer_hidden_link(self):
        # Looking only at home, deduplicating hrefs, or matching prefixes misses the contract.
        self.copy_templates()
        self.replace("hike/index.html", "</footer>", '<a href="/about/">One</a>'
                     '<a href="/&#97;bout/">Two</a><a href="/policies/?fixture">Other</a></footer>')
        lines = self.assert_findings(self.invoke(), "footer-hidden-link 2")
        self.assertEqual([line for line in lines if line.startswith("link ")],
                         ["link hike/index.html about"] * 2)

    def test_c3_usage_exit_2(self):
        # Don't turn invocation mistakes into content findings or a partial stdout report.
        for args in ((), ("--content", self.content, "--unexpected-fixture"),
                     ("--content", self.content, "--today", "2026-02-30")):
            with self.subTest(case=len(args)):
                result = self.run_cli(*args)
                self.assertEqual(result.returncode, 2)
                self.assertEqual(result.stdout, "")  # No last stdout line on usage errors.
                self.assertTrue(result.stderr.startswith("usage:"))

    def test_c4_read_only(self):
        # Even byte-identical rewrites or creating and removing a sidecar change the snapshot.
        self.copy_templates()

        def snapshot(directory):
            return {p.relative_to(directory): (p.stat().st_mtime_ns, None if p.is_dir() else p.read_bytes())
                    for p in (directory, *directory.rglob("*"))}

        inputs = (self.content, self.templates)
        before = [snapshot(path) for path in inputs]
        self.assert_pass(self.invoke())
        self.assertEqual([snapshot(path) for path in inputs], before)

    def test_c5_no_private_values(self):
        # Reports must not dump rendered words or argparse/renderer exception details.
        self.show_about()
        self.copy_templates()

        def assert_private(result):
            combined = result.stdout + result.stderr
            for canary in (TITLE, PARAGRAPH, PRODUCT, str(self.content), str(self.templates)):
                self.assertFalse(canary in combined, "CLI disclosed a fixture canary")

        result = self.invoke()
        assert_private(result)
        self.assert_pass(result)
        (self.templates / "index.html").rename(self.templates / "unused.html")
        result = self.invoke()
        assert_private(result)
        self.assert_findings(result, "render-failed")
        result = self.run_cli("--content", self.content, "--today", self.templates)
        assert_private(result)
        self.assertEqual((result.returncode, result.stdout), (2, ""))

    def test_c6_shown_linked(self):
        # Shown uses store.pageAbout.shown and the stock home footer supplies the link.
        self.show_about()
        lines = self.assert_pass(self.run_cli("--content", self.content))
        self.assertIn("page about shown", lines)
        self.assertIn("shown 1 of 4", lines)
        self.assertNotIn("note shown-unlinked about", lines)

    def test_c7_hardcoded_hidden_link(self):
        # A hand-written FAQ link bypasses the dynamic footer's visibility guard.
        self.copy_templates()
        self.replace("index.html", "</footer>", '<a href="/faq/">Fixture FAQ</a></footer>')
        lines = self.assert_findings(self.invoke(), "footer-hidden-link 1")
        self.assertEqual([line for line in lines if line.startswith("link ")], ["link index.html faq"])

    def test_c8_robots_case(self):
        # Directive lists and mixed case must work independently of HTML tag/attribute spelling.
        self.copy_templates()
        self.replace("info/index.html", "{{info.robots}}",
                     '<META CONTENT="follow, NoInDeX" NAME="RoBoTs" />')
        self.assert_pass(self.invoke())

    def test_shown_unlinked_is_informational(self):
        # Hike still links to about, but a missing home link is only a note.
        self.show_about()
        self.copy_templates()
        self.replace("index.html", "<button data-policy>", '<button data-policy="">')
        lines = self.assert_pass(self.invoke())
        self.assertIn("note shown-unlinked about", lines)
