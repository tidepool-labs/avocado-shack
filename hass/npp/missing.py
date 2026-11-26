"""S3: decide essential questions before any draft. No model, network or writes.

The composer supplies validated owner identity/finance projections from intake,
not the raw merged private slots. Use `questions` and `identified` on Jobs.Plan;
this module does not create or publish a listing. Maker evidence is kept separate.
"""
from dataclasses import dataclass
import json
import re
import unicodedata

from hass import claims, label_reader, live_policy

RULES = "hass-missing-info/missing-info.json"
# The pinned duplicate rule prescribes this question but does not give it a template ID.
DUPLICATE = "That looks like an existing listing. Do you want to add another?"
# Shelves a non-food item may use; every other category is a food shelf.
NON_FOOD_CATEGORIES = ("flowers", "general")


@dataclass(frozen=True)
class OwnerPrice:
    """Checked owner-price span and a separately checked unit (item/pound/basket).

    `unresolved` includes conflict, ambiguity and untrusted parser fallback. Never
    instantiate an amount from a label, web page or an unchecked model answer.
    """
    amount: str | None = None
    unit: str | None = None
    unresolved: bool = False


@dataclass(frozen=True)
class Maker:
    state: str  # absent, known, near, contradictory, ambiguous, unidentified or new
    phrase: str | None = None
    key: str | None = None
    record: dict | None = None

    @property
    def research_allowed(self):
        # Only a maker the owner named that is not on the site yet. New still requires
        # official-site verification in S4; an absent maker (none named) never licenses research.
        return self.state == "new"


@dataclass(frozen=True)
class Decision:
    identified: bool
    item: str | None
    category: str | None
    price: OwnerPrice
    maker: Maker
    duplicate_sources: tuple
    missing: tuple
    questions: tuple  # tuples of (durable question id, rendered sentence)
    note: str = ""

    @property
    def ready(self):
        return not self.missing and not self.questions


def _near(value):
    key = " ".join("".join(c for c in claims.fold(value) if not unicodedata.category(c).startswith("P")).split())
    return key[:-1] if key.endswith("s") and not key.endswith("ss") else key


def _owner_maker(texts, item):
    # Intake supplies the finance-free clauses. A possessive only counts when
    # its suffix is the identified product; a supplier ('from') never counts.
    # An explicit "made by" names the maker as typed and outranks a possessive
    # read anywhere in the turn ("made by Brian's, Brian's sourdough bread" is
    # Brian's, not "Brian"); among the same form the latest clause wins.
    found = {}
    for text in texts:
        for clause in re.split(r"[;\n,]", text):
            form, match = "made_by", re.search(r"\bmade by\s+(.+?)\s*$", clause, re.I)
            if not match and item:
                form = "possessive"
                match = re.fullmatch(r"\s*(?:(?:add|new)\s+)?(.+?)['’]s\s+" + re.escape(item) + r"\s*[.!]?\s*", clause, re.I)
            if match:
                value = match[1].strip().rstrip(".!")
                found[form] = (None if re.search(r"\b(?:maybe|perhaps|probably|not|never|rather than|instead|but)\b|\?", value, re.I)
                               else label_reader.identity_text("brand", value))
    name = found["made_by"] if "made_by" in found else found.get("possessive")
    lines = "\n".join(claims.fold(line) for text in texts for line in text.splitlines())
    return name if name and live_policy._owner_said(name, lines) else None


_HEDGE = re.compile(r"\b(?:maybe|perhaps|probably|not|never|rather than|instead|but|or|like|similar)\b|[?$0-9]", re.I)
# A clause about the maker, not a product name. Fail closed (None keeps the photo and the identity question), so this is
# deliberately broad: it opens with a preposition, conjunction, relative word or pronoun ("in Vermont", "and Sons",
# "that sells honey", "we make honey"); it carries a verb from the list below ("is based in Vermont", "was founded");
# or its first word is a third-person verb form, a plural-looking word ending in "s" that is followed by more item
# words other than a connector ("produces honey", "bottles syrup", "supplies farms"). "peaches in syrup", "dates and
# figs" and one-word names ("pickles") still count; a plural-noun-first name such as "Brussels sprouts" is lost.
_NOT_ITEM = re.compile(r"^(?:in|from|at|near|on|of|by|for|to|with|and|since|who|that|which|where|when|"
                       r"i|we|they|he|she|it|its|our|their|his|her|this|these|those|there|"
                       r"make|produce|sell|grow|own|ship|bottle|supply|offer|run|operate)\b"
                       r"|\b(?:is|are|was|were|am|be|been|has|have|had|does|did|based|located|founded|established|"
                       r"makes|sells|owns|lives|grows|ships|produces|started|began)\b", re.I)
