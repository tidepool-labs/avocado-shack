"""Private intake parsing and storage for item.add.

With itemIntake enabled, dispatch + intake_simple build one editable catalog preview
instead of interviewing the owner. Typed quantity/cost/price are separated from public
copy before any general interpreter call and retained with the open request.
Only the selling price goes on the catalog card; cost and quantity stay private.

The pure single-answer helpers remain for bounded parsing and existing skill-toolkit
consumers. They are not the production conversation flow. Photo claims need no separate
consent; the editable draft is the review. Existing live-policy holds still apply.
"""
from __future__ import annotations

import json
import os
import re
import sqlite3
from datetime import date, datetime, timedelta

from hass import voice
from hass.content_model import FORBIDDEN_TEXT, INVISIBLE_RE

PREFIX = "intake:"  # the asked-slot name of an intake question on the open request ("intake:qty")
STORE = "item-intake.jsonl"  # the private record, in the state folder
PENDING = ("CREATE TABLE IF NOT EXISTS intake_pending (code TEXT PRIMARY KEY, record_json TEXT NOT NULL, created_at TEXT NOT NULL)")
KEEP_DAYS = 30  # a waiting record nobody said yes to is forgotten after this long
MAX_TEXT = 400
PRIVATE_HEAD = "Kept private, not on the website:"
INTRO = "A few quick questions for your books. Say skip if you don't know one."
START = ("Got the photo. A few quick questions: name, maker, how many, how it's sold, price, details, dates and a note "
         "for customers. First, what is it called?")
RECEIPT = "CREATE TABLE IF NOT EXISTS intake_receipt (provider_id TEXT PRIMARY KEY, sent_at TEXT NOT NULL)"

ORDER = ("maker_site", "qty", "qty_unit", "sold_by", "price", "cost", "ingredients", "variety", "origin", "claims",
         "allergens", "storage", "best_by", "received", "low_stock", "customer_note", "new_badge")
TEXT_FIELDS = ("ingredients", "variety", "origin", "claims", "allergens", "storage")
LABELS = {"ingredients": "Ingredients", "variety": "Flavor, size or variety", "origin": "Origin",
          "claims": "On the label (unverified, your word)", "maker_site": "Maker's website", "allergens": "Allergens", "storage": "Storage and use"}

SKIP = re.compile(r"^\s*(?:skip(?:\s+(?:it|this|that|one))?|pass|next|(?:i\s+)?(?:don'?t|do\s+not|dont)\s+know|dunno|not\s+sure|no\s+idea"
                  r"|unknown|n/?a|i\s+forgot|can'?t\s+(?:say|tell|remember))\s*[.!]*\s*$", re.IGNORECASE)
NONE_WORDS = re.compile(r"^\s*(?:none|no|nope|nothing|nil|no\s+claims?|no\s+allergens?)\s*[.!]*\s*$", re.IGNORECASE)
ABORT = re.compile(r"^\s*(?:cancel|stop|never\s*mind|forget\s+it|drop\s+it|start\s+over|quit)\s*[.!]*\s*$", re.IGNORECASE)
CODED_KEYWORD = re.compile(r"^\s*(?:yes|no|ok|okay|approve|reject|undo|cancel|show)[\s,:-]+[0-9a-f]{4,6}\s*[.!]*\s*$", re.IGNORECASE)

UNIT_WORDS = {"each": "each", "ea": "each", "item": "each", "items": "each", "piece": "each", "pieces": "each",
              "case": "case", "cases": "case", "bag": "bag", "bags": "bag", "lb": "lb", "lbs": "lb", "pound": "lb",
              "pounds": "lb", "oz": "oz", "ounce": "oz", "ounces": "oz", "bundle": "bundle", "bundles": "bundle",
              "bunch": "bundle", "bunches": "bundle", "dozen": "dozen", "dozens": "dozen", "box": "box", "boxes": "box",
              "jar": "jar", "jars": "jar", "bottle": "bottle", "bottles": "bottle", "tin": "tin", "tins": "tin",
              "carton": "carton", "cartons": "carton", "tub": "tub", "tubs": "tub", "pack": "pack", "packs": "pack",
              "pouch": "pouch", "pouches": "pouch", "loaf": "loaf", "loaves": "loaf", "kg": "kg", "g": "g", "can": "can", "cans": "can", "jug": "jug", "jugs": "jug",
              "bar": "bar", "bars": "bar", "sack": "sack", "sacks": "sack", "crate": "crate", "crates": "crate",
              "gallon": "gallon", "gallons": "gallon"}
SOLD_WORDS = {"item": "per item", "pound": "per pound", "bag": "per bag", "bundle": "per bundle"}
NUMBER_WORDS = {"a": 1, "an": 1, "one": 1, "two": 2, "three": 3, "four": 4, "five": 5, "six": 6, "seven": 7, "eight": 8, "nine": 9,
                "ten": 10, "eleven": 11, "twelve": 12}
MONTHS = {m: i for i, m in enumerate("jan feb mar apr may jun jul aug sep oct nov dec".split(), 1)}


# -- small helpers ----------------------------------------------------------------------------------------------------
def _clean(text) -> str:
    return " ".join(text.split()) if isinstance(text, str) else ""


def _q(text) -> str:
    return voice.quote(text)


def _said(text) -> str:
    """His own words for the summary, without a closing full stop (the sentence adds its own)."""
    return voice.quote(str(text).strip().rstrip(" ."))


