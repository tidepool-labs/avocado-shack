"""HASS-NPP-A: the new-product pipeline's runtime assets and eval-case inputs are what the design says they are.

Every test names the contract it protects and the believable bug that would break it (CI-ARTICLE-1). Stdlib only: the schema
checker below supports just the keywords the NPP schemas use (type, enum, required, properties, additionalProperties,
items, min/max Items, minimum, maximum, minLength, maxLength, pattern, and $ref to a top-level key of the same file).
No network, no model, no live Hass: files under hass/npp, hass/tests/npp and the generator script only.
"""
import importlib.util
import itertools
import json
import re
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
ASSETS = ROOT / "hass" / "npp" / "assets"
CASES = ROOT / "hass" / "tests" / "npp" / "cases"
CHAOS_PHOTOS = ROOT / "hass" / "tests" / "chaos" / "photos"
PINS = ROOT / "hass" / "npp" / "pins.json"
CATEGORIES = ("fruit", "vegetables", "dairy", "eggs", "meat", "pantry", "drinks", "bread", "flowers", "general")
KINDS = ("food", "drink", "fresh", "non-food")
NUMBER_WORDS = set("zero one two three four five six seven eight nine ten eleven twelve thirteen fourteen fifteen sixteen seventeen "
                   "eighteen nineteen twenty thirty forty fifty sixty seventy eighty ninety hundred thousand dozen half once twice".split())
SENTENCE_END = re.compile(r"[.!?]+(?=\s|$)")


def load(path):
    return json.loads(Path(path).read_text(encoding="utf-8"))


def asset(rel):
    return load(ASSETS / rel)


def script(name):
    spec = importlib.util.spec_from_file_location(name, ROOT / "scripts" / "hass" / f"{name}.py")
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def validate(schema, value, root=None, where="$"):
    """Problems (strings) of `value` against the schema subset described in the module docstring."""
    root = root if root is not None else schema
    if "$ref" in schema:
        return validate(root[schema["$ref"]], value, root, where)
    problems = []
    types = schema.get("type")
    if types is not None:
        types = [types] if isinstance(types, str) else types
        names = {"string": str, "boolean": bool, "object": dict, "array": list, "null": type(None)}
        ok = False
        for t in types:
            if t == "integer":
                ok = ok or (isinstance(value, int) and not isinstance(value, bool))
            elif t == "number":
                ok = ok or (isinstance(value, (int, float)) and not isinstance(value, bool))
            else:
                ok = ok or isinstance(value, names[t])
        if not ok:
            return [f"{where}: expected {types}, got {type(value).__name__}"]
    if "enum" in schema and value not in schema["enum"]:
        problems.append(f"{where}: {value!r} not in enum")
    if isinstance(value, str):
        if "minLength" in schema and len(value) < schema["minLength"]:
            problems.append(f"{where}: shorter than {schema['minLength']}")
        if "maxLength" in schema and len(value) > schema["maxLength"]:
            problems.append(f"{where}: longer than {schema['maxLength']}")
        if "pattern" in schema and not re.search(schema["pattern"], value):
            problems.append(f"{where}: does not match {schema['pattern']}")
    if isinstance(value, (int, float)) and not isinstance(value, bool):
        if "minimum" in schema and value < schema["minimum"]:
            problems.append(f"{where}: below {schema['minimum']}")
        if "maximum" in schema and value > schema["maximum"]:
            problems.append(f"{where}: above {schema['maximum']}")
    if isinstance(value, list):
        if "minItems" in schema and len(value) < schema["minItems"]:
            problems.append(f"{where}: fewer than {schema['minItems']} items")
        if "maxItems" in schema and len(value) > schema["maxItems"]:
            problems.append(f"{where}: more than {schema['maxItems']} items")
        if "items" in schema:
            for i, item in enumerate(value):
                problems += validate(schema["items"], item, root, f"{where}[{i}]")
    if isinstance(value, dict):
        for key in schema.get("required", []):
            if key not in value:
                problems.append(f"{where}: missing {key}")
        props = schema.get("properties", {})
        for key, item in value.items():
            if key in props:
                problems += validate(props[key], item, root, f"{where}.{key}")
            elif schema.get("additionalProperties") is False:
                problems.append(f"{where}: unexpected {key}")
    return problems


def sentences(text):
    return len(SENTENCE_END.findall(text))


def render(template, slots, phrases):
    """Mirror of the grammar in copy-templates.json: {slot}, {slot|cap}, {slot|a}, {phrase:<bank>}."""
    def fill(match):
        token = match.group(1)
        if token.startswith("phrase:"):
            return phrases[token[7:]]
        name, _, transform = token.partition("|")
        value = slots[name]
        if transform == "cap":
            return value[:1].upper() + value[1:]
        if transform == "a":
            return ("an " if value[:1].lower() in "aeiou" else "a ") + value
        return value
    return re.sub(r"\{([^{}]+)\}", fill, template)


def applicable(phrase, kind, category):
    if kind not in phrase["kinds"]:
        return False
    if "categories" in phrase and category not in phrase["categories"]:
        return False
    return category not in phrase.get("categories_except", ())


def default_phrases(phrases_doc, template, kind, category):
    out = {}
    for slot, bank in template.get("phrases", {}).items():
        found = [p for p in phrases_doc["phrases"] if p["bank"] == bank and p.get("default") and applicable(p, kind, category)]
        out[slot] = found[0]["text"] if len(found) == 1 else None
    return out


def words(text):
    """The no-copying gate's normalisation (copy-templates.json no_copying): lower-case letters and digits, any other character splits."""
    return re.findall(r"[^\W_]+", text.lower())


def spans(text, n):
    w = words(text)
    return {tuple(w[i:i + n]) for i in range(len(w) - n + 1)}


def shared_span(a, b, n=8):
    """True when the two descriptions share a run of n or more words (design 3.2 no-copying)."""
    return bool(spans(a, n) & spans(b, n))


def catalog():
    """(product id, category, description) of every record of the live catalog snapshot in the repo."""
    data = json.loads((ROOT / "storefront-mockup" / "shop-data.json").read_text(encoding="utf-8"))
    return [(p["id"], p["category"], p["name"], p["description"]) for p in data["products"] if p.get("description")]


def kind_key(category, kind):
    return "flowers" if (category, kind) == ("flowers", "fresh") else kind


def resolve_default(templates_doc, kind, category, item, published):
    """Steps 3 and 4 of copy-templates.json no_copying.resolution: rung a, else rung b, else a failing case (AssertionError)."""
    by_id = {t["id"]: t for t in templates_doc["templates"]}
    for rung in templates_doc["defaults"]["description"][kind_key(category, kind)]:
        text = render(by_id[rung]["text"], {"item": item}, {})
        if not any(shared_span(text, other) for other in published):
            return rung, text
    raise AssertionError(f"both default rungs copy a published description: {item}")


