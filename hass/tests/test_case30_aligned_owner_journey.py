"""Case 30 owner journey with an ordinary-looking maker address, and its reserved-address control (plans H52, FIX2).

Strict NPP case 30 now names the ordinary-looking `minersfigs.com` address (served only by the harness's local fake
host from the case's own page file) and expects the label casing in the description (G decision FIX2). The reserved
`minersfigs.example` address that the strict case used before stays covered here as its own negative control: the
same view with only the address swapped back must still be refused. Python sockets are loopback-only.

Fixtures only: no model, network, live Hass, host.json, Clover or recording.
"""
import copy
import importlib.util
import ipaddress
import json
import socket
import sys
import unittest
from pathlib import Path
from unittest.mock import patch

from hass import npp, preview

ROOT = Path(__file__).resolve().parents[2]
FIXTURE = json.loads((ROOT / 'hass' / 'tests' / 'fixtures' / 'case30_aligned_owner.json').read_text(encoding='utf-8'))
spec = importlib.util.spec_from_file_location('npp_run_case30_aligned', ROOT / 'hass' / 'tests' / 'npp' / 'run_npp.py')
run_npp = importlib.util.module_from_spec(spec)
sys.modules[spec.name] = run_npp
spec.loader.exec_module(run_npp)

RESERVED, OWNER_URL = FIXTURE['reserved_url'], FIXTURE['owner_url']
_RESOLVE, _CONNECT = socket.getaddrinfo, socket.socket.connect


def _loopback_only(host):
    if host is not None and not ipaddress.ip_address(host).is_loopback:
        raise AssertionError(f'non-loopback network attempt: {host}')


def _resolve(host, *args, **kwargs):
    _loopback_only(host)
    return _RESOLVE(host, *args, **kwargs)


def _connect(sock, addr):
    if sock.family in (socket.AF_INET, socket.AF_INET6):
        _loopback_only(addr[0])
    return _CONNECT(sock, addr)


def loopback_only():
    return (patch.object(socket, 'getaddrinfo', side_effect=_resolve),
            patch.object(socket.socket, 'connect', _connect))


def strict_view():
    """Case 30 exactly as the strict harness runs it (its only variant), with the fixture's S2 reading added."""
    case = run_npp.load_cases()[FIXTURE['base_case']]
    [(variant, view)] = list(run_npp.case_views(case))
    assert variant is None
    view = copy.deepcopy(view)
    view['inputs'].setdefault('stubs', {})['identify'] = copy.deepcopy(FIXTURE['identify']['output'])
    return view


def aligned_view():
    """The owner journey with the ordinary-looking address: since FIX2 this is the strict case itself."""
    view = strict_view()
    assert RESERVED not in json.dumps(view), 'the reserved address survived somewhere'
    return view


def reserved_view(url=RESERVED):
    """The strict view with only the owner's address swapped back to the reserved one everywhere the case names it."""
    view = strict_view()
    first = view['turns'][0]
    assert first['text'].count(OWNER_URL) == 1, first['text']
    first['text'] = first['text'].replace(OWNER_URL, url)
    pages = view['inputs']['web']['pages']
    pages[url] = pages.pop(OWNER_URL)
    for row in view['inputs']['stubs']['extract']:
        assert row['url'] == OWNER_URL, row
        row['url'] = url
    expect = view['expect']
    assert expect['research']['owner_stated_url'] == OWNER_URL and expect['listing']['maker_url'] == OWNER_URL
    expect['research']['owner_stated_url'] = url
    expect['listing']['maker_url'] = url
    assert OWNER_URL not in json.dumps(view), 'the ordinary address survived somewhere'
    return view


def changed_paths(a, b, path=()):
    if isinstance(a, dict) and isinstance(b, dict):
        out = []
        for key in sorted(set(a) | set(b)):
            if key not in a or key not in b:
                out.append(path + (key,))
            else:
                out += changed_paths(a[key], b[key], path + (key,))
        return out
    if isinstance(a, list) and isinstance(b, list) and len(a) == len(b):
        return [p for i, (x, y) in enumerate(zip(a, b)) for p in changed_paths(x, y, path + (i,))]
    return [] if a == b else [path]


def renderer_ready():
    return bool(preview.Previewer(str(ROOT)).env.get('PLAYWRIGHT_MODULE'))


