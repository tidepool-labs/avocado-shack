#!/usr/bin/env python3
"""Check a maker story sentence is kept only when it is Mike's own or his pronoun sentence with the maker's name.

Offline and read-only: calls only the pure `hass.newitem._story_ok` on fixed,
made-up cases. Run as `python3 -B scripts/hass/npp_story_own_sentence.py`.
"""

import argparse
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

NAME = "npp_story_own_sentence"

# (story, maker, message): every maker and sentence is a made-up fixture.
CASES = [
    ('Cedar Row Apiary keeps bees on the hill.', 'Cedar Row Apiary', 'They keep bees on the hill.'),
    ('Cedar Row Apiary keeps bees on the hill.', 'Cedar Row Apiary', 'They keep bees on the hill, but not here.'),
    ('Ana Ruiz keeps bees near Fillmore.', 'Cedar Row Apiary', 'Ana Ruiz keeps bees near Fillmore.'),
    ('They keep bees on the hill.', 'Cedar Row Apiary', 'They keep bees on the hill.'),
    ('Cedar Row Apiary is organic.', 'Cedar Row Apiary', 'Cedar Row Apiary is not organic.'),
    ('Cedar Row Apiary keeps bees on the hill. It sells honey.', 'Cedar Row Apiary', 'They keep bees on the hill.'),
    ('Cedar Row Apiary keeps bees on the hill.', None, 'They keep bees on the hill.'),
    ('', 'Cedar Row Apiary', 'They keep bees.'),
    ('Cedar Row Apiary has two hives.', 'Cedar Row Apiary', 'They have two hives.'),
    ('Cedar Row Apiary keeps bees on the hill.', 'Cedar Row Apiary', 'He keeps bees on the hill.'),
    ('Cedar Row Apiary keeps bees that heal on the hill.', 'Cedar Row Apiary', 'They keep bees that heal on the hill.'),
    ('Cedar Row Apiary carries jars to town.', 'Cedar Row Apiary', 'They carry jars to town.'),
]

# Cases whose story must never be kept: a joiner, a pronoun subject, an
# unaffirmed claim, a sentence he did not say, no maker, or an empty story.
MUST_REFUSE = (1, 3, 4, 5, 6, 7, 10)

# The case lines measured on the unpatched repo. Case 9 is dropped (the safe
# side) because _third_person gives "keepses" for "He keeps".
EXPECTED = (
    "case 0 kept=yes",
    "case 1 kept=no",
    "case 2 kept=yes",
    "case 3 kept=no",
    "case 4 kept=no",
    "case 5 kept=no",
    "case 6 kept=no",
    "case 7 kept=no",
    "case 8 kept=yes",
    "case 9 kept=no",
    "case 10 kept=no",
    "case 11 kept=yes",
)


def check():
    """Return the output lines (case lines and FAIL findings) in order."""
    lines = []
    try:
        from hass import newitem
        for i, (story, maker, message) in enumerate(CASES):
            ok = newitem._story_ok(story, maker, message)
            line = f"case {i} kept={'yes' if ok else 'no'}"
            lines.append(line)
            if ok and i in MUST_REFUSE:
                lines.append(f"FAIL unsaid-story-kept {i}")
            if line != EXPECTED[i]:
                lines.append(f"FAIL story-changed {i}")
    except Exception:
        lines.append("FAIL check-error")
    return lines


def main(argv=None):
    argparse.ArgumentParser(
        prog="npp_story_own_sentence.py",
        description="Check a maker story sentence is kept only when it is Mike's own "
                    "sentence or his pronoun sentence with the maker's name.",
    ).parse_args(argv)
    lines = check()
    failed = any(line.startswith("FAIL ") for line in lines)
    lines.append(f"{'FAIL' if failed else 'PASS'} {NAME}")
    print("\n".join(lines))
    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(main())
