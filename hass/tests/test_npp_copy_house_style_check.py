"""Offline CLI contract for checking NPP's fallback copy against house style."""

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

from hass import content_model

SCRIPT = Path(__file__).resolve().parents[2] / "scripts/hass/npp_copy_house_style_check.py"
PASS = "PASS npp_copy_house_style_check"
FAIL = "FAIL npp_copy_house_style_check"
JAM = "Raspberry jam"
JUICE = "Apple juice"
JAM_DESCRIPTION = "A pretend spread for a make-believe breakfast."
JUICE_DESCRIPTION = "A pretend drink for a make-believe picnic."

SPEC = importlib.util.spec_from_file_location("npp_copy_house_style_check", SCRIPT)
assert SPEC is not None and SPEC.loader is not None
checker = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(checker)


def snapshot(directory):
    return {
        path.relative_to(directory): (path.stat().st_mtime_ns, path.read_bytes() if path.is_file() else None)
        for path in (directory, *directory.rglob("*"))
    }


class NppCopyHouseStyleCheckTests(unittest.TestCase):
    def setUp(self):
        temporary = tempfile.TemporaryDirectory()
        self.addCleanup(temporary.cleanup)
        self.root = Path(temporary.name).resolve()
        self.content = self.root / "synthetic-content"
        self.content.mkdir()
        for source in content_model.CONTENT_DIR.glob("*.json"):
            shutil.copyfile(source, self.content / source.name)
        self.products = self.content / "products.json"
        document = json.loads(self.products.read_bytes())
        document["products"] = [
            {"id": "synthetic-spread", "name": JAM, "category": "pantry", "status": "active",
             "description": JAM_DESCRIPTION},
            {"id": "synthetic-drink", "name": JUICE, "category": "drinks", "status": "active",
             "description": JUICE_DESCRIPTION},
            {"id": "synthetic-held", "name": "Pretend Hidden Snack", "category": "pantry", "status": "held",
             "description": "An unused sentence for a held item."},
        ]
        self.products.write_text(json.dumps(document), encoding="utf-8")

    def cli(self, *args):
        return subprocess.run([sys.executable, "-B", str(SCRIPT), *args], cwd=self.root,
                              capture_output=True, text=True, timeout=20)

    def invoke(self):
        out, err = io.StringIO(), io.StringIO()
        with redirect_stdout(out), redirect_stderr(err):
            status = checker.main(["--content", str(self.content)])
        return subprocess.CompletedProcess([], status, out.getvalue(), err.getvalue())

    def assert_report(self, result, status, trailer, *findings):
        self.assertEqual(result.returncode, status)
        self.assertEqual(result.stderr, "")
        lines = result.stdout.splitlines()
        self.assertEqual(lines[-1:], [trailer])
        self.assertEqual([line for line in lines[:-1] if line.startswith("FAIL ")], list(findings))
        return lines[:-1]

    def test_c1_full_pass(self):
        # The standalone command must work away from the checkout and end with the PASS trailer.
        self.assert_report(self.cli("--content", str(self.content)), 0, PASS)

    def test_c2_findings_trailer(self):
        # A writer error on one product must not suppress a later completed style finding.
        original = checker.copy.Writer.write

        def write(writer, ctx, select):
            if ctx.item == JUICE:
                raise RuntimeError("synthetic writer error")
            return original(writer, ctx, select)

        with patch.object(checker.copy.Writer, "write", write), patch.object(
            checker.house_style, "check_description", return_value={"pass": False, "checks": []}
        ):
            self.assert_report(self.invoke(), 1, FAIL, "FAIL check-error", "FAIL style-fail 1")

    def test_c2_1_unsafe_input(self):
        # Following a directory symlink or treating a file/missing path as content is unsafe.
        alias = self.root / "alias"
        alias.symlink_to(self.content, target_is_directory=True)
        for label, path in (("symlink", alias), ("file", self.products), ("absent", self.root / "absent")):
            with self.subTest(kind=label):
                self.assert_report(self.cli("--content", str(path)), 1, FAIL, "FAIL unsafe-input")

    def test_c2_2_content_invalid(self):
        # A real loader error must not crash or turn into a pass over zero products.
        self.products.write_text("{", encoding="utf-8")
        self.assert_report(self.invoke(), 1, FAIL, "FAIL content-invalid")

    def test_c2_3_assets_invalid(self):
        # Never continue with unchecked fallback assets.
        with patch.object(checker.npp, "assets", side_effect=ValueError("synthetic asset error")):
            self.assert_report(self.invoke(), 1, FAIL, "FAIL assets-invalid")

    def test_c2_4_style_spec_invalid(self):
        # A missing style specification is not agreement with house style.
        with patch.object(checker.house_style, "load_spec", side_effect=OSError("synthetic spec error")):
            self.assert_report(self.invoke(), 1, FAIL, "FAIL style-spec-invalid")

    def test_c2_5_check_error(self):
        # Exceptions on either side of the comparison emit a single check-error, even for both products.
        for target, name in ((checker.copy.Writer, "write"), (checker.house_style, "check_description")):
            with self.subTest(operation=name), patch.object(target, name, side_effect=RuntimeError("synthetic error")):
                self.assert_report(self.invoke(), 1, FAIL, "FAIL check-error")

    def test_c2_6_style_fail(self):
        # A real hard style failure on generated copy must fail even if the other description passes.
        original = checker.copy.Writer.write

        def write(writer, ctx, select):
            result = original(writer, ctx, select)
            if ctx.item == JAM:
                result.text["description"] = "<" + result.text["description"]
            return result

        with patch.object(checker.copy.Writer, "write", write):
            lines = self.assert_report(self.invoke(), 1, FAIL, "FAIL style-fail 1")
        self.assertIn("style-pass 1", lines)
        self.assertIn("style-fail 1", lines)

    def test_c3_usage_exit_2(self):
        # Malformed command lines are usage errors, not findings or successes.
        for args in (("--content",), ("--unknown",), ("--cont", str(self.content))):
            with self.subTest(flag=args[0]):
                result = self.cli(*args)
                self.assertEqual(result.returncode, 2)
                self.assertEqual(result.stdout, "")  # No last line for argparse errors.
                self.assertTrue(result.stderr.startswith("usage:"))

    def test_c4_read_only(self):
        # Rewriting equal bytes or leaving a sidecar/directory still violates read-only.
        inputs = (self.content, checker.npp.ROOT, checker.house_style.SPEC_PATH.parent)
        before = [snapshot(directory) for directory in inputs]
        self.assert_report(self.cli("--content", str(self.content)), 0, PASS)
        self.assertTrue(before == [snapshot(directory) for directory in inputs], "input tree changed")

    def test_c5_no_private_values(self):
        # Guard report lines, caught exceptions, and argparse diagnostics against data leaks.
        canaries = (JAM, JAM_DESCRIPTION, str(self.content))
        ok = self.cli("--content", str(self.content))
        self.assert_report(ok, 0, PASS)
        with patch.object(checker.house_style, "check_description", side_effect=ValueError(" ".join(canaries))):
            error = self.invoke()
        self.assert_report(error, 1, FAIL, "FAIL check-error")
        usage = self.cli("--content", str(self.content), str(self.content))
        self.assertEqual((usage.returncode, usage.stdout), (2, ""))
        for result in (ok, error, usage):
            for index, value in enumerate(canaries):
                self.assertFalse(value in result.stdout + result.stderr, f"canary {index} leaked")

    def test_c6_two_products(self):
        # Detect lost/inactive products and a wrong ordering, kind, owner or duplicate-copy context.
        original = checker.copy.Writer.write
        with patch.object(checker.copy.Writer, "write", autospec=True, side_effect=original) as write:
            lines = self.assert_report(self.invoke(), 0, PASS)
        self.assertIn("products 2", lines)
        self.assertIn("written 2", lines)
        self.assertIn("style-pass 2", lines)
        self.assertEqual(
            [(ctx.kind, ctx.category, ctx.variant, ctx.item, ctx.owner_words, ctx.other_descriptions, select)
             for (_, ctx, select), _ in write.call_args_list],
            [("drink", "drinks", "raw", JUICE, JUICE, (JAM_DESCRIPTION,), None),
             ("food", "pantry", "raw", JAM, JAM, (JUICE_DESCRIPTION,), None)],
        )

    def test_c7_patched_fail(self):
        # Aggregate two failed verdicts, but don't count soft misses in failed verdicts.
        verdict = {"pass": False, "checks": [{"hard": False, "ok": False}]}
        with patch.object(checker.house_style, "check_description", return_value=verdict):
            lines = self.assert_report(self.invoke(), 1, FAIL, "FAIL style-fail 2")
        self.assertEqual(lines[:-1], ["products 2", "written 2", "style-pass 0", "style-fail 2", "soft-misses 0"])

    def test_c8_live_copy(self):
        # Pin default catalog totals, including legitimate Writer declines and passing soft misses.
        lines = self.assert_report(self.cli(), 0, PASS)
        self.assertEqual(lines, ["products 170", "written 166", "style-pass 166", "style-fail 0", "soft-misses 8"])
