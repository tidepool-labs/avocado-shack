"""SKILLS-ITEMADD-1: the item.add skill (add a new item end to end; reports/hass/SKILLS-SPEC.md 3.1, card 14).

Proves, against the real content: the lint and the case file, the live boundary class, the plain words of every owner
sentence (docs/hass/VOICE.md), the drafted defaults (derive: functions), the order of the questions, D2 (today's shelf
check on its own line), D5 (the maker note), D9 (price and size left off), "same as last time", a hidden maker, a twin
and the picture advice. The case rows themselves run through the real Conversation and Editor in test_skills_cases.
Run: python3 -B -m unittest hass.tests.test_skills_item_add -v
"""
import copy
import unittest
from types import SimpleNamespace

from hass import live_policy, preview, skills, voice
from hass.content_model import REPO_ROOT, load_and_validate
from hass.ops import load_registry
from hass.skills import item_add as ia
from hass.skills import testkit
from hass.skills.model import lint_plan_output

CONTENT = load_and_validate(REPO_ROOT / "hass" / "content", REPO_ROOT / "storefront-mockup")
SYN = REPO_ROOT / "reports" / "hass" / "newitem-1" / "synthetic"
SHA = "2cec1911a59002428a1c22e1a9dd1f9226243e49829bfed452aafd7773446bf3"  # jar-white-sheet.jpg
FULL = {"name": "Wildflower honey", "form": "packaged", "maker": "Bee Happy Farm", "place": "Atascadero, California",
        "shelf": "pantry", "description": "Wildflower honey from Bee Happy Farm in Atascadero. Spoon a little onto buttered toast.",
        "image_alt": "Wildflower honey in a jar", "availability": "yes", "photo": SHA}


def ctx(*texts, content=CONTENT, **extra):
    return SimpleNamespace(today="2026-11-08", content=content, texts=list(texts), **extra)


def refusal(slots, *texts, **extra):
    with unittest.TestCase().assertRaises(ia.Refusal) as caught:
        ia.describe_add(slots, ctx(*texts, **extra))
    return caught.exception


def with_last(key, form_shelf="vegetables"):
    """A copy of the content whose last added product is from ``key``."""
    content = copy.deepcopy(CONTENT)
    content.products.append({"id": "photo-product-175", "name": "Test peaches", "brand": key, "category": form_shelf,
                             "producerKey": key, "status": "active"})
    return content


class Declaration(unittest.TestCase):
    def test_registered_and_the_lint_and_case_file_are_clean(self):
        self.assertIs(skills.load_skills().get("item.add"), ia.ITEM_ADD)
        ops = load_registry()
        self.assertEqual(skills.skill_lint([ia.ITEM_ADD], ops, repo_root=REPO_ROOT), [])
        golden = ia.plan_add(dict(FULL), SimpleNamespace(today="2026-11-08", next_product_id="photo-product-175", texts=["new honey", "skip"]))
        self.assertEqual(lint_plan_output(ia.ITEM_ADD, golden, ops), [])

    def test_live_class_matches_the_live_boundary(self):
        """chat-live (HASS-LIVE-ADD-1): a new product with its brand and maker is in the live table, so live_policy lets this plan through
        (the brand fields are guarded inside product.add; the owner-words rule is the conversation's, see test_live_add)."""
        scratch = testkit.Scratch({}, {"item.add": ia.ITEM_ADD}, photos=["reports/hass/newitem-1/synthetic/jar-white-sheet.jpg"])
        try:
            plan = ia.plan_add({"name": "Cal Poly honey", "maker": "Cal Poly", "availability": "yes", "photo": SHA}, scratch._ctx())
            out = scratch.editor.prepare(plan)
            self.assertEqual(out["result"], "ok", out)
            self.assertEqual(live_policy.check(out["draft"]), [])
            self.assertEqual(live_policy.unsaid(out["draft"], "Cal Poly honey"), [])
        finally:
            scratch.close()
        self.assertEqual(ia.ITEM_ADD.live_class, "chat-live")

    def test_every_owner_sentence_passes_the_voice_rules(self):
        fixed = list(ia.ASK.values()) + [ia.ONE_PHOTO, ia.NO_LAST_FARM, ia.STORE_LINE, ia.NO_BYTES, ia.RETAKE_BUSY,
                                         ia.RETAKE_SMALL, ia.RETAKE_OTHER, ia.AS_TAKEN, ia.PICTURE_OK, ia.MANY_ITEMS,
                                         ia.description_refusal(["it has a number in it", "it has sales words",
                                                                 "it has an exclamation or question mark",
                                                                 "it is shorter than the others on the site"]).reply]
        fixed += [reply.replace("<Product>", "Cal Poly honey").replace("<Maker>", "Etto") for _why, reply in ia.ITEM_ADD.refuse]
        asked = [ia.question(s, {"name": "Tomatoes", "form": "fresh", "maker": "Smith Farm"}, ctx()) for s in ia.ASK]
        for text in fixed + asked:
            with self.subTest(text=text):
                self.assertEqual(voice.check(voice.plain(text)), [])
                self.assertLessEqual(text.count("?"), 1, "one question at a time")


