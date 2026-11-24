"""HASS-NL-1: pre-processing hints for the interpreter request.

make_hinter(content) returns hinter(text, today, aliases) -> dict: facts the shop's own software works out from the owner's
words, the catalog and the Pacific calendar, so a small model does not have to guess them. The interpreter request carries
them as "hints"; the prompt tells the model to use them and that a hint never supplies a claim, a price or a quantity.

  products   each product phrase the owner wrote, resolved to ONE product ("is") or listed as "ambiguous" candidates
  makers     a maker named on its own, with its products
  shelves    a whole shelf (bread, meat, dairy ...) with its active products, so the model drafts one change each or asks
  hikes      a hike or route idea named in the message, or the scheduled hikes on a weekday the owner named
  dates      today/tomorrow/weekday/"the 29th"/"dec 5"/a named US holiday (Thanksgiving ...) worked out in Pacific time (an unclear day lists both readings)
  times      explicit clock times as HH:MM; numbers   spoken numbers as digits; price   money words and amounts

Pure and deterministic: no clock, no I/O, no network. Anything the matching cannot settle is left out, never guessed; a
hint that is wrong can only make the model ask, because the registry, editor and claim checks still run on every draft.
"""
from __future__ import annotations

import difflib
import re
import unicodedata
from datetime import date, timedelta

MAX_LIST, MAX_PHRASE_MATCHES, SHELF_DRAFT_MAX = 8, 25, 6
SHELVES = {"fruit": "fruit", "vegetable": "vegetables", "veggie": "vegetables", "dairy": "dairy", "egg": "eggs", "meat": "meat",
           "pantry": "pantry", "drink": "drinks", "bread": "bread", "flower": "flowers"}
NAME_STOP = frozenset("a an and at by de for from in of on or the to with".split())
MSG_STOP = frozenset("""a about actually after again all also am an and any anymore are as at back be because been before being but by
 can cancel change check checked could couldnt did do does dont down for from gave get go going gone got had has have hey hi
 done em hide hiding him her his how i if im in into is it its ive just kill know let lets like limited little look low made make
 lol theyre theres whats
 many me more my need new no not now of off ok okay on one only or other our out over pls please pull put really remove
 removing rn said say see set should show shown site so sold some stop take takes than that thats the their them then
 there these they this those through to today tomorrow tonight too u up us use want was we well went were what when where
 which who why will with would wont ya yeah yes you your youre hike hikes walk walks listing mark marked available
 availability supply stock running shelf shelves shelfs""".split())
WORD_NUMBERS = {"zero": 0, "one": 1, "two": 2, "three": 3, "four": 4, "five": 5, "six": 6, "seven": 7, "eight": 8, "nine": 9, "ten": 10,
                "eleven": 11, "twelve": 12, "thirteen": 13, "fourteen": 14, "fifteen": 15, "sixteen": 16, "seventeen": 17,
                "eighteen": 18, "nineteen": 19, "twenty": 20, "thirty": 30, "forty": 40, "fifty": 50, "sixty": 60, "dozen": 12}
WEEKDAYS = {"monday": 0, "mon": 0, "tuesday": 1, "tue": 1, "tues": 1, "wednesday": 2, "wed": 2, "thursday": 3, "thu": 3, "thur": 3,
            "thurs": 3, "friday": 4, "fri": 4, "saturday": 5, "sat": 5, "sunday": 6, "sun": 6}
WEEKDAY_NAMES = ("Monday", "Tuesday", "Wednesday", "Thursday", "Friday", "Saturday", "Sunday")
MONTHS = {"jan": 1, "january": 1, "feb": 2, "february": 2, "mar": 3, "march": 3, "apr": 4, "april": 4, "may": 5, "jun": 6, "june": 6,
          "jul": 7, "july": 7, "aug": 8, "august": 8, "sep": 9, "sept": 9, "september": 9, "oct": 10, "october": 10, "nov": 11,
          "november": 11, "dec": 12, "december": 12}
HIKE_WORD_RE = re.compile(r"\b(?:hikes?|walks?|outings?|trails?|routes?|trek|meet(?:ing)?\s?(?:up|point))\b")
RANGE_RE = re.compile(r"\b(\d{1,2})(?::(\d{2}))?\s*([ap]\.?m\.?)?\s*(?:to|-|\u2013|until|till|through)\s*(\d{1,2})(?::(\d{2}))?\s*([ap]\.?m\.?)?(?!\d)")
TOKEN_RE = re.compile(r"[a-z0-9]+(?:'[a-z]+)?")
PRICE_CUE_RE = re.compile(r"\$|\b(?:bucks?|dollars?|cents?|prices?|priced|pricing|charg\w*|costs?|mark(?:ed)?\s?down|markdown|discount\w*|sale|each|per\s(?:lb|pound))\b|%\s*off")
MONEY_RE = re.compile(r"\$\s?(\d+(?:\.\d{1,2})?)|\b(\d+(?:\.\d{1,2})?)\s*(?:bucks?|dollars?)\b|\b(\d+\.\d{2})\b")
TIME_RE = re.compile(r"\b(\d{1,2})(?::(\d{2}))?\s*([ap])\.?m\b\.?|\b([01]?\d|2[0-3]):([0-5]\d)\b|\b(noon|midnight)\b")
ORDINAL_RE = re.compile(r"\b(\d{1,2})(?:st|nd|rd|th)\b")
MONTH_DAY_RE = re.compile(r"\b(" + "|".join(sorted(MONTHS, key=len, reverse=True)) + r")\.?\s+(\d{1,2})(?:st|nd|rd|th)?\b")
DAY_MONTH_RE = re.compile(r"\b(\d{1,2})(?:st|nd|rd|th)?\s+(?:of\s+)?(" + "|".join(sorted(MONTHS, key=len, reverse=True)) + r")\b(?:\.(?=(?:,\s*|\s+)(?:'\d{2}(?![\d:])|'\d+(?!:)|\d{3,}(?!:))))?")
SLASH_RE = re.compile(r"(?<!/)\b(1[0-2]|0?[1-9])/([0-3]?\d)\b(?:/(\d+))?")  # m/d or m/d/yy(yy); a year-first 2027/12/5 is not read
ISO_RE = re.compile(r"\b(\d{4})-(\d{2})-(\d{2})\b")
YEAR_RE = re.compile(r"(?:,\s*|\s+)(?:'(\d{2})|(\d{4}))(?![\d:])")  # a year the owner wrote right after a month and day
BAD_YEAR_RE = re.compile(r"(?:,\s*|\s+)(?:\d{3,}|'\d+)(?!\d)(?!:)(?!\s*[ap]\.?m\b)")  # three or more digits after a month and day that YEAR_RE did not take, and that are not a clock time
WEEKDAY_RE = re.compile(r"\b(?:(this|next|last|coming|on)\s+)?(" + "|".join(sorted(WEEKDAYS, key=len, reverse=True)) + r")s?\b")
RELATIVE_RE = re.compile(r"\b(today|tonight|tomorrow|tmrw|tmr|yesterday|day after tomorrow)\b")
IN_RE = re.compile(r"\bin\s+(\d{1,2}|" + "|".join(WORD_NUMBERS) + r")\s+(day|week)s?\b")
PREFIX_MIN, FUZZY_MIN, FUZZY_CUTOFF = 4, 5, 0.8
SLIPS = {"leak": "leek", "egs": "egg", "agg": "egg", "morale": "morel", "chevy": "chevre", "tumeric": "turmeric", "bok": "bok",
         "avacado": "avocado", "guac": "guacamole", "mango": "mango", "bluberei": "blueberry", "blubereis": "blueberry"}  # voice-to-text and phone slips the spelling match cannot reach