_VERB_FIRST = re.compile(r"^(?!(?:\w*(?:ss|us|is)\b))\w{3,}s\s+(?!(?:and|in|with|of|n|&)\b)\S", re.I)


def _named_in(text):
    # The maker clause comes first and the item clause must follow it: "Maple Valley honey, made by Maple Valley" is
    # the maker named after the product, not the name typed after its maker.
    clauses = [clause.strip() for clause in re.split(r"[;\n,]", text)]
    makers = [(at, match[1].strip().rstrip(".!")) for at, clause in enumerate(clauses)
              if (match := re.fullmatch(r"made by\s+(.+?)\s*", clause, re.I))]
    if len(makers) != 1 or not makers[0][1]:
        return None
    made_at, maker = makers[0]
    lead = re.compile(re.escape(maker) + r"\s+(.+)", re.I)
    found = []  # (clause index, name) of every clause that leads with the maker, wherever it sits
    for at, clause in enumerate(clauses):
        match = lead.fullmatch(clause)
        if not match:
            continue
        rest = match[1].strip().rstrip(".!").strip()
        bad = not rest or _HEDGE.search(rest) or _NOT_ITEM.search(rest) or _VERB_FIRST.search(rest)
        found.append((at, None if bad else label_reader.identity_text("name", rest)))
    return found[0][1] if len(found) == 1 and found[0][0] > made_at else None


def owner_named_item(texts):
    """The product name the owner typed right after naming its maker: "made by Maple Valley, Maple Valley dark and robust
    maple syrup" -> "dark and robust maple syrup". Only a clause of the same message that starts with the exact made-by
    phrase (a word boundary after it) and adds plain item words counts; a hedge, question, price, digit or a clause that
    describes the maker ("Maple Valley is based in Vermont") gives None, as does a clause that only repeats the maker.
    Like an "it is ..." line, the result is the owner's own field and so outranks the photo read; the latest message wins."""
    return next((name for text in reversed(list(texts)) if (name := _named_in(text))), None)


def owner_typed_item(texts, plain):
    """The owner's own item name from either form, the one typed last winning: `plain` is the "it is ..." reader
    (job.owner_item) and the made-by form is owner_named_item's. A later message that gives neither keeps the earlier
    one; inside one message the made-by clause follows the "it is" opening, so it wins there."""
    return next((name for text in reversed(list(texts)) if (name := _named_in(text) or plain(text))), None)


def _maker(phrase, evidence, makers):
    if not phrase:
        return Maker("absent")
    label = evidence.get("brand_on_label")
    if label and evidence["confidence"]["brand"] >= 0.8:
        tokens = lambda value: set(re.findall(r"[^\W_]+", claims.fold(value)))
        if not tokens(phrase) & tokens(label):
            return Maker("contradictory", phrase)
    fold = claims.fold(phrase)
    exact, near = [], []
    for key, record in makers.items():
        if record.get("hidden") is True:
            continue
        names = (key, record["name"])
        if any(fold == claims.fold(n) for n in names):
            exact.append((key, record))
        elif any(_near(fold) == _near(n) for n in names):
            near.append((key, record))
    if len(exact) == 1:
        return Maker("known", phrase, *exact[0])
    if not exact and len(near) == 1:
        return Maker("near", phrase, *near[0])
    return Maker("ambiguous" if exact or near else "new", phrase)


def _duplicates(item, products, makers, clover):
    if not item:
        return ()
    key = claims.fold(item)
    return tuple(source for source, hit in (
        ("catalog", any(key == claims.fold(p["name"]) for p in products if p.get("status") != "held")),
        ("makers", any(key in (claims.fold(k), claims.fold(m["name"])) for k, m in makers.items() if not m.get("hidden"))),
        ("clover", clover is not None and any(key == claims.fold(i.name) for i in clover.items)),
    ) if hit)


