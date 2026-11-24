"""Fixture-only contract tests for the catalog picture header checker."""

from contextlib import redirect_stderr, redirect_stdout
import importlib.util
import io
import json
from pathlib import Path
import struct
import subprocess
import sys
import tempfile
import unittest
import zlib


SCRIPT = Path(__file__).resolve().parents[2] / "scripts/hass/content_image_format.py"
SPEC = importlib.util.spec_from_file_location("content_image_format", SCRIPT)
assert SPEC is not None and SPEC.loader is not None
CHECKER = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(CHECKER)
ASSETS = Path("assets/products")
HOME = "photo-0123456789abcdef.png"


def png(width, height):
    # Only the signature and complete IHDR chunk; no image data needed.
    payload = struct.pack(">IIBBBBB", width, height, 8, 2, 0, 0, 0)
    chunk = b"IHDR" + payload
    return b"\x89PNG\r\n\x1a\n" + struct.pack(">I", len(payload)) + chunk + struct.pack(">I", zlib.crc32(chunk))


def jpeg(width, height):
    # APP payload includes a fake marker; then fill, TEM and restart before SOF0.
    prefix = b"\xff\xd8\xff\xe1\x00\x06x\xff\xc0x\xff\xff\x01\xff\xd0"
    frame = struct.pack(">HBHHB", 11, 8, height, width, 1) + b"\x01\x11\x00"
    return prefix + b"\xff\xc0" + frame


def webp(kind, payload):
    chunk = kind + struct.pack("<I", len(payload)) + payload + b"\0" * (len(payload) % 2)
    return b"RIFF" + struct.pack("<I", 4 + len(chunk)) + b"WEBP" + chunk