def fold(text) -> str:
    text = unicodedata.normalize("NFKD", str(text)).replace("\u2019", "'").replace("\u2018", "'")
    return "".join(c for c in text if not unicodedata.combining(c)).lower()


def stem(token: str) -> str:
    if "'" in token: token = token.split("'")[0]
    if len(token) > 4 and token.endswith("ies"): return token[:-3] + "y"
    if len(token) > 3 and token.endswith("oes"): return token[:-2]
    if len(token) > 3 and token.endswith(("ches", "shes", "sses", "xes")): return token[:-2]
    if len(token) > 3 and token.endswith("s") and not token.endswith(("ss", "us")): return token[:-1]
    return token


def tokens(text, stop=NAME_STOP) -> list:
    return [stem(t) for t in TOKEN_RE.findall(fold(text)) if t not in stop and stem(t) not in stop]


class _Index:
    def __init__(self, content):
        self.products = []
        for p in content.products if isinstance(getattr(content, "products", None), list) else []:
            if not isinstance(p, dict) or not isinstance(p.get("id"), str): continue
            name = tokens(p.get("name") or "")
            desc = tokens(p.get("description") or "") if isinstance(p.get("description"), str) else []
            if name: self.products.append({"id": p["id"], "name": str(p.get("name")), "tokens": name, "set": frozenset(name), "head": name[-1],
                                           "desc": frozenset(desc), "status": p.get("status"), "category": p.get("category"), "maker": p.get("producerKey"),
                                           "brand": p.get("brand") if isinstance(p.get("brand"), str) else ""})
        self.makers = []
        makers = content.makers if isinstance(getattr(content, "makers", None), dict) else {}
        for key, m in makers.items():
            name = tokens(m.get("name") if isinstance(m, dict) and m.get("name") else key)
            if name: self.makers.append({"key": str(key), "name": str(m.get("name") if isinstance(m, dict) and m.get("name") else key), "tokens": name})
        community = getattr(content, "community", None)
        community = community if isinstance(community, dict) else {}
        self.hikes = [e for e in community.get("events") or [] if isinstance(e, dict) and isinstance(e.get("id"), str)]
        self.ideas = [r for r in community.get("routeIdeas") or [] if isinstance(r, dict) and isinstance(r.get("id"), str)]
        store = getattr(content, "store", None)
        hours = store.get("hours") if isinstance(store, dict) else None
        self.hours = [h for h in hours if isinstance(h, str)] if isinstance(hours, list) else []
        self.vocab = {t for p in self.products for t in p["tokens"]} | {t for m in self.makers for t in m["tokens"]} \
            | {t for e in (*self.hikes, *self.ideas) for t in tokens(e.get("title") or "")}
        self.vocab |= set(SHELVES)
        self.vocab_list = sorted(self.vocab)

    def canon(self, token):
        """(vocabulary token, guessed): the token itself, a unique longer word it starts, or a close spelling; else (None, False)."""
        if token in self.vocab: return token, False
        if SLIPS.get(token) in self.vocab: return SLIPS[token], True
        if len(token) >= PREFIX_MIN - 1:
            longer = [v for v in self.vocab_list if v.startswith(token)]
            if len(longer) == 1: return longer[0], True
            if longer: return None, False  # several words start this way (lem: lemon, lemonade): the owner has not chosen, so no hint
        if len(token) >= FUZZY_MIN:
            close = difflib.get_close_matches(token, self.vocab_list, n=2, cutoff=FUZZY_CUTOFF)
            # two words equally close (peich: peach, perch) are a tie, not a unique correction: leave the token unresolved
            if len(close) == 2 and difflib.SequenceMatcher(None, close[0], token).ratio() == difflib.SequenceMatcher(None, close[1], token).ratio():
                return None, False
            if close: return close[0], True
        return None, False


def _entry(p) -> dict:
    out = {"id": p["id"], "name": p["name"]}
    if p["status"] not in (None, "active"): out["status"] = p["status"]
    return out