class MissingInfo:
    def __init__(self, pinned):
        _, files, self.replies = pinned
        self.rules = json.loads(files[RULES])
        self.essentials = {rule["id"]: rule for rule in self.rules["essentials"]}

    def decide(self, reading=None, *, price=OwnerPrice(), owner_item=None, owner_texts=(), products=(), makers=None,
               clover=None, ask_counts=None, answered=(), duplicate_confirmed=False, near_maker_confirmed=None):
        """Return a pure decision over S2 evidence and projected inputs.

        `clover` is an optional already-loaded local Snapshot, not a client; only
        names are inspected. Receipts can use rule IDs, not finance or till rows.
        `owner_item` is a field explicitly set by the owner, not a caption dump.
        History inputs are durable question IDs supplied by the composer.
        `near_maker_confirmed` is the owner's answer to the near_maker question: True reuses the matched record,
        False keeps the owner-named maker as new, None (unanswered) asks once.
        """
        evidence, makers, ask_counts = reading or {}, makers or {}, ask_counts or {}
        templates = self.replies["questions"]
        caps = self.replies["caps"]
        limit = min(self.rules["max_questions"], caps["max_questions_per_reply"])
        minimum = self.essentials["identity"]["min_confidence"]
        confidence = evidence.get("confidence", {})
        photo_item = evidence.get("item") if evidence.get("is_product") is True and confidence.get("item", 0) >= minimum else None
        item = label_reader.identity_text("name", owner_item, title=True) or photo_item
        kind = evidence.get("kind") if photo_item else None
        defaults = self.rules["kind_default_category"]
        guess = evidence.get("category_guess") if kind and confidence.get("category", 0) >= minimum else None
        # A non-food item may sit only on a non-food shelf: a confident flowers read is kept (golden 12),
        # household items and any food-shelf guess fall back to the kind default (general).
        if kind == "non-food" and guess not in NON_FOOD_CATEGORIES:
            guess = None
        category = guess or defaults.get(kind)

        amount = price.amount if not price.unresolved and re.fullmatch(r"[0-9]{1,6}\.[0-9]{2}", price.amount or "") else None
        # A package is ordinarily sold by the item, not the pound. Fresh/unclassified
        # and explicit unsupported units (including basket) must not silently default.
        unit = price.unit if price.unit in ("item", "pound") else None
        if amount and price.unit is None and kind in {"food", "drink", "non-food"}:
            unit = "item"
        missing_ids = {"identity": not item, "selling_price": not amount, "price_unit": bool(amount and not unit)}
        missing = tuple(q for q in self.rules["ask_order"] if missing_ids[q])
        questions = []

        def add(qid, sentence, attempts):
            if (qid not in answered and ask_counts.get(qid, 0) < attempts and len(questions) < limit
                    and len(" ".join([*(v for _, v in questions), sentence])) <= caps["question_max_chars"]):
                questions.append((qid, sentence))
                return True
            return False

        for qid in missing:
            if not item and qid != "identity":
                break  # first find out what it is; no price read-back or extra ask on a non-product
            rule = self.essentials[qid]
            template = rule["question_when_unit_said"] if qid == "selling_price" and unit else rule["question"]
            add(qid, templates[template], self.rules["max_asks_per_essential"])

        duplicates = _duplicates(item, products, makers, clover)
        if duplicates and not duplicate_confirmed:
            add("duplicate", DUPLICATE, 1)
            missing += ("duplicate",)  # a skipped or exhausted question does not authorize adding a twin
        maker = _maker(_owner_maker(owner_texts, item), evidence, makers) if item else Maker("unidentified")
        note = ""
        if maker.state == "near":
            assert maker.record is not None
            if near_maker_confirmed is True:
                maker = Maker("known", maker.phrase, maker.key, maker.record)  # owner confirmed the existing maker
            elif near_maker_confirmed is False:
                maker = Maker("new", maker.phrase)  # owner said it is a different maker; S4 may research it
            elif not add("near_maker", templates["ask_near_maker"].format(maker=maker.record["name"]), 1):
                # Do not treat an unconfirmed near-match as grounds for a research call.
                maker = Maker("near", maker.phrase)
        if maker.state == "contradictory":
            note = self.replies["brackets"]["parts"]["maker_left_off_label"].format(brand=evidence["brand_on_label"])
        return Decision(bool(item), item, category, OwnerPrice(amount, unit, price.unresolved), maker, duplicates,
                        missing, tuple(questions), note)