def _units(qty, unit) -> str:
    """\"1 jar\", \"137 jars\", \"5 lb\", \"3 cases\": the unit as he said it, plural when there is more than one."""
    if not unit or qty == 1 or unit in ("lb", "oz", "kg", "g", "each"):
        return unit
    if unit == "loaf":
        return "loaves"
    return unit + ("es" if unit.endswith(("s", "x", "ch", "sh")) else "s")


def _num_text(n) -> str:
    return str(int(n)) if float(n) == int(n) else ("%g" % n)


def _day_text(iso) -> str:
    try:
        d = date.fromisoformat(iso)
        return f"{d:%b} {d.day}, {d.year}"
    except (TypeError, ValueError):
        return "a day I can't read"


def money_text(value) -> str:
    return "$" + value if isinstance(value, str) and value else ""


def enabled(ctx) -> bool:
    return getattr(ctx, "intake", False) is True


def commerce_answers(value):
    """Strict model boundary: bool/float/extra keys and out-of-range quantities are not commerce facts."""
    keys = {"price_cents", "cost_cents", "quantity"}
    if not isinstance(value, dict) or set(value) != keys: return {}
    if any(v is not None and (type(v) is not int or not 0 <= v <= (100000 if k == "quantity" else 99999999))
           for k, v in value.items()): return {}
    out = {k: "%d.%02d" % divmod(value[source], 100) for k, source in (("price", "price_cents"), ("cost", "cost_cents"))
           if value[source] is not None}
    if value["quantity"] is not None: out.update(qty=value["quantity"], qty_unit="each")
    return out


_COUNT_WORD = (r"(?:zero|one|two|three|four|five|six|seven|eight|nine|ten|eleven|twelve|thirteen|fourteen|"
               r"fifteen|sixteen|seventeen|eighteen|nineteen|twenty|thirty|forty|fifty|sixty|seventy|"
               r"eighty|ninety|hundred|thousand|million|billion|trillion|dozen|half|halves|quarter|quarters|couple)")
_FINANCE_CUE = re.compile(
    r"\b(?:bought|paid|cost|costs|wholesale|sell|selling|price|retail|have|stock|qty|quantity|purchased|dollars?|items?)\b|\$|\d"
    r"|\b" + _COUNT_WORD + r"\b|\b(?:a|an)\s+(?:" + "|".join(UNIT_WORDS) + r")\b",
    re.I,
)


def unresolved_finance(text):
    """Detect finance left in the deterministic parser's public remainder."""
    return bool(_FINANCE_CUE.search(text))


def without_unresolved_finance(text):
    """Fail closed on whole unresolved clauses, including on reader failure."""
    return "; ".join(part.strip() for part in re.split(r"[;\n]+|(?<!\d),|,(?!\d)", text)
                     if part.strip() and not unresolved_finance(part))


_SELL = r"(?:I['’]?ll\s+|(?:I\s+)?(?:will\s+)?)sell(?:ing)?\b"
_CAPTION_BREAK = re.compile(
    r"[;\n]+|(?<!\d),|,(?!\d)|"
    r"\s+and\s+(?=" + _SELL + r"|(?:I\s+)?(?:bought|paid)\b|\d\b(?!\s+cents?\b))|"
    r"(?<=\w)[.!]\s+(?=" + _SELL + r")|"
    r"(?<=\d)\s+(?=sell(?:ing)?\b)|\s*/\s*(?=sell(?:ing)?\b)", re.I)
_SLASH_COST = re.compile(r"\s*\$\d+(?:\.\d{1,2})?\s*")


def caption_spans(caption):
    """Yield independent caption clauses with offsets into the original text."""
    start = 0
    for cut in (*_CAPTION_BREAK.finditer(caption), None):
        end = cut.start() if cut else len(caption)
        part = caption[start:end]
        if cut and cut[0].strip() == '/' and _SLASH_COST.fullmatch(part):
            part = 'cost ' + part.strip()  # explicitly supported "$3 / sell $5 each" shorthand
        yield start, end, part
        if cut:
            start = cut.end()


