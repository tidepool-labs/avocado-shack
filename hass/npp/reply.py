"""S9/S11/S13 owner lines and the S10 edit segment of the stage port (design 1.2-1.4, reply-templates.json).

Every owner-facing line comes from the pinned hass-npp-reply/reply-templates.json: the ready prompt carries its own
version tag (``yes <code>-<n>``) and at most one bracket of fallback words (<= bracket_max_chars, parts dropped in the
asset's drop order); guards are one line and never offer a card; the publish confirmation names the live link.

``Stages`` is the stage port the job runner (hass/npp/job.py) drives. Its edit segment (S10) is built here: his new
words since the parent version become a typed patch on a copy of the parent listing, or one question. The start segment
and the card render are C/D/E/F work, passed in as ``start`` and ``render``.
"""
import json
import re

from hass.npp import edits
from hass.npp.job import Plan
from hass.skills import intake_simple

SITE = "https://theavocadoman.com"
PRODUCT_ID = re.compile(r"[a-z0-9][a-z0-9-]{0,63}")
SEEN = "_texts"  # how many request texts a version has consumed (job-private, never published)
NAME_FROM_PHOTO = "nameFromPhoto"  # the listing kept the photo's name over a made-by name that disagreed with it
QUESTION_STATES = ("asking",)
EDIT_STATES = ("working", "card_out", "editing")


def compose(replies, parts):
    """The one bracket (without parentheses) for ``parts`` {part key: format args}, or "" when none apply.

    Parts join in priority order (the reverse of drop_order); while the bracket would pass bracket_max_chars the first
    remaining part of drop_order is dropped (reply-templates.json brackets.compose.rule)."""
    rule, texts = replies["brackets"]["compose"], replies["brackets"]["parts"]
    order = [k for k in reversed(rule["drop_order"]) if k in parts]
    unknown = set(parts) - set(rule["drop_order"])
    if unknown:
        raise ValueError(f"unknown bracket part {sorted(unknown)[0]}")
    shown = {k: texts[k].format(**parts[k]) for k in order}
    cap = replies["caps"]["bracket_max_chars"]
    for key in rule["drop_order"]:
        if len(rule["separator"].join(shown.values())) + 2 <= cap:
            break
        shown.pop(key, None)
    return rule["separator"].join(shown.values())


def ready_line(replies, code, n, parts=None):
    """``Post this? Reply yes <code>-<n>, or tell me what to change.`` plus the composed bracket."""
    text = replies["prompts"]["ready"].format(code=code, n=n)
    note = compose(replies, parts or {})
    return f"{text} ({note})" if note else text


def guard(replies, key):
    """One of the one-line approval guards (not_ready, which_card, replaced, render_failed, live_check_failed)."""
    if key == "guard_note" or key not in replies["guards"]:
        raise KeyError(key)
    return replies["guards"][key]


def posted(replies, product_id, site=SITE):
    """S13, sent only after the live check sees the card: the item link on the market shelf and the undo hint."""
    if not isinstance(product_id, str) or not PRODUCT_ID.fullmatch(product_id):
        raise ValueError("product id")
    return replies["confirm"]["posted"].format(url=f"{site}/?item={product_id}#market")


def question(replies, edit):
    """(question id, sentence) for an Edit that asks or replies; None for a patch."""
    if edit.reply:
        return edit.reply, replies["edits"][edit.reply]
    if edit.ask:
        return edit.ask, replies["questions"][edit.ask].format(**dict(edit.ask_args))
    return None


def one_line(text):
    """True for a guard-shaped line: one line, at most one sentence plus one bracket."""
    if "\n" in text or text.count("(") > 1:
        return False
    body = re.sub(r"\s*\([^()]*\)$", "", text)
    return len(re.findall(r"[.!?](?:\s|$)", body)) <= 1


class Stages:
    """The job runner's stage port (see hass/npp/job.py). ``start(work)`` and ``render(work, listing)`` are the C/D/E/F
    composition; this class owns turn routing and the edit segment."""

    def __init__(self, pinned, *, start, render, mapper=None):
        _pins, files, self.replies = pinned
        self.grammar = edits.Grammar(files)
        self.start, self.render_card, self.mapper = start, render, mapper

    def takes_turn(self, text, state):
        """Cheap routing only. An answer while Hass waits on his question; a change while a card is out. A question
        to Hass ("what time do we close?") is not taken: it gets its normal answer."""
        words = " ".join(text.split())
        if not words or words.endswith("?") or intake_simple.QUESTION.match(words):
            return False
        if state in QUESTION_STATES:
            return True
        if state not in EDIT_STATES:
            return False
        return bool(self.grammar.match(words) or intake_simple.PRICE_EDIT.fullmatch(words)
                    or self.grammar.supplier(words) or re.match(r"(?:please\s+)?(?:change|make|use|put|call|say|set|swap)\b",
                                                                words, re.I))

    def plan(self, work):
        if work.parent is None:
            plan = self.start(work)
            if isinstance(plan, Plan) and plan.listing is not None:
                # Version 1 consumed every text so far; the edit segment reads only what came after its parent.
                plan = Plan(listing={**plan.listing, SEEN: len(work.request["texts"])}, patch=plan.patch,
                            questions=plan.questions, retake=plan.retake, identified=plan.identified)
            return plan
        return self.edit(work)

    def edit(self, work):
        """S10 on the job's parent version: the new texts since it, read in order (the last value wins)."""
        parent = json.loads(work.parent["listing_json"])
        texts = work.request["texts"]
        finance = dict(work.request["slots"].get("intake", {}))
        seen = parent.get(SEEN, 0)
        new = [t for t in texts[seen:] if isinstance(t, str)]
        price_changed = finance.get("price") is not None and finance["price"] != parent.get("sellingPrice")
        found = []
        for text in new or [""]:
            got = edits.read(self.grammar, text, finance, self.mapper)
            if got.ask == "ask_price" and price_changed:
                got = edits.Edit(patch=edits.price_patch(finance))  # the amount was read by code from this turn
            if (asked := question(self.replies, got)) is not None:
                return Plan(questions=(asked,), identified=True)
            found.append(got)
        if price_changed and not any(f == "sellingPrice" for e in found for f, _ in e.patch):
            found.append(edits.Edit(patch=edits.price_patch(finance)))
        listing, patch = edits.apply(parent, found)
        listing[SEEN] = len(texts)
        if "name" in patch:
            # He named the item himself ("call it ...", the correction the name-from-photo note offers): the card no
            # longer carries the photo's name, so the note goes with it.
            listing.pop(NAME_FROM_PHOTO, None)
        if not patch or all(parent.get(k) == v for k, v in patch.items() if k != "rewrite") and "rewrite" not in patch:
            return Plan(questions=(("ask_edit_unclear", self.replies["questions"]["ask_edit_unclear"]),), identified=True)
        return Plan(listing=listing, patch=patch, identified=True)

    def render(self, work, listing):
        return self.render_card(work, listing)

    def cap(self, work, listing):
        """The bounded local fallback at the segment deadline: never waits on a model; a missing listing re-plans."""
        if listing is not None:
            return self.render(work, listing)
        plan = self.plan(work)
        return (plan, self.render(work, plan.listing)) if plan.listing is not None and not plan.questions else plan


def build_stages(conversation, pinned):
    """Construct the full port or fail closed; never route a partial pipeline to prepare."""
    try:
        from hass.npp.stages import build

        return build(conversation, pinned)
    except (ImportError, KeyError, ValueError, TypeError):
        return None
