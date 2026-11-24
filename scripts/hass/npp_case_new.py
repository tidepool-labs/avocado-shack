#!/usr/bin/env python3
"""Start an offline NPP regression case; replace all TODOs before committing it."""

import argparse
from datetime import date
import json
from pathlib import Path
import re
import sys

# Direct script execution puts scripts/hass, not the checkout root, on sys.path.
sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
from hass.tests.test_npp_assets import load, validate
from scripts.hass import npp_findings

TERMINALS = {"listing": "published", "question": "asking", "contract": "card_out"}


def finding_defaults(ledger, finding_id):
    for row in npp_findings.read_ledger(npp_findings.ledger_path(ledger)):
        if row["id"] == finding_id:
            # A closed repeat retains its state marker but has a closure card.
            if row["card"]:
                raise ValueError("finding is closed")
            stage = int(row["stage"][1:])
            path = "contract" if 9 <= stage <= 13 else "question" if stage == 3 else "listing"
            return path, row["summary"]
    raise ValueError("finding not found")


def scaffold(cases, day, words, path, title, *, finding_id=None):
    if not re.fullmatch(r"[a-z0-9-]{3,40}", words):
        raise ValueError("slug must match [a-z0-9-]{3,40}")
    try:
        parsed_day = date.fromisoformat(day)
    except ValueError:
        raise ValueError("day must be a valid YYYY-MM-DD date") from None
    if parsed_day.isoformat() != day:
        raise ValueError("day must be a valid YYYY-MM-DD date")
    tag = f"npp-{day.replace('-', '')}-"
    tagged_slug = re.compile(rf"{tag}([0-9]+)(?:-|$)")

    schema = load(cases / "case.schema.json")
    highest_id = highest_serial = 0
    for entry in cases.glob("case-*.json"):
        existing = load(entry)
        if (not isinstance(existing, dict) or type(existing.get("id")) is not int
                or not isinstance(existing.get("slug"), str)):
            raise ValueError("existing case must have an integer id and a string slug")
        highest_id = max(highest_id, existing["id"])
        match = tagged_slug.match(existing["slug"])
        if match:
            highest_serial = max(highest_serial, int(match[1]))

    # FORMAT.md uses the slug in the file name; prefix it with the real-failure tag.
    case_id = highest_id + 1
    slug = f"{tag}{highest_serial + 1}-{words}"
    if finding_id is not None:
        # The case schema has no finding-reference field; its id is the case number.
        title = f"{title} [{finding_id}]"
    case = {
        "id": case_id,
        "slug": slug,
        "title": title,
        "contract": "TODO: describe the contract this regression protects",
        "bug": "TODO: describe the bug that makes the case fail",
        "path": path,
        "terminal": TERMINALS[path],
        "settings": {"npp": True, "houseRender": True, "photo_polish": True,
                     "itemIntake": True, "liveSite": False, "approvalTtlSeconds": 7200},
        "turns": [{"at_s": 0, "from": "mike", "text": "TODO: replace with a synthetic turn", "photos": []}],
        "inputs": {},
        # The schema accepts an object here, but CaseInputsTest requires state == terminal.
        "expect": {"state": "TODO"},
    }
    problems = validate(schema, case)
    if problems:
        raise ValueError("; ".join(problems))
    target = cases / f"case-{case_id:02d}-{slug}.json"
    if finding_id is not None:
        npp_findings.ledger_path(target)  # Keep copied ledger text outside Git, too.
    with target.open("x", encoding="utf-8") as handle:
        handle.write(json.dumps(case, indent=2) + "\n")
    return target.name


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--cases", required=True, type=Path, help="case directory (outside Git for findings)")
    parser.add_argument("--day", required=True, metavar="YYYY-MM-DD")
    parser.add_argument("--slug", required=True)
    parser.add_argument("--path", choices=TERMINALS)
    parser.add_argument("--title")
    parser.add_argument("--finding", metavar="ID", help="derive path and title from an open finding")
    parser.add_argument("--ledger", type=Path, metavar="FILE", help="private ledger to read with --finding")
    args = parser.parse_args(argv)
    if args.finding is not None or args.ledger is not None:
        if args.finding is None or args.ledger is None:
            parser.error("--finding and --ledger must be used together")
        if args.path is not None or args.title is not None:
            parser.error("--finding supplies --path and --title; do not pass them together")
    elif args.path is None or args.title is None:
        parser.error("--path and --title are required without --finding and --ledger")
    try:
        path, title = args.path, args.title
        if args.finding is not None:
            path, title = finding_defaults(args.ledger, args.finding)
        name = scaffold(args.cases, args.day, args.slug, path, title, finding_id=args.finding)
    except OSError as exc:
        print(f"FAIL {exc.strerror}")
        return 1
    except ValueError as exc:
        print(f"FAIL {exc}")
        return 1
    print(f"PASS npp_case_new {name}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
