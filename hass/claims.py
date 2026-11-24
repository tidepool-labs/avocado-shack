"""NB-AV-05 (H03/H05): organic, origin, grade, process, diet and maker claims a draft adds that the owner did not say.

Pure and stdlib-only. After the editor prepares a draft, every text field it changes is scanned for claim terms that
are new (more of them than before) and absent from the owner's message; a new producerKey must name a maker the owner
named (by key or by name). Matching is on folded text and whole words: "organically" is not "organic", "locale" is
not "local". A revert draft (only history.revert ops) restores earlier text and is never checked.
RF2030-4: an owner word with a negator among the 3 words before it in its clause ("not organic", "isn't local") is not
said; fail-closed, so "not only organic but local" leaves "organic" unsaid and the owner gets the claim question.
RF2030-5: a list-of-text field (store hours lines) is checked as its newline-joined lines; other lists are skipped.
RF0250-3: a maker key or name the owner only negates is not named.
RF2330-12: fair-trade, animal-welfare and farming-method claims also need the owner's words.
RF1230-17: negators also count typed without the apostrophe ("isnt", "dont"); "wont"/"cant" may over-ask (fail-closed).
AV2022-04: a changed product brand/displayBrand or maker place must share a word with the owner's text; a maker url's host.
AV0022-11: events and routeIdeas text is also scanned for ACCESS_TERMS (dogs, wheelchair, permit, parking); longest term wins.
AV0022-12: an events number with a unit (mi, km, ft, hours, min; ranges give both ends) a draft adds must be in the owner's
text or in the text of the route idea the hike's trailId names; "3.20 miles" is "3.2 mi", "3,2" is 3.2; "5k", "10h" are not.
RF0220-11: a store record's notice.text and homeImage.imageAlt strings are checked like any text field (labels "notice.text",
"homeImage.imageAlt"); no other dictionary is scanned, and a leaf that is not a string is skipped.
AV1937-05: a hike.repeat copies title, trailId and the event text (never the recap) from a real hike; a copied value that
equals the same field of that source hike (read from the content by the conversation) is not checked again.
AV2152-10: health and award terms (HEALTH_AWARD_TERMS) a draft adds also need the owner's words; treat and best are not terms.
AV1124A-08: VARIANT_TERMS (organically, gmo free, preservative free, sulfite free, no pesticides) are asked like any term, an owner's "organic"
also backs "organically"; a number joined to a unit by a hyphen ("2-mile", "3-hr") is the same quantity as "2 miles", "3 hours".
"""
import re
import unicodedata
from collections import Counter
from decimal import Decimal

from hass.content_model import EVENT_TEXT_FIELDS

TERMS = ("organic", "certified", "pesticide-free", "spray-free", "non-gmo", "local", "locally", "grown in", "made in",
         "raised in", "harvested in", "sourced from", "produced in", "family farm", "estate",
         "extra virgin", "cold pressed", "first press", "unfiltered", "unpasteurized", "raw honey", "gluten-free",
         "dairy-free", "nut-free", "sugar-free", "vegan", "kosher", "halal", "all natural", "no preservatives", "grass-fed",
         "pasture-raised", "wild-caught")
_PUNCT = str.maketrans({**{c: "'" for c in "\u2018\u2019\u201b\u02bc\u0060\u00b4\u2032"},
                        **{c: '"' for c in "\u201c\u201d\u201e\u2033"}, **{chr(c): "-" for c in range(0x2010, 0x2016)}})


def fold(text) -> str:
    """NFKD, combining marks dropped, typographic apostrophes/quotes/dashes made ASCII, casefolded, spaces collapsed."""
    plain = "".join(c for c in unicodedata.normalize("NFKD", str(text)) if not unicodedata.combining(c))
    return " ".join(plain.translate(_PUNCT).casefold().split())


