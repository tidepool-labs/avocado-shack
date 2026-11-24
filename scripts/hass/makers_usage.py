#!/usr/bin/env python3
"""Report maker usage in an offline copy of the catalog."""

import argparse
from collections import Counter
from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from hass import claims, content_model


class ReportParser(argparse.ArgumentParser):
    def error(self, message):
        # The default diagnostic can echo unrecognized arguments, including paths.
        super().error("invalid arguments")


def report(content):
    makers = {key: row for key, row in content.makers.items() if isinstance(row, dict)}
    hidden = {key for key, row in makers.items() if row.get("hidden") is True}
    names = Counter(row["name"].strip().casefold() for row in makers.values()
                    if isinstance(row.get("name"), str))
    placeholder = claims.PLACEHOLDER.strip().casefold()
    used, held, no_url = set(), set(), set()
    unlinked = []
    active = linked = unknown = active_on_hidden = 0
    malformed = len(content.makers) - len(makers)

    for row in content.products:
        if not isinstance(row, dict):
            malformed += 1
            continue
        status = row.get("status")
        key = row.get("producerKey")
        if status == "held":
            if isinstance(key, str) and key in makers:
                held.add(key)
            continue
        if status not in ("active", "hidden"):
            continue
        is_active = status == "active"
        active += is_active
        if key is None:
            brand, product_id = row.get("brand"), row.get("id")
            if is_active and isinstance(brand, str) and isinstance(product_id, str):
                brand = brand.strip().casefold()
                if brand != placeholder and names[brand] == 1:
                    unlinked.append(product_id)
            continue
        linked += is_active
        if not isinstance(key, str) or key not in content.makers:
            unknown += 1
        elif key in makers:
            used.add(key)
            if is_active:
                active_on_hidden += key in hidden
                if "url" not in makers[key]:
                    no_url.add(key)

    unused = makers.keys() - used
    print(f"makers {len(makers)}")
    print(f"hidden-makers {len(hidden)}")
    print(f"active-products {active}")
    print(f"linked {linked}")
    print(f"note unused-maker {len(unused)}")
    for key in sorted(unused - hidden):
        print(f"unused {key}")
    print(f"note held-only-maker {len(held - used)}")
    print(f"note no-url {len(no_url)}")
    print(f"note unlinked-brand {len(unlinked)}")
    for product_id in sorted(unlinked):
        print(f"unlinked {product_id}")
    print(f"note malformed {malformed}")
    if unknown:
        print(f"FAIL unknown-maker {unknown}")
    if active_on_hidden:
        print(f"FAIL active-on-hidden-maker {active_on_hidden}")
    return finish(failed=bool(unknown or active_on_hidden))


def finish(*, failed):
    print("FAIL makers_usage" if failed else "PASS makers_usage")
    return int(failed)


def main(argv=None):
    parser = ReportParser(description=__doc__, allow_abbrev=False)
    parser.add_argument("--content", required=True, type=Path, metavar="DIR",
                        help="copy of the catalog content directory")
    directory = parser.parse_args(argv).content
    if directory.is_symlink() or not directory.is_dir():
        print("FAIL unsafe-input")
        return finish(failed=True)

    try:
        content = content_model.load_content(directory)
    except (content_model.ContentError, UnicodeDecodeError, OSError):
        print("FAIL content-invalid")
        return finish(failed=True)
    if not isinstance(content.products, list) or not isinstance(content.makers, dict):
        print("FAIL content-invalid")
        return finish(failed=True)
    return report(content)


if __name__ == "__main__":
    sys.exit(main())
