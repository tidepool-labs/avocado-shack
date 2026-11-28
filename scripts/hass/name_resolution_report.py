#!/usr/bin/env python3
"""Report aggregate full-name resolution findings from local Hass content."""

import argparse
from collections import Counter
from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
from hass import content_model
from hass.ops import catalog
from hass.skills import kinds


class PrivateArgumentParser(argparse.ArgumentParser):
    def error(self, message):
        # argparse's default diagnostic can echo an unrecognized path or name.
        super().error("invalid arguments")


def raw_at_cap(content, query):
    raw = catalog.lookup(content, "product", query)
    candidates = raw.get("candidates")
    if ("match" in raw or not isinstance(candidates, list)
            or not 1 <= len(candidates) <= catalog.MAX_CANDIDATES
            or any(not isinstance(item, dict)
                   or not all(isinstance(item.get(field), str) for field in ("id", "name", "brand"))
                   or item.get("status") not in content_model.PRODUCT_STATUSES
                   for item in candidates)):
        raise ValueError("invalid raw candidates")
    # At the raw cap we cannot tell exactly-full from truncated.
    return len(candidates) == catalog.MAX_CANDIDATES


def count_resolutions(content):
    products = Counter()
    for product in sorted(content.active_products(), key=lambda p: p["id"]):
        result = kinds.product_ref(content, product["name"])
        if result.status == "several":
            products["several-at-cap"] += raw_at_cap(content, product["name"])
            products["not-offered"] += product["id"] not in result.ids
            products["several"] += 1
        else:
            products["one" if result.status == "one" else "other"] += 1
    makers = Counter()
    for key in sorted(content.makers):
        result = kinds.maker_ref(content, content.makers[key]["name"])
        makers["one" if result.status == "one" else "other"] += 1
    return products, makers


def finish(*reasons):
    for reason in reasons:
        print(f"FAIL {reason}")
    print(f"{'FAIL' if reasons else 'PASS'} name_resolution_report")
    return 1 if reasons else 0


def main(argv=None):
    parser = PrivateArgumentParser(prog="name_resolution_report.py", description=__doc__)
    parser.add_argument("--content", type=Path, default=content_model.CONTENT_DIR, metavar="DIR")
    path = parser.parse_args(argv).content
    try:
        if path.is_symlink() or not path.is_dir():
            return finish("unsafe-input")
    except OSError:
        return finish("unsafe-input")
    try:
        content = content_model.load_content(path)
    except Exception:
        return finish("content-invalid")
    try:
        products, makers = count_resolutions(content)
    except Exception:
        return finish("check-error")

    print(f"products {products['one'] + products['several'] + products['other']}")
    for label in ("one", "several", "several-at-cap", "not-offered", "other"):
        print(f"product {label} {products[label]}")
    print(f"makers {makers['one'] + makers['other']}")
    for label in ("one", "other"):
        print(f"maker {label} {makers[label]}")

    findings = (
        ("ambiguous-products", products["several"]),
        ("unresolved-products", products["not-offered"] + products["other"]),
        ("unresolved-makers", makers["other"]),
    )
    return finish(*(f"{reason} {count}" for reason, count in findings if count))


if __name__ == "__main__":
    sys.exit(main())
