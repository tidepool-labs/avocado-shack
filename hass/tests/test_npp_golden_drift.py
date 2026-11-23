"""Offline CLI contract tests for the golden/catalog comparison."""

from contextlib import redirect_stderr, redirect_stdout
import importlib.util
import io
import json
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest


ROOT = Path(__file__).resolve().parents[2]
SCRIPT = ROOT / "scripts/hass/npp_golden_drift.py"
PRODUCT = {
    "id": "fixture-item", "status": "active", "name": "Fixture bread",
    "displayBrand": "Fixture Bakery", "description": "A crusty loaf.", "category": "bread",
}
PASS = "PASS npp_golden_drift"
FAIL = "FAIL npp_golden_drift"


class GoldenDriftTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        spec = importlib.util.spec_from_file_location("npp_golden_drift", SCRIPT)
        assert spec is not None and spec.loader is not None
        cls.cli = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(cls.cli)

    def setUp(self):
        temporary = tempfile.TemporaryDirectory()
        self.addCleanup(temporary.cleanup)
        self.root = Path(temporary.name)
        self.content = self.root / "content"
        self.goldens = self.root / "golden"
        self.content.mkdir()
        self.goldens.mkdir()
        self.products = self.content / "products.json"
        self.golden = self.goldens / "reference.json"
        self.args = ["--content", str(self.content), "--golden", str(self.goldens)]

    def write_json(self, path, data):
        path.write_text(json.dumps(data), encoding="utf-8")

    def write_products(self, *rows):
        self.write_json(self.products, {"products": list(rows)})

    def golden_record(self, product_id="fixture-item"):
        return {
            "product_id": product_id, "category": "bread",
            "card": {"name": "Fixture bread", "brand": "Fixture Bakery", "description": "A crusty loaf."},
        }

    def invoke(self, args=None):
        stdout, stderr = io.StringIO(), io.StringIO()
        with redirect_stdout(stdout), redirect_stderr(stderr):
            try:
                code = self.cli.main(self.args if args is None else args)
            except SystemExit as exc:
                code = exc.code
        return code, stdout.getvalue(), stderr.getvalue()

    def assert_report(self, result, *, goldens, matched, findings=()):
        code, stdout, stderr = result
        self.assertEqual(code, 1 if findings else 0)
        self.assertEqual(stderr, "")
        self.assertEqual(stdout.splitlines(), [
            f"goldens {goldens}", f"matched {matched}", *findings, FAIL if findings else PASS,
        ])

    def test_c1_full_pass(self):
        # A filename-based lookup or use of the wrong brand field rejects this exact match.
        self.write_products(dict(PRODUCT, brand="Not the display brand"))
        self.write_json(self.golden, self.golden_record())
        (self.goldens / "ignore.txt").write_text("not JSON", encoding="utf-8")
        self.assert_report(self.invoke(), goldens=1, matched=1)

    def test_c2_1_unreadable_products(self):
        # Missing, symlinked, non-UTF-8 and wrong-shaped input must not look like missing ids.
        self.write_json(self.golden, self.golden_record())
        check = dict(goldens=1, matched=0, findings=["FAIL unreadable products"])
        with self.subTest(input="absent"):
            self.assert_report(self.invoke(), **check)
        for tag, payload in (
            ("non-UTF-8", b'\xff'), ("malformed", b'{"products":'),
            ("not an object", b'[]'), ("missing list", b'{}'),
            ("wrong list type", b'{"products":{}}'), ("non-JSON constant", b'{"products":[NaN]}'),
        ):
            with self.subTest(input=tag):
                self.products.write_bytes(payload)
                self.assert_report(self.invoke(), **check)
        with self.subTest(input="symlink to valid JSON"):
            target = self.root / "catalog.json"
            self.write_json(target, {"products": [PRODUCT]})
            alternate = self.root / "alternate-content"
            alternate.mkdir()
            (alternate / "products.json").symlink_to(target)
            self.assert_report(self.invoke(["--content", str(alternate), *self.args[2:]]), **check)

    def test_c2_2_golden_unreadable(self):
        # A JSON parse alone misses absent or non-string fields; errors name only the file.
        self.write_products(PRODUCT)
        check = dict(goldens=1, matched=0, findings=["FAIL golden-unreadable reference.json"])
        for tag, raw in (("malformed", b"{"), ("non-UTF-8", b"\xff")):
            with self.subTest(input=tag):
                self.golden.write_bytes(raw)
                self.assert_report(self.invoke(), **check)
        for field in ("product_id", "category", "name", "brand", "description"):
            for missing in (True, False):
                with self.subTest(field=field, missing=missing):
                    record = self.golden_record()
                    fields = record if field in record else record["card"]
                    if missing:
                        del fields[field]
                    else:
                        fields[field] = 7
                    self.write_json(self.golden, record)
                    self.assert_report(self.invoke(), **check)

    def test_c2_3_golden_missing(self):
        # An id-only join would accept inactive rows; a field-only join would accept a decoy id.
        self.write_json(self.golden, self.golden_record())
        no_status = {k: v for k, v in PRODUCT.items() if k != "status"}
        for tag, row in (
            ("absent id", dict(PRODUCT, id="fixture-other")),
            ("inactive", dict(PRODUCT, status="inactive")), ("absent status", no_status),
        ):
            with self.subTest(input=tag):
                self.write_products(row)
                self.assert_report(self.invoke(), goldens=1, matched=0,
                                   findings=["FAIL golden-missing fixture-item"])

    def test_c2_4_golden_drift(self):
        # Trimming, case folding, or stopping at the first difference loses a field finding.
        self.write_products(dict(PRODUCT, name="Fixture bread ", displayBrand="fixture bakery",
                                 description="A crusty loaf!", category="Bread"),
                            dict(PRODUCT, id="fixture-control"))
        self.write_json(self.golden, self.golden_record())
        self.write_json(self.goldens / "control.json", self.golden_record("fixture-control"))
        self.assert_report(self.invoke(), goldens=2, matched=1, findings=[
            f"FAIL golden-drift fixture-item {field}"
            for field in ("name", "displayBrand", "description", "category")
        ])

    def test_c3_usage_exit_2(self):
        # Absence, unknown flags and absent flag values are usage errors, not findings.
        for args in ([], [*self.args, "--unknown"], ["--content"], [*self.args, "--golden"]):
            with self.subTest(args=args):
                code, stdout, stderr = self.invoke(args)
                self.assertEqual(code, 2)
                self.assertEqual(stdout, "")  # No last stdout line for a usage error.
                self.assertTrue(stderr.startswith("usage: "))

    def test_c4_read_only(self):
        # A normalizing rewrite can preserve bytes but still change the mtime.
        self.write_products(PRODUCT)
        self.write_json(self.golden, self.golden_record())

        def snapshot():
            return {
                path.relative_to(self.root): (path.stat().st_mtime_ns,
                                              path.read_bytes() if path.is_file() else None)
                for path in self.root.rglob("*")
            }

        before = snapshot()
        self.assert_report(self.invoke(), goldens=1, matched=1)
        self.assertEqual(snapshot(), before)
        self.write_products(dict(PRODUCT, description="Different."))
        before = snapshot()
        self.assert_report(self.invoke(), goldens=1, matched=0,
                           findings=["FAIL golden-drift fixture-item description"])
        self.assertEqual(snapshot(), before)

    def test_c5_no_private_values(self):
        # Printing a record, exception, parsed argv or even a diff would expose these canaries.
        canaries = ("canary-message-body", "canary-chat-id", "canary-sender-id",
                    "canary-full-record-id", "canary-full-digest", "canary-golden-description")
        message, chat, sender, record_id, digest, description = canaries
        self.write_products(dict(PRODUCT, description=message, chat=chat, sender=sender,
                                 digest=digest), dict(PRODUCT, id=record_id))
        golden = self.golden_record()
        golden["card"]["description"] = description
        self.write_json(self.golden, golden)
        (self.goldens / "malformed.json").write_text(f'{{"extra":"{message}"', encoding="utf-8")
        result = self.invoke()
        self.assert_report(result, goldens=2, matched=0, findings=[
            "FAIL golden-unreadable malformed.json", "FAIL golden-drift fixture-item description",
        ])
        usage = self.invoke([*self.args, str(self.content), sender])
        self.assertEqual(usage[0:2], (2, ""))
        for output in (result[1] + result[2], usage[1] + usage[2]):
            for value in (*canaries, str(self.root), str(self.content), str(self.goldens)):
                self.assertNotIn(value, output)

    def test_c6_repo_smoke(self):
        # The direct CLI must find its shipped defaults without depending on cwd.
        directory = ROOT / "hass/npp/assets/hass-gallery-style/golden"
        shipped_ids = {json.loads(path.read_text(encoding="utf-8"))["product_id"]
                       for path in directory.glob("*.json")}
        result = subprocess.run([sys.executable, "-B", str(SCRIPT), "--content", str(ROOT / "hass/content")],
                                cwd=self.root, capture_output=True, text=True, timeout=10)
        self.assertIn(result.returncode, (0, 1))
        lines = result.stdout.splitlines()
        self.assertEqual(lines[-1], PASS if result.returncode == 0 else FAIL)
        for line in lines:
            if line.startswith(("FAIL golden-missing ", "FAIL golden-drift ")):
                self.assertTrue(line.split()[2] in shipped_ids, "reported id does not belong to a shipped golden")
