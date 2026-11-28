"""Offline CLI checks against pinned NPP edits and a town-preserving fixture."""

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
SCRIPT = ROOT / 'scripts/hass/npp_maker_restated_town.py'
PASS = 'PASS npp_maker_restated_town'
FAIL = 'FAIL npp_maker_restated_town'


class MakerRestatedTownTests(unittest.TestCase):
    def setUp(self):
        self.temp = self.enterContext(TemporaryDirectory())
        self.addCleanup(setattr, sys, 'path', sys.path[:])
        spec = importlib.util.spec_from_file_location(SCRIPT.stem, SCRIPT)
        assert spec is not None and spec.loader is not None
        self.tool = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(self.tool)

    def invoke(self):
        stdout, stderr = StringIO(), StringIO()
        with redirect_stdout(stdout), redirect_stderr(stderr):
            status = self.tool.main([])
        self.assertEqual(stderr.getvalue(), '')
        return status, stdout.getvalue().splitlines()

    def cli(self, *args):
        return subprocess.run([sys.executable, '-B', str(SCRIPT), *args],
                              cwd=self.temp, capture_output=True, text=True, timeout=10)

    def preserving_apply(self):
        original = self.tool.edits.apply

        def apply(listing, parsed):
            maker = listing['maker'].casefold()
            return original(listing, [
                replace(edit, patch=tuple((field, value) for field, value in edit.patch
                                          if field != 'maker' or value.casefold() != maker))
                for edit in parsed
            ])

        return patch.object(self.tool.edits, 'apply', side_effect=apply)

    def test_c1_full_pass(self):
        # A hard-coded failing exit/trailer or early PASS would break the clean run.
        with self.preserving_apply() as apply:
            status, lines = self.invoke()
        self.assertEqual((status, lines[-1]), (0, PASS))
        self.assertEqual(apply.call_count, 5)
        self.assertEqual(len(lines), 6)

    def test_c2_findings_trailer(self):
        # A failed middle read must neither erase earlier findings nor stop later checks.
        original = self.tool.edits.read

        def read(grammar, text, finance):
            if text == 'made by Miners, Watsonville':
                raise RuntimeError('fixture error')
            return original(grammar, text, finance)

        with patch.object(self.tool.edits, 'read', side_effect=read):
            status, lines = self.invoke()
        self.assertEqual((status, lines[-1]), (1, FAIL))
        self.assertEqual(lines[:-1], [
            'case 0 maker=Miners town=none', 'FAIL town-dropped 0',
            'case 1 maker=Miners town=none', 'FAIL town-dropped 1',
            'FAIL check-error', 'case 3 maker=Bees Co town=none',
            'case 4 maker=Miners town=Watsonville',
        ])

    def test_c2_1_town_dropped(self):
        # The lowercase input alone doesn't test casefold: the real parser title-cases it.
        original = self.tool.edits.apply

        def apply(listing, parsed):
            out, changed = original(listing, parsed)
            if out['maker'] == 'Miners' and 'makerTown' not in out:
                out['maker'] = 'MiNeRs'
            return out, changed

        with patch.object(self.tool.edits, 'apply', side_effect=apply):
            status, lines = self.invoke()
        self.assertEqual((status, lines[-1]), (1, FAIL))
        self.assertEqual([line for line in lines[:-1] if line.startswith('FAIL ')],
                         ['FAIL town-dropped 0', 'FAIL town-dropped 1'])

    def test_c2_2_check_error(self):
        # An exception during setup must be a finding without a traceback or error text.
        for module, name in ((self.tool.hass.npp, 'assets'), (self.tool.edits, 'Grammar')):
            with self.subTest(call=name), patch.object(module, name, side_effect=RuntimeError('fixture error')):
                status, lines = self.invoke()
                self.assertEqual((status, lines[-1]), (1, FAIL))
                self.assertEqual(lines[:-1], ['FAIL check-error'])

    def test_c3_usage_exit_2(self):
        # Reject stray input, including argparse's otherwise successful help flag.
        for arg in ('extra', '--unknown', '--help', '-h', '--'):
            with self.subTest(arg=arg):
                result = self.cli(arg)
                self.assertEqual((result.returncode, result.stdout), (2, ''))
                self.assertIn('error: unrecognized arguments:', result.stderr.splitlines()[-1])

    def test_c4_read_only(self):
        # Catch a checker that writes a report or changes a pin or storefront entry.
        def snapshot():
            entries = {}
            for tree in ('hass', 'storefront-mockup'):
                root = ROOT / tree
                for path in (root, *root.rglob('*')):
                    stamp = path.lstat()
                    entries[path.relative_to(ROOT)] = stamp.st_size, stamp.st_mtime_ns
            return entries

        before = snapshot()
        result = self.cli()
        self.assertEqual((result.returncode, result.stdout.splitlines()[-1]), (1, FAIL))
        self.assertEqual(snapshot(), before)

    def test_c5_output_shape(self):
        # The real CLI must not add progress banners, debug lines, or stderr warnings.
        result = self.cli()
        lines = result.stdout.splitlines()
        self.assertEqual((result.returncode, lines[-1], result.stderr), (1, FAIL, ''))
        for line in lines[:-1]:
            self.assertRegex(line, r'^(?:case [0-4] maker=\S.* town=\S.*|FAIL town-dropped [0-4])$')

    def test_c6_fixture(self):
        # Removing a redundant maker patch must not remove the town or mask a real maker change.
        with self.preserving_apply():
            status, lines = self.invoke()
        self.assertEqual((status, lines[-1]), (0, PASS))
        self.assertEqual(lines[:-1], [
            'case 0 maker=Miners town=Watsonville', 'case 1 maker=Miners town=Watsonville',
            'case 2 maker=Miners town=Watsonville', 'case 3 maker=Bees Co town=none',
            'case 4 maker=Miners town=Watsonville',
        ])

    def test_c7_live_pins(self):
        # Pin the diagnostic on this base, including the supplier control and unchanged parent.
        npp, edits = self.tool.hass.npp, self.tool.edits
        with (patch.object(npp, 'assets', wraps=npp.assets) as assets,
              patch.object(edits, 'Grammar', wraps=edits.Grammar) as grammar,
              patch.object(edits, 'read', wraps=edits.read) as read,
              patch.object(edits, 'apply', wraps=edits.apply) as apply):
            status, lines = self.invoke()
        self.assertEqual((status, lines[-1]), (1, FAIL))
        self.assertEqual(lines[:-1], [
            'case 0 maker=Miners town=none', 'FAIL town-dropped 0',
            'case 1 maker=Miners town=none', 'FAIL town-dropped 1',
            'case 2 maker=Miners town=Watsonville', 'case 3 maker=Bees Co town=none',
            'case 4 maker=Miners town=Watsonville',
        ])
        assets.assert_called_once_with()
        self.assertEqual(grammar.call_count, 1)
        self.assertEqual([call.args[1:] for call in read.call_args_list], [
            ('made by Miners', {}), ('made by miners', {}), ('made by Miners, Watsonville', {}),
            ('made by Bees Co', {}), ('from Bees', {}),
        ])
        self.assertEqual(apply.call_count, 5)
        self.assertEqual(self.tool.LISTING, {'name': 'Honey', 'maker': 'Miners', 'makerTown': 'Watsonville'})