class DraftedDefaults(unittest.TestCase):
    def test_form_from_his_words_the_shelf_or_asked(self):
        self.assertEqual(ia.form_guess({"name": "Honey"}, ctx("new honey in a jar")), "packaged")
        self.assertEqual(ia.form_guess({"name": "Tomatoes"}, ctx("fresh tomatoes today")), "fresh")
        self.assertEqual(ia.form_guess({"name": "Roast Bros coffee", "shelf": "drinks"}, ctx("it goes with drinks")), "packaged")
        self.assertIsNone(ia.form_guess({"name": "Lemon curd"}, ctx("add lemon curd")))

    def test_shelf_he_named_else_the_shelf_of_the_same_kind_else_asked(self):
        self.assertEqual(ia.same_kind_majority({"name": "Honey"}, ctx("new honey")), "pantry")
        self.assertEqual(ia.same_kind_majority({"name": "Heirloom tomatoes"}, ctx("tomatoes")), "vegetables")
        self.assertIsNone(ia.same_kind_majority({"name": "Lemon curd"}, ctx("lemon curd")))
        with self.assertRaises(ia.Refusal) as caught:
            ia.describe_add({**FULL, "name": "Lemon curd", "shelf": None, "maker": "Linn's"}, ctx("lemon curd from Linn's"))
        self.assertTrue(caught.exception.reply.startswith("Which shelf does it go on:"))

    def test_town_of_a_saved_maker_none_for_a_new_one(self):
        self.assertEqual(ia.saved_place({"maker": "Cal Poly"}, ctx()), "San Luis Obispo, California")
        self.assertEqual(ia.saved_place({"maker": "don't know"}, ctx()), ia.NOT_NEEDED)
        self.assertIsNone(ia.saved_place({"maker": "Bee Happy Farm"}, ctx()))

    def test_description_is_machine_valid_and_names_maker_and_town(self):
        text = ia.house_description({"name": "Cal Poly honey", "maker": "Cal Poly"}, ctx("new honey from Cal Poly"))
        self.assertIn("Cal Poly in San Luis Obispo", text)
        self.assertFalse(any(c.isdigit() for c in text) or "$" in text or "!" in text)

    def test_caption_is_the_name_plus_the_container_only_when_said(self):
        self.assertEqual(ia.alt_text({"name": "Cal Poly honey"}, ctx("Cal Poly honey 8oz jar")), "Cal Poly honey in a jar")
        self.assertEqual(ia.alt_text({"name": "Cal Poly honey"}, ctx("new honey from Cal Poly")), "Cal Poly honey")