def caption_answers(caption, extracted=None):
    """Separate typed finance spans from public words. Never called on image output.

    Ambiguous clauses stay untouched for the existing refusal/question path, not guessed.
    Repeated conflicting answers are not seeded.
    """
    # _read_intake tags photo turns in the existing per-turn handoff. Their
    # caption must keep the original routing into the label/preview path.
    photo = False
    if isinstance(extracted, dict) and extracted.keys() == {"photo_fields"}:
        extracted, photo = extracted["photo_fields"], True
    if not photo and re.match(r"\s*(?:(?:add|description)\s*:|say\s+it['’]s\b|(?:rename|change the name)\b)", caption, re.I):
        return caption, {}  # literal copy edits are not instructions to change the price
    basis = r"(?:(?:\s*/\s*|\s+(?:(?:per|a)\s+)?)(?:lbs?|pounds?|each|items?|baskets?))"
    cash = r"(?P<amount>\$\s*[0-9]{1,6}(?:\.(?:[0-9]{1,2}|[0-9]O))?)"
    stock = (r"(?P<count>\d+)\s+(?P<unit>lb|pounds?|items?|each)\s+in\s+stock" if photo else
             r"(?P<count>[0-9]{1,6})\s+(?P<unit>lbs?|pounds?|items?|each)\s+in\s+stock")
    word = "(?:" + "|".join(ONES) + ")"
    tens = "(?:" + "|".join(TENS) + ")"
    spoken_cash = r"(?P<amount>\b(?:[0-9]{1,6}|" + tens + r"(?:[- ]" + word + r")?|" + word + r")\s+(?:dollars?|bucks?))"
    uncertain = r"\b(?:minus|negative|or|maybe|about|around)\s*$"
    # Voice dictation sometimes spells the punctuation between a spoken price and the next clause.
    if not photo:
        caption = re.sub(r"(?<=\w)\s+(?:comma|period)\s+(?=" + _SELL + r"|they\b)", "; ", caption, flags=re.I)
    public, answers, conflicts = [], {}, set()
    model = commerce_answers(extracted)
    for _, _, part in caption_spans(caption):
        text = re.sub(r"^(?:I['’]?ll\s+(?=sell\b)|(?:I\s+)?(?:will\s+)?(?:just\s+(?=bought\b))?)",
                      "", part.strip().rstrip(".!"), flags=re.I)
        got, price_basis = {}, ""
        purchase = re.fullmatch(r"(?:bought|got|purchased)\s+(\d+)(?:\s+of\s+(?:these|them))?\s+(?:at|for)\s+(.+)", text, re.I)
        money = re.fullmatch(r"(bought|purchased|paid|costs?|wholesale|sell|selling|(?:sale\s+)?price|retail)"
                             r"(?:\s+(?:it|them))?(?:\s+(?:for|at))?\s*:?\s+(.+)", text, re.I)
        retail = re.fullmatch(r"(\$.+?)\s+retail", text, re.I)
        qty = re.fullmatch(r"(?:(bought|got|have|stock|qty|quantity)\s*:?\s*)?(\d+(?:\.\d+)?)(?:\s+(of them|of these|each|[a-z]+))?", text, re.I)
        if purchase:
            count = _parse_count(purchase[1])
            cost = _parse_money(purchase[2])
            if count is not None and cost is not None: got.update(qty=count, qty_unit="each", cost=cost)
        elif qty and (qty[1] or qty[3]):
            unit = "each" if not qty[3] or qty[3].lower() in ("of them", "of these") else qty[3]
            parsed = _parse_qty(qty[2] + " " + unit)
            if parsed: got.update(qty=parsed[0], qty_unit=parsed[1])
            elif unit in UNIT_WORDS and _parse_count(qty[2]) == 0:
                got.update(qty=0, qty_unit=UNIT_WORDS[unit])
        elif photo and re.fullmatch(r"\$\d+(?:\.\d{1,2})?(?:/(?:lb|each)|\s+(?:each|per\s+(?:lb|pound|item|each)))?", text, re.I):
            value = _parse_money(text)
            if value is not None: got["price"] = value
        elif match := re.fullmatch(stock, text, re.I):
            got.update(qty=int(match["count"]), qty_unit=UNIT_WORDS[match["unit"].lower()])
        elif money:
            key = "cost" if money[1].lower() in {"bought", "purchased", "paid", "cost", "costs", "wholesale"} else "price"
            value = _parse_money(money[2])
            if value is not None: got[key] = value
        elif retail:
            value = _parse_money(retail[1])
            if value is not None: got["price"] = value
        remaining = part.strip()
        if not photo and not got and not (purchase or qty or money or retail):
            # Retain the owner words before a finance tail, without accepting a
            # prefix of a malformed amount or guessing between two values.
            if match := re.search(r"(?:^|\s+)(?:and\s+)?" + stock + r"$", text, re.I):
                count = int(match["count"])
                if count <= 100000 and not re.search(uncertain, text[:match.start()], re.I):
                    got.update(qty=count, qty_unit=UNIT_WORDS[match["unit"].lower()])
                    remaining = text = text[:match.start()].strip()
            cue = r"(?:(?P<cost>cost|paid|bought)\s+(?:(?:for|at)\s+)?|for\s+)?"
            match = None
            if text.count("$") == 1:
                match = re.search(rf"(?:^|\s+){cue}{cash}(?P<basis>{basis}*)$", text, re.I)
            elif "$" not in text:
                aside = r"(?:they(?:['’]re|\s+are)\s+(?:like\s+)?)?"
                match = re.search(rf"(?:^|\s+){aside}{cue}{spoken_cash}(?P<basis>{basis}+)$", text, re.I)
            if match:
                units = set(re.findall(r"[a-z]+", match["basis"].lower())) - {"per", "a"}
                units = {"basket" if u in ("basket", "baskets") else _parse_sold_by(u) for u in units}
                amount = re.sub(r"(?<=\.[0-9])o$", "0", match["amount"], flags=re.I)
                value = _parse_money(amount)
                before = text[:match.start()].strip()
                # A price-shaped suffix does not override a nearby unresolved
                # finance cue ("don't sell $5 each", "costs about $3").
                if (value is not None and len(units) <= 1 and not re.search(uncertain, before, re.I)
                        and (match["cost"] or not unresolved_finance(re.sub(r"^new item\b", "", before, flags=re.I)))):
                    key = "cost" if match["cost"] else "price"
                    got[key] = value
                    if key == "price": price_basis = next(iter(units), "")
                    remaining = before
                    if re.fullmatch(r"(?:add|new(?: item)?)(?:\s+(?:it|this|that))?", remaining, re.I):
                        remaining = ""  # an add command alone is not a product name
                    elif re.match(r"(?:add|new(?: item)?)\s+", remaining, re.I):
                        # An unverified adjective or superlative is not part of a food name.
                        remaining = re.sub(r"^(add|new(?: item)?)\s+(?:(?:organic|local)\s+)+", r"\1 ", remaining, flags=re.I)
                        remaining = re.sub(r"\s+best ever$", "", remaining, flags=re.I)
                        if re.fullmatch(r"add|new(?: item)?", remaining.strip(), re.I):
                            remaining = ""
        if not got:
            if remaining and not (model and re.search(r"\b(?:bought|paid|cost|sell|selling|price|retail|have|stock|qty|quantity|purchased|dollars?|items?)\b|\$", text, re.I)):
                public.append(part.strip())
            continue
        if "qty" in got and (type(got["qty"]) is not int or not 0 <= got["qty"] <= 100000):
            got.pop("qty")
            got.pop("qty_unit", None)
        if price_basis == "basket": got["price_unit"] = "basket"  # no public basket basis in the current catalog schema
        elif price_basis: got["sold_by"] = price_basis
        elif "price" in got:
            # Units in cost and quantity clauses do not set the sale basis.
            priced = retail[1] if retail else text
            if unit := re.search(basis + r"$", priced, re.I):
                parsed_unit = _parse_sold_by(unit[0])
                if parsed_unit:
                    got["sold_by"] = parsed_unit
                elif unit[0].lower().endswith(("basket", "baskets")):
                    got["price_unit"] = "basket"
        if remaining and remaining != part.strip(): public.append(remaining)
        for key, value in got.items():
            if key in answers and answers[key] != value: conflicts.add(key)
            answers[key] = value

    out = {k: v for k, v in {**answers, **model}.items() if k not in conflicts}
    if "qty" in out and answers.get("qty_unit"): out["qty_unit"] = answers["qty_unit"]
    return "; ".join(public), out


