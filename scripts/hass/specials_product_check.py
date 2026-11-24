#!/usr/bin/env python3
"""Report saved weekly specials whose linked product will not appear on the card."""

import argparse
from datetime import date
from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
from hass import content_model


class PrivateArgumentParser(argparse.ArgumentParser):
    def error(self, message):
        # Argparse's diagnostics can echo raw values for rejected arguments.
        super().error("invalid arguments; see --help")


def fail(reason):
    print(f"FAIL {reason}")
    print("FAIL specials_product_check")
    return 1


def report(content, today):
    saved = content.store.get("specials", [])
    # The loader checks the file envelopes, not the shape of their payloads.
    specials = saved if isinstance(saved, list) else [saved]
    products = content.products if isinstance(content.products, list) else [content.products]
    by_id = {
        row["id"]: row.get("status") for row in products
        if isinstance(row, dict) and isinstance(row.get("id"), str)
    }
    malformed = sum(not isinstance(row, dict) for row in specials + products)
    findings = []
    if not specials:
        print("specials none")
    else:
        # Only dates determine membership. Unvalidated display fields must not
        # participate in active_specials' presentation sort.
        dates = []
        upcoming = ended = unreadable = 0
        for special in specials:
            if not isinstance(special, dict):
                continue
            dates.append({"start": special.get("start"), "end": special.get("end")})
            start = content_model.iso_day(special.get("start"))
            end = content_model.iso_day(special.get("end"))
            if start is None or end is None:
                unreadable += 1
                continue
            if start > today:
                upcoming += 1
            elif end < today:
                ended += 1
                continue
            if "product" in special:
                pid = special["product"]
                status = by_id.get(pid) if isinstance(pid, str) else None
                if status != "active":
                    sid = special.get("id")
                    if not isinstance(sid, str) or not content_model.ID_RE.fullmatch(sid):
                        sid = "unknown"
                    findings.append((sid, status if status in ("hidden", "held") else "unknown"))
        print(f"stored {len(specials)} of {content_model.MAX_SPECIALS_STORED}")
        print(f"active {len(content_model.active_specials({'specials': dates}, today))}")
        print(f"upcoming {upcoming}")
        print(f"ended {ended}")
        print(f"note unreadable-days {unreadable}")
    if malformed:
        print(f"note malformed {malformed}")
    for sid, status in sorted(findings):
        print(f"special {sid} product {status}")
    if findings:
        return fail(f"special-product-not-active {len(findings)}")
    print("PASS specials_product_check")
    return 0


def main(argv=None):
    parser = PrivateArgumentParser(prog="specials_product_check.py", description=__doc__)
    parser.add_argument("--content", required=True, type=Path, metavar="DIR", help="copied content directory")
    parser.add_argument("--today", type=date.fromisoformat, metavar="YYYY-MM-DD", help="default: shop's Pacific date")
    args = parser.parse_args(argv)
    try:
        if args.content.is_symlink() or not args.content.is_dir():
            return fail("unsafe-input")
    except (OSError, ValueError):
        return fail("unsafe-input")
    try:
        content = content_model.load_content(args.content)
    except (content_model.ContentError, UnicodeDecodeError, OSError):
        return fail("content-invalid")
    return report(content, args.today or content_model.shop_today())


if __name__ == "__main__":
    raise SystemExit(main())
