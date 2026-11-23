"""Exercise the offline pilot photo CLI against synthetic local fixtures."""

import hashlib
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest

from PIL import Image, ImageDraw, ImageFilter, TiffImagePlugin


SCRIPT = Path(__file__).resolve().parents[2] / "scripts/hass/pilot_photo_precheck.py"
PASS = "PASS pilot_photo_precheck"
FAIL = "FAIL pilot_photo_precheck"


def checkerboard():
    image = Image.new("RGB", (128, 96), "black")
    draw = ImageDraw.Draw(image)
    for y in range(0, 96, 16):
        for x in range(0, 128, 16):
            if (x // 16 + y // 16) % 2:
                draw.rectangle((x, y, x + 15, y + 15), fill="white")
    return image


class PilotPhotoPrecheckTests(unittest.TestCase):
    def setUp(self):
        temp = tempfile.TemporaryDirectory()
        self.addCleanup(temp.cleanup)
        self.root = Path(temp.name).resolve()

    def save(self, name, image=None, **options):
        path = self.root / name
        (checkerboard() if image is None else image).save(path, **options)
        return path

    def invoke(self, *args):
        return subprocess.run(
            [sys.executable, "-B", str(SCRIPT), *map(str, args)],
            cwd=self.root, capture_output=True, text=True, timeout=10,
        )

    def assert_report(self, result, code, *lines):
        self.assertEqual(result.returncode, code, result.stderr)
        self.assertEqual(result.stderr, "")
        self.assertEqual(result.stdout.splitlines(), [*lines, PASS if code == 0 else FAIL])

    def metadata(self, k, path, fmt="PNG", size="128x96", gps="no", sharpness="ok"):
        return [f"photo {k} format {fmt}", f"photo {k} size {size}",
                f"photo {k} bytes {path.stat().st_size}", f"photo {k} gps {gps}",
                f"photo {k} sharpness {sharpness}"]

    def test_c1_full_pass(self):
        # Ten valid arguments catch an off-by-one cap, skipped photos, or a wrong status.
        path = self.save("fixture.png")
        metadata = [line for k in range(1, 11) for line in self.metadata(k, path)]
        self.assert_report(self.invoke(*([path] * 10)), 0, *metadata)

    def test_c2_1_unreadable(self):
        # A following stat, open-only validation, or an early return loses findings.
        good = self.save("good.png")
        absent = self.root / "absent.png"
        link = self.root / "link.png"
        link.symlink_to(good)
        directory = self.root / "directory"
        directory.mkdir()
        invalid = self.root / "invalid.png"
        invalid.write_bytes(b"synthetic invalid image")
        truncated = self.root / "truncated.png"
        truncated.write_bytes(good.read_bytes()[:50])
        with Image.open(truncated) as image:
            with self.assertRaises(OSError):
                image.load()
        self.assert_report(self.invoke(absent, link, directory, invalid, truncated, good), 1,
                           *(f"FAIL unreadable {k}" for k in range(1, 6)), *self.metadata(6, good))

    def test_c2_2_soft(self):
        # A numeric zero is a finding, and it must not prevent subsequent checks.
        photo = self.save("flat.png", Image.new("RGB", (128, 96)))
        self.assert_report(self.invoke(photo, self.root / "absent.png"), 1,
                           *self.metadata(1, photo, sharpness="soft"),
                           "FAIL soft 1", "FAIL unreadable 2")

    def test_c3_usage_exit_2(self):
        # Treating CLI mistakes as image findings would write stdout and exit 1.
        photo = self.save("fixture.png")
        for args in ((), ("--unknown", photo), (photo,) * 11):
            with self.subTest(count=len(args)):
                result = self.invoke(*args)
                self.assertEqual(result.returncode, 2)
                self.assertEqual(result.stdout, "")  # No last stdout line on usage errors.
                self.assertTrue(result.stderr.startswith("usage: pilot_photo_precheck "))
                self.assertTrue(result.stderr.splitlines()[-1].startswith("pilot_photo_precheck: error: "))

    def test_c4_read_only(self):
        # Re-encoding in place, touching a source, or adding a preview must be visible.
        sub = self.root / "nested"
        sub.mkdir()
        sharp = self.save("fixture.png")
        soft = self.save("nested/flat.png", Image.new("RGB", (128, 96)))
        before = [(path.read_bytes(), path.stat().st_mtime_ns) for path in (sharp, soft)]
        self.assert_report(self.invoke(sharp, soft), 1, *self.metadata(1, sharp),
                           *self.metadata(2, soft, sharpness="soft"), "FAIL soft 2")
        self.assertEqual([(path.read_bytes(), path.stat().st_mtime_ns) for path in (sharp, soft)], before)
        self.assertEqual(set(self.root.iterdir()), {sharp, sub})
        self.assertEqual(set(sub.iterdir()), {soft})

    def test_c5_no_private_values(self):
        # Printing EXIF, exceptions, a digest, or argparse's raw unknown flag leaks data.
        text, chat, sender, fixture_id = ("fixture-message-canary", "fixture-chat-canary",
                                          "fixture-sender-canary", "fixture-id-canary")
        exif = Image.Exif()
        exif[270], exif[315], exif[33432], exif[42016] = text, chat, sender, fixture_id
        photo = self.save("fixture-basename-canary.jpg", exif=exif)
        absent = self.root / "fixture-missing-canary.png"
        raw_flag = f"--fixture-flag={photo}"
        result = self.invoke(photo, absent)
        self.assert_report(result, 1, *self.metadata(1, photo, fmt="JPEG"), "FAIL unreadable 2")
        usage = self.invoke(raw_flag, photo)
        self.assertEqual((usage.returncode, usage.stdout), (2, ""))
        output = result.stdout + result.stderr + usage.stdout + usage.stderr
        for value in (text, chat, sender, fixture_id, hashlib.sha256(photo.read_bytes()).hexdigest(),
                      str(photo), str(absent), photo.name, absent.name, raw_flag):
            self.assertNotIn(value, output)

    def test_c6_sharp_vs_blur(self):
        # A constant label or drift from the calibrated blur check breaks the pair.
        image = checkerboard()
        sharp = self.save("sharp.png", image)
        blur = self.save("blur.png", image.filter(ImageFilter.GaussianBlur(4)))
        self.assert_report(self.invoke(sharp), 0, *self.metadata(1, sharp))
        self.assert_report(self.invoke(blur), 1, *self.metadata(1, blur, sharpness="soft"), "FAIL soft 1")

    def test_c7_gps_reported(self):
        # Looking only at decoded pixels loses GPS; dumping tag values exposes it.
        rational = TiffImagePlugin.IFDRational
        exif = Image.Exif()
        exif[34853] = {1: "N", 2: (rational(0), rational(0), rational(56789, 1000)),
                       3: "E", 4: (rational(0), rational(0), rational(43217, 1000))}
        photo = self.save("gps.jpg", exif=exif)
        result = self.invoke(photo)
        self.assert_report(result, 0, *self.metadata(1, photo, fmt="JPEG", gps="yes"))
        for coordinate in ("56789", "43217", "56.789", "43.217"):
            self.assertNotIn(coordinate, result.stdout + result.stderr)

    def test_c8_unscored_small_photo(self):
        # Either dimension below eight is unscored, not a zero score or a failure.
        for width, height in ((7, 16), (16, 7), (8, 8)):
            with self.subTest(size=(width, height)):
                size = f"{width}x{height}"
                photo = self.save(f"{size}.png", Image.new("RGB", (width, height)))
                result = self.invoke(photo)
                if (width, height) == (8, 8):
                    self.assert_report(result, 1, *self.metadata(1, photo, size=size, sharpness="soft"),
                                       "FAIL soft 1")
                else:
                    self.assert_report(result, 0, *self.metadata(1, photo, size=size, sharpness="unscored"))
