"""SKILLS-ITEMADD-1: add a new item end to end (reports/hass/SKILLS-SPEC.md 3.1, card 14 of 20).

One skill, ``item.add``. Mike sends a photo and a few words; Hass drafts ONE change that adds the product, the maker when
the maker is new, the picture and, when he says whether it is in stock, today's shelf check on its own line. He sees a
preview and says yes. The skill only plans typed ops (``maker.add``, ``product.add``, ``store.confirm_selection`` or
``product.set_availability``); the editor, claims gate, live boundary, preview and ``yes <code>`` approval are unchanged (HASS-LIVE-ADD-1: the live boundary lets this change go live under its own rules).

Decisions this card applies: D2 (a new item records today's shelf check on its own line), D5 (a maker with no story gets
the one line "<Maker> is based in <place>."), D6 (a picture that cannot be made to match: kindly ask for a retake; Mike
may say yes knowingly), D9 (no price anywhere: a price or size is left off and said so).

Fields, in the order Hass asks for what is missing (one short plain question at a time, never two):
    name -> what it is (packaged or fresh) -> maker or farm -> their town (new maker only) -> shelf (only when no
    other product of that kind shows it) -> description (drafted in the shop's voice; he corrects it) -> picture
    caption (drafted) -> in stock or not -> the photo.
A required fact the site needs and Mike has not said is asked, never guessed: a farm ("Who grew these tomatoes?"), a town,
a stock word. "Same farm as last time?" is offered from the makers already saved: "same" means the maker of the product added
last. A description, a shelf and a caption are drafted by code from his words (``derive:`` defaults) and shown as "I set".

Interface (built against the SKILLS-FW-3 dispatcher, PR 526, and the FW-2 router, PR 525; neither is merged):

* ``plan(slots, ctx)``: ``ctx.content`` (the loaded, read-only content), ``ctx.today`` (an ISO day or a date) and
  ``ctx.texts`` (the owner's joined texts, or ``ctx.owner_text``). Every attribute is optional: with none the plan still
  turns complete slots into ops when it is told the new product's id (``ctx.next_product_id``; the content gives it
  otherwise), and leaves the checks that need the content to the editor, which repeats every one of them.
  ``plan`` is pure. It fills a missing drafted slot with the same ``derive:`` function the dispatcher calls, so it works
  on the model's raw slots as well as on slots the dispatcher already completed.
* A plan that must stop raises ``Refusal`` (``.reply`` is the owner's sentence; ``.kind`` is "question" when one answer
  fixes it; ``.backlog`` a backlog reason or None), the convention items.py and makers.py already use.
* ``notes(name, slots, ctx)`` gives the lines a proposal shows beside the draft: ``say`` (the shelf-check line, a maker used
  or created), ``set`` ("I set: ..."), ``warn`` ("Left off: ...", the picture advice). The test kit plays it.
* ``question(slot, slots, ctx)`` gives the dynamic wording of the question for a missing slot (the product's name, the saved
  maker offered as "same"); the static ``Slot.ask`` is the fallback.
* The picture: the slot holds the sha256 of the stored original and the plan passes it as ``photo=<sha>``; the house render
  itself happens in ``photos.install`` behind the ``houseRender`` setting (SKILLS-PIC-1). ``ctx.house_render`` says whether it
  is on; the picture advice reads the stored original through ``ctx.photo_bytes(sha)`` or ``ctx.media_root`` and uses the
  read-only checks of hass/house_style.py and hass/newitem_render.py (#504), never editing them.

Owner wording follows docs/hass/VOICE.md. Skill page: docs/hass/skills/item_add.md.
"""
from __future__ import annotations

import hashlib
import json
import re
import types
from datetime import date
from pathlib import Path
from typing import NamedTuple

from hass import claims, house_style as hs, live_policy, maker_site, media, newitem, newitem_render, voice
from hass.content_model import (AVAILABILITY, CATEGORIES, FORBIDDEN_TEXT, INVISIBLE_RE, SHELF_LABELS, TEXT_LIMITS,
                                checked_on)
from hass.interpret_check import PLAIN_TEXT_REPLY, PRICE_REPLY
from hass.ops import catalog
from hass.ops.photos import _alt_problem
from hass.skills import item_intake as intake_mod, makers
from hass.skills.model import Skill, Slot, Trigger, Undo

LIMITS = TEXT_LIMITS["product"]
UNKNOWN_BRAND = "Producer not identified"  # the house words for a product with no known maker
UNKNOWN_SAID = "unknown"  # what the maker slot holds when he skipped the maker (DONT_KNOW reads it; no denial word, so it stays traceable)
NOT_NEEDED = "not needed"  # what the town slot holds when there is no maker to place (unknown or already saved)
FORMS = ("packaged", "fresh")
DONT_KNOW = re.compile(r"^(?:i\s+)?(?:don'?t|do\s+not|dont)\s+know\b|^(?:dunno|not\s+sure|no\s+idea|unknown|nobody|no\s+one"
                       r"|someone|the\s+market|from\s+the\s+market)\b|^producer\s+not\s+identified$", re.IGNORECASE)
SAME_AS_LAST = re.compile(r"^(?:yes[,. ]+)?(?:the\s+)?same(?:\s+(?:farm|maker|one|people|folks|guys|grower|place))?"
                          r"(?:\s+as\s+(?:last\s+time|before|the\s+last\s+one|last\s+one|the\s+other(?:\s+one)?))?[\s.!]*$",
                          re.IGNORECASE)
PACKAGED_WORDS = re.compile(r"\b(?:packag\w*|jar|jars|bottle|bottles|bag|bags|box|boxes|tin|tins|carton|tub|pouch|jug)\b",
                            re.IGNORECASE)
FRESH_WORDS = re.compile(r"\bfresh\b|\bpicked\b|\bloose\b|\bbunch(?:es)?\b|\bfrom the (?:field|farm|garden)\b", re.IGNORECASE)
FRESH_SHELVES = frozenset({"fruit", "vegetables", "eggs", "flowers"})
PACKAGED_SHELVES = frozenset({"pantry", "drinks"})  # dairy, meat and bread can be either: he is asked
FRESH_CHOICES = ("fruit", "vegetables", "dairy", "eggs", "meat", "bread", "flowers")  # the shelves offered for a fresh product
PACKAGED_CHOICES = ("dairy", "meat", "pantry", "drinks", "bread")  # ... and for a packaged one

# -- what Hass says (docs/hass/VOICE.md: short, plain, one question at a time) --------------------------------------
ASK = {"name": "What is it called?", "form": "Is it packaged or fresh?", "maker": "Who made or grew it?",
       "place": "Where are they based (town and state)?", "shelf": "Which shelf does it go on?",
       "description": "What should the description say?", "image_alt": "What does the photo show?",
       "availability": "Is it in stock right now?", "photo": "Send a photo of it."}
ONE_PHOTO = "One photo can go on one product. Which one is this photo for?"
NO_LAST_FARM = "I don't have a farm from last time. Who made or grew it?"
STORE_LINE = "This also records today as the day you checked the shelves."
NO_BYTES = "I couldn't read that photo safely, so nothing changed. Could you send it again as a screenshot?"
RETAKE_BUSY = ("I couldn't separate the product from the background, so the picture won't look like the others. "
               "A new photo on a plain surface, like a white sheet or a bare counter, would look better. "
               "If this one is fine, just reply yes.")
