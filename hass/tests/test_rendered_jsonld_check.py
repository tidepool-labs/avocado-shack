"""Exercise the offline checker against disposable content and real templates."""

from contextlib import redirect_stderr, redirect_stdout
import importlib.util
from io import StringIO
import json
from pathlib import Path
import shutil
import subprocess
import sys
from tempfile import TemporaryDirectory
import unittest


ROOT = Path(__file__).resolve().parents[2]
SCRIPT = ROOT / "scripts/hass/rendered_jsonld_check.py"
SPEC = importlib.util.spec_from_file_location("rendered_jsonld_check", SCRIPT)
assert SPEC is not None and SPEC.loader is not None
CHECK = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(CHECK)

SLOT = '<script type="application/ld+json">{{store.jsonLd}}</script>'
PASS = "PASS rendered_jsonld_check"
FAIL = "FAIL rendered_jsonld_check"
STORE = {
    "name": "Canary Orchard Shop",
    "streetAddress": "Canary Orchard Lane",
    "town": "Canary Testville",
    "hours": ["Monday-Friday 9am-5pm", "Closed Saturday-Sunday"],
}
PRODUCT = "Canary Test Plum"


def _script(text):
    return f'<script type="application/ld+json">{text}</script>'


class RenderedJsonLdCheckTests(unittest.TestCase):
    def setUp(self):
        temporary = TemporaryDirectory()
        self.addCleanup(temporary.cleanup)
        self.root = Path(temporary.name).resolve()
        self.content = self.root / "fixture-content"
        self.content.mkdir()
        self.templates = self.root / "fixture-templates"
        self.write_content("store", STORE)
        self.write_content("makers", {"makers": {"fixture-maker": {
            "name": "Fixture Maker", "place": "Testville, California", "story": "A fixture orchard.",
        }}})
        self.write_content("products", {"products": [{
            "id": "fixture-plum", "name": PRODUCT, "brand": "Fixture Maker", "displayBrand": "Fixture Maker",
            "producerKey": "fixture-maker", "category": "fruit", "image": "assets/products/fixture-plum.webp",
            "description": "A fixture plum.", "status": "active",
        }]})
        self.write_content("community", {"club": {
            "clubName": "Fixture Club", "organizer": "Fixture Organizer",
            "intendedSender": "fixture@example.com", "emailConnected": False,
        }, "events": [], "routeIdeas": []})

    def write_content(self, name, data):
        (self.content / f"{name}.json").write_text(json.dumps({"schemaVersion": 1, **data}), encoding="utf-8")

    def copy_templates(self):
        if not self.templates.exists():
            shutil.copytree(ROOT / "hass/templates", self.templates)
        return self.templates / "index.html"

    def replace_slot(self, replacement):
        home = self.copy_templates()
        original = (ROOT / "hass/templates/index.html").read_text(encoding="utf-8")
        self.assertEqual(original.count(SLOT), 1)
        home.write_text(original.replace(SLOT, replacement), encoding="utf-8")

    def replace_block(self, block):
        self.replace_slot(_script(json.dumps(block, indent=2)))

    def args(self):
        args = ["--content", str(self.content), "--today", "2026-11-20"]
        if self.templates.exists():
            args.extend(["--templates", str(self.templates)])
        return args

    def invoke(self, args=None):
        stdout, stderr = StringIO(), StringIO()
        with redirect_stdout(stdout), redirect_stderr(stderr):
            try:
                code = CHECK.main(self.args() if args is None else args)
            except SystemExit as exc:
                code = exc.code
        return code, stdout.getvalue(), stderr.getvalue()

    def cli(self, args):
        # Calling from outside the checkout proves repo-relative imports and defaults.
        result = subprocess.run([sys.executable, "-B", str(SCRIPT), *args], cwd=self.root,
                                capture_output=True, text=True, timeout=10)
        return result.returncode, result.stdout, result.stderr

    def assert_report(self, result, *lines, exit_code=0):
        code, stdout, stderr = result
        self.assertEqual(code, exit_code, stdout + stderr)
        self.assertEqual(stdout.splitlines(), list(lines))  # Includes the exact final line and any reason.
        self.assertEqual(stderr, "")

    def test_c1_full_pass(self):
        # Catch a broken script entry point or resolution of default templates relative to cwd.
        self.assert_report(self.cli(["--content", str(self.content)]), "jsonld 1", PASS)

    def test_c2_1_unsafe_input(self):
        # A directory test alone would follow a valid directory symlink.
        self.copy_templates()
        plain = self.root / "plain-file"
        plain.touch()
        for flag, directory in (("--content", self.content), ("--templates", self.templates)):
            alias = directory.with_name(directory.name + "-link")
            alias.symlink_to(directory, target_is_directory=True)
            for path in (alias, plain, self.root / "absent"):
                with self.subTest(flag=flag, kind=path.name):
                    args = self.args()
                    args[args.index(flag) + 1] = str(path)
                    self.assert_report(self.invoke(args), "FAIL unsafe-input", FAIL, exit_code=1)

    def test_c2_2_content_invalid(self):
        # Bypassing the validator would accept the wrong schema version.
        path = self.content / "store.json"
        for raw in (json.dumps({**STORE, "schemaVersion": 2}).encode(), b"{", b"\xff"):
            path.write_bytes(raw)
            with self.subTest(raw=raw[:1]):
                self.assert_report(self.invoke(), "FAIL content-invalid", FAIL, exit_code=1)

    def test_c2_3_render_failed(self):
        # The directory exists, but render can fail on a slot, undecodable bytes, or missing file.
        home = self.copy_templates()
        for data in (b"{{fixture.unknownSlot}}", b"\xff"):
            home.write_bytes(data)
            self.assert_report(self.invoke(), "FAIL render-failed", FAIL, exit_code=1)
        home.rename(home.with_suffix(".unused"))
        self.assert_report(self.invoke(), "FAIL render-failed", FAIL, exit_code=1)

    def test_c2_4_jsonld_missing(self):
        # Comments, near-match types, and a valid block on another page are not home JSON-LD.
        self.replace_slot(f'<!--{SLOT}--><script type="Application/ld+json">{{}}</script>')
        hike = self.templates / "hike/index.html"
        with hike.open("a", encoding="utf-8") as output:
            output.write(SLOT)
        self.assert_report(self.invoke(), "jsonld 0", "FAIL jsonld-missing", FAIL, exit_code=1)

    def test_c2_5_jsonld_duplicate(self):
        # Reading only the first block or requiring one attribute spelling would miss the duplicate.
        self.replace_slot(SLOT + "<SCRIPT id='second' TYPE='application/ld+json'>\n{}\n</SCRIPT>")
        self.assert_report(self.invoke(), "jsonld 2", "FAIL jsonld-duplicate 2", FAIL, exit_code=1)

    def test_c2_6_jsonld_invalid(self):
        # Valid JSON arrays and nonstandard constants cannot certify an object.
        for text in ("{", "[]", '{"extra": NaN}'):
            with self.subTest(text=text):
                self.replace_slot(_script(text))
                self.assert_report(self.invoke(), "jsonld 1", "FAIL jsonld-invalid", FAIL, exit_code=1)

    def test_c2_7_jsonld_mismatch(self):
        # A well-formed hard-coded block can drift in every field; null isn't absent.
        block = {"@type": "Store", "name": "Stale fixture name", "address": {
            "streetAddress": "Stale fixture street", "addressLocality": "Stale fixture town",
        }, "telephone": None, "openingHoursSpecification": []}
        self.replace_block(block)
        self.assert_report(self.invoke(), "jsonld 1", "mismatch type", "mismatch name", "mismatch street",
                           "mismatch town", "mismatch telephone", "mismatch hours", "FAIL jsonld-mismatch 6",
                           FAIL, exit_code=1)

    def test_c3_usage_exit_2(self):
        # Usage mistakes aren't findings or tracebacks; stdout must be entirely empty.
        for args in ([], self.args() + ["--unknown"], self.args() + ["--today", "2026-02-30"]):
            with self.subTest(args=args):
                code, stdout, stderr = self.invoke(args)
                self.assertEqual((code, stdout), (2, ""))
                self.assertIn("usage:", stderr)

    def test_c4_read_only(self):
        # Catch generated files, rewrites of identical bytes, and transient directory entries.
        self.copy_templates()

        def snapshot():
            return {path: (path.stat().st_mtime_ns, path.read_bytes() if path.is_file() else None)
                    for root in (self.content, self.templates) for path in (root, *root.rglob("*"))}

        before = snapshot()
        self.assert_report(self.cli(self.args()), "jsonld 1", PASS)
        self.assertEqual(snapshot(), before)

    def test_c5_no_private_values(self):
        # Raw HTML, JSON, loader/render exceptions, and argparse error detail can all leak input.
        def scan(result):
            for marker in (STORE["name"], STORE["streetAddress"], STORE["town"], PRODUCT,
                           str(self.content), str(self.templates)):
                self.assertNotIn(marker, result[1] + result[2])

        self.copy_templates()
        result = self.invoke()
        scan(result)
        self.assert_report(result, "jsonld 1", PASS)
        private_address = {"name": STORE["name"], "addressLocality": STORE["town"],
                           "streetAddress": STORE["streetAddress"], "extra": PRODUCT}
        self.replace_block(private_address)
        result = self.invoke()
        scan(result)
        self.assert_report(result, "jsonld 1", "mismatch type", "mismatch street", "mismatch town",
                           "mismatch hours", "FAIL jsonld-mismatch 4", FAIL, exit_code=1)
        (self.templates / "index.html").rename(self.templates / "index.unused")
        result = self.invoke()
        scan(result)
        self.assert_report(result, "FAIL render-failed", FAIL, exit_code=1)
        self.write_content("store", {**STORE, PRODUCT: True})
        result = self.invoke()
        scan(result)
        self.assert_report(result, "FAIL content-invalid", FAIL, exit_code=1)
        result = self.invoke(self.args() + ["--unknown", str(self.content)])
        scan(result)
        self.assertEqual(result[:2], (2, ""))

    def test_c6_escaped_name(self):
        # Comparing encoded script text instead of JSON values would lose the ampersand.
        self.write_content("store", {**STORE, "name": "Fixture’s Fruit & Greens"})
        self.assert_report(self.invoke(), "jsonld 1", PASS)

    def test_c7_unreadable_hours_ok(self):
        # Unreadable and all-closed weeks both omit the key, but only unreadable gets a note.
        self.write_content("store", {**STORE, "hours": ["Mon 9-5"]})
        self.assert_report(self.invoke(), "jsonld 1", "note hours-unreadable", PASS)
        self.write_content("store", {**STORE, "hours": ["Closed Monday-Sunday"]})
        self.assert_report(self.invoke(), "jsonld 1", PASS)
        block = {"@type": "GroceryStore", "name": STORE["name"], "address": {
            "streetAddress": STORE["streetAddress"], "addressLocality": STORE["town"],
        }, "openingHoursSpecification": []}
        self.replace_block(block)
        self.assert_report(self.invoke(), "jsonld 1", "mismatch hours", "FAIL jsonld-mismatch 1", FAIL, exit_code=1)

    def test_c8_telephone_checked(self):
        # A presence-only comparator would also accept unformatted digits.
        self.write_content("store", {**STORE, "phone": "8055550100"})
        self.assert_report(self.invoke(), "jsonld 1", PASS)
        block = {"@type": "GroceryStore", "name": STORE["name"], "address": {
            "streetAddress": STORE["streetAddress"], "addressLocality": STORE["town"],
        }, "openingHoursSpecification": [{}] * 5}
        self.replace_block({**block, "telephone": "+1-805-555-0100"})
        self.assert_report(self.invoke(), "jsonld 1", PASS)
        for telephone in ({}, {"telephone": "8055550100"}):
            with self.subTest(telephone=telephone):
                self.replace_block({**block, **telephone})
                self.assert_report(self.invoke(), "jsonld 1", "mismatch telephone", "FAIL jsonld-mismatch 1",
                                   FAIL, exit_code=1)


if __name__ == "__main__":
    unittest.main()