class Questions(unittest.TestCase):
    def test_the_order_is_name_form_maker_town_stock_photo(self):
        steps = [({}, "What is it called?"), ({"name": "Lemon curd"}, "Is it packaged or fresh?"),
                 ({"name": "Lemon curd", "form": "packaged"}, "Who makes this lemon curd?"),
                 ({"name": "Lemon curd", "form": "packaged", "maker": "Smith Farm", "shelf": "pantry"},
                  "Where is Smith Farm based (town and state)?"),
                 ({"name": "Lemon curd", "form": "packaged", "maker": "Linn's", "shelf": "pantry"}, "Is it in stock right now?"),
                 ({"name": "Lemon curd", "form": "packaged", "maker": "Linn's", "shelf": "pantry", "availability": "yes"},
                  "Send a photo of it.")]
        for slots, want in steps:
            with self.subTest(want=want):
                got = refusal(slots)
                self.assertEqual((voice.plain(got.reply).split(" (Last")[0], got.kind), (want, "question"))

    def test_the_farm_question_offers_the_last_maker_by_name(self):
        content = with_last("Fair Hills Farm")
        asked = voice.plain(ia.question("maker", {"name": "Tomatoes", "form": "fresh"}, ctx(content=content)))
        self.assertEqual(asked, "Who grew these tomatoes? (Last time it was Fair Hills Farm. Say the name again to use them.)")
        packaged = voice.plain(ia.question("maker", {"name": "Lemon curd", "form": "packaged"}, ctx()))
        self.assertTrue(packaged.endswith("(Last time it was Etto. Say the name again to use them.)"), packaged)

    def test_same_uses_the_maker_of_the_last_product_added_once_he_says_the_name(self):
        content = with_last("Fair Hills Farm")
        said = ctx("same farm as last time, Fair Hills Farm", content=content)
        done = ia.describe_add({**FULL, "name": "Heirloom tomatoes", "form": "fresh", "maker": "same farm as last time",
                                "shelf": "vegetables"}, said)
        add = next(op for op in done.ops if op["op"] == "product.add")["args"]
        self.assertEqual((add["producerKey"], add["brand"]), ("Fair Hills Farm", "Fair Hills Farm"))
        self.assertIn("the maker to Fair Hills Farm, the same as last time", [voice.plain(s) for s in done.set_lines])
        self.assertNotIn("maker.add", [op["op"] for op in done.ops])
        self.assertEqual([voice.plain(p) for p in ia.set_phrases({**FULL, "maker": "same", "shelf": "vegetables"}, said)][:1],
                         ["the maker to Fair Hills Farm, the same as last time"])

    def test_same_without_the_name_in_his_words_asks_him_to_say_it(self):
        content = with_last("Fair Hills Farm")
        got = refusal({**FULL, "name": "Heirloom tomatoes", "form": "fresh", "maker": "same farm as last time", "shelf": "vegetables"},
                      "same farm as last time", content=content)
        self.assertEqual((voice.plain(got.reply), got.kind), ("Please say the name, so I use the right one: Fair Hills Farm.", "question"))
        self.assertEqual(voice.check(voice.plain(got.reply)), [])

    def test_same_with_no_saved_maker_asks(self):
        content = copy.deepcopy(CONTENT)
        content.products = [p for p in content.products if not p["id"].startswith("photo-product-")]
        self.assertEqual(refusal({**FULL, "maker": "same"}, content=content).reply, ia.NO_LAST_FARM)

    def test_latest_product_without_a_visible_maker_does_not_reuse_an_older_farm(self):
        slots = {**FULL, "maker": None}
        for fields in ({"brand": ia.UNKNOWN_BRAND}, {"brand": "Etto", "producerKey": "Etto"}):
            with self.subTest(fields=fields):
                content = with_last("Fair Hills Farm")
                content.makers["Etto"]["hidden"] = True
                content.products.insert(0, {"id": "photo-product-176", "name": "Test plums", "category": "fruit",
                                            "status": "active", **fields})
                said = ctx("same farm as last time, Fair Hills Farm", content=content)
                with self.assertRaises(ia.Refusal) as caught:
                    ia.plan_add({**slots, "maker": "same farm as last time"}, said)
                self.assertEqual((caught.exception.kind, caught.exception.reply), ("question", ia.NO_LAST_FARM))
                self.assertEqual(ia.question("maker", slots, said), "Who makes this wildflower honey?")