def _decide(span, products, *, prefer_ordered=False):
    """('is'|'ambiguous', [products]) for a span of vocabulary tokens, or None when no product contains it."""
    want = frozenset(span)
    contains = [p for p in products if want <= p["set"]]
    exact = [p for p in contains if p["set"] == want]
    if prefer_ordered:
        ordered = [p for p in exact if p["tokens"] == span]
        if ordered:
            return ("is" if len(ordered) == 1 else "ambiguous"), ordered
    kind = [p for p in contains if p["head"] == span[-1] and p not in exact]
    cands = exact + kind
    if not cands:  # only a word inside names (or in none): products whose description uses the word are candidates too (coffee)
        contains = contains + [p for p in products if p not in contains and want <= p["desc"]]
    if not contains: return None
    if len(exact) == 1: return "is", exact  # AV2007-12: one whole name that is exactly what was said beats the kind siblings (raspberries / golden raspberries)
    if not cands: return ("is", contains) if len(contains) == 1 else ("ambiguous", contains)
    if len(cands) == 1:  # one product of that kind; a same-shelf, same-maker sibling that merely mentions the word makes it unclear
        lone = cands[0]
        siblings = [p for p in contains if p not in cands and p["maker"] == lone["maker"] and p["category"] == lone["category"]]
        return ("ambiguous", cands + siblings) if siblings else ("is", cands)
    return "ambiguous", cands


def _spans(words, index, alias_seqs, guessed):
    """Greedy, longest first: non-overlapping (start, end, kind, data) over the vocabulary tokens of one run of words."""
    found, taken = [], [False] * len(words)
    options = []
    for i in range(len(words)):
        for j in range(len(words), i, -1):
            span = words[i:j]
            if any(w is None for w in span): continue
            options.append((j - i, 0, i, j, span))
    options.sort(key=lambda o: (-o[0], o[1], o[2]))
    for length, _, i, j, span in options:
        if any(taken[i:j]): continue
        raw = tuple(w for w in span)
        alias = next((a for a in alias_seqs if a[0] == raw), None)
        if alias is not None:
            found.append((i, j, "alias", alias[1]))
        elif len(raw) == 1 and raw[0] in SHELVES:
            found.append((i, j, "shelf", None))
        else:
            # A spelling correction must not break a tie between whole names.
            decision = _decide(span, index.products, prefer_ordered=not any(guessed[i:j]))
            maker = next((m for m in index.makers if m["tokens"] == list(raw)), None)
            if maker is not None and (decision is None or decision[0] == "ambiguous" or len(raw) < max(len(p["tokens"]) for p in decision[1])):
                found.append((i, j, "maker", maker))
            elif decision is not None and not (len(raw) == 1 and len(decision[1]) > MAX_PHRASE_MATCHES):
                found.append((i, j, decision[0], decision[1]))
            else:
                continue
        for k in range(i, j): taken[k] = True
    return sorted(found)


def _shelf_of(span):
    return SHELVES.get(span[0]) if len(span) == 1 else None


def phrase_hints(text, index, aliases) -> dict:
    """products / makers / shelves for the phrases in ``text``."""
    tokens_ = [stem(t) for t in TOKEN_RE.findall(fold(text))]
    raw = TOKEN_RE.findall(fold(text))
    alias_seqs = []
    for a in aliases or []:
        if isinstance(a, dict) and isinstance(a.get("name"), str):
            seq = tuple(tokens(a["name"], stop=NAME_STOP | {"the"}))
            if seq: alias_seqs.append((seq, a))
    alias_words = {w for seq, _ in alias_seqs for w in seq}  # an alias word is read as written, in the catalog or not
    canon, guessed = [], []
    for original, token in zip(raw, tokens_):
        if original in MSG_STOP or token in MSG_STOP or original in NAME_STOP or token in NAME_STOP:
            canon.append("")
            guessed.append(False)
            continue
        word, guess = (token, False) if token in alias_words else index.canon(token)
        canon.append(word)
        guessed.append(guess)
    products, makers, shelves, said = [], [], [], {}
    run = []
    for k in range(len(canon) + 1):
        if k < len(canon) and canon[k] != "":
            run.append(k)
            continue
        if run:
            words = [canon[x] for x in run]
            for i, j, kind, data in _spans(words, index, alias_seqs, [guessed[x] for x in run]):
                phrase = " ".join(raw[x] for x in run[i:j])
                span = words[i:j]
                fuzzy = any(guessed[x] for x in run[i:j])
                if kind == "shelf":
                    shelf = SHELVES[span[0]]
                    members = [p for p in index.products if p["category"] == shelf and p["status"] == "active"]
                    if len(members) == 1: products.append({"said": phrase, "is": _entry(members[0])})
                    elif members: shelves.append({"said": phrase, "shelf": shelf, "count": len(members), "products": [_entry(p) for p in members][:MAX_LIST * 3]})
                    continue
                if kind == "maker":
                    members = [p for p in index.products if p["maker"] == data["key"]]
                    makers.append({"said": phrase, "key": data["key"], "name": data["name"], "products": [_entry(p) for p in members][:MAX_LIST],
                                   **({"more": len(members) - MAX_LIST} if len(members) > MAX_LIST else {})})
                elif kind == "alias":
                    pid_ = data.get("id")
                    hit = next((p for p in index.products if p["id"] == pid_), None) if data.get("kind") == "product" else None
                    if hit: products.append({"said": phrase, "is": _entry(hit), "alias": True})
                    elif data.get("kind") == "maker": makers.append({"said": phrase, "key": data.get("id"), "alias": True})
                elif kind == "is":
                    products.append({"said": phrase, "is": _entry(data[0]), **({"spelling": "guessed"} if fuzzy else {})})
                else:
                    products.append({"said": phrase, "ambiguous": [_entry(p) for p in data][:MAX_LIST], **({"more": len(data) - MAX_LIST} if len(data) > MAX_LIST else {}),
                                     **({"spelling": "guessed"} if fuzzy else {})})
        run = []
    out = {}
    if products: out["products"] = products[:MAX_LIST]
    if makers: out["makers"] = makers[:MAX_LIST]
    if shelves: out["shelves"] = shelves[:3]
    return out


