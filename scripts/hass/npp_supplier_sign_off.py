#!/usr/bin/env python3
"""Report whether the offline NPP edit reader keeps a supplier before a sign-off."""

import argparse
from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

import hass.npp
from hass.npp import edits


TEXTS = (
    "This is from miners.",
    "This is from miners. Thanks!",
    "This is from miners. Thank you.",
    "This is from miners! :)",
    "Thanks! This is from miners.",
    "This is from miners, thanks",
)


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__, add_help=False)
    parser.parse_args(argv)

    try:
        grammar = edits.Grammar(hass.npp.assets()[1])
    except Exception:
        print("FAIL check-error")
        print("FAIL npp_supplier_sign_off")
        return 1

    failed = False
    for index, text in enumerate(TEXTS):
        try:
            edit = edits.read(grammar, text, {})
        except Exception:
            print("FAIL check-error")
            failed = True
            continue

        patch = dict(edit.patch)
        if "supplier" in patch:
            print(f"case {index} supplier={patch['supplier']}")
        elif edit.ask is not None:
            print(f"case {index} {edit.ask}")
        if patch.get("supplier") != "Miners":
            print(f"FAIL supplier-missed {index}")
            failed = True

    print("FAIL npp_supplier_sign_off" if failed else "PASS npp_supplier_sign_off")
    return int(failed)


if __name__ == "__main__":
    raise SystemExit(main())