class Plan(unittest.TestCase):
    def test_new_maker_product_and_todays_shelf_check_on_its_own_line(self):
        done = ia.describe_add(dict(FULL), ctx("new wildflower honey from Bee Happy Farm in Atascadero, its in", "skip"))
        self.assertEqual([op["op"] for op in done.ops], ["maker.add", "product.add", "store.confirm_selection"])
        self.assertEqual(done.ops[0]["args"]["story"], "Bee Happy Farm is based in Atascadero, California.")  # D5
        self.assertEqual(done.ops[2]["args"], {"yes": ["photo-product-175"]})
        self.assertIn(ia.STORE_LINE, done.say)  # D2

    def test_a_skipped_story_stays_skipped_while_the_draft_is_revised(self):
        """Codex RETURN at 9f213272 item 1: after 'skip', changing the description or caption revises the draft (D5 line only)."""
        for later in ("make the description say Spoon it on toast", "the caption should be honey jar", "call it Clover honey"):
            for skip in ("skip", "skip the story", "no"):
                with self.subTest(skip=skip, later=later):
                    done = ia.describe_add(dict(FULL), ctx("new wildflower honey from Bee Happy Farm in Atascadero, its in", skip, later))
                    self.assertEqual(done.ops[0]["args"]["story"], "Bee Happy Farm is based in Atascadero, California.")
        with self.assertRaises(ia.Refusal) as caught:  # no skip anywhere: still the one story question
            ia.describe_add(dict(FULL), ctx("new wildflower honey from Bee Happy Farm in Atascadero, its in", "the caption should be honey jar"))
        self.assertEqual(caught.exception.reply, ia.ASK_STORY.format(maker="Bee Happy Farm"))

    def test_check_already_recorded_today_sets_only_the_word(self):
        content = copy.deepcopy(CONTENT)
        content.store["selection_checked_on"] = "2026-11-08"
        done = ia.describe_add({**FULL, "availability": "no"}, ctx("new honey", "skip", content=content))
        self.assertEqual(done.ops[-1], {"op": "product.set_availability", "args": {"id": "photo-product-175", "available": "no"}})
        self.assertNotIn(ia.STORE_LINE, done.say)

    def test_price_and_size_are_left_off_never_written(self):
        done = ia.describe_add({**FULL, "name": "Cal Poly honey 8oz", "maker": "Cal Poly", "image_alt": None},
                               ctx("Cal Poly honey 8oz jar $9 just got in"))
        add = next(op for op in done.ops if op["op"] == "product.add")["args"]
        self.assertEqual(add["name"], "Cal Poly honey")
        self.assertFalse(any("$" in str(v) or "8oz" in str(v) for v in add.values()))
        self.assertEqual(done.left_off, ("the price ($9) and the size (8oz), because the website shows no prices or sizes",))

    def test_unknown_maker_has_no_maker_record(self):
        done = ia.describe_add({**FULL, "maker": "dont know"}, ctx("new jam, dont know who makes it"))
        add = done.ops[0]["args"]
        self.assertEqual((done.ops[0]["op"], add["brand"], "producerKey" in add), ("product.add", ia.UNKNOWN_BRAND, False))

    def test_hidden_maker_is_asked_about_not_used(self):
        content = copy.deepcopy(CONTENT)
        content.makers["Linn's"]["hidden"] = True
        got = refusal({**FULL, "maker": "Linn's"}, content=content)
        self.assertEqual((voice.plain(got.reply), got.kind), ("Linn's is hidden. Do you want me to bring them back first?", "question"))

    def test_a_twin_is_named_before_anything_else_is_asked(self):
        got = refusal({"name": "Rigatoni pasta", "maker": "Etto", "photo": SHA}, "Etto's new rigatoni")
        self.assertEqual(voice.plain(got.reply), "Rigatoni pasta is already on the site. Do you want to change it instead?")

    def test_the_plan_is_pure_and_keeps_the_slots(self):
        slots = {"name": "Cal Poly honey", "maker": "Cal Poly", "availability": "yes", "photo": SHA}
        given = dict(slots)
        first = ia.plan_add(given, ctx("new honey from Cal Poly, it's in"))
        self.assertEqual(given, slots)
        self.assertEqual(ia.plan_add(dict(slots), ctx("new honey from Cal Poly, it's in")), first)


