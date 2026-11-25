#!/usr/bin/env python3
"""Check that a label claim the copy stage leaves off can reach the owner's card note.

Offline fixture probe. It drives the unmodified ProductionStages.start_plan and
render_listing (real Writer, real _candidate, real compose) over one synthetic
item and three label readings, and reports whether the claim reached the Writer
input, came back as a Writer omission, and appears in the final Card.note.
"""

import argparse
from datetime import datetime, timezone
from decimal import Decimal
import hashlib
from pathlib import Path
import sys
import tempfile
import types
from typing import Any
from unittest import mock

ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from hass import npp  # noqa: E402
from hass.npp import copy, identify, job, missing, stages  # noqa: E402

NAME = "npp_claim_note_reach"
ITEM = "Wildflower Honey"
OWNER_TEXT = "Wildflower Honey $4 each"
PHOTO = b"fixture-photo-bytes"
PHOTO_SHA = hashlib.sha256(PHOTO).hexdigest()
PNG = b"\x89PNG\r\n\x1a\n" + b"fixture-card"
CREATED_AT = datetime(2030, 1, 1, tzinfo=timezone.utc).isoformat()
IMAGE_PATH = "fixture-house.png"
PRICE: Any = Decimal("4")
IMAGE_SHA = hashlib.sha256(b"fixture-house-picture").hexdigest()
LEFT_OFF = "left off: "
# (case label, visible_claims the label read returns, tuple the Writer must see, safe omission tuple it must return)
CASES = (
    ("organic", ["Organic"], ("Organic",), ("unconfirmed origin or organic wording",)),
    ("health", ["immune support"], ("immune support",), ("immune support",)),
    ("no_claim", [], (), ()),
)


class Recorder:
    """Observe the real Writer without altering what the pipeline sees (``tamper`` is a test-only seam)."""

    def __init__(self, writer, tamper=None):
        self.writer, self.tamper, self.calls = writer, tamper, []

    def write(self, ctx, select=None, **options):
        written = self.writer.write(ctx, select, **options)
        if written is not None and self.tamper is not None:
            written = self.tamper(written)
        self.calls.append((tuple(ctx.label_claims), select, None if written is None else tuple(written.dropped)))
        return written

    def __getattr__(self, name):
        return getattr(self.writer, name)


class FrozenHouse:
    """A frozen house-style picture whose bracket annotation is off (it is not what this probe qualifies)."""
    variant, note, image_path, image_sha256 = "house", False, IMAGE_PATH, IMAGE_SHA
    matches_draft = stages.picture.FrozenPicture.matches_draft


def _fixture_port(root, claims, stages_class, tamper):
    pinned = npp.assets()
    png_path = root / "card.png"
    png_path.write_bytes(PNG)
    content = types.SimpleNamespace(products=(), makers={}, active_products=lambda: ())
    draft = {"created_at": CREATED_AT, "assets": {IMAGE_PATH: "sha256:" + IMAGE_SHA}}
    editor = types.SimpleNamespace(candidate=lambda operations: {"result": "ok", "draft": dict(draft)})
    conversation = types.SimpleNamespace(
        editor=editor, settings={}, _now=lambda: datetime(2030, 1, 1, tzinfo=timezone.utc),
        _capture=lambda draft, candidate=False: {"ok": True, "picture": PNG, "png": str(png_path), "cardEvidence": {}})
    decision = missing.Decision(
        True, ITEM, "pantry", missing.OwnerPrice(PRICE, "item"), missing.Maker("absent"), (), (), ())
    evidence = {"kind": "food", "is_product": True, "item": ITEM, "visible_claims": list(claims), "label_words": [],
                "has_person_or_screen": False, "size_text": None, "brand_on_label": None}
    port: Any = object.__new__(stages_class or stages.ProductionStages)
    recorder = Recorder(copy.Writer(pinned), tamper)
    port.replies, port.pinned, port.c, port.writer = pinned[2], pinned, conversation, recorder
    port.selector = None
    port.identifier = types.SimpleNamespace(read=lambda photos: identify.Reading(evidence, {}) if tuple(photos) else None)
    port.missing = types.SimpleNamespace(decide=lambda *args, **kwargs: decision)
    port.catalog = lambda: content
    port.clover = lambda: None
    port._photo = lambda sha: PHOTO
    port._research = lambda *args, **kwargs: ()
    port._picture = lambda work, listing, private, *, local: (
        FrozenHouse(), work.request["attachments"][0], "", [])
    return port, recorder


def _work():
    request = {"texts": [OWNER_TEXT], "attachments": [PHOTO_SHA],
               "slots": {"intake": {"price": "4", "price_span": [17, 24]}}}
    return job.Work("fixture-job", request, None, datetime(2030, 1, 1, 0, 5, tzinfo=timezone.utc))


def _case(root, claims, stages_class, tamper):
    port, recorder = _fixture_port(root, claims, stages_class, tamper)
    work = _work()
    plan = port.start_plan(work)
    if not isinstance(plan, job.Plan) or plan.listing is None:
        raise ValueError("no plan")
    card = port.render_listing(work, plan.listing, local=True)
    if not isinstance(card, job.Card):
        raise ValueError("no card")
    return recorder.calls, card.note, port.replies["brackets"]["compose"]["separator"]


def probe(stages_class=None, tamper=None):
    """One observation per case: label, input matched, omission matched, note parts matched (plus the note, never printed)."""
    results = []
    # Only fixture-only validation and OCR seams are replaced; nothing real runs for them.
    with tempfile.TemporaryDirectory() as folder, \
            mock.patch.object(stages.validate, "listing", lambda *args, **kwargs: types.SimpleNamespace(ok=True)), \
            mock.patch.object(stages.picture, "read_text", lambda *args, **kwargs: ""):
        for label, claims, expected_input, expected_drop in CASES:
            calls, note, separator = _case(Path(folder), claims, stages_class, tamper)
            if not calls or any(select is not None for _, select, _ in calls):
                raise ValueError("writer not observed or selector ran")
            parts = [part for part in note.split(separator) if part.startswith(LEFT_OFF)]
            expected_parts = [LEFT_OFF + expected_drop[0]] if expected_drop else []
            results.append((label, all(seen == expected_input for seen, _, _ in calls),
                            all(dropped == expected_drop for _, _, dropped in calls), parts == expected_parts, note))
    return results


def report(results):
    """The fixed stdout lines and the exit code for a list of probe observations."""
    yes = lambda flag: "yes" if flag else "no"
    lines = [f"claim {label} writer_input={yes(a)} writer_drop={yes(b)} card_note={yes(c)}" for label, a, b, c, _ in results]
    for index, reason in ((1, "label-claims-unpassed"), (2, "writer-drop-mismatch"), (3, "claim-note-mismatch")):
        if not all(row[index] for row in results):
            lines.append(f"FAIL {reason}")
    failed = any(line.startswith("FAIL ") for line in lines)
    lines.append(f"FAIL {NAME}" if failed else f"PASS {NAME}")
    return lines, int(failed)


def main(argv=None, *, stages_class=None, tamper=None):
    argparse.ArgumentParser(description=__doc__).parse_args(argv)
    try:
        lines, code = report(probe(stages_class, tamper))
    except Exception:  # noqa: BLE001 - report only the fixed finding, never exception text
        lines, code = ["FAIL check-error", f"FAIL {NAME}"], 1
    print("\n".join(lines))
    return code


if __name__ == "__main__":
    sys.exit(main())
