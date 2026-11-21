"""Behavioral contract for the offline accessibility CLI, using only fixtures."""

from contextlib import redirect_stderr, redirect_stdout
from datetime import date
import importlib.util
import io
import json
from pathlib import Path
import shutil
import subprocess
import sys
from tempfile import TemporaryDirectory
import unittest
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[2]
SCRIPT = ROOT / "scripts/hass/rendered_a11y_check.py"
PASS = "PASS rendered_a11y_check"
FAIL = "FAIL rendered_a11y_check"
PRODUCT = "Synthetic Fruit Canary"
STORE = "Synthetic Store Canary"
ADDRESS = "Synthetic Address Canary"
PRIVATE_MARKUP = "synthetic-private-markup"


class RenderedA11yCheckTests(unittest.TestCase):
    def setUp(self):
        temp = TemporaryDirectory()
        self.addCleanup(temp.cleanup)
        self.root = Path(temp.name).resolve()
        self.content = self.root / "content-canary"
        self.content.mkdir()
        self.templates = self.root / "templates-canary"
        documents = {
            "products": {"products": [{
                "id": "fixture-fruit", "name": PRODUCT, "category": "fruit",
                "producerKey": "fixture-farm", "brand": "Fixture Farm",
                "displayBrand": "Fixture Farm", "image": "assets/products/fixture-fruit.webp",
                "description": "A piece of fruit.", "status": "active",
            }]},
            "makers": {"makers": {"fixture-farm": {
                "name": "Fixture Farm", "place": "Testville, California", "story": "A fixture farm.",
            }}},
            "store": {"name": STORE, "streetAddress": ADDRESS, "town": "Testville",
                      "hours": ["Monday-Friday 9am-5pm", "Closed Saturday-Sunday"]},
            "community": {"club": {"clubName": "Fixture Walking Club", "intendedSender": "Fixture Sender",
                                   "organizer": "Fixture Organizer", "emailConnected": False},
                          "events": [], "routeIdeas": []},
        }
        for name, document in documents.items():
            (self.content / f"{name}.json").write_text(
                json.dumps({"schemaVersion": 1, **document}), encoding="utf-8")

    def copy_templates(self):
        shutil.copytree(ROOT / "hass/templates", self.templates)

    def edit(self, page, old, new):
        path = self.templates / page
        text = path.read_text(encoding="utf-8")
        self.assertIn(old, text)
        path.write_text(text.replace(old, new), encoding="utf-8")

    def append_markup(self, markup, page="index.html"):
        self.edit(page, "</body>", markup + "</body>")

    def cli(self, *args):
        return subprocess.run([sys.executable, "-B", str(SCRIPT), *args], cwd=self.root,
                              capture_output=True, text=True, timeout=10)

    def run_check(self):
        args = ["--content", str(self.content), "--today", "2030-01-01"]
        if self.templates.is_dir():
            args.extend(("--templates", str(self.templates)))
        return self.cli(*args)

    def assert_result(self, result, status, lines):
        self.assertEqual(result.stderr, "")
        self.assertEqual(result.returncode, status)
        self.assertEqual(result.stdout.splitlines(), lines)

    def assert_findings(self, result, *lines):
        self.assert_result(result, 1, ["pages 6", *lines, FAIL])

    def test_c1_full_pass(self):
        # The default templates render six clean pages even with no image files on disk.
        self.assert_result(self.run_check(), 0, ["pages 6", PASS])
        # The default date is the shop's date, not the caller's local date.
        spec = importlib.util.spec_from_file_location("rendered_a11y_check", SCRIPT)
        assert spec is not None and spec.loader is not None
        check = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(check)
        today = date(2030, 1, 2)
        with (patch.object(check.content_model, "shop_today", return_value=today),
              patch.object(check.sitegen, "render", wraps=check.sitegen.render) as render,
              redirect_stdout(io.StringIO()) as stdout,
              redirect_stderr(io.StringIO()) as stderr):
            status = check.main(["--content", str(self.content)])
        self.assertEqual(render.call_args.kwargs["today"], today)
        self.assertEqual((status, stdout.getvalue().splitlines(), stderr.getvalue()),
                         (0, ["pages 6", PASS], ""))

    def test_c2_1_unsafe_input(self):
        # is_dir alone would follow a symlink to a perfectly valid directory.
        self.copy_templates()
        file = self.root / "not-a-folder"
        file.touch()
        missing = self.root / "missing-folder"
        for option, target in (("--content", self.content), ("--templates", self.templates)):
            alias = target.with_suffix(".alias")
            alias.symlink_to(target, target_is_directory=True)
            for bad in (alias, file, missing):
                with self.subTest(option=option, bad=bad.name):
                    result = self.cli("--content", str(bad if option == "--content" else self.content),
                                      "--templates", str(bad if option == "--templates" else self.templates))
                    self.assert_result(result, 1, ["FAIL unsafe-input", FAIL])

    def test_c2_2_content_invalid(self):
        # Do not bypass validation or let invalid JSON/UTF-8 produce a traceback.
        for raw in (b'{"schemaVersion": 0, "products": []}', b"{", b"\xff"):
            with self.subTest(raw=raw):
                (self.content / "products.json").write_bytes(raw)
                self.assert_result(self.run_check(), 1, ["FAIL content-invalid", FAIL])

    def test_c2_3_render_failed(self):
        # Unknown slot and unreadable-as-file template exercise distinct render errors.
        self.copy_templates()
        template = self.templates / "index.html"
        self.append_markup("{{unknown.slot}}")
        self.assert_result(self.run_check(), 1, ["FAIL render-failed", FAIL])
        template.rename(template.with_suffix(".fixture"))
        template.mkdir()
        self.assert_result(self.run_check(), 1, ["FAIL render-failed", FAIL])

    def test_c2_4_no_lang(self):
        # An attribute-presence check would miss a blank language value.
        self.copy_templates()
        self.edit("index.html", '<html lang="en">', "<html>")
        self.edit("hike/index.html", '<html lang="en">', '<html lang="  ">')
        self.assert_findings(self.run_check(), "page hike/index.html no-lang 1",
                             "page index.html no-lang 1", "FAIL no-lang 2")

    def test_c2_5_h1_count(self):
        # A minimum-one test misses extra headings; a maximum-one test misses zero.
        self.copy_templates()
        self.edit("hike/index.html", "<h1 ", "<h2 ")
        self.edit("hike/index.html", "</h1>", "</h2>")
        self.append_markup("<h1>Extra heading</h1>")
        self.assert_findings(self.run_check(), "page hike/index.html h1-count 1",
                             "page index.html h1-count 1", "FAIL h1-count 2")

    def test_c2_6_img_no_alt(self):
        # Count images (not pages), including self-closing markup outside links.
        self.copy_templates()
        self.append_markup('<img src="x"><img src="y" />')
        self.assert_findings(self.run_check(), "page index.html img-no-alt 2", "FAIL img-no-alt 2")

    def test_c2_7_duplicate_id(self):
        # Three copies count once; a copy on a different page does not collide.
        self.copy_templates()
        self.append_markup('<i id="shared"></i><i id="repeat"></i>' * 2 + '<i id="repeat"></i>')
        self.append_markup('<i id="repeat"></i><i id="local-only"></i>', "hike/index.html")
        self.append_markup('<i id="local-only"></i>')
        self.assert_findings(self.run_check(), "page index.html duplicate-id 2", "FAIL duplicate-id 2")

    def test_c2_8_empty_link(self):
        # Ignore non-links and script/hidden text; accept aria-label and nested visible text.
        self.copy_templates()
        self.append_markup('<a href="#"></a><a href="#" aria-label=" "><span hidden>Hidden</span>'
                           '<script>invisible()</script></a><a></a>'
                           '<a href="#" aria-label="Menu"></a><a href="#"><span>Read</span></a>')
        self.assert_findings(self.run_check(), "page index.html empty-link 2", "FAIL empty-link 2")

    def test_c3_usage_exit_2(self):
        # CLI syntax failures are not named accessibility failures or stdout reports.
        for args in ((), ("--content", str(self.content), "--unknown"),
                     ("--content", str(self.content), "--today", "2030-02-30")):
            with self.subTest(args=args):
                result = self.cli(*args)
                self.assertEqual((result.returncode, result.stdout), (2, ""))
                self.assertTrue(result.stderr.startswith("usage:"))

    def test_c4_read_only(self):
        # A render-to-disk or same-byte rewrite would change the tree or mtimes.
        self.copy_templates()

        def snapshot():
            return {path: (path.stat().st_mtime_ns, None if path.is_dir() else path.read_bytes())
                    for root in (self.content, self.templates) for path in (root, *root.rglob("*"))}

        before = snapshot()
        self.assert_result(self.run_check(), 0, ["pages 6", PASS])
        self.assertEqual(snapshot(), before)

    def test_c5_no_private_values(self):
        # A debug dump of input data, tags, ids, or exception text would disclose canaries.
        self.copy_templates()
        self.append_markup(f'<div id="{PRIVATE_MARKUP}">{PRODUCT} {STORE} {ADDRESS}</div>'
                           f'<div id="{PRIVATE_MARKUP}"></div><img src="{PRIVATE_MARKUP}">')
        result = self.run_check()
        # A directory in place of the template produces an OSError with an absolute path.
        template = self.templates / "index.html"
        template.rename(template.with_suffix(".fixture"))
        template.mkdir()
        render_error = self.run_check()
        usage_error = self.cli("--content", str(self.content), "--today", str(self.templates))
        for run in (result, render_error, usage_error):
            for value in (PRODUCT, STORE, ADDRESS, PRIVATE_MARKUP, str(self.content), str(self.templates)):
                self.assertFalse(value in run.stdout or value in run.stderr, "canary leaked")
        self.assert_findings(result, "page index.html img-no-alt 1", "page index.html duplicate-id 1",
                             "FAIL img-no-alt 1", "FAIL duplicate-id 1")
        self.assert_result(render_error, 1, ["FAIL render-failed", FAIL])
        self.assertEqual((usage_error.returncode, usage_error.stdout), (2, ""))

    def test_c6_empty_alt_informational(self):
        # A truthiness check for alt would mistakenly fail on decorative images.
        self.copy_templates()
        self.append_markup('<img src="x" alt="">')
        self.append_markup('<img src="y" alt="">', "hike/index.html")
        self.assert_result(self.run_check(), 0, ["pages 6", "note empty-alt 2", PASS])

    def test_c7_image_link_has_words(self):
        # A text-only link check would miss the accessible name supplied by the image.
        self.copy_templates()
        self.append_markup('<a href="#"><span><img src="x" alt="Open gallery" /></span></a>')
        self.assert_result(self.run_check(), 0, ["pages 6", PASS])

    def test_c8_whitespace_link_empty(self):
        # Character references decode to whitespace, not words.
        self.copy_templates()
        self.append_markup('<a href="#">\n <span>&nbsp;</span>\t</a>')
        self.assert_findings(self.run_check(), "page index.html empty-link 1", "FAIL empty-link 1")
