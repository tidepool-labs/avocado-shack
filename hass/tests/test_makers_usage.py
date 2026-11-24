"""Contract tests for the offline maker usage report, using catalog copies."""

from contextlib import redirect_stderr, redirect_stdout
import importlib.util
from io import StringIO
import json
from pathlib import Path
import subprocess
import sys
from tempfile import TemporaryDirectory
import unittest

from hass.claims import PLACEHOLDER


SCRIPT = Path(__file__).resolve().parents[2] / "scripts/hass/makers_usage.py"
SPEC = importlib.util.spec_from_file_location("makers_usage", SCRIPT)
assert SPEC is not None and SPEC.loader is not None
REPORT = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(REPORT)


def product(product_id, key=None, *, status="active", brand="Fixture Brand", **fields):
    return dict(id=product_id, producerKey=key, status=status, brand=brand, **fields)


class MakersUsageTests(unittest.TestCase):
    def setUp(self):
        temporary = TemporaryDirectory()
        self.addCleanup(temporary.cleanup)
        self.root = Path(temporary.name).resolve()
        self.content = self.root / "catalog-copy"
        self.content.mkdir()

    def write(self, *, products=(), makers=None):
        for filename, fields in {
            "products.json": {"products": list(products)},
            "makers.json": {"makers": makers or {}},
            "community.json": {},
            "store.json": {},
        }.items():
            (self.content / filename).write_text(
                json.dumps({"schemaVersion": 1, **fields}), encoding="utf-8",
            )

    def invoke(self, *args):
        stdout, stderr = StringIO(), StringIO()
        with redirect_stdout(stdout), redirect_stderr(stderr):
            try:
                code = REPORT.main(list(args))
            except SystemExit as exc:
                code = exc.code
        return code, stdout.getvalue().splitlines(), stderr.getvalue()

    def run_report(self, path=None):
        return self.invoke("--content", str(self.content if path is None else path))

    def assert_pass(self, result):
        code, lines, err = result
        self.assertEqual(code, 0)
        self.assertEqual(lines[-1], "PASS makers_usage")
        self.assertEqual(err, "")
        self.assertFalse(any(line.startswith("FAIL ") for line in lines))
        return lines

    def assert_findings(self, result, *findings):
        code, lines, err = result
        self.assertEqual(code, 1)
        self.assertEqual(lines[-1], "FAIL makers_usage")
        self.assertEqual(err, "")
        self.assertEqual([line for line in lines[:-1] if line.startswith("FAIL ")], list(findings))
        return lines

    def test_c1_full_pass(self):
        # Conflating held and hidden usage, counting listings rather than unique
        # makers without a URL, or omitting normalization breaks this report.
        self.write(makers={
            "z-unused": {"name": "Unused"},
            "active": {"name": "  Straße Maker "},
            "only-hidden-use": {"name": "Hidden Use"},
            "a-held": {"name": "Held Use"},
            "placeholder": {"name": PLACEHOLDER},
            "malformed": None,
        }, products=[
            product("active-a", "active"), product("active-b", "active"),
            product("hidden-a", "only-hidden-use", status="hidden"),
            product("held-a", "a-held", status="held"),
            product("held-b", "active", status="held"),
            product("held-c", "only-hidden-use", status="held"),
            product("held-d", "missing", status="held"),
            product("z-unlinked", brand=" STRASSE MAKER  "),
            product("a-unlinked", brand="straße maker"),
            product("hidden-unlinked", status="hidden", brand="straße maker"),
            product("placeholder-product", brand=PLACEHOLDER),
            "malformed product", [],
        ])
        self.assertEqual(self.assert_pass(self.run_report()), [
            "makers 5", "hidden-makers 0", "active-products 5", "linked 2",
            "note unused-maker 3", "unused a-held", "unused placeholder", "unused z-unused",
            "note held-only-maker 1", "note no-url 1",
            "note unlinked-brand 2", "unlinked a-unlinked", "unlinked z-unlinked",
            "note malformed 3", "PASS makers_usage",
        ])

    def test_c2_1_unsafe_input(self):
        # A symlink to otherwise valid content must be rejected before loading.
        self.write()
        alias = self.root / "alias"
        alias.symlink_to(self.content, target_is_directory=True)
        for path in (alias, self.content / "store.json", self.root / "absent"):
            with self.subTest(input_kind=path.name):
                lines = self.assert_findings(self.run_report(path), "FAIL unsafe-input")
                self.assertEqual(lines, ["FAIL unsafe-input", "FAIL makers_usage"])

    def test_c2_2_content_invalid(self):
        # The real loader must read the ancillary files and hide decode diagnostics.
        for raw in (b'{"schemaVersion": 2}', b'{', b'\xff'):
            with self.subTest(raw=raw):
                self.write()
                (self.content / "community.json").write_bytes(raw)
                lines = self.assert_findings(self.run_report(), "FAIL content-invalid")
                self.assertEqual(lines, ["FAIL content-invalid", "FAIL makers_usage"])

    def test_c2_3_unknown_maker(self):
        # Count product rows, not keys, and include hidden but not held products.
        self.write(products=[product("first", "missing"), product("second", "missing"),
                             product("third", "missing", status="hidden"),
                             product("fourth", "missing", status="held")])
        lines = self.assert_findings(self.run_report(), "FAIL unknown-maker 3")
        self.assertIn("linked 2", lines)

    def test_c2_4_active_on_hidden_maker(self):
        # Held/hidden links are not visibility findings; active links are, per row.
        makers = {"retired": {"hidden": True}}
        products = [
            product("first", "retired"), product("second", "retired"),
            product("third", "retired", status="hidden"),
            product("fourth", "retired", status="held"),
        ]
        self.write(makers=makers, products=products)
        lines = self.assert_findings(self.run_report(), "FAIL active-on-hidden-maker 2")
        self.assertIn("hidden-makers 1", lines)
        self.assertIn("note unused-maker 0", lines)
        self.assertNotIn("retired", "\n".join(lines))
        self.write(makers=makers, products=[*products, product("fifth", "missing")])
        self.assert_findings(self.run_report(), "FAIL unknown-maker 1",
                             "FAIL active-on-hidden-maker 2")

    def test_c3_usage_exit_2(self):
        # Parser errors must not be converted to report findings or success.
        for args in ((), ("--content", str(self.content), "--bogus"), ("--content",)):
            with self.subTest(args=args):
                code, lines, err = self.invoke(*args)
                self.assertEqual(code, 2)
                self.assertEqual(lines, [])  # No last stdout line for a usage error.
                self.assertTrue(err.startswith("usage: "))

    def test_c4_read_only(self):
        # Rewrites that preserve bytes or add a sidecar must also be detected.
        self.write()
        before = {p.name: (p.read_bytes(), p.stat().st_mtime_ns) for p in self.content.iterdir()}
        directory_mtime = self.content.stat().st_mtime_ns
        result = subprocess.run([sys.executable, "-B", str(SCRIPT), "--content", str(self.content)],
                                cwd=self.content, capture_output=True, text=True, timeout=10)
        self.assert_pass((result.returncode, result.stdout.splitlines(), result.stderr))
        self.assertEqual({p.name for p in self.content.iterdir()}, set(before))
        self.assertEqual(self.content.stat().st_mtime_ns, directory_mtime)
        for name, (raw, mtime) in before.items():
            path = self.content / name
            self.assertEqual(path.read_bytes(), raw)
            self.assertEqual(path.stat().st_mtime_ns, mtime)

    def test_c5_no_private_values(self):
        # Dumping records, echoing argv or printing loader errors leaks canaries.
        place, story, url, description = ("place-canary", "story-canary",
                                          "https://example.com/url-canary", "description-canary")
        self.write(makers={"maker": {"place": place, "story": story, "url": url}},
                   products=[product("item", "maker", description=description)])
        result = self.run_report()
        self.assert_pass(result)
        (self.content / "makers.json").write_text(json.dumps({
            "schemaVersion": 1, "makers": {}, story: place,
        }), encoding="utf-8")
        invalid = self.run_report()
        self.assert_findings(invalid, "FAIL content-invalid")
        usage = self.invoke("--content", str(self.content), str(self.root))
        self.assertEqual(usage[:2], (2, []))
        for _, lines, stderr in (result, invalid, usage):
            output = "\n".join(lines) + stderr
            for canary in (place, story, url, description, str(self.root), str(self.content)):
                self.assertNotIn(canary, output)

    def test_c6_ambiguous_brand(self):
        # A normalized name lookup must not silently pick the first or last maker.
        self.write(makers={"one": {"name": " Same Maker "},
                           "two": {"name": "SAME MAKER", "hidden": True}},
                   products=[product("ambiguous", brand="same maker")])
        lines = self.assert_pass(self.run_report())
        self.assertIn("note unlinked-brand 0", lines)
        self.assertNotIn("unlinked ambiguous", lines)

    def test_c7_hidden_maker_not_named(self):
        # Hidden makers must contribute to the count but not the key listing.
        self.write(makers={"do-not-name": {"hidden": True}, "visible": {}})
        lines = self.assert_pass(self.run_report())
        self.assertIn("hidden-makers 1", lines)
        self.assertIn("note unused-maker 2", lines)
        self.assertEqual([line for line in lines if line.startswith("unused ")], ["unused visible"])
        self.assertNotIn("do-not-name", "\n".join(lines))

    def test_c8_clean_catalog(self):
        # A complete linked catalog has no false-positive findings or notes.
        self.write(makers={"maker": {"name": "Fixture Brand", "url": "https://example.com"}},
                   products=[product("item", "maker")])
        self.assertEqual(self.assert_pass(self.run_report()), [
            "makers 1", "hidden-makers 0", "active-products 1", "linked 1",
            "note unused-maker 0", "note held-only-maker 0", "note no-url 0",
            "note unlinked-brand 0", "note malformed 0", "PASS makers_usage",
        ])
