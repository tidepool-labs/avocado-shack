"""Offline CLI contract tests for the catalog description overlap audit."""

from contextlib import redirect_stderr, redirect_stdout
import importlib.util
import io
import json
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import patch


ROOT = Path(__file__).resolve().parents[2]
CONTENT = ROOT / "hass/content"
SCRIPT = ROOT / "scripts/hass/catalog_copy_overlap.py"
NAME = "Synthetic Canary Lantern"
SHARED = "Amber robots fold tiny paper moons beside silver ponds."
PASS = "PASS catalog_copy_overlap"
FAIL = "FAIL catalog_copy_overlap"
ONE_PAIR = ["span-words 8", "descriptions 3", "pairs 1", "products 2", "largest 1"]
NO_PAIRS = ["span-words 8", "descriptions 3", "pairs 0", "products 0", "largest 0"]


def snapshot(root):
    return {p.relative_to(root): (p.stat().st_mtime_ns, p.read_bytes() if p.is_file() else None)
            for p in (root, *root.rglob("*"))}


class CatalogCopyOverlapTests(unittest.TestCase):
    def setUp(self):
        temporary = tempfile.TemporaryDirectory(dir=ROOT)
        self.addCleanup(temporary.cleanup)
        self.root = Path(temporary.name).resolve()

    def fixture(self, overlap=False):
        content = self.root / "synthetic-content"
        content.mkdir()
        for path in CONTENT.glob("*.json"):
            shutil.copy2(path, content / path.name)
        products_path = content / "products.json"
        document = json.loads(products_path.read_bytes())
        active = [p for p in document["products"] if p["status"] == "active"]
        descriptions = [
            SHARED,
            SHARED if overlap else "Amber robots fold tiny paper moons beside violet windows.",
            "Wool clouds drift over cobalt hills during midnight rehearsals.",
        ]
        products = [dict(p, id=f"synthetic-{i}", name=f"{NAME} {i}", description=text)
                    for i, (p, text) in enumerate(zip(active, descriptions, strict=False))]
        if not overlap:
            products.extend([
                dict(products[0], id="synthetic-hidden", status="hidden"),
                dict(products[0], id="synthetic-empty", description=""),
            ])
        document["products"] = products
        products_path.write_text(json.dumps(document), encoding="utf-8")
        return content

    def invoke(self, *args):
        return subprocess.run([sys.executable, "-B", str(SCRIPT), *map(str, args)],
                              cwd=self.root, capture_output=True, text=True, timeout=10)

    def assert_result(self, result, code, trailer, lines):
        self.assertEqual(result.returncode, code)
        self.assertEqual(result.stderr, "")
        self.assertEqual(result.stdout.splitlines(), [*lines, trailer])

    def test_c1_full_pass(self):
        # Completing all checks must produce the full report and a success trailer.
        self.assert_result(self.invoke("--content", self.fixture()), 0, PASS, NO_PAIRS)

    def test_c2_findings_trailer(self):
        # A finding must not fall through to a success trailer or emit a second reason.
        content = self.fixture(overlap=True)
        for args, lines in (
            (("--content", self.root / "missing"), ["FAIL unsafe-input"]),
            (("--content", content), [*ONE_PAIR, "FAIL shared-pairs 1 0"]),
        ):
            with self.subTest(reason=lines[-1]):
                self.assert_result(self.invoke(*args), 1, FAIL, lines)

    def test_c2_1_unsafe_input(self):
        # Following a valid directory symlink or treating a file as content would misclassify it.
        content = self.fixture()
        link = self.root / "alias"
        link.symlink_to(content, target_is_directory=True)
        for path in (link, content / "products.json", self.root / "missing"):
            with self.subTest(kind=path.name):
                self.assert_result(self.invoke("--content", path), 1, FAIL, ["FAIL unsafe-input"])

    def test_c2_2_content_invalid(self):
        # Malformed JSON must report a fixed reason, not a traceback or an empty success.
        content = self.fixture()
        (content / "products.json").write_text("not JSON", encoding="utf-8")
        self.assert_result(self.invoke("--content", content), 1, FAIL, ["FAIL content-invalid"])

    def test_c2_3_assets_invalid(self):
        # A pin-read failure cannot silently fall back to a hardcoded span length.
        content = self.fixture()
        spec = importlib.util.spec_from_file_location("catalog_copy_overlap", SCRIPT)
        assert spec is not None and spec.loader is not None
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)
        stdout, stderr = io.StringIO(), io.StringIO()
        with patch("hass.npp.assets", side_effect=OSError(str(content))), \
                redirect_stdout(stdout), redirect_stderr(stderr):
            code = module.main(["--content", str(content)])
        result = subprocess.CompletedProcess([], code, stdout.getvalue(), stderr.getvalue())
        self.assert_result(result, 1, FAIL, ["FAIL assets-invalid"])

    def test_c2_4_shared_pairs(self):
        # The finding must report the actual count and limit, not treat overlap as informational.
        result = self.invoke("--content", self.fixture(overlap=True), "--max-pairs", 0)
        self.assert_result(result, 1, FAIL, [*ONE_PAIR, "FAIL shared-pairs 1 0"])

    def test_c3_usage_exit_2(self):
        # Usage errors must never become findings; diagnostics must not echo argument values.
        for args in (("--content",), ("--max-pairs",), ("--unknown", str(self.root)),
                     ("--max-pairs", "-1"), ("--max-pairs", "1.5"),
                     ("--max-pairs", str(self.root))):
            with self.subTest(flag=args[0]):
                result = self.invoke(*args)
                self.assertEqual(result.returncode, 2)
                self.assertEqual(result.stdout, "")  # No stdout trailer for usage errors.
                self.assertTrue(result.stderr.startswith("usage: "))
                self.assertNotIn(str(self.root), result.stderr)

    def test_c4_read_only(self):
        # Rewrites (even identical bytes) and output sidecars must not touch the inputs.
        content = self.fixture()
        assets = ROOT / "hass/npp/assets"
        pins = assets.parent / "pins.json"
        before = (snapshot(content), snapshot(assets), snapshot(pins))
        self.assert_result(self.invoke("--content", content), 0, PASS, NO_PAIRS)
        self.assertTrue(before == (snapshot(content), snapshot(assets), snapshot(pins)),
                        "input tree changed")

    def test_c5_no_private_values(self):
        # Even a matching pair is reported as counts, never as listing examples or paths.
        content = self.fixture(overlap=True)
        result = self.invoke("--content", content)
        for value in (SHARED, NAME, str(content), str(self.root), "synthetic-0", "synthetic-1"):
            self.assertNotIn(value, result.stdout + result.stderr)
        self.assert_result(result, 1, FAIL, [*ONE_PAIR, "FAIL shared-pairs 1 0"])

    def test_c6_one_pair(self):
        # Two shared runs in nine words must count as one unordered pair; equality passes.
        content = self.fixture(overlap=True)
        self.assert_result(self.invoke("--content", content), 1, FAIL,
                           [*ONE_PAIR, "FAIL shared-pairs 1 0"])
        self.assert_result(self.invoke("--content", content, "--max-pairs", 1), 0, PASS, ONE_PAIR)

    def test_c7_no_overlap(self):
        # Seven common words, a hidden match and an empty description must not affect the totals.
        result = self.invoke("--content", self.fixture(), "--max-pairs", 0)
        self.assert_result(result, 0, PASS, NO_PAIRS)

    def test_c8_live_overlap(self):
        # Pin the default checkout and the real NPP tokenization against catalog drift.
        self.assert_result(self.invoke(), 1, FAIL, [
            "span-words 8", "descriptions 170", "pairs 139", "products 46", "largest 10",
            "FAIL shared-pairs 139 0",
        ])
