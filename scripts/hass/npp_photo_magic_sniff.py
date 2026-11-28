#!/usr/bin/env python3
"""Check Hass photo signatures, end markers and voice-note routing offline."""

import argparse
from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
from hass import media  # noqa: E402

# Synthetic byte strings for signature checks, not decodable image fixtures.
CASES = [
    b'\xff\xd8\xff\xe0\x00\x00\x00\x00\x00\x00\x00\x00\xff\xd9',
    b'\xff\xd8\xff\xe0\x00\x00\x00\x00\x00\x00\x00\x00\xff\xd9\x00\x00\x00',
    b'\xff\xd8\xff\xe0\x00\x00\x00\x00\x00\x00\x00\x00',
    b'\x89PNG\r\n\x1a\n\x00\x00\x00\x00\x00\x00\x00\x00IEND\xaeB`\x82',
    b'\x89PNG\r\n\x1a\n\x00\x00\x00\x00\x00\x00\x00\x00IEND',
    b'\x89PNG\r\n\x1a\n',
    b'GIF89a\x00\x00\x00\x00\x00\x00\x00\x00',
    b'ID3\x00\x00\x00\x00\x00\x00\x00\x00',
    b'RIFF\x00\x00\x00\x00WAVEfmt ',
    b'\x00\x00\x00\x18ftypM4A \x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00',
    b'',
]
MUST_NONE = (2, 4, 5, 6, 7, 8, 9, 10)
EXPECTED = (
    "case 0 sniff='jpeg' audio=no",
    "case 1 sniff='jpeg' audio=no",
    "case 2 sniff=None audio=no",
    "case 3 sniff='png' audio=no",
    "case 4 sniff=None audio=no",
    "case 5 sniff=None audio=no",
    "case 6 sniff=None audio=no",
    "case 7 sniff=None audio=yes",
    "case 8 sniff=None audio=yes",
    "case 9 sniff=None audio=yes",
    "case 10 sniff=None audio=no",
)


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__, add_help=False)
    parser.parse_args(argv)

    failed = False
    for i, data in enumerate(CASES):
        try:
            kind = media.sniff(data)
            audio = media.is_audio(data)
        except Exception:
            print("FAIL check-error")
            failed = True
            break

        line = f"case {i} sniff={kind!r} audio={'yes' if audio else 'no'}"
        print(line)
        if i in MUST_NONE and kind is not None:
            print(f"FAIL bad-bytes-accepted {i}")
            failed = True
        if line != EXPECTED[i]:
            print(f"FAIL sniff-changed {i}")
            failed = True

    print(f"{'FAIL' if failed else 'PASS'} npp_photo_magic_sniff")
    return int(failed)


if __name__ == "__main__":
    sys.exit(main())