def photo_description(intake):
    details = intake.get("photo_details") or {}
    if intake.get("photo_confirmed") is not True: return ""
    text = details.get("description", "")
    accepted = [claim for i, claim in enumerate(details.get("printed_claims", []))
                if intake.get("photo_claim_answers", {}).get(str(i)) is True]
    return " ".join([text, *(c.rstrip(".") + "." for c in accepted)]).strip()


def acknowledge(db, provider_id, now) -> bool:
    """The photo message ``provider_id`` has had its first question. True the first time, False when it was already answered (a
    photo that could not be fetched is tried again later and must not be answered twice)."""
    db.execute(RECEIPT)
    stamp = now.isoformat() if hasattr(now, "isoformat") else str(now)
    return db.execute("INSERT OR IGNORE INTO intake_receipt(provider_id, sent_at) VALUES (?, ?)", (provider_id, stamp)).rowcount == 1


def acknowledged(db, provider_id) -> bool:
    try:
        return db.execute("SELECT 1 FROM intake_receipt WHERE provider_id = ?", (provider_id,)).fetchone() is not None
    except sqlite3.Error:
        return False


# A skipped or unknown answer to a PUBLIC question is never turned into a value: a name or a shelf is needed for the listing, so he
# is told so and asked once more (he can say cancel); a maker he does not know is listed as not identified, and a town he does not
# know leaves the maker not identified too (the name he gave stays in his private record only).
PUBLIC_NEEDED = {"name": "I can't list it without a name, and I won't make one up.",
                 "form": "I need to know that to put it on the right shelf, and I won't guess.",
                 "shelf": "I can't list it without a shelf, and I won't pick one for you."}


# -- what is asked next -----------------------------------------------------------------------------------------------
def next_key(intake, new_maker=False):
    """The next question's key, in the order Mike is asked, or None when everything is answered or skipped. A key that is in
    ``intake`` (even as None, which is a skip) is done."""
    got = intake if isinstance(intake, dict) else {}
    for key in ORDER:
        if key in got:
            continue
        if key == "maker_site" and not new_maker:
            continue
        if key == "qty_unit" and got.get("qty") is None:
            continue
        return key
    return None


def _per(intake) -> str:
    return {"item": "for each one", "pound": "per pound", "bag": "for each bag", "bundle": "for each bundle"}.get(
        (intake or {}).get("sold_by"), "for each one")


def question(key, name, intake) -> str:
    """The one plain question for ``key``. Never two questions in one."""
    what = _q(name) if name else "it"
    if key == "maker_site":
        return "Do they have a website? Send the address, like www.example.com, or say skip."
    if key == "qty":
        return f"How many did you buy of {what}? A number and what they come in is perfect, like 12 jars, 3 cases or 5 lb."
    if key == "qty_unit":
        return f"And what are the {_num_text(intake['qty'])} counted in: each, cases, bags, pounds or ounces?"
    if key == "sold_by":
        return "Is it sold per item, per pound, per bag or per bundle?"
    if key == "price":
        return f"What do you charge {_per(intake)}? I keep prices private. The website does not show them."
    if key == "cost":
        return f"What did you pay {_per(intake)}? You can skip this one."
    if key == "ingredients":
        return "What are the ingredients?"
    if key == "variety":
        return "Is there a flavor, size or variety I should note?"
    if key == "origin":
        return "Where does it come from?"
    if key == "claims":
        return "Does the label say anything special, like organic? I note it as your word, unchecked, and keep it off the website."
    if key == "allergens":
        return "Are there any allergens on the label?"
    if key == "storage":
        return "How should it be stored or used?"
    if key == "best_by":
        return "What is the best-by or expiration date?"
    if key == "received":
        return "What day did you buy or receive it?"
    if key == "low_stock":
        return "At what count should I call it low on stock?"
    if key == "customer_note":
        return "Is there one sentence you would like customers to read about it?"
    if key == "new_badge":
        return "Should it show the New label? Yes or no."
    raise KeyError(key)


