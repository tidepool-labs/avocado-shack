#!/usr/bin/env python3
"""Compare NPP timestamp acceptance without recording or sending anything."""

import argparse
from pathlib import Path
import sys


sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
from hass.npp import evidence, receipt


VALUES = (
    "2026-11-21T09:30:00Z",
    "2026-11-21T09:30:00+00:00",
    "2026-11-21T01:30:00-08:00",
    "2026-11-21T14:30:00+05:00",
    "2026-11-21T09:30:00.123Z",
    "2026-11-21 09:30:00Z",
    "2026-11-21T09:30Z",
    "2026-11-21T01:30:00-0800",
    "2026-11-21T09:30:00",
    "20261121T093000Z",
    "2026-11-21T09:30:00.123456-08:00",
    "2026-11-21T09:30:00z",
)


def _approval_accepts(value):
    record = evidence.Evidence()
    try:
        record.approval(1, "G", value, "c1", "abcdef1")
    except ValueError:
        return False
    return True


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__, add_help=False)
    argv = sys.argv[1:] if argv is None else argv
    parser.parse_args(argv)
    if argv:  # argparse accepts a bare end-of-options marker by default.
        parser.error("this command takes no arguments")

    failed = False
    for position, value in enumerate(VALUES, 1):
        try:
            receipt_ok = receipt.instant(value) is not None
            evidence_ok = _approval_accepts(value)
        except Exception:
            # No result pair is available; do not invent one or echo the error.
            print("FAIL check-error")
            failed = True
            continue
        receipt_status = "ok" if receipt_ok else "refused"
        evidence_status = "ok" if evidence_ok else "refused"
        print(f"instant {position:02d} receipt={receipt_status} evidence={evidence_status}")
        if receipt_ok != evidence_ok:
            print(f"FAIL instant-disagree {position:02d}")
            failed = True

    print("FAIL npp_instant_parity" if failed else "PASS npp_instant_parity")
    return int(failed)


if __name__ == "__main__":
    raise SystemExit(main())
