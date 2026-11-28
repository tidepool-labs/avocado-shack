"""Exercise the offline photo diagnostic against live helpers and fixture drift."""

from contextlib import redirect_stderr, redirect_stdout
import importlib.util
from io import StringIO
from pathlib import Path
import subprocess
import sys
import unittest
from unittest.mock import call, patch

from hass import media

ROOT = Path(__file__).resolve().parents[2]
SCRIPT = ROOT / "scripts/hass/npp_photo_magic_sniff.py"
SPEC = importlib.util.spec_from_file_location("npp_photo_magic_sniff", SCRIPT)
assert SPEC is not None and SPEC.loader is not None
CHECK = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(CHECK)

PASS = "PASS npp_photo_magic_sniff"
FAIL = "FAIL npp_photo_magic_sniff"
LIVE = [
    "case 0 sniff='jpeg' audio=no",
    "case 1 sniff='jpeg' audio=no",
    "case 2 sniff=None audio=no",
    "case 3 sniff='png' audio=no",
    "case 4 sniff=None audio=no",
    "case 5 sniff=None audio=no",
    "case 6 sniff=None audio=no",
    "case 7 sniff=None audio=yes",
    "case 8 sniff=None audio=yes",
    "case 9 sniff=None audio=yes",
    "case 10 sniff=None audio=no",
]


def run_cli(*args):
    return subprocess.run(
        [sys.executable, "-B", str(SCRIPT), *args], cwd=ROOT,
        capture_output=True, text=True, timeout=10,
    )


def snapshot():
    entries = {}
    for tree in (ROOT / "hass", ROOT / "storefront-mockup"):
        for path in (tree, *tree.rglob("*")):
            info = path.lstat()
            entries[path.relative_to(ROOT)] = (info.st_size, info.st_mtime_ns)
    return entries


class PhotoMagicSniffTests(unittest.TestCase):
    def run_check(self, exit_code, trailer):
        stdout, stderr = StringIO(), StringIO()
        with redirect_stdout(stdout), redirect_stderr(stderr):
            code = CHECK.main([])
        lines = stdout.getvalue().splitlines()
        self.assertEqual(code, exit_code)
        self.assertEqual(lines[-1:], [trailer])
        self.assertEqual(stderr.getvalue(), "")
        return lines[:-1]

    def test_c1_full_pass(self):
        # A correct main() can still be wired to the wrong CLI exit status.
        result = run_cli()
        self.assertEqual(result.returncode, 0)
        self.assertEqual(result.stdout.splitlines()[-1:], [PASS])
        self.assertEqual(result.stderr, "")

    def test_c2_findings_trailer(self):
        # A finding must not yield PASS or be deferred past its case's line.
        with patch.object(media, "sniff", side_effect=media._prefix):
            lines = self.run_check(1, FAIL)
        self.assertEqual(lines, [
            *LIVE[:2],
            "case 2 sniff='jpeg' audio=no", "FAIL bad-bytes-accepted 2", "FAIL sniff-changed 2",
            LIVE[3],
            "case 4 sniff='png' audio=no", "FAIL bad-bytes-accepted 4", "FAIL sniff-changed 4",
            "case 5 sniff='png' audio=no", "FAIL bad-bytes-accepted 5", "FAIL sniff-changed 5",
            *LIVE[6:],
        ])

    def test_c2_1_bad_bytes_accepted(self):
        # Prefix-only acceptance loses the end-marker safety check.
        with patch.object(media, "sniff", lambda data: media._prefix(data)):
            lines = self.run_check(1, FAIL)
        self.assertEqual([line for line in lines if line.startswith("FAIL ")], [
            "FAIL bad-bytes-accepted 2", "FAIL sniff-changed 2",
            "FAIL bad-bytes-accepted 4", "FAIL sniff-changed 4",
            "FAIL bad-bytes-accepted 5", "FAIL sniff-changed 5",
        ])

    def test_c2_2_sniff_changed(self):
        # MUST_NONE alone misses drift on accepted PNG case 3 or audio drift.
        with patch.object(media, "PNG_END", b"IEND"):
            lines = self.run_check(1, FAIL)
        self.assertEqual([line for line in lines if line.startswith("FAIL sniff-changed ")], [
            "FAIL sniff-changed 3", "FAIL sniff-changed 4",
        ])
        with patch.object(media, "is_audio", return_value=False):
            lines = self.run_check(1, FAIL)
        self.assertEqual([line for line in lines if line.startswith("FAIL ")], [
            "FAIL sniff-changed 7", "FAIL sniff-changed 8", "FAIL sniff-changed 9",
        ])

    def test_c2_3_check_error(self):
        # A classifier error must stop the loop without printing exception text.
        for name in ("sniff", "is_audio"):
            with self.subTest(name=name):
                real = getattr(media, name)
                with patch.object(media, name, side_effect=[real(CHECK.CASES[0]),
                                                           RuntimeError("fixture error")]) as check:
                    lines = self.run_check(1, FAIL)
                self.assertEqual(lines, [LIVE[0], "FAIL check-error"])
                self.assertEqual(check.call_args_list, [call(data) for data in CHECK.CASES[:2]])

    def test_c3_usage_exit_2(self):
        # No input tokens, including argparse's default help flag, are allowed.
        for token in ("photo", "--unknown", "--help", "-h", "--"):
            with self.subTest(token=token):
                result = run_cli(token)
                self.assertEqual(result.returncode, 2)
                self.assertEqual(result.stdout, "")
                self.assertTrue(result.stderr.startswith("usage: "))
                self.assertTrue(result.stderr.splitlines()[-1].startswith(
                    "npp_photo_magic_sniff.py: error: "))

    def test_c4_read_only(self):
        # An accidental storage call or file touch changes names, size or mtime.
        before = snapshot()
        result = run_cli()
        self.assertEqual(result.returncode, 0)
        self.assertEqual(result.stdout.splitlines()[-1:], [PASS])
        self.assertEqual(result.stderr, "")
        self.assertEqual(snapshot(), before)

    def test_c5_output_shape(self):
        # Extra logging, blank lines or debug banners break the line protocol.
        pattern = (
            r"(?:case [0-9]+ sniff=(?:'jpeg'|'png'|None) audio=(?:yes|no)"
            r"|FAIL (?:bad-bytes-accepted [0-9]+|sniff-changed [0-9]+|check-error))\Z"
        )
        for line in self.run_check(0, PASS):
            self.assertRegex(line, pattern)
        with patch.object(media, "PNG_END", b"IEND"):
            for line in self.run_check(1, FAIL):
                self.assertRegex(line, pattern)

    def test_c6_fixture(self):
        # Shortening the trailer both rejects the good case and accepts bad bytes.
        with patch.object(media, "PNG_END", b"IEND"):
            lines = self.run_check(1, FAIL)
        self.assertEqual([line for line in lines if line.startswith("FAIL ")], [
            "FAIL sniff-changed 3", "FAIL bad-bytes-accepted 4", "FAIL sniff-changed 4",
        ])

    def test_c7_live_pins(self):
        # A static report could match the pins without calling the classifiers.
        with (patch.object(media, "sniff", wraps=media.sniff) as sniff,
              patch.object(media, "is_audio", wraps=media.is_audio) as is_audio):
            lines = self.run_check(0, PASS)
        self.assertEqual(lines, LIVE)
        calls = [call(data) for data in CHECK.CASES]
        self.assertEqual(sniff.call_args_list, calls)
        self.assertEqual(is_audio.call_args_list, calls)


if __name__ == "__main__":
    unittest.main()