# -- hikes -------------------------------------------------------------------------------------------------------------
def hike_hints(text, index, today: date, weekday_hits) -> dict:
    words = {stem(t) for t in TOKEN_RE.findall(fold(text)) if t not in MSG_STOP and t not in NAME_STOP}
    out = []
    for e in index.hikes:
        title = set(tokens(e.get("title") or "")) - {"walk", "hike"}
        if title and title <= words:
            out.append({"hike": e["id"], "title": e.get("title"), "startsAt": e.get("startsAt"), "status": e.get("status")})
    ideas = []
    for r in index.ideas:
        title = set(tokens(r.get("title") or "")) - {"walk", "hike"}  # same reduced set for both tests, like events
        if title and title <= words: ideas.append({"routeIdea": r["id"], "title": r.get("title")})
    rows = []
    for name, wd in weekday_hits if HIKE_WORD_RE.search(fold(text)) or out or ideas else ():  # a weekday alone is not about hikes
        on = [e for e in index.hikes if e.get("status") == "scheduled" and _weekday_of(e.get("startsAt")) == wd]
        if on: rows.append({"said": name, "scheduled hikes": [{"hike": e["id"], "title": e.get("title"), "startsAt": e.get("startsAt")} for e in on][:MAX_LIST]})
    result = {}
    if out or ideas: result["named"] = (out + ideas)[:MAX_LIST]
    if rows: result["onThatWeekday"] = rows
    return result


def _weekday_of(starts_at):
    try: return date.fromisoformat(str(starts_at)[:10]).weekday()
    except ValueError: return None


# -- dates, times, numbers, prices ---------------------------------------------------------------------------------------
def _shift(d: date, days: int):
    """``d`` moved by ``days``, or None when that day is outside the calendar (date.min..date.max): a hint is never clamped or guessed."""
    try: return d + timedelta(days=days)
    except OverflowError: return None


def _next_weekday(today: date, wd: int, include_today=False):
    delta = (wd - today.weekday()) % 7
    return _shift(today, delta if (delta or include_today) else 7)


_ORD_UNITS = ("first", "second", "third", "fourth", "fifth", "sixth", "seventh", "eighth", "ninth", "tenth", "eleventh", "twelfth", "thirteenth", "fourteenth",
              "fifteenth", "sixteenth", "seventeenth", "eighteenth", "nineteenth")
ORDINAL_WORDS = {w: i + 1 for i, w in enumerate(_ORD_UNITS)}  # AV2007-11: spoken calendar days 1-31, a closed list (no general number parser)
ORDINAL_WORDS.update({"twentieth": 20, "thirtieth": 30})
for _tens, _base in (("twenty", 20), ("thirty", 30)):
    for _i, _w in enumerate(_ORD_UNITS[:9] if _base == 20 else _ORD_UNITS[:1]):
        ORDINAL_WORDS[f"{_tens} {_w}"] = _base + _i + 1
ORDINAL_WORD_RE = re.compile(r"(?<![\w-])(" + "|".join(sorted((w.replace(" ", r"[ -]") for w in ORDINAL_WORDS), key=len, reverse=True)) + r")(?![\w-])")
ORD_BAD_BEFORE_RE = re.compile(r"(?:zero|minus|negative|twenty|thirty|forty|fifty|sixty|seventy|eighty|ninety|hundred|\d)[ -]$")
ORD_BEFORE_RE = re.compile(r"(?:\bthe|\b(?:" + "|".join(sorted(WEEKDAYS, key=len, reverse=True)) + r")s?\.?(?:,?\s+the)?|\b(?:" + "|".join(sorted(MONTHS, key=len, reverse=True)) + r")\.?)[\s,]+$")
ORD_AFTER_RE = re.compile(r"\s+(?:of\s+)?(?:" + "|".join(sorted(MONTHS, key=len, reverse=True)) + r")\b")


def _ordinal_suffix(n):
    return "th" if 10 <= n % 100 <= 20 else {1: "st", 2: "nd", 3: "rd"}.get(n % 10, "th")


def _spoken_days(t):
    """AV2007-11: (date-local text, segments). A spelled-out day of the month ('the twenty first', 'november thirtieth', 'saturday the fifth') is read as its
    numeric ordinal ('21st') so it takes the same calendar path; only in a day context (after 'the', a weekday or a month, or before a month). ``segments`` maps
    each replacement back to the words said: [(new_start, new_end, said)]. Other hint families never see this text."""
    out, segs, pos, shift = [], [], 0, 0
    for m in ORDINAL_WORD_RE.finditer(t):
        before, after = t[:m.start()], t[m.end():]
        if ORD_BAD_BEFORE_RE.search(before) or not (ORD_BEFORE_RE.search(before) or ORD_AFTER_RE.match(after)): continue
        n = ORDINAL_WORDS[m.group(1).replace("-", " ")]
        new = f"{n}{_ordinal_suffix(n)}"
        out.append(t[pos:m.start()]); out.append(new)
        start = m.start() + shift
        segs.append((start, start + len(new), m.group(1)))
        shift += len(new) - (m.end() - m.start()); pos = m.end()
    out.append(t[pos:])
    return "".join(out), segs


def _said_words(t, segs, s, e):
    """The words as said for t[s:e] of the date-local text: each numeric stand-in goes back to its spoken form."""
    res, pos = [], s
    for a, b, said in segs:
        if b <= s or a >= e: continue
        res.append(t[pos:a]) if a > pos else None
        res.append(said); pos = b
    res.append(t[pos:e])
    return "".join(res)


def _safe_date(year, month, day):
    try: return date(year, month, day)
    except ValueError: return None


