"""Offline CLI contract for the four owner-photo path rules."""

from contextlib import redirect_stderr, redirect_stdout
import importlib.util
import io
import json
from pathlib import Path
import re
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[2]
SCRIPT = ROOT / "scripts/hass/owner_photo_path_agreement.py"
SPEC = importlib.util.spec_from_file_location("owner_photo_path_agreement", SCRIPT)
assert SPEC is not None and SPEC.loader is not None
checker = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(checker)

PHOTO_RULE = r"^assets\/products\/photo-[0-9a-f]{16}\.(jpg|png)$"
PASS = "PASS owner_photo_path_agreement"
FAIL = "FAIL owner_photo_path_agreement"
COUNTS = ("installed 6", "near-misses 8")


def declaration(pattern):
    return f"const installedImage=s=>typeof s==='string'&&/{pattern}/.test(s);"


class OwnerPhotoPathAgreementTests(unittest.TestCase):
    def setUp(self):
        temporary = tempfile.TemporaryDirectory()
        self.addCleanup(temporary.cleanup)
        self.root = Path(temporary.name)
        self.shop = self.root / "shop.js"

    def fixture(self, text):
        self.shop.write_text(text, encoding="utf-8")
        return self.shop

    def invoke(self, path):
        stdout, stderr = io.StringIO(), io.StringIO()
        with patch.object(checker, "SHOP", path), redirect_stdout(stdout), redirect_stderr(stderr):
            code = checker.main([])
        return code, stdout.getvalue(), stderr.getvalue()

    def run_cli(self, *args):
        result = subprocess.run([sys.executable, "-B", str(SCRIPT), *args],
                                cwd=self.root, capture_output=True, text=True, timeout=15)
        return result.returncode, result.stdout, result.stderr

    def assert_run(self, result, code, *lines):
        self.assertEqual(result, (code, "\n".join(lines) + "\n", ""))

    def test_c1_full_pass(self):
        # Quoting/unescaping mistakes must not reject a standalone valid declaration.
        self.assert_run(self.invoke(self.fixture(declaration(PHOTO_RULE))), 0, *COUNTS, PASS)

    def test_c2_findings_trailer(self):
        # A completed comparison with drift must exit 1, not just print a warning.
        path = self.fixture(declaration(r"^never$") + "\n" + declaration(PHOTO_RULE))
        self.assert_run(self.invoke(path), 1, *COUNTS, "FAIL installed-refused site 6", FAIL)

    def test_c2_1_input_unsafe(self):
        # Following a symlink to otherwise valid text would incorrectly pass.
        target = self.fixture(declaration(PHOTO_RULE))
        alias = self.root / "alias.js"
        alias.symlink_to(target)
        for name, path in (("symlink", alias), ("directory", self.root)):
            with self.subTest(kind=name):
                self.assert_run(self.invoke(path), 1, "FAIL input-unsafe shop", FAIL)

    def test_c2_2_input_too_large(self):
        # Source exceeding the cap must not reach extraction even if it starts valid.
        path = self.fixture(declaration(PHOTO_RULE) + " " * 1_000_000)
        self.assert_run(self.invoke(path), 1, "FAIL input-too-large shop", FAIL)

    def test_c2_3_input_unreadable(self):
        # Loader failures must not fall through to regex parsing or expose data.
        expected = ("FAIL input-unreadable shop", FAIL)
        with self.subTest(kind="missing"):
            self.assert_run(self.invoke(self.shop), 1, *expected)
        with self.subTest(kind="invalid UTF-8"):
            self.shop.write_bytes(declaration(PHOTO_RULE).encode() + b"\xff")
            self.assert_run(self.invoke(self.shop), 1, *expected)
        # SHOP is UTF-8 JavaScript, not JSON. Inject the other specified failures
        # at the read boundary rather than treating arbitrary JS text as JSON.
        path = self.fixture(declaration(PHOTO_RULE))
        with self.subTest(kind="invalid JSON"), patch.object(
            Path, "open", side_effect=json.JSONDecodeError("synthetic", "{", 1)
        ):
            self.assert_run(self.invoke(path), 1, *expected)
        with self.subTest(kind="wrong shape"), patch.object(
            Path, "open", return_value=io.StringIO(declaration(PHOTO_RULE))
        ):
            self.assert_run(self.invoke(path), 1, *expected)

    def test_c2_4_js_regex_missing(self):
        # Unanchored source is refused even if fullmatch could make it pass.
        for text in ("// no declaration", declaration(PHOTO_RULE[1:]), declaration(PHOTO_RULE[:-1])):
            with self.subTest(text=text):
                self.assert_run(self.invoke(self.fixture(text)), 1, "FAIL js-regex-missing", FAIL)

    def test_c2_5_js_regex_invalid(self):
        # A malformed regex must not leak Python's parser diagnostic.
        path = self.fixture(declaration(r"^[$"))
        self.assert_run(self.invoke(path), 1, "FAIL js-regex-invalid", FAIL)

    def test_c2_6_installed_refused(self):
        # The check must report per-rule counts, not the first rejection or a total.
        path = self.fixture(declaration(PHOTO_RULE.replace("jpg|png", "jpg")))
        with patch.object(checker.content_model, "HOME_IMAGE_RE", re.compile(r"never")), \
             patch.object(checker.house_style, "OWNER_IMAGE_RE", re.compile(r"assets/products/photo-0{16}\.jpg")):
            self.assert_run(self.invoke(path), 1, *COUNTS,
                            "FAIL installed-refused home 6", "FAIL installed-refused owner 5",
                            "FAIL installed-refused site 3", FAIL)

    def test_c2_7_near_miss_disagree(self):
        # Any accepting rule is enough, even if both Python rules still reject.
        rule = PHOTO_RULE.replace("[0-9a-f]", "[0-9a-fA-F]").replace("jpg|png", "jpg|png|jpeg")
        self.assert_run(self.invoke(self.fixture(declaration(rule))), 1, *COUNTS,
                        "FAIL near-miss-disagree 1", "FAIL near-miss-disagree 4", FAIL)

    def test_c2_8_check_error(self):
        # An installer exception must fail closed without printing its message.
        path = self.fixture(declaration(PHOTO_RULE))
        with patch.object(checker.item_picture, "installed_names", side_effect=RuntimeError("synthetic")):
            self.assert_run(self.invoke(path), 1, "FAIL check-error", FAIL)

    def test_c3_usage_exit_2(self):
        # Argparse would normally special-case help and a bare end-of-options marker.
        for arg in ("extra", "--unknown", "-h", "--help", "--"):
            with self.subTest(arg=arg):
                code, stdout, stderr = self.run_cli(arg)
                self.assertEqual(code, 2)
                self.assertEqual(stdout, "")
                self.assertIn("error:", stderr.splitlines()[-1])

    def test_c4_read_only(self):
        # Catch new files, rewrites, and changes to directory entries under either tree.
        def snapshot():
            entries = {}
            for tree in (ROOT / "hass", ROOT / "storefront-mockup"):
                for path in (tree, *tree.rglob("*")):
                    info = path.lstat()
                    entries[path.relative_to(ROOT)] = (info.st_size, info.st_mtime_ns)
            return entries

        before = snapshot()
        self.assert_run(self.run_cli(), 0, *COUNTS, PASS)
        self.assertEqual(snapshot(), before)

    def test_c5_output_shape(self):
        # A real check failure must report labels/counts only, not source or paths.
        path = self.fixture("// synthetic marker\n" + declaration(PHOTO_RULE.replace("png", "webp")))
        self.assert_run(self.invoke(path), 1, *COUNTS,
                        "FAIL installed-refused site 3", "FAIL near-miss-disagree 5", FAIL)

    def test_c6_fixture_pass(self):
        # A one-extension storefront drift must report just the webp probe.
        original = checker.SHOP.read_text(encoding="utf-8")
        self.assert_run(self.invoke(self.fixture(original)), 0, *COUNTS, PASS)
        self.assertIn("(jpg|png)", original)
        drifted = original.replace("(jpg|png)", "(jpg|png|webp)", 1)
        self.assert_run(self.invoke(self.fixture(drifted)), 1, *COUNTS, "FAIL near-miss-disagree 5", FAIL)

    def test_c7_live_pins(self):
        # An unpatched CLI run from elsewhere must resolve the real checkout.
        self.assert_run(self.run_cli(), 0, *COUNTS, PASS)
