"""Fixture-only tests for the offline picture reference audit CLI."""

from contextlib import redirect_stderr, redirect_stdout
import importlib.util
import io
import json
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest


SCRIPT = Path(__file__).resolve().parents[2] / "scripts/hass/content_image_refs.py"
SPEC = importlib.util.spec_from_file_location("content_image_refs", SCRIPT)
assert SPEC is not None and SPEC.loader is not None
AUDIT = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(AUDIT)

PHOTO = "photo-0123456789abcdef.jpg"
HOME = "home.webp"  # The audit is not the stricter home-image validator.
PASS = "PASS content_image_refs"
FAIL = "FAIL content_image_refs"


def product(pid, status="active", filename=PHOTO, **fields):
    return {"id": pid, "status": status, "image": f"assets/products/{filename}", **fields}


class ContentImageRefsTests(unittest.TestCase):
    def setUp(self):
        self.root = Path(self.enterContext(tempfile.TemporaryDirectory())).resolve()
        self.content = self.root / "fixture-content-canary"
        self.site = self.root / "fixture-site-canary"
        self.pictures = self.site / "assets" / "products"
        self.content.mkdir()
        self.pictures.mkdir(parents=True)
        self.write_content()

    def write_content(self, rows=(), **store):
        for name, fields in {
            "products": {"products": list(rows)},
            "makers": {"makers": {}},
            "community": {},
            "store": store,
        }.items():
            (self.content / f"{name}.json").write_text(
                json.dumps({"schemaVersion": 1, **fields}), encoding="utf-8"
            )

    def args(self, *, content=None, site=None):
        return ["--content", str(content or self.content), "--site", str(site or self.site)]

    def cli(self, *args):
        result = subprocess.run([sys.executable, "-B", str(SCRIPT), *args], cwd=self.root,
                                capture_output=True, text=True, timeout=10)
        return result.returncode, result.stdout, result.stderr

    def audit(self, **paths):
        out, err = io.StringIO(), io.StringIO()
        with redirect_stdout(out), redirect_stderr(err):
            code = AUDIT.main(self.args(**paths))
        return code, out.getvalue(), err.getvalue()

    def assert_report(self, result, *reasons):
        code, out, err = result
        lines = out.splitlines()
        self.assertEqual(code, 1 if reasons else 0, (out, err))
        self.assertEqual(err, "")
        self.assertEqual(lines[-1:], [FAIL if reasons else PASS])
        self.assertEqual([line for line in lines[:-1] if line.startswith("FAIL ")],
                         [f"FAIL {reason}" for reason in reasons])
        return lines[:-1]

    def test_c1_full_pass(self):
        # Filtering by status would lose the held and legacy references; counting
        # per record would double-count the shared image. Malformed rows are notes.
        self.write_content([
            product("fixture-active"), product("fixture-hidden", "hidden"),
            product("fixture-held", "held", "held.jpg"),
            product("fixture-legacy", "legacy", "legacy.png"), None, ["fixture"]
        ], homeImage={"image": f"assets/products/{HOME}"})
        for name in (PHOTO, HOME, "legacy.png"):
            (self.pictures / name).write_bytes(b"fixture")
        self.assertEqual(self.assert_report(self.cli(*self.args())), [
            "files 3", "referenced 4", "note not-regular 0", "note orphan 0",
            "note shared-image 1", "note held-image-missing 1", "note malformed 2",
        ])

    def test_c2_1_unsafe_input(self):
        # is_dir() alone would accept a link to an otherwise valid copy.
        ordinary_file = self.root / "fixture-file"
        ordinary_file.touch()
        for option, target in (("content", self.content), ("site", self.site)):
            alias = self.root / f"alias-{option}"
            alias.symlink_to(target, target_is_directory=True)
            for unsafe in (alias, ordinary_file, self.root / "absent"):
                with self.subTest(option=option, kind=unsafe.name):
                    self.assertEqual(self.assert_report(self.audit(**{option: unsafe}),
                                                        "unsafe-input"), ["FAIL unsafe-input"])

        for kind in ("absent", "file", "link", "assets-link"):
            with self.subTest(kind=kind):
                site = self.root / f"site-{kind}"
                assets = site / "assets"
                site.mkdir()
                if kind == "assets-link":
                    assets.symlink_to(self.pictures.parent, target_is_directory=True)
                else:
                    assets.mkdir()
                    pictures = assets / "products"
                    if kind == "file":
                        pictures.touch()
                    elif kind == "link":
                        pictures.symlink_to(self.pictures, target_is_directory=True)
                self.assertEqual(self.assert_report(self.audit(site=site), "unsafe-input"),
                                 ["FAIL unsafe-input"])

    def test_c2_2_content_invalid(self):
        # Reading only products/store or parsing JSON instead of using the loader
        # would miss bad schemas, duplicate keys, or invalid UTF-8 in the other files.
        for filename, raw in (
            ("community.json", b'{"schemaVersion": 2}'),
            ("makers.json", b'{"schemaVersion": 1, "makers": {}, "makers": {}}'),
            ("store.json", b'{"schemaVersion": 1, "name": "\xff"}'),
        ):
            with self.subTest(filename=filename):
                self.write_content()
                (self.content / filename).write_bytes(raw)
                self.assertEqual(self.assert_report(self.audit(), "content-invalid"),
                                 ["FAIL content-invalid"])

    def test_c2_3_image_missing(self):
        # One shared absent filename means two missing products, not one. The
        # home picture is its own row, and a directory cannot satisfy any reference.
        self.write_content([product("z-fixture"), product("a-fixture")],
                           homeImage={"image": f"assets/products/{HOME}"})
        (self.pictures / HOME).mkdir()
        lines = self.assert_report(self.audit(), "image-missing 3")
        self.assertIn("note not-regular 1", lines)
        self.assertIn("note shared-image 1", lines)
        self.assertEqual(lines[-4:], ["missing a-fixture", "missing store.homeImage",
                                     "missing z-fixture", "FAIL image-missing 3"])

    def test_c2_4_bad_image_path(self):
        # A basename-only or partial match would accept the bad string; held bad
        # paths are notes and non-string active paths must not reach the regex.
        self.write_content([
            product("fixture-active", image=17),
            product("fixture-hidden", "hidden", image=f"assets/products/{PHOTO}\n"),
            product("fixture-held", "held", image="fixture-not-a-path"),
        ])
        lines = self.assert_report(self.audit(), "bad-image-path 2")
        self.assertIn("referenced 0", lines)
        self.assertIn("note held-image-missing 1", lines)
        self.assertFalse(any(line.startswith("missing ") for line in lines))

    def test_c3_usage_exit_2(self):
        # Usage failures belong to argparse, not the report's finding envelope.
        for args in ((), tuple(self.args()[:2]), (*self.args(), "--unknown"),
                     ("--content", "--site", str(self.site))):
            with self.subTest(argc=len(args)):
                code, out, err = self.cli(*args)
                self.assertEqual(code, 2)
                self.assertEqual(out, "")  # No last stdout line at all.
                self.assertIn("usage:", err)

    def test_c4_read_only(self):
        # Byte equality alone would miss same-byte rewrites; enumerating only
        # preexisting inputs would miss new reports, caches, or directories.
        self.write_content([product("fixture-active")])
        (self.pictures / PHOTO).write_bytes(b"fixture picture")
        (self.site / "fixture-unrelated.html").write_bytes(b"fixture page")

        def snapshot():
            return {
                path.relative_to(self.root): (path.stat().st_mtime_ns,
                                             path.read_bytes() if path.is_file() else None)
                for directory in (self.content, self.site)
                for path in (directory, *directory.rglob("*"))
            }

        before = snapshot()
        self.assert_report(self.cli(*self.args()))
        self.assertEqual(snapshot(), before)

    def test_c5_no_private_values(self):
        # Dumping records, raw invalid paths, or exceptions can leak private input.
        private = {"name": "canary-product-name", "description": "canary-description",
                   "imageAlt": "canary-product-alt"}
        home_alt = "canary-home-alt"
        self.write_content([product("fixture-missing", **private),
                            product("fixture-bad", image=str(self.content))],
                           homeImage={"image": f"assets/products/{PHOTO}", "imageAlt": home_alt})
        result = self.audit()
        lines = self.assert_report(result, "bad-image-path 1", "image-missing 2")
        self.assertIn("missing fixture-missing", lines)
        self.assertIn("note shared-image 0", lines)  # Home is not another product.
        for canary in (*private.values(), home_alt, str(self.content), str(self.site)):
            self.assertNotIn(canary, result[1] + result[2])
        # Argparse's default unrecognized-argument error echoes its value.
        code, out, err = self.cli(*self.args(), "--unknown", str(self.site))
        self.assertEqual((code, out), (2, ""))
        self.assertNotIn(str(self.site), err)

    def test_c6_hidden_missing(self):
        # An active-only scan would miss this restorable listing's picture.
        self.write_content([product("fixture-hidden", "hidden")])
        self.assertEqual(self.assert_report(self.audit(), "image-missing 1")[-2:],
                         ["missing fixture-hidden", "FAIL image-missing 1"])

    def test_c7_orphan_listed(self):
        # Unreferenced regular files are sorted notes, not failures, even if
        # their names do not match the product-image pattern.
        for name in ("z-orphan.jpg", "a-orphan.txt"):
            (self.pictures / name).touch()
        lines = self.assert_report(self.audit())
        self.assertEqual(lines[0], "files 2")
        self.assertEqual(lines[3:6], ["note orphan 2", "orphan a-orphan.txt", "orphan z-orphan.jpg"])

    def test_c8_symlink_not_followed(self):
        # A real regular target would fool a stat that follows symlinks.
        target = self.root / "fixture-target.jpg"
        target.touch()
        (self.pictures / PHOTO).symlink_to(target)
        (self.pictures / "dangling.jpg").symlink_to(self.root / "absent")
        self.write_content([product("fixture-active")])
        lines = self.assert_report(self.audit(), "image-missing 1")
        self.assertIn("files 0", lines)
        self.assertIn("note not-regular 2", lines)
        self.assertEqual(lines[-2:], ["missing fixture-active", "FAIL image-missing 1"])