def _date_row(said, d):
    return {"said": said, "date": d.isoformat(), "weekday": WEEKDAY_NAMES[d.weekday()]}


def _named_date(t, m, month, day, today, year=True):
    """(said, date) for a month and day the owner wrote, or None. An explicit year after it (December 5 2027, 5 Dec '27) is used as
    written and an odd one (a four digits that are not 2000-2099, e.g. a clock) leaves the hint out; with no year the next such day
    from ``today`` is the hint. A hint is never a different year than the one the owner wrote."""
    y = YEAR_RE.match(t, m.end()) if year else None
    if y:
        n = int(y.group(1)) + 2000 if y.group(1) else int(y.group(2))
        d = _safe_date(n, month, day) if 2000 <= n <= 2099 else None
        return (t[m.start():y.end()], d) if d is not None else None
    if year and BAD_YEAR_RE.match(t, m.end()): return None  # digits that look like a year but are not one (dec 5 202, 5 dec 20277): no hint
    # Earliest real occurrence on/after today; Feb 29 can be up to 8 years away (non-leap century), so search a bounded 9 years.
    d = None
    for yr in range(today.year, min(today.year + 8, date.max.year) + 1):
        c = _safe_date(yr, month, day)
        if c is not None and c >= today: d = c; break
    return (m.group(0), d) if d is not None else None


def _slash_year(m):
    """(said, date) for 12/5/2027 or 12/5/27; None for a bad day or a year that is not two or four digits."""
    n = m.group(3)
    if len(n) not in (2, 4): return None
    n = int(n) + 2000 if len(n) == 2 else int(n)
    d = _safe_date(n, int(m.group(1)), int(m.group(2))) if 2000 <= n <= 2099 else None
    return (m.group(0), d) if d is not None else None


HOLIDAY_RE = re.compile(r"(?<![a-z0-9])(thanksgiving(?: day)?|christmas(?: day| eve)?|new year's (?:day|eve)|memorial day|labor day)(?![a-z0-9])")
HOLIDAY_PAST_RE = re.compile(r"(?:last|past|previous|since)\s+$")  # words before a holiday that mean a day gone by
HOLIDAY_YEAR_BEFORE_RE, HOLIDAY_YEAR_AFTER_RE = re.compile(r"\b(?:19|20)\d\d\s+$"), re.compile(r"\s*(?:of |in )?(?:(?:19|20)\d\d\b|'\d\d\b)")


def _holiday_date(word, year):
    """The date of the US holiday ``word`` (a folded HOLIDAY_RE match) in ``year``: the real day, not the observed one; None past year 9999."""
    try:
        if word.startswith("thanksgiving"): return date(year, 11, 1) + timedelta(days=(3 - date(year, 11, 1).weekday()) % 7 + 21)
        if word.startswith("memorial"): return date(year, 5, 31) - timedelta(days=date(year, 5, 31).weekday())
        if word.startswith("labor"): return date(year, 9, 1) + timedelta(days=(-date(year, 9, 1).weekday()) % 7)
        month, day = {"christmas eve": (12, 24), "christmas": (12, 25), "christmas day": (12, 25), "new year's eve": (12, 31), "new year's day": (1, 1)}[word]
        return date(year, month, day)
    except (ValueError, OverflowError):
        return None


def _holiday_hints(text, today: date) -> list:
    """Rows for each US holiday the folded ``text`` names: its coming date on or after ``today`` (Pacific), so the model never
    works the day out. Last/past or explicitly yeared phrases get no row; July 4th is read by the month-day pass."""
    rows = []
    for m in HOLIDAY_RE.finditer(text):
        before, after = text[:m.start()], text[m.end():]
        if HOLIDAY_PAST_RE.search(before) or HOLIDAY_YEAR_BEFORE_RE.search(before) or HOLIDAY_YEAR_AFTER_RE.match(after): continue
        found = [d for d in (_holiday_date(m.group(1), y) for y in (today.year, today.year + 1)) if d is not None and d >= today]
        if found: rows.append(_date_row(m.group(1), min(found)))
    return rows


_MONTH_FULL = ("January", "February", "March", "April", "May", "June", "July", "August", "September", "October", "November", "December")
PAIR_GAP_RE = re.compile(r"[\s,]*(?:(?:the|on)[\s,]+)*")  # all that may sit between a weekday and the date beside it


def weekday_mismatch_question(row) -> str:
    """AV2007-10: the one code-owned question for a paired row marked ``weekday_mismatch`` ('You said Friday, but November 14 is a Saturday.')."""
    d = date.fromisoformat(row["date"])
    return f"You said {row['said_weekday']}, but {_MONTH_FULL[d.month - 1]} {d.day} is a {WEEKDAY_NAMES[d.weekday()]}. Which day?"


def _pair_weekdays(t, rows, wspans, dspans):
    """AV2007-10: a weekday written right beside ONE explicit date is that date's weekday. Same day: the weekday row folds into the
    date row. Different day: the date row is marked ``weekday_mismatch`` with both readings of the weekday. Anything else stays apart."""
    for ws, we, wrow, wd in wspans:
        near = [x for x in dspans if (x[0] >= we and PAIR_GAP_RE.fullmatch(t[we:x[0]])) or (x[1] <= ws and PAIR_GAP_RE.fullmatch(t[x[1]:ws]))]
        if len(near) != 1: continue
        ds, de, drow = near[0]
        if sum(1 for o in wspans if (ds >= o[1] and PAIR_GAP_RE.fullmatch(t[o[1]:ds])) or (de <= o[0] and PAIR_GAP_RE.fullmatch(t[de:o[0]]))) != 1: continue
        if wrow is not None: rows.remove(wrow)
        if date.fromisoformat(drow["date"]).weekday() == wd: continue
        readings = [] if wrow is None else [wrow[k] for k in ("date", "next", "last") if wrow.get(k)] + list(wrow.get("unclear", ()))
        drow.update({"weekday_mismatch": True, "said_weekday": WEEKDAY_NAMES[wd], "weekday_dates": list(dict.fromkeys(readings))})


