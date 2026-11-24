#!/usr/bin/env python3
"""Check captured pilot replies and card HTML for listed private numbers."""

import argparse
from html.parser import HTMLParser
from pathlib import Path
import sys

ROOT = str(Path(__file__).resolve().parents[2])
if ROOT not in sys.path:
    sys.path.insert(0, ROOT)

from hass.npp.private_numbers import values


class CardText(HTMLParser):
    """Static approximation of card text; no CSS or JavaScript evaluation."""

    SKIP = {"script", "style"}
    ATTRIBUTES = {"alt", "title", "aria-label"}
    BREAKS = set("address article aside blockquote br caption dd div dl dt fieldset "
                 "figcaption figure footer form h1 h2 h3 h4 h5 h6 header hr li main "
                 "nav ol p pre section table tbody td th thead tr ul".split())

    def __init__(self):
        super().__init__(convert_charrefs=True)
        self.body = []
        self.labels = []
        self.skipping = None

    def handle_starttag(self, tag, attrs):
        if self.skipping:
            return
        if tag in self.SKIP:
            self.skipping = tag
            return
        if tag in self.BREAKS:
            self.body.append("\n")
        self.labels.extend(value for name, value in attrs if name in self.ATTRIBUTES and value)

    def handle_endtag(self, tag):
        if self.skipping:
            if tag == self.skipping:
                self.skipping = None
        elif tag in self.BREAKS:
            self.body.append("\n")

    def handle_data(self, data):
        if not self.skipping:
            self.body.append(data.replace("\n", " "))

    def fields(self):
        # Keep inline text connected, but don't form a number across blocks or labels.
        for field in [*"".join(self.body).split("\n"), *self.labels]:
            yield " ".join(field.split())


def load_private(path):
    private = set()
    for line in path.read_text(encoding="utf-8").splitlines():
        token = line.strip()
        if not token:
            continue
        readings = values(token)
        if (len(readings) != 1 or not readings[0].digits
                or (readings[0].start, readings[0].end) != (0, len(token))):
            raise ValueError("invalid private list")
        private.update(readings[0].amounts)
    if not private:
        raise ValueError("empty private list")
    return private


def hit_count(text, private):
    return sum(bool(reading.amounts & private) for reading in values(text))


class ScanArguments(argparse.ArgumentParser):
    def error(self, message):
        # argparse's default diagnostics can echo user-supplied arguments.
        self.exit(2, "error: invalid arguments (see --help)\n")


def main(argv=None):
    parser = ScanArguments(description=__doc__)
    parser.add_argument("--private", required=True, type=Path, help="UTF-8 file, one decimal number per line")
    parser.add_argument("--text", action="append", type=Path, default=[], help="captured reply text (repeatable)")
    parser.add_argument("--html", action="append", type=Path, default=[], help="captured card HTML (repeatable)")
    parser.add_argument("--receipt", action="store_true",
                        help="require nonempty reply and extracted card text; static scan only, not OCR or live verification")
    args = parser.parse_args(argv)
    try:
        private = load_private(args.private)
    except (OSError, ValueError):
        print("error: private list must be readable and contain decimal numbers", file=sys.stderr)
        return 2

    if not (args.text or args.html):
        print("error: provide at least one --text or --html capture", file=sys.stderr)
        return 2

    status = 0
    usable_kinds = set()
    for kind, paths in (("text", args.text), ("html", args.html)):
        for path in paths:
            try:
                source = path.read_text(encoding="utf-8")
            except (OSError, ValueError):
                print("error: could not read captured input as UTF-8", file=sys.stderr)
                status = 2
                continue
            if kind == "html":
                card = CardText()
                try:
                    card.feed(source)
                    card.close()
                except (AssertionError, ValueError):
                    print("error: could not parse captured HTML", file=sys.stderr)
                    status = 2
                    continue
                fields = list(card.fields())
            else:
                fields = [source]
            if args.receipt and any(field.strip() for field in fields):
                usable_kinds.add(kind)
            count = sum(hit_count(field, private) for field in fields)
            basename = path.name
            if not basename.isprintable() or hit_count(basename, private):
                basename = "[redacted filename]"
            print(f"{basename}: " + (f"private-number ({count})" if count else "clean"))
            if count:
                status = max(status, 1)
    if args.receipt and usable_kinds != {"text", "html"}:
        print("error: receipt requires nonempty reply text and extracted card text", file=sys.stderr)
        return 2
    return status


if __name__ == "__main__":
    sys.exit(main())
