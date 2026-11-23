#!/usr/bin/env python3
"""Compare catalog copy lengths with the committed gallery measurements offline."""

import argparse
import importlib.util
import json
import os
from pathlib import Path
import stat
import sys


ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))

FIELDS = {"name": "name", "description": "description", "image_alt": "imageAlt"}


class PrivateArgumentParser(argparse.ArgumentParser):
    def error(self, message):
        # argparse's diagnostic can echo unrecognized arguments, including paths.
        super().error("invalid arguments; provide --content DIR")


def load_limits_module():
    spec = importlib.util.spec_from_file_location(
        "npp_limits", ROOT / "scripts/hass/npp_limits.py"
    )
    if spec is None or spec.loader is None:
        raise ImportError("could not load npp_limits")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def open_regular(path, flags):
    fd = os.open(path, flags | os.O_NOFOLLOW | os.O_NONBLOCK)
    try:
        if stat.S_ISREG(os.fstat(fd).st_mode):
            return fd
        raise ValueError("expected a regular file")
    except (OSError, ValueError):
        os.close(fd)
        raise


def reject_constant(_token):
    raise ValueError("expected a JSON value")


def read_records(directory, key, container_type):
    try:
        with open(directory / f"{key}.json", encoding="utf-8", opener=open_regular) as source:
            document = json.load(source, parse_constant=reject_constant)
        records = document[key]
        if isinstance(records, container_type):
            rows = records.values() if isinstance(records, dict) else records
            if all(isinstance(row, dict) for row in rows):
                return records
    except (OSError, ValueError, KeyError, TypeError, RecursionError):
        pass
    return None


def nonempty_text(rows, column):
    return [value for row in rows if isinstance(value := row.get(column), str) and value.strip()]


def main(argv=None):
    parser = PrivateArgumentParser(description=__doc__, allow_abbrev=False)
    parser.add_argument("--content", required=True, type=Path, help="directory of copied catalog files")
    args = parser.parse_args(argv)
    limits = load_limits_module()
    committed = json.loads(limits.LIMITS.read_text(encoding="utf-8"))["fields"]

    findings = []
    products = read_records(args.content, "products", list)
    makers = read_records(args.content, "makers", dict)
    if products is None:
        findings.append("unreadable products")
    if makers is None:
        findings.append("unreadable makers")

    active = [row for row in products or [] if row.get("status") == "active"]
    values = {key: nonempty_text(active, column) for key, column in FIELDS.items()}
    producer_keys = set(nonempty_text(active, "producerKey"))
    values["maker_story"] = nonempty_text(
        (row for key, row in (makers or {}).items() if key in producer_keys), "story"
    )

    print(f"records {len(active)}")
    for key, texts in values.items():
        measured = limits.stat(texts) if texts else None
        for unit in ("chars", "words"):
            catalog_p90 = measured[unit]["p90"] if measured else 0
            print(f"field {key} {unit}-p90 {committed[key][unit]['p90']} {catalog_p90}")
        if key in limits.SOFT_HARD:
            hard_max = limits.SOFT_HARD[key]["hard_max_chars"]
            over = sum(len(text) > hard_max for text in texts)
            if over:
                findings.append(f"over-hard-max {key} {over}")

    for reason in findings:
        print(f"FAIL {reason}")
    print(f"{'FAIL' if findings else 'PASS'} npp_limits_drift")
    return int(bool(findings))


if __name__ == "__main__":
    sys.exit(main())
