"""Exercise the offline supplier sign-off diagnostic with the pinned edit reader."""

from contextlib import redirect_stderr, redirect_stdout
import importlib.util
import io
from pathlib import Path
import subprocess
import sys
from tempfile import TemporaryDirectory
import unittest
from unittest.mock import patch


ROOT = Path(__file__).resolve().parents[2]
SCRIPT = ROOT / "scripts/hass/npp_supplier_sign_off.py"
PASS = "PASS npp_supplier_sign_off"
FAIL = "FAIL npp_supplier_sign_off"
EXPECTED_TEXTS = (
    "This is from miners.",
    "This is from miners. Thanks!",
    "This is from miners. Thank you.",
    "This is from miners! :)",
    "Thanks! This is from miners.",
    "This is from miners, thanks",
)


def snapshot():
    entries = {}
    for name in ("hass", "storefront-mockup"):
        tree = ROOT / name
        for path in (tree, *tree.rglob("*")):
            info = path.lstat()
            entries[path.relative_to(ROOT)] = (info.st_size, info.st_mtime_ns)
    return entries


class SupplierSignOffTests(unittest.TestCase):
    def setUp(self):
        spec = importlib.util.spec_from_file_location("npp_supplier_sign_off", SCRIPT)
        assert spec is not None and spec.loader is not None
        self.tool = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(self.tool)
        self.edits = self.tool.edits
        self.original_supplier = self.edits.Grammar.supplier

    def invoke(self, *args):
        with TemporaryDirectory() as temporary:
            return subprocess.run(
                [sys.executable, "-B", str(SCRIPT), *args], cwd=temporary,
                capture_output=True, text=True, timeout=10,
            )

    def run_main(self, status, trailer):
        stdout, stderr = io.StringIO(), io.StringIO()
        with redirect_stdout(stdout), redirect_stderr(stderr):
            code = self.tool.main([])
        return self.check_result(code, stdout.getvalue(), stderr.getvalue(), status, trailer)

    def check_result(self, code, stdout, stderr, status, trailer):
        self.assertEqual(code, status, stdout + stderr)
        self.assertEqual(stderr, "")
        lines = stdout.splitlines()
        self.assertEqual(lines[-1:], [trailer])
        return lines

    def sentence_supplier(self, grammar, text):
        for sentence in self.edits.SENTENCE.split(" ".join(text.split())):
            if (supplier := self.original_supplier(grammar, sentence)) is not None:
                return supplier
        return None

    def all_sign_offs_supplier(self, grammar, text):
        # Only the fixture relaxes comma sign-offs; real edits.read still makes the patch.
        return self.sentence_supplier(grammar, text.removesuffix(", thanks"))

    def patch_supplier(self, supplier):
        def wrapper(grammar, text):
            return supplier(grammar, text)

        return patch.object(self.edits.Grammar, "supplier", wrapper)

    def test_c1_full_pass(self):
        # A hard-coded failure or an incomplete run would reject this all-read fixture.
        with self.patch_supplier(self.all_sign_offs_supplier):
            lines = self.run_main(0, PASS)
        self.assertEqual(lines, [*(f"case {i} supplier=Miners" for i in range(6)), PASS])

    def test_c2_findings_trailer(self):
        # A reader failure must not suppress later findings or cause a second trailer.
        original_read = self.edits.read

        def read(grammar, text, finance):
            if text == EXPECTED_TEXTS[0]:
                raise RuntimeError("fixture error")
            return original_read(grammar, text, finance)

        with self.patch_supplier(self.sentence_supplier):
            with patch.object(self.edits, "read", side_effect=read):
                lines = self.run_main(1, FAIL)
        self.assertEqual([line for line in lines if line.startswith("FAIL ")],
                         ["FAIL check-error", "FAIL supplier-missed 5", FAIL])

    def test_c2_1_supplier_missed(self):
        # Any supplier patch is not enough: the specific name has to be Miners.
        def wrong_supplier(grammar, text):
            if text == EXPECTED_TEXTS[2]:
                text = "This is from Grove. Thank you."
            return self.all_sign_offs_supplier(grammar, text)

        with patch.object(self.edits.Grammar, "supplier", wrong_supplier):
            lines = self.run_main(1, FAIL)
        cases = [f"case {i} supplier=Miners" for i in range(6)]
        cases[2:3] = ["case 2 supplier=Grove", "FAIL supplier-missed 2"]
        self.assertEqual(lines, [*cases, FAIL])

    def test_c2_2_check_error(self):
        # A setup error must fail without leaking the exception or trying to read cases.
        for module, name in ((self.tool.hass.npp, "assets"), (self.edits, "Grammar")):
            with self.subTest(call=name):
                with patch.object(module, name, side_effect=RuntimeError("fixture error")):
                    lines = self.run_main(1, FAIL)
                self.assertEqual(lines, ["FAIL check-error", FAIL])

    def test_c3_usage_exit_2(self):
        # Ignored arguments (or argparse's default help) would bypass the zero-arg contract.
        for arg in ("extra", "--unknown", "--help", "-h", "--"):
            with self.subTest(arg=arg):
                result = self.invoke(arg)
                self.assertEqual(result.returncode, 2)
                self.assertEqual(result.stdout, "")  # No last stdout line on usage errors.
                self.assertTrue(result.stderr.startswith("usage: "))
                self.assertEqual(result.stderr.splitlines()[-1],
                                 f"npp_supplier_sign_off.py: error: unrecognized arguments: {arg}")

    def test_c4_read_only(self):
        # A checkout-relative cache or saved patch would change the tree snapshot.
        before = snapshot()
        result = self.invoke()
        self.check_result(result.returncode, result.stdout, result.stderr, 1, FAIL)
        self.assertEqual(snapshot(), before)

    def test_c5_output_shape(self):
        # Running from a different directory still emits only case/finding lines, not debug output.
        result = self.invoke()
        lines = self.check_result(result.returncode, result.stdout, result.stderr, 1, FAIL)
        for line in lines[:-1]:
            self.assertRegex(line, r"\A(?:case [0-5] (?:supplier=Miners|ask_edit_unclear)|FAIL supplier-missed [0-5])\Z")
        self.assertEqual(sum(line.startswith("case ") for line in lines), 6)
        self.assertEqual(len(lines), 11)

    def test_c6_fixture(self):
        # Looking at every sentence handles separate sign-offs but cannot split at the comma.
        with self.patch_supplier(self.sentence_supplier):
            lines = self.run_main(1, FAIL)
        self.assertEqual(lines, [*(f"case {i} supplier=Miners" for i in range(5)),
                                 "case 5 ask_edit_unclear", "FAIL supplier-missed 5", FAIL])

    def test_c7_live_pins(self):
        # Pin the baseline and verify each input flows through the real reader with empty finance.
        with patch.object(self.edits, "read", wraps=self.edits.read) as read:
            lines = self.run_main(1, FAIL)
        self.assertEqual([(text, finance) for _, text, finance in
                          (call.args for call in read.call_args_list)],
                         [(text, {}) for text in EXPECTED_TEXTS])
        self.assertEqual(lines, [
            "case 0 supplier=Miners",
            "case 1 ask_edit_unclear", "FAIL supplier-missed 1",
            "case 2 ask_edit_unclear", "FAIL supplier-missed 2",
            "case 3 ask_edit_unclear", "FAIL supplier-missed 3",
            "case 4 supplier=Miners",
            "case 5 ask_edit_unclear", "FAIL supplier-missed 5",
            FAIL,
        ])
