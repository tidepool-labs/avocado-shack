"""Offline CLI and fault-injection tests for the NPP reply fallback check."""

from contextlib import redirect_stderr, redirect_stdout
from dataclasses import replace
import importlib.util
from io import StringIO
from pathlib import Path
import subprocess
import sys
from tempfile import TemporaryDirectory
import unittest
from unittest.mock import patch


ROOT = Path(__file__).resolve().parents[2]
SCRIPT = ROOT / 'scripts/hass/npp_selector_reply_fallback.py'
PASS = 'PASS npp_selector_reply_fallback'
FAIL = 'FAIL npp_selector_reply_fallback'


def snapshot():
    state = {}
    for tree in (ROOT / 'hass', ROOT / 'storefront-mockup'):
        for path in (tree, *tree.rglob('*')):
            info = path.lstat()
            state[path.relative_to(ROOT)] = (info.st_size, info.st_mtime_ns)
    return state


class SelectorReplyFallbackTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        spec = importlib.util.spec_from_file_location('npp_selector_reply_fallback', SCRIPT)
        assert spec is not None and spec.loader is not None
        cls.tool = importlib.util.module_from_spec(spec)
        with patch.object(sys, 'path', sys.path[:]):
            spec.loader.exec_module(cls.tool)

    def cli(self, *args):
        with TemporaryDirectory() as temp:
            result = subprocess.run(
                [sys.executable, '-B', str(SCRIPT), *args],
                cwd=temp, capture_output=True, text=True, timeout=15,
            )
        return result.returncode, result.stdout, result.stderr

    def invoke(self):
        out, err = StringIO(), StringIO()
        with redirect_stdout(out), redirect_stderr(err):
            code = self.tool.main([])
        return code, out.getvalue(), err.getvalue()

    def assert_run(self, receipt, code, last):
        status, out, err = receipt
        self.assertEqual(status, code, out + err)
        self.assertEqual(err, '')
        lines = out.splitlines()
        self.assertTrue(lines, 'expected an output trailer')
        self.assertEqual(lines[-1], last)
        return lines[:-1]

    def assert_findings(self, receipt, *expected):
        lines = self.assert_run(receipt, 1, FAIL)
        self.assertEqual([line for line in lines if line.startswith('FAIL ')], list(expected))
        return lines

    def test_c1_full_pass(self):
        # A good run must not return a failure status or lose its CLI trailer.
        self.assert_run(self.cli(), 0, PASS)

    def test_c2_findings_trailer(self):
        # A finding must survive later successful checks; the loop must not stop at the first miss.
        writer = self.tool.copy.Writer
        write = writer.write

        def regress(instance, ctx, select=None):
            result = write(instance, ctx, select)
            if select is not None and not result.basic:
                return replace(result, basic=True)
            if select is not None and select(instance.step, 'P', {}, {}) == [1, 2]:
                return None
            return result

        with patch.object(writer, 'write', regress):
            lines = self.assert_findings(self.invoke(), 'FAIL good-reply-dropped', 'FAIL write-none list')
        self.assertIn('reply unknown-template raw=dict basic=yes', lines)

    def test_c2_1_bad_reply_used(self):
        # Changing either selections or the basic flag independently must report the bad reply.
        writer = self.tool.copy.Writer
        write = writer.write
        for changes in ({'selections': {}}, {'basic': False}, {'selections': {}, 'basic': False}):
            with self.subTest(changes=changes):
                def regress(instance, ctx, select=None):
                    result = write(instance, ctx, select)
                    if select is not None and select(instance.step, 'P', {}, {}) == [1, 2]:
                        return replace(result, **changes)
                    return result

                with patch.object(writer, 'write', regress):
                    self.assert_findings(self.invoke(), 'FAIL bad-reply-used list')

    def test_c2_1_ignored_reply_rejected_by_adapter(self):
        # The real selector must expose ignored parsed replies, not reject them.
        copy = self.tool.copy
        real_selector = copy.codex_selector

        def regress(transport):
            select = real_selector(transport=transport)

            def reject_list(*args):
                raw = select(*args)
                return None if raw == [1, 2] else raw

            return reject_list

        with patch.object(copy, 'codex_selector', regress):
            lines = self.assert_findings(self.invoke(), 'FAIL bad-reply-used list')
        self.assertIn('reply list raw=none basic=yes', lines)
        self.assertIn('reply unknown-template raw=dict basic=yes', lines)

    def test_c2_1_bad_reply_used_scalar(self):
        # A scalar accepted by the real selector must not crash reply-kind reporting,
        # even when the real writer still falls back to defaults.
        replies = tuple(
            (name, group, self.tool.wrap('false') if name == 'not-json' else reply)
            for name, group, reply in self.tool._replies()
        )
        with patch.object(self.tool, '_replies', return_value=replies):
            lines = self.assert_findings(self.invoke(), 'FAIL bad-reply-used not-json')
        self.assertFalse(any(line.startswith('reply not-json ') for line in lines))

    def test_c2_2_good_reply_dropped(self):
        # A basic flag or a different ID in any required field drops the good reply.
        writer = self.tool.copy.Writer
        write = writer.write
        for field in (None, 'name', 'description', 'imageAlt'):
            with self.subTest(field=field):
                def regress(instance, ctx, select=None):
                    result = write(instance, ctx, select)
                    if select is not None and not result.basic:
                        if field is None:
                            return replace(result, basic=True)
                        selections = {**result.selections, field: {'template_id': 'wrong'}}
                        return replace(result, selections=selections)
                    return result

                with patch.object(writer, 'write', regress):
                    self.assert_findings(self.invoke(), 'FAIL good-reply-dropped')

    def test_c2_3_write_none(self):
        # A writer refusal for the good reply must not become a traceback or a silent skip.
        writer = self.tool.copy.Writer
        write = writer.write

        def regress(instance, ctx, select=None):
            result = write(instance, ctx, select)
            return None if select is not None and not result.basic else result

        with patch.object(writer, 'write', regress):
            self.assert_findings(self.invoke(), 'FAIL write-none good')

    def test_c2_4_check_error(self):
        # A checker exception is a failure, but its message must not be copied into the receipt.
        copy = self.tool.copy
        real_selector, real_write = copy.codex_selector, copy.Writer.write
        first = True

        def broken_selector(transport):
            nonlocal first
            if first:
                first = False
                raise RuntimeError('synthetic exception detail')
            return real_selector(transport=transport)

        def broken_write(instance, ctx, select=None):
            result = real_write(instance, ctx, select)
            if select is not None and not result.basic:
                raise RuntimeError('synthetic exception detail')
            return result

        with patch.object(copy, 'codex_selector', broken_selector):
            self.assert_findings(self.invoke(), 'FAIL check-error')
        with patch.object(copy.Writer, 'write', broken_write):
            self.assert_findings(self.invoke(), 'FAIL check-error')

    def test_c3_usage_exit_2(self):
        # No argument may run the checks or be treated as a successful option.
        for arg in ('extra', '--unknown', '--help', '--'):
            with self.subTest(arg=arg):
                code, out, err = self.cli(arg)
                self.assertEqual(code, 2)
                self.assertEqual(out, '')
                self.assertTrue(err.startswith('usage:'))
                self.assertIn('error: unrecognized arguments:', err.splitlines()[-1])

    def test_c4_read_only(self):
        # Accidental cache, preview or config writes change the source-tree snapshot.
        before = snapshot()
        self.assert_run(self.cli(), 0, PASS)
        self.assertEqual(snapshot(), before)

    def test_c5_output_shape(self):
        # Keep the receipt parseable, including when the checker has a finding.
        row = r'reply [a-z0-9-]+ raw=(dict|list|none) basic=(yes|no)'
        for line in self.assert_run(self.invoke(), 0, PASS):
            self.assertRegex(line, f'^{row}$')
        with patch.object(self.tool.copy, '_unique', dict):
            for line in self.assert_run(self.invoke(), 1, FAIL):
                self.assertRegex(line, f'^(?:{row}|FAIL bad-reply-used dup-(?:top|nested))$')

    def test_c6_fixture(self):
        # A last-key-wins decoder must be detected even when rendering still falls back.
        with patch.object(self.tool.copy, '_unique', dict):
            self.assert_findings(self.invoke(), 'FAIL bad-reply-used dup-top', 'FAIL bad-reply-used dup-nested')

    def test_c7_live_pins(self):
        # Pin the distinction between adapter rejection and writer fallback, not just the trailer.
        self.assertEqual(self.assert_run(self.cli(), 0, PASS), [
            'reply good raw=dict basic=no',
            'reply status500 raw=none basic=yes',
            'reply dup-top raw=none basic=yes',
            'reply dup-nested raw=none basic=yes',
            'reply not-json raw=none basic=yes',
            'reply no-choices raw=none basic=yes',
            'reply raw-not-json raw=none basic=yes',
            'reply oserror raw=none basic=yes',
            'reply timeout raw=none basic=yes',
            'reply failed raw=none basic=yes',
            'reply list raw=list basic=yes',
            'reply extra-key raw=dict basic=yes',
            'reply unknown-template raw=dict basic=yes',
        ])
