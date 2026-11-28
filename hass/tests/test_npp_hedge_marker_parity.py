"""Offline contract tests for the S4-to-S5 maker quote comparison."""

from contextlib import contextmanager, redirect_stderr, redirect_stdout
from importlib.util import module_from_spec, spec_from_file_location
import io
from pathlib import Path
import runpy
import subprocess
import sys
from tempfile import TemporaryDirectory
import unittest
from unittest.mock import patch


ROOT = Path(__file__).resolve().parents[2]
SCRIPT = ROOT / 'scripts/hass/npp_hedge_marker_parity.py'
PASS = 'PASS npp_hedge_marker_parity'
FAIL = 'FAIL npp_hedge_marker_parity'
ATTEMPTS = None


def deny_io(event, _args):
    # Count before raising: a stage could catch the denial and return a result.
    if ATTEMPTS is not None and (event.startswith(('socket.', 'subprocess.')) or event in {
        'os.exec', 'os.fork', 'os.forkpty', 'os.posix_spawn', 'os.spawn', 'os.system', 'pty.spawn',
    }):
        ATTEMPTS.append(event)
        raise AssertionError('fixture attempted socket or process I/O')


@contextmanager
def offline():
    global ATTEMPTS
    ATTEMPTS = []
    try:
        yield ATTEMPTS
    finally:
        ATTEMPTS = None


class HedgeMarkerParityTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        # The hook is inert outside fixture execution, including the deliberate CLI launch.
        sys.addaudithook(deny_io)

    def setUp(self):
        self.scratch = Path(self.enterContext(TemporaryDirectory())).resolve()
        spec = spec_from_file_location('npp_hedge_marker_parity', SCRIPT)
        assert spec is not None and spec.loader is not None
        self.tool = module_from_spec(spec)
        with offline() as attempts:
            spec.loader.exec_module(self.tool)
        self.assertEqual(attempts, [])

    def invoke(self):
        stdout, stderr = io.StringIO(), io.StringIO()
        with offline() as attempts, redirect_stdout(stdout), redirect_stderr(stderr):
            code = self.tool.main([])
        self.assertEqual(attempts, [])
        self.assertEqual(stderr.getvalue(), '')
        return code, stdout.getvalue().splitlines()

    def cli(self, *args):
        return subprocess.run(
            [sys.executable, '-B', str(Path(__file__).resolve()), '--guarded-cli', *args],
            cwd=self.scratch, capture_output=True, text=True, timeout=20,
        )

    def assert_pass(self, code, lines):
        self.assertEqual(code, 0)
        self.assertEqual(lines[-1], PASS)
        self.assertEqual([line for line in lines if line.startswith('FAIL ')], [])

    def assert_findings(self, code, lines, *expected):
        self.assertEqual(code, 1)
        self.assertEqual(lines[-1], FAIL)
        self.assertEqual([line for line in lines[:-1] if line.startswith('FAIL ')], list(expected))

    @contextmanager
    def writer_markers(self, *, append):
        # Change only the rule input on a fresh real Writer, not the S4 asset bytes.
        writer = self.tool.copy.Writer
        init = writer.__init__

        def adjusted(instance, pinned):
            init(instance, pinned)
            instance.fact_rules['negation_hedge_markers'].extend(append)

        with patch.object(writer, '__init__', adjusted):
            yield

    def bypass_negative_control(self):
        research = self.tool.research
        check = research._check

        def bypass(row, *args):
            if row['quote'] == 'Fixture Farm is not small, alongside honey.':
                return None
            return check(row, *args)

        return patch.object(research, '_check', bypass)

    def test_c1_full_pass(self):
        # The fixture is a real successful CLI, not just an importable helper.
        result = self.cli()
        self.assertEqual(result.stderr, '')
        self.assert_pass(result.returncode, result.stdout.splitlines())

    def test_c2_findings_trailer(self):
        # A connected mismatch must change the exit status and final line.
        with self.writer_markers(append=('family',)):
            self.assert_findings(*self.invoke(), 'FAIL s5-stricter 11')

    def test_c2_1_s5_stricter(self):
        # Do not stop at or duplicate the first mismatch; S5-only keeps aren't failures.
        with self.writer_markers(append=('family', 'unsold')):
            self.assert_findings(*self.invoke(), 'FAIL s5-stricter 11', 'FAIL s5-stricter 13')

    def test_c2_2_control_broken(self):
        # The positive control can fail on its own; two broken controls still report once.
        with self.writer_markers(append=('willow',)):
            code, lines = self.invoke()
            self.assert_findings(code, lines, 'FAIL s5-stricter 10', 'FAIL control-broken')
            self.assertIn('hedge 10 s4=keep s5=refuse', lines)
            with self.bypass_negative_control():
                self.assert_findings(*self.invoke(), 'FAIL s5-stricter 2', 'FAIL s5-stricter 10',
                                     'FAIL control-broken')

    def test_c2_3_check_error(self):
        # Exceptions and corrupt stage data must fail closed without diagnostics from the stage.
        research = self.tool.research
        writer = self.tool.copy.Writer
        actual_research = research.research

        def bad_receipt(*args, **kwargs):
            result = actual_research(*args, **kwargs)
            result.receipt['facts'][0]['quote'] = 'incorrect quote'
            return result

        def bad_projection(*args, **kwargs):
            result = actual_research(*args, **kwargs)
            if result.story_facts:
                return research.Result((dict(result.story_facts[0], value='jam'),), result.receipt)
            return result

        def duplicate_verify(*args, **kwargs):
            verify = kwargs['verify']

            def twice(*row_args):
                verify(*row_args)
                return verify(*row_args)

            return actual_research(*args, **dict(kwargs, verify=twice))

        for name, mutation in (
            ('S4 exception', patch.object(research, 'research', side_effect=RuntimeError('fixture diagnostic'))),
            ('S5 exception', patch.object(writer, 'bindings', side_effect=RuntimeError('fixture diagnostic'))),
            ('receipt', patch.object(research, 'research', new=bad_receipt)),
            ('projection', patch.object(research, 'research', new=bad_projection)),
            ('verify traffic', patch.object(research, 'research', new=duplicate_verify)),
            ('binding value', patch.object(writer, 'bindings', return_value={'makes': ('honey', 'wrong-id')})),
            ('binding shape', patch.object(writer, 'bindings', return_value=[])),
        ):
            with self.subTest(name=name), mutation:
                code, lines = self.invoke()
                self.assert_findings(code, lines, 'FAIL check-error')
                self.assertNotIn('fixture diagnostic', '\n'.join(lines))

    def test_c3_usage_exit_2(self):
        # Arguments must not accidentally trigger an auditable PASS or run the corpus.
        for argument in ('extra', '--unknown'):
            with self.subTest(argument=argument):
                result = self.cli(argument)
                self.assertEqual(result.returncode, 2)
                self.assertEqual(result.stdout, '')
                self.assertIn('error: unrecognized arguments:', result.stderr)
                self.assertIn(argument, result.stderr)

    def test_c4_read_only(self):
        # Catch sidecars, bytecode and writes in either checkout tree.
        def snapshot():
            entries = {}
            for root in (ROOT / 'hass', ROOT / 'storefront-mockup'):
                self.assertTrue(root.is_dir())
                for path in (root, *root.rglob('*')):
                    stat = path.lstat()
                    entries[path.relative_to(ROOT)] = (stat.st_size, stat.st_mtime_ns)
            return entries

        before = snapshot()
        result = self.cli()
        self.assertEqual(result.stderr, '')
        self.assert_pass(result.returncode, result.stdout.splitlines())
        self.assertEqual(snapshot(), before)
        self.assertEqual(list(self.scratch.iterdir()), [])

    def test_c5_output_shape(self):
        # No debug logs, partial rows or unexpected failure forms on ordinary runs.
        code, ordinary = self.invoke()
        self.assert_pass(code, ordinary)
        self.assertEqual(len(ordinary), 15)
        with self.writer_markers(append=('family',)):
            code, stricter = self.invoke()
        self.assert_findings(code, stricter, 'FAIL s5-stricter 11')
        self.assertEqual(stricter[14:], ['FAIL s5-stricter 11', FAIL])
        for lines in (ordinary, stricter):
            for index, line in enumerate(lines[:14]):
                self.assertRegex(line, rf'^hedge {index} s4=(refuse|keep) s5=(refuse|keep)$')

    def test_c6_fixture(self):
        # Real writers respond to marker drift, and real S4 responds to bypassed dispatch.
        with self.writer_markers(append=('family',)):
            code, lines = self.invoke()
            self.assert_findings(code, lines, 'FAIL s5-stricter 11')
            self.assertIn('hedge 11 s4=keep s5=refuse', lines)
        with self.bypass_negative_control():
            code, lines = self.invoke()
            self.assert_findings(code, lines, 'FAIL s5-stricter 2', 'FAIL control-broken')
            self.assertIn('hedge 2 s4=keep s5=refuse', lines)
        self.assert_pass(*self.invoke())

    def test_c7_live_pins(self):
        # Guard the measured asymmetric vectors and verify the actual handoff, not just its log.
        s4_keeps = (5, 10, 11, 13)
        s5_keeps = (1, 4, 5, 10, 11, 13)
        receipts, bindings = [], []
        research = self.tool.research
        writer = self.tool.copy.Writer
        actual_research, actual_bindings = research.research, writer.bindings

        def observe_s4(*args, **kwargs):
            result = actual_research(*args, **kwargs)
            receipts.append(result)
            return result

        def observe_s5(instance, ctx, field):
            result = actual_bindings(instance, ctx, field)
            bindings.append((ctx, field, result))
            return result

        with patch.object(research, 'research', observe_s4), patch.object(writer, 'bindings', observe_s5):
            code, lines = self.invoke()
        self.assert_pass(code, lines)
        labels = ('refuse', 'keep')
        self.assertEqual(lines[:-1], [
            f'hedge {i} s4={labels[i in s4_keeps]} s5={labels[i in s5_keeps]}' for i in range(14)
        ])
        self.assertEqual(len(receipts), 14)
        self.assertEqual(len(bindings), 14)
        self.assertEqual(tuple(i for i, receipt in enumerate(receipts) if receipt.story_facts), s4_keeps)
        self.assertEqual(tuple(i for i, (_, _, result) in enumerate(bindings) if 'makes' in result), s5_keeps)
        for i, (receipt, (ctx, field, result)) in enumerate(zip(receipts, bindings, strict=True)):
            self.assertEqual(field, 'story')
            fact, = ctx.facts
            self.assertEqual((fact.id, fact.value, fact.verdict), ('official-makes', 'honey', 'supports'))
            row = receipt.story_facts[0] if i in s4_keeps else receipt.receipt['facts'][0]
            self.assertEqual((fact.slot, fact.value, fact.url, fact.quote),
                             (row['slot'], row['value'], row['url'], row['quote']))
            if i in s4_keeps:
                self.assertEqual(fact.id, row['id'])
            if i in s5_keeps:
                self.assertEqual(result['makes'], ('honey', fact.id))


if __name__ == '__main__':
    if sys.argv[1:2] == ['--guarded-cli']:
        sys.argv = [str(SCRIPT), *sys.argv[2:]]
        sys.addaudithook(deny_io)
        with offline() as attempts:
            try:
                runpy.run_path(str(SCRIPT), run_name='__main__')
            finally:
                if attempts:
                    raise AssertionError('fixture attempted socket or process I/O')
    else:
        unittest.main()
