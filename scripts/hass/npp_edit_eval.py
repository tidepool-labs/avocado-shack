#!/usr/bin/env python3
"""Score S10 mapper recordings offline, or collect one on the attended private host.

A recording is a JSON array of {id, output, model} rows. Output is the
mapper's parsed answer (null if unavailable); model is the returned ID or
null if unavailable. Keep recordings outside Git. Replay prints no raw
answers or model metadata. Accuracy is exact answers / recorded rows.
"""
import argparse
from collections import Counter
import json
import os
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[2]
PHRASES = ROOT / "hass/tests/npp/edit_eval/phrases.json"
if __package__ in (None, ""):
    sys.path.insert(0, str(ROOT))

from hass.npp import assets, edits  # noqa: E402


LABELS = ("exact", "partial", "wrong", "invalid")


def _score(expected, output, schema):
    if edits.valid_mapping(output, schema) is None:
        return "invalid"
    if output["action"] == "ask":
        return "exact" if expected == "ask" else "wrong"
    if not output["patches"]:
        return "invalid"
    if expected == "ask":
        return "wrong"
    # The gold patches have distinct fields. Ordering doesn't matter, but
    # duplicate or extra entries cannot earn exact credit.
    def pairs(patches):
        return Counter((patch["field"], patch["value"]) for patch in patches)

    wanted, got = pairs(expected), pairs(output["patches"])
    return "exact" if wanted == got else "partial" if wanted & got else "wrong"


def _report(rows, expected, schema, minimum):
    counts, seen = Counter(), set()
    for index, row in enumerate(rows, 1):
        phrase_id, verdict = None, "invalid"
        if isinstance(row, dict) and isinstance(row.get("id"), str):
            if row["id"] in expected and row["id"] not in seen:
                phrase_id = row["id"]
                seen.add(phrase_id)
                if set(row) == {"id", "output", "model"} and (row["model"] is None or isinstance(row["model"], str)):
                    verdict = _score(expected[phrase_id], row["output"], schema)
        counts[verdict] += 1
        print(f"{phrase_id or f'row {index}'}: {verdict}")
    accuracy = counts["exact"] / len(rows)
    print(f"accuracy: {counts['exact']}/{len(rows)} ({accuracy:.2%}); "
          + " ".join(f"{label}={counts[label]}" for label in LABELS))
    failed = accuracy < minimum
    print(f"{'FAIL' if failed else 'PASS'} npp_edit_eval")
    return int(failed)


def _record(phrases, grammar, step, transport):
    model = None

    def observe(url, body, headers, timeout):
        nonlocal model
        status, raw = transport(url, body, headers, timeout)
        if status == 200:
            # Only response metadata counts; never infer the ID from the pin.
            try:
                returned = json.loads(raw).get("model")
            except (ValueError, AttributeError, TypeError):
                returned = None
            if isinstance(returned, str):
                model = returned
        return status, raw

    mapper = edits.codex_mapper(transport=observe, step=step)
    rows = []
    for phrase in phrases:
        model = None
        output = mapper(grammar.prompt, grammar.schema, phrase["phrase"], grammar.fields)
        rows.append({"id": phrase["id"], "output": output, "model": model})
    return rows


def main(argv=None, *, transport_factory=None):
    parser = argparse.ArgumentParser(description="Replay or record S10 edit mappings", allow_abbrev=False)
    mode = parser.add_mutually_exclusive_group(required=True)
    mode.add_argument("--replay", type=Path, metavar="FILE")
    mode.add_argument("--record", action="store_true", help="attended private-host run only")
    parser.add_argument("--max-calls", type=int, help="record at most N phrases, in fixture order (1–60)")
    parser.add_argument("--yes-record", action="store_true")
    parser.add_argument("--out", type=Path, help="new private recording file outside any Git worktree")
    parser.add_argument("--min", type=float, default=0.0, help="minimum exact accuracy as a fraction (0–1)")
    args = parser.parse_args(argv)
    if not 0 <= args.min <= 1:
        parser.error("--min must be between 0 and 1")
    if args.record:
        if not args.yes_record or args.max_calls is None or not 1 <= args.max_calls <= 60:
            parser.error("--record requires --yes-record and --max-calls between 1 and 60")
        if args.out is None:
            parser.error("--record requires --out")
        if transport_factory is None:
            parser.error("recording transport unavailable")
    elif args.yes_record or args.max_calls is not None or args.out is not None:
        parser.error("record options require --record")

    try:
        pins, files, _ = assets()
        grammar = edits.Grammar(files)
        phrases = json.loads(PHRASES.read_bytes())
        expected = {row["id"]: row["expected"] for row in phrases}
        if args.record:
            assert args.out is not None and transport_factory is not None  # checked above, before any I/O
            out = args.out.resolve()
            if out.is_relative_to(ROOT) or any((p / ".git").exists() for p in out.parents):
                parser.error("--out must be outside Git worktrees")
            batch = phrases[:args.max_calls]
            if not batch or any(not row["phrase"].strip() or edits.DIGIT.search(row["phrase"]) for row in batch):
                parser.error("recording requires digit-free phrases")
            step = pins["steps"]["edit_map"]
            # Reserve a new owner-only file before constructing the transport.
            fd = os.open(out, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
            with os.fdopen(fd, "w", encoding="utf-8") as stream:
                rows = _record(batch, grammar, step, transport_factory(step))
                json.dump(rows, stream, indent=2, allow_nan=False)
                stream.write("\n")
        else:
            rows = json.loads(args.replay.read_bytes())
            if not isinstance(rows, list) or not rows:
                raise ValueError("expected a nonempty recording array")
    except (OSError, ValueError):
        print("could not read or write eval data")
        print("FAIL npp_edit_eval")
        return 1
    return _report(rows, expected, grammar.schema, args.min)


if __name__ == "__main__":
    def attended_transport(step):
        # The Hermes runner echoes the requested pin in its 'model' field.
        # CodexTransport exposes no service model ID, so _record leaves it null.
        return edits.CodexTransport(step["effort"])

    sys.exit(main(transport_factory=attended_transport))
