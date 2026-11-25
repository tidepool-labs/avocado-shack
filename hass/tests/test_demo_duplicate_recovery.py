"""Operator boundary for the public OFF duplicate-recovery exercise."""
import contextlib
import io
import json
import unittest
from types import SimpleNamespace
from unittest.mock import patch

from hass import preview
from scripts.hass import demo_duplicate_recovery as drill


class DuplicateRecoveryTests(unittest.TestCase):
    def test_missing_browser_fails_closed(self):
        # A stand-in or a skipped browser must not appear to be a successful rehearsal.
        with patch.object(preview, 'Previewer', return_value=SimpleNamespace(env={})):
            out = io.StringIO()
            with contextlib.redirect_stdout(out):
                self.assertEqual(drill.main([]), 1)
        self.assertEqual(json.loads(out.getvalue())['failed_step'], 'browser')

    def test_public_fixture_uses_real_editor_renderer_and_delivery_gate(self):
        if not preview.Previewer(drill.ROOT).env.get('PLAYWRIGHT_MODULE'):
            self.skipTest('requires the real Playwright renderer')
        # Plausible regressions: a duplicate overwrites the original, or its old/undelivered
        # code is accepted. Only this journey ties the real duplicate refusal to the recovered PNG.
        out = io.StringIO()
        with contextlib.redirect_stdout(out):
            self.assertEqual(drill.main([]), 0, out.getvalue())
        result = json.loads(out.getvalue())
        self.assertEqual(result['result'], 'PASS')
        self.assertEqual(result['mode'], 'public OFF fixture only')
        self.assertEqual(result['steps'], ['duplicate_refused', 'replacement_delivered', 'only_confirmed_version_reaches_off_gate'])