def weekday_mismatches(text, today: date) -> list:
    """AV2007-10: every paired row of ``text`` whose weekday disagrees with its date (not cut to MAX_LIST), else []."""
    return [r for r in all_date_rows(text, today)[0] if r.get("weekday_mismatch")]


def date_hints(text, today: date):
    """(rows, [(said weekday, weekday number)]): every day the message names, in Pacific time (``today`` is the Pacific day)."""
    rows, hits = all_date_rows(text, today)
    return rows[:MAX_LIST], hits



def all_date_rows(text, today: date):
    t, rows, hits = fold(text), [], []
    t, segs = _spoken_days(t)
    wspans, dspans = [], []
    day = lambda d: d.isoformat()  # noqa: E731
    for m in RELATIVE_RE.finditer(t):
        word = m.group(1)
        d = _shift(today, {"today": 0, "tonight": 0, "tomorrow": 1, "tmrw": 1, "tmr": 1, "yesterday": -1, "day after tomorrow": 2}[word])
        if d is not None: rows.append({"said": word, "date": day(d), "weekday": WEEKDAY_NAMES[d.weekday()]})
    for m in WEEKDAY_RE.finditer(t):
        mod, name = m.group(1), m.group(2)
        wd = WEEKDAYS[name]
        hits.append((name, wd))
        nxt, last = _next_weekday(today, wd), _shift(today, -(((today.weekday() - wd) % 7) or 7))
        said = f"{mod} {name}" if mod and mod != "on" else name
        n0 = len(rows)
        if mod == "next" or wd == today.weekday() and mod != "last":
            first, second = (nxt, None if nxt is None else _shift(nxt, 7)) if mod == "next" and wd != today.weekday() else (today, _shift(today, 7))
            if first is not None and second is not None:  # both readings or no row: never a lone date for an ambiguous day
                rows.append({"said": said, "unclear": [day(first), day(second)], "weekday": WEEKDAY_NAMES[wd], "note": "two readings; ask which unless the owner said"})
        elif mod == "last":
            if last is not None: rows.append({"said": said, "date": day(last), "weekday": WEEKDAY_NAMES[wd]})
        elif nxt is not None and last is not None:
            rows.append({"said": said, "next": day(nxt), "last": day(last), "weekday": WEEKDAY_NAMES[wd], "note": "next = the coming one; last = the one just past"})
        wspans.append((m.start(), m.end(), rows[n0] if len(rows) > n0 else None, wd))
    for m in ORDINAL_RE.finditer(t):
        n = int(m.group(1))
        if not 1 <= n <= 31: continue
        d = None
        for k in range(3):  # three consecutive months always contain every day 1..31; real dates decide month lengths
            y, mo = divmod(today.year * 12 + today.month - 1 + k, 12)
            c = _safe_date(y, mo + 1, n) if y <= date.max.year else None
            if c is not None and c >= today: d = c; break
        if d is not None and not MONTH_DAY_RE.search(t[max(0, m.start() - 12):m.end()]) and not DAY_MONTH_RE.search(t[m.start():m.end() + 14]):
            rows.append({"said": m.group(0), "date": day(d), "weekday": WEEKDAY_NAMES[d.weekday()]})
            dspans.append((m.start(), m.end(), rows[-1]))
    for m in MONTH_DAY_RE.finditer(t):
        found = _named_date(t, m, MONTHS[m.group(1)], int(m.group(2)), today)
        if found: rows.append(_date_row(*found)); dspans.append((m.start(), m.start() + len(found[0]), rows[-1]))
    for m in DAY_MONTH_RE.finditer(t):
        found = _named_date(t, m, MONTHS[m.group(2)], int(m.group(1)), today)
        if found: rows.append(_date_row(*found)); dspans.append((m.start(), m.start() + len(found[0]), rows[-1]))
    for m in SLASH_RE.finditer(t):
        if m.group(3) is None: found = _named_date(t, m, int(m.group(1)), int(m.group(2)), today, year=False)
        else: found = _slash_year(m)
        if found: rows.append(_date_row(*found)); dspans.append((m.start(), m.start() + len(found[0]), rows[-1]))
    for m in ISO_RE.finditer(t):
        d = _safe_date(int(m.group(1)), int(m.group(2)), int(m.group(3)))
        if d is not None and 2000 <= d.year <= 2099: rows.append(_date_row(m.group(0), d)); dspans.append((m.start(), m.end(), rows[-1]))
    _pair_weekdays(t, rows, wspans, dspans)
    if segs:
        for ds, de, drow in dspans: drow["said"] = _said_words(t, segs, ds, de) if drow["said"] == t[ds:de] else drow["said"]
    for m in IN_RE.finditer(t):
        n = int(m.group(1)) if m.group(1).isdigit() else WORD_NUMBERS[m.group(1)]
        d = _shift(today, n * (7 if m.group(2) == "week" else 1))
        if d is not None: rows.append({"said": m.group(0), "date": day(d), "weekday": WEEKDAY_NAMES[d.weekday()]})
    rows.extend(_holiday_hints(t, today))
    if re.search(r"\b(next week|this weekend|next month|couple (?:of )?(?:days|weeks)|few (?:days|weeks)|sometime|soon)\b", t):
        rows.append({"said": "a loose time", "date": None, "note": "not one day: ask which day"})
    return [r for r in rows if r.get("weekday_mismatch")] + [r for r in rows if not r.get("weekday_mismatch")], hits  # a contradiction is never cut by MAX_LIST