# -- reading an answer ------------------------------------------------------------------------------------------------
# A fixed reading accepts only a COMPLETE, UNAMBIGUOUS answer (the whole text is the number, the money, the unit, the day, the
# yes or the no). Anything else ("9 dollars and a bit", "12 or maybe 24 jars", "yes, actually no") is never cut down to its first
# part: it goes to the interpreter once (when one is set up, and only on the first try), and if that cannot give an exact value
# either, Mike is asked again in plain words. A third unreadable answer is left blank and he is told so; it is never guessed.
ONES = {w: i for i, w in enumerate("zero one two three four five six seven eight nine ten eleven twelve thirteen fourteen fifteen "
                                   "sixteen seventeen eighteen nineteen".split())}
TENS = {"twenty": 20, "thirty": 30, "forty": 40, "fifty": 50, "sixty": 60, "seventy": 70, "eighty": 80, "ninety": 90}
YES_FULL = re.compile(r"^(?:yes|yep|yeah|yup|y|sure|ok|okay|please|do it|yes please|sure thing)\s*[.!]*$", re.IGNORECASE)
NO_FULL = re.compile(r"^(?:no|nope|nah|n|no thanks|no thank you|not needed|not this time|leave it off)\s*[.!]*$", re.IGNORECASE)
INTERPRETED = frozenset({"qty", "qty_unit", "sold_by", "price", "cost", "best_by", "received", "low_stock", "new_badge"})
BLANK_NAMES = {"maker_site": "the website", "qty": "how many", "qty_unit": "what they are counted in", "sold_by": "how it is sold",
               "price": "the price", "cost": "what you paid", "best_by": "the best-by date", "received": "the day you got it",
               "low_stock": "the low-stock count", "new_badge": "the New label", "ingredients": "the ingredients",
               "variety": "the variety", "origin": "the origin", "claims": "the label claims", "allergens": "the allergens",
               "storage": "the storage", "customer_note": "your sentence for customers"}
MAX_NUMBER = 1_000_000


def _word_number(text):
    """0 to 99 spelled out ("nine", "twenty five", "twenty-five"), else None."""
    parts = text.replace("-", " ").split()
    if len(parts) == 1:
        return ONES.get(parts[0], TENS.get(parts[0]))
    if len(parts) == 2 and parts[0] in TENS and parts[1] in ONES and 1 <= ONES[parts[1]] <= 9:
        return TENS[parts[0]] + ONES[parts[1]]
    return None


def _whole(text):
    """A whole number from digits or words ("57", "fifty seven"), else None."""
    text = text.strip()
    return int(text) if re.fullmatch(r"\d{1,6}", text) else _word_number(text)


def _lead(text):
    """(number, the rest of the text) when the text starts with a number (12, 1,200, 2.5, twelve, twenty five, a, an), else None."""
    m = re.match(r"(\d{1,3}(?:,\d{3})+|\d+)(\.\d+)?(?=\s|$|[a-z])", text)
    if m:
        number = float(m.group(1).replace(",", "") + (m.group(2) or ""))
        if not 0 <= number <= MAX_NUMBER:  # includes non-finite values, before any integer conversion
            return None
        return (int(number) if number.is_integer() else number), text[m.end():].strip()
    tokens = [t for t in re.split(r"[\s-]+", text) if t]
    for size in (2, 1):
        if len(tokens) >= size:
            got = 1 if size == 1 and tokens[0] in ("a", "an") else _word_number(" ".join(tokens[:size]))
            if got is not None:
                return got, " ".join(tokens[size:])
    return None


def _parse_qty(text):
    """(number, unit or None) from a COMPLETE answer ("12 jars", "3 cases", "a dozen", "5 lb", "twelve"), else None."""
    t = _clean(text).lower().rstrip(".!").strip()
    if t in ("a dozen", "one dozen", "dozen"):
        return 12, "each"
    if t in ("half a dozen", "half dozen"):
        return 6, "each"
    got = _lead(t)
    if got is None or not 0 < got[0] <= MAX_NUMBER:
        return None
    number, rest = got
    if rest == "":
        return None if t in ("a", "an") else (number, None)
    unit = UNIT_WORDS.get(rest)
    if unit is None:  # a longer rest ("or maybe 24 jars", "jars of honey") is not a unit
        return None
    return (number * 12, "each") if unit == "dozen" else (number, unit)


def _parse_count(text):
    """A plain count (the low-stock number; 0 is allowed) from a COMPLETE answer, else None."""
    t = _clean(text).lower().rstrip(".!").strip()
    got = _lead(t) if t not in ("a", "an") else None
    if got is None or not 0 <= got[0] <= MAX_NUMBER or (got[1] and UNIT_WORDS.get(got[1]) in (None, "dozen")):
        return None
    return got[0]


