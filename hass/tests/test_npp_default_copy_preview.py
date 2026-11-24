"""Behavioral contract for the offline, counts-only NPP preview CLI."""

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
SCRIPT = ROOT / "scripts/hass/npp_default_copy_preview.py"
PASS = "PASS npp_default_copy_preview"
FAIL = "FAIL npp_default_copy_preview"
NAME = "Canary orchard jam"
DESCRIPTION = "Canary description sentence about an imaginary orchard."

spec = importlib.util.spec_from_file_location("npp_default_copy_preview", SCRIPT)
assert spec is not None and spec.loader is not None
preview = importlib.util.module_from_spec(spec)
spec.loader.exec_module(preview)


class NppDefaultCopyPreviewTests(unittest.TestCase):
    def setUp(self):
        temporary = tempfile.TemporaryDirectory()
        self.addCleanup(temporary.cleanup)
        self.root = Path(temporary.name).resolve()
        self.content = self.root / "synthetic-catalog"
        self.content.mkdir()
        for source in CONTENT.glob("*.json"):
            shutil.copyfile(source, self.content / source.name)

    def products(self, *rows):
        path = self.content / "products.json"
        document = json.loads(path.read_text(encoding="utf-8"))
        document["products"] = [
            dict(id=f"fixture-product-{index}", name=name, category=category, status=status,
                 description=DESCRIPTION, brand="", image="assets/products/fixture.webp",
                 producerKey="", displayBrand="")
            for index, (name, category, status) in enumerate(rows)
        ]
        path.write_text(json.dumps(document), encoding="utf-8")

    def cli(self, *options):
        return subprocess.run([sys.executable, "-B", str(SCRIPT), *map(str, options)],
                              cwd=self.root, capture_output=True, text=True, timeout=60)

    def run_fixture(self, *options):
        return self.cli("--content", self.content, *options)

    def in_process(self):
        stdout, stderr = io.StringIO(), io.StringIO()
        with redirect_stdout(stdout), redirect_stderr(stderr):
            code = preview.main(["--content", str(self.content)])
        return subprocess.CompletedProcess([], code, stdout.getvalue(), stderr.getvalue())

    def assert_report(self, result, code, *lines):
        self.assertEqual(result.returncode, code)
        self.assertEqual(result.stderr, "")
        self.assertEqual(result.stdout.splitlines(), list(lines))

    def test_c1_full_pass(self):
        # A check with no active rows still runs and reports a successful zero tally.
        self.products(("Inactive jam", "pantry", "hidden"), ("Held juice", "drinks", "held"))
        self.assert_report(self.run_fixture(), 0, "products 0", "copy 0", "no-copy 0",
                           "no-copy-reason item-not-plain 0", "no-copy-reason other 0", PASS)

    def test_c2_findings_trailer(self):
        # A late failure must not present partial results or finish with the PASS trailer.
        self.products(("Raspberry jam", "pantry", "active"), ("Apple juice", "drinks", "active"))
        write = preview.copy.Writer.write

        def fail_second(writer, context, selector):
            if context.category == "drinks":
                raise RuntimeError(DESCRIPTION)
            return write(writer, context, selector)

        with patch.object(preview.copy.Writer, "write", fail_second):
            self.assert_report(self.in_process(), 1, "FAIL writer-error", FAIL)

    def test_c2_1_unsafe_input(self):
        # Following links or loading a file/missing directory would misclassify these.
        link = self.root / "catalog-link"
        link.symlink_to(self.content, target_is_directory=True)
        missing = self.root / "absent"
        dangling = self.root / "dangling"
        dangling.symlink_to(missing, target_is_directory=True)
        for path in (link, dangling, missing, self.content / "products.json"):
            with self.subTest(path=path.name):
                self.assert_report(self.cli("--content", path), 1, "FAIL unsafe-input", FAIL)

    def test_c2_2_content_invalid(self):
        # Malformed JSON is not an empty catalog or an unhandled traceback.
        (self.content / "products.json").write_text("{", encoding="utf-8")
        self.assert_report(self.run_fixture(), 1, "FAIL content-invalid", FAIL)

    def test_c2_3_assets_invalid(self):
        # A pin load failure must not be ignored or misreported as a writer error.
        self.products((NAME, "pantry", "active"))
        with patch.object(preview.npp, "assets", side_effect=ValueError(DESCRIPTION)):
            self.assert_report(self.in_process(), 1, "FAIL assets-invalid", FAIL)

    def test_c2_4_writer_error(self):
        # Neither a per-item exception nor a constructor failure is a normal no-copy result.
        self.products((NAME, "pantry", "active"))
        error = RuntimeError(f"{NAME}: {DESCRIPTION} {self.content}")
        with patch.object(preview.copy.Writer, "write", side_effect=error):
            self.assert_report(self.in_process(), 1, "FAIL writer-error", FAIL)
        with patch.object(preview.copy, "Writer", side_effect=error):
            self.assert_report(self.in_process(), 1, "FAIL writer-error", FAIL)

    def test_c2_5_no_copy_over(self):
        # The failure reports both the measured count and the caller's nondefault limit.
        self.products(("Jam (large)", "pantry", "active"), ("Juice (large)", "drinks", "active"))
        self.assert_report(self.run_fixture("--max-no-copy", 1), 1,
                           "products 2", "copy 0", "no-copy 2", "no-copy-reason item-not-plain 2",
                           "no-copy-reason other 0", "FAIL no-copy-over 2 1", FAIL)

    def test_c3_usage_exit_2(self):
        # Parser errors must not fall through to the tool's finding or totals output.
        for args in (("--content",), ("--unknown",), ("--owner-words", "label"),
                     ("--max-no-copy", "-1"), ("--max-no-copy", "1.5")):
            with self.subTest(args=args):
                result = self.cli(*args)
                self.assertEqual(result.returncode, 2)
                self.assertEqual(result.stdout, "")  # No trailer on usage errors.
                self.assertTrue(result.stderr.startswith("usage:"))

    def test_c4_read_only(self):
        # An overwrite, touch or newly created sidecar must change this snapshot.
        self.products((NAME, "pantry", "active"))

        def snapshot():
            return {p.relative_to(self.content): (p.stat().st_mtime_ns, p.read_bytes() if p.is_file() else None)
                    for p in (self.content, *self.content.rglob("*"))}

        before = snapshot()
        self.assert_report(self.run_fixture(), 0, "products 1", "copy 1", "no-copy 0",
                           "template desc-food-default 1", "no-copy-reason item-not-plain 0",
                           "no-copy-reason other 0", PASS)
        self.assertEqual(snapshot(), before)

    def test_c5_no_private_values(self):
        # Catch row dumps, unsanitized loader exceptions and argparse value echoes.
        self.products((NAME, "pantry", "active"), ("Canary drink", "drinks", "active"))
        result = self.run_fixture()
        self.assertEqual(result.returncode, 0)
        self.assertEqual(result.stdout.splitlines()[-1], PASS)
        usage = self.cli("--unknown", self.content)
        self.assertEqual(usage.returncode, 2)
        self.assertEqual(usage.stdout, "")
        error = ValueError(f"{NAME}: {DESCRIPTION} {self.content}")
        with patch.object(preview.content_model, "load_content", side_effect=error):
            invalid = self.in_process()
        self.assert_report(invalid, 1, "FAIL content-invalid", FAIL)
        for value in (NAME, DESCRIPTION, str(self.content), "fixture-product-0", "Canary drink"):
            self.assertFalse(any(value in run.stdout + run.stderr for run in (result, invalid, usage)),
                             "private input echoed")

    def test_c6_two_products(self):
        # Using one kind for both categories or emitting the wrong template ID fails.
        self.products(("Raspberry jam", "pantry", "active"), ("Apple juice", "drinks", "active"))
        self.assert_report(self.run_fixture(), 0, "products 2", "copy 2", "no-copy 0",
                           "template desc-drink-default 1", "template desc-food-default 1",
                           "no-copy-reason item-not-plain 0", "no-copy-reason other 0", PASS)

    def test_c7_not_plain(self):
        # Parenthesized names stay in the not-plain bucket; equality must pass the cap.
        self.products(("Olive oil (large)", "pantry", "active"))
        counts = ("products 1", "copy 0", "no-copy 1", "no-copy-reason item-not-plain 1", "no-copy-reason other 0")
        self.assert_report(self.run_fixture(), 1, *counts, "FAIL no-copy-over 1 0", FAIL)
        self.assert_report(self.run_fixture("--max-no-copy", 1), 0, *counts, PASS)

    def test_c8_live_preview(self):
        # The checked-in snapshot catches changes to the real fallback mix and the owner-words toggle.
        self.assert_report(self.cli(), 1, "products 170", "copy 166", "no-copy 4",
                           "template desc-drink-default 14", "template desc-flowers-default 1",
                           "template desc-food-default 86", "template desc-fresh-default 65",
                           "no-copy-reason item-not-plain 2", "no-copy-reason other 2", "FAIL no-copy-over 4 0", FAIL)
        self.assert_report(self.cli("--owner-words", "none"), 1, "products 170", "copy 159", "no-copy 11",
                           "template desc-drink-default 9", "template desc-flowers-default 1",
                           "template desc-food-default 84", "template desc-fresh-default 65",
                           "no-copy-reason item-not-plain 9", "no-copy-reason other 2", "FAIL no-copy-over 11 0", FAIL)
