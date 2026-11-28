#!/usr/bin/env python3
"""Check maker-site host and address filters offline, without resolving names."""

import argparse
import ipaddress
from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
from hass import maker_site


CASES = [
    ("host", "cedarrow.com"),
    ("host", "shop.cedar-row.co.uk"),
    ("host", "printer.local"),
    ("host", "localhost"),
    ("host", "0x7f.1"),
    ("host", "127.1"),
    ("host", "cedarrow.com."),
    ("host", "xn--caf-dma.com"),
    ("host", "bad_name.com"),
    ("ip", "93.184.216.34"),
    ("ip", "10.0.0.5"),
    ("ip", "127.0.0.1"),
    ("ip", "2606:4700::1111"),
    ("ip", "::ffff:10.0.0.5"),
    ("ip", "64:ff9b::a00:5"),
    ("ip", "2002:a00:5::1"),
]
MUST_REFUSE = (2, 3, 4, 5, 6, 8, 10, 11, 13, 14, 15)
EXPECTED = (
    "case 0 host=yes",
    "case 1 host=yes",
    "case 2 host=no",
    "case 3 host=no",
    "case 4 host=no",
    "case 5 host=no",
    "case 6 host=no",
    "case 7 host=yes",
    "case 8 host=no",
    "case 9 ip=yes",
    "case 10 ip=no",
    "case 11 ip=no",
    "case 12 ip=yes",
    "case 13 ip=no",
    "case 14 ip=no",
    "case 15 ip=no",
)


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__, add_help=False)
    argv = sys.argv[1:] if argv is None else argv
    parser.parse_args(argv)
    if argv:  # Even an option terminator on its own is not a supported argument.
        parser.error("no arguments are accepted")

    failed = False
    for i, (kind, value) in enumerate(CASES):
        try:
            if kind == "host":
                ok = maker_site._plain_host(value)
            else:
                ok = maker_site._public_ip(ipaddress.ip_address(value))
        except Exception:
            print("FAIL check-error")
            failed = True
            break

        line = f"case {i} {kind}={'yes' if ok else 'no'}"
        print(line)
        if i in MUST_REFUSE and ok:
            print(f"FAIL private-host-allowed {i}")
            failed = True
        if line != EXPECTED[i]:
            print(f"FAIL host-changed {i}")
            failed = True

    print("FAIL npp_maker_host_guard" if failed else "PASS npp_maker_host_guard")
    return int(failed)


if __name__ == "__main__":
    sys.exit(main())
