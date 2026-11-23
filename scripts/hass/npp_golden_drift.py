#!/usr/bin/env python3
"""Compare NPP golden cards with an offline copy of the product catalog."""

import argparse
import json
from pathlib import Path
import sys


ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))
DEFAULT_GOLDEN = ROOT / "hass/npp/assets/hass-gallery-style/golden"


class Parser(argparse.ArgumentParser):
    def error(self, message):
        # argparse can include the rejected argument (e.g. an input path).
        super().error("invalid arguments; see --help")


def reject_constant(_token):
    raise ValueError("not a JSON constant")


def read_json(path):
    if not path.is_file():
        raise ValueError("not a file")
    return json.loads(path.read_text(encoding="utf-8"), parse_constant=reject_constant)


def read_products(path):
    if path.is_symlink():
        raise ValueError("products is a symlink")
    data = read_json(path)
    if not isinstance(data, dict) or not isinstance(data.get("products"), list):
        raise ValueError("expected a products list")
    return {
        row["id"]: row for row in data["products"]
        if isinstance(row, dict) and isinstance(row.get("id"), str)
    }


def read_golden(path):
    data = read_json(path)
    card = data["card"]
    product_id = data["product_id"]
    fields = {
        "name": card["name"],
        "displayBrand": card["brand"],
        "description": card["description"],
        "category": data["category"],
    }
    if not isinstance(product_id, str) or not all(isinstance(v, str) for v in fields.values()):
        raise ValueError("expected string fields")
    return product_id, fields


def label(text):
    # A malformed identifier or filename must not inject another output line.
    return "".join(char if char.isprintable() else ascii(char)[1:-1] for char in text)


def main(argv=None):
    parser = Parser(prog="npp_golden_drift.py", description=__doc__)
    parser.add_argument("--content", required=True, type=Path, metavar="DIR")
    parser.add_argument("--golden", type=Path, metavar="DIR", default=DEFAULT_GOLDEN)
    args = parser.parse_args(argv)

    failures = []
    try:
        products = read_products(args.content / "products.json")
    except (OSError, ValueError, RecursionError):
        products = None
        failures.append("unreadable products")

    goldens = sorted(args.golden.glob("*.json"))
    matched = 0
    for path in goldens:
        try:
            product_id, fields = read_golden(path)
        except (OSError, ValueError, RecursionError, KeyError, TypeError):
            failures.append(f"golden-unreadable {label(path.name)}")
            continue
        if products is None:
            continue
        product = products.get(product_id)
        if product is None or product.get("status") != "active":
            failures.append(f"golden-missing {label(product_id)}")
            continue
        differing = [field for field, value in fields.items() if product.get(field) != value]
        if differing:
            failures.extend(f"golden-drift {label(product_id)} {field}" for field in differing)
        else:
            matched += 1

    print(f"goldens {len(goldens)}")
    print(f"matched {matched}")
    for reason in failures:
        print(f"FAIL {reason}")
    print(f"{'FAIL' if failures else 'PASS'} npp_golden_drift")
    return int(bool(failures))


if __name__ == "__main__":
    sys.exit(main())
