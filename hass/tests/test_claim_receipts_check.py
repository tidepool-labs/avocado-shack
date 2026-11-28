"""Fixture-only contract tests for the offline claim receipt CLI."""

from contextlib import redirect_stderr, redirect_stdout
import hashlib
import importlib.util
import io
import json
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest

from hass.media import SIDECAR_MAX


SCRIPT = Path(__file__).resolve().parents[2] / "scripts/hass/claim_receipts_check.py"
PASS = "PASS claim_receipts_check"
FAIL = "FAIL claim_receipts_check"
FOLDERS = {"label": "labels", "owner": "owner-claims"}


class ClaimReceiptsCheckTests(unittest.TestCase):
    def setUp(self):
        temporary = tempfile.TemporaryDirectory()
        self.addCleanup(temporary.cleanup)
        self.root = Path(temporary.name).resolve()
        self.content = self.root / "synthetic-content"
        self.media = self.root / "synthetic-media"
        self.content.mkdir()
        self.media.mkdir()
        self.label = {"source": "label", "photo": "a1" * 32,
                      "text": ["fixture-label-line-one", "fixture-label-line-two"]}
        self.owner = {"source": "owner", "photo": "b2" * 32,
                      "text": ["fixture-owner-café", "fixture-owner-line-two"]}
        self.product = {"name": "fixture-product-name", "id": "fixture-product-id",
                        "status": "hidden", "labelSource": self.label, "ownerSource": self.owner}
        for filename, payload in (("makers.json", {"makers": {}}), ("community.json", {}),
                                  ("store.json", {})):
            self.write_json(self.content / filename, {"schemaVersion": 1, **payload})
        self.write_products([self.product])

    @staticmethod
    def write_json(path, value):
        path.write_text(json.dumps(value), encoding="utf-8")

    def write_products(self, products):
        self.write_json(self.content / "products.json", {"schemaVersion": 1, "products": products})

    def receipt_path(self, claim, *, suffix_text=None):
        folder = self.media / FOLDERS[claim["source"]]
        folder.mkdir(exist_ok=True)
        filename = claim["photo"]
        if claim["source"] == "owner":
            text = claim["text"] if suffix_text is None else suffix_text
            filename += "-" + hashlib.sha256(json.dumps(text, sort_keys=True).encode()).hexdigest()
        return folder / (filename + ".json")

    def invoke(self, *args):
        return subprocess.run([sys.executable, "-B", str(SCRIPT), *map(str, args)],
                              cwd=self.root, capture_output=True, text=True, timeout=10)

    def check(self, *, content=None, media=None):
        return self.invoke("--content", content or self.content, "--media", media or self.media)

    def assert_report(self, result, code, *lines):
        # Compare the complete line sequence, including the exact terminal verdict.
        self.assertEqual(result.returncode, code)
        self.assertEqual(result.stdout.splitlines(), [*lines, FAIL if code else PASS])
        self.assertEqual(result.stderr, "")

    def snapshot(self):
        snapshot = {}
        for root in (self.content, self.media):
            for path in (root, *root.rglob("*")):
                snapshot[path] = (path.stat().st_mtime_ns, None if path.is_dir() else path.read_bytes())
        return snapshot

    def test_c1_full_pass(self):
        # Filtering by active status, skipping the owner claim, or counting junk as claims breaks this.
        self.write_products([None, self.product, ["not an object"], {"status": "active"}])
        self.write_json(self.receipt_path(self.label), self.label)
        self.write_json(self.receipt_path(self.owner), self.owner)
        self.assert_report(self.check(), 0, "label-sourced 1", "owner-sourced 1", "receipts-ok 2",
                           "note malformed 2")

    def test_c2_1_unsafe_input(self):
        # A stat/exists check can follow a symlink or overlook a dangling link.
        regular = self.root / "regular"
        regular.touch()
        absent = self.root / "absent"
        for flag, directory in (("content", self.content), ("media", self.media)):
            alias = self.root / (flag + "-alias")
            alias.symlink_to(directory, target_is_directory=True)
            for invalid in (alias, regular, absent):
                with self.subTest(flag=flag, entry=invalid.name):
                    self.assert_report(self.check(**{flag: invalid}), 1, "FAIL unsafe-input")
        for name in FOLDERS.values():
            for entry in ("file", "directory-symlink", "dangling-symlink"):
                with self.subTest(folder=name, entry=entry):
                    with tempfile.TemporaryDirectory(dir=self.root) as backing:
                        media = Path(backing)
                        if entry == "file":
                            (media / name).touch()
                        else:
                            target = self.root if entry == "directory-symlink" else absent
                            (media / name).symlink_to(target, target_is_directory=True)
                        self.assert_report(self.check(media=media), 1, "FAIL unsafe-input")

    def test_c2_2_content_invalid(self):
        # Reading only products or echoing loader exceptions breaks this.
        for data in (b'{"schemaVersion": 2}', b'{"schemaVersion": 1,"schemaVersion": 1}',
                     b'{bad json', b'\xff'):
            with self.subTest(data=data):
                (self.content / "store.json").write_bytes(data)
                self.assert_report(self.check(), 1, "FAIL content-invalid")

    def test_c2_3_bad_provenance(self):
        # Testing truthiness or validating an owner claim as a label loses these failures.
        self.write_products([{**self.product, "labelSource": None, "ownerSource": self.label}])
        self.assert_report(self.check(), 1, "label-sourced 1", "owner-sourced 1", "receipts-ok 0",
                           "FAIL bad-provenance 2")

    def test_c2_4_receipt_missing(self):
        # An existing folder is not evidence that a specific receipt exists; report both findings.
        self.receipt_path(self.label)
        self.receipt_path(self.owner)
        self.write_products([self.product, {"labelSource": None}])
        self.assert_report(self.check(), 1, "label-sourced 2", "owner-sourced 1", "receipts-ok 0",
                           "FAIL bad-provenance 1", "FAIL receipt-missing 2")

    def test_c2_5_receipt_unsafe(self):
        # A successful read through a symlink must not validate the receipt; directories aren't receipts.
        target = self.root / "decoy.json"
        self.write_json(target, self.label)
        self.receipt_path(self.label).symlink_to(target)
        self.receipt_path(self.owner).mkdir()
        self.assert_report(self.check(), 1, "label-sourced 1", "owner-sourced 1", "receipts-ok 0",
                           "FAIL receipt-unsafe 2")

    def test_c2_6_receipt_mismatch(self):
        # Check the byte cap and each receipt field independently, not merely existence or overlap.
        self.write_products([{"labelSource": self.label}])
        path = self.receipt_path(self.label)
        good = json.dumps(self.label).encode()
        capped = good.ljust(SIDECAR_MAX, b" ")
        path.write_bytes(capped)
        self.assert_report(self.check(), 0, "label-sourced 1", "owner-sourced 0", "receipts-ok 1")
        for name, data in (
            ("too large", capped + b" "), ("bad encoding", b"\xff"), ("bad JSON", b"{"),
            ("non-object", json.dumps([self.label]).encode()),
            ("wrong source", json.dumps({**self.label, "source": "owner"}).encode()),
            ("wrong photo", json.dumps({**self.label, "photo": self.owner["photo"]}).encode()),
            ("non-list text", json.dumps({**self.label, "text": "not a list"}).encode()),
            ("non-string line", json.dumps({**self.label, "text": [*self.label["text"], 1]}).encode()),
            ("missing line", json.dumps({**self.label, "text": self.label["text"][:1]}).encode()),
        ):
            with self.subTest(case=name):
                path.write_bytes(data)
                self.assert_report(self.check(), 1, "label-sourced 1", "owner-sourced 0", "receipts-ok 0",
                                   "FAIL receipt-mismatch 1")

    def test_c3_usage_exit_2(self):
        # Missing or malformed flags must not be reported as catalog findings.
        for args in (("--media", self.media), ("--content", self.content),
                     ("--content", self.content, "--media"),
                     ("--content", self.content, "--media", self.media, "--unknown")):
            with self.subTest(args=tuple(str(arg) for arg in args if isinstance(arg, str))):
                result = self.invoke(*args)
                self.assertEqual(result.returncode, 2)
                self.assertEqual(result.stdout, "")  # No terminal stdout line on usage errors.
                self.assertIn("usage:", result.stderr)

    def test_c4_read_only(self):
        # Detect a rewrite even when it writes identical bytes, or creates a sidecar.
        self.write_json(self.receipt_path(self.label), self.label)
        self.write_json(self.receipt_path(self.owner), self.owner)
        before = self.snapshot()
        spec = importlib.util.spec_from_file_location("claim_receipts_check", SCRIPT)
        assert spec is not None and spec.loader is not None
        checker = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(checker)
        stdout, stderr = io.StringIO(), io.StringIO()
        with redirect_stdout(stdout), redirect_stderr(stderr):
            code = checker.main(["--content", str(self.content), "--media", str(self.media)])
        self.assertEqual(code, 0)
        self.assertEqual(stdout.getvalue().splitlines(),
                         ["label-sourced 1", "owner-sourced 1", "receipts-ok 2", PASS])
        self.assertEqual(stderr.getvalue(), "")
        self.assertEqual(self.snapshot(), before)

    def test_c5_no_private_values(self):
        # Debugging output, decode exceptions or raw loader diagnostics could leak private values.
        valid_path = self.receipt_path(self.label)
        self.write_json(valid_path, self.label)
        self.receipt_path(self.owner).write_text(self.owner["text"][0], encoding="utf-8")
        mismatch = self.check()
        self.assert_report(mismatch, 1, "label-sourced 1", "owner-sourced 1", "receipts-ok 1",
                           "FAIL receipt-mismatch 1")
        self.write_json(self.content / "products.json", {"schemaVersion": 1, "products": [self.product],
                                                         self.product["name"]: None})
        invalid = self.check()
        self.assert_report(invalid, 1, "FAIL content-invalid")
        usage = self.invoke("--content", self.content, "--media", self.media, self.content)
        self.assertEqual((usage.returncode, usage.stdout), (2, ""))
        for result in (mismatch, invalid, usage):
            for value in (*self.label["text"], *self.owner["text"], self.label["photo"], self.owner["photo"],
                          self.product["name"], self.product["id"], str(self.content), str(self.media)):
                self.assertFalse(value in result.stdout or value in result.stderr, "private value leaked")

    def test_c6_no_folder_created(self):
        # The ordinary source() reader creates directories even for missing receipts.
        before = self.snapshot()
        self.assert_report(self.check(), 1, "label-sourced 1", "owner-sourced 1", "receipts-ok 0",
                           "FAIL receipt-missing 2")
        self.assertEqual(list(self.media.iterdir()), [])
        self.assertEqual(self.snapshot(), before)

    def test_c7_extra_lines_ok(self):
        # Equality/order checks or deriving the owner filename from receipt text would reject this.
        for claim in (self.label, self.owner):
            receipt = {**claim, "text": ["extra fixture line", *reversed(claim["text"])]}
            self.write_json(self.receipt_path(claim), receipt)
        self.assert_report(self.check(), 0, "label-sourced 1", "owner-sourced 1", "receipts-ok 2")

    def test_c8_owner_suffix_rule(self):
        # A photo-prefix scan could accidentally accept a decoy at a different text digest.
        self.write_products([{"ownerSource": self.owner}])
        self.write_json(self.receipt_path(self.owner, suffix_text=list(reversed(self.owner["text"]))), self.owner)
        self.assert_report(self.check(), 1, "label-sourced 0", "owner-sourced 1", "receipts-ok 0",
                           "FAIL receipt-missing 1")


if __name__ == "__main__":
    unittest.main()
