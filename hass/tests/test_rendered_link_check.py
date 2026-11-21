"""Offline CLI contract tests using synthetic content and site files."""

from contextlib import redirect_stderr, redirect_stdout
import importlib.util
import io
import json
from pathlib import Path
import shutil
import subprocess
import sys
from tempfile import TemporaryDirectory
import unittest


ROOT = Path(__file__).resolve().parents[2]
SCRIPT = ROOT / "scripts/hass/rendered_link_check.py"
SPEC = importlib.util.spec_from_file_location("rendered_link_check", SCRIPT)
assert SPEC is not None and SPEC.loader is not None
CHECK = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(CHECK)
PASS = "PASS rendered_link_check"
FAIL = "FAIL rendered_link_check"
PRODUCT = "Canary Orchard Fruit"
STORE = "Canary Corner Market"
ADDRESS = "Example Lane Address Canary"


class RenderedLinkCheckTests(unittest.TestCase):
    def setUp(self):
        temporary = TemporaryDirectory()
        self.addCleanup(temporary.cleanup)
        self.root = Path(temporary.name).resolve()
        self.content = self.root / "content-canary"
        self.site = self.root / "site-canary"
        self.templates = self.root / "templates-canary"
        self.content.mkdir()
        self.site.mkdir()
        shutil.copytree(ROOT / "hass/templates", self.templates)
        self.products = {"products": [{
            "id": "test-fruit", "name": PRODUCT, "brand": "Example Orchard",
            "displayBrand": "Example Orchard", "category": "fruit",
            "image": "assets/products/test-fruit.webp", "description": "A crisp fruit.",
            "status": "active", "producerKey": "example-orchard",
        }]}
        self.write_content("products", self.products)
        self.write_content("makers", {"makers": {"example-orchard": {
            "name": "Example Orchard", "place": "Testville, California", "story": "A small orchard.",
        }}})
        self.write_content("store", {
            "name": STORE, "streetAddress": ADDRESS, "town": "Testville, California",
            "hours": ["Monday-Friday 9am-5pm", "Closed Saturday-Sunday"],
        })
        self.write_content("community", {
            "club": {"clubName": "Example Walking Club", "organizer": "Example Guide",
                     "intendedSender": "walks@example.invalid", "emailConnected": False},
            "events": [], "routeIdeas": [],
        })
        # No generated files or product pictures are present in the site fixture.
        for path in (
            "assets/favicon.png", "assets/logo-header.png", "assets/store.jpg", "assets/michael.jpg",
            "style.css", "hiking.css", "trail-explorer.css", "script.js", "shop.js", "community.js",
            "trail-explorer.js",
        ):
            target = self.site / path
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_bytes(b"fixture")

    def write_content(self, name, fields):
        (self.content / f"{name}.json").write_text(json.dumps({"schemaVersion": 1, **fields}), encoding="utf-8")

    def plant(self, page, markup):
        template = self.templates / page
        text = template.read_text(encoding="utf-8")
        self.assertIn("</body>", text)
        template.write_text(text.replace("</body>", markup + "\n</body>"), encoding="utf-8")

    def args(self, **overrides):
        options = {"content": self.content, "site": self.site, "templates": self.templates, "today": "2026-01-05"}
        options.update(overrides)
        return [part for key, value in options.items() if value is not None for part in (f"--{key}", str(value))]

    def invoke(self, argv=None):
        stdout, stderr = io.StringIO(), io.StringIO()
        with redirect_stdout(stdout), redirect_stderr(stderr):
            try:
                code = CHECK.main(self.args() if argv is None else argv)
            except SystemExit as error:
                code = error.code
        return code, stdout.getvalue().splitlines(), stderr.getvalue()

    def assert_pass(self, result):
        code, lines, stderr = result
        self.assertEqual((code, lines[-1:], stderr), (0, [PASS], ""), lines)
        self.assertFalse(any(line.startswith(("FAIL ", "broken ", "note unprintable ")) for line in lines))
        return lines

    def assert_failure(self, result, reason):
        code, lines, stderr = result
        self.assertEqual((code, lines[-1:], stderr), (1, [FAIL], ""), lines)
        self.assertEqual([line for line in lines[:-1] if line.startswith("FAIL ")], [f"FAIL {reason}"])
        return lines

    def test_c1_full_pass(self):
        # The direct CLI must work outside the repo, with default templates/date
        # and even though generated JS and browser-added product pictures are absent on disk.
        result = subprocess.run(
            [sys.executable, "-B", str(SCRIPT), *self.args(templates=None, today=None)],
            cwd=self.root, capture_output=True, text=True, timeout=10,
        )
        lines = self.assert_pass((result.returncode, result.stdout.splitlines(), result.stderr))
        self.assertEqual(lines[0], "pages 6")
        self.assertRegex(lines[1], r"^links [1-9][0-9]*$")
        self.assertRegex(lines[2], r"^skipped [1-9][0-9]*$")
        self.assertEqual(len(lines), 4)

    def test_c2_1_unsafe_input(self):
        # is_dir alone accepts aliases to real directories; a file or missing root is also unsafe.
        for option in ("content", "site", "templates"):
            alias = self.root / f"alias-{option}"
            alias.symlink_to(getattr(self, option), target_is_directory=True)
            for path in (alias, self.content / "store.json", self.root / "absent"):
                with self.subTest(option=option, path=path.name):
                    self.assertEqual(self.assert_failure(self.invoke(self.args(**{option: path})), "unsafe-input"),
                                     ["FAIL unsafe-input", FAIL])

    def test_c2_2_content_invalid(self):
        # Neither an invalid schema nor unreadable UTF-8 may reach render.
        for raw in (b'{"schemaVersion":0}', b'\xff'):
            with self.subTest(raw=raw):
                (self.content / "products.json").write_bytes(raw)
                self.assertEqual(self.assert_failure(self.invoke(), "content-invalid"),
                                 ["FAIL content-invalid", FAIL])

    def test_c2_3_render_failed(self):
        # Unknown slots and missing template files must become the same safe diagnostic.
        self.plant("index.html", "{{unknownSlot}}")
        self.assertEqual(self.assert_failure(self.invoke(), "render-failed"), ["FAIL render-failed", FAIL])
        missing_template = self.root / "incomplete"
        missing_template.mkdir()
        self.assertEqual(self.assert_failure(self.invoke(self.args(templates=missing_template)), "render-failed"),
                         ["FAIL render-failed", FAIL])

    def test_c2_4_broken_link(self):
        # Check mixed tags, normalized duplicates, cross-page uniqueness, traversal,
        # character references, and suppressed (but still counted) targets.
        baseline = self.assert_pass(self.invoke())
        self.plant("index.html", '<img src="/zebra.png?x#y"/><a href="./zebra.png#z"></a>'
                   '<link href="/alpha.css"><img src="/odd&#32;name.png">'
                   '<a href="/' + 'x' * 122 + '"></a><img src="/../style.css">')
        (self.site / "hike").mkdir()
        (self.site / "hike/local.png").write_bytes(b"fixture")
        self.plant("hike/index.html", '<img src="../zebra.png"><img src="local.png?x">'
                   '<a href="?current-page"></a><img src="dir/../loc&#97;l.png">')
        lines = self.assert_failure(self.invoke(), "broken-link 6")
        self.assertEqual(lines[:3], [baseline[0], f"links {int(baseline[1].split()[1]) + 10}", baseline[2]])
        self.assertEqual(lines[3:], [
            "broken hike/index.html /zebra.png", "broken index.html /alpha.css", "broken index.html /zebra.png",
            "note unprintable 3", "FAIL broken-link 6", FAIL,
        ])

    def test_c3_usage_exit_2(self):
        # Usage errors are not findings and cannot leak offending argument values.
        for argv in (self.args(content=None), self.args(site=None), self.args() + ["--unknown"],
                     self.args(today="2026-02-30")):
            with self.subTest(argv_length=len(argv)):
                code, lines, stderr = self.invoke(argv)
                self.assertEqual((code, lines), (2, []))  # No last stdout line.
                self.assertTrue(stderr.startswith("usage: "))

    def test_c4_read_only(self):
        # Publishing or caching outputs, or rewriting identical input bytes, changes this snapshot.
        def snapshot():
            return {
                path.relative_to(self.root): (path.stat().st_mtime_ns, path.read_bytes() if path.is_file() else None)
                for directory in (self.content, self.site, self.templates)
                for path in (directory, *directory.rglob("*"))
            }

        before = snapshot()
        self.assert_pass(self.invoke())
        self.assertEqual(snapshot(), before)

    def test_c5_no_private_values(self):
        # Do not dump rendered HTML, detail from validation/render errors, or raw argv.
        results = [self.invoke()]
        self.assert_pass(results[-1])
        self.plant("index.html", f'<a href="/missing?query={PRODUCT}#{STORE}"></a>'
                   f'<img src="/{ADDRESS}">')
        results.append(self.invoke())
        self.assert_failure(results[-1], "broken-link 2")
        self.plant("index.html", "{{PrivateTemplateCanary}}")
        results.append(self.invoke())
        self.assert_failure(results[-1], "render-failed")
        self.products["products"][0]["producerKey"] = PRODUCT
        self.write_content("products", self.products)
        results.append(self.invoke())
        self.assert_failure(results[-1], "content-invalid")
        results.append(self.invoke(self.args(today=self.content)))
        self.assertEqual(results[-1][:2], (2, []))
        results.append(self.invoke(self.args() + [str(self.templates)]))
        self.assertEqual(results[-1][:2], (2, []))
        for _, lines, stderr in results:
            for marker in (PRODUCT, STORE, ADDRESS, "PrivateTemplateCanary", str(self.content), str(self.site),
                           str(self.templates)):
                self.assertFalse(marker in "\n".join(lines) + stderr, "private marker leaked")

    def test_c6_index_pages_found(self):
        # Root and directory routes must match render keys, not disk index files.
        baseline = self.assert_pass(self.invoke())
        self.plant("hike/index.html", '<a href="/">Home</a><a href="/hike">Hike</a>')
        lines = self.assert_pass(self.invoke())
        self.assertEqual(lines[1], f"links {int(baseline[1].split()[1]) + 2}")
        self.assertFalse((self.site / "index.html").exists())
        self.assertFalse((self.site / "hike").exists())

    def test_c7_symlinked_target_broken(self):
        # A symlinked intermediate component and a symlinked leaf both look like
        # regular files to stat() but neither is an allowed target.
        (self.site / "nested").mkdir()
        external = self.root / "external"
        external.mkdir()
        (external / "leaf.png").write_bytes(b"fixture")
        (self.site / "nested/alias").symlink_to(external, target_is_directory=True)
        (self.site / "alias.png").symlink_to(external / "leaf.png")
        self.plant("index.html", '<img src="/nested/alias/leaf.png"><img src="/alias.png">')
        self.assertEqual(self.assert_failure(self.invoke(), "broken-link 2")[3:], [
            "broken index.html /alias.png", "broken index.html /nested/alias/leaf.png", "FAIL broken-link 2", FAIL,
        ])

    def test_c8_skipped_values(self):
        # A checker that ignores only HTTPS would misclassify the other references.
        baseline = self.assert_pass(self.invoke())
        self.plant("index.html", '<a href="mailto:walks@example.invalid"></a>'
                   '<a href="https://example.invalid/path"></a><a href="#top"></a>'
                   '<img src="//example.invalid/leaf.png"><img src="TeSt+v1.0-scheme:leaf.png">')
        lines = self.assert_pass(self.invoke())
        self.assertEqual(lines[:2], baseline[:2])
        self.assertEqual(lines[2], f"skipped {int(baseline[2].split()[1]) + 5}")


if __name__ == "__main__":
    unittest.main()
