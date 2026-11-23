#!/usr/bin/env python3
"""Report the size and voice-rule count of Hass's registry-generated help."""

import argparse
from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
from hass import capabilities, voice


def positive_int(value: str) -> int:
    number = int(value)
    if number < 1:
        raise argparse.ArgumentTypeError("must be a positive integer")
    return number


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description=__doc__, allow_abbrev=False)
    parser.add_argument("--max-lines", type=positive_int, default=80)
    parser.add_argument("--max-chars", type=positive_int, default=6000)
    args = parser.parse_args(argv)

    try:
        text = capabilities.help_section()
    except Exception:
        print("FAIL help-error")
        print("FAIL help_text_voice_check")
        return 1

    lines = len(text.splitlines())
    chars = len(text)
    broken = len(voice.check(text, long_ok=True))
    print(f"lines {lines}")
    print(f"chars {chars}")
    print(f"broken {broken}")

    findings = []
    if broken:
        findings.append(f"voice {broken}")
    if lines > args.max_lines:
        findings.append(f"too-long lines {lines}")
    if chars > args.max_chars:
        findings.append(f"too-long chars {chars}")
    for reason in findings:
        print(f"FAIL {reason}")
    print("FAIL help_text_voice_check" if findings else "PASS help_text_voice_check")
    return int(bool(findings))


if __name__ == "__main__":
    sys.exit(main())