class OnePhotoOneProduct(unittest.TestCase):
    """Rule one-photo: the skill itself asks which product the photo is for, whatever the model returned (finding 1)."""

    def test_two_products_in_his_message_ask_which_one_even_for_a_complete_plan(self):
        text = "add the lemon curd and the plum jam, both in stock"
        got = refusal({**FULL, "name": "Lemon curd", "maker": "Linn's", "shelf": "pantry"}, text)
        self.assertEqual((got.reply, got.kind, got.backlog), (ia.ONE_PHOTO, "question", None))
        with self.assertRaises(ia.Refusal):
            ia.plan_add({**FULL, "name": "Lemon curd", "maker": "Linn's"}, ctx(text))  # no ops, from plan_add too

    def test_a_name_that_lists_two_products_asks_which_one(self):
        for name in ("Lemon curd and the plum jam", "Lemon curd & plum jam", "Lemon curd + plum jam", "Lemon curd, and plum jam"):
            with self.subTest(name=name):
                self.assertEqual(refusal({**FULL, "name": name, "maker": "Linn's"}, "new jams from Linn's, in stock").reply, ia.ONE_PHOTO)

    def test_and_in_the_name_with_both_in_his_words_asks_which_one(self):
        self.assertEqual(refusal({**FULL, "name": "Lemon curd and plum jam", "maker": "Linn's"}, "got both from Linn's").reply, ia.ONE_PHOTO)

    def test_one_product_whose_name_has_and_is_not_two_products(self):
        for name in ("Salt and vinegar chips", "Mac and cheese"):
            with self.subTest(name=name):
                done = ia.describe_add({**FULL, "name": name, "maker": "Linn's", "shelf": "pantry"}, ctx(f"new {name.lower()} from Linn's, in stock"))
                self.assertEqual([op["op"] for op in done.ops], ["product.add", "store.confirm_selection"])

    def test_a_missing_name_still_asks_which_one_when_he_named_two(self):
        self.assertEqual(refusal({"photo": SHA}, "add the lemon curd and the plum jam").reply, ia.ONE_PHOTO)

    def test_he_picks_one_and_the_same_plan_then_drafts_it_two_turn_regression(self):
        first, pick = "add the lemon curd and the plum jam, both in stock", "The lemon curd only, please"
        slots = {**FULL, "name": "Lemon curd", "maker": "Linn's", "shelf": "pantry"}
        self.assertEqual(refusal(slots, first).reply, ia.ONE_PHOTO)  # turn 1: refused
        done = ia.describe_add(slots, ctx(first, pick))  # turn 2: his pick is in, the first message is still in the transcript
        self.assertEqual([op["op"] for op in done.ops], ["product.add", "store.confirm_selection"])
        self.assertEqual(done.ops[0]["args"]["name"], "Lemon curd")

    def test_a_pick_that_is_not_the_planned_product_or_lists_two_again_still_asks(self):
        first = "add the lemon curd and the plum jam, both in stock"
        slots = {**FULL, "name": "Lemon curd", "maker": "Linn's", "shelf": "pantry"}
        for later in ("The plum jam only, please", "yes, both", "the lemon curd and the plum jam", "in stock"):
            with self.subTest(later=later):
                self.assertEqual(refusal(slots, first, later).reply, ia.ONE_PHOTO)

    def test_a_pick_before_the_two_products_does_not_clear_them(self):
        slots = {**FULL, "name": "Lemon curd", "maker": "Linn's", "shelf": "pantry"}
        self.assertEqual(refusal(slots, "the lemon curd only", "add the lemon curd and the plum jam, both in stock").reply, ia.ONE_PHOTO)

    def test_add_bare_and_comma_lists_ask_before_any_plan(self):
        for text in ("add the lemon curd and the plum jam", "add lemon curd and plum jam", "add lemon curd, plum jam",
                     "add lemon curd, and plum jam", "add lemon curd & plum jam", "Adding lemon curd, plum jam, from Linn's"):
            for name in ("Lemon curd", "Plum jam"):
                with self.subTest(text=text, name=name):
                    slots = {**FULL, "name": name, "maker": "Linn's", "shelf": "pantry"}
                    given = copy.deepcopy(slots)
                    got = refusal(slots, text)
                    self.assertEqual((got.reply, got.kind, got.backlog), (ia.ONE_PHOTO, "question", None))
                    self.assertEqual(slots, given)
                    with self.assertRaises(ia.Refusal):
                        ia.plan_add(copy.deepcopy(slots), ctx(text))  # no ops at all

    def test_add_lists_with_a_describing_word_ask_before_any_plan(self):
        # sweet / organic open a product phrase ("sweet corn"), so they are not asides; the question comes whichever name was chosen
        for text, names in (("add lemon curd and sweet corn", ("Lemon curd", "Sweet corn")),
                            ("add lemon curd, organic raspberry jam", ("Lemon curd", "Organic raspberry jam")),
                            ("add sweet corn and lemon curd", ("Lemon curd", "Sweet corn")),
                            ("add organic raspberry jam, lemon curd", ("Lemon curd", "Organic raspberry jam")),
                            ("add lemon curd and the fresh local plum jam", ("Lemon curd", "Fresh local plum jam"))):
            for name in names:
                with self.subTest(text=text, name=name):
                    slots = {**FULL, "name": name, "maker": "Linn's", "shelf": "pantry"}
                    self.assertEqual(refusal(slots, text).reply, ia.ONE_PHOTO)
                    with self.assertRaises(ia.Refusal):
                        ia.plan_add(copy.deepcopy(slots), ctx(text))

    def test_add_describing_words_alone_are_still_asides(self):
        for text in ("add lemon curd, sweet", "add lemon curd, organic", "add lemon curd, fresh from the farm",
                     "add lemon curd, tasty on toast", "add lemon curd, sweet and tart", "add lemon curd and great photo",
                     "add lemon curd, fresh packaged in a jar", "add lemon curd, organic, in stock"):
            with self.subTest(text=text):
                done = ia.describe_add({**FULL, "name": "Lemon curd", "maker": "Linn's", "shelf": "pantry"}, ctx(text))
                self.assertEqual([op["op"] for op in done.ops], ["product.add", "store.confirm_selection"])

    def test_add_compound_name_and_caption_are_not_lists(self):
        for name, text in (("Salt and vinegar chips", "add salt and vinegar chips"),
                           ("Cookies and Cream chocolate", "Add Cookies and Cream chocolate from Linn's"),
                           ("Lemon curd", "add lemon curd, in a jar"),
                           ("Lemon curd", "add lemon curd, please"),
                           ("Lemon curd", "add lemon curd, on a plain counter"),
                           ("Lemon curd", "add lemon curd, great on toast and scones"),
                           ("Lemon curd", "add lemon curd, from Smith Farm in Salem, Oregon"),
                           ("Lemon curd", "add lemon curd, Smith Farm, Oregon"),
                           ("Lemon curd", "add lemon curd, in stock and on the pantry shelf")):
            with self.subTest(text=text):
                done = ia.describe_add({**FULL, "name": name, "maker": "Linn's", "shelf": "pantry"}, ctx(text))
                self.assertEqual([op["op"] for op in done.ops], ["product.add", "store.confirm_selection"])
        for name in ("Salt and vinegar chips", "Lemon curd"):  # a list that holds a compound name still asks
            with self.subTest(name=name):
                self.assertEqual(refusal({**FULL, "name": name, "maker": "Linn's"}, "add salt and vinegar chips and lemon curd").reply, ia.ONE_PHOTO)

    def test_add_bare_list_keeps_question_until_positive_single_choice(self):
        slots = {**FULL, "name": "Lemon curd", "maker": "Linn's", "shelf": "pantry"}
        for first in ("add lemon curd and plum jam", "add lemon curd, plum jam"):
            for later in ("ok", "add lemon curd and plum jam", "add lemon curd, plum jam", "yes, both", "the plum jam only please"):
                with self.subTest(first=first, later=later):
                    self.assertEqual(refusal(slots, first, later).reply, ia.ONE_PHOTO)
            with self.subTest(first=first, later="pick"):
                done = ia.describe_add(slots, ctx(first, "the lemon curd only please"))
                self.assertEqual([op["op"] for op in done.ops], ["product.add", "store.confirm_selection"])
                self.assertEqual(done.ops[0]["args"]["name"], "Lemon curd")
                self.assertNotIn("plum", repr(done.ops).lower())


