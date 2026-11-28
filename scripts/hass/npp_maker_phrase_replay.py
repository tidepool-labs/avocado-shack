#!/usr/bin/env python3
"""Replay common maker phrases through NPP S3 and report counts offline."""

import argparse
from collections import Counter
import json
from pathlib import Path
import re
import stat
import sys
import unicodedata

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))
from hass.npp import missing

MAKERS = ROOT / "hass/content/makers.json"
MAKERS_CAP = 2_000_000
KINDS = ("key", "name", "lower", "the", "plural", "no-apostrophe", "ascii")
STATE = re.compile(r"[a-z]{1,20}")


def _reject_constant(_token):
    raise ValueError("non-JSON number")


def _load_makers():
    """Return the catalog and a fixed diagnostic if it cannot be loaded."""
    try:
        info = MAKERS.lstat()
        if not stat.S_ISREG(info.st_mode):
            return None, "input-unsafe makers"
        if info.st_size > MAKERS_CAP:
            return None, "input-too-large makers"
        with MAKERS.open("rb") as source:
            data = source.read(MAKERS_CAP + 1)
        if len(data) > MAKERS_CAP:
            return None, "input-too-large makers"
        document = json.loads(data.decode("utf-8"), parse_constant=_reject_constant)
    except (OSError, ValueError, RecursionError):
        return None, "input-unreadable makers"

    makers = document.get("makers") if isinstance(document, dict) else None
    if not isinstance(makers, dict) or not all(
        isinstance(row, dict)
        and all(isinstance(row.get(field), str) for field in ("name", "place"))
        and all(field not in row or isinstance(row[field], str) for field in ("story", "url"))
        for row in makers.values()
    ):
        return None, "input-unreadable makers"
    return makers, None


def _phrases(key, name):
    yield "key", key
    yield "name", name
    yield "lower", name.lower()
    yield "the", "the " + name
    yield "plural", name[:-1] if name.endswith("s") else name + "s"
    bare = name.replace("'", "").replace("’", "")
    if bare != name:
        yield "no-apostrophe", bare
    plain = "".join(c for c in unicodedata.normalize("NFKD", name) if not unicodedata.combining(c))
    if plain != name:
        yield "ascii", plain


def _replay(makers):
    tried = Counter()
    states = {kind: Counter() for kind in KINDS}
    findings = {}
    for key in sorted(makers):
        for kind, phrase in _phrases(key, makers[key]["name"]):
            tried[kind] += 1
            try:
                state = missing._maker(phrase, {"brand_on_label": None, "confidence": {"brand": 0.0}}, makers).state
            except Exception:
                findings["check-error"] = None
                continue
            if not isinstance(state, str) or not STATE.fullmatch(state):
                findings["state-invalid"] = None
                continue
            states[kind][state] += 1

    for kind in KINDS:
        print(f"tried {kind} {tried[kind]}")
        for state, count in sorted(states[kind].items()):
            print(f"state {kind} {state} {count}")
        for state, reason in (("new", "research"), ("ambiguous", "ambiguous")):
            if count := states[kind][state]:
                findings[f"maker-phrase-{reason} {kind} {count}"] = None
    return findings


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__, add_help=False)
    parser.parse_args(argv)
    makers, error = _load_makers()
    findings = (error,) if error else _replay(makers)
    for reason in findings:
        print(f"FAIL {reason}")
    print(f"{'FAIL' if findings else 'PASS'} npp_maker_phrase_replay")
    return int(bool(findings))


if __name__ == "__main__":
    sys.exit(main())