RETAKE_SMALL = ("This photo is small, so the picture will look a little soft. A photo taken closer would look better. "
                "If this one is fine, just reply yes.")
RETAKE_OTHER = ("The picture won't quite match the others. A new photo on a plain surface, with the product in the middle, "
                "would look better. If this one is fine, just reply yes.")
AS_TAKEN = ("I'll use the photo as you took it, so it may look different from the other pictures. A photo on a plain surface, "
            "with the product in the middle, would look better. If this one is fine, just reply yes.")
PICTURE_OK = "The picture is tidied up to match the other pictures on the site."
# HASS-LIVE-ADD-2: the maker's story. A new maker with no words from him and no web address gets ONE plain question, never a
# made-up story. His answer is his own words; "skip" keeps only the one line that says where they are based (D5).
ASK_STORY = "What should we say about {maker}? A sentence is enough."
SKIP_STORY = re.compile(r"\b(?:skip(?:\s+it|\s+the\s+story)?|no\s+story|nothing\s+to\s+(?:say|add)|leave\s+it\s+(?:out|off|blank)|just\s+the\s+town)\b"
                        r"|^\s*(?:no|none|nope|nothing|never\s*mind)[\s.!]*$", re.IGNORECASE)
# HASS-SEC-3 (H2): what a maker's own website says is never published by itself. It is offered here, in the preview, labelled
# with where and when it was read, and goes on the website only with his yes to this exact draft (the same yes-code flow).
SITE_SAYS = ("The maker's own site says: {summary} (source: {url}, read on {day}). "
             "These words go on the website as their story only if you say yes to this change.")


def site_says(summary, url, retrieved) -> str:
    """The preview line for a story written from the maker's website: the exact words, the address and the day it was read
    (the words and the address are marked as quoted, so the voice rules do not judge an address's slashes)."""
    try:
        day = date.fromisoformat(retrieved)
        when = f"{day:%b} {day.day}, {day.year}"
    except (TypeError, ValueError):
        when = "a day I can't read"
    return SITE_SAYS.format(summary=_q(summary), url=_q(url), day=when)


SITE_SKIPPED = "I couldn't use {maker}'s website, so the story is {what}."
LIVE_CLAIM = ("I can't put {what} on the website from chat, so nothing changed. Send it again without that and I'll add the "
              "product.")  # the backlog line that follows says the message is written down for Graham
MANY_ITEMS = "I can add one product at a time. Which one do you want first?"
# One photo is one product (rule one-photo): he names two products in one message, or the name slot lists two. A determiner
# before each product ("the lemon curd and the plum jam") or a list sign (& +) is what tells two products from one name such
# as "Salt and vinegar chips"; "both" in his message with "and" in the name says the same.
_NOUN = r"[\w'\u2019-]+(?:\s+[\w'\u2019-]+){0,3}?"
TWO_IN_MESSAGE = re.compile(rf"\b(?:add|adding|got(?:\s+in)?|have|new)\s+(?:the|a|an|some)\s+{_NOUN}\s+and\s+(?:the|a|an|some)\s+\w",
                            re.IGNORECASE)
TWO_IN_NAME = re.compile(r"\band\s+(?:the|a|an|some|another|their)\s+\w|\s[&+]\s|,\s+and\s|\bplus\s+(?:the|a|an|some)\s+\w", re.IGNORECASE)
# A bare list in his add phrase ("add lemon curd and plum jam", "add lemon curd, plum jam"): the product the model chose sits
# next to a list sign and another product phrase. The chosen name is taken out whole first, so "Salt and vinegar chips" is one
# product; a phrase that opens with a preposition, a stock or photo word or a describing word, or is a maker or a place, is an
# aside and not a second product.
ADD_PHRASE = re.compile(r"\b(?:add|adding|got(?:\s+in)?|have|new)\s+([^.!?\n]+)", re.IGNORECASE)
_SIGN = r"(?:\s*,\s*(?:and\s+)?|\s+and\s+|\s+plus\s+)"
_ASIDE_WORDS = frozenset(
    "in on at from by with for of to into please thanks thank both all also too it its it's that which this these those "
    "photo picture pic image caption stock today now is are was were goes go put sold size price made make makes "
    "taste flavor flavour texture stuff i we he she they and or but so yes no ok okay".split())
# Describing words that open a product phrase ("sweet corn", "organic raspberry jam") but are only an aside when nothing that
# names a product follows them ("great on toast", "fresh from the farm", "tasty").
_DESCRIBING_WORDS = frozenset(
    "great good nice lovely perfect tasty delicious sweet tart fresh packaged organic local homemade handmade new".split())
_MAKER_WORDS = frozenset("farm farms ranch orchard orchards kitchen kitchens bakery creamery dairy company co inc llc apiary "
                         "vineyard winery mill foods garden gardens".split())
_STATES = frozenset(
    "alabama alaska arizona arkansas california colorado connecticut delaware florida georgia hawaii idaho illinois indiana iowa "
    "kansas kentucky louisiana maine maryland massachusetts michigan minnesota mississippi missouri montana nebraska nevada "
    "ohio oklahoma oregon pennsylvania tennessee texas utah vermont virginia washington wisconsin wyoming".split())
BOTH_WORD = re.compile(r"\b(?:both|each\s+of\s+them|two\s+(?:new\s+)?(?:items|products|things))\b", re.IGNORECASE)


class Refusal(ValueError):
    """A plan that cannot go on. ``reply`` is the owner's sentence; ``kind`` is "question" or "refuse"; ``backlog`` names a
    backlog reason, or None."""

    def __init__(self, reply, kind="refuse", backlog=None):
        super().__init__(reply)
        self.reply, self.kind, self.backlog = reply, kind, backlog


class Outcome(NamedTuple):
    ops: list
    set_lines: tuple = ()  # "I set: ..." (what Hass chose because he did not say)
    left_off: tuple = ()  # "Left off: ..." (a price or size, with the reason)
    say: tuple = ()  # plain extra sentences (the shelf-check line, a maker used or created)
    warn: tuple = ()  # the picture advice
    sources: tuple = ()  # HASS-LIVE-ADD-2: where a drafted maker story was read (maker_site.record), kept privately with the draft


# -- plain helpers -------------------------------------------------------------------------------------------------
def _clean(value) -> str:
    return " ".join(value.split()) if isinstance(value, str) else ""


def _fold(text) -> str:
    return claims.fold(text or "")


def _content(ctx):
    return getattr(ctx, "content", None)


def _texts(ctx) -> list:
    texts = getattr(ctx, "texts", None)
    if isinstance(texts, (list, tuple)):
        return [t for t in texts if isinstance(t, str)]
    one = getattr(ctx, "owner_text", None)
    return [one] if isinstance(one, str) and one else []


def _message(ctx) -> str:
    return "\n".join(_texts(ctx))


def _today(ctx):
    raw = getattr(ctx, "today", None)
    if isinstance(raw, date):
        return raw
    try:
        return date.fromisoformat(raw) if isinstance(raw, str) else None
    except ValueError:
        return None


def _q(text) -> str:
    return voice.quote(text)


def _live(ctx) -> bool:
    """True when what the plan makes goes to the real website on his yes (settings ``liveSite``): the live gate is then judged
    here as well, so a claim is rewritten out or refused in plain words, not only caught later."""
    return getattr(ctx, "live", False) is True