# HASS-SEC-2 (H1): the live claim gate reads text through skeleton(), so a claim word cannot hide behind a lookalike letter
# or an invisible character. Lookalikes: one Latin letter per Cyrillic, Greek, Armenian or small-capital letter that looks the
# same (Unicode TR39 confusables, the letters that matter for English words); a word still mixing scripts after this is caught
# by live_policy's mixed-script rule.
_LOOKALIKE = str.maketrans({pair[0]: pair[1] for pair in (
    "аa АA вb ВB еe ЕE ёe Ёe кk КK мm МM нh НH оo ОO рp РP сc СC тt ТT уy УY хx ХX ѕs ЅS іi ІI їi ЇI јj ЈJ ԁd ԛq ԚQ ԝw ԜW "
    "үy ҮY һh ҺH ӏl ӀI ьb Ьb ɡg "                                                     # Cyrillic (and Latin script g)
    "αa ΑA βb ΒB γy εe ΕE ζz ΖZ ηn ΗH ιi ΙI κk ΚK μu ΜM νv ΝN οo ΟO ρp ΡP τt ΤT υu ΥY χx ΧX ωw ϲc ϹC ϳj "  # Greek
    "օo Օo սu Սu ցg հh ոn ռn զq "                                                    # Armenian
    "ıi ȷj ɩi ɑa ʏy ᴀa ʙb ᴄc ᴅd ᴇe ɢg ʜh ɪi ᴊj ᴋk ʟl ᴍm ɴn ᴏo ᴘp ʀr ꜱs ᴛt ᴜu ᴠv ᴡw ᴢz"  # Latin lookalikes, small capitals
).split()})
# Characters that show nothing (or nothing that changes a word) and are dropped before matching: every format character
# (soft hyphen, zero-width space/joiners, word joiner, bidi marks, Mongolian vowel separator, tag characters), every
# non-spacing or enclosing mark (accents, variation selectors), and the Hangul and Braille blanks.
_BLANKS = frozenset("\u115f\u1160\u3164\uffa0\u2800")


def _shown(c) -> bool:
    return c not in _BLANKS and unicodedata.category(c) not in ("Cf", "Mn", "Me")


def unhidden(text) -> str:
    """NFKC, then every character that shows nothing dropped, then accents dropped (NFKD). Line breaks kept; letters as typed."""
    plain = "".join(c for c in unicodedata.normalize("NFKC", str(text)) if _shown(c))
    return "".join(c for c in unicodedata.normalize("NFKD", plain) if _shown(c) and not unicodedata.combining(c))


def skeleton(text) -> str:
    """unhidden(), lookalike letters made Latin, typographic marks ASCII, casefolded, spaces and line breaks collapsed. Pure."""
    return " ".join(unhidden(text).translate(_LOOKALIKE).translate(_PUNCT).casefold().split())


def _pattern(phrase: str):
    """Whole words; a space or hyphen between words matches either ("pesticide free" is "pesticide-free")."""
    words = re.split(r"[-\s]+", fold(phrase))
    return re.compile(r"(?<!\w)" + r"[-\s]".join(re.escape(w) for w in words) + r"(?!\w)")


FARM_TERMS = ("fair trade", "fairtrade", "free-range", "cage-free", "hormone-free", "antibiotic-free", "biodynamic",
              "regenerative", "chemical-free", "unsprayed")
HEALTH_AWARD_TERMS = ("cures", "heals", "prevents", "immune", "immunity", "detox", "anti-inflammatory", "antioxidant",
                      "probiotic", "superfood", "medicinal", "lowers cholesterol", "weight loss", "award-winning",
                      "prize-winning", "gold medal")  # AV2152-10; kept apart from TERMS (its pin)
VARIANT_TERMS = ("organically", "gmo-free", "preservative-free", "sulfite-free", "sulphite-free", "no pesticides")  # AV1124A-08; apart from TERMS (its pin)
_BACKED_BY = {"organically": _pattern("organic")}  # an owner's affirmed "organic" also backs "organically"
_TERM_RES = tuple((term, _pattern(term)) for term in TERMS + FARM_TERMS + HEALTH_AWARD_TERMS + VARIANT_TERMS)
ACCESS_TERMS = ("dogs allowed", "dogs welcome", "dog friendly", "dog-friendly", "pet friendly", "leashed dogs",
                "wheelchair accessible", "wheelchair friendly", "ada accessible", "stroller friendly", "no permit",
                "no permit needed", "permit not required", "free parking", "parking available", "open to the public",
                "public access", "kid friendly", "family friendly", "safe for kids", "restrooms", "drinking water")
_ACCESS_RES = tuple((t, _pattern(t)) for i, t in enumerate(ACCESS_TERMS)  # one entry per spelling (hyphen = space)
                    if _pattern(t) not in [_pattern(u) for u in ACCESS_TERMS[:i]])


