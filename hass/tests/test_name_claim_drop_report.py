"""Offline CLI contracts for the counts-only NPP name report."""

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

from hass.content_model import CONTENT_DIR


SCRIPT = Path(__file__).resolve().parents[2] / "scripts/hass/name_claim_drop_report.py"
SPEC = importlib.util.spec_from_file_location("name_claim_drop_report", SCRIPT)
assert SPEC is not None and SPEC.loader is not None
REPORT = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(REPORT)
PASS = "PASS name_claim_drop_report"
FAIL = "FAIL name_claim_drop_report"
ORIGIN = "unconfirmed origin or organic wording"


class NameClaimDropReportTests(unittest.TestCase):
    def setUp(self):
        temp = tempfile.TemporaryDirectory()
        self.addCleanup(temp.cleanup)
        self.root = Path(temp.name).resolve()
        self.content = self.root / "synthetic-content"
        self.content.mkdir()
        for source in CONTENT_DIR.glob("*.json"):
            shutil.copyfile(source, self.content / source.name)
        self.products_file = self.content / "products.json"
        self.data = json.loads(self.products_file.read_text(encoding="utf-8"))
        self.data["products"] = []
        self.add_product("z-sample-jam", "Raspberry jam")
        self.add_product("a-sample-juice", "Apple juice")

    def add_product(self, identifier, name, status="active"):
        self.data["products"].append({"id": identifier, "name": name, "status": status})
        self.products_file.write_text(json.dumps(self.data), encoding="utf-8")

    def add_organic(self):
        self.add_product("b-sample-beet", "Organic beet juice")

    def cli(self, *args):
        result = subprocess.run(
            [sys.executable, "-B", str(SCRIPT), *args], cwd=self.root,
            capture_output=True, text=True, timeout=10,
        )
        return result.returncode, result.stdout, result.stderr

    def fixture_cli(self, *args):
        return self.cli("--content", str(self.content), *args)

    def in_process(self):
        stdout, stderr = io.StringIO(), io.StringIO()
        with redirect_stdout(stdout), redirect_stderr(stderr):
            code = REPORT.main(["--content", str(self.content)])
        return code, stdout.getvalue(), stderr.getvalue()

    def assert_report(self, result, code, trailer, *, info=None, findings=()):
        status, stdout, stderr = result
        self.assertEqual(status, code)
        self.assertEqual(stderr, "")
        lines = stdout.splitlines()
        self.assertTrue(lines)
        self.assertEqual(lines[-1], trailer)
        self.assertEqual([line for line in lines[:-1] if line.startswith("FAIL ")], list(findings))
        if info is not None:
            self.assertEqual(lines, [*info, *findings, trailer])

    def test_c1_full_pass(self):
        # A clean run must emit its success trailer, not merely exit zero.
        self.assert_report(self.fixture_cli(), 0, PASS)

    def test_c2_findings_trailer(self):
        # Independent findings each appear once and precede the failure trailer.
        self.add_organic()
        real_filter = REPORT.drop_copy_claims

        def with_bad_reason(name, owner_words):
            clean, reasons = real_filter(name, owner_words)
            return clean, reasons + (("invalid/reason",) if not owner_words else ())

        with patch.object(REPORT, "drop_copy_claims", side_effect=with_bad_reason):
            self.assert_report(self.in_process(), 1, FAIL,
                               findings=("FAIL reason-invalid", "FAIL emptied-names 1 0"))

    def test_c2_1_unsafe_input(self):
        # A symlink to a valid folder must not pass the ordinary is_dir check.
        alias = self.root / "alias"
        alias.symlink_to(self.content, target_is_directory=True)
        for path in (alias, self.products_file, self.root / "missing"):
            with self.subTest(input_kind=path.name):
                self.assert_report(self.cli("--content", str(path)), 1, FAIL,
                                   info=(), findings=("FAIL unsafe-input",))

    def test_c2_2_content_invalid(self):
        # An unreadable content document is not a zero-product success.
        self.products_file.write_text("{", encoding="utf-8")
        self.assert_report(self.fixture_cli(), 1, FAIL, info=(), findings=("FAIL content-invalid",))

    def test_c2_3_check_error(self):
        # Even a failure in the owner-said arm must not produce partial counts.
        with patch.object(REPORT, "drop_copy_claims",
                          side_effect=[("Apple juice", ()), RuntimeError(str(self.content))]) as drop:
            self.assert_report(self.in_process(), 1, FAIL, info=(), findings=("FAIL check-error",))
        self.assertEqual([call.args for call in drop.call_args_list],
                         [("Apple juice", ""), ("Apple juice", "Apple juice")])

    def test_c2_4_reason_invalid(self):
        # Reject the whole malformed reason (including a valid prefix), but sort and count safe reasons.
        reasons = ("zulu", "alpha", "redaction-canary\n", "a" * 81)
        with patch.object(REPORT, "drop_copy_claims", return_value=("Apple juice", reasons)):
            self.assert_report(self.in_process(), 1, FAIL, findings=("FAIL reason-invalid",), info=(
                "products 2", "changed-label-only 1", "emptied-label-only 0", "changed-owner-said 1",
                "reason 2 alpha", "reason 2 zulu",
            ))

    def test_c2_5_emptied_names(self):
        # The threshold uses the supplied maximum and actual empty-name count.
        self.add_organic()
        self.add_product("c-sample-beet", "Organic beet spread")
        self.assert_report(self.fixture_cli("--max-emptied", "1"), 1, FAIL,
                           findings=("FAIL emptied-names 2 1",))

    def test_c3_usage_exit_2(self):
        # Invalid flags, missing flag operands and bad maxima must remain argparse errors.
        for args in (("--unknown",), ("--content",), ("--max-emptied",),
                     ("--max-emptied", "-1"), ("--max-emptied", "1.5")):
            with self.subTest(args=args):
                code, stdout, stderr = self.cli(*args)
                self.assertEqual(code, 2)
                self.assertEqual(stdout, "")  # No last stdout line for C3.
                self.assertIn("usage:", stderr)

    def test_c4_read_only(self):
        # Rewriting identical bytes or creating a sidecar also violates read-only.
        self.add_organic()

        def snapshot():
            return {p.relative_to(self.content): (p.stat().st_mtime_ns, p.read_bytes() if p.is_file() else None)
                    for p in (self.content, *self.content.rglob("*"))}

        before = snapshot()
        self.assert_report(self.fixture_cli("--max-emptied", "1"), 0, PASS)
        self.assertEqual(snapshot(), before)

    def test_c5_no_private_values(self):
        # Never log a dropped name, its id, or an input path (even in a parser error).
        name, identifier = "Organic privacy canary syrup", "synthetic-id-canary"
        self.add_product(identifier, name)
        finding = self.fixture_cli()
        self.assert_report(finding, 1, FAIL, findings=("FAIL emptied-names 1 0",))
        usage = self.fixture_cli("--max-emptied", str(self.content))
        self.assertEqual(usage[:2], (2, ""))
        for _, stdout, stderr in (finding, usage):
            for canary in (name, identifier, str(self.content)):
                self.assertFalse(canary in stdout or canary in stderr, "output exposed a canary")

    def test_c6_plain_names(self):
        # Plain active names stay intact; hidden names do not enter the report.
        self.add_product("h-sample-hidden", "Organic pear juice", "hidden")
        self.assert_report(self.fixture_cli(), 0, PASS, info=(
            "products 2", "changed-label-only 0", "emptied-label-only 0", "changed-owner-said 0",
        ))

    def test_c7_organic_name(self):
        # A label-only claim empties the name, but owner-said restores it; equality passes.
        self.add_organic()
        info = ("products 3", "changed-label-only 1", "emptied-label-only 1",
                "changed-owner-said 0", f"reason 1 {ORIGIN}")
        self.assert_report(self.fixture_cli(), 1, FAIL, info=info, findings=("FAIL emptied-names 1 0",))
        self.assert_report(self.fixture_cli("--max-emptied", "1"), 0, PASS, info=info)

    def test_c8_live_names(self):
        # Pin the checked-in corpus and verify the CLI finds it independently of cwd.
        self.assert_report(self.cli(), 1, FAIL, info=(
            "products 170", "changed-label-only 7", "emptied-label-only 7",
            "changed-owner-said 0", f"reason 7 {ORIGIN}",
        ), findings=("FAIL emptied-names 7 0",))