class SchemaCheckerTest(unittest.TestCase):
    def test_checker_rejects_what_the_npp_schemas_forbid(self):
        """Contract: the stdlib checker used below really rejects wrong types, extras and bad enums (a checker that accepts everything would make every schema test pass)."""
        schema = {"type": "object", "required": ["a"], "additionalProperties": False,
                  "properties": {"a": {"type": "string", "enum": ["x"], "maxLength": 1}, "b": {"type": ["integer", "null"], "minimum": 0}}}
        self.assertEqual(validate(schema, {"a": "x", "b": None}), [])
        for bad in ({}, {"a": "y"}, {"a": "x", "c": 1}, {"a": "x", "b": -1}, {"a": "x", "b": True}, [], {"a": "xx"}):
            self.assertTrue(validate(schema, bad), bad)


class LimitsTest(unittest.TestCase):
    def test_npp_limits_reproduces_the_gallery_style_table(self):
        """Contract: limits come from the measured TSV, not from memory. Bug: a mistyped percentile or a changed TSV that no longer matches the published table."""
        limits_script = script("npp_limits")
        limits = limits_script.build(limits_script.load_rows())
        skill = (ASSETS / "hass-gallery-style" / "SKILL.md").read_text(encoding="utf-8")
        published = {}
        for line in skill.splitlines():
            cells = [c.strip() for c in line.strip().strip("|").split("|")]
            if len(cells) == 4 and re.fullmatch(r"\d+", cells[1]):
                published[cells[0]] = cells
        self.assertEqual(limits["records"], 105)
        for key, label, _column in limits_script.FIELDS:
            f = limits["fields"][key]
            want = published[label]
            self.assertEqual(
                [str(f["present"]), f"{f['words']['p50']} / {f['words']['p90']}", f"{f['chars']['p50']} / {f['chars']['p90']}"],
                want[1:], label)
        self.assertEqual(limits["description_sentence_endings"], {"2": 88, "3": 17})
        self.assertEqual(limits["badges"], {"organic": 13, "new": 0})

    def test_committed_limits_json_is_the_generator_output(self):
        """Contract: limits.json is generated, never edited by hand. Bug: a hand edit that drifts from the TSV."""
        limits_script = script("npp_limits")
        committed = (ASSETS / "hass-gallery-style" / "limits.json").read_text(encoding="utf-8")
        self.assertEqual(committed, limits_script.render(limits_script.build(limits_script.load_rows())))
        self.assertEqual(limits_script.main(["--check"]), 0)

    def test_soft_and_hard_limits_fit_the_site_content_model(self):
        """Contract: the hard limits NPP enforces are inside the content model's own limits (design 2.2). Bug: a hard limit above what the site accepts."""
        from hass.content_model import TEXT_LIMITS
        limits = asset("hass-gallery-style/limits.json")["limits"]
        self.assertLessEqual(limits["description"]["hard_max_chars"], TEXT_LIMITS["product"]["description"])
        self.assertLessEqual(limits["maker_story"]["hard_max_chars"], TEXT_LIMITS["maker"]["story"])
        for part in limits.values():
            self.assertLess(part["soft_max_chars"], part["hard_max_chars"])


class GoldenTest(unittest.TestCase):
    def test_goldens_and_bad_cards_match_the_card_schema(self):
        """Contract: the twelve goldens and the calibration cards share one card shape. Bug: a malformed golden silently skipped by the judge or the validator."""
        schema = asset("hass-gallery-style/card.schema.json")
        files = sorted((ASSETS / "hass-gallery-style" / "golden").glob("*.json")) + sorted((ASSETS / "hass-style-judge" / "calibration" / "bad").glob("*.json"))
        self.assertEqual(len(list((ASSETS / "hass-gallery-style" / "golden").glob("*.json"))), 12)
        for path in files:
            self.assertEqual(validate(schema, load(path)), [], path.name)

    def test_goldens_equal_their_live_tsv_rows_and_fit_the_limits(self):
        """Contract: a golden is a live record, not paraphrased. Bug: a golden that differs from gallery-fields.tsv, or one outside the hard limits it is supposed to teach."""
        limits_script = script("npp_limits")
        rows = {r["id"]: r for r in limits_script.load_rows()}
        limits = asset("hass-gallery-style/limits.json")["limits"]
        for path in sorted((ASSETS / "hass-gallery-style" / "golden").glob("*.json")):
            g = load(path)
            card = g["card"]
            if g["product_id"] in rows:  # eleven are in the 105 packaged records; the bouquet is the one fresh-view card
                row = rows[g["product_id"]]
                self.assertEqual((card["brand"], card["name"], card["description"], card["origin"]), (row["brand"], row["name"], row["description"], row["origin"]), path.name)
            self.assertLessEqual(len(card["description"]), limits["description"]["hard_max_chars"], path.name)
            self.assertIn(sentences(card["description"]), (1, 2, 3), path.name)
            story = (card["meet_the_maker"] or {}).get("story")
            if story:
                self.assertLessEqual(len(story), 600)
            self.assertNotIn("$", json.dumps(card), "a golden never carries a price symbol")


class IdentifyAssetsTest(unittest.TestCase):
    def test_identify_examples_validate_against_the_schema(self):
        """Contract: S2 few-shot examples are valid outputs of the schema the runtime will enforce. Bug: an example the schema would reject, teaching the model a shape code refuses."""
        schema = asset("hass-product-identify/identify.schema.json")
        examples = asset("hass-product-identify/examples.json")["examples"]
        self.assertEqual(len(examples), 6)
        for ex in examples:
            self.assertEqual(validate(schema, ex["output"]), [], ex["photo"])
            self.assertTrue((CHAOS_PHOTOS / ex["photo"].split(":")[-1].split("/")[-1]).exists(), ex["photo"])
        self.assertEqual(set(schema["properties"]["category_guess"]["enum"]) - {None}, set(CATEGORIES))

    def test_identify_schema_has_no_price_or_cost_field(self):
        """Contract: S2 never reads a price, cost or quantity (design 1.9). Bug: a schema field that lets the vision model return one."""
        props = set(asset("hass-product-identify/identify.schema.json")["properties"])
        self.assertFalse({p for p in props if re.search(r"price|cost|quantity|qty|origin|town|maker", p)})


class MissingInfoTest(unittest.TestCase):
    def test_every_question_exists_and_the_budget_is_two(self):
        """Contract: S3 asks at most two questions, each from a fixed reply template. Bug: a rule that names a question id with no template."""
        rules = asset("hass-missing-info/missing-info.json")
        replies = asset("hass-npp-reply/reply-templates.json")
        self.assertEqual(rules["max_questions"], 2)
        self.assertEqual(rules["ask_order"], [e["id"] for e in rules["essentials"]])
        for e in rules["essentials"]:
            self.assertIn(e["question"], replies["questions"])
            if "question_when_unit_said" in e:
                self.assertIn(e["question_when_unit_said"], replies["questions"])
        self.assertIn(rules["maker_resolution"]["near_match"]["question"], replies["questions"])

    def test_price_is_never_read_from_a_photo_model_or_web_page(self):
        """Contract: selling price comes only from the owner's words (design 1.9). Bug: a missing-info source list that allows a model or photo price."""
        price = next(e for e in asset("hass-missing-info/missing-info.json")["essentials"] if e["id"] == "selling_price")
        self.assertTrue({"photo", "model", "label", "web_page"} <= set(price["never_from"]))

    def test_brand_maker_town_are_never_asked_for(self):
        """Contract: brand, maker and town are omitted, not asked (design S3; G 2026-11-18 14:00 lets research supply them, never a question). Bug: an ask for maker."""
        rules = asset("hass-missing-info/missing-info.json")
        self.assertTrue({"brand", "maker", "town", "story"} <= set(rules["omit_dont_ask"]))
        self.assertFalse({e["id"] for e in rules["essentials"]} & {"brand", "maker", "town"})
        self.assertEqual(set(rules["kind_default_category"].values()) - set(CATEGORIES), set())