def _claim_kinds(text) -> list:
    """The kinds of claim the live gate would refuse in ``text`` (live_policy.PROTECTED), [] when none."""
    return sorted(live_policy._protected(text)[1]) if isinstance(text, str) else []


def _live_claims(ctx, *texts) -> None:
    """Live: a claim (where the food comes from, organic, health, awards, prices, contact, trail facts) in his words is
    refused with the plain reason. The refusal is kept as a policy row for Graham (backlog), never drafted."""
    if not _live(ctx):
        return
    kinds = sorted({k for t in texts for k in _claim_kinds(t)})
    if kinds:
        what = _join([live_policy.PLAIN_KINDS.get(k, "a claim I can't check") for k in kinds], "or")
        raise Refusal(LIVE_CLAIM.format(what=what), "refuse", "policy")


def _site_story(name, url, said, ctx, answered=False, town=""):
    """({"page", "story"} for the maker's own website, or None when he gave no address). A page that cannot be read or has
    nothing usable asks him ONE plain question, never a made-up story. Pure: the read happened BEFORE the conversation's write
    transaction and only its result is behind ``ctx.maker_page`` (HASS-SEC-3 M2). ``answered``: he has already given his own
    story words or said to skip it, so the website is optional: a page that cannot be used is left out (None) and his answer
    is used, instead of asking the same question again. ``town`` is the town he confirmed (the only place the story may name)."""
    address = _clean(url)
    if not address:
        return None
    ask = ASK_STORY.format(maker=name)
    reader = getattr(ctx, "maker_page", None)
    try:
        if not callable(reader):
            raise maker_site.PageError("unreachable")
        page = reader(address)
    except maker_site.PageError as exc:
        if answered:
            return None
        # a site that could not be read (or not in time) is the one plain line, which already asks for his sentence
        raise Refusal(exc.reply if exc.code == "unreachable" else f"{exc.reply} {ask}", "question") from exc
    story = maker_site.draft_story(name, page, said=said, town=town, today=_today(ctx))
    if story is None:
        if answered:
            return None
        raise Refusal(f"{maker_site.CODES['unreadable']} {ask}", "question")
    return {"page": page, "story": story}


def _said(name, text) -> bool:
    """True when ``name`` is among his words (case, accents and punctuation ignored)."""
    return bool(re.search(r"(?<!\w)" + re.escape(_fold(name)) + r"(?!\w)", _fold(text)))


def _join(names, last="or") -> str:
    names = list(names)
    return names[0] if len(names) == 1 else ", ".join(names[:-1]) + f" {last} " + names[-1]


def _price_size(*texts) -> tuple:
    """([price phrases], [size phrases]) the owner wrote, in order, each once."""
    price, size = [], []
    for text in texts:
        for m in newitem.PRICE_RE.finditer(text or ""):
            if m.group(0) not in price:
                price.append(m.group(0))
        for m in newitem.SIZE_RE.finditer(text or ""):
            if m.group(0) not in size:
                size.append(m.group(0))
    return price, size


def clean_name(raw) -> str:
    """The product name as the site wants it: his words with any price or size taken out. '' when nothing is left."""
    name = _clean(raw)
    name = newitem.PRICE_RE.sub(" ", name)
    name = newitem.SIZE_RE.sub(" ", name)
    return _clean(name).strip(" ,-")


def kind_word(name: str, content=None) -> str:
    words = re.findall(r"[\w'’-]+", _fold(name))
    return words[-1] if words else ""


def container(ctx, name="") -> str | None:
    """The container he named (jar, bottle ...), from his words and the name, else None."""
    said = _message(ctx) + "\n" + (name or "")
    return next((c for c in newitem.CONTAINERS if newitem._has(said, c)), None)


def last_maker(content):
    """Return the visible maker key of the highest-numbered active photo product, or None."""
    if content is None:
        return None
    latest, latest_n = None, -1
    for p in content.products:
        m = re.fullmatch(r"photo-product-(\d+)", p.get("id", ""))
        if not m or p.get("status") != "active":
            continue
        n = int(m.group(1))
        if n > latest_n:
            latest, latest_n = p, n
    if latest is None:
        return None
    key = latest.get("producerKey")
    maker = content.makers.get(key)
    return key if maker is not None and not maker.get("hidden") else None


def _maker_names(content) -> dict:
    return {makers._norm(m.get("name", "")): k for k, m in content.makers.items()}


# -- the maker: saved, "the same as last time", unknown or new ----------------------------------------------------------
def resolve_maker(raw, content, aliases=None) -> dict:
    """What he said about who makes it: {"mode": "existing"|"new"|"unknown", "key", "name"}. Stops with a question when it
    is empty, ambiguous or hidden. With no content a name is taken as a new maker."""
    text = _clean(raw)
    if not text:
        raise Refusal(ASK["maker"], "question")
    if DONT_KNOW.match(text):
        return {"mode": "unknown"}
    if SAME_AS_LAST.match(text):
        key = last_maker(content)
        if key is None:
            raise Refusal(NO_LAST_FARM, "question")
        return {"mode": "existing", "key": key, "name": content.makers[key]["name"], "same": True}
    if content is None:
        return {"mode": "new", "name": text}
    found = catalog.lookup(content, "maker", text, aliases)
    if "match" in found:
        key = found["match"]
        maker = content.makers[key]
        if maker.get("hidden") is True:
            raise Refusal(f"{_q(maker['name'])} is hidden. Do you want me to bring them back first?", "question")
        return {"mode": "existing", "key": key, "name": maker["name"]}
    cands = found["candidates"]
    visible = [c for c in cands if c["status"] == "visible"]
    exact = [c for c in visible if makers._norm(c["name"]) == makers._norm(text)]
    if len(exact) == 1:
        return {"mode": "existing", "key": exact[0]["id"], "name": exact[0]["name"]}
    if len(visible) > 1:
        raise Refusal(f"Which maker do you mean: {_join([_q(c['name']) for c in visible])}?", "question")
    if cands and not visible:
        raise Refusal(f"{_q(cands[0]['name'])} is hidden. Do you want me to bring them back first?", "question")
    return {"mode": "new", "name": text}


def _soft_maker(raw, ctx):
    try:
        return resolve_maker(raw, _content(ctx), getattr(ctx, "aliases", None))
    except Refusal:
        return None


# -- drafted defaults (the dispatcher calls these by name; the plan calls them for a slot still empty) ----------------
def form_guess(slots, ctx):
    """packaged when he names a container, fresh for produce that sits on a fresh shelf, else None (he is asked)."""
    name = clean_name(slots.get("name"))
    said = _message(ctx) + "\n" + name
    if PACKAGED_WORDS.search(said):
        return "packaged"
    if FRESH_WORDS.search(said):
        return "fresh"
    shelf = _clean(slots.get("shelf")).casefold() or same_kind_majority(slots, ctx)  # a shelf he named says it too
    return "fresh" if shelf in FRESH_SHELVES else "packaged" if shelf in PACKAGED_SHELVES else None


def same_kind_majority(slots, ctx):
    """The shelf he named, else the shelf most products of the same kind sit on, else None (he is asked)."""
    named = newitem.stated_shelf(_message(ctx)) if _message(ctx) else None
    if named:
        return named
    content, name = _content(ctx), clean_name(slots.get("name"))
    if content is None or not name:
        return None
    return newitem.kind_index(content).get(kind_word(name), {}).get("shelf")


