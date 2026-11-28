#!/usr/bin/env python3
"""Report which synthetic copyright footers pass the offline S4 ownership check."""

import argparse
import json
from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from hass import npp
from hass.npp import research


NAME = 'npp_copyright_footer_shapes'
FIRST_SHOP = 13
FOOTERS = (
    '&copy; Miners Orchards. All rights reserved.',
    '&copy; 2024 Miners Orchards. All rights reserved.',
    'Copyright 2024 Miners Orchards.',
    '&copy; 2020-2024 Miners Orchards.',
    '&copy;2024 Miners Orchards.',
    '&copy; 2024 Miners Orchards | Privacy',
    'Copyright &copy; 2024 Miners Orchards. All rights reserved.',
    'Copyright &copy; 2024, Miners Orchards.',
    '&copy; 2024 Miners Orchards &middot; Powered by Shopify',
    '&copy; 2024 Miners Orchards All rights reserved',
    '&copy; 2024 Miners Orchards - All rights reserved',
    '&copy; 2024 Miners Orchards &ndash; All rights reserved',
    '&copy; Miners Orchards 2024.',
    '&copy; 2024 Miners Orchards Shop.',
    '&copy; 2024 Fresh Market Co. All rights reserved.',
)
HTML = (
    '<html><head><title>Miners Orchards</title></head><body><h1>Miners Orchards</h1>'
    '<p>Miners Orchards grows apples in Arroyo Grande.</p><footer>{footer}</footer></body></html>'
)


def main(argv=None):
    argparse.ArgumentParser(prog=NAME, description=__doc__, add_help=False).parse_args(argv)

    try:
        _, files, _ = npp.assets()
        markers = research._markers(json.loads(files['hass-maker-research/facts.schema.json']))
    except Exception:
        print('FAIL check-error')
        print(f'FAIL {NAME}')
        return 1

    failed = False
    for i, footer in enumerate(FOOTERS):
        try:
            page = research.parse_page('https://miners.example/', '2026-11-21', HTML.format(footer=footer))
            reason = research._own_site(page, 'Miners Orchards', 'Arroyo Grande', markers)
        except Exception:
            print('FAIL check-error')
            failed = True
            continue

        print(f'footer {i} reason={reason}')
        if i < FIRST_SHOP and reason != 'official':
            print(f'FAIL footer-refused {i}')
            failed = True
        elif i >= FIRST_SHOP and reason == 'official':
            print(f'FAIL shop-accepted {i}')
            failed = True

    print(f'{"FAIL" if failed else "PASS"} {NAME}')
    return int(failed)


if __name__ == '__main__':
    sys.exit(main())
