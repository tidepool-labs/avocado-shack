"""Check Hass NPP delivery receipt rules using only in-memory fixtures."""

import argparse
from datetime import datetime, timedelta, timezone
from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from hass.npp import receipt

Q = datetime(2026, 11, 21, 10, 0, tzinfo=timezone.utc)
MINUTE = timedelta(minutes=1)
AT = Q + MINUTE
NOW = Q + 5 * MINUTE
SHA = "ab" * 64
GOOD = {
    "state": "confirmed",
    "png_sha256": SHA,
    "confirmed_at": AT.isoformat(),
    "provider_guid": "g-1",
}
RECORDS = (
    (GOOD, (AT, "g-1")),
    (dict(GOOD, state="queued"), None),
    (dict(GOOD, png_sha256="cd" * 64), None),
    (dict(GOOD, confirmed_at="2026-11-21T10:01:00"), None),
    (dict(GOOD, confirmed_at=(Q - MINUTE).isoformat()), None),
    (dict(GOOD, confirmed_at=(NOW + MINUTE).isoformat()), None),
    (dict(GOOD, provider_guid="g" * 513), (AT, None)),
    (dict(GOOD, provider_guid=5), (AT, None)),
    (None, None),
    ("x", None),
)
QUEUED_BAD = ("2026-11-21T10:00:00", "garbage", "")
INSTANTS = (
    (Q.isoformat(), True),
    (QUEUED_BAD[0], False),
    (QUEUED_BAD[1], False),
    (Q, True),
    (datetime(2026, 11, 21, 10, 0), False),
    (5, False),
)


def source_for(record):
    def source(_row_id):
        if isinstance(record, Exception):
            raise record
        return dict(record) if isinstance(record, dict) else record

    return source


def check(find):
    sources = (
        *((i, source_for(record), expected) for i, (record, expected) in enumerate(RECORDS)),
        ("oserror", source_for(OSError()), None),
        ("valueerror", source_for(ValueError()), None),
        ("no-source", None, None),
    )
    for label, source, expected in sources:
        try:
            ok = receipt.confirmation(source, 1, SHA, Q, NOW) == expected
        except Exception:
            ok, reason = False, "check-error"
        else:
            reason = f"record-rule {label}"
        if isinstance(label, int):
            print(f"record {label} ok={'yes' if ok else 'no'}")
        if not ok:
            find(reason)

    for i, (value, aware) in enumerate(INSTANTS):
        try:
            parsed = receipt.instant(value)
        except Exception:
            find("check-error")
        else:
            if (parsed is not None) != aware:
                find(f"instant-rule {i}")

    good_source = source_for(GOOD)
    for i, text in enumerate(QUEUED_BAD):
        try:
            queued = receipt.instant(text)
        except Exception:
            find("check-error")
            continue
        try:
            result = receipt.confirmation(good_source, 1, SHA, queued, NOW)
        except Exception:
            status = "raises"
        else:
            status = "none" if result is None else "non-none"
        print(f"queued-bad {i} result={status}")
        if status != "none":
            find(f"queued-unreadable-{status} {i}")


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__, add_help=False)
    parser.parse_args(argv)

    failed = False

    def find(reason):
        nonlocal failed
        failed = True
        print(f"FAIL {reason}")

    check(find)
    print(f"{'FAIL' if failed else 'PASS'} npp_delivery_receipt_rules")
    return int(failed)


if __name__ == "__main__":
    sys.exit(main())