def _parse_money(text):
    """"9.57" from a COMPLETE answer ("$9.57", "9.5", "9 dollars", "9 dollars and 57 cents", "nine dollars", "57 cents"), else None."""
    t = _clean(text).lower().rstrip(".!").strip()
    t = re.sub(r"\s+(?:each|apiece|per\s+(?:item|unit))$", "", t)
    cents = None
    if m := re.fullmatch(r"\$?\s*(\d{1,6})(?:\.(\d{1,2}))?(?:\s*(?:dollars?|bucks?|usd))?(?:\s*(?:each|apiece|(?:per|a|/)\s*[a-z]+))?", t):
        cents = int(m.group(1)) * 100 + int((m.group(2) or "0").ljust(2, "0"))
    elif m := re.fullmatch(r"\$?(.+?) (?:dollars?|bucks?)(?: (?:and )?(.+?) cents?)?", t):
        dollars, extra = _whole(m.group(1)), (_whole(m.group(2)) if m.group(2) else 0)
        cents = None if dollars is None or extra is None or extra > 99 else dollars * 100 + extra
    elif m := re.fullmatch(r"(.+?) cents?", t):
        got = _whole(m.group(1))
        cents = got if got is not None and 0 < got <= 99 else None
    return None if cents is None else "%d.%02d" % divmod(cents, 100)


SOLD_FILLER = frozenset({"sold", "per", "by", "the", "a", "an", "each"})
SOLD_KEYS = {"item": "item", "items": "item", "piece": "item", "pieces": "item", "unit": "item", "jar": "item", "bottle": "item",
             "box": "item", "loaf": "item", "tin": "item", "carton": "item", "tub": "item", "pack": "item",
             "pound": "pound", "lb": "pound", "lbs": "pound", "pounds": "pound", "weight": "pound",
             "bag": "bag", "bags": "bag", "bundle": "bundle", "bundles": "bundle", "bunch": "bundle", "bunches": "bundle"}


def _parse_sold_by(text):
    """item, pound, bag or bundle from a COMPLETE answer that names exactly one of them ("per pound", "by the bag", "each"), else None."""
    if any(c.isnumeric() for c in _clean(text)):  # "per 2 pounds" is not "per pound": a number is never erased
        return None
    words = re.sub(r"[^a-z ]", " ", _clean(text).lower()).split()
    rest = [w for w in words if w not in SOLD_FILLER]
    if not rest:
        return "item" if "each" in words else None
    return SOLD_KEYS.get(rest[0]) if len(rest) == 1 else None


def _parse_unit(text):
    if any(c.isnumeric() for c in _clean(text)):  # "jar2" is not "jar": a number is never erased
        return None
    words = re.sub(r"[^a-z ]", "", _clean(text).lower()).split()
    unit = UNIT_WORDS.get(words[0]) if len(words) == 1 else None
    return unit if unit and unit != "dozen" else None


def parse_day(text, today, *, past=False):
    """A date from his words (today, tomorrow, in 3 weeks, Dec 20, 12/20/2027, 2027-12-20), else None. With no year the
    next such day is taken for a best-by date, the last such day for a day he bought it (``past``)."""
    t = re.sub(r"(\d)(?:st|nd|rd|th)\b", r"\1", re.sub(r"[,.]", " ", _clean(text).lower())).strip()
    t = re.sub(r"^(?:on|by|about|around|best by|exp(?:ires?)?)\s+", "", t)
    if t in ("today", "now"):
        return today
    if t == "yesterday":
        return today - timedelta(days=1)
    if t == "tomorrow":
        return today + timedelta(days=1)
    m = re.fullmatch(r"in (\d{1,3}) (day|week|month)s?", t)
    if m:
        n = int(m.group(1))
        return today + timedelta(days=n * {"day": 1, "week": 7, "month": 30}[m.group(2)])
    year = month = day = None
    if (m := re.fullmatch(r"(\d{4})[-/ ](\d{1,2})[-/ ](\d{1,2})", t)):
        year, month, day = int(m[1]), int(m[2]), int(m[3])
    elif (m := re.fullmatch(r"(\d{1,2})[/-](\d{1,2})(?:[/-](\d{2,4}))?", t)):
        month, day = int(m[1]), int(m[2])
        year = int(m[3]) if m[3] else None
    elif (m := re.fullmatch(r"([a-z]{3})[a-z]* (\d{1,2})(?: (\d{2,4}))?", t)) and m[1] in MONTHS:
        month, day = MONTHS[m[1]], int(m[2])
        year = int(m[3]) if m[3] else None
    elif (m := re.fullmatch(r"(\d{1,2}) ([a-z]{3})[a-z]*(?: (\d{2,4}))?", t)) and m[2] in MONTHS:
        day, month = int(m[1]), MONTHS[m[2]]
        year = int(m[3]) if m[3] else None
    else:
        return None
    if year is not None and year < 100:
        year += 2000
    try:
        if year is not None:
            found = date(year, month, day)
            return found if 2000 <= found.year <= 2100 else None
        found = date(today.year, month, day)
        if past and found > today:
            found = date(today.year - 1, month, day)
        elif not past and found < today:
            found = date(today.year + 1, month, day)
        return found
    except ValueError:
        return None


def _text_value(key, text):
    """(value, None) for free words, or (None, the plain re-ask)."""
    words = _clean(text)
    if any(bad in words for bad in FORBIDDEN_TEXT) or INVISIBLE_RE.search(words):
        return None, "I can't use one of the characters in that. Could you say it again in plain words?"
    if len(words) > MAX_TEXT:
        return None, "That is a bit long for my notes. Could you shorten it?"
    if NONE_WORDS.match(words) and key in ("allergens", "claims"):
        return "none", None  # for these two, "none" is an answer; for the others it is nothing to note
    if NONE_WORDS.match(words):
        return "", None
    return words, None


