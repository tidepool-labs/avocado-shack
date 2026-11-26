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
    name_from_photo: bool = False  # a made-by name that disagreed with a confident photo read was not used

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
# A clause after the maker is either an item name ("dark and robust maple syrup", "Brussels sprouts") or a sentence
# about the maker ("is based in Vermont", "works in Vermont", "produces honey"). A sentence needs a verb; a name is a
# noun phrase. English third-person verbs and plural nouns share one shape ("works"/"sprouts"), so no single word list
# or shape rule separates them (four returns on #634). _maker_sentence() therefore uses four independent tests, each
# failing closed (None keeps the photo read and the identity question). They are a first layer only: against a
# confident photo read, decide() uses a made-by name only when agrees_with_photo() holds, i.e. it repeats a photo word
# and adds only plain modifiers (no connector, verb or verb-shaped word); otherwise the photo name stays and the card
# says so (rule-29 disposition A, t_8bbd055e):
#  1. it opens with a word that cannot start an item name: preposition, conjunction, relative word or pronoun
#     ("in Vermont", "and Sons", "that sells honey", "we make honey");
#  2. it carries a copula, auxiliary or a past participle that only describes a business ("is based", "was founded",
#     "located in", "family owned"), anywhere in the clause;
#  3. its first word is a finite maker verb: a closed set of base forms that are not also food words ("make honey",
#     "produce honey"), or the third-person form of any maker activity verb, including ones that double as nouns
#     ("works", "lives", "bakes", "crafts", "roasts");
#  4. structure, not vocabulary, for verbs no list names: (a) a lowercase first word shaped like a third-person verb
#     (ends in "s", not "ss"/"us"/"is") followed by an object rather than a connector ("whittles spoons", "bottles
#     syrup"); (b) a lowercase preposition followed by a capitalized word, i.e. a place or a business ("whittles in
#     Vermont", "sold at Costco"); (c) a time or frequency word anywhere ("opened last year", "bakes daily", "for
#     three generations"); (d) a lowercase past-tense first word ("-ed") that stands alone or is followed by a
#     function word rather than a noun ("moved here", "expanded in 2019", "relocated to Barre").
# Item names keep their typed shape: a capitalized origin word ("Brussels sprouts", "Swiss cheese"), connectors
# ("peaches in syrup", "dates and figs"), one plural word ("pickles"), participle adjectives before a noun ("smoked
# salmon", "cured salami", "smoked and cured ham"). A lowercase plural-first name followed by a noun ("greens mix")
# falls back to the photo read.
_OPENER = frozenset("in from at near on of by for to with and since who that which where when whose "
                    "i we they he she it its it's our their his her my this these those there here".split())
_STATEMENT = frozenset("is are was were am be been being has have had having does did will would could should shall "
                       "might based located founded established started began begun opened owned operated "
                       "headquartered situated family-owned".split())
_FIRST_VERB = frozenset("make produce sell grow own operate supply offer manufacture create provide deliver distribute "
                        "import specialize specialise".split())
# Third-person forms only, as the first word. Verbs whose plural noun is a common one-word product ("rolls",
# "blends", "mixes", "preserves", "spreads") are left to test 4.
_ACTIVITY = ("make produce sell grow own operate supply offer manufacture create provide deliver distribute import "
             "export specialize specialise work live run ship bottle bake brew craft roast raise cook harvest farm "
             "source ferment smoke cure press pick serve design build hand-make hand-craft hand-pour").split()
_THIRD_PERSON = frozenset(word + ("es" if re.search(r"(?:s|x|z|ch|sh|o)$", word) else "s") if not word.endswith("y")
                          or word[-2] in "aeiou" else word[:-1] + "ies" for word in _ACTIVITY)
_CONNECTOR = frozenset("and & n with in of".split())
_PLACE_PREPOSITION = frozenset("in at from near outside around across throughout since".split())
_TIME = frozenset("last ago yesterday today tonight daily weekly monthly yearly annually every always recently lately "
                  "nowadays year years month months week weeks decade decades generation generations".split())
_AFTER_PAST = (_OPENER - {"and"}) | _TIME | {"a", "an", "the"}


def _maker_sentence(rest):
    words = re.findall(r"[^\W\d_][\w'’-]*|&", rest)
    if not words:
        return True
    low = [word.lower().replace("’", "'") for word in words]
    first = low[0]
    if first in _OPENER or first in _FIRST_VERB or first in _THIRD_PERSON or _STATEMENT.intersection(low):
        return True
    if _TIME.intersection(low):
        return True
    if (words[0].islower() and len(first) >= 4 and first.endswith("s") and not first.endswith(("ss", "us", "is"))
            and len(low) > 1 and low[1] not in _CONNECTOR):
        return True
    if words[0].islower() and len(first) >= 4 and first.endswith("ed") and (len(low) == 1 or low[1] in _AFTER_PAST):
        return True
    return any(word in _PLACE_PREPOSITION and words[at].islower() and words[at + 1][:1].isupper()
               for at, word in enumerate(low[:-1]))


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
        bad = not rest or _HEDGE.search(rest) or _maker_sentence(rest)
        found.append((at, None if bad else label_reader.identity_text("name", rest)))
    return found[0][1] if len(found) == 1 and found[0][0] > made_at else None


