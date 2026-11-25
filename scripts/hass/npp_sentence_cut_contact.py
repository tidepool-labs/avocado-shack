#!/usr/bin/env python3
"""Check the live gate cuts text into sentences without splitting a contact token or a decimal number.

Offline and read-only: calls only the pure repo function hass.live_policy._pieces on fixed fixture text.
"""

import argparse
from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from hass import claims, live_policy  # noqa: E402,F401  (claims: the in-process patch target of the tests)

NAME = "npp_sentence_cut_contact"

CASES = [
    ('Fresh honey. Spoon it on toast.', ''),
    ('Email ana@cedarrow.example for more.', 'ana@cedarrow.example'),
    ('Costs $4.50 a jar.', '$4.50'),
    ('See www.cedarrow.example. Thanks.', 'www.cedarrow.example'),
    ('Write to ana at cedarrow.com. Thanks.', 'ana at cedarrow.com'),
    ('Call 000.555.0100 now.', '000.555.0100'),
    ('Size 2.5 lb; keep cool.', '2.5'),
    (['one', {'a': 1}], ''),
    (12, ''),
    ('Hid\u200bden honey. Next one', 'Hidden'),
    ('Email \u0430na@cedarrow.example now.', '\u0430na@cedarrow.example'),
    ('Visit cedarrow dot com. Thanks!', 'cedarrow dot com'),
]

# Cases whose token must survive whole inside one shown piece.
MUST_WHOLE = (1, 2, 3, 4, 5, 6, 9, 10, 11)

# The measured live answers, one line per case (informational lines; any difference is `pieces-changed`).
EXPECTED = [
    "case 0 pieces=['Fresh honey', ' Spoon it on toast']",
    "case 1 pieces=['Email ana@cedarrow.example for more']",
    "case 2 pieces=['Costs $4.50 a jar']",
    "case 3 pieces=['See www.cedarrow.example. Thanks']",
    "case 4 pieces=['Write to ana at cedarrow.com', ' Thanks']",
    "case 5 pieces=['Call 000.555.0100 now']",
    "case 6 pieces=['Size 2.5 lb', ' keep cool']",
    "case 7 pieces=['one', '{\"a\": 1}']",
    "case 8 pieces=['12']",
    "case 9 pieces=['Hidden honey', ' Next one']",
    "case 10 pieces=['Email \\u0430na@cedarrow.example now']",
    "case 11 pieces=['Visit cedarrow dot com', ' Thanks']",
]


def check_case(index, value, token):
    """Return (case line, findings) for one case; raises if a repo call fails."""
    got = live_policy._pieces(value)
    shown_pieces = [shown for shown, _s in got]
    line = f"case {index} pieces={ascii(shown_pieces)}"
    findings = []
    if index in MUST_WHOLE and token and not any(token in shown for shown in shown_pieces):
        findings.append(f"FAIL contact-or-number-split {index}")
    if line != EXPECTED[index]:
        findings.append(f"FAIL pieces-changed {index}")
    return line, findings


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.parse_args(argv)
    failed = False
    for index, (value, token) in enumerate(CASES):
        try:
            line, findings = check_case(index, value, token)
        except Exception:
            print("FAIL check-error")
            failed = True
            break
        print(line)
        for finding in findings:
            print(finding)
            failed = True
    print(f"FAIL {NAME}" if failed else f"PASS {NAME}")
    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(main())