def _fixed(key, words, today):
    """The fixed reading of one answer: ("ok", answers, extra), ("fail", why) when it is not a complete exact answer (the
    interpreter may try), or ("again", why) when it can never be used as it stands."""
    if key == "maker_site":
        from hass import maker_site  # lazy: the website reader is only needed for this question
        found = maker_site.addresses_in([words])
        if len(found) == 1:
            return ("ok", {key: found[0]}, {"maker_url": found[0]})
        return ("again", "I couldn't use that address." if not found else "I found more than one address there.")
    if key == "qty":
        parsed = _parse_qty(words)
        if parsed is None:
            return ("fail", "I didn't catch an exact number there.")
        out = {"qty": parsed[0]}
        if parsed[1]:
            out["qty_unit"] = parsed[1]
        return ("ok", out, {})
    if key == "qty_unit":
        unit = _parse_unit(words)
        return ("ok", {key: unit}, {}) if unit else ("fail", "I didn't catch that unit.")
    if key == "sold_by":
        got = _parse_sold_by(words)
        return ("ok", {key: got}, {}) if got else ("fail", "I didn't catch that.")
    if key in ("price", "cost"):
        got = _parse_money(words)
        return ("ok", {key: got}, {}) if got else ("fail", "I didn't catch an exact amount there.")
    if key in TEXT_FIELDS or key == "customer_note":
        value, why = _text_value(key, words)
        return ("ok", {key: value or None}, {}) if why is None else ("again", why)
    if key in ("best_by", "received"):
        found = parse_day(words, today, past=key == "received")
        return ("ok", {key: found.isoformat()}, {}) if found else ("fail", "I couldn't read that date. Something like Dec 20, 2027 works.")
    if key == "low_stock":
        got = _parse_count(words)
        return ("ok", {key: got}, {}) if got is not None else ("fail", "I didn't catch an exact number there.")
    if key == "new_badge":
        if YES_FULL.match(words):
            return ("ok", {key: True}, {})
        if NO_FULL.match(words):
            return ("ok", {key: False}, {})
        return ("fail", "I need a plain yes or no there.")
    raise KeyError(key)


def from_reader(key, out, today):
    """The answers the interpreter's exact value stands for, or None. Every value is checked here by the same rules as a typed
    answer: a vague, partial or out-of-range value is nothing."""
    value = out.get("value") if isinstance(out, dict) else None
    if value is None or isinstance(value, (list, tuple)):
        return None
    try:
        if key == "qty" and isinstance(value, dict):
            number, unit = value.get("number"), value.get("unit")
            if isinstance(number, bool) or not isinstance(number, (int, float)) or not 0 < number <= MAX_NUMBER:
                return None
            result = {"qty": int(number) if number == int(number) else number}
            if unit is not None:
                if _parse_unit(str(unit)) is None:
                    return None
                result["qty_unit"] = _parse_unit(str(unit))
            return result
        if key == "qty_unit":
            return {key: _parse_unit(str(value))} if _parse_unit(str(value)) else None
        if key == "sold_by":
            return {key: value} if value in SOLD_WORDS else None
        if key in ("price", "cost"):
            text = str(value).strip()
            return {key: _parse_money(text)} if re.fullmatch(r"\d{1,6}(?:\.\d{1,2})?", text) and _parse_money(text) else None
        if key in ("best_by", "received"):
            found = date.fromisoformat(str(value))
            return {key: found.isoformat()} if 2000 <= found.year <= 2100 else None
        if key == "low_stock":
            if isinstance(value, bool) or not isinstance(value, (int, float)) or not 0 <= value <= MAX_NUMBER:
                return None
            return {key: int(value) if value == int(value) else value}
        if key == "new_badge" and isinstance(value, bool):
            return {key: value}
    except (ValueError, TypeError):
        return None
    return None


def read(key, text, intake, *, today, asks=1, reader=None):
    """Read his answer to question ``key``. Returns one of

        ("abort", None)                              he wants to stop the whole thing
        ("again", reply)                             the answer cannot be used: the one question again, in plain words
        ("ok", {key: value, ...}, extra, note)       the intake answers it sets (a skipped question is ``{key: None}``), the slots
                                                     of the skill it also sets (``maker_url``), and a sentence to say first or None

    ``reader(key, words)`` is the interpreter for an answer the fixed reading cannot take: asked once (the first try only) and
    its value is checked again here. ``asks`` is how many times this question has been asked; the third unreadable answer
    is left blank, with a note, so he is never stuck.
    """
    words = _clean(text)
    if ABORT.match(words):
        return ("abort", None)
    if not words or SKIP.match(words):
        return ("ok", {key: None}, {}, None)
    status, *rest = _fixed(key, words, today)
    if status == "ok":
        return ("ok", rest[0], rest[1], None)
    if status == "fail" and reader is not None and asks <= 1 and key in INTERPRETED:
        try:
            got = from_reader(key, reader(key, words), today)
        except Exception:  # noqa: BLE001 - a reader that fails is no reader: he is asked again
            got = None
        if got:
            return ("ok", got, {}, None)
    if asks >= 3:  # asked three times and still not readable: that one is left blank and he is told, never guessed
        return ("ok", {key: None}, {}, f"I couldn't read that, so I left {BLANK_NAMES.get(key, 'that')} blank.")
    return ("again", rest[0])