class ReplyTemplatesTest(unittest.TestCase):
    def test_questions_and_guards_respect_their_caps(self):
        """Contract: design 1.4: questions at most 160 characters, guards one line, a fallback bracket at most 60. Bug: a long or two-sentence guard that re-creates the wall of text."""
        r = asset("hass-npp-reply/reply-templates.json")
        for key, text in r["questions"].items():
            self.assertLessEqual(len(text), r["caps"]["question_max_chars"], key)
            self.assertEqual(text.count("?"), 1, key)
        for key, text in r["guards"].items():
            if key != "guard_note":
                self.assertEqual(sentences(text), 1, key)
        for key, part in r["brackets"]["parts"].items():
            self.assertLessEqual(len("(" + part.format(brand="Quarry Lane", claim="immune support") + ")"), r["caps"]["bracket_max_chars"], key)
        self.assertEqual(set(r["brackets"]["compose"]["drop_order"]), set(r["brackets"]["parts"]))

    def test_ready_prompt_carries_a_version_tag_and_nothing_private(self):
        """Contract: R2.1 every prompt names `yes <code>-<n>`. Bug: a prompt without the version, or one that mentions cost or quantity."""
        r = asset("hass-npp-reply/reply-templates.json")
        self.assertIn("yes {code}-{n}", r["prompts"]["ready"])
        text = json.dumps({k: v for k, v in r.items() if k not in ("never_say", "about")})
        self.assertNotRegex(text.lower(), r"\bcost\b|\bquantity\b|\bqty\b")

    def test_replies_the_cases_quote_exist_in_the_templates(self):
        """Contract: a case that expects a reply line expects one the pipeline can say. Bug: a case string that drifted from the template, so the real run could never pass."""
        r = asset("hass-npp-reply/reply-templates.json")
        texts = [t for group in ("questions", "prompts", "guards", "confirm", "edits") for t in r[group].values() if isinstance(t, str)]
        bracket = r["brackets"]
        rule = bracket["compose"]
        ordered = [bracket["parts"][name] for name in reversed(rule["drop_order"])]
        # A quoted suffix can span the separator and a part, as in case 36.
        for count in range(1, len(ordered) + 1):
            for parts in itertools.combinations(ordered, count):
                note = rule["open"] + rule["separator"].join(parts) + rule["close"]
                if len(note) <= r["caps"]["bracket_max_chars"]:
                    texts.append(note)
        regexes = [re.compile(".+".join(re.escape(piece) for piece in re.split(r"\{\w+\}", t))) for t in texts]
        checked = 0
        for case in all_cases():
            for unit in units(case):
                for rep in unit["expect"].get("replies", []):
                    if rep.get("source", "").startswith("existing"):
                        continue
                    for need in rep.get("has_all", []):
                        checked += 1
                        self.assertTrue(any(rx.fullmatch(need) for rx in regexes) or any(need in t for t in texts), f"case {case['id']}: {need!r}")
        self.assertGreater(checked, 20)


class ResearchAssetsTest(unittest.TestCase):
    def test_default_allowlist_is_empty_and_the_denylist_is_exact_domains(self):
        """Contract: the G-maintained allowlist starts empty; the denylist is exact registered domains. Bug: a pre-filled allowlist, or a wildcard or URL in the denylist that matches too much."""
        sources = asset("hass-maker-research/sources.json")
        self.assertEqual(sources["allowlist"], [])
        for d in sources["deny_domains"]:
            self.assertRegex(d, r"^[a-z0-9-]+(\.[a-z0-9-]+)+$", d)
        self.assertEqual(len(sources["deny_domains"]), len(set(sources["deny_domains"])))

    def test_search_is_only_to_locate_and_carries_no_owner_digits(self):
        """Contract: G 2026-11-18 14:00: search only locates the official site; queries use the maker and town only. Bug: a query form that can carry price, cost, quantity or an owner sentence."""
        search = asset("hass-maker-research/sources.json")["discovery"]["search"]
        self.assertTrue(search["enabled"])
        self.assertLessEqual(search["max_queries"], 2)
        for form in search["query_forms"]:
            self.assertFalse(set(re.findall(r"\{(\w+)\}", form)) - set(search["query_slots_allowed"]), form)
            self.assertNotRegex(form, r"\d")
        self.assertTrue({"digits", "price", "cost", "quantity", "owner_sentence"} <= set(search["query_forbidden"]))

    def test_official_site_checks_require_identity_and_a_unique_candidate(self):
        """Contract: when not confident there is no story: identity checks are required, not optional, and exactly one domain may pass. Bug: a title match alone granting identity."""
        site = asset("hass-maker-research/sources.json")["official_site"]
        self.assertIn("name_in_title_or_site_name_or_main_heading", site["all_required"])
        self.assertIn("page_presents_itself_as_the_makers_own_site", site["all_required"])
        self.assertIn("exactly one registered domain passes", site["unique_candidate"])
        self.assertEqual(site["when_unsure"], "no story")
        self.assertNotIn("domain contains a folded token of the maker name", site["all_required"])

    def test_fact_schema_slots_and_nature_enum_match_the_copy_templates(self):
        """Contract: only typed slots the templates can use exist (R2.2). Bug: a fact slot with no template, or a nature value the article rule would render wrongly."""
        facts = asset("hass-maker-research/facts.schema.json")
        templates = asset("hass-listing-copy/copy-templates.json")
        slots = set(facts["properties"]["facts"]["items"]["properties"]["slot"]["enum"])
        self.assertEqual(slots, {"name", "town", "makes", "founded", "nature"})
        used = {t["slots"][s] for t in templates["templates"] if t["field"] == "story" for s in t["slots"]}
        self.assertTrue({"nature", "makes", "founded", "town", "maker_name"} <= used)
        for v in facts["nature_enum"]:
            self.assertRegex(v, r"^[a-z][a-z -]+$")
        sample = {"facts": [{"slot": "makes", "value": "dried figs", "url": "https://minersfigs.example/about", "quote": "Miners makes dried figs."}]}
        self.assertEqual(validate(facts, sample), [])
        sample["facts"][0]["slot"] = "award"
        self.assertTrue(validate(facts, sample))

    def test_verifier_prompt_keeps_the_three_verdicts_and_no_listing_context(self):
        """Contract: the entailment verifier is separate and sees one claim and one quote. Bug: a prompt that hands it the listing or owner words."""
        text = (ASSETS / "hass-maker-research" / "verify.md").read_text(encoding="utf-8")
        for verdict in asset("hass-maker-research/facts.schema.json")["verdicts"]:
            self.assertIn(verdict, text)
        self.assertNotRegex(text.lower(), r"owner'?s words:|listing:|price:")