class HouseDescriptionIsEnforced(unittest.TestCase):
    """Rule house-description: the hard checks refuse or ask, they do not only warn (finding 2)."""

    BAD = {"digits": "Lemon curd from Linn's in Cambria, 100 jars today. Spoon it onto warm buttered toast with tea.",
           "hype": "Tasty lemon curd from Linn's in Cambria. Spoon it onto warm buttered toast and enjoy a little tea.",
           "exclaim": "Lemon curd from Linn's in Cambria! Spoon it onto warm buttered toast and enjoy a little tea.",
           "question": "Lemon curd from Linn's in Cambria. Would you spoon it onto warm buttered toast with some tea?",
           "short": "Lemon curd from Linn's. Try it.",
           "long": "Lemon curd from Linn's in Cambria. " + "Spoon it onto warm buttered toast and sit with a cup of tea. " * 3,
           "one sentence": "Lemon curd from Linn's in Cambria that goes well on warm buttered toast with a cup of tea at breakfast.",
           "four sentences": "Lemon curd from Linn's in Cambria. Spoon it onto toast. Fold it into cream. Eat it with tea for breakfast."}

    def test_each_hard_failure_is_asked_again_and_makes_no_ops(self):
        for what, text in self.BAD.items():
            with self.subTest(what=what):
                got = refusal({**FULL, "name": "Lemon curd", "maker": "Linn's", "shelf": "pantry", "description": text}, "new lemon curd from Linn's, in stock")
                self.assertEqual(got.kind, "question")
                self.assertTrue(got.reply.startswith("That description won't match the others on the site:"), got.reply)
                self.assertTrue(got.reply.endswith("Could you send a different one?"))
                self.assertEqual(voice.check(voice.plain(got.reply)), [])

    def test_the_reviewers_example_names_every_reason(self):
        got = refusal({**FULL, "name": "Lemon curd", "maker": "Linn's", "description": "The best 100 jars of lemon curd! Tasty stuff for everyone."},
                      "new lemon curd from Linn's, in stock")
        for reason in ("a number", "sales words", "an exclamation or question mark", "shorter than the others"):
            self.assertIn(reason, got.reply)

    def test_the_reasons_are_the_spec_numbers(self):
        def two(n):  # two plain sentences, n characters in all
            body = ("Spoon it onto toast " * 20)[:n - 25].rstrip()
            return "Honey from Linn's here. " + body + "a" * (n - 25 - len(body)) + "."
        self.assertEqual(len(two(58)), 58)
        self.assertIn("shorter", " ".join(ia.description_problems(two(58))))  # 59 is the shortest on the site
        self.assertEqual(ia.description_problems(two(59)), [])
        self.assertEqual(ia.description_problems(two(167)), [])  # and 167 the longest
        self.assertIn("longer", " ".join(ia.description_problems(two(168))))
        self.assertEqual(ia.description_problems(FULL["description"]), [])
        self.assertEqual(ia.description_problems("Honey from Cal Poly in San Luis Obispo. Spoon a little beside cheese or onto buttered toast; give it a chance to be tasted on its own."), [])
        self.assertIn("longer", " ".join(ia.description_problems("Honey from here. " + "Spoon a little onto buttered toast. " * 5)))

    def test_a_claim_word_is_left_to_the_claims_gate_not_refused_here(self):
        self.assertEqual(ia.description_problems("Organic raspberry jam from Linn's in Cambria. Butter the toast first."), [])

    def test_a_good_description_of_his_own_goes_through(self):
        done = ia.describe_add({**FULL, "name": "Lemon curd", "maker": "Linn's", "shelf": "pantry",
                                "description": "Lemon curd from Linn's in Cambria. Spoon it onto warm buttered toast."}, ctx("new lemon curd from Linn's, in stock"))
        self.assertEqual(done.ops[0]["op"], "product.add")

    def test_the_drafted_description_passes_its_own_hard_checks(self):
        for name, maker, said in (("Cal Poly honey", "Cal Poly", "new honey from Cal Poly"), ("Jam", "don't know", "new jam, dont know who makes it")):
            text = ia.house_description({"name": name, "maker": maker}, ctx(said))
            self.assertEqual(ia.description_problems(text, said), [], text)


