#!/usr/bin/env python3
"""Check the fixed S7 card text against storefront source, without running JS."""

import argparse
from pathlib import Path
import stat
import sys


ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))

from hass.npp import validate


SHOP = ROOT / 'storefront-mockup' / 'shop.js'
SHOP_CAP = 1_000_000
NAME = 'npp_card_fixed_text_check'

# Row ID, Python role (if any), expected Python value, literal JS snippets.
ROWS = (
    ('link', ':scope > .card-link', ('Link to this',),
     ('class="text-link card-link"', '>Link to this</a>')),
    ('badges', '.food-badges > span', ('New', 'Organic'),
     ('<div class="food-badges">', '<span>New</span>', '<span>Organic</span>')),
    ('summary', '.maker-story > summary', ('Meet the maker',),
     ('<details class="maker-story">', '<summary>Meet the maker')),
    ('visit', '.maker-story-content > a', ('Visit MAKERX ↗',),
     ('<div class="maker-story-content">',
      '>Visit ${esc(m.name)} <span aria-hidden="true">↗</span></a>')),
    ('see-all', '.maker-story-content > button.text-link[data-from]', ('See all 2 from MAKERX',),
     ('class="text-link" data-from=', 'See all ${makerCounts.get(p.producerKey)} from ${esc(m.name)}</button>')),
    ('availability', '.availability', (), ('class="product-meta availability"',)),
    ('origin-unknown', None, 'Ask us about the source in store.', ("'Ask us about the source in store.'",)),
    ('origin-forms', None, None, ('`From ${p.supplier}`', '`Based in ${maker(p).place}`')),
    ('market-brand', None, None, ("'From the market'",)),
)


def read_shop():
    """Return (text, None) or (None, a fixed finding); never parse JS or JSON."""
    try:
        info = SHOP.lstat()
        if not stat.S_ISREG(info.st_mode):
            return None, 'input-unsafe shop'
        if info.st_size > SHOP_CAP:
            return None, 'input-too-large shop'
        with SHOP.open('rb') as source:
            raw = source.read(SHOP_CAP + 1)
        if len(raw) > SHOP_CAP:
            return None, 'input-too-large shop'
        return raw.decode('utf-8'), None
    except (OSError, UnicodeDecodeError):
        return None, 'input-unreadable shop'


def python_findings():
    expected_roles = {role for _, role, _, _ in ROWS if role is not None}
    try:
        roles = set(validate._fixed_ui(None, None, False))
        ui = validate._fixed_ui('MAKERX', 2, True)
        findings = ['ui-roles-changed'] if roles != expected_roles else []
        for row, role, expected, _ in ROWS:
            if role is not None:
                actual = ui.get(role)
            elif row == 'origin-unknown':
                actual = getattr(validate, 'ORIGIN_UNKNOWN', None)
            else:
                continue
            if actual != expected:
                findings.append(f'ui-literal-changed {row}')
        return findings
    except Exception:
        # Do not expose exception details from S7 or imply a completed comparison.
        return ['check-error']


def finish(findings):
    for reason in findings:
        print(f'FAIL {reason}')
    print(f'{"FAIL" if findings else "PASS"} {NAME}')
    return int(bool(findings))


def main(argv=None):
    argparse.ArgumentParser(description=__doc__, add_help=False).parse_args(argv)
    shop, error = read_shop()
    if error is not None:
        return finish([error])
    assert shop is not None

    print(f'rows {len(ROWS)}')
    print(f'snippets {sum(len(snippets) for _, _, _, snippets in ROWS)}')
    findings = python_findings()
    findings.extend(f'js-text-missing {row}' for row, _, _, snippets in ROWS
                    if any(snippet not in shop for snippet in snippets))
    return finish(findings)


if __name__ == '__main__':
    sys.exit(main())
