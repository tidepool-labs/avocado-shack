#!/usr/bin/env python3
"""Check S7's capture binding offline with synthetic evidence."""

import argparse
import hashlib
from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
from hass.npp import validate


PNG = b'\x89PNG\r\n\x1a\n' + b'fixture'
CASES = ('same', 'other-bytes', 'other-product', 'empty-product', 'text-png', 'upper-hash', 'not-dict')


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__, add_help=False)
    parser.parse_args(argv)

    digest = hashlib.sha256(PNG).hexdigest()
    product = 'p-fixture'
    evidence = {'pngSha256': digest, 'productId': product,
                'fragments': ['a'], 'priceIndex': 0, 'makerCount': 2}
    inputs = {
        'same': (evidence, PNG, product),
        'other-bytes': (evidence, PNG + b'0', product),
        'other-product': (evidence, PNG, 'p-other'),
        'empty-product': (evidence, PNG, ''),
        'text-png': (evidence, PNG.decode('latin-1'), product),
        'upper-hash': ({**evidence, 'pngSha256': digest.upper()}, PNG, product),
        'not-dict': (list(evidence.items()), PNG, product),
    }

    failed = False
    for case in CASES:
        used = False
        finding = None
        try:
            result = validate.captured_dom(*inputs[case])
        except Exception:
            finding = 'check-error'
        else:
            # A refusal supplies no fields; even a lone price index of zero is use.
            used = result is not None and result != (None, None, None)
            if case == 'same' and result != (['a'], 0, 2):
                finding = 'same-refused'
            elif case != 'same' and used:
                finding = f'capture-used {case}'

        print(f"capture {case} used={'yes' if used else 'no'}")
        if finding is not None:
            print(f'FAIL {finding}')
            failed = True

    print(f"{'FAIL' if failed else 'PASS'} npp_captured_dom_binding")
    return int(failed)


if __name__ == '__main__':
    sys.exit(main())
