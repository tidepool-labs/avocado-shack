"""Local-only finance provenance and number screens. Never serialize scan results in receipts."""
from dataclasses import dataclass, field
from decimal import Decimal
import re
import unicodedata

from hass.content_model import valid_selling_price
from hass.skills import item_intake as intake

_WORD = '(?:' + '|'.join((*intake.ONES, *intake.TENS)) + ')'
_NUMBER = re.compile(
    rf'half(?:[ -]+a)?[ -]+dozen|(?:{_WORD}[ -]+|a )?\bdozen\b|'
    rf'\d{{1,3}}(?:,\d{{3}})+(?:\.\d+)?|\d+(?:\.\d+)?|'
    rf'\b{_WORD}(?:[ -]+{_WORD})?\b', re.I)
_MONEY = re.compile(r'[$¢€£¥]|\b(?:cents?|dollars?|bucks?|usd)\b|(?<!\d)\d+\.\d{2}(?!\d)', re.I)
_UNCLEAR = re.compile(r'\b(?:or|maybe|about|around|roughly|approximately)\b', re.I)
_UNPLACED = re.compile(r'\b(?:half|halves|quarters?|couple|hundred|thousand|million|billion|trillion|point|grand|score|gross|pair)\b', re.I)


@dataclass(frozen=True)
class Number:
    start: int
    end: int
    amounts: frozenset
    digits: bool


def values(text, *, finance_clause=False):
    """Read numbers with offsets; outside a finance clause, also screen ambiguous component readings."""
    found = []
    for m in _NUMBER.finditer(text):
        amounts: set[int | Decimal]
        token = m[0].lower()
        digits = token[0].isdecimal()
        if digits:
            amounts = {Decimal(token.replace(',', ''))}
        elif token.endswith('dozen'):
            count, _ = intake._parse_qty(token) or (None, None)
            amounts = {Decimal(str(count))} if count is not None else set()
        elif (number := intake._word_number(token)) is not None:
            amounts = {number}
        else:
            left, right = (intake._word_number(w) for w in re.split('[ -]+', token))
            amounts = set() if left is None or right is None else {left, right}
            if left is not None and right is not None and left < 10 and right >= 10:
                if finance_clause:
                    amounts.clear()  # a single shorthand money value, not independent quantities
                amounts.update({left * 100 + right, Decimal(left) + Decimal(right) / 100})
        found.append(Number(*m.span(), frozenset(amounts), digits))
    return tuple(found)


def problem(text, private=(), *, permitted=(), digits_allowed=False):
    """Return a fixed reason, never the detected text or amount. Permits are exact character ranges."""
    normalized = unicodedata.normalize('NFKC', text)
    if _MONEY.search(normalized):
        return 'money'
    # Do not transfer character offsets through normalization (ligatures etc.).
    if normalized != text and any(c.isnumeric() for c in normalized):
        return 'number-unclear'
    numbers = values(text)
    idioms = literal_spans(text, ['half-and-half', 'half and half'])
    if ((numbers and _UNCLEAR.search(text)) or any(not n.amounts for n in numbers)
            or any(not any(a <= m.start() < b for a, b in (*idioms, *((n.start, n.end) for n in numbers)))
                   for m in _UNPLACED.finditer(text))
            or any(c.isnumeric() and not c.isdecimal() for c in text)):
        return 'number-unclear'
    for n in numbers:
        if any(a <= n.start and n.end <= b for a, b in permitted):
            continue
        if n.amounts.intersection(private):
            return 'private-number'
        if n.digits and not digits_allowed:
            return 'unsupported-number'
    return None


def literal_spans(text, literals):
    """Exact normalized OCR phrases, never a substring of another token."""
    return tuple(m.span() for value in literals if value for m in re.finditer(
        r'(?<!\w)' + re.escape(value) + r'(?!\w)', text, re.I))


