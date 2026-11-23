#!/usr/bin/env python3
"""Check route ideas in a content copy for calendar-day wording."""

import argparse
from pathlib import Path
import re
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from hass import content_model


TEXT_FIELDS = tuple(
    field for field in content_model.ROUTE_IDEA_FIELDS
    if field not in {"id", "sourceUrl", "status", "rsvpEnabled"}
)
MONTH = (r"(?:Jan(?:uary)?|Feb(?:ruary)?|Mar(?:ch)?|Apr(?:il)?|May|Jun(?:e)?|"
         r"Jul(?:y)?|Aug(?:ust)?|Sep(?:tember)?|Oct(?:ober)?|Nov(?:ember)?|Dec(?:ember)?)")
DAY = r"(?:[1-9]|[12][0-9]|3[01])"
DATE = re.compile(
    rf"\b\d{{4}}-\d{{2}}-\d{{2}}\b|\b{MONTH}\b\.?\s+{DAY}(?:st|nd|rd|th)?\b|"
    rf"\b{DAY}\s+{MONTH}\b\.?", re.IGNORECASE,
)
WEEKDAY = re.compile(r"\b(?:Monday|Tuesday|Wednesday|Thursday|Friday|Saturday|Sunday)\b", re.IGNORECASE)


class QuietParser(argparse.ArgumentParser):
    def error(self, message):
        # Argparse can interpolate unrecognized arguments, including copy paths.
        super().error("invalid arguments; use --content DIR")


def fail(reason):
    print(f"FAIL {reason}")
    print("FAIL route_idea_dates")
    return 1


def main(argv=None):
    parser = QuietParser(prog="route_idea_dates.py", description=__doc__, allow_abbrev=False)
    parser.add_argument("--content", required=True, metavar="DIR", help="read-only copy of hass/content")
    args = parser.parse_args(argv)
    directory = Path(args.content)
    if not args.content or directory.is_symlink() or not directory.is_dir():
        return fail("unsafe-input")
    try:
        content = content_model.load_and_validate(directory, None)
    except (content_model.ContentError, UnicodeDecodeError, OSError):
        return fail("content-invalid")

    published = hidden = dated_published = dated_hidden = weekdays = invalid_ids = 0
    findings = []
    for idea in content.community["routeIdeas"]:
        idea_id = idea["id"]
        safe_id = isinstance(idea_id, str) and content_model.ID_RE.fullmatch(idea_id) is not None
        invalid_ids += not safe_id
        dated_fields = []
        for field in TEXT_FIELDS:
            value = idea[field]
            if DATE.search(value):
                dated_fields.append(field)
            weekdays += len(WEEKDAY.findall(value))
        if idea["status"] == "hidden":
            hidden += 1
            dated_hidden += bool(dated_fields)
        else:
            published += 1
            dated_published += bool(dated_fields)
            if safe_id:
                findings.extend((idea_id, field) for field in dated_fields)

    print(f"ideas {published}")
    print(f"hidden {hidden}")
    print(f"note dated-hidden {dated_hidden}")
    print(f"note weekday {weekdays}")
    print(f"note invalid-id {invalid_ids}")
    for idea_id, field in sorted(findings):
        print(f"dated {idea_id} {field}")
    if dated_published:
        return fail(f"dated-idea {dated_published}")
    print("PASS route_idea_dates")
    return 0


if __name__ == "__main__":
    sys.exit(main())