def saved_place(slots, ctx):
    """The town of a maker the site already has (or the one used last time); NOT_NEEDED for an unknown maker; None for a new
    maker, whose town he is asked for."""
    choice = _soft_maker(slots.get("maker"), ctx) if _clean(slots.get("maker")) else None
    if choice is None:
        return None
    if choice["mode"] == "unknown":
        return NOT_NEEDED
    if choice["mode"] == "existing":
        return _content(ctx).makers[choice["key"]].get("place") or None
    return None


def _note_problems(slots, ctx) -> list:
    """HASS-INTAKE-2: why his one sentence for customers cannot be the description ([] when it can). It is his own words, so the
    house checks that apply to any description of his apply to it."""
    note = _clean(_intake(slots).get("customer_note"))
    if not note:
        return []
    try:
        why = description_problems(_text(note, "description", "description"), _message(ctx))
    except Refusal:
        return ["it has a price, a number or a character the website can't show"]
    if _live(ctx) and _claim_kinds(note):
        why.append("it says something I can't put on the website from chat")
    return why


def house_description(slots, ctx):
    """The description in the shop's own voice, from his words and the serving sentences already on the site. Machine-valid,
    not accepted: Mike reads it and may change it. HASS-INTAKE-2: his one sentence for customers is used as it is when it passes."""
    note = _clean(_intake(slots).get("customer_note"))
    if note and not _note_problems(slots, ctx):
        return note
    photo_text = intake_mod.photo_description(_intake(slots))
    if photo_text:
        # Same content, house-style and live-claim checks as any other description.
        # Never relax those gates for a photo or for the label's yes.
        try:
            if not description_problems(_text(photo_text, "description", "description"), _message(ctx)) and not (
                    _live(ctx) and _claim_kinds(photo_text)):
                return photo_text
        except Refusal:
            pass
    content, name = _content(ctx), clean_name(slots.get("name"))
    if content is None or not name:
        return None
    choice = _soft_maker(slots.get("maker"), ctx) if _clean(slots.get("maker")) else None
    place = _clean(slots.get("place"))
    facts = dict.fromkeys(newitem.FACT_KEYS)
    facts.update(name=name, kind=kind_word(name), container=container(ctx, name))
    if choice and choice["mode"] != "unknown":
        facts["maker"] = choice["name"]
        facts["place"] = (content.makers[choice["key"]].get("place") if choice["mode"] == "existing" else place) or None
        if facts["place"] == NOT_NEEDED:
            facts["place"] = None
    text = newitem.compose(facts, content, hs.load_spec(), _message(ctx))["text"]
    if _live(ctx) and _claim_kinds(text):  # rewritten without the claim, never sent with it (HASS-LIVE-ADD-2 B)
        facts.update(maker=None, place=None)
        text = newitem.compose(facts, content, hs.load_spec(), _message(ctx))["text"]
    sentences = [s for s in hs.sentences(text) if not (_live(ctx) and _claim_kinds(s))]
    for extra in newitem.GENERIC_SERVING:
        if len(sentences) >= 2:
            break
        if extra not in sentences:
            sentences.append(extra)
    return " ".join(sentences)


def alt_text(slots, ctx):
    """The picture caption: the product's name, plus 'in a <container>' only when he said the container."""
    name = clean_name(slots.get("name"))
    return newitem.alt_text({"name": name, "container": container(ctx, name)}) if name else None


AVAILABILITY_WORDS = {"yes": "in stock", "limited": "low on stock", "no": "sold out"}


def _intake(slots) -> dict:
    """HASS-INTAKE-2: his private intake answers so far (quantity, price, dates ...); never a public word."""
    got = slots.get("intake") if isinstance(slots, dict) else None
    return got if isinstance(got, dict) else {}


def stock_guess(slots, ctx):
    """HASS-INTAKE-2: the stock word from the count he said he bought (and his low-stock number), else None (he is asked). Shown
    as "I set", so he can change it before his yes."""
    got = _intake(slots)
    qty, low = got.get("qty"), got.get("low_stock")
    if isinstance(qty, bool) or not isinstance(qty, (int, float)) or qty <= 0:
        return None
    return "limited" if isinstance(low, (int, float)) and not isinstance(low, bool) and qty <= low else "yes"


DERIVERS = {"form_guess": form_guess, "same_kind_majority": same_kind_majority, "saved_place": saved_place,
            "house_description": house_description, "alt_text": alt_text, "stock_guess": stock_guess}


# -- HASS-INTAKE-2: the full intake interview (hooks the dispatcher calls; setting ``itemIntake``) -------------------------
def _new_maker(slots, ctx) -> bool:
    choice = _soft_maker(slots.get("maker"), ctx) if _clean(slots.get("maker")) else None
    return bool(choice and choice["mode"] == "new")


def answer(req, text, ctx):
    """HASS-INTAKE-2: with the interview on, a plain short answer to the name, maker or town question is read by fixed code (no
    model call, so the questions come at once). Anything longer, with a number or a list in it, is left to the model.
    ``skip`` and ``don't know`` mean the same here as at every other question and are never kept as a value: a name, shelf or
    packaging he skips is asked once more (see ``intake_skip``); a maker he skips is listed as not identified; a town he skips
    leaves the maker not identified too, and the name he gave stays in his private record only."""
    slot = req.get("asked_slot")
    if not intake_mod.enabled(ctx) or req.get("state") != "open" or slot not in ("name", "maker", "place", "shelf", "form"):
        return None
    words = _clean(text)
    if words and intake_mod.SKIP.match(words):
        if slot == "maker":
            return {"maker": UNKNOWN_SAID, "place": NOT_NEEDED, "_text": UNKNOWN_SAID}
        if slot == "place":
            return {"maker": UNKNOWN_SAID, "place": NOT_NEEDED, "_text": UNKNOWN_SAID,
                    "intake": {**_intake(req.get("slots")), "maker_named": _clean((req.get("slots") or {}).get("maker"))}}
        return {"skipped": slot}
    if slot not in ("name", "maker", "place"):
        return None
    if not words or len(words.split()) > 6 or re.search(r"[\d$@/]", words) or "\n" in text or len(words) > 60:
        return None
    if re.fullmatch(r"(?:yes|no|ok|okay|cancel|stop)[.!]*", words, re.IGNORECASE) or (slot == "name" and (TWO_IN_NAME.search(words) or "," in words)):
        return None
    return {slot: words}


def intake_skip(req, slot, ctx) -> str:
    """The one honest reply to a skipped name, shelf or packaging: nothing is invented, the same question comes once more."""
    why = intake_mod.PUBLIC_NEEDED.get(slot, "I can't go on without that.")
    ask = question(slot, req.get("slots") or {}, ctx)
    return f"{why} {ask[:-1] if ask.endswith('?') else ask}, or say cancel?"


def intake_next(slots, ctx):
    """(asked-slot name, the one question) for the next intake question, or None when the interview is off or done. The
    answers wait in ``slots["intake"]``; a skipped question is kept there as None, so it is never asked twice."""
    if not intake_mod.enabled(ctx):
        return None
    got = _intake(slots)
    key = intake_mod.next_key(got, _new_maker(slots, ctx))
    if key is None:
        return None
    ask = intake_mod.question(key, clean_name(slots.get("name")), got)
    return intake_mod.PREFIX + key, (f"{intake_mod.INTRO} {ask}" if not got else ask)