class ContentImageFormatTests(unittest.TestCase):
    def setUp(self):
        temporary = tempfile.TemporaryDirectory()
        self.addCleanup(temporary.cleanup)
        self.root = Path(temporary.name).resolve()
        self.content = self.root / "canary-content-copy"
        self.site = self.root / "canary-site-copy"
        self.content.mkdir()
        (self.site / ASSETS).mkdir(parents=True)

    def write_content(self, products=(), home=None):
        store = {} if home is None else {"homeImage": {"image": str(ASSETS / home), "imageAlt": "Demo image"}}
        for name, payload in (("products", {"products": list(products)}), ("makers", {"makers": {}}),
                              ("community", {}), ("store", store)):
            (self.content / f"{name}.json").write_text(json.dumps({"schemaVersion": 1, **payload}), encoding="utf-8")

    def product(self, product_id, filename, status="active", **fields):
        return {"id": product_id, "status": status, "image": str(ASSETS / filename), **fields}

    def image(self, filename, data):
        (self.site / ASSETS / filename).write_bytes(data)

    def arguments(self):
        return ["--content", str(self.content), "--site", str(self.site)]

    def cli(self, *args):
        return subprocess.run([sys.executable, "-B", str(SCRIPT), *args], cwd=self.root,
                              capture_output=True, text=True, timeout=10)

    def assert_outcome(self, code, stdout, stderr, expected):
        self.assertEqual(code, expected, stderr)
        lines = stdout.splitlines()
        self.assertEqual(lines[-1:], ["PASS content_image_format" if expected == 0 else "FAIL content_image_format"])
        self.assertEqual(stderr, "")
        return lines[:-1]

    def run_check(self, expected=0, args=None):
        out, err = io.StringIO(), io.StringIO()
        with redirect_stdout(out), redirect_stderr(err):
            code = CHECKER.main(self.arguments() if args is None else args)
        return self.assert_outcome(code, out.getvalue(), err.getvalue(), expected)

    def test_c1_full_pass(self):
        # Duplicate references, malformed rows and missing/nonregular copies must not fail.
        self.write_content([self.product("p-one", "sample.jpg"), self.product("p-two", "sample.jpg", "hidden"),
                            self.product("p-missing", "missing.webp"), self.product("p-link", "link.jpg"),
                            self.product("p-directory", "directory.png"), None, [1]], home=HOME)
        self.image("sample.jpg", jpeg(301, 29))
        self.image(HOME, png(41, 502))
        (self.site / ASSETS / "link.jpg").symlink_to("sample.jpg")
        (self.site / ASSETS / "directory.png").mkdir()
        result = self.cli(*self.arguments())
        self.assertEqual(self.assert_outcome(result.returncode, result.stdout, result.stderr, 0), [
            "checked 2", "format jpeg 1", "format png 1", "width-min 41", "width-max 301",
            "height-min 29", "height-max 502", "note missing 3", "note malformed 2",
        ])

    def test_c2_1_unsafe_input(self):
        # is_dir() alone would allow a symlink to a valid input directory.
        self.write_content()
        link = self.root / "directory-link"
        link.symlink_to(self.content, target_is_directory=True)
        file = self.content / "store.json"
        absent = self.root / "no-directory"
        for index in (1, 3):
            for target in (link, file, absent):
                with self.subTest(argument=index, target=target.name):
                    args = self.arguments()
                    args[index] = str(target)
                    self.assertEqual(self.run_check(1, args), ["FAIL unsafe-input"])

    def test_c2_2_content_invalid(self):
        # Invalid JSON, UTF-8 and mismatched envelope versions must not escape the loader boundary.
        self.write_content()
        for bad in (b"{", b"\xff", b'{"schemaVersion":2}'):
            with self.subTest(bad=bad):
                (self.content / "community.json").write_bytes(bad)
                self.assertEqual(self.run_check(1), ["FAIL content-invalid"])

    def test_c2_3_ext_mismatch(self):
        # Report actual format and sorted owners, but count the shared file only once.
        self.write_content([self.product("p-z", HOME), self.product("p-a", HOME, "hidden")], home=HOME)
        self.image(HOME, jpeg(39, 52))
        self.assertEqual(self.run_check(1), [
            "checked 1", "format jpeg 1", "width-min 39", "width-max 39", "height-min 52", "height-max 52",
            "mismatch p-a", "mismatch p-z", "mismatch store.homeImage", "FAIL ext-mismatch 1",
        ])

    def test_c2_4_unreadable(self):
        # Known magic isn't enough; a valid SOF beyond 1 MiB must not be read.
        self.write_content([self.product("p-z", "unknown.png"), self.product("p-b", "distant.jpeg"),
                            self.product("p-a", "cut.webp")])
        self.image("unknown.png", b"not a photo")
        app = b"\xff\xe1\xff\xff" + bytes(65533)
        self.image("distant.jpeg", b"\xff\xd8" + 16 * app + jpeg(50, 60)[2:])
        self.image("cut.webp", b"\x89PNG\r\n\x1a\n")
        self.assertEqual(self.run_check(1), [
            "checked 3", "format jpeg 1", "format png 1", "mismatch p-a", "FAIL ext-mismatch 1",
            "unreadable p-a", "unreadable p-b", "unreadable p-z", "FAIL unreadable 3",
        ])

    def test_c3_usage_exit_2(self):
        # Syntax failures stay on stderr and are not handled like findings.
        self.write_content()
        args = self.arguments()
        for invalid in (args[:2], [*args, "--unknown"], args[:-1]):
            with self.subTest(invalid=invalid):
                result = self.cli(*invalid)
                self.assertEqual(result.returncode, 2)
                self.assertEqual(result.stdout.splitlines(), [])  # No final stdout line for C3.
                self.assertTrue(result.stderr.startswith("usage:"))

    def test_c4_read_only(self):
        # Catch rewrites (even identical ones) and new files or directories.
        self.write_content([self.product("p-one", "only.png")])
        self.image("only.png", png(9, 16))

        def snapshot():
            return {item: (item.stat().st_mtime_ns, item.read_bytes() if item.is_file() else None)
                    for item in self.root.rglob("*")}

        before = snapshot()
        result = self.cli(*self.arguments())
        self.assert_outcome(result.returncode, result.stdout, result.stderr, 0)
        self.assertEqual(snapshot(), before)

    def test_c5_no_private_values(self):
        # Diagnostics should emit IDs only, never the records, paths or raw argv.
        name, description = "Canary-Name", "Canary-Description"
        self.write_content([self.product("p-one", "invalid.png", name=name, description=description)])
        self.image("invalid.png", b"bad")
        result = self.cli(*self.arguments())
        self.assertEqual(self.assert_outcome(result.returncode, result.stdout, result.stderr, 1),
                         ["checked 1", "unreadable p-one", "FAIL unreadable 1"])
        usage = self.cli(*self.arguments(), "--unknown", str(self.content))
        self.assertEqual((usage.returncode, usage.stdout), (2, ""))
        for value in (name, description, str(self.content), str(self.site)):
            self.assertNotIn(value, result.stdout + result.stderr + usage.stdout + usage.stderr)

    def test_c6_sizes_exact(self):
        # Isolate the formats so another picture cannot mask a wrong min or max.
        cases = (
            ("fixture.png", "png", png(513, 1027), 513, 1027),
            ("fixture.jpeg", "jpeg", jpeg(1025, 771), 1025, 771),
            ("fixture.webp", "webp", webp(b"VP8 ", b"\0\0\0\x9d\x01\x2a" +
                                          struct.pack("<HH", 0x8000 | 317, 0x4000 | 242)), 317, 242),
            ("fixture.webp", "webp", webp(b"VP8L", b"\x2f" +
                                          struct.pack("<I", 700 | (1050 << 14) | (1 << 28))), 701, 1051),
            ("fixture.webp", "webp", webp(b"VP8X", b"\0" * 4 + b"\x02\x01\x01\x04\x02\x00"), 65795, 517),
        )
        for filename, kind, data, width, height in cases:
            with self.subTest(kind=data[12:16] if kind == "webp" else kind):
                self.write_content([self.product("p-one", filename)])
                self.image(filename, data)
                self.assertEqual(self.run_check(), [
                    "checked 1", f"format {kind} 1", f"width-min {width}", f"width-max {width}",
                    f"height-min {height}", f"height-max {height}",
                ])

    def test_c7_truncated_jpeg(self):
        # APP segment length itself is incomplete; no indexing past end or bogus dimension.
        self.write_content([self.product("p-one", "cut.jpg")])
        self.image("cut.jpg", b"\xff\xd8\xff\xe1\x00")
        self.assertEqual(self.run_check(1), ["checked 1", "format jpeg 1", "unreadable p-one", "FAIL unreadable 1"])

    def test_c8_held_skipped(self):
        # If held rows are selected, this existing invalid file would fail the run.
        self.write_content([self.product("p-held", "hold.jpg", "held")])
        self.image("hold.jpg", b"bad")
        self.assertEqual(self.run_check(), ["checked 0"])

    def test_site_asset_directory_symlink_is_missing(self):
        # A regular leaf under a linked directory is not an in-copy file.
        self.write_content([self.product("p-one", "outside.jpg")])
        elsewhere = self.root / "elsewhere"
        elsewhere.mkdir()
        (elsewhere / "outside.jpg").write_bytes(b"bad")
        other_site = self.root / "other-site"
        (other_site / "assets").mkdir(parents=True)
        (other_site / ASSETS).symlink_to(elsewhere, target_is_directory=True)
        self.assertEqual(self.run_check(args=["--content", str(self.content), "--site", str(other_site)]),
                         ["checked 0", "note missing 1"])


if __name__ == "__main__":
    unittest.main()
