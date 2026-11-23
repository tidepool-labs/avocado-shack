#!/usr/bin/env python3
"""Render a sample-only Markdown review page of the Hass NPP reply asset."""

import argparse
import html
import json
import os
from pathlib import Path
import re
import stat
import sys


ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))
DEFAULT_TEMPLATES = ROOT / "hass/npp/assets/hass-npp-reply/reply-templates.json"
SECTIONS = ("questions", "prompts", "brackets", "guards", "confirm", "edits")
SAMPLES = {
    "brand": "Example Brand",
    "claim": "example claim",
    "code": "4ed1",
    "maker": "Example Maker",
    "n": "2",
    "name": "Example Source",
    "url": "https://theavocadoman.com/?item=example#market",
}
PLACEHOLDER = re.compile(r"\{\{|\}\}|\{([A-Za-z_][A-Za-z0-9_]*)\}")


class CatalogParser(argparse.ArgumentParser):
    def error(self, message):
        # Argparse's default error can repeat caller-supplied paths and values.
        super().error("invalid arguments; see --help")


def reject_constant(_token):
    raise ValueError("not a JSON constant")


def read_templates(path):
    # Reject symlink inputs at open; don't wait on non-regular inputs such as FIFOs.
    fd = os.open(path, os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK)
    try:
        if not stat.S_ISREG(os.fstat(fd).st_mode):
            raise ValueError("not a regular file")
        with os.fdopen(fd, encoding="utf-8", closefd=False) as source:
            data = json.load(source, parse_constant=reject_constant)
    finally:
        os.close(fd)
    if not isinstance(data, dict) or any(
        not isinstance(data.get(section), dict) for section in (*SECTIONS, "existing")
    ):
        raise ValueError("missing template sections")
    phrases = data.get("never_say")
    if not isinstance(phrases, list) or any(not isinstance(p, str) for p in phrases):
        raise ValueError("missing never_say list")
    return data


def strings(obj, prefix=""):
    for key in sorted(obj):
        value = obj[key]
        path = f"{prefix}.{key}" if prefix else key
        if isinstance(value, str):
            yield path, value
        elif isinstance(value, dict):
            yield from strings(value, path)
        # Arrays (e.g. brackets.compose.drop_order) are metadata, not templates.


def cell(text):
    """Keep literal punctuation and physical line breaks inside one table cell."""
    text = re.sub(r"([\\`*_\[\]|~])", r"\\\1", html.escape(text, quote=False))
    text = re.sub(r"^ +| +$", lambda match: "&#32;" * len(match[0]), text)
    return text.replace("\r\n", "<br>").replace("\r", "<br>").replace("\n", "<br>")


def build_page(data):
    rows = ["# Hass new-product replies (sample values)", "",
            "| Section | Key | Rendered line | Characters |", "| --- | --- | --- | ---: |"]
    findings = []
    phrases = [phrase.casefold() for phrase in data["never_say"]]
    templates = rendered = 0
    for section in SECTIONS:
        for key, template in strings(data[section]):
            templates += 1
            unknown = dict.fromkeys(match[1] for match in PLACEHOLDER.finditer(template)
                                    if match[1] is not None and match[1] not in SAMPLES)
            if unknown:
                findings.extend(f"unknown-placeholder {section}.{key} {name}" for name in unknown)
                continue
            line = PLACEHOLDER.sub(lambda match: SAMPLES[match[1]] if match[1] else match[0][0], template)
            rendered += 1
            folded = line.casefold()
            if any(phrase in folded for phrase in phrases):
                findings.append(f"never-say {section}.{key}")
            rows.append(f"| {section} | {cell(key)} | {cell(line)} | {len(line)} |")
    for key in sorted(data["existing"]):
        rows.append(f"| existing | {cell(key)} | existing | — |")
    return "\n".join(rows) + "\n", templates, rendered, findings


def fail(*reasons):
    for reason in reasons:
        print(f"FAIL {reason}")
    print("FAIL npp_reply_catalog")
    return 1


def main(argv=None):
    parser = CatalogParser(prog="npp_reply_catalog.py", description=__doc__, allow_abbrev=False)
    parser.add_argument("--out", required=True, type=Path, help="new Markdown file in an existing directory")
    parser.add_argument("--templates", type=Path, default=DEFAULT_TEMPLATES, help="reply template JSON override")
    args = parser.parse_args(argv)

    findings = []
    try:
        if os.path.lexists(args.out):
            findings.append("out-exists")
        if not args.out.parent.is_dir():
            findings.append("out-parent")
    except (OSError, ValueError):
        parser.error("invalid output destination")
    try:
        data = read_templates(args.templates)
        page, templates, rendered, content_findings = build_page(data)
        payload = page.encode("utf-8")  # Validate before creating the output.
    except (OSError, ValueError, RecursionError):
        return fail(*findings, "templates-unreadable")
    findings.extend(content_findings)
    if findings:
        return fail(*findings)

    try:
        fd = os.open(args.out, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
        with os.fdopen(fd, "wb") as output:
            output.write(payload)
    except FileExistsError:
        return fail("out-exists")
    except (FileNotFoundError, NotADirectoryError):
        return fail("out-parent")
    except (OSError, ValueError):
        parser.error("invalid output destination")

    print(f"templates {templates}")
    print(f"rendered {rendered}")
    print("written yes")
    print("PASS npp_reply_catalog")
    return 0


if __name__ == "__main__":
    sys.exit(main())