def intake_read(req, text, ctx) -> dict:
    """His answer to the open intake question: {"abort": True}, {"again": the question again} or {"slots": the slots it sets,
    "public": whether the answer may join his texts (only a maker's website), "note": a sentence to say first or None}."""
    key = (req.get("asked_slot") or "")[len(intake_mod.PREFIX):]
    today = _today(ctx) or date.today()
    got = intake_mod.read(key, text, _intake(req["slots"]), today=today, asks=req.get("asks") or 1,
                          reader=(lambda k, words: ctx.intake_reader(k, words, today)) if getattr(ctx, "intake_reader", None) else None)
    if got[0] == "abort":
        return {"abort": True}
    if got[0] == "again":  # what was wrong, then the same one question again
        return {"again": f"{got[1]} {intake_mod.question(key, clean_name(req['slots'].get('name')), _intake(req['slots']))}"}
    answers, extra, note = got[1], got[2], got[3]
    return {"slots": {"intake": {**_intake(req["slots"]), **answers}, **extra}, "public": "maker_url" in extra, "note": note}


def intake_record(skill_name, slots, ctx, code, now):
    """The private record kept beside the draft ``code`` (None when he gave no intake answers)."""
    got = _intake(slots)
    if not got:
        return None
    content = _content(ctx)
    maker = _clean(slots.get("maker"))
    maker = None if not maker or maker == UNKNOWN_BRAND or DONT_KNOW.match(maker) else maker  # unknown is not a maker's name
    return intake_mod.record(code, clean_name(slots.get("name")), maker, _clean(slots.get("shelf")) or None,
                             _next_id(ctx, content), slots.get("photo"), got, now)


def _filled(slots, ctx):
    """(slots with every empty drafted slot filled by its derive function, [names filled])."""
    out, filled = dict(slots), []
    for slot in SKILL_SLOTS:
        if out.get(slot.name) not in (None, "", []) or not (isinstance(slot.default, str) and slot.default.startswith("derive:")):
            continue
        if slot.name == "place" and not _clean(out.get("maker")):
            continue
        value = DERIVERS[slot.default[7:]](out, ctx)
        if value not in (None, ""):
            out[slot.name] = value
            filled.append(slot.name)
    return out, filled


# -- the question for a missing slot -----------------------------------------------------------------------------------
def question(slot_name, slots, ctx) -> str:
    """The one short question for ``slot_name``, in his words where the site knows them. Never two questions in one."""
    content, name = _content(ctx), clean_name(slots.get("name"))
    if slot_name == "maker":
        verb = "grew" if slots.get("form") == "fresh" else "makes"
        what = "these " + name.lower() if name.endswith("s") else "this " + name.lower() if name else "it"
        last = last_maker(content)
        offer = f" (Last time it was {_q(content.makers[last]['name'])}. Say the name again to use them.)" if last else ""
        return f"Who {verb} {what}?{offer}" if name else ASK["maker"]
    if slot_name == "place":
        choice = _soft_maker(slots.get("maker"), ctx) if _clean(slots.get("maker")) else None
        who = choice["name"] if choice and choice.get("name") else _clean(slots.get("maker"))
        return f"Where is {_q(who)} based (town and state)?" if who else ASK["place"]
    if slot_name == "shelf":
        shelves = FRESH_CHOICES if slots.get("form") == "fresh" else PACKAGED_CHOICES
        return "Which shelf does it go on: " + _join([SHELF_LABELS[c] for c in shelves]) + "?"
    return ASK.get(slot_name, ASK["name"])


# -- reading the slots -----------------------------------------------------------------------------------------------
def _text(value, limit_key, what, *, ask=None) -> str:
    text = _clean(value)
    if not text:
        if ask:
            raise Refusal(ask, "question")
        return ""
    if newitem.PRICE_RE.search(text) or "$" in text:
        raise Refusal(PRICE_REPLY)
    if any(bad in text for bad in FORBIDDEN_TEXT) or INVISIBLE_RE.search(text):
        raise Refusal(PLAIN_TEXT_REPLY)
    if len(text) > LIMITS[limit_key]:
        raise Refusal(f"That {what} is longer than the website has room for. Could you make it shorter?")
    return text


def _form(value) -> str:
    text = _clean(value).casefold()
    if text in FORMS:
        return text
    if re.search(r"\bfresh\b", text) and not PACKAGED_WORDS.search(text):
        return "fresh"
    if PACKAGED_WORDS.search(text):
        return "packaged"
    raise Refusal(ASK["form"], "question")


def _twin(content, name, brand):
    want = (_fold(name), _fold(brand))
    return next((p for p in content.products if (_fold(p.get("name", "")), _fold(p.get("brand", ""))) == want), None)


def _selection_checked_today(ctx, content):
    flag = getattr(ctx, "selection_checked_today", None)
    if isinstance(flag, bool):
        return flag
    today = _today(ctx)
    return bool(content is not None and today is not None and checked_on(content.store) == today)


def _next_id(ctx, content):
    given = getattr(ctx, "next_product_id", None)
    if isinstance(given, str) and given:
        return given
    return newitem.next_product_id(content) if content is not None else None


# -- one photo, one product -------------------------------------------------------------------------------------------
def _norm(text) -> str:
    text = (text or "").lower().replace("\u2019", "'")
    return " ".join(re.sub(r"\s[&+]\s", " and ", text).split())


def _is_product_phrase(chunk, *, after="") -> bool:
    """True when ``chunk`` (the words beside the chosen name in a list) reads as another product and not an aside."""
    words = chunk.split()
    while words and words[0] in ("the", "a", "an", "some", "another"):
        words = words[1:]
    while words and words[0] in _DESCRIBING_WORDS:  # "sweet corn" opens with a describing word but still names a product
        words = words[1:]
    if not words or words[0] in _ASIDE_WORDS or not words[0][0].isalpha():
        return False
    for i, word in enumerate(words):
        if word in _ASIDE_WORDS:
            words = words[:i]
            break
    if not words or len(words) > 4 or any(w.strip(".,") in _MAKER_WORDS for w in words):
        return False
    nxt = re.match(r"\s*,\s*([a-z]+)", after)
    return not (nxt and nxt.group(1) in _STATES)  # "Smith Farm, Oregon" is a maker and its place


def _bare_list(name, turn) -> bool:
    """True when this text lists another product right beside the one the model named: ``add lemon curd and plum jam`` or
    ``add lemon curd, plum jam``. The name is taken out whole, so ``Salt and vinegar chips`` is one product."""
    name = _norm(_clean(name))
    if not name:
        return False
    find = re.compile(r"(?<![\w'])" + r"\s+".join(re.escape(t) for t in name.split()) + r"(?![\w'])")
    for phrase in ADD_PHRASE.finditer(_norm(turn)):
        listed = phrase.group(1)
        hit = find.search(listed)
        if not hit:
            continue
        left, right = listed[:hit.start()], listed[hit.end():]
        beside = re.match(_SIGN + r"(.+)", right)
        if beside:
            tail = beside.group(1)
            other = re.split(r",|\s+and\s+|\s+plus\s+", tail)[0]
            if _is_product_phrase(other, after=tail[len(other):]):
                return True
        before = re.search(r"^(.*?)" + _SIGN + r"(?:(?:the|a|an|some|another)\s+)?$", left)
        if before and _is_product_phrase(re.split(_SIGN, before.group(1))[-1]):
            return True
    return False


