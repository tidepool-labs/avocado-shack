"""Offline CLI contract for the no-change reply diagnostic."""

from contextlib import redirect_stderr, redirect_stdout
import importlib.util
import io
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import patch

from hass.npp import edits, reply
from hass.npp.job import Plan


ROOT = Path(__file__).resolve().parents[2]
SCRIPT = ROOT / "scripts/hass/npp_edit_no_change_reply.py"
PASS = "PASS npp_edit_no_change_reply"
FAIL = "FAIL npp_edit_no_change_reply"
CONTROL = "nochange control reply=patch"


def snapshot():
    result = {}
    for tree in (ROOT / "hass", ROOT / "storefront-mockup"):
        for path in (tree, *tree.rglob("*")):
            stat = path.lstat()
            result[path.relative_to(ROOT)] = (stat.st_size, stat.st_mtime_ns)
    return result


class NoChangeReplyTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        spec = importlib.util.spec_from_file_location("npp_edit_no_change_reply", SCRIPT)
        if spec is None or spec.loader is None:
            raise ImportError("could not load the no-change reply diagnostic")
        cls.tool = importlib.util.module_from_spec(spec)
        with patch.object(sys, "path", sys.path.copy()), patch.object(sys, "dont_write_bytecode", True):
            spec.loader.exec_module(cls.tool)

    def cli(self, *args):
        with tempfile.TemporaryDirectory() as fixture_dir:
            return subprocess.run(
                [sys.executable, "-B", str(SCRIPT), *args], cwd=fixture_dir,
                capture_output=True, text=True, timeout=15,
            )

    def invoke(self):
        stdout, stderr = io.StringIO(), io.StringIO()
        with redirect_stdout(stdout), redirect_stderr(stderr):
            code = self.tool.main([])
        self.assertEqual(stderr.getvalue(), "")
        return code, stdout.getvalue().splitlines()

    def accept_parsed_noop(self, stage, work):
        text = work.request["texts"][-1]
        parsed = edits.read(stage.grammar, text, work.request["slots"]["intake"], None)
        if parsed.patch == (("name", self.tool.LISTING["name"]),):
            return Plan(listing=dict(self.tool.LISTING), patch={}, identified=True)
        return self.real_edit(stage, work)

    real_edit = staticmethod(reply.Stages.edit)

    def test_c1_full_pass(self):
        # A clean run must reach all four checks and use the success trailer/exit.
        with patch.object(reply.Stages, "edit", autospec=True, side_effect=self.accept_parsed_noop) as edit:
            code, lines = self.invoke()
        self.assertEqual(code, 0)
        self.assertEqual(lines[-1], PASS)
        self.assertEqual(edit.call_count, 4)
        self.assertEqual(lines[-2], CONTROL)
        self.assertEqual(len(lines), 5)

    def test_c2_findings_trailer(self):
        # Multiple findings must survive in order, with one terminal FAIL.
        unclear = Plan(questions=(("ask_edit_unclear", "fixture"),), identified=True)
        with patch.object(edits, "read", return_value=edits.Edit(patch=(("name", "Wildflower Honey"),))), \
             patch.object(reply.Stages, "edit", return_value=unclear):
            code, lines = self.invoke()
        self.assertEqual(code, 1)
        self.assertEqual(lines[-1], FAIL)
        self.assertEqual([line for line in lines if line.startswith("FAIL ")], [
            "FAIL nochange-called-unclear 0", "FAIL nochange-called-unclear 1",
            "FAIL nochange-called-unclear 2", "FAIL control-broken", FAIL,
        ])

    def test_c2_1_nochange_called_unclear(self):
        # Only the name-patch/unclear conjunction counts, not an unread edit or a non-name patch.
        name = edits.Edit(patch=(("name", "Wildflower Honey"),))
        category = edits.Edit(patch=(("category", "pantry"),))
        unread = edits.Edit(ask="ask_edit_unclear")
        unclear = Plan(questions=(("ask_edit_unclear", "fixture"),), identified=True)
        changed = Plan(listing={"name": "Clover Honey"}, patch={"name": "Clover Honey"}, identified=True)
        with patch.object(edits, "read", side_effect=[category, unread, name]), \
             patch.object(reply.Stages, "edit", side_effect=[unclear, unclear, unclear, changed]):
            code, lines = self.invoke()
        self.assertEqual(code, 1)
        self.assertEqual(lines[-1], FAIL)
        self.assertEqual([line for line in lines[:-1] if line.startswith("FAIL ")],
                         ["FAIL nochange-called-unclear 2"])

    def test_c2_2_control_broken(self):
        # Even with an accepted no-op, a question for a genuine rename fails closed.
        def broken_control(stage, work):
            if work.request["texts"][-1] == "call it Clover Honey":
                return Plan(questions=(("ask_price", "fixture"),), identified=True)
            return self.accept_parsed_noop(stage, work)

        with patch.object(reply.Stages, "edit", autospec=True, side_effect=broken_control):
            code, lines = self.invoke()
        self.assertEqual(code, 1)
        self.assertEqual(lines[-1], FAIL)
        self.assertEqual(lines[-3:-1], ["nochange control reply=ask_price", "FAIL control-broken"])
        self.assertEqual([line for line in lines[:-1] if line.startswith("FAIL ")], ["FAIL control-broken"])

    def test_c2_3_check_error(self):
        # An exception must not leak its text, abort the remaining checks, or look clean.
        marker = "fixture-exception-text"
        real_read = edits.read

        def bad_read(grammar, text, finance, mapper):
            if text == "call it Wildflower Honey":
                raise RuntimeError(marker)
            return real_read(grammar, text, finance, mapper)

        def bad_edit(stage, work):
            if work.request["texts"][-1] == "call it Wildflower Honey":
                raise RuntimeError(marker)
            return self.real_edit(stage, work)

        for injected in (
            patch.object(edits, "read", side_effect=bad_read),
            patch.object(reply.Stages, "edit", autospec=True, side_effect=bad_edit),
        ):
            with self.subTest(), injected:
                code, lines = self.invoke()
                self.assertEqual(code, 1)
                self.assertEqual(lines[-1], FAIL)
                self.assertEqual([line for line in lines[:-1] if line.startswith("FAIL ")], ["FAIL check-error"])
                self.assertNotIn(marker, "\n".join(lines))
                self.assertEqual(len(lines), 5)
                self.assertEqual(lines[-2], CONTROL)

    def test_c3_usage_exit_2(self):
        # Even implicit help and the option terminator are arguments, not accepted modes.
        for arg in ("extra", "--unknown", "--help", "--"):
            with self.subTest(arg=arg):
                result = self.cli(arg)
                self.assertEqual(result.returncode, 2)
                self.assertEqual(result.stdout, "")  # No stdout trailer on a usage error.
                self.assertEqual(result.stderr.splitlines()[-1],
                                 f"{SCRIPT.name}: error: unrecognized arguments: {arg}")

    def test_c4_read_only(self):
        # A cache write, temporary file in the source tree, or asset rewrite changes the snapshot.
        before = snapshot()
        result = self.cli()
        self.assertEqual(result.returncode, 1)
        self.assertEqual(result.stdout.splitlines()[-1], FAIL)
        self.assertEqual(snapshot(), before)

    def test_c5_output_shape(self):
        # Logs, reply sentences, case text, or a traceback must not enter either output stream.
        result = self.cli()
        self.assertEqual(result.returncode, 1)
        self.assertEqual(result.stderr, "")
        lines = result.stdout.splitlines()
        self.assertEqual(lines[-1], FAIL)
        for line in lines[:-1]:
            self.assertRegex(line, r"\A(?:nochange [0-2] read=(?:yes|no) reply=[a-z_]+|"
                                   r"nochange control reply=[a-z_]+|"
                                   r"FAIL (?:nochange-called-unclear [0-2]|control-broken|check-error))\Z")

    def test_c6_fixture(self):
        # An empty patch is a classified no-op, not a question or a probe error.
        with patch.object(reply.Stages, "edit", autospec=True, side_effect=self.accept_parsed_noop):
            code, lines = self.invoke()
        self.assertEqual(code, 0)
        self.assertEqual(lines[-1], PASS)
        self.assertIn("nochange 0 read=yes reply=patch", lines)

    def test_c7_live_pins(self):
        # The checked-in grammar and real edit stage must reproduce the measured baseline.
        result = self.cli()
        self.assertEqual(result.returncode, 1)
        lines = result.stdout.splitlines()
        self.assertEqual(lines[-1], FAIL)
        self.assertEqual(lines, [
            "nochange 0 read=yes reply=ask_edit_unclear",
            "FAIL nochange-called-unclear 0",
            "nochange 1 read=no reply=ask_edit_unclear",
            "nochange 2 read=no reply=ask_edit_unclear",
            CONTROL,
            FAIL,
        ])


if __name__ == "__main__":
    unittest.main()