class PreviewShowsTheNewProduct(unittest.TestCase):
    """The proposal screenshot is of the new product card (with its picture and neighbours), also beside a new maker (finding 3)."""

    def draft(self, slots):
        scratch = testkit.Scratch({}, {"item.add": ia.ITEM_ADD}, photos=["reports/hass/newitem-1/synthetic/jar-white-sheet.jpg"])
        try:
            plan = ia.plan_add(slots, SimpleNamespace(today="2026-11-08", next_product_id="photo-product-175", content=CONTENT,
                                                texts=["new honey", "skip"]))
            out = scratch.editor.prepare(plan)
            self.assertEqual(out["result"], "ok", out)
            return out["draft"]["records"]
        finally:
            scratch.close()

    def test_a_new_maker_comes_first_but_the_product_is_what_is_shown(self):
        records = self.draft(dict(FULL))
        self.assertEqual([r["collection"] for r in records][:2], ["makers", "products"])
        target = preview.target_for(preview.proposal_record(records))
        self.assertEqual((target["kind"], target["id"], target["name"]), ("product", "photo-product-175", "Wildflower honey"))

    def test_a_saved_maker_shows_the_product_as_before(self):
        records = self.draft({**FULL, "maker": "Cal Poly", "place": None})
        self.assertEqual(preview.proposal_record(records), records[0])
        self.assertEqual(preview.target_for(records[0])["kind"], "product")

    def test_a_maker_alone_still_shows_the_maker(self):
        record = {"collection": "makers", "key": "Etto", "before": None, "after": {"name": "Etto", "place": "Templeton, California"}}
        self.assertIs(preview.proposal_record([record]), record)


class Picture(unittest.TestCase):
    def test_flag_off_a_photo_that_misses_the_house_look_gets_the_kind_advice(self):
        say, warn = ia.picture_review((SYN / "bag-red-cloth.jpg").read_bytes(), False)
        self.assertEqual((say, warn), ((), (ia.AS_TAKEN,)))

    def test_bytes_that_are_not_a_photo_are_one_plain_sentence(self):
        say, warn = ia.picture_review(b"not a photo", False)
        self.assertEqual(say, ())
        self.assertEqual(len(warn), 1)
        self.assertEqual(voice.check(warn[0]), [])

    def test_notes_show_the_lines_beside_the_draft(self):
        got = ia.notes("item.add", {**FULL, "name": "Cal Poly honey 8oz", "maker": "Cal Poly"}, ctx("Cal Poly honey 8oz $9"))
        self.assertIn(ia.STORE_LINE, got["say"])
        self.assertTrue(any(line.startswith("Left off: the price ($9)") for line in got["warn"]))
        self.assertEqual(ia.notes("item.add", {}, ctx()), {})


if __name__ == "__main__":
    unittest.main()