def _two_in_turn(name, turn) -> bool:
    """True when this one text of his (with the name the model gave) puts two products on the photo."""
    if name and re.search(r"\band\b", name, re.IGNORECASE) and BOTH_WORD.search(turn):
        return True
    return bool(TWO_IN_MESSAGE.search(turn)) or _bare_list(name, turn)


def several_products(raw_name, message) -> bool:
    """True when his words (or the name the model gave) put two products on the one photo and he has not yet said which.

    ``message`` is his texts so far, a list (a single string is one text). The question this raises is answered by a later
    text of his that names the one product the plan is for (``The lemon curd only, please``) and does not list two again;
    the earlier text is kept, so a plan whose product he never picked still asks."""
    turns = [message] if isinstance(message, str) else [t for t in (message or []) if isinstance(t, str)]
    name = _clean(raw_name)
    if name and TWO_IN_NAME.search(name):
        return True
    asked = [i for i, turn in enumerate(turns) if _two_in_turn(name, turn)]
    if not asked:
        return False
    if name and re.search(r"\band\b", name, re.IGNORECASE):  # the model still has two products in the one name
        return True
    named = re.compile(rf"(?<!\w){re.escape(name.lower())}(?!\w)") if name else None
    for turn in turns[asked[-1] + 1:]:
        if named and named.search(turn.lower()) and not _two_in_turn(name, turn) and not BOTH_WORD.search(turn) \
                and not TWO_IN_NAME.search(turn):
            return False
    return True


# -- the description: the house hard checks (reports/hass/SKILLS-SPEC.md 3.1, rule house-description) ------------------
def description_problems(text, owner_text="") -> list:
    """The plain-words reasons a description cannot go on the site, [] when it can. Hard: no digit or price, no ``!`` or ``?``,
    no hype word, and the shop's own length (the measured minimum and maximum) and sentence count. An unstated claim word is
    left to the claims gate, which asks him about it, so it is not a reason here."""
    spec = hs.load_spec()["descriptions"]
    check = hs.check_description(text, owner_text=owner_text)
    failed = {c["name"] for c in check["checks"] if not c["ok"]}
    why = []
    if "no price or number" in failed:
        why.append("it has a number in it")
    if "no hype words" in failed:
        why.append("it has sales words")
    if "no exclamation or question marks" in failed:
        why.append("it has an exclamation or question mark")
    chars = hs.description_metrics(text)["chars"]
    if chars < spec["chars"]["min"]:
        why.append("it is shorter than the others on the site")
    elif chars > spec["chars"]["max"]:
        why.append("it is longer than the others on the site")
    if "sentence count like the others" in failed:
        why.append(f"it should be {spec['sentences']['min']} or {spec['sentences']['max']} sentences")
    return why


def description_refusal(why) -> Refusal:
    return Refusal(f"That description won't match the others on the site: {_join(why, 'and')}. "
                   "Could you send a different one?", "question")


