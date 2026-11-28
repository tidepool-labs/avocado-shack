"""Offline CLI contract tests; never instantiate Conversation or NPP stages."""

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
SCRIPT = ROOT / "scripts/hass/npp_port_conversation_contract.py"
PASS = "PASS npp_port_conversation_contract"
FAIL = "FAIL npp_port_conversation_contract"


def snapshot():
    result = {}
    for tree in (ROOT / "hass", ROOT / "storefront-mockup"):
        for path in (tree, *tree.rglob("*")):
            stat = path.lstat()
            result[path.relative_to(ROOT)] = (stat.st_size, stat.st_mtime_ns)
    return result


class NppPortConversationContractTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        spec = importlib.util.spec_from_file_location("npp_port_conversation_contract", SCRIPT)
        assert spec is not None and spec.loader is not None
        cls.script = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(cls.script)

    def run_fixture(self, source, *, conversation_source=None):
        stdout, stderr = io.StringIO(), io.StringIO()
        with TemporaryDirectory() as directory:
            root = Path(directory)
            path = root / "calls.py"
            if source is not None:
                path.write_text(source, encoding="utf-8")
            cls_path = self.script.CONVERSATION_SOURCE
            if conversation_source is not None:
                cls_path = root / "conversation.py"
                cls_path.write_text(conversation_source, encoding="utf-8")
            with (patch.multiple(self.script, SOURCES=(path,), CONVERSATION_SOURCE=cls_path),
                  redirect_stdout(stdout), redirect_stderr(stderr)):
                status = self.script.main([])
        return status, stdout.getvalue().splitlines(), stderr.getvalue()

    def run_cli(self, *args, cwd=ROOT):
        return subprocess.run([sys.executable, "-B", str(SCRIPT), *args],
                              cwd=cwd, capture_output=True, text=True, timeout=15)

    def assert_result(self, result, status, trailer):
        code, lines, stderr = result
        self.assertEqual(code, status)
        self.assertEqual(stderr, "")
        self.assertTrue(lines)
        self.assertEqual(lines[-1], trailer)
        return lines

    def assert_findings(self, result, *expected):
        lines = self.assert_result(result, 1, FAIL)
        self.assertEqual([line for line in lines[:-1] if line.startswith("FAIL ")], list(expected))
        return lines

    def test_c1_full_pass(self):
        # Tuple/chained stores and a method keyword must satisfy the same port.
        result = self.run_fixture("self.c.editor.fetch()\nself.c.log\nself.c._capture(d, candidate=True)\n")
        self.assert_result(result, 0, PASS)

    def test_c2_findings_trailer(self):
        # A successfully parsed source with a finding is not a successful run.
        self.assert_result(self.run_fixture("self.c.absent\n"), 1, FAIL)

    def test_c2_1_attribute_missing(self):
        # Repeated/unsorted references produce unique, sorted missing names.
        result = self.run_fixture("self.c.z_missing\nself.c.a_missing.it\nself.c.z_missing\n")
        self.assert_findings(result, "FAIL attribute-missing a_missing", "FAIL attribute-missing z_missing")

    def test_c2_2_keyword_missing(self):
        # Inspect direct calls only; finding order must not follow call order.
        result = self.run_fixture(
            "self.c._capture(d, z=True, a=True, candidate=True)\n"
            "self.c._capture(d, a=True)\nself.c.outbox.add(nested=True)\n"
        )
        self.assert_findings(result, "FAIL keyword-missing _capture.a", "FAIL keyword-missing _capture.z")

    def test_c2_3_none_used(self):
        # Strings, comments, and accesses on other receivers are not port use.
        self.assert_findings(self.run_fixture(
            '"self.c.editor"\n# self.c.settings\nother.c.editor\nself.other.c.settings\n'
        ), "FAIL none-used")

    def test_c2_4_parse_error(self):
        # Unreadable/invalid sources at either end must not look like empty input or success.
        for result in (self.run_fixture(None), self.run_fixture("def broken(\n"),
                       self.run_fixture("self.c.editor\n", conversation_source="class Conversation(\n")):
            with self.subTest(result=result):
                self.assert_findings(result, "FAIL parse-error")

    def test_c3_usage_exit_2(self):
        # Even argparse's implicit help flag would violate the no-arguments contract.
        for arg in ("extra", "--unknown", "--help", "--"):
            with self.subTest(arg=arg):
                result = self.run_cli(arg)
                self.assertEqual(result.returncode, 2)
                self.assertEqual(result.stdout, "")  # No stdout trailer on usage errors.
                self.assertIn("unrecognized arguments:", result.stderr.splitlines()[-1])

    def test_c4_read_only(self):
        # A state directory or cache created by an import would change this snapshot.
        with TemporaryDirectory() as directory:
            before = snapshot()
            result = self.run_cli(cwd=Path(directory))
            self.assert_result((result.returncode, result.stdout.splitlines(), result.stderr), 0, PASS)
            self.assertEqual(snapshot(), before)

    def test_c5_output_shape(self):
        # No debug lines or traceback may accompany a multi-finding report.
        result = self.run_fixture("self.c.absent\nself.c._capture(d, unexpected=True)\n")
        lines = self.assert_result(result, 1, FAIL)
        self.assertEqual(lines, [
            "port used=2", "port missing=1 bad_keywords=1", "FAIL attribute-missing absent",
            "FAIL keyword-missing _capture.unexpected", FAIL,
        ])

    def test_c6_fixture(self):
        # The externally patched SOURCES seam must report both kinds of drift together.
        result = self.run_fixture("self.c.no_such_thing\nself.c._capture(d, nope=True)\n")
        self.assert_findings(result, "FAIL attribute-missing no_such_thing", "FAIL keyword-missing _capture.nope")

    def test_c7_live_pins(self):
        # Both real consumers must be scanned, and the measured base has no port drift.
        result = self.run_cli()
        lines = self.assert_result((result.returncode, result.stdout.splitlines(), result.stderr), 0, PASS)
        self.assertEqual(lines, ["port used=14", "port missing=0 bad_keywords=0", PASS])


if __name__ == "__main__":
    unittest.main()