def picture_problem(read, source_read, label_words, private=()):
    """Unchanged label tokens can be public; a sticker or unreadable picture cannot qualify."""
    if not isinstance(read, str) or not isinstance(source_read, str):
        return 'picture-unreadable'
    read, source_read = (' '.join(text.split()) for text in (read, source_read))
    confirmed = [' '.join(word.split()) for word in label_words if isinstance(word, str)
                 and literal_spans(source_read, [' '.join(word.split())])]
    return problem(read, private, permitted=literal_spans(read, confirmed), digits_allowed=True)


@dataclass(frozen=True)
class Finance:
    public_words: str = field(repr=False)
    selling_price: str | None = None
    price_span: tuple[int, int] | None = None
    private: frozenset = field(default=frozenset(), repr=False)
    has_cost: bool = False
    has_qty: bool = False


_BASIS = re.compile(r'(?:(?:/\s*|\s+(?:per|a)\s+)([a-z]+)|\s+(each|apiece|items?|lbs?|pounds?|baskets?))$', re.I)
_COST_CUE = re.compile(r'\b(?:bought|purchased|paid|costs?|wholesale)\b', re.I)


def finance(caption, *, answer_unit=None, local_answers=None):
    """Keep private numbers local. A verified local fallback may add safety tokens, not establish a price span.

    For a direct reply to a price question, `answer_unit` is the already resolved each/per-lb basis.
    A numeric amount must still be present in that reply and readable by the real money parser.
    """
    _, parsed = intake.caption_answers(caption)
    extra = intake.commerce_answers(local_answers)
    costs = {a['cost'] for a in (parsed, extra) if 'cost' in a}
    counts = {a['qty'] for a in (parsed, extra) if 'qty' in a}
    prices, public_parts = [], []
    for start, end, clause in intake.caption_spans(caption):
        part = clause.strip().rstrip('.!').strip()
        remainder, atoms = intake.caption_answers(part)
        if quantity := re.fullmatch(r'(?:got|have|qty|quantity|stock)\s*:?\s+(.+)', part, re.I):
            count = intake._parse_qty(quantity[1])
            if count and type(count[0]) is int and 0 <= count[0] <= 100000:
                atoms['qty'], remainder = count[0], ''
        if 'cost' in atoms:
            costs.add(atoms['cost'])
        if 'qty' in atoms:
            counts.add(atoms['qty'])
        priced = re.sub(r'\s+retail$', '', part, flags=re.I) if part.startswith('$') else part
        basis = _BASIS.search(priced)
        unit = answer_unit
        if basis:
            stated = (basis[1] or basis[2]).lower()
            unit = 'each' if stated == 'apiece' else {'item': 'each', 'pound': 'per lb'}.get(intake._parse_sold_by(stated) or '')
        amount = atoms.get('price')
        if start == 0 and end == len(caption) and answer_unit and not ({'price', 'cost'} & atoms.keys()):
            direct = part[:basis.start()].strip() if basis else part
            if found := intake._parse_money(direct):
                amount, remainder = found, ''
                if 'qty' not in extra:
                    counts.clear()  # the entire turn is a direct answer to the price question
        if amount and unit in {'each', 'per lb'} and 'cost' not in atoms and not intake.unresolved_finance(remainder):
            prices.append((f'{amount} {unit}', (start, end)))
        if remainder:
            public_parts.append(remainder)

    private = {n for cost in costs for n in (Decimal(cost), Decimal(cost) * 100)} | counts
    public = '; '.join(public_parts)
    unresolved = intake.unresolved_finance(public)
    if unresolved:
        # Unparsed finance is never a public span, even on reader failure.
        private.update(n for part in public_parts if intake.unresolved_finance(part)
                       for v in values(part, finance_clause=bool(_COST_CUE.search(part))) for n in v.amounts)
    price, span = prices[0] if len(prices) == 1 and not unresolved else (None, None)
    if price is None or not valid_selling_price(price) or (parsed.get('price') is not None and not price.startswith(parsed['price'] + ' ')):
        price, span = None, None
    return Finance(intake.without_unresolved_finance(public), price, span, frozenset(private),
                   bool(costs), bool(counts))