# -- the plan ----------------------------------------------------------------------------------------------------------
def describe_add(slots: dict, ctx=None) -> Outcome:
    if not isinstance(slots, dict):
        raise Refusal(ASK["name"], "question")
    content, message = _content(ctx), _message(ctx)
    if several_products(slots.get("name"), _texts(ctx)):  # one photo is one product, whatever the model returned
        raise Refusal(ONE_PHOTO, "question")
    slots, filled = _filled(slots, ctx)

    # 1. name: his words, no price or size
    raw_name = _clean(slots.get("name"))
    if not raw_name:
        raise Refusal(question("name", slots, ctx), "question")
    name = clean_name(raw_name)
    if not name:
        raise Refusal(question("name", slots, ctx), "question")
    if any(c.isdigit() for c in name):
        raise Refusal("The name can't have numbers or sizes in it. What is it called?", "question")
    name = _text(name, "name", "name")
    _live_claims(ctx, name, slots.get("story"), slots.get("image_alt"))  # live: a claim in a public word is refused, never drafted
    price, size = _price_size(raw_name, message)

    # 2. what it is: packaged or fresh
    if not _clean(slots.get("form")):
        raise Refusal(question("form", slots, ctx), "question")
    form = _form(slots["form"])
    slots["form"] = form

    # 3. the maker or farm
    if not _clean(slots.get("maker")):
        raise Refusal(question("maker", slots, ctx), "question")
    choice = resolve_maker(slots["maker"], content, getattr(ctx, "aliases", None))
    if choice.get("same") and not _said(choice["name"], message):  # the claims gate wants a maker in his own words: he is asked to say it
        raise Refusal(f"Please say the name, so I use the right one: {_q(choice['name'])}.", "question")
    ops: list = []
    sources: tuple = ()
    set_lines: list = []
    say: list = []
    left: list = []
    key = brand = None
    if choice["mode"] == "unknown":
        brand = UNKNOWN_BRAND
        say.append("I couldn't tell who makes it, so the card says it is from the market.")
    elif choice["mode"] == "existing":
        key, brand = choice["key"], choice["name"]
        if choice.get("same"):
            set_lines.append(f"the maker to {_q(brand)}, the same as last time")
        else:
            say.append(f"{_q(brand)} is already on the site, so I'm using them.")
    else:  # a new maker needs their town; with no story the one-line note is written (D5)
        place = _clean(slots.get("place"))
        if not place or place == NOT_NEEDED:
            raise Refusal(question("place", slots, ctx), "question")
        # the maker's story (HASS-LIVE-ADD-2 C, HASS-SEC-3 H2): his own words, plus a short story written from a few facts on
        # the maker's OWN website when he gave its address (maker_site.draft_story: what they make, since when, the town he
        # confirmed; never a page sentence). It is labelled in the preview with its address and day, and goes live only with
        # his yes to this draft. With neither, one plain question; "skip" keeps only the D5 line. The address itself is not
        # kept on the maker (the website-link field is protected and is never published); it is the story's recorded source.
        mine = _clean(slots.get("story"))
        # a skip given in any later text of this request holds for the rest of it, so revising the description or caption after
        # a skipped story revises the draft instead of asking for the story again (Codex RETURN at 9f213272, item 1)
        skipped = any(SKIP_STORY.search(t) for t in _texts(ctx)[1:])
        found = _site_story(choice["name"], slots.get("maker_url"), mine, ctx, answered=bool(mine) or skipped,
                            town=place.split(",")[0].strip())
        summary = " ".join(found["story"]["sentences"]) if found else ""
        story_in = " ".join(part for part in (mine, summary) if part)
        if not story_in and not skipped:
            raise Refusal(ASK_STORY.format(maker=choice["name"]), "question")
        try:
            made = makers.describe_add({"name": choice["name"], "place": place, "story": story_in or None, "url": None},
                                       types.SimpleNamespace(content=content, owner_text=message or None))
        except makers.Refusal as exc:
            raise Refusal(exc.reply, exc.kind) from exc
        if found and summary in made.ops[0]["args"].get("story", ""):  # the label is shown exactly when the text is in the draft
            sources = (maker_site.record(found["page"], found["story"]),)
            say.append(site_says(summary, found["page"]["url"], found["page"]["retrieved"]))
        elif _clean(slots.get("maker_url")):  # the website could not be used and his answer (or skip) stands in for it
            say.append(SITE_SKIPPED.format(maker=_q(choice["name"]), what="your words" if mine else "just the town"))
        ops += made.ops
        key, brand = made.ops[0]["args"]["key"], choice["name"]
        set_lines += list(made.set_lines)
        left += list(made.left_off)
        say.append(f"{_q(brand)} is new on the site, so I'm adding them too.")

    # twin: the same name and maker is never a second product (asked before anything else is asked)
    if content is not None and (twin := _twin(content, name, brand)) is not None:
        tail = {"active": "is already on the site. Do you want to change it instead?",
                "hidden": "is on the site but hidden. Do you want me to bring it back instead?"}.get(
            twin.get("status"), "is on hold until someone has looked at it.")
        raise Refusal(f"{_q(twin['name'])} {tail}", "question" if twin.get("status") != "held" else "refuse")

    # 4. the shelf
    shelf = _clean(slots.get("shelf")).casefold()
    if shelf not in CATEGORIES:
        raise Refusal(question("shelf", slots, ctx), "question")
    if "shelf" in filled and newitem.stated_shelf(message) != shelf:  # he named the shelf himself: nothing to say
        set_lines.append(f"the shelf to {SHELF_LABELS[shelf]}, like the other products of this kind")

    # 5. the description: drafted in the shop's voice, or his own words
    description = _clean(slots.get("description"))
    photo_draft = intake_mod.photo_description(_intake(slots))
    if photo_draft and description != photo_draft:
        left.append("the photo's description or approved label wording, because the website's existing wording and claim checks still apply. "
                    "The photo details stay in your private notes")
    if _clean(_intake(slots).get("customer_note")) and (why := _note_problems(slots, ctx)):  # HASS-INTAKE-2: said once, never silently dropped
        left.append(f"your sentence for customers, because {_join(why, 'and')}. I wrote the usual kind of description instead")
    if description and "description" not in filled and _live(ctx) and (kinds := _claim_kinds(description)):
        # live: his own description says something the website cannot carry from chat; it is rewritten without it, and he is told
        slots = dict(slots, description=house_description({**slots, "description": None}, ctx))
        description = _clean(slots.get("description"))
        filled.append("description")
        left.append("your wording of the description, because it says "
                    + _join([live_policy.PLAIN_KINDS.get(k, "a claim I can't check") for k in kinds], "or")
                    + ", which I can't put on the website from chat")
    if not description:
        raise Refusal(question("description", slots, ctx), "question")
    description = _text(description, "description", "description")
    if (why := description_problems(description, message)):
        raise description_refusal(why)
    if "description" in filled:
        set_lines.append(f"the description to \u201c{_q(description)}\u201d, and you can send a different one if you like")

    # 6. the picture caption
    alt = _clean(slots.get("image_alt"))
    if not alt:
        raise Refusal(question("image_alt", slots, ctx), "question")
    alt = _text(alt, "imageAlt", "picture caption")
    if (bad := _alt_problem(alt, "0" * 64)):
        raise Refusal("The picture caption should say what the photo shows, like " + _q("Wildflower honey in a jar") + ". What should it say?",
                      "question")

    # 7. in stock or not
    word = slots.get("availability")
    if word not in AVAILABILITY:
        raise Refusal(question("availability", slots, ctx), "question")
    if "availability" in filled:  # HASS-INTAKE-2: worked out from the count he gave
        set_lines.append(f"the stock word to {AVAILABILITY_WORDS[word]}, from the count you gave")

    # 8. the photo
    sha = slots.get("photo")
    if not (isinstance(sha, str) and media.SHA_RE.fullmatch(sha)):
        raise Refusal(question("photo", slots, ctx), "question")

    args = {"name": name, "brand": brand, "category": shelf, "description": description, "photo": sha, "imageAlt": alt}
    if key is not None:
        args["producerKey"] = key
    display = _clean(slots.get("display_brand"))
    if display:
        args["displayBrand"] = _text(display, "displayBrand", "maker line")
    if _intake(slots).get("new_badge") is False:  # HASS-INTAKE-2: his "no" to the New label
        if _live(ctx):  # the live table of allowed arguments is G's own list and has no such argument: said, never hidden
            left.append("your no to the New label, because the live website adds it by itself for two weeks and I can't turn it off from "
                        "chat. I wrote your no down for Graham")
        else:  # added without its day: the shop shows no label for a product with no addedOn (shop.js isNew)
            args["showNew"] = False
            set_lines.append("no New label on it, as you asked")
    ops.append({"op": "product.add", "args": args})

    # 9. the inventory word and today's shelf check (D2): the check goes in the same change, on its own line
    new_id = _next_id(ctx, content)
    if new_id is None:
        raise Refusal("I can't tell which product number comes next, so nothing was drafted. Please send it again in a few minutes.")
    if _selection_checked_today(ctx, content):
        ops.append({"op": "product.set_availability", "args": {"id": new_id, "available": word}})
    else:
        ops.append({"op": "store.confirm_selection", "args": {word: [new_id]}})
        say.append(STORE_LINE)

    # a price or size is never written: say so, once
    if price or size:
        parts = ([f"the price ({_join(price, 'and')})"] if price else []) + ([f"the size ({_join(size, 'and')})"] if size else [])
        left.append(f"{_join(parts, 'and')}, because the website shows no prices or sizes")
    return Outcome(ops, tuple(set_lines), tuple(left), tuple(say), _picture_notes(ctx, sha), sources)


def plan_add(slots: dict, ctx=None) -> list:
    key = _drafted_key(slots)
    done = describe_add(slots, ctx)
    _remember(ctx, key, done)
    return done.ops


# HASS-SEC-3 (L3): the Outcome of the drafting call itself, kept on the ctx the dispatcher drafts with, so the lines shown
# beside the draft (``notes``) and the private source record (``sources``) describe the very read the draft was written from.
def _drafted_key(slots) -> str:
    try:
        return json.dumps(slots, sort_keys=True, default=str)
    except (TypeError, ValueError):
        return repr(slots)


def _remember(ctx, key, done) -> None:
    if ctx is None:
        return
    kept = getattr(ctx, "drafted", None)
    if not isinstance(kept, dict):
        try:
            ctx.drafted = kept = {}
        except AttributeError:
            return
    kept[key] = done


def _drafted(ctx, slots):
    kept = getattr(ctx, "drafted", None)
    return kept.get(_drafted_key(slots)) if isinstance(kept, dict) else None


# -- the picture advice (read-only: nothing is written, nothing is committed) ----------------------------------------------
def _original(ctx, sha):
    """The stored original's bytes when the caller can give them (``ctx.photo_bytes(sha)`` or ``ctx.media_root``), else None.

    The source-photo ceiling (``media.MAX_BYTES``) is enforced again at this later read: a file is read through an open stream
    with a ``MAX_BYTES + 1`` bound and anything longer is refused (None) before it is hashed or reviewed. A ``photo_bytes``
    result longer than the ceiling is refused before it is copied; what happens inside that trusted callback is not bounded here."""
    fn = getattr(ctx, "photo_bytes", None)
    try:
        if callable(fn):
            data = fn(sha)
            if data and len(data) > media.MAX_BYTES:
                return None
            return bytes(data) if data else None
        root = getattr(ctx, "media_root", None)
        if not root:
            return None
        folder = Path(root) / "originals" / sha[:2]
        for ext in ("jpg", "png"):
            path = folder / f"{sha}.{ext}"
            if path.is_file():
                with path.open("rb") as stream:
                    data = stream.read(media.MAX_BYTES + 1)
                if len(data) > media.MAX_BYTES:
                    return None
                return data if hashlib.sha256(data).hexdigest() == sha else None
    except (OSError, ValueError, TypeError):
        return None
    return None


