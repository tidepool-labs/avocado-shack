"""Offline CLI and fixture contracts for the reply reference audit."""

from contextlib import redirect_stderr, redirect_stdout
import importlib.util
import io
import json
from pathlib import Path
import subprocess
import sys
import tempfile
import textwrap
import unittest
from unittest.mock import patch

from hass import npp

ROOT = Path(__file__).resolve().parents[2]
SCRIPT = ROOT / "scripts/hass/npp_reply_reference_check.py"
SPEC = importlib.util.spec_from_file_location("npp_reply_reference_check", SCRIPT)
assert SPEC is not None and SPEC.loader is not None
check = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(check)

PASS = "PASS npp_reply_reference_check"
FAIL = "FAIL npp_reply_reference_check"


class ReplyReferenceCheckTests(unittest.TestCase):
    def setUp(self):
        temporary = tempfile.TemporaryDirectory()
        self.addCleanup(temporary.cleanup)
        self.fixtures = Path(temporary.name)

    def source(self, text, name="x.py"):
        (self.fixtures / name).write_text(textwrap.dedent(text).lstrip("\n"), encoding="utf-8")

    def fixture_run(self, pattern="*.py"):
        output, errors = io.StringIO(), io.StringIO()
        with patch.object(check, "SOURCES", str(self.fixtures / pattern)), \
                redirect_stdout(output), redirect_stderr(errors):
            code = check.main([])
        self.assertEqual(errors.getvalue(), "")
        return code, output.getvalue().splitlines()

    def cli(self, *args):
        return subprocess.run(
            [sys.executable, "-B", str(SCRIPT), *args], cwd=self.fixtures,
            capture_output=True, text=True, timeout=10,
        )

    def assert_result(self, result, exit_code, *findings):
        code, lines = result
        self.assertEqual(code, exit_code)
        self.assertEqual(lines[-1], PASS if exit_code == 0 else FAIL)
        self.assertEqual(lines[1:-1], list(findings))
        return lines[0]

    def test_c1_full_pass(self):
        # Closed-over aliases must resolve, but unrelated shadowing must not leak.
        self.source('''
            def outer(replies):
                rules, texts = replies['brackets']['compose'], replies['brackets']['parts']
                def captured():
                    return rules['separator']
                def unrelated(texts, key):
                    return texts[key]
                def local(key):
                    value = texts[key]
                    texts = {}
                    return value
                return texts['maker_left_off_label']
            def sibling(rules, key):
                return rules[key]
        ''')
        self.assertEqual(self.assert_result(self.fixture_run(), 0),
                         "refs files=1 sections=2 references=4 dynamic=0 asks=5")

    def test_c2_findings_trailer(self):
        # A good later file must not overwrite the earlier failure status.
        self.source("replies['guards']['unknown']", "a.py")
        self.source("replies['guards']['not_ready']", "z.py")
        self.assert_result(self.fixture_run(), 1, "FAIL reply-ref-missing a.py guards unknown")

    def test_c2_1_assets_unreadable(self):
        # Loader failures are classified without exposing their text or retrying.
        self.source("replies['guards']['not_ready']")
        with patch.object(npp, "assets", side_effect=ValueError("fixture error")) as load:
            self.assert_result(self.fixture_run(), 1, "FAIL assets-unreadable")
            load.assert_called_once_with()

    def test_c2_2_source_unreadable(self):
        # No input, IO failure, decoding failure, and parse failure cannot pass.
        self.assert_result(self.fixture_run(), 1, "FAIL source-unreadable")
        path = self.fixtures / "x.py"
        path.mkdir()
        self.assert_result(self.fixture_run(), 1, "FAIL source-unreadable")
        other = self.fixtures / "y.py"
        for data in (b"\xff", b"def invalid syntax"):
            with self.subTest(data=data):
                other.write_bytes(data)
                self.assert_result(self.fixture_run(other.name), 1, "FAIL source-unreadable")

    def test_c2_3_reply_section_missing(self):
        # A missing parent is reported once per root lookup, in source order.
        self.source("self.replies['z_missing']['child']\nreplies['a_missing']", "a.py")
        self.source("replies['z_missing']", "z.py")
        self.assert_result(self.fixture_run(), 1,
                           "FAIL reply-section-missing a.py z_missing",
                           "FAIL reply-section-missing a.py a_missing",
                           "FAIL reply-section-missing z.py z_missing")

    def test_c2_4_reply_ref_missing(self):
        # Nested aliases and literal keywords must report missing paths, not cascades.
        self.source('''
            parts = replies['brackets']['parts']
            parts['missing_label']['child']
            self.replies['guards']['missing_guard']
            Edit(ask='missing_ask', reply='missing_edit')
        ''')
        self.assert_result(self.fixture_run(), 1,
                           "FAIL reply-ref-missing x.py brackets parts.missing_label",
                           "FAIL reply-ref-missing x.py guards missing_guard",
                           "FAIL reply-ref-missing x.py questions missing_ask",
                           "FAIL reply-ref-missing x.py edits missing_edit")

    def test_c2_5_ask_untemplated(self):
        # Source alone cannot cover new schema IDs; null is not an ask.
        self.source("replies['guards']['not_ready']")
        asks = ["z_unknown", None, "ask_price", "a_unknown"]
        schema = {"properties": {"ask_id": {"enum": asks}}}
        _, _, templates = npp.assets()
        with patch.object(npp, "assets", return_value=(None, {
            "hass-listing-edit/edit.schema.json": json.dumps(schema).encode(),
        }, templates)):
            self.assertEqual(self.assert_result(self.fixture_run(), 1,
                                                "FAIL ask-untemplated z_unknown",
                                                "FAIL ask-untemplated a_unknown"),
                             "refs files=1 sections=1 references=1 dynamic=0 asks=3")

    def test_c2_6_reply_key_unresolved(self):
        # Literal neighbors and membership guards cannot certify a dynamic lookup.
        for source, line in (
            ("def guard(replies, key):\n    return replies['guards'][key]", 2),
            ("replies[section]['not_ready']", 1),
            ("def f(self, k):\n    table = self.replies['guards']\n    return table[k]", 3),
            ("if key not in replies['guards']: pass\nreplies['guards'][key]", 2),
            ("table = replies['guards']\ntable.get(key)", 2),
            ("table = {'nested': replies['guards']}", 1),
        ):
            with self.subTest(source=source):
                self.source(source)
                self.assert_result(self.fixture_run(), 1, f"FAIL reply-key-unresolved x.py {line}")
        self.source("Edit(ask='ask_price', reply='picture_request')\n"
                    "guard(replies, key)\nreplies['guards'][key]")
        self.assertEqual(self.assert_result(self.fixture_run(), 1, "FAIL reply-key-unresolved x.py 3"),
                         "refs files=1 sections=1 references=2 dynamic=1 asks=5")

    def test_c2_6_exception_paths_preserve_possible_aliases(self):
        # A failed RHS leaves the old alias intact; an exception later in the
        # suite can also expose an alias introduced and then cleared there.
        for source, line in (
            ("table = replies['guards']\ntry:\n    table = may_raise()\n"
             "except Exception:\n    pass\ntable['nope']", 6),
            ("try:\n    if condition:\n        table = replies['guards']\n"
             "        may_raise()\n        table = {}\nexcept Exception:\n    table[key]", 7),
            ("table = replies['guards']\ntry:\n    table = may_raise()\n"
             "finally:\n    table[key]", 5),
            ("table = replies['guards']\ntry:\n    table = may_raise()\n"
             "except* Exception:\n    pass\ntable[key]", 6),
            ("try:\n    may_raise()\nexcept* ValueError:\n    table = replies['guards']\n"
             "    may_raise()\n    table = {}\nexcept* TypeError:\n    table[key]", 8),
            ("try:\n    may_raise()\nexcept Exception:\n    table = replies['guards']\n"
             "else:\n    table = {}\ntable[key]", 7),
        ):
            with self.subTest(source=source):
                self.source(source)
                self.assert_result(self.fixture_run(), 1, f"FAIL reply-key-unresolved x.py {line}")
        # Stable aliases stay checkable, and inner locals must not taint an
        # outer binding just because their function is defined inside the try.
        self.source('''
            table = replies['guards']
            try:
                def unrelated():
                    table = {}
                may_raise()
            except Exception:
                table['not_ready']
            finally:
                table['not_ready']
            table['not_ready']
        ''')
        self.assertEqual(self.assert_result(self.fixture_run(), 0),
                         "refs files=1 sections=1 references=3 dynamic=0 asks=5")

    def test_c3_usage_exit_2(self):
        # Unsupported options must not accidentally run the scan.
        for arg in ("fixture.py", "--unknown", "--help", "--"):
            with self.subTest(arg=arg):
                result = self.cli(arg)
                self.assertEqual((result.returncode, result.stdout), (2, ""))
                self.assertIn("usage:", result.stderr)

    def test_c4_read_only(self):
        # Catch a cache or report write even if the scan's stdout stays unchanged.
        def snapshot():
            state = {}
            for name in ("hass", "storefront-mockup"):
                tree = ROOT / name
                for path in (tree, *tree.rglob("*")):
                    stat = path.stat()
                    state[path.relative_to(ROOT)] = (stat.st_size, stat.st_mtime_ns)
            return state

        before = snapshot()
        result = self.cli()
        self.assertEqual((result.returncode, result.stdout.splitlines()[-1]), (1, FAIL))
        self.assertEqual(snapshot(), before)
        self.assertEqual(list(self.fixtures.iterdir()), [])

    def test_c5_output_shape(self):
        # Extra diagnostics or leaking source/absolute paths breaks the line protocol.
        self.source("replies['missing']\nreplies['guards']['missing']\nreplies[var]")
        self.assertEqual(self.assert_result(self.fixture_run(), 1,
                                            "FAIL reply-section-missing x.py missing",
                                            "FAIL reply-ref-missing x.py guards missing",
                                            "FAIL reply-key-unresolved x.py 3"),
                         "refs files=1 sections=2 references=1 dynamic=1 asks=5")

    def test_c6_fixture(self):
        # Changing just the literal must change the verdict, not occurrence counts.
        self.source('replies["guards"]["not_ready"]')
        self.assertEqual(self.assert_result(self.fixture_run(), 0),
                         "refs files=1 sections=1 references=1 dynamic=0 asks=5")
        self.source('replies["guards"]["nope"]')
        self.assertEqual(self.assert_result(self.fixture_run(), 1, "FAIL reply-ref-missing x.py guards nope"),
                         "refs files=1 sections=1 references=1 dynamic=0 asks=5")

    def test_c7_live_pins(self):
        # Pinned checkout: an all-literal pass is insufficient with computed sites.
        result = self.cli()
        self.assertEqual(result.stderr, "")
        summary = self.assert_result((result.returncode, result.stdout.splitlines()), 1,
                                     "FAIL reply-key-unresolved missing.py 172",
                                     "FAIL reply-key-unresolved reply.py 35",
                                     "FAIL reply-key-unresolved reply.py 55",
                                     "FAIL reply-key-unresolved reply.py 68",
                                     "FAIL reply-key-unresolved reply.py 70")
        self.assertEqual(summary, "refs files=15 sections=18 references=35 dynamic=5 asks=5")