def _access_counts(text: str) -> dict:
    """{term: matches} in folded text, a match inside a longer term's match (\"no permit\" in \"no permit needed\") left out."""
    found = [(m.span(), term) for term, rx in _ACCESS_RES for m in rx.finditer(text)]
    kept = [(sp, t) for sp, t in found if not any(o != sp and o[0] <= sp[0] and sp[1] <= o[1] for o, _t in found)]
    return {term: sum(t == term for _s, t in kept) for term, _rx in _ACCESS_RES}


UNITS = {"mi": "mi", "mile": "mi", "miles": "mi", "km": "km", "kilometer": "km", "kilometers": "km", "kilometre": "km",
         "kilometres": "km", "ft": "ft", "foot": "ft", "feet": "ft", "hr": "hour", "hrs": "hour", "hour": "hour",
         "hours": "hour", "min": "min", "mins": "min", "minute": "min", "minutes": "min"}  # "h" alone is not a unit
_NUM = r"\d+(?:[.,]\d+)?"
QTY_RE = re.compile(rf"(?<![\w.,:])({_NUM})(?:\s*(?:[-–]|to)\s*({_NUM}))?(?:-|\s*)({'|'.join(sorted(UNITS, key=len, reverse=True))})(?!\w)")


def _quantities(text: str) -> list:
    """[(matched text, ((number, unit), ...))] in folded text; a range gives both ends, numbers as Decimal (3.0 is 3)."""
    return [(m.group(0), tuple((Decimal(n.replace(",", ".")), UNITS[m.group(3)]) for n in m.group(1, 2) if n))
            for m in QTY_RE.finditer(text)]


def _pairs(*texts) -> set:
    return {p for t in texts for _m, ps in _quantities(fold(t)) for p in ps}


NEGATORS = ("not", "no", "never", "nor", "without", "isn't", "aren't", "wasn't", "weren't", "don't", "doesn't", "didn't",
            "won't", "cannot", "can't", "isnt", "arent", "wasnt", "werent", "dont", "doesnt", "didnt", "wont", "cant",
            "hasn't", "haven't", "hadn't", "hasnt", "havent", "hadnt")
_CLAUSE = re.compile(r"[.!?;:\n]")


def _affirmed(rx, owner: str) -> bool:
    """True when some match of rx in the folded owner text (newlines kept) has no negator among the (up to) 3 words
    just before it in its clause. Clauses end at . ! ? ; : or a newline; words split on whitespace, , " ( ) stripped."""
    for clause in _CLAUSE.split(owner):
        for m in rx.finditer(clause):
            words = [w for w in (w.strip(',"()') for w in clause[:m.start()].replace("-", " ").split()) if w]  # RF0240-12: not-organic negates
            if not set(words[-3:]) & set(NEGATORS):
                return True
    return False


SOURCE_FIELDS = {"products": ("brand", "displayBrand"), "makers": ("place", "url")}
STOP = {"the", "and", "of", "a", "an", "co", "inc", "llc", "company"}
PLACEHOLDER = "Producer not identified"


def _words(value) -> set:
    """Folded words of value, stop words and single characters dropped."""
    return {w for w in re.findall(r"\w+", fold(value)) if w not in STOP and len(w) > 1}


def _host(url) -> str:
    """Folded host of url (scheme and user part skipped, port dropped), leading "www." removed; "" when there is none."""
    m = re.match(r"(?:[a-z][a-z0-9+.-]*://)?(?:[^@/?#\s]*@)?([^/:?#\s]*)", fold(url))
    host = m.group(1).strip(".") if m else ""
    return host[4:] if host.startswith("www.") else host


def _source_hit(field: str, new: str, owner: str) -> bool:
    """True when a source field's new value is not backed by the owner's (folded) text."""
    if new == PLACEHOLDER: return False
    if field == "url":
        host = _host(new)
        return not host or not re.search(r"(?<![\w.-])(?:www\.)?" + re.escape(host) + r"(?![\w-]|\.\w)", owner)
    words = _words(new)
    # RF0640-10: one significant word with an affirmed (not negated) whole-word occurrence backs the value
    return bool(words) and not any(_affirmed(re.compile(r"(?<!\w)" + re.escape(w) + r"(?!\w)"), owner) for w in words)


def _lines(value) -> bool:
    return isinstance(value, list) and all(isinstance(item, str) for item in value)


def _said(phrase, lines: str) -> bool:
    return bool(isinstance(phrase, str) and phrase.strip() and _affirmed(_pattern(phrase), lines))


