#!/usr/bin/env python3
"""Check saved maker stories offline and report counts only."""

import argparse
from pathlib import Path
import stat
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from hass import content_model, voice
from hass.skills import makers


class _Parser(argparse.ArgumentParser):
    def error(self, message):
        # Argparse may include raw arguments (including paths) in its error.
        super().error("invalid arguments")


def _fail(reason):
    print(f"FAIL {reason}")
    print("FAIL maker_story_check")
    return 1


def main(argv=None):
    parser = _Parser(prog="maker_story_check.py", description=__doc__, allow_abbrev=False)
    parser.add_argument("--content", type=Path, default=content_model.CONTENT_DIR,
                        metavar="DIR", help="content directory (default: hass/content)")
    directory = parser.parse_args(argv).content
    try:
        if not stat.S_ISDIR(directory.lstat().st_mode):
            return _fail("unsafe-input")
    except (OSError, ValueError):
        return _fail("unsafe-input")

    try:
        content = content_model.load_content(directory)
    except Exception:
        return _fail("content-invalid")

    voice_problems = reworded = over_limit = fallback_problems = 0
    try:
        # The loader checks the outer envelope, not the maker records.
        for _, maker in sorted(content.makers.items()):
            story, name, place = maker["story"], maker["name"], maker["place"]
            voice_problems += bool(voice.check(story))
            reworded += makers.story_words(story, name) != story
            over_limit += len(story) > content_model.MAX_STORY
            fallback_problems += bool(voice.check(makers.fallback_story(name, place)))
    except Exception:
        return _fail("check-error")

    print("makers", len(content.makers))
    print("voice-problems", voice_problems)
    print("reworded", reworded)
    print("over-limit", over_limit)
    print("fallback-problems", fallback_problems)

    failed = False
    for reason, count in (("story-voice", voice_problems), ("story-over-limit", over_limit),
                          ("fallback-voice", fallback_problems)):
        if count:
            print(f"FAIL {reason} {count}")
            failed = True
    print("FAIL maker_story_check" if failed else "PASS maker_story_check")
    return int(failed)


if __name__ == "__main__":
    sys.exit(main())