def time_hints(text) -> list:
    out = []
    for m in TIME_RE.finditer(fold(text)):
        if m.group(6):
            out.append({"said": m.group(0), "time": "12:00" if m.group(6) == "noon" else "00:00"})
        elif m.group(3):
            hour, minute = int(m.group(1)), int(m.group(2) or 0)
            if 1 <= hour <= 12 and minute < 60:
                out.append({"said": m.group(0).strip(), "time": f"{hour % 12 + (12 if m.group(3) == 'p' else 0):02d}:{minute:02d}"})
        else:
            out.append({"said": m.group(0), "time": f"{int(m.group(4)):02d}:{m.group(5)}"})
    return out[:MAX_LIST]


def number_hints(text) -> list:
    return [{"said": w, "value": WORD_NUMBERS[w]} for w in TOKEN_RE.findall(fold(text)) if w in WORD_NUMBERS and w != "one"][:MAX_LIST]


def price_hints(text):
    t = fold(text)
    if not PRICE_CUE_RE.search(t): return None
    amounts = [next(g for g in m.groups() if g) for m in MONEY_RE.finditer(t)]
    return {"mentioned": True, "amounts": amounts[:MAX_LIST]}


PLAIN_WORDS = frozenset("a also and at can could change changes hours hour i is it me my of on our please set shop shops store the to update we would you make".split())  # only these may surround the days and ranges: any other word may be a clause nothing here proves already true


def _clock(hour, minute, mark):
    return f"{hour % 12 or 12}{':' + minute if minute and minute != '00' else ''}{mark}"


def asked_range(text):
    """('9am', '5pm') for "9 to 5", "8:30-4pm" and the like (a bare end before the start is the afternoon); else None."""
    m = RANGE_RE.search(fold(text))
    if not m: return None
    h1, m1, a1, h2, m2, a2 = int(m.group(1)), m.group(2), m.group(3), int(m.group(4)), m.group(5), m.group(6)
    if not (1 <= h1 <= 12 and 1 <= h2 <= 12): return None
    a1, a2 = (a1 or "")[:1], (a2 or "")[:1]
    if not a2 and not a1: a1, a2 = ("a" if h1 >= 6 else "p"), ("p" if h2 <= 8 or h2 < h1 else "a")
    elif not a2: a2 = "p" if a1 == "a" and h2 < h1 else a1
    elif not a1: a1 = "a" if h1 <= h2 or a2 == "p" else "p"
    return _clock(h1, m1, a1 + "m"), _clock(h2, m2, a2 + "m")


def _stored_weekday(word):
    """Weekday index for a complete stored word (a WEEKDAYS spelling, optionally with one plural s), else None: never a prefix."""
    w = word.lower()
    return WEEKDAYS.get(w, WEEKDAYS.get(w[:-1]) if w.endswith("s") else None)


def _day_shows(index, wd, asked):
    """The Store line text for weekday ``wd`` when it shows exactly ``asked``, else None."""
    for line in index.hours:
        for part in line.split("\u00b7"):
            m = re.match(r"\s*([A-Za-z]+)(?:\s*[\u2013-]\s*([A-Za-z]+))?\s+(.+?)\s*$", part)
            if not m: continue
            first = _stored_weekday(m.group(1))
            last = first if m.group(2) is None else _stored_weekday(m.group(2))
            if first is None or last is None or not first <= wd <= last: continue
            shown = re.sub(r"\s*[\u2013-]\s*", "\u2013", m.group(3).lower().replace(" ", ""))
            if shown == f"{asked[0]}\u2013{asked[1]}": return m.group(3)
    return None


_DAY_SPAN_RE = re.compile(r"\s*(?:[-\u2013\u2014]|to|through|until)\s*")  # what joins two weekdays into a span


def hours_hints(text, index):
    """The Store already shows EVERY day and hours the owner asks for: a fact for "it already says that", never a draft.
    Each day is matched to its own range (the nearest one); any change not already true, or any pairing in doubt, gives no hint."""
    t = fold(text)
    ranges = [(m.start(), m.end(), asked_range(m.group(0))) for m in RANGE_RE.finditer(t)]
    days = [(m.start(), m.end(), WEEKDAYS[m.group(2)]) for m in WEEKDAY_RE.finditer(t)]
    if not (ranges and days and index.hours) or any(r[2] is None for r in ranges): return None
    if any(_DAY_SPAN_RE.fullmatch(t[a[1]:b[0]]) for a, b in zip(days, days[1:])): return None  # "Monday-Friday": endpoints never prove the days between
    rest = WEEKDAY_RE.sub(" ", RANGE_RE.sub(" ", t))  # every other word must be plain filler: "closed", "opens at 10am", "from 10" are changes nothing here proves already true
    if any(w not in PLAIN_WORDS for w in TOKEN_RE.findall(rest)): return None
    same, used = [], set()
    for start, end, wd in days:
        dist = sorted((max(r[0] - end, start - r[1], 0), k) for k, r in enumerate(ranges))
        if len(dist) > 1 and dist[0][0] == dist[1][0]: return None  # equally near two ranges: cannot tell which is meant
        k = dist[0][1]
        shown = _day_shows(index, wd, ranges[k][2])
        if shown is None: return None  # this day is asked to change (or is not on the Store)
        used.add(k)
        same.append(f"{WEEKDAY_NAMES[wd]} already {shown}")
    if len(used) != len(ranges): return None  # a requested range no day was matched to
    return list(dict.fromkeys(same)) or None


# -- AV2007-12: one stock product named whole ("out of raspberries", "raspberries are back", "blubereis sold out") ----------
LEMONS_RE = re.compile("(?:\U0001F34B\ufe0f?)+")  # one or more lemon emoji read as the one word \"lemons\": never a count
LEAD_RE = re.compile(r"^(?:(?:we|they)'?re |we are |i'?m |im |all )*")
OUT_OF_RE = re.compile(r"^out of (?P<p>.+)$")
BACK_RE = re.compile(r"^(?P<p>.+?) (?:(?:is|are) )?back(?: in)?$")
SOLD_RE = re.compile(r"^(?P<p>.+?) (?:(?:is|are) )?(?:sold out|out)$")
STOCK_NOISE = frozenset("""and or but also then plus nor not no never dont doesnt isnt arent wasnt werent cant wont low limited available hide hidden hold
 out sold back gone left today tomorrow tonight yesterday if when until maybe it them this that these those""".split())