NESTED_TEXT = {"homeImage": ("imageAlt",), "notice": ("text",), "banner": ("text",)}  # RF0220-11 (+AVB-19 banner): the only dict-valued store slots with free text
PAGE_TEXT = ("pageAbout", "pageGettingHere", "pagePolicies", "pageFaq")  # AVB-19-B2: a fixed page's words, checked as one text


def _page_words(page) -> str:
    """Every owner text of a fixed page (title, intro, paragraphs, questions and answers), one per line; not a page: ''."""
    if not isinstance(page, dict):
        return ""
    texts = [page.get("title"), page.get("intro")] + list(page.get("paragraphs") or [])
    texts += [e.get(k) for e in page.get("entries") or [] if isinstance(e, dict) for k in ("q", "a")]
    return "\n".join(t for t in texts if isinstance(t, str))


def _fields(r: dict, before: dict, after: dict):
    """(label, new, old) per changed-field candidate of a record, top-level fields sorted. A store record's notice and
    homeImage dicts give only their NESTED_TEXT leaves, labelled "notice.text"; an old container or leaf that is not a
    dict or string counts as empty, a new one that is not a dict is handled as any top-level value. Other dicts: skipped."""
    for field in sorted(after):
        new, old = after[field], before.get(field)
        if r.get("collection") == "store" and field == "specials" and isinstance(new, list):  # AVO-SPECIALS-1: each special's words
            old_by_id = {sp.get("id"): sp for sp in old if isinstance(sp, dict)} if isinstance(old, list) else {}
            for sp in new:
                if isinstance(sp, dict) and isinstance(sp.get("id"), str):
                    for leaf in ("title", "deal"):
                        if isinstance(sp.get(leaf), str):
                            yield f"specials.{sp['id']}.{leaf}", sp[leaf], old_by_id.get(sp["id"], {}).get(leaf)
        elif r.get("collection") == "store" and field in NESTED_TEXT and isinstance(new, dict):
            old = old if isinstance(old, dict) else {}
            for leaf in NESTED_TEXT[field]:
                if isinstance(new.get(leaf), str):
                    yield f"{field}.{leaf}", new[leaf], old.get(leaf)
        elif r.get("collection") == "store" and field in PAGE_TEXT and isinstance(new, dict):
            yield f"{field}.words", _page_words(new), _page_words(old)
        else:
            yield field, new, old


REPEAT_FIELDS = ("title",) + tuple(f for f in EVENT_TEXT_FIELDS if f != "recap") + ("trailId",)  # what hike.repeat copies


def _copied(draft: dict, sources) -> dict:
    """{record index: source event} for each new event record that a hike.repeat op in the draft made, else nothing.

    A record counts only when it is a new scheduled event whose id starts hike-<date>- and whose start is the op's local
    date and time, and its source is a real event in ``sources``. A record is claimed by one repeat op at most.
    """
    if not isinstance(sources, dict):
        return {}
    found, spent = {}, set()
    for call in draft.get("ops") or []:
        args = call.get("args") if isinstance(call, dict) and call.get("op") == "hike.repeat" else None
        source = sources.get(args.get("id")) if isinstance(args, dict) and isinstance(args.get("id"), str) else None
        if not isinstance(source, dict) or not all(isinstance(args.get(k), str) for k in ("date", "time")):
            continue
        for i, r in enumerate(draft.get("records") or []):
            after = r.get("after") if isinstance(r.get("after"), dict) else {}
            if (r.get("collection") == "events" and r.get("before") is None and i not in spent
                    and isinstance(r.get("key"), str) and r["key"].startswith(f"hike-{args['date']}-")
                    and after.get("status") == "scheduled" and after.get("id") == r["key"]
                    and isinstance(after.get("startsAt"), str)
                    and after["startsAt"].startswith(f"{args['date']}T{args['time']}")
                    and after.get("title") == source.get("title")):
                spent.add(i)
                found[i] = source
                break
    return found


def _defaulted(draft: dict) -> set:
    """Indexes of new product records whose displayBrand the catalog generated ('From the market' for an unidentified
    producer) because the product.add op named no displayBrand; an explicitly supplied label is not exempt."""
    adds = [c.get("args") for c in draft.get("ops") or [] if isinstance(c, dict) and c.get("op") == "product.add"
            and isinstance(c.get("args"), dict)]
    created = [i for i, r in enumerate(draft.get("records") or [])  # product.add is the only op that creates a product
               if r.get("collection") == "products" and r.get("before") is None]
    out = set()
    for i, a in zip(created, adds):  # the k-th creating record belongs to the k-th product.add op, one to one
        after = draft["records"][i].get("after")
        if (isinstance(after, dict) and "displayBrand" not in a and a.get("brand") == "Producer not identified"
                and after.get("displayBrand") == "From the market" and after.get("brand") == "Producer not identified"
                and after.get("name") == a.get("name")):
            out.add(i)
    return out


