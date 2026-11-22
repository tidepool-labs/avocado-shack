"""Offline CLI contract tests using disposable content and template fixtures."""

from contextlib import redirect_stderr, redirect_stdout
from datetime import date
import importlib.util
import io
import json
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile
import unittest

from hass import content_model, sitegen

ROOT = Path(__file__).resolve().parents[2]
SCRIPT = ROOT / "scripts/hass/rendered_inline_check.py"
TEMPLATES = ROOT / "hass/templates"
TODAY = "2026-01-10"
PRODUCT, STORE, ADDRESS = "Fixture Canary Fruit", "Fixture Canary Shop", "Fixture Canary Lane"
PASS = "PASS rendered_inline_check"
FAIL = "FAIL rendered_inline_check"
BASE_REPORT = [
    "pages 6", "csp 2", "note no-csp about/index.html", "note no-csp faq/index.html",
    "note no-csp getting-here/index.html", "note no-csp policies/index.html",
    "note inline-style-no-csp 4",
]

SPEC = importlib.util.spec_from_file_location("rendered_inline_check", SCRIPT)
assert SPEC is not None and SPEC.loader is not None
CHECK = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(CHECK)


class RenderedInlineCheckTests(unittest.TestCase):
    def setUp(self):
        temp = tempfile.TemporaryDirectory()
        self.addCleanup(temp.cleanup)
        self.root = Path(temp.name).resolve()
        self.content = self.root / "content-canary"
        self.content.mkdir()
        self.templates = self.root / "templates-canary"
        self.store = {
            "name": STORE, "streetAddress": ADDRESS, "town": "Testville",
            "hours": ["Monday-Friday 9am-5pm", "Closed Saturday-Sunday"],
        }
        self.write_content("store", self.store)
        self.write_content("products", {"products": [{
            "id": "fixture-fruit", "name": PRODUCT, "brand": "Fixture Farm",
            "displayBrand": "Fixture Farm", "category": "fruit",
            "image": "assets/products/fixture-fruit.webp", "description": "Sample fruit.",
            "producerKey": "fixture-farm", "status": "active",
        }]})
        self.write_content("makers", {"makers": {"fixture-farm": {
            "name": "Fixture Farm", "place": "Testville, California", "story": "Sample maker.",
        }}})
        self.write_content("community", {
            "club": {"clubName": "Fixture Club", "organizer": "Fixture Organizer",
                     "intendedSender": "Fixture Sender", "emailConnected": False},
            "events": [], "routeIdeas": [],
        })

    def write_content(self, name, payload):
        (self.content / f"{name}.json").write_text(
            json.dumps({"schemaVersion": 1, **payload}), encoding="utf-8",
        )

    def copy_templates(self):
        shutil.copytree(TEMPLATES, self.templates)

    def change_template(self, name, old, new):
        path = self.templates / name
        text = path.read_text(encoding="utf-8")
        self.assertIn(old, text)
        path.write_text(text.replace(old, new, 1), encoding="utf-8")

    def args(self):
        return ["--content", str(self.content), "--templates", str(self.templates), "--today", TODAY]

    def cli(self, *args):
        result = subprocess.run([sys.executable, "-B", str(SCRIPT), *args], cwd=self.root,
                                capture_output=True, text=True, timeout=10)
        return result.returncode, result.stdout, result.stderr

    def run_check(self, args=None):
        out, err = io.StringIO(), io.StringIO()
        with redirect_stdout(out), redirect_stderr(err):
            code = CHECK.main(self.args() if args is None else args)
        return code, out.getvalue(), err.getvalue()

    def assert_report(self, result, code, lines, last):
        actual_code, out, err = result
        self.assertEqual(actual_code, code)
        self.assertEqual(err, "")
        self.assertEqual(out.splitlines(), [*lines, last])

    def assert_rendered_home_contains(self, fragment):
        content = content_model.load_and_validate(self.content, None)
        files = sitegen.render(content, self.templates, today=date.fromisoformat(TODAY))
        self.assertIn(fragment, files["storefront-mockup/index.html"])

    def test_c1_full_pass(self):
        # Without a working standalone import or template default this fails outside the checkout.
        self.assert_report(self.cli("--content", str(self.content)), 0, BASE_REPORT, PASS)

    def test_c2_1_unsafe_input(self):
        # is_dir() alone follows links; checking only existence admits regular files.
        self.copy_templates()
        regular_file = self.content / "store.json"
        missing = self.root / "missing"
        for index, target in ((1, self.content), (3, self.templates)):
            alias = self.root / (target.name + "-link")
            alias.symlink_to(target, target_is_directory=True)
            for path in (alias, regular_file, missing):
                with self.subTest(option_index=index, kind=path.name):
                    args = self.args()
                    args[index] = str(path)
                    self.assert_report(self.run_check(args), 1, ["FAIL unsafe-input"], FAIL)

    def test_c2_2_content_invalid(self):
        # A schema or decoding failure must not reach rendering or expose the loader's diagnostic.
        self.copy_templates()
        for raw in (b'{"schemaVersion":2}', b"\xff"):
            with self.subTest(raw=raw):
                (self.content / "products.json").write_bytes(raw)
                self.assert_report(self.run_check(), 1, ["FAIL content-invalid"], FAIL)

    def test_c2_3_render_failed(self):
        # Unknown slots and unreadable templates fail at render, not as invalid content or tracebacks.
        self.copy_templates()
        self.change_template("index.html", "</head>", "{{fixtureUnknownSlot}}</head>")
        self.assert_report(self.run_check(), 1, ["FAIL render-failed"], FAIL)
        path = self.templates / "index.html"
        path.write_bytes(b"\xff")
        self.assert_report(self.run_check(), 1, ["FAIL render-failed"], FAIL)
        path.rename(self.templates / "unread-template.html")
        self.assert_report(self.run_check(), 1, ["FAIL render-failed"], FAIL)

    def test_c2_4_inline_style(self):
        # Count both forms, including markup seen before the CSP meta and across pages.
        self.copy_templates()
        self.change_template("index.html", "<head>", '<head><style media="screen">p {color: inherit}</style>')
        self.change_template("index.html", 'http-equiv="Content-Security-Policy"',
                             'HTTP-EQUIV="content-security-policy"')
        self.change_template("hike/index.html", "</body>", '<p STYLE="color: inherit">Sample</p></body>')
        self.assert_report(self.run_check(), 1, BASE_REPORT + [
            "FAIL inline-style 2", "page hike/index.html inline-style 1", "page index.html inline-style 1",
        ], FAIL)

    def test_c2_5_inline_handler(self):
        # Matching only onclick, or matching data-on* as well, returns the wrong count.
        self.copy_templates()
        self.change_template("index.html", "</body>",
                             '<button ONCLICK="" onfocus data-onclick="">Sample</button></body>')
        self.assert_report(self.run_check(), 1, BASE_REPORT + [
            "FAIL inline-handler 2", "page index.html inline-handler 2",
        ], FAIL)

    def test_c2_6_inline_script(self):
        # Exempt only the exact JSON-LD type, not every typed script or a case variant.
        self.copy_templates()
        self.change_template("index.html", "</body>", '<script></script><script type="Application/ld+json">'
                             '{}</script></body>')
        self.assert_report(self.run_check(), 1, BASE_REPORT + [
            "FAIL inline-script 2", "page index.html inline-script 2",
        ], FAIL)

    def test_c2_7_script_url(self):
        # Scope includes non-CSP pages, entity-decoded URLs and all three named attributes.
        self.copy_templates()
        self.change_template("info/index.html", "</body>",
                             '<a HREF="&#32;JaVaScRiPt:">Sample</a><form action=" javascript:"></form></body>')
        self.change_template("hike/index.html", "</body>",
                             '<script SRC="javascript:"></script><a href="#javascript:">Sample</a></body>')
        urls = [
            "FAIL script-url 9", "page about/index.html script-url 2", "page faq/index.html script-url 2",
            "page getting-here/index.html script-url 2", "page hike/index.html script-url 1",
            "page policies/index.html script-url 2",
        ]
        self.assert_report(self.run_check(), 1, BASE_REPORT + urls, FAIL)

        # A finding must not short-circuit later checks; kind order is stable.
        self.change_template("index.html", "</body>",
                             '<script></script><p onclick="" style=""></p></body>')
        self.assert_report(self.run_check(), 1, BASE_REPORT + [
            "FAIL inline-style 1", "page index.html inline-style 1",
            "FAIL inline-handler 1", "page index.html inline-handler 1",
            "FAIL inline-script 1", "page index.html inline-script 1",
        ] + urls, FAIL)

    def test_c3_usage_exit_2(self):
        # Do not collapse argparse usage errors into the tool's finding status.
        for args in ([], ["--content", str(self.content), "--not-a-flag"],
                     ["--content", str(self.content), "--today", "2026-02-30"]):
            with self.subTest(args=args):
                code, out, err = self.cli(*args)
                self.assertEqual(code, 2)
                self.assertEqual(out, "")  # No final stdout line on usage errors.
                self.assertIn("usage:", err)

    def test_c4_read_only(self):
        # Snapshot membership, bytes and mtimes to catch in-place rewrites and extra output files.
        self.copy_templates()

        def snapshot():
            return {p.relative_to(self.root): (p.stat().st_mtime_ns, p.read_bytes() if p.is_file() else None)
                    for root in (self.content, self.templates) for p in (root, *root.rglob("*"))}

        before = snapshot()
        self.assert_report(self.run_check(), 0, BASE_REPORT, PASS)
        self.assertEqual(snapshot(), before)

    def test_c5_no_private_values(self):
        # Never print source data, offending HTML, filesystem paths or renderer diagnostics.
        self.copy_templates()
        self.change_template("index.html", "</body>", f'<p style="{PRODUCT}"></p></body>')
        finding = self.run_check()
        self.change_template("index.html", "</body>", "{{fixtureUnknownSlot}}</body>")
        render_error = self.run_check()
        self.write_content("store", {**self.store, "hours": []})
        content_error = self.run_check()
        for result in (finding, render_error, content_error):
            output = result[1] + result[2]
            for value in (PRODUCT, STORE, ADDRESS, str(self.content), str(self.templates), "fixtureUnknownSlot"):
                self.assertFalse(value in output, "private input leaked into CLI output")
        self.assert_report(finding, 1, BASE_REPORT + ["FAIL inline-style 1", "page index.html inline-style 1"], FAIL)
        self.assert_report(render_error, 1, ["FAIL render-failed"], FAIL)
        self.assert_report(content_error, 1, ["FAIL content-invalid"], FAIL)

    def test_c6_jsonld_allowed(self):
        # A blanket ban on src-less scripts would flag real structured data on the home page.
        self.copy_templates()
        self.assert_rendered_home_contains(b'<script type="application/ld+json">')
        self.assert_report(self.run_check(), 0, BASE_REPORT, PASS)

    def test_c7_no_csp_informational(self):
        # Non-CSP styles contribute to the note only; a commented meta cannot activate it.
        self.copy_templates()
        self.change_template("info/index.html", "</head>", '<!-- <meta http-equiv="Content-Security-Policy"> -->'
                             '<style>p {color: inherit}</style></head>')
        self.change_template("info/index.html", "</body>", '<p style="" onclick=""></p><script></script></body>')
        self.assert_report(self.run_check(), 0, BASE_REPORT[:-1] + ["note inline-style-no-csp 12"], PASS)

    def test_c8_src_script_allowed(self):
        # Counting every script, even with src, breaks the real banner configuration.
        self.copy_templates()
        self.write_content("store", {**self.store, "banner": {"text": "Fixture banner", "start": TODAY, "end": TODAY}})
        self.assert_rendered_home_contains(b'<script src="/banner.js"></script>')
        self.assert_report(self.run_check(), 0, BASE_REPORT, PASS)


if __name__ == "__main__":
    unittest.main()