NO_PRODUCT = "I don't know a product called that. What is it called on the site?"
HELD_WORDS = {"held": "I can't change {name} right now. It is on hold until someone has looked at it.",
              "hidden": "{name} is hidden. Do you want me to bring it back first?"}


def _label(p, same) -> str:
    return f"{p['name']} ({p['brand']})" if p.get("brand") and sum(1 for q in same if q["name"] == p["name"]) > 1 else p["name"]


def resolve_stock_choice(text, content, aliases=None):
    """AV2007-12: {"ops": [...], "revises": None} or {"question": ...} for a whole message that only says one product is out
    ("out of raspberries", "raspberries are sold out") or back ("raspberries are back"); None for anything else (a question, a
    negation, a price, a date, several products or clauses, leftover words, a shelf or maker): the interpreter's reading stands.
    Never raises; reads only the catalogue and the owner's own aliases."""
    try:
        if not isinstance(text, str) or not text.strip() or len(text) > 200: return None
        t = LEMONS_RE.sub(" lemons ", fold(text))
        if "?" in t or PRICE_CUE_RE.search(t) or RELATIVE_RE.search(t) or WEEKDAY_RE.search(t): return None
        t = " ".join(re.sub(r"[^\w']+", " ", t).split())
        t = LEAD_RE.sub("", t, count=1)
        if m := OUT_OF_RE.match(t): phrase, available = m.group("p"), "no"
        elif m := BACK_RE.match(t): phrase, available = m.group("p"), "yes"
        elif m := SOLD_RE.match(t): phrase, available = m.group("p"), "no"
        else: return None
        words = [w for w in TOKEN_RE.findall(phrase) if w not in NAME_STOP and w not in ("our", "my", "all", "some", "any")]
        if not words or len(words) > 6 or re.search(r"\d", phrase) or any(w in STOCK_NOISE or w.endswith("n't") for w in TOKEN_RE.findall(phrase)): return None
        index = _Index(content)
        alias_seqs = []
        for a in aliases or []:
            if isinstance(a, dict) and isinstance(a.get("name"), str):
                seq = tuple(tokens(a["name"], stop=NAME_STOP | {"the"}))
                if seq: alias_seqs.append((seq, a))
        alias_words = {w for seq, _ in alias_seqs for w in seq}
        canon, guessed = [], False
        for w in words:
            token = stem(w)
            word, guess = (token, False) if token in alias_words else index.canon(token)
            canon.append(word)
            guessed = guessed or guess
        known = [c for c in canon if c is not None]
        if not known: return {"question": NO_PRODUCT}  # nothing in it is on the site: never offer a name the shop does not carry
        if len(known) != len(canon): return None  # a leftover word: not a whole product name
        span = tuple(canon)
        alias = next((a for seq, a in alias_seqs if seq == span), None)
        if alias is not None:
            hit = next((p for p in index.products if p["id"] == alias.get("id")), None) if alias.get("kind") == "product" else None
            found = [hit] if hit else []
            if not found: return None  # a maker alias or a stale one: nothing to invent
            decision = ("is", found)
        elif any(m["tokens"] == list(span) for m in index.makers) or (len(span) == 1 and span[0] in SHELVES and not any(p["set"] == frozenset(span) for p in index.products)):
            return None  # a maker or a whole shelf: not one product
        else:
            decision = _decide(list(span), index.products)
            if decision is not None and guessed:
                named = [p for p in decision[1] if frozenset(span) <= p["set"]]  # a corrected spelling picks only by name, never by a description
                decision = (decision[0], named) if named else None
                if decision and len(named) == 1: decision = ("is", named)
        if decision is None: return {"question": NO_PRODUCT}
        kind, found = decision
        if kind == "is":
            p = found[0]
            if p["status"] in HELD_WORDS: return {"question": HELD_WORDS[p["status"]].format(name=p["name"])}
            if p["status"] not in (None, "active"): return None
            return {"ops": [{"op": "product.set_availability", "args": {"id": p["id"], "available": available}}], "revises": None}
        usable = [p for p in found if p["status"] in (None, "active")] or found
        names = [_label(p, usable) for p in sorted(usable, key=lambda p: (p["name"], p["id"]))][:MAX_LIST]
        return {"question": "Which one do you mean: " + (names[0] if len(names) == 1 else ", ".join(names[:-1]) + " or " + names[-1]) + "?"}
    except (TypeError, ValueError, KeyError, AttributeError, IndexError, RecursionError):
        return None


def make_hinter(content):
    """hinter(text, today: date, aliases=None) -> dict (empty when there is nothing to say; never raises)."""
    index = _Index(content)

    def hinter(text, today: date, aliases=None) -> dict:
        try:
            out = phrase_hints(text, index, aliases)
            dates, weekdays = date_hints(text, today)
            hikes = hike_hints(text, index, today, weekdays)
            if hikes.get("named") and out.get("products"):  # "cass hill" in a hike message is the hike, not the product of that name
                titles = [set(tokens(n.get("title") or "")) for n in hikes["named"]]
                out["products"] = [p for p in out["products"] if not any(set(tokens(p["said"])) <= t for t in titles)]
                if not out["products"]: del out["products"]
            for key, value in (("alreadyTrue", hours_hints(text, index)), ("hikes", hikes), ("dates", dates), ("times", time_hints(text)), ("numbers", number_hints(text)), ("price", price_hints(text))):
                if value: out[key] = value
            return out
        except Exception:  # noqa: BLE001 - a hint is a convenience; the request still goes out without it
            return {}
    return hinter