# -- what Hass says back, and what is kept ----------------------------------------------------------------------------
def private_lines(intake) -> list:
    """The "kept private" summary shown beside the draft (every line is private; none of it goes on the website)."""
    got = intake if isinstance(intake, dict) else {}
    if not got:
        return []
    out = [PRIVATE_HEAD]
    qty, unit = got.get("qty"), got.get("qty_unit")
    if qty is not None:
        out.append(f"Bought: {_num_text(qty)}" + (f" {_q(_units(qty, unit))}" if unit else "") + ".")
    if got.get("sold_by"):
        out.append(f"Sold {SOLD_WORDS[got['sold_by']]}.")
    if got.get("price"):
        out.append(f"Price: {money_text(got['price'])} {_per(got)}.")
    if got.get("cost"):
        out.append(f"You paid: {money_text(got['cost'])} {_per(got)}.")
    for key in TEXT_FIELDS:
        if got.get(key):
            out.append(f"{LABELS[key]}: {_said(got[key])}.")
    if got.get("best_by"):
        out.append(f"Best by: {_day_text(got['best_by'])}.")
    if got.get("received"):
        out.append(f"Bought or received: {_day_text(got['received'])}.")
    if got.get("low_stock") is not None:
        out.append(f"Low on stock at: {_num_text(got['low_stock'])}.")
    if got.get("maker_site"):
        out.append(f"Maker's website: {_said(got['maker_site'])}.")
    if got.get("customer_note"):
        out.append(f"Your sentence for customers: {_said(got['customer_note'])}.")
    skipped = [LABELS.get(k, k.replace("_", " ")).split(" (")[0].lower() for k in ORDER if k in got and got[k] is None
               and k != "qty_unit"]
    if skipped:
        out.append("Skipped, so I left them blank: " + ", ".join(skipped) + ".")
    return out


def skipped_names(intake) -> list:
    return [k for k in ORDER if isinstance(intake, dict) and k in intake and intake[k] is None]


def record(draft_code, name, maker, shelf, product_id, photo, intake, now) -> dict:
    """The private intake record, as it is kept. Owner texts are never in it; only his answers to these questions."""
    intake = intake if isinstance(intake, dict) else {}
    answers = {k: v for k, v in intake.items() if k in ORDER}
    named = _clean((intake or {}).get("maker_named")) or None  # the maker he named when he skipped their town
    return {"schema": 1, "kind": "item.intake", "status": "saved", "draft": draft_code, "product": product_id, "name": name,
            "maker": maker or named, "maker_unknown": maker is None and named is None, "shelf": shelf, "photo": photo,
            "answers": answers, "skipped": skipped_names(intake),
            **({"photo_read": {"details": intake["photo_details"], "confirmed": intake.get("photo_confirmed"),
                               "claim_answers": intake.get("photo_claim_answers", {})}} if intake.get("photo_details") else {}),
            "claims_unverified": bool(answers.get("claims") and answers["claims"] != "none"
                                      or (intake.get("photo_details") or {}).get("printed_claims")),
            "drafted_at": now.isoformat() if hasattr(now, "isoformat") else str(now)}


def keep_pending(db, code, rec, now) -> None:
    """Keep the record beside the draft ``code`` until it is applied (the conversation's own private state)."""
    db.execute(PENDING)
    stamp = now.isoformat() if hasattr(now, "isoformat") else str(now)
    cutoff = (now - timedelta(days=KEEP_DAYS)).isoformat() if hasattr(now, "isoformat") else ""
    db.execute("DELETE FROM intake_pending WHERE created_at < ?", (cutoff,))
    db.execute("INSERT OR REPLACE INTO intake_pending(code, record_json, created_at) VALUES (?, ?, ?)",
               (code, json.dumps(rec, sort_keys=True, ensure_ascii=False), stamp))


def _append(sdir, row) -> None:
    path = os.path.join(str(sdir), STORE)
    fd = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_APPEND | os.O_NOFOLLOW, 0o600)
    with os.fdopen(fd, "a", encoding="utf-8") as out:
        out.write(json.dumps(row, sort_keys=True, ensure_ascii=False) + "\n")


def save_applied(db, sdir, code, now):
    """The draft ``code`` was applied: the waiting record becomes one line of ``item-intake.jsonl``. Returns the row or None."""
    try:
        db.execute(PENDING)
        found = db.execute("SELECT record_json FROM intake_pending WHERE code = ?", (code,)).fetchone()
        if found is None:
            return None
        row = json.loads(found["record_json"] if hasattr(found, "keys") else found[0])
        row["applied_at"] = now.isoformat() if hasattr(now, "isoformat") else str(now)
        _append(sdir, row)
        db.execute("DELETE FROM intake_pending WHERE code = ?", (code,))
        return row
    except (OSError, sqlite3.Error, ValueError):
        return None  # best effort: a record that cannot be written never undoes a change that was applied


def mark_undone(sdir, code, now):
    """The change ``code`` was undone: if it had a saved record, one more line says so; the earlier line is never edited."""
    path = os.path.join(str(sdir), STORE)
    try:
        with open(path, encoding="utf-8") as src:
            saved = any(json.loads(line).get("draft") == code and json.loads(line).get("status") == "saved" for line in src if line.strip())
        if not saved:
            return None
        _append(sdir, {"schema": 1, "kind": "item.intake", "status": "undone", "draft": code,
                       "undone_at": now.isoformat() if hasattr(now, "isoformat") else str(now)})
    except (OSError, ValueError):
        return None
    return True
