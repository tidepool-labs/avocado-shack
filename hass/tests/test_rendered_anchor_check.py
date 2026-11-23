"""Numbered CLI contract tests using only synthetic content and offline renders."""

from datetime import date
import html
import json
from pathlib import Path
import re
import shutil
import subprocess
import sys
import tempfile
import unittest

from hass import content_model, sitegen


ROOT = Path(__file__).resolve().parents[2]
SCRIPT = ROOT / "scripts/hass/rendered_anchor_check.py"
TEMPLATES = ROOT / "hass/templates"
TODAY = "2026-01-15"
PRODUCT = "Fixture Canary Pear"
STORE = "Fixture Canary Market"
ADDRESS = "Example Orchard Lane"


class RenderedAnchorCheckTests(unittest.TestCase):
    def setUp(self):
        temp = tempfile.TemporaryDirectory(prefix="anchor-fixture-")
        self.addCleanup(temp.cleanup)
        self.root = Path(temp.name).resolve()
        self.content = self.root / "content-canary"
        self.templates = self.root / "templates-canary"
        self.content.mkdir()
        self.write_json("makers", {"makers": {"fixture-maker": {
            "name": "Fixture Orchard", "place": "Testville, California", "story": "A small orchard.",
        }}})
        self.write_json("products", {"products": [{
            "id": "fixture-pear", "name": PRODUCT, "brand": "Fixture Orchard",
            "displayBrand": "Fixture Orchard", "producerKey": "fixture-maker", "category": "fruit",
            "image": "assets/products/fixture-pear.webp", "description": "A crisp pear.", "status": "active",
        }]})
        self.write_json("community", {
            "club": {"clubName": "Fixture Walking Club", "organizer": "Fixture Organizer",
                     "intendedSender": "fixture@example.invalid", "emailConnected": False},
            "events": [], "routeIdeas": [],
        })
        self.store = {"name": STORE, "streetAddress": ADDRESS, "town": "Testville",
                      "hours": ["Monday-Friday 9am-5pm", "Closed Saturday-Sunday"]}
        self.write_json("store", self.store)

    def write_json(self, name, data):
        (self.content / f"{name}.json").write_text(
            json.dumps({"schemaVersion": 1, **data}), encoding="utf-8",
        )

    def copy_templates(self):
        shutil.copytree(TEMPLATES, self.templates)

    def add_markup(self, page, markup):
        path = self.templates / page
        text = path.read_text(encoding="utf-8")
        self.assertIn("</body>", text)
        path.write_text(text.replace("</body>", markup + "\n</body>"), encoding="utf-8")

    def cli(self, *args):
        return subprocess.run(
            [sys.executable, "-B", str(SCRIPT), *map(str, args)], cwd=self.root,
            capture_output=True, text=True, timeout=10,
        )

    def invoke(self, *, content=None, templates=None):
        args = ["--content", content if content is not None else self.content, "--today", TODAY]
        if templates is not None:
            args.extend(("--templates", templates))
        return self.cli(*args)

    def assert_result(self, result, reason=None):
        self.assertEqual(result.stderr, "")
        self.assertEqual(result.returncode, 0 if reason is None else 1, result.stdout)
        lines = result.stdout.splitlines()
        self.assertTrue(lines)
        marker = "PASS" if reason is None else "FAIL"
        self.assertEqual(lines[-1], f"{marker} rendered_anchor_check")
        self.assertEqual([line for line in lines[:-1] if line.startswith("FAIL ")],
                         [] if reason is None else [f"FAIL {reason}"])
        return lines

    def test_c1_full_pass(self):
        # Resolving against cwd or checking source-page IDs for cross-page links breaks this.
        control = self.assert_result(self.cli("--content", self.content))
        self.assertIn("pages 6", control)
        self.copy_templates()
        self.add_markup("hike/index.html", """
            <a href="?view=walks#hikes">Same page</a>
            <a href="/?view=home#market">Home</a>
            <a href="/hike#hikes">Directory index</a>
            <a href="/about/#main">Trailing slash</a>
            <a href="../index.html#newsletter">Relative file</a>
            <a href="&#35;hikes">Decoded href</a>
            <span id="walk&amp;talk"></span><a href="#walk&amp;talk">Non-reportable ID</a>
        """)
        lines = self.assert_result(self.invoke(templates=self.templates))
        checked_before = int(control[1].removeprefix("anchors "))
        self.assertGreater(checked_before, 0)
        self.assertEqual(lines[:2], ["pages 6", f"anchors {checked_before + 7}"])
        self.assertFalse(any(line.startswith(("anchor ", "note offpage ")) for line in lines))

    def test_c2_1_unsafe_input(self):
        # is_dir() alone follows symlinks; exists() alone admits files.
        self.copy_templates()
        link = self.root / "linked-directory"
        link.symlink_to(self.content, target_is_directory=True)
        for option in ("content", "templates"):
            for path in (link, self.content / "store.json", self.root / "absent"):
                with self.subTest(option=option, path=path.name):
                    self.assert_result(self.invoke(**{option: path}), "unsafe-input")

    def test_c2_2_content_invalid(self):
        # Invalid schema, malformed JSON, or decoder failures must not traceback.
        path = self.content / "store.json"
        for raw in (b'{"schemaVersion": 0}', b'{', b'\xff'):
            with self.subTest(raw=raw):
                path.write_bytes(raw)
                self.assertEqual(self.assert_result(self.invoke(), "content-invalid"),
                                 ["FAIL content-invalid", "FAIL rendered_anchor_check"])

    def test_c2_3_render_failed(self):
        # Both a bad template slot and an unreadable-as-a-template directory fail cleanly.
        self.copy_templates()
        self.add_markup("index.html", "{{fixture.unknown}}")
        for templates in (self.templates, self.root / "empty-templates"):
            with self.subTest(templates=templates.name):
                templates.mkdir(exist_ok=True)
                self.assertEqual(self.assert_result(self.invoke(templates=templates), "render-failed"),
                                 ["FAIL render-failed", "FAIL rendered_anchor_check"])

    def test_c2_4_anchor_missing(self):
        # Count href occurrences as checked, but count each missing tuple only once.
        before = self.assert_result(self.invoke())
        self.copy_templates()
        self.add_markup("index.html", """
            <a href="#Zulu">Missing</a><a href="?a=1#Zulu">Same jump</a>
            <a href="/about/#Alpha">Also missing</a>
            <a href="#Bad&#10;fragment">Unsafe to print</a>
        """)
        self.add_markup("hike/index.html", '<a href="/#Zulu">Different source</a>')
        lines = self.assert_result(self.invoke(templates=self.templates), "anchor-missing 4")
        self.assertEqual(lines, [
            before[0], f"anchors {int(before[1].removeprefix('anchors ')) + 5}",
            "anchor hike/index.html index.html Zulu",
            "anchor index.html about/index.html Alpha",
            "anchor index.html index.html Zulu",
            "note unprintable 1", "FAIL anchor-missing 4", "FAIL rendered_anchor_check",
        ])

    def test_c3_usage_exit_2(self):
        # Don't normalize argparse's rejection into a findings exit or report.
        for args in ((), ("--content", self.content, "--unknown"),
                     ("--content", self.content, "--today", "2026-02-30")):
            with self.subTest(args=args):
                result = self.cli(*args)
                self.assertEqual(result.returncode, 2)
                self.assertEqual(result.stdout, "")  # C3 has no final stdout line.
                self.assertIn("usage:", result.stderr)

    def test_c4_read_only(self):
        # Catch generated-file writes, same-byte rewrites, and newly created entries.
        self.copy_templates()

        def snapshot():
            return {path.relative_to(self.root): (path.stat().st_mtime_ns,
                                                   path.read_bytes() if path.is_file() else None)
                    for root in (self.content, self.templates)
                    for path in (root, *root.rglob("*"))}

        before = snapshot()
        self.assert_result(self.invoke(templates=self.templates))
        self.assertEqual(snapshot(), before)

    def test_c5_no_private_values(self):
        # Never print untrusted fragment text, rendered content, or loader/renderer diagnostics.
        self.copy_templates()
        canaries = (PRODUCT, STORE, ADDRESS, str(self.content), str(self.templates))
        self.add_markup("index.html", "".join(
            f'<a href="#{html.escape(value, quote=True)}">Fixture</a>' for value in canaries
        ))
        missing = self.invoke(templates=self.templates)
        lines = self.assert_result(missing, "anchor-missing 5")
        self.assertIn("note unprintable 5", lines)
        empty = self.root / "missing-template-input-canary"
        empty.mkdir()
        render_error = self.invoke(templates=empty)
        self.assert_result(render_error, "render-failed")
        missing_file_dir = self.root / "missing-content-input-canary"
        missing_file_dir.mkdir()
        content_error = self.invoke(content=missing_file_dir)
        self.assert_result(content_error, "content-invalid")
        for result in (missing, render_error, content_error):
            for canary in (*canaries, str(empty), str(missing_file_dir)):
                self.assertNotIn(canary, result.stdout + result.stderr)

    def test_c6_hidden_newsletter(self):
        # Counting only home or checking template IDs would miss the actual stale jumps.
        self.write_json("store", {**self.store, "homeSections": [
            {"id": name, "shown": name != "newsletter"} for name in content_model.HOME_SECTIONS
        ]})
        content = content_model.load_and_validate(self.content, None)
        pages = sitegen.render(content, TEMPLATES, today=date.fromisoformat(TODAY))
        self.assertNotIn(b'id="newsletter"', pages["storefront-mockup/index.html"])
        expected = {key.removeprefix("storefront-mockup/") for key, data in pages.items()
                    if key.endswith(".html") and re.search(rb'href="/?#newsletter"', data)}
        self.assertGreaterEqual(len(expected), 1)
        lines = self.assert_result(self.invoke(), f"anchor-missing {len(expected)}")
        self.assertEqual([line for line in lines if line.startswith("anchor ")],
                         [f"anchor {page} index.html newsletter" for page in sorted(expected)])

    def test_c7_empty_fragment(self):
        # A bare '#' must neither fail nor increase the checked counter.
        before = self.assert_result(self.invoke())
        self.copy_templates()
        self.add_markup("index.html", '<a href="#">Top</a><a href="/absent#">Empty off-page</a>')
        self.assertEqual(self.assert_result(self.invoke(templates=self.templates)), before)

    def test_c8_offpage_not_checked(self):
        # Unknown or external paths must not be misresolved to a rendered page.
        before = self.assert_result(self.invoke())
        self.copy_templates()
        self.add_markup("index.html", """
            <a href="/absent/#Missing">No rendered page</a>
            <a href="https://example.invalid/#Missing">External URL</a>
            <a href="//about/#Missing">External authority resembling a site page</a>
        """)
        lines = self.assert_result(self.invoke(templates=self.templates))
        self.assertEqual(lines, [*before[:-1], "note offpage 3", before[-1]])


if __name__ == "__main__":
    unittest.main()