class AlignedFixtureShapeTests(unittest.TestCase):
    def test_strict_case_30_names_the_ordinary_address_and_the_label_casing(self):
        # Contract (FIX2): strict case 30 is the owner journey with an ordinary-looking address and the description in
        # the label casing of the saved S2 reading. Bug caught: the strict case drifting back to the reserved address
        # (which the guard refuses at every turn, so the case could never reach a card).
        case = run_npp.load_cases()[30]
        self.assertIn(OWNER_URL, case['turns'][0]['text'])
        self.assertEqual(case['expect']['research']['owner_stated_url'], OWNER_URL)
        self.assertNotIn(RESERVED, json.dumps(case))
        self.assertEqual(case['expect']['description_equals'], FIXTURE['description_equals'])

    def test_the_reserved_control_differs_from_the_strict_case_only_at_the_address(self):
        # Contract: same maker, town, photo, page file, quote controls, price, edit, yes and undo.
        # Bug caught: a control that quietly drops a negated or past quote control or changes the owner's words.
        strict, reserved = strict_view(), reserved_view()
        self.assertEqual(reserved['turns'][0]['text'],
                         strict['turns'][0]['text'].replace(OWNER_URL, RESERVED))
        self.assertEqual(reserved['inputs']['web']['pages'][RESERVED], strict['inputs']['web']['pages'][OWNER_URL])
        paths = {p for p in changed_paths(strict, reserved)}
        allowed = {('turns', 0, 'text'), ('inputs', 'web', 'pages', RESERVED), ('inputs', 'web', 'pages', OWNER_URL),
                   ('expect', 'research', 'owner_stated_url'), ('expect', 'listing', 'maker_url')}
        allowed |= {('inputs', 'stubs', 'extract', i, 'url') for i in range(len(strict['inputs']['stubs']['extract']))}
        self.assertEqual(paths - allowed, set())
        quotes = [(r['slot'], r['value'], r['quote']) for r in reserved['inputs']['stubs']['extract']]
        self.assertEqual(quotes, [(r['slot'], r['value'], r['quote']) for r in strict['inputs']['stubs']['extract']])
        self.assertEqual(len(quotes), 4)


class AlignedResearchTests(unittest.TestCase):
    def test_production_seed_reads_the_ordinary_address_from_the_owner_words(self):
        # Contract: production picks the owner's maker, town and this address out of his own message.
        # Bug caught: the regression passing only because the harness hands research an address production never read.
        from hass.npp import stages
        view = aligned_view()
        seed = run_npp.owner_seed(view)
        self.assertEqual((seed['maker'], seed['url']), ('Miners', OWNER_URL))
        _town, url = stages._site_words(seed['maker'], [view['turns'][0]['text']])
        self.assertEqual(url, OWNER_URL)

    def test_all_four_quote_controls_hold_on_the_local_fake_host(self):
        # Contract: supported nature and product kept with their quote; past town and negated organic claim dropped;
        # one fetch of the owner's page, no search, nothing off loopback.
        # Bug caught: the plausible address making research keep a past or negated fact, or search the web.
        resolve, connect = loopback_only()
        with resolve, connect:
            failures, evidence = run_npp.run_research(aligned_view())
        self.assertEqual(failures, [])
        result, world = evidence['result'], evidence['world']
        self.assertEqual(sorted((f['slot'], f['value']) for f in result.facts),
                         [('makes', 'dried figs'), ('nature', 'orchard')])
        self.assertEqual(sorted(r['slot'] for r in result.receipt['facts'] if not r['kept']), ['makes', 'town'])
        self.assertEqual(world.calls['search'], 0)
        self.assertEqual(set(world.fetched), {OWNER_URL})


class ReservedAddressTests(unittest.TestCase):
    def test_the_reserved_address_is_still_refused_with_the_same_reading_and_page(self):
        # Contract: strict case 30's reserved .example address never reaches a card, a yes or a commit, even with the
        # S2 reading and page that make the strict journey pass.
        # Bug caught: the ordinary-address strict case masking a loosened reserved-domain guard. The two views differ
        # only in the address (see AlignedFixtureShapeTests), so this pair pins the refusal on the address alone. The
        # guard refuses before any drawing, so the renderer is not started.
        resolve, connect = loopback_only()
        with resolve, connect:
            failures, evidence = run_npp.run_conversation(reserved_view(), run_npp.Tapes())
        state = evidence['state']
        self.assertEqual((state['cards'], state['approvals'], state['commits']), (0, 0, 0))
        self.assertNotEqual(state['state'], 'published')
        self.assertEqual(sum(len(o['cards']) for o in evidence['observed']), 0)
        self.assertEqual(evidence['missing'], [])  # no drawing was even attempted (it would miss the capture tape)
        self.assertIn("turn 0: reply kind 'guard', want 'card'", failures)


@unittest.skipUnless(renderer_ready(), 'the real card renderer (Node 22 + Playwright) is not available')
class AlignedOwnerJourneyTests(unittest.TestCase):
    def test_photo_details_to_delivered_v1_v2_one_yes_one_commit_and_undo(self):
        # Contract: with the real phone renderer, the owner gets v1 then v2 (price edit), says yes to v2 only, one commit
        # publishes it with the maker panel and the two kept facts, and undo drafts the hide; the card checks pass.
        # Bug caught: a plausible maker address that renders, publishes or undoes differently from the strict contract.
        resolve, connect = loopback_only()
        with resolve, connect:
            failures, evidence = run_npp.run_conversation(aligned_view(), run_npp.Tapes(), preview=True)
        self.assertEqual(failures, [])
        self.assertEqual(evidence['missing'], [])
        self.assertEqual(evidence['gaps'], [])
        state = evidence['state']
        self.assertEqual(state['state'], 'published')
        self.assertEqual((state['cards'], state['approvals'], state['commits']), (2, 1, 1))
        self.assertEqual([len(turn['cards']) for turn in evidence['observed']], [1, 1, 0, 0])


if __name__ == '__main__':
    unittest.main()
