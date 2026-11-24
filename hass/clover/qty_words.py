"""Parse one local inventory sentence; never resolve an item or write to the till."""
from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal
import re

from hass.skills.item_intake import _word_number


@dataclass(frozen=True)
class CountIntent:
    mode: str
    quantity: Decimal
    unit: str | None
    query: str


_DIGITS = re.compile(r"[0-9]+(?:\.[0-9]{1,3})?")
_SET = re.compile(r"set (?!(?:the )?price\b)(?:the count of )?(.+?) to (.+)")
_ARRIVAL = re.compile(r"(?:(?:we )?(?:got|received)) (.+)")
_COUNT_PREFIX = re.compile(r"^(?:there (?:are|is)|we have) ")
_COUNT_SUFFIX = re.compile(r"(?: on the shelf(?: now)?| now)$")
_QUESTION = re.compile(r"^(?:am|are|is|can|could|do|does|did|have|has|how|what|when|where|which|who|will|would)\b")
_UNCLEAR_QUERY = re.compile(
    r"\b(?:about|around|approximately|roughly|some|few|or|dozen|hundred|thousand|million|"
    r"dollars?|cents?|pounds?|lbs?)\b|\b(?:case of|came in)\b"
)
# A price, two products joined by a word, or a leading distance/duration is not
# one product name; refuse so the message takes the normal reading instead.
_NOT_ONE_PRODUCT = re.compile(
    r"\b(?:bucks|euros?|quid|pence|pennies|and|plus)\b|&"
    r"|^(?:miles?|km|kilometers?|kilometres?|foot|feet|inch(?:es)?|hours?|minutes?)\b"
)
# A set sentence that names the website or its photo/page is a site edit, not stock.
_SITE_WORDS = re.compile(r"\b(?:website|photos?|pictures?|images?|pages?|listings?)\b")


def _amount(text: str) -> tuple[Decimal, str | None, str] | None:
    """Consume one leading quantity, leaving any following product text intact."""
    first, _, rest = text.partition(" ")
    fractional = "." in first
    if _DIGITS.fullmatch(first):
        quantity = Decimal(first)
    elif first == "a" and (rest == "dozen" or rest.startswith("dozen ")):
        quantity = Decimal(1)
    else:
        # Prefer a complete compound ("twenty five") over its first word.
        second, _, tail = rest.partition(" ")
        number = _word_number(f"{first} {second}") if second else None
        if number is not None:
            rest = tail
        else:
            number = _word_number(first)
        if number is None:
            return None
        quantity = Decimal(number)

    if rest == "dozen" or rest.startswith("dozen "):
        if fractional:
            return None
        quantity = Decimal(int(quantity) * 12)  # Exact even under a low-precision Decimal context.
        rest = rest.removeprefix("dozen").lstrip()

    unit, _, tail = rest.partition(" ")
    if unit in ("lb", "lbs", "pounds"):
        return quantity, "lb", tail
    return None if fractional else (quantity, None, rest)


def _intent(mode: str, amount: tuple[Decimal, str | None, str] | None,
            query: str | None = None) -> CountIntent | None:
    if amount is None:
        return None
    quantity, unit, rest = amount
    if query is None:
        if mode == "add":
            rest = rest.removeprefix("more ")
        query = rest.removeprefix("of ")
    elif rest:  # Label-first syntax must end at the quantity (and optional unit).
        return None

    query = re.sub(r"^(?:the|an?) ", "", query)
    # Reject leftover quantity words as well as digit-bearing tokens; neither
    # belongs to the product name when parsing an unambiguous till count.
    words = re.split(r"[ '\-]", query)
    if (_UNCLEAR_QUERY.search(query) or _NOT_ONE_PRODUCT.search(query)
            or (mode == "set" and _SITE_WORDS.search(query))
            or any(not word.isalpha() or _word_number(word) is not None for word in words)):
        return None
    return CountIntent(mode, quantity, unit, query)


def parse(text: str) -> CountIntent | None:
    """Recognize bounded, single-product count, arrival, and explicit set forms."""
    # Unlike chat._clean, do not erase line breaks or question punctuation.
    if not isinstance(text, str) or len(text) > 200 or text.splitlines() != [text] or "?" in text:
        return None
    clean = " ".join(text.lower().replace("’", "'").replace("‘", "'").split()).rstrip(".!").rstrip()
    if _QUESTION.match(clean):
        return None
    if clean.startswith("set "):
        match = _SET.fullmatch(clean)
        return _intent("set", _amount(match[2]), match[1]) if match else None
    if ":" in clean:
        label, _, amount = clean.partition(":")
        return _intent("count", _amount(amount.strip()), label.rstrip())
    if match := _ARRIVAL.fullmatch(clean):
        return _intent("add", _amount(match[1]))
    if clean.endswith(" came in"):
        return _intent("add", _amount(clean.removesuffix(" came in")))
    body = _COUNT_SUFFIX.sub("", _COUNT_PREFIX.sub("", clean))
    amount = _amount(body)
    if amount and not amount[2].startswith("more "):
        return _intent("count", amount)
    return None