class CopyTemplatesTest(unittest.TestCase):
    def setUp(self):
        self.t = asset("hass-listing-copy/copy-templates.json")
        self.p = asset("hass-listing-copy/voice-phrases.json")
        self.by_id = {x["id"]: x for x in self.t["templates"]}

    def test_templates_are_closed_declared_and_free_of_digits(self):
        """Contract: R2.2 every template declares its slots and sentences and carries no digit, currency or number word. Bug: a template that leaks a number or uses a slot it never declared."""
        self.assertEqual(len(self.by_id), len(self.t["templates"]))
        for tpl in self.t["templates"]:
            names = re.findall(r"\{([^{}]+)\}", tpl["text"])
            slots = {n.partition("|")[0] for n in names if not n.startswith("phrase:")}
            banks = {n[7:] for n in names if n.startswith("phrase:")}
            self.assertEqual(slots, set(tpl["slots"]), tpl["id"])
            self.assertEqual(banks, set(tpl.get("phrases", {}).values()), tpl["id"])
            self.assertEqual(set(tpl.get("phrases", {})), banks, tpl["id"])
            for slot_type in tpl["slots"].values():
                self.assertIn(slot_type, self.t["slot_types"], tpl["id"])
            literal = re.sub(r"\{[^{}]+\}", " ", tpl["text"])
            self.assertNotRegex(literal, r"[\d$¢%]", tpl["id"])
            self.assertFalse(NUMBER_WORDS & set(re.findall(r"[a-z]+", literal.lower())), tpl["id"])
            if tpl["sentences"]:
                self.assertEqual(sentences(render(tpl["text"], {s: "Word" for s in tpl["slots"]}, {b: "Phrase here." for b in banks})), tpl["sentences"], tpl["id"])
            self.assertTrue(set(tpl["kinds"]) <= set(KINDS), tpl["id"])
        self.assertTrue(all(t["field"] in ("name", "imageAlt", "description", "story") for t in self.t["templates"]))

    def test_story_templates_bind_a_kept_fact_and_declare_what_they_assert(self):
        """Contract: a story sentence binds at least one kept fact and the fixed text can assert only declared things. Bug: a story template with no fact slot, which would restate owner words as researched fact."""
        for tpl in self.t["templates"]:
            if tpl["field"] != "story":
                continue
            fact_slots = {tpl["slots"][s] for s in tpl["slots"]} & {"nature", "makes", "founded"}
            self.assertTrue(fact_slots, tpl["id"])
            self.assertTrue(set(tpl["requires_facts_any"]) <= fact_slots, tpl["id"])
            for need in tpl.get("requires_facts_all", []):
                self.assertIn(need, fact_slots, tpl["id"])
        self.assertEqual(set(self.t["defaults"]["story"]["order"]), {t["id"] for t in self.t["templates"] if t["field"] == "story"})
        for desc in (t for t in self.t["templates"] if t["field"] == "description"):
            self.assertFalse({"nature", "makes", "founded"} & set(desc["slots"].values()), "a description carries no researched fact")

    def test_phrases_assert_nothing_and_non_food_has_no_serving_words(self):
        """Contract: the voice phrase bank holds no factual assertion, number, hype or (for non-food) serving word. Bug: a phrase like 'Roasted in small batches.' or a glue blurb that says serve."""
        banned = set(self.p["banned_words"])
        non_food = set(self.p["non_food_banned_words"])
        ids = [x["id"] for x in self.p["phrases"]]
        self.assertEqual(len(ids), len(set(ids)))
        for ph in self.p["phrases"]:
            words = set(re.findall(r"[a-z'-]+", ph["text"].lower()))
            self.assertRegex(ph["text"], r"^[A-Z][^0-9$]+[.]$", ph["id"])
            self.assertEqual(sentences(ph["text"]), 1, ph["id"])
            self.assertFalse(words & banned, ph["id"])
            self.assertFalse(words & NUMBER_WORDS, ph["id"])
            self.assertLessEqual(len(ph["text"].split()), 7, ph["id"] + ": a phrase of 8+ words is itself a copyable span")
            self.assertTrue(set(ph["kinds"]) <= set(KINDS), ph["id"])
            if ph["kinds"] == ["non-food"]:
                self.assertFalse(words & non_food, ph["id"])

    def test_every_default_resolves_and_renders_within_limits(self):
        """Contract: the deterministic fallback always exists: every kind (and the flowers category) has two item-anchored rungs that need only the item slot and carry it in every sentence with no bank phrase: rung a (kind specific) with at most 5 fixed words between two name slots, rung b (the short universal one) with at most 2 and render inside the limits even for a long name. Bug: a kind or category with no default, or a default that needs a phrase or a slot code cannot bind."""
        limits = asset("hass-gallery-style/limits.json")["limits"]["description"]
        ladder = self.t["defaults"]["description"]
        self.assertEqual(set(ladder), {"food", "drink", "fresh", "flowers", "non-food"})
        long_item = "montana de oro sea salt tortilla chips"
        for key, rungs in ladder.items():
            self.assertEqual(len(rungs), 2, key)
            self.assertEqual(rungs[1], "desc-default-short", key)
            for n, rung in enumerate(rungs):
                tpl = self.by_id[rung]
                self.assertEqual((tpl["slots"], tpl.get("phrases", {})), ({"item": "item"}, {}), rung)
                kind = "fresh" if key == "flowers" else key
                self.assertIn(kind, tpl["kinds"], rung)
                if n == 0:
                    self.assertEqual(tpl.get("categories") == ["flowers"], key == "flowers", rung)
                runs = [len(run.split()) for run in tpl["text"].split("{item}")[1:-1]]
                self.assertTrue(runs and max(runs) <= (5, 2)[n], (rung, runs))
                self.assertEqual(tpl["text"].count("{item}"), 2, rung)
                text = render(tpl["text"], {"item": long_item}, {})
                self.assertLessEqual(len(text), limits["hard_max_chars"], rung)
                self.assertEqual(sentences(text), 2, rung)
        for kind in KINDS:
            for category in CATEGORIES:
                if category == "flowers" and kind != "fresh":
                    continue
                tpls = [self.by_id[r] for r in ladder[kind_key(category, kind)]]
                self.assertTrue(all(applicable(t, kind, category) for t in tpls), (kind, category))
        stories = [x for x in self.p["phrases"] if x.get("default")]
        self.assertEqual([x["bank"] for x in stories], ["story_close"], "only story_close has a default phrase")
        self.assertIn(self.t["defaults"]["name"], self.by_id)
        self.assertIn(self.t["defaults"]["imageAlt"], self.by_id)

    def test_no_selection_or_default_copies_the_catalog_and_fallbacks_do_not_copy_each_other(self):
        """Contract: design 3.2 no-copying (no 8+-word span shared with another catalog description) run for real over the 170-odd live descriptions: every renderable phrase combination, every default rung, and a sequence of published fallbacks. Bug: a fallback such as the flower default 'A little color for the kitchen table. No occasion required.' that is already the live bouquet text, or a phrase-only default that is identical for every product so the second published fallback copies the first."""
        records = catalog()
        self.assertGreater(len(records), 150)
        live = [r[3] for r in records]
        bouquet = next(r[3] for r in records if r[0] == "photo-product-006")
        self.assertTrue(shared_span(bouquet, "A little color for the kitchen table. No occasion required."), "negative control: the comparison finds the old flower default")
        by_bank = {}
        for ph in self.p["phrases"]:
            by_bank.setdefault(ph["bank"], []).append(ph)
        for tpl in self.t["templates"]:
            if tpl["field"] != "description" or not tpl.get("phrases"):
                continue
            for kind in tpl["kinds"]:
                for category in CATEGORIES:
                    if "categories" in tpl and category not in tpl["categories"] or category in tpl.get("categories_except", ()):
                        continue
                    banks = [[x for x in by_bank[b] if applicable(x, kind, category)] for b in tpl["phrases"].values()]
                    for combo in itertools.product(*banks):
                        slots = {"item": "zq item", "maker_name": "zm maker", "town": "zt town"}
                        text = render(tpl["text"], slots, dict(zip(tpl["phrases"], (x["text"] for x in combo))))
                        for other in live:
                            self.assertFalse(shared_span(text, other), (tpl["id"], kind, category, text, other))
        for key, rungs in self.t["defaults"]["description"].items():
            for rung in rungs:
                text = render(self.by_id[rung]["text"], {"item": "zq item"}, {})
                self.assertFalse(any(shared_span(text, other) for other in live), rung)
        published = list(live)
        kinds = {"fruit": "fresh", "vegetables": "fresh", "flowers": "fresh", "drinks": "drink", "general": "non-food"}
        rung_b = 0
        for _pid, category, name, _desc in records:
            got = resolve_default(self.t, kinds.get(category, "food"), category, name.lower(), published)
            rung_b += got[0].endswith("-b")
            published.append(got[1])
        self.assertLess(rung_b, len(records) // 4, "rung b is the rare second choice, not the norm")
        flower = resolve_default(self.t, "fresh", "flowers", "mixed flower bouquet", live)
        self.assertEqual(flower[0], "desc-flowers-default")
        self.assertFalse(shared_span(flower[1], bouquet))

    def test_a_colliding_fallback_takes_the_short_rung_and_brand_mates_stay_unique(self):
        """Contract: no_copying.resolution step 3: when rung a would share 8 words with an already published fallback, rung b (short fixed runs) is used and passes, including for two products of one brand and kind (shared prefix and suffix); two different names never publish the same text. Bug: a one-rung ladder that publishes the copy or crashes, or a rung whose fixed words let 'Fair Hills Farm black tea' and 'Fair Hills Farm chamomile tea' repeat 8 words."""
        first = resolve_default(self.t, "food", "pantry", "sea salt tortilla chips", [])
        second = resolve_default(self.t, "food", "pantry", "montana de oro sea salt tortilla chips", [first[1]])
        self.assertEqual((first[0], second[0]), ("desc-food-default", "desc-default-short"))
        self.assertTrue(shared_span(render(self.by_id["desc-food-default"]["text"], {"item": "montana de oro sea salt tortilla chips"}, {}), first[1]), "rung a really would have copied")
        self.assertFalse(shared_span(first[1], second[1]))
        tea = resolve_default(self.t, "drink", "drinks", "fair hills farm chamomile tea", [])
        mate = resolve_default(self.t, "drink", "drinks", "fair hills farm black tea", [tea[1]])
        self.assertEqual((tea[0], mate[0]), ("desc-drink-default", "desc-default-short"), "3 shared prefix words + 1 shared suffix word + the 4 fixed words of rung a is 8: rung a would copy")
        again = resolve_default(self.t, "drink", "drinks", "fair hills farm cinnamon black tea", [tea[1], mate[1]])
        self.assertEqual(again[0], "desc-default-short")
        self.assertFalse(any(shared_span(again[1], other) for other in (tea[1], mate[1])))

    def test_story_default_phrase_is_unique(self):
        """Contract: the one remaining default phrase (story_close) resolves to exactly one phrase for every kind. Bug: two defaults for one bank, so the story close would depend on file order."""
        for kind in KINDS:
            tpl = self.by_id["story-founded"]
            got = default_phrases(self.p, tpl, kind, "pantry")
            self.assertTrue(all(got.values()), kind)

    def test_alt_templates_never_write_illustration_or_a_price(self):
        """Contract: design 1.7: alt is plain words, no (illustration) added by Hass. Bug: an alt template that adds the suffix the site already adds, giving it twice."""
        for tpl in self.t["templates"]:
            if tpl["field"] == "imageAlt":
                self.assertNotIn("illustration", tpl["text"].lower())
                self.assertTrue(tpl["variants"])

    def test_selection_schema_accepts_ids_and_rejects_prose(self):
        """Contract: R2.2 the model can return template and phrase IDs only; there is no field for prose. Bug: a schema with a free-text field the model could fill with a fabricated sentence."""
        schema = asset("hass-listing-copy/listing.schema.json")
        good = {"name": {"template_id": "name-item"}, "imageAlt": {"template_id": "alt-name"},
                "description": {"template_id": "desc-food-plain", "phrase_ids": ["food-open-1", "food-use-1", "food-close-1"]},
                "story": {"template_id": "story-makes-town", "phrase_ids": [], "fact_ids": ["f1"]}}
        self.assertEqual(validate(schema, good), [])
        self.assertEqual(validate(schema, dict(good, story=None)), [])
        self.assertTrue(validate(schema, dict(good, description={"template_id": "x", "phrase_ids": [], "text": "The beans are roasted in copper pans."})))
        self.assertTrue(validate(schema, dict(good, prose="free text")))
        for key in schema["properties"]:
            self.assertNotIn("text", schema["properties"][key]["properties"] if "properties" in schema["properties"][key] else {})

    def test_rendered_defaults_equal_the_strings_the_cases_expect(self):
        """Contract: cases 30 and 36 expect the reviewed default description (rung a, anchored on the case's item), cases 30 and 31 the story; they must equal what the templates render. Bug: a template edit that silently changes the default while the cases still pass on a stale string."""
        food = self.by_id[self.t["defaults"]["description"]["food"][0]]
        seen = 0
        for case in all_cases():
            for unit in units(case):
                if "description_equals" in unit["expect"]:
                    default = render(food["text"], {"item": unit["inputs"]["item"]}, {})
                    self.assertEqual(unit["expect"]["description_equals"], default, case["id"])
                    seen += 1
        self.assertEqual(seen, 2)
        story = {"story-nature-makes-town": {"maker_name": "Miners", "nature": "orchard", "town": "Paso Robles", "makes": "dried figs"},
                 "story-makes-town": {"maker_name": "Miners", "makes": "dried figs", "town": "Paso Robles"}}
        want = {"Miners is an orchard in Paso Robles, and it makes dried figs.": "story-nature-makes-town",
                "Miners makes dried figs in Paso Robles.": "story-makes-town"}
        found = set()
        for case in all_cases():
            for unit in units(case):
                if "story_equals" in unit["expect"]:
                    tid = want[unit["expect"]["story_equals"]]
                    self.assertEqual(render(self.by_id[tid]["text"], story[tid], {}), unit["expect"]["story_equals"])
                    found.add(tid)
        self.assertEqual(found, set(story))


class EditGrammarTest(unittest.TestCase):
    def test_each_form_matches_its_examples_and_rejects_its_negatives(self):
        """Contract: S10 deterministic forms match exactly the owner phrasings they claim. Bug: a pattern that swallows a sentence ('from 3 to 4 dollars' as a supplier) or never matches its own example."""
        grammar = asset("hass-listing-edit/edit-grammar.json")
        fields = set(asset("hass-listing-edit/edit.schema.json")["properties"]["patches"]["items"]["properties"]["field"]["enum"])
        replies = asset("hass-npp-reply/reply-templates.json")
        self.assertEqual(len({f["id"] for f in grammar["forms"]}), len(grammar["forms"]))
        for form in grammar["forms"]:
            rx = re.compile(form["pattern"], re.IGNORECASE)
            self.assertIn(form["field"], fields, form["id"])
            self.assertTrue(form["examples"] and form["negatives"], form["id"])
            for ex in form["examples"]:
                m = rx.fullmatch(ex["text"])
                self.assertIsNotNone(m, ex["text"])
                self.assertEqual(m.groupdict(), ex["captures"], ex["text"])
            for text in form["negatives"]:
                self.assertIsNone(rx.fullmatch(text), text)
            if "reply" in form:
                group, key = form["reply"].split(".")
                self.assertIn(key, replies[group])
        self.assertEqual(set(grammar["model_mapping"]["fields_allowed"]), fields)

    def test_edit_forms_do_not_overlap_on_the_examples(self):
        """Contract: each example is claimed by exactly one form, so grammar order cannot change a result. Bug: two forms matching the same message, with the winner decided by list order."""
        forms = [(f["id"], re.compile(f["pattern"], re.IGNORECASE), f) for f in asset("hass-listing-edit/edit-grammar.json")["forms"]]
        for fid, _rx, form in forms:
            for ex in form["examples"]:
                hits = [other for other, rx, _f in forms if rx.fullmatch(ex["text"])]
                self.assertEqual(hits, [fid], ex["text"])

    def test_category_form_only_names_real_shelves(self):
        """Contract: an edit can only move a product to a shelf the content model has. Bug: a shelf word in the pattern that CATEGORIES does not contain."""
        grammar = asset("hass-listing-edit/edit-grammar.json")
        form = next(f for f in grammar["forms"] if f["id"] == "category")
        group = re.search(r"\(\?P<value>([^)]*)\)", form["pattern"]).group(1).split("|")
        self.assertEqual(set(group), set(CATEGORIES))


class PhotoPolicyTest(unittest.TestCase):
    def test_edit_prompt_equals_the_runtime_prompt_and_existing_refs_resolve(self):
        """Contract: design 2.2 the photo asset's prompt is photo_polish.PROMPT unchanged, and it points only at existing constants (no new thresholds). Bug: a prompt reworded in the asset while the runtime still uses the old one, or a ref to a constant that no longer exists."""
        import importlib
        from hass import photo_polish
        photo = asset("hass-product-photo/photo.json")
        self.assertEqual(photo["prompt"], photo_polish.PROMPT)
        self.assertEqual(photo["model"], photo_polish.MODEL)
        self.assertTrue(photo["no_new_thresholds"])
        for ref in photo["existing_refs"]:
            parts = ref.split(".")
            module = None
            for i in range(len(parts) - 1, 0, -1):
                try:
                    module = importlib.import_module(".".join(parts[:i]))
                    rest = parts[i:]
                    break
                except ImportError:
                    continue
            self.assertIsNotNone(module, ref)
            obj = module
            for name in rest:
                obj = getattr(obj, name)
        self.assertEqual({v["variant"] for v in photo["variant_order"]}, {"polished", "raw", "house", "none"})
        self.assertNotIn("webp", json.dumps(photo["variant_order"]).lower())

    def test_raw_conditions_are_the_five_in_the_design(self):
        """Contract: design 1.7 the raw owner photo is allowed only under five conditions. Bug: a dropped condition (for example the screen flag), letting a phone screen onto the site."""
        ids = [c["id"] for c in asset("hass-product-photo/photo.json")["raw_conditions"]]
        self.assertEqual(ids, ["no_person_or_screen", "ocr_read_ok", "no_money_or_private_token", "no_contact_or_path", "sharp"])


class PinsTest(unittest.TestCase):
    def test_every_asset_is_pinned_and_hashes_match(self):
        """Contract: design 2.1 assets are pinned by sha256; a changed, added or removed asset must refresh the pin. Bug: an asset edit that leaves pins.json stale, so the runtime would refuse it (or accept a changed one)."""
        problems = script("npp_limits").pins_check()
        self.assertEqual(problems, [], "run: python3 scripts/hass/npp_limits.py pins")

    def test_pin_check_catches_each_kind_of_drift(self):
        """Contract: the hash check has teeth. Bug: a checker that returns no problems for a tampered file, an unpinned file or a missing one."""
        import tempfile
        mod = script("npp_limits")
        with tempfile.TemporaryDirectory() as tmp:
            tmp = Path(tmp)
            assets = tmp / "assets"
            (assets / "a").mkdir(parents=True)
            (assets / "a" / "one.json").write_text("{}", encoding="utf-8")
            pins = tmp / "pins.json"
            pins.write_text(json.dumps({"assets": {}}), encoding="utf-8")
            mod.pins_write(pins, assets)
            self.assertEqual(mod.pins_check(pins, assets), [])
            (assets / "a" / "one.json").write_text("{ }", encoding="utf-8")
            self.assertEqual(mod.pins_check(pins, assets), ["hash differs: a/one.json"])
            (assets / "a" / "two.json").write_text("{}", encoding="utf-8")
            self.assertIn("asset not pinned: a/two.json", mod.pins_check(pins, assets))
            (assets / "a" / "one.json").unlink()
            self.assertIn("pinned file missing: a/one.json", mod.pins_check(pins, assets))

    def test_pinned_models_and_segment_follow_the_design(self):
        """Contract: design 2.3 and 1.3 model ids, effort and the 100 s cap are pinned. Bug: a step with no model, a cap that counts owner wait, or a picture model that differs from photo_polish."""
        from hass import photo_polish
        pins = load(PINS)
        for name, step in pins["steps"].items():
            self.assertTrue(step["model"], name)
        self.assertEqual(pins["steps"]["picture"]["model"], photo_polish.MODEL)
        self.assertEqual(pins["segment"]["cap_s"], 100)
        self.assertFalse(pins["segment"]["owner_wait_counts"])
        self.assertTrue(pins["research"]["search_only_to_locate"])
        self.assertEqual(pins["steps"]["judge"]["effort"], "medium")


class JudgeAssetsTest(unittest.TestCase):
    def test_rubric_and_calibration_manifest_are_consistent(self):
        """Contract: design 3.3 seven dimensions, pass 4.0 with none below 3, calibration of 3 runs; the manifest names real files. Bug: a manifest entry for a card that does not exist, which would silently shrink the calibration set."""
        rubric = asset("hass-style-judge/rubric.json")
        self.assertEqual(len(rubric["dimensions"]), 7)
        self.assertEqual((rubric["pass"]["mean_at_least"], rubric["pass"]["dimension_at_least"]), (4.0, 3))
        self.assertEqual(rubric["calibration"]["runs"], 3)
        manifest = asset("hass-style-judge/calibration/manifest.json")
        self.assertEqual(len(manifest["good"]), 12)
        for pid in manifest["good"]:
            self.assertTrue((ASSETS / manifest["good_dir"] / f"{pid}.json").exists(), pid)
        for pid in manifest["bad"]:
            self.assertTrue((ASSETS / manifest["bad_dir"] / f"{pid}.json").exists(), pid)
        dims = {d["id"] for d in rubric["dimensions"]}
        for pid in manifest["bad"]:
            self.assertTrue(set(load(ASSETS / manifest["bad_dir"] / f"{pid}.json")["breaks"]) <= dims, pid)


def all_cases():
    return [load(p) for p in sorted(CASES.glob("case-*.json"))]


def units(case):
    """Variants inherit turns unless replaced, and shallowly overlay inputs and expect."""
    if "variants" not in case:
        return [dict(case)]
    out = []
    for v in case["variants"]:
        out.append({"turns": v.get("turns", case.get("turns")), "inputs": {**case.get("inputs", {}), **v.get("inputs", {})},
                    "expect": {**case.get("expect", {}), **v.get("expect", {})}, "id": v["id"]})
    return out


class CaseInputsTest(unittest.TestCase):
    def setUp(self):
        self.schema = load(CASES / "case.schema.json")
        self.cases = all_cases()

    def test_there_are_38_cases_with_permanent_ids_and_a_path_and_terminal(self):
        """Contract: design 3.1 and NPP-A acceptance: all 38 cases exist and each declares its path and terminal state. Bug: a missing, duplicated or renumbered case, or one with no terminal state."""
        self.assertEqual([c["id"] for c in self.cases], list(range(1, 39)))
        self.assertEqual(len({c["slug"] for c in self.cases}), 38)
        for case in self.cases:
            self.assertEqual(validate(self.schema, case), [], case["slug"])
            self.assertTrue(case["path"] and case["terminal"])
            if "variants" in case:
                inherits_turns = any("turns" not in v for v in case["variants"])
                self.assertEqual("turns" in case, inherits_turns, case["id"])
            self.assertTrue(all(unit.get("turns") for unit in units(case)), case["id"])
            self.assertEqual(CASES.joinpath(f"case-{case['id']:02d}-{case['slug']}.json").exists(), True)
            allowed = {"listing": {"published"}, "question": {"asking", "retake", "expired"}, "contract": {"published", "card_out"}}[case["path"]]
            self.assertIn(case["terminal"], allowed, case["id"])

    def test_paths_match_the_design_table(self):
        """Contract: the path of each case is the design's (listing 1-17,19,21,23,24,26,27,29-32,36-38; question 18,20,22,28,33; contract 25,34,35). Bug: a case moved to a path with weaker checks."""
        by = {c["id"]: c["path"] for c in self.cases}
        question = {18, 20, 22, 28, 33}
        contract = {25, 34, 35}
        for i in range(1, 39):
            self.assertEqual(by[i], "question" if i in question else "contract" if i in contract else "listing", i)
        self.assertEqual({c["id"]: c["terminal"] for c in self.cases if c["id"] in (18, 20, 22, 28, 33, 34, 35)},
                         {18: "asking", 20: "expired", 22: "asking", 28: "retake", 33: "asking", 34: "card_out", 35: "card_out"})

    def test_listing_cases_run_v1_edit_v2_tagged_yes_then_undo(self):
        """Contract: design 3.1 listing path: delivered card v1, an edit, delivered card v2, `yes <code>-2`, one commit, then `undo` drafts the hide; only the two spec rows that fix a restart or sole-delivered control (23, 24) skip the edit and keep their v1 approval. Bug: a fixture that ends at `yes <code>-1`, so the replay can never test the edit, the re-approval of the new tag or the undo."""
        controls = {23, 24}
        edit = re.compile(r"^(make it \$\d+(\.\d{2})?( per lb)?|shorter)$")
        for case in self.cases:
            if case["path"] != "listing":
                continue
            self.assertEqual("control" in case, case["id"] in controls, case["id"])
            for unit in units(case):
                turns, exp = unit["turns"], unit["expect"]
                texts = [t["text"] for t in turns]
                self.assertEqual([t["at_s"] for t in turns], sorted({t["at_s"] for t in turns}), case["id"])
                self.assertEqual(texts[-1], "undo", case["id"])
                self.assertEqual(exp["undo"], {"draft": "hide", "commits": 1}, case["id"])
                self.assertEqual(exp["commits"], 1, case["id"])
                self.assertTrue({"reply", "delivery_approval"} <= set(exp["checks"]), case["id"])
                if case["id"] in controls:
                    self.assertNotIn("yes {code}-2", texts, case["id"])
                    self.assertEqual(exp["versions"], [{"n": 1, "delivered": True, "approved": True}], case["id"])
                    self.assertEqual([r["kind"] for r in exp["replies"]][-2:], ["posted", "undo_draft"], case["id"])
                    continue
                self.assertEqual(texts[-2], "yes {code}-2", case["id"])
                self.assertRegex(texts[-3], edit, case["id"])
                self.assertEqual(exp["versions"], [{"n": 1, "delivered": True}, {"n": 2, "delivered": True, "approved": True}], case["id"])
                tail = [r for r in exp["replies"] if r["turn"] >= len(turns) - 3]
                self.assertEqual([(r["turn"] - len(turns), r["kind"]) for r in tail], [(-3, "card"), (-2, "posted"), (-1, "undo_draft")], case["id"])
                self.assertIn("Post this? Reply yes <code>-2, or tell me what to change.", tail[0]["has_all"], case["id"])
                self.assertIn("picture_bytes", exp["edit_keeps"], case["id"])
                self.assertEqual("description" in exp["edit_keeps"], texts[-3] != "shorter", case["id"])
                if "image_edit" in exp.get("calls", {}):
                    self.assertIn(exp["calls"]["image_edit"], (0, 1), "an edit never starts a second picture edit")

    def test_expect_keys_and_checks_are_in_the_documented_vocabulary(self):
        """Contract: expectation keys are a documented vocabulary, so a typo cannot make an assertion vanish. Bug: 'comits: 1' silently never checked."""
        keys, checks, kinds = set(self.schema["x-expect-keys"]), set(self.schema["x-check-ids"]), set(self.schema["x-reply-kinds"])
        for case in self.cases:
            for unit in units(case):
                self.assertFalse(set(unit["expect"]) - keys, (case["id"], set(unit["expect"]) - keys))
                self.assertFalse(set(unit["expect"].get("checks", [])) - checks, case["id"])
                for rep in unit["expect"].get("replies", []):
                    self.assertIn(rep["kind"], kinds, case["id"])
                    self.assertEqual(rep["count"] == 0, rep["kind"] == "none", case["id"])
                self.assertTrue(unit["expect"].get("state") or unit["expect"].get("replies"), case["id"])
        for case in self.cases:
            for unit in units(case):
                self.assertEqual(unit["expect"]["state"], {"published": "published", "asking": "asking", "retake": "retake", "expired": "expired", "card_out": "card_out"}[case["terminal"]], case["id"])

    def test_question_cases_assert_no_draft_and_listing_cases_a_commit(self):
        """Contract: design 3.2 per path: a question case has no draft row, no approval prompt and no commit; a published listing commits exactly once. Bug: a question case that forgot to forbid a draft."""
        for case in self.cases:
            for unit in units(case):
                exp = unit["expect"]
                if case["path"] == "question":
                    self.assertEqual((exp.get("draft_rows"), exp.get("commits"), exp.get("approval_rows")), ("none", 0, 0), case["id"])
                    self.assertIn("no_draft", exp["checks"], case["id"])
                    self.assertTrue(all(r["kind"] != "card" for r in exp["replies"]), case["id"])
                elif case["terminal"] == "published":
                    self.assertEqual(exp["commits"], 1, case["id"])
                if case["id"] in (18, 22, 28, 33):
                    self.assertEqual(exp["total_replies"], 1, case["id"])

    def test_every_photo_edit_and_page_file_exists(self):
        """Contract: a case never names a fixture that is not in the repo. Bug: a renamed photo that leaves a case pointing at nothing, found only on the private host."""
        for case in self.cases:
            for unit in units(case):
                for t in unit["turns"]:
                    for photo in t["photos"]:
                        scheme, name = photo.split(":")
                        folder = CASES / "photos" if scheme == "npp" else CHAOS_PHOTOS
                        self.assertTrue((folder / name).exists(), (case["id"], photo))
                polish = unit["inputs"].get("polish", {})
                if polish.get("source") == "file":
                    self.assertTrue((CASES / polish["file"].split(":")[1]).exists(), case["id"])
                for addr, page in unit["inputs"].get("web", {}).get("pages", {}).items():
                    self.assertTrue((CASES / page["file"]).exists(), (case["id"], addr))
                    self.assertRegex(addr, r"^https://[a-z0-9.-]+\.example/")
            if "golden" in case:
                self.assertTrue((ASSETS / case["golden"]).exists(), case["id"])

    def test_golden_cases_1_to_12_follow_the_twelve_goldens(self):
        """Contract: cases 1-12 are the twelve goldens in order with the golden's own brand, origin and category; the two no-maker goldens do no research. Bug: a golden case whose expected origin or panel differs from the live card."""
        goldens = sorted((ASSETS / "hass-gallery-style" / "golden").glob("*.json"))
        used = []
        for case in self.cases[:12]:
            g = load(ASSETS / case["golden"])
            used.append(g["product_id"])
            listing = case["expect"]["listing"]
            self.assertEqual((listing["brand"], listing["origin"], listing["category"], listing["maker_panel"]),
                             (g["card"]["brand"], g["card"]["origin"], g["category"], g["card"]["meet_the_maker"] is not None), case["id"])
            self.assertEqual(case["expect"]["calls"], {"image_edit": 1, "search": 0, "fetch": 0, "extract": 0, "verify": 0}, case["id"])
            self.assertEqual(case["turns"][0]["photos"], [f"npp:golden-{g['product_id'].split('-')[-1]}.jpg"])
        self.assertEqual(sorted(used), sorted(load(p)["product_id"] for p in goldens))
        self.assertEqual([c["id"] for c in self.cases[:12] if c["expect"]["listing"]["brand"] == "From the market"], [9, 12])

    def test_research_cases_use_a_synthetic_web_and_follow_the_g_decision(self):
        """Contract: G 2026-11-18 14:00: official site by search or owner URL, search only to locate, queries without digits, no story unless confident, never an extraction for an unverified page. Bug: a case that encodes the superseded 'zero search' rule, or a query carrying the owner's price."""
        forms = asset("hass-maker-research/sources.json")["discovery"]["search"]["query_forms"]
        allowed = {f.format(maker="Miners", town="Paso Robles") for f in forms} | {forms[1].format(maker="Miners")}
        deny = set(asset("hass-maker-research/sources.json")["deny_domains"])
        research = [c for c in self.cases if c["id"] in (29, 30, 31, 37, 38)]
        self.assertEqual(len(research), 5)
        searched = 0
        for case in research:
            for unit in units(case):
                web = unit["inputs"].get("web")
                if web is None:
                    continue
                for query in web["search"]:
                    searched += 1
                    self.assertIn(query, allowed)
                    self.assertNotRegex(query, r"\d")
                for results in web["search"].values():
                    for result in results:
                        host = re.sub(r"^https://(www\.)?", "", result["url"]).split("/")[0]
                        if host in deny:
                            self.assertIn(result["url"], web["forbid_fetch"], "a denied domain is never fetched")
                for forbidden in web["forbid_fetch"]:
                    self.assertNotIn(forbidden, web["pages"])
        self.assertGreater(searched, 0)
        for cid in (37, 38):
            for unit in units(next(c for c in self.cases if c["id"] == cid)):
                self.assertEqual(unit["expect"]["calls"]["extract"], 0, cid)
                self.assertIsNone(unit["expect"]["story"], cid)
        self.assertEqual(next(c for c in self.cases if c["id"] == 30)["inputs"]["web"]["search"], {}, "case 30 is the owner-stated URL route")

    def test_state_machine_cases_use_the_confirmed_send_vocabulary(self):
        """Contract: R2.1 cases 34 and 35 are driven through the outbox and the delivered-receipt boundary, never by seeding 'delivered'. Bug: a case that marks a version delivered without a scripted send."""
        c34 = next(c for c in self.cases if c["id"] == 34)
        self.assertEqual(c34["inputs"]["outbox"]["v1"]["sends"], ["fail", "ok"])
        self.assertTrue(any(t.get("restart") for t in c34["turns"]) and any(t.get("retry_send") for t in c34["turns"]))
        c35 = next(c for c in self.cases if c["id"] == 35)
        self.assertEqual([u["id"] for u in units(c35)], ["a", "b", "c"])
        self.assertTrue(any(t.get("reply_to") == "v1" for t in units(c35)[1]["turns"]))
        c25 = next(c for c in self.cases if c["id"] == 25)
        self.assertEqual(c25["inputs"]["outbox"]["v2"]["sends"], [])
        for case in self.cases:
            self.assertNotIn("delivered", json.dumps(case.get("inputs", {})).replace('"delivered_at_s"', ""), case["id"])

    def test_fixtures_hold_no_private_value_or_contact(self):
        """Contract: fixtures are synthetic. Bug: a real email, phone number, home path or street address committed in an asset or case."""
        pattern = re.compile(r"[\w.+-]+@[\w-]+\.[\w.]+|\(?\b\d{3}\)?[ .-]\d{3}[ .-]\d{4}\b|/home/user|\b\d{2,5} [A-Z][a-z]+ (Street|St|Avenue|Ave|Road|Rd|Lane|Ln)\b")
        for folder in (ASSETS, CASES):
            for path in folder.rglob("*"):
                if path.suffix in (".json", ".md", ".html", ".tsv"):
                    self.assertIsNone(pattern.search(path.read_text(encoding="utf-8")), str(path.relative_to(ROOT)))


if __name__ == "__main__":
    unittest.main()
