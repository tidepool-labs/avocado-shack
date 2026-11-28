"""Offline runbook contract: inspect docs and argparse; never execute a setup step."""
import argparse
import ast
import importlib
import inspect
import re
import unittest
from pathlib import Path
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[2]
DOC = ROOT / 'docs/hass/MAC_RUNBOOK.md'
MARK = re.compile(r'<!-- step (\d+) needs: ([\w, -]+) makes: ([\w, -]+) -->')


def ids(text):
    return set() if text.strip() == '-' else set(text.split(','))


def parser_for(module):
    captured = []

    def capture(parser, *args, **kwargs):
        captured.append(parser)
        raise InterruptedError('inspection only')

    with patch.object(argparse.ArgumentParser, 'parse_args', capture):
        try:
            module.main([])
        except InterruptedError:
            pass
    return captured[0]


class MacRunbookTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.doc = DOC.read_text()
        cls.steps = {int(n): body for n, body in re.findall(
            r'(?ms)^(\d+)\. (.*?)(?=^\d+\. |^## Phase |\Z)', cls.doc)}

    def test_numbering_phases_and_budgets(self):
        self.assertEqual(re.findall(r'(?m)^(\d+)\. ', self.doc), [str(n) for n in range(1, 24)])
        self.assertEqual(re.findall(r'^## Phase ([A-E])', self.doc, re.M), list('ABCDE'))
        phases = re.split(r'^## Phase [A-E].*$', self.doc, flags=re.M)[1:]
        self.assertEqual([len(re.findall(r'^\d+\. ', p, re.M)) for p in phases], [9, 2, 3, 5, 4])
        self.assertLessEqual(len(self.doc.splitlines()), 210)
        self.assertLessEqual(len(Path(__file__).read_text().splitlines()), 150)
        connect = (ROOT / 'docs/hass/CONNECT.md').read_text()
        self.assertLessEqual(len(connect.splitlines()), 60)
        self.assertIn('[MAC_RUNBOOK.md](MAC_RUNBOOK.md)', connect)

    def test_prerequisite_walk_and_safety_edges(self):
        made, creators = set(), {}
        for n, body in self.steps.items():
            matches = MARK.findall(body)
            self.assertEqual(len(matches), 1, n)
            number, needs, makes = matches[0]
            self.assertEqual(int(number), n)
            self.assertFalse(ids(needs) - made, (n, ids(needs) - made))
            for item in ids(makes):
                self.assertNotIn(item, creators, item)
                creators[item] = n
            made |= ids(makes)
            self.assertIn('**G /', body)
            self.assertIn('Expected:', body)
            if re.search(r'python3(?:\.12)? (?:hass/|[^`\n]*mac/)', body):
                self.assertLessEqual(creators['R'], n)
                self.assertLessEqual(creators['runtime'], n)
        for before, after in [('host-key', 'services'), ('deploy-key', 'site-checkout'),
                              ('ssh-alias', 'site-checkout'), ('release-config', 'live'),
                              ('adopted', 'live'), ('picture-ok', 'live')]:
            self.assertLess(creators[before], creators[after])
        self.assertIn('**picture**', self.steps[19])
        self.assertIn('Stop here if no picture', self.steps[19])
        self.assertIn('"hold"', self.steps[16])
        self.assertIn('`private`', self.steps[19])
        self.assertIn('`live`', self.steps[22])

    def test_commands_match_real_argparse_without_running_them(self):
        commands = re.findall(r'python3(?:\.12)? (?:[^`\n ]*/)?((?:hass|mac)/[\w_]+\.py)(?: ([\w-]+))?', self.doc)
        self.assertTrue(commands)
        for path, command in set(commands):
            self.assertTrue((ROOT / path).is_file(), path)
            module = importlib.import_module(path[:-3].replace('/', '.'))
            parser = parser_for(module)
            choices = set()
            for action in parser._actions:
                if action.choices:
                    choices.update(action.choices)
            if command:
                self.assertIn(command, choices, path)
        for unit in re.findall(r'\bhass-(?:receiver|worker|health|backup)(?:\.(?:timer|service))?\b', self.doc):
            self.assertTrue((ROOT / 'deploy/hass' / (unit if '.' in unit else unit + '.service')).is_file(), unit)

    def test_config_names_match_closed_keys_and_settings(self):
        from hass import conversation, host, publish_live
        from mac import hass_forwarder
        blocks = re.findall(r'```json\n(.*?)\n\s*```', self.doc, re.S)
        self.assertEqual(len(blocks), 3)
        names = lambda text: set(re.findall(r'"(\w+)"\s*:', text))
        self.assertEqual(names(blocks[0]), hass_forwarder.KEYS - {'gChat', 'ownerChats'})  # gChat and ownerChats are optional: documented in BRIDGE_WIRING.md
        sandbox_doc = (ROOT / 'docs/hass/SANDBOX.md').read_text(encoding='utf-8')
        sandbox_keys = {'live', 'off', 'mode_gen', 'demoLock'}  # optional switch keys: documented in SANDBOX.md, absent from the first-install example
        for key in sandbox_keys:
            self.assertIn('\"' + key + '\"', sandbox_doc)
        self.assertEqual(names(blocks[1]) - {'url', 'model'}, host.KEYS - {'release', 'clover'} - sandbox_keys)
        tree = ast.parse(inspect.getsource(publish_live.release_config))
        release_keys = next(n.value for n in ast.walk(tree) if isinstance(n, ast.Assign)
                            and any(isinstance(t, ast.Name) and t.id == 'keys' for t in n.targets))
        self.assertEqual(names(blocks[2]), set(ast.literal_eval(release_keys)))
        source = inspect.getsource(conversation.load_settings)
        for key in ['ownerSenders', 'ownerChat', 'approvalTtlSeconds', 'interpreterDailyCap', 'liveSite', 'approvalNeedsCode']:
            self.assertIn('"' + key + '"', source)
            self.assertIn('`' + key + '`', self.doc)

    def test_transport_runtime_smoke_and_stop_contract(self):
        self.assertNotRegex(self.doc, r'\bscp\b|ssh[^`\n]*@?agentorange')
        for unit in (ROOT / 'deploy/hass').glob('*.service'):
            self.assertIn('WorkingDirectory=%h/.local/share/hass/runtime', unit.read_text())
        smoke = self.steps[18]
        positions = [smoke.index(x) for x in ['owner texts `status`', "stranger's text", 'replies `no`', 'hass/inbox.py status']]
        self.assertEqual(positions, sorted(positions))
        for token in ['launchctl bootout', 'touch ~/.config/hass/STOP', 'systemctl --user stop hass-worker hass-receiver']:
            self.assertIn(token, self.steps[23])
        self.assertLess(self.steps[16].index('Write `'), self.steps[16].index('python3 hass/host.py start-point --host'))
        for case in ['Cancelled', 'expired', 'duplicate', 'stale']:
            self.assertIn(case, self.steps[19])
        self.assertIn('must not create another commit', self.steps[19])
        self.assertNotRegex(self.doc, r'(?:ExecStart|WorkingDirectory)=[^\n]*writer')
        self.assertIn('bundle create', self.steps[11])
        self.assertIn('rev-parse HEAD', self.steps[11])
        self.assertIn('--confirm <manifest>', self.steps[21])
        self.assertNotRegex(self.doc, r'(?i)\b[0-9a-f]{32,}\b|\b(?:100\.\d+|192\.168)\.\d+\.\d+|\+\d[\d ()-]{7,}')
        self.assertNotRegex(self.doc, r'[\w.+-]+@[\w.-]+\.[a-zA-Z]{2,}')


if __name__ == '__main__':
    unittest.main()