def picture_review(data: bytes, house_render: bool) -> tuple:
    """(say, warn) lines about this photo, in plain words. With the house render on, the render is tried and the picture is
    judged as it would be committed; with it off the photo goes on the site as sent, so it is judged as it is."""
    try:
        if house_render:
            out = newitem_render.render(data)
            report, check = out["report"], out["check"]
            small = any("small" in r for r in report.get("review", []))
            busy = report.get("isolation") != "cutout" or any("Could not cut" in r for r in report.get("review", []))
            if not busy and not small and not report.get("review") and check["pass"]:
                return (PICTURE_OK,), ()
            return (), ((RETAKE_BUSY if busy else RETAKE_SMALL if small else RETAKE_OTHER),)
        return (), (() if hs.check_image(data)["pass"] else (AS_TAKEN,))
    except (hs.PillowMissing, ImportError):
        return (), ()  # the picture tools are not here: say nothing rather than guess
    except (media.Refused, newitem_render.Refused) as exc:
        return (), (exc.reply,)
    except Exception:  # noqa: BLE001 - a photo that cannot be decoded is one plain sentence, never a crash
        return (), (NO_BYTES,)


def _picture_notes(ctx, sha) -> tuple:
    out = []
    data = _original(ctx, sha)
    if data is not None:
        say, warn = picture_review(data, bool(getattr(ctx, "house_render", False)))
        out += list(say) + list(warn)
    return tuple(out)


def set_phrases(slots, ctx) -> list:
    """The plain phrases for the dispatcher's "I set: ..." line (D8): what Hass chose because he did not say. Never raises."""
    try:
        return list(describe_add(dict(slots), ctx).set_lines)
    except Refusal:
        return []


SET_PHRASES = {"item.add": set_phrases}


def sources(name, slots, ctx) -> list:
    """Where the drafted maker story was read ([maker_site.record, ...]); the dispatcher keeps them privately with the draft.
    HASS-SEC-3 (L3): only ever the drafting call's own record (kept by ``plan_add`` on the ctx it drafted with); the plan is
    never run again for it, so the page is never read a second time and the record cannot describe a different read.
    Never raises."""
    done = _drafted(ctx, slots)
    return list(done.sources) if done is not None else []


def notes(name, slots, ctx) -> dict:
    """The lines a proposal shows beside the draft, as the test kit (and the dispatcher, once it asks) plays them. With the
    drafting ctx (HASS-SEC-3 L3) they are the drafting call's own lines, so the label he reads is the text the draft carries."""
    done = _drafted(ctx, slots)
    if done is None:
        try:
            done = describe_add(dict(slots), ctx)
        except Refusal:
            return {}
    say = list(done.say) + [w for w in done.warn if w in (PICTURE_OK,)] + intake_mod.private_lines(_intake(slots))
    warn = [f"Left off: {line}." for line in done.left_off] + [w for w in done.warn if w != PICTURE_OK]
    return {"say": say, "set": [f"I set: {line}." for line in done.set_lines], "warn": warn}


# -- the skill ---------------------------------------------------------------------------------------------------------
_MAKERS, _PRODUCTS, _STORE = "hass/content/makers.json", "hass/content/products.json", "hass/content/store.json"
_GEN = (("storefront-mockup/catalog-products.js", "products"), ("storefront-mockup/index.html", "products"),
        ("storefront-mockup/producers.js", "producers"), ("storefront-mockup/producers.json", "producers"))
_PICTURE = ("storefront-mockup/assets/products/photo-<sha16>.<ext>", "file")

SKILL_SLOTS = (
    Slot("name", "text", required=True, ask=ASK["name"], owner_words=True, limit=("product", "name")),
    Slot("form", "enum", required=True, default="derive:form_guess", ask=ASK["form"]),
    Slot("maker", "text", required=True, ask=ASK["maker"], owner_words=True),
    Slot("place", "text", required="if:maker", default="derive:saved_place", ask=ASK["place"], owner_words=True,
         limit=("maker", "place")),
    Slot("story", "text", required=False, owner_words=True, limit=("maker", "story")),
    Slot("maker_url", "url", required=False, owner_words=True),
    Slot("shelf", "shelf", required=True, default="derive:same_kind_majority", ask=ASK["shelf"]),
    Slot("description", "text", required=True, default="derive:house_description", ask=ASK["description"], owner_words=True,
         limit=("product", "description")),
    Slot("image_alt", "text", required=True, default="derive:alt_text", ask=ASK["image_alt"], owner_words=True,
         limit=("product", "imageAlt")),
    Slot("display_brand", "text", required=False, owner_words=True, limit=("product", "displayBrand")),
    Slot("availability", "availability", required=True, default="derive:stock_guess", ask=ASK["availability"]),
    Slot("photo", "attachment", required=True, ask=ASK["photo"], from_attachment=True),
)

ITEM_ADD = Skill(
    pack='site', targets=('site',), approval_class='A1', sandbox='full', logs=('subjects', 'fields'), who='owner',
    name="item.add", label="add a new product", version=2,
    summary="Add a new product from a photo and a few words: its maker if new, the picture, and whether it is in stock.",
    triggers=(
        Trigger("new honey from Cal Poly, goes on the pantry shelf"),
        Trigger("new hott sauce from bee happy farm in atascadero, wildflower flavor, its in", "typo"),
        Trigger("add this", "vague"),
        Trigger("Etto's new rigatoni, same shelf as their other pasta"),
        Trigger("Cal Poly honey 8oz jar $9 just got in"),
        Trigger("new jam, dont know who makes it"),
        Trigger("I have a new item", "vague"),
        Trigger("add the lemon curd and the plum jam", "multi"),
        Trigger("organic local raspberry jam from Linn's"),
        Trigger("got some fresh tomatoes in today, same farm as last time"),
    ),
    slots=SKILL_SLOTS,
    rules=("twin", "maker-not-held", "house-picture", "house-description", "claims", "shelf-check-today", "price-left-off",
           "story-note", "one-photo"),
    plan=plan_add,
    edits=((_MAKERS, "makers[key]"), (_PRODUCTS, "products[id]"), (_STORE, "selection_checked_on"), _PICTURE) + _GEN,
    side_effects=("picture-render", "maker-create", "inventory-word", "shelf-check-day"),
    preview="product:the new product", approval="owner-yes", live_class="chat-live",  # HASS-LIVE-ADD-1: live_policy.LIVE has product.add and maker.add
    undo=Undo("revert", "The product is hidden, not deleted; a new maker is hidden with it; the picture file stays on the site folder, unused."),
    refuse=(
        ("a price is in the message", PRICE_REPLY),
        ("the product is already on the site", "<Product> is already on the site. Do you want to change it instead?"),
        ("the maker is hidden", "<Maker> is hidden. Do you want me to bring them back first?"),
        ("two products on one photo", ONE_PHOTO),
        ("the photo cannot be read", media.REPLIES["unreadable"]),
    ),
    cases="hass/tests/fixtures/skills/item_add/item.add.jsonl",
)

SKILLS = (ITEM_ADD,)