def unstated(draft: dict, owner_text, makers, routes=None, sources=None) -> list:
    """[(where, term)] for claims the draft adds that the owner's text does not contain; where = collection key field.
    makers: {key: maker} from the content (None when unreadable: every producerKey change is then unstated).
    routes: {id: routeIdea} (None when unreadable: only the owner's text backs an events number).
    sources: {id: event} of the content's real hikes (None when unreadable: a hike.repeat copy is checked like any text)."""
    if all(isinstance(c, dict) and c.get("op") == "history.revert" for c in draft.get("ops") or [None]):
        return []
    records = draft.get("records") or []
    lines = "\n".join(fold(line) for line in str(owner_text or "").splitlines())  # fold() collapses newlines
    known = dict(makers or {})
    known.update({r.get("key"): r["after"] for r in records if r.get("collection") == "makers"
                  and isinstance(r.get("after"), dict)})  # a maker this same draft adds or renames
    hits, repeats, defaulted = [], _copied(draft, sources), _defaulted(draft)
    for n, r in enumerate(records):
        before = r.get("before") if isinstance(r.get("before"), dict) else {}
        after = r.get("after") if isinstance(r.get("after"), dict) else {}
        copy_of = repeats.get(n)
        for field, new, old in _fields(r, before, after):
            if copy_of is not None and field in REPEAT_FIELDS and field in copy_of and new == copy_of[field]:
                continue  # AV1937-05: copied word for word from the real hike this repeat names
            if _lines(new):  # RF2030-5: a list of text (store hours) is checked as its newline-joined lines
                new, old = "\n".join(new), "\n".join(old) if _lines(old) else ""
            if not isinstance(new, str) or new == old: continue
            where = f"{r.get('collection')} {r.get('key')} {field}"
            if field == "producerKey" and r.get("collection") == "products":
                maker = known.get(new)
                name = maker.get("name") if isinstance(maker, dict) else None
                if makers is None or not (_said(new, lines) or _said(name, lines)): hits.append((where, "maker"))
                continue
            if n in defaulted and field == "displayBrand": continue  # generated default, not an owner claim
            if field in SOURCE_FIELDS.get(r.get("collection"), ()) and new.strip() and _source_hit(field, new, lines):
                hits.append((where, "link" if field == "url" else field))  # AV2022-04; the term scan still runs
            text, was = fold(new), fold(old if isinstance(old, str) else "")
            hits += [(where, term) for term, rx in _TERM_RES
                     if len(rx.findall(text)) > len(rx.findall(was)) and not _affirmed(rx, lines)
                     and not (term in _BACKED_BY and _affirmed(_BACKED_BY[term], lines))]
            if r.get("collection") in ("events", "routeIdeas"):  # AV0022-11
                now_n, was_n = _access_counts(text), _access_counts(was)
                hits += [(where, term) for term, rx in _ACCESS_RES
                         if now_n[term] > was_n[term] and not _affirmed(rx, lines)]
            if r.get("collection") == "events":  # AV0022-12
                trail = after.get("trailId")
                idea = routes.get(trail) if isinstance(routes, dict) and isinstance(trail, str) else None
                backed = _pairs(owner_text) | _pairs(*(v for v in idea.values() if isinstance(v, str)) if idea else ())
                now_q, was_q = _quantities(text), Counter(p for _m, ps in _quantities(was) for p in ps)
                added = {p for p, n in Counter(p for _m, ps in now_q for p in ps).items() if n > was_q[p] and p not in backed}
                hits += [(where, t) for t in dict.fromkeys(m for m, ps in now_q if added & set(ps))]
    return hits


def question(hits) -> str:
    """One owner question naming the first two claim words that his message did not contain."""
    from hass.voice import quote
    terms = list(dict.fromkeys(term for _where, term in hits))
    named = " and ".join(quote(f'"{t}"') for t in terms[:2])
    if len(terms) == 1:
        return f"You didn't say {named} in your message. Is that true? Send the change again with it in your own words, or without it."
    more = " (and a few more)" if len(terms) > 2 else ""
    return (f"You didn't say {named}{more} in your message. Are they true? "
            "Send the change again with them in your own words, or without them.")
