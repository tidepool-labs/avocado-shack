#!/usr/bin/env python3
"""Check whether Hass reads the category keys and words on the site's shelf buttons."""

import argparse
from pathlib import Path
import re
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from hass import content_model
from hass.skills import kinds


PRINTABLE_WORD = re.compile(r"[A-Za-z]{1,40}")


def shelf_probes(key):
    yield "shelf-word-unread", key
    label = content_model.SHELF_LABELS[key]
    words = re.findall(r"[A-Za-z]+", label)
    yield "shelf-label-unread", label
    for word in words:
        if word.lower() != key:
            yield "shelf-word-unread", word


def check_probe(key, reason, probe):
    try:
        result = kinds.shelf(probe)
        if result.status == "one" and result.value == key:
            return None
    except Exception:
        return "check-error"

    # Never include the full label or resolver reply in a diagnostic.
    fields = (key,) if reason == "shelf-label-unread" else (key, probe)
    if not all(PRINTABLE_WORD.fullmatch(word) for word in fields):
        return "word-invalid"
    return " ".join((reason, *fields))


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__, add_help=False)
    parser.parse_args(argv)

    findings = []
    probes = read = 0
    for key in content_model.CATEGORIES:
        try:
            for reason, probe in shelf_probes(key):
                probes += 1
                finding = check_probe(key, reason, probe)
                if finding is None:
                    read += 1
                else:
                    findings.append(finding)
        except (KeyError, TypeError):
            # Missing or malformed label data prevents its probes from running.
            findings.append("check-error")

    print("categories", len(content_model.CATEGORIES))
    print("probes", probes)
    print("read", read)
    for finding in findings:
        print("FAIL", finding)
    print("FAIL shelf_words_check" if findings else "PASS shelf_words_check")
    return int(bool(findings))


if __name__ == "__main__":
    sys.exit(main())