def owner_named_item(texts):
    """The product name the owner typed right after naming its maker: "made by Maple Valley, Maple Valley dark and robust
    maple syrup" -> "dark and robust maple syrup". Only a clause of the same message that starts with the exact made-by
    phrase (a word boundary after it) and adds plain item words counts; a hedge, question, price, digit or a clause that
    describes the maker ("Maple Valley is based in Vermont") gives None, as does a clause that only repeats the maker.
    Unlike an "it is ..." line it is read out of a sentence, so decide() (owner_named) uses it only when no confident
    photo read disagrees with it; the latest message wins."""
    return next((name for text in reversed(list(texts)) if (name := _named_in(text))), None)


def owner_typed_form(texts, plain):
    """("it_is" | "made_by", name) for the owner's own item name, the form typed last winning, or (None, None):
    `plain` is the "it is ..." reader (job.owner_item) and the made-by form is owner_named_item's. A later message that
    gives neither keeps the earlier one; inside one message the made-by clause follows the "it is" opening, so it wins
    there. The two forms differ in weight: an "it is ..." line is the owner's item field and always outranks the photo;
    a made-by name is read out of a sentence, so decide() lets it replace only a photo read it agrees with."""
    for text in reversed(list(texts)):
        if name := _named_in(text):
            return "made_by", name
        if name := plain(text):
            return "it_is", name
    return None, None


def owner_typed_item(texts, plain):
    """The owner's own item name from either form, the one typed last winning (see owner_typed_form)."""
    return owner_typed_form(texts, plain)[1]


_FILLER = frozenset("and & n of the with a an in".split())
# Words a modifier of the photo's own name never needs. A made-by name that adds one of them to the photo words is a
# sentence about the maker ("whittles with maple syrup", "sells maple syrup in Vermont"), not a fuller item name.
_NOT_MODIFIER = ((_OPENER | _PLACE_PREPOSITION | _CONNECTOR | _STATEMENT | _TIME | _FIRST_VERB | _THIRD_PERSON
                  | {"of", "the", "a", "an", "or", "but", "so", "than", "via"}) - {"and", "&", "n"})


def _fold_plural(word):
    return word[:-1] if len(word) > 3 and word.endswith("s") and not word.endswith("ss") else word


def _name_words(value):
    return {_fold_plural(word) for word in re.findall(r"[^\W\d_]+", claims.fold(value or ""))} - _FILLER


def _verb_shaped(word):
    # A third-person verb and a plural noun share this shape ("whittles"/"sprouts"); as an added word it is not trusted.
    return len(word) >= 4 and word.endswith("s") and not word.endswith(("ss", "us", "is"))


def agrees_with_photo(name, photo_item):
    """A made-by name agrees with a confident photo read when it repeats at least one of the photo's content words (one
    plural s folded) and every word it adds is a plain modifier: no function word other than "and", no verb and no
    verb-shaped word. "dark and robust maple syrup", "maple syrups" and "Grade A syrup" agree with "maple syrup",
    "Calabrese salamini" with "Calabrese Mini Salami". "whittles with maple syrup", "sells maple syrup in Vermont" and
    "Pours maple syrup" do not: decide() then keeps the photo read and the card says so. This is structural, not a
    vocabulary of maker sentences: an added word that could be a verb or a connector is never trusted."""
    photo = _name_words(photo_item)
    words = re.findall(r"[^\W\d_]+(?:-[^\W\d_]+)*", claims.fold(name or ""))
    if not photo or not words or not {_fold_plural(word) for word in words} & photo:
        return False
    added = [word for word in words if _fold_plural(word) not in photo and word not in ("and", "&", "n", "a")]
    return not any(word in _NOT_MODIFIER or _verb_shaped(word) for word in added)


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

    def decide(self, reading=None, *, price=OwnerPrice(), owner_item=None, owner_named=None, owner_texts=(), products=(),
               makers=None, clover=None, ask_counts=None, answered=(), duplicate_confirmed=False, near_maker_confirmed=None):
        """Return a pure decision over S2 evidence and projected inputs.

        `clover` is an optional already-loaded local Snapshot, not a client; only
        names are inspected. Receipts can use rule IDs, not finance or till rows.
        `owner_item` is a field explicitly set by the owner, not a caption dump.
        `owner_named` is the name he typed after its maker (owner_typed_form "made_by"): it names the item when there is
        no confident photo read or when it agrees with that read; against a confident photo it does not agree with,
        the photo read is kept and `name_from_photo` tells the composer to say so (on the card he corrects it with
        "call it ...", the card-out name edit; before a card, an "it is ..." line outranks the photo). When the label also
        contradicts the maker he named, no name is used and the identity question is asked instead (checkpoint 2, A).
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
        name_from_photo = bool(not owner_item and owner_named and photo_item
                               and not agrees_with_photo(owner_named, photo_item))
        identity_conflict = bool(name_from_photo and _maker(_owner_maker(owner_texts, photo_item), evidence,
                                                             makers).state == "contradictory")
        if identity_conflict:
            # Checkpoint 2 option A (t_3eb38fab): his made-by name disagrees with the confident photo read AND the label
            # contradicts the maker he named. The one bracket cannot carry both explanations, and the photo and the
            # caption disagree on item and maker alike, so no card yet: neither name is used and the existing identity
            # question is asked. His "it is ..." answer then names it and the card carries only the label explanation.
            photo_item, name_from_photo = None, False
        typed = owner_item or (None if name_from_photo or identity_conflict else owner_named)
        item = label_reader.identity_text("name", typed, title=True) or photo_item
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
                        missing, tuple(questions), note, name_from_photo)
