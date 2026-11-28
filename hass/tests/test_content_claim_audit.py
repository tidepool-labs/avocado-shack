"""Offline CLI contract tests using synthetic catalog copies."""

from contextlib import redirect_stderr, redirect_stdout
import importlib.util
import io
import json
from pathlib import Path
import subprocess
import sys
from tempfile import TemporaryDirectory
import unittest


SCRIPT = Path(__file__).resolve().parents[2] / "scripts/hass/content_claim_audit.py"
PASS = "PASS content_claim_audit"
FAIL = "FAIL content_claim_audit"


def product(product_id, **fields):
    return {"id": product_id, "status": "active", "category": "fruit", **fields}


def source(kind, *lines):
    return {"source": kind, "photo": "a" * 64, "text": list(lines)}


class ContentClaimAuditTests(unittest.TestCase):
    def setUp(self):
        temporary = TemporaryDirectory()
        self.addCleanup(temporary.cleanup)
        self.root = Path(temporary.name).resolve()
        self.content = self.root / "synthetic-catalog"
        self.content.mkdir()

    def write(self, filename, **fields):
        (self.content / filename).write_text(json.dumps({"schemaVersion": 1, **fields}), encoding="utf-8")

    def catalog(self, *products):
        self.write("products.json", products=products)
        self.write("makers.json", makers={})
        self.write("community.json")
        self.write("store.json")

    def cli(self, *args):
        return subprocess.run([sys.executable, "-B", str(SCRIPT), *args], cwd=self.root,
                              capture_output=True, text=True, timeout=10)

    def audit(self):
        return self.cli("--content", str(self.content))

    def assert_report(self, result, code, *lines):
        self.assertEqual(result.returncode, code)
        self.assertEqual(result.stdout, "\n".join(lines) + "\n")
        self.assertEqual(result.stderr, "")

    def test_c1_full_pass(self):
        # An audit must count active records even with empty copy, without scanning other fields.
        self.catalog(product("fixture-plain", description="Crisp slices.", imageAlt="Cures colds."),
                     product("fixture-missing"), product("fixture-nontext", description=["Cures colds."]),
                     None, ["not a product object"])
        self.assert_report(self.audit(), 0, "active 3", "note malformed 2", "note origin 0", PASS)

    def test_c2_1_unsafe_input(self):
        # Following a directory symlink, or opening a regular file, is not an input copy.
        self.catalog()
        link = self.root / "alias"
        link.symlink_to(self.content, target_is_directory=True)
        for path in (link, self.content / "products.json", self.root / "absent"):
            with self.subTest(path=path.name):
                self.assert_report(self.cli("--content", str(path)), 1, "FAIL unsafe-input", FAIL)

    def test_c2_2_content_invalid(self):
        # Invalid envelopes, JSON and UTF-8 must not become passes or tracebacks.
        for raw in (b'{"schemaVersion":0}', b'{', b'\xff'):
            with self.subTest(raw=raw):
                self.catalog()
                (self.content / "store.json").write_bytes(raw)
                self.assert_report(self.audit(), 1, "FAIL content-invalid", FAIL)
        # An incomplete copy must not leak its path in a missing-file traceback.
        self.catalog()
        (self.content / "makers.json").rename(self.content / "not-makers.json")
        self.assert_report(self.audit(), 1, "FAIL content-invalid", FAIL)

    def test_c2_3_claim(self):
        # Multiple kinds on a product count once towards FAIL; origin co-hits do not pardon it.
        self.catalog(product("fixture-z", description="Ask for the price."),
                     product("fixture-y", description="Certified organic."),
                     product("fixture-a", description=("Cures colds. Certified organic. Ask for the price. "
                                                       "See https://catalog.invalid. оrganic.")),
                     product("fixture-b", description="Certified organic."))
        self.assert_report(self.audit(), 1, "active 4", "kind contact 1",
                           "kind health/awards/endorsements 1", "kind origin/organic 3", "kind prices 2",
                           "kind unchecked_claims 1", "note origin 2", "origin fixture-b", "origin fixture-y",
                           "claim fixture-a contact,health/awards/endorsements,origin/organic,prices,unchecked_claims",
                           "claim fixture-z prices", "FAIL claim 2", FAIL)

    def test_c3_usage_exit_2(self):
        # Argument syntax errors are argparse errors, not content findings or path echoes.
        for args in ((), ("--content",), ("--content", str(self.content), "--bogus", str(self.root))):
            with self.subTest(argument_count=len(args)):
                result = self.cli(*args)
                self.assertEqual(result.returncode, 2)
                self.assertEqual(result.stdout, "")  # There is no last stdout line for C3.
                self.assertTrue(result.stderr.startswith("usage: "))
                self.assertNotIn(str(self.root), result.stderr)

    def test_c4_read_only(self):
        # Even a finding must not normalize the copy or leave a report or temporary directory in it.
        self.catalog(product("fixture-readonly", description="Cures colds."))

        def snapshot():
            return {path.relative_to(self.content): (path.stat().st_mtime_ns,
                                                      None if path.is_dir() else path.read_bytes())
                    for path in (self.content, *self.content.rglob("*"))}

        before = snapshot()
        self.assert_report(self.audit(), 1, "active 1", "kind health/awards/endorsements 1",
                           "note origin 0", "claim fixture-readonly health/awards/endorsements", "FAIL claim 1", FAIL)
        self.assertEqual(snapshot(), before)

    def test_c5_no_private_values(self):
        # Findings must emit kinds only; errors must not print even loader-supplied diagnostics.
        description = "Cures colds. Synthetic description marker."
        label = "Synthetic label marker."
        owner = "Synthetic owner marker."
        self.catalog(product("fixture-privacy", description=description, labelSource=source("label", label),
                             ownerSource=source("owner", owner)))
        result = self.audit()
        for canary in (description, label, owner, str(self.content)):
            self.assertFalse(canary in result.stdout or canary in result.stderr, "private input was echoed")
        self.assertEqual(result.returncode, 1)
        self.assertEqual(result.stdout.splitlines()[-2:], ["FAIL claim 1", FAIL])
        self.assertIn("kind health/awards/endorsements 1", result.stdout.splitlines())
        self.assertEqual(result.stderr, "")

        # An unknown root key is echoed by ContentError itself, but must not escape main().
        self.write("products.json", products=[], **{str(self.content): label})
        spec = importlib.util.spec_from_file_location("content_claim_audit", SCRIPT)
        assert spec is not None and spec.loader is not None
        audit = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(audit)
        stdout, stderr = io.StringIO(), io.StringIO()
        with redirect_stdout(stdout), redirect_stderr(stderr):
            code = audit.main(["--content", str(self.content)])
        self.assertEqual(code, 1)
        self.assertEqual(stdout.getvalue(), "FAIL content-invalid\nFAIL content_claim_audit\n")
        self.assertEqual(stderr.getvalue(), "")

    def test_c6_label_attribution(self):
        # Ignoring provenance (or accepting the quote without evidence) changes the origin count.
        description = 'Label says: "certified organic"'
        self.catalog(product("fixture-sourced", description=description,
                             labelSource=source("label", "certified organic")),
                     product("fixture-unsourced", description=description))
        self.assert_report(self.audit(), 0, "active 2", "kind origin/organic 1", "note origin 1",
                           "origin fixture-unsourced", PASS)

    def test_c7_name_exemption(self):
        # An omitted name exemption flags the sourced name; globally reusing names masks the other row.
        description = "From Harbor Lane Farm."
        self.catalog(product("fixture-brand", brand="Harbor Lane Farm", description=description),
                     product("fixture-no-brand", description=description))
        self.assert_report(self.audit(), 0, "active 2", "kind origin/organic 1", "note origin 1",
                           "origin fixture-no-brand", PASS)

    def test_c8_hidden_not_screened(self):
        # Screening every product would report this health copy even though it isn't active.
        self.catalog(product("fixture-hidden", status="hidden", description="Cures colds."),
                     product("fixture-held", status="held", description="Cures colds."))
        self.assert_report(self.audit(), 0, "active 0", "note origin 0", PASS)
