"""SKILLS-FW-3 tests: a skill reply from the interpreter becomes slots, a plan and an ordinary draft; the open request keeps what
was asked between turns (spec 2.6, 2.7).

Conversation runs on the H02 throwaway repo with the PRODUCTION op registry and an injected clock; the interpreter is a scripted
stand-in (no model, no socket) that returns what a correct model returns for each text. The skills are TOY skills defined here,
because the catalog skills are later cards; they exercise the same Skill/Slot model. Every test also checks the rule that never
changes: nothing is written before the owner's own `yes <code>` (no writer commit, no approval row).
Run: python3 -m unittest hass.tests.test_skill_dispatch -v
"""
import json
import sys
import types
import unittest
from datetime import timedelta
from unittest import mock

from hass import conversation, voice
from hass.skills import dispatch
from hass.skills.model import Registry, Skill, Slot, Trigger, Undo
from hass.tests.test_conversation import CHAT, OWNER, SETTINGS, STRANGER, ConversationTestCase
from hass.tests.test_hike_flow import Clocked, Scripted

SATURDAY = "2026-11-07"  # the test clock starts Monday 2026-11-02
LIVE1 = "add a hike Saturday at 8am, Mill Creek trailhead, easy, bring water"
OPEN1 = "add a hike Saturday, Mill Creek trailhead, easy"  # no time: the one missing slot
FIRST = "add a hike this Saturday at 8am, easy, bring water"  # no place
LIVE3 = "create a new hike on Fiscalini Ranch this Saturday at 8am"


def _plan_hike(slots, ctx):
    args = {"title": slots["title"], "date": slots["day"], "time": slots["time"], "meetingPoint": slots["place"], "rsvpEnabled": False}
    if slots.get("difficulty"):
        args["difficulty"] = slots["difficulty"]
    return [{"op": "hike.create", "args": args}]


def _plan_describe(slots, ctx):
    return [{"op": "product.edit", "args": {"id": slots["product"], "description": slots["description"]}}]


def toy(name, label, slots, plan, **kw):
    fields = dict(name=name, label=label, summary="A toy skill for the dispatch tests.", triggers=(Trigger("toy"),), slots=slots,
                  rules=(), plan=plan, edits=(("hass/content/community.json", "events"),), side_effects=("none",),
                  preview="hike", approval="owner-yes", live_class="chat-live", undo=Undo("revert", "none"), refuse=(),
                  cases="hass/tests/fixtures/skills/toy/%s.jsonl" % name, version=1)
    fields.update(kw)
    return Skill(**fields)


HIKE_ADD = toy("hike.add", "add a hike", (
    Slot("title", "text", True, ask="What is the hike called?", limit=("event", "title")),
    Slot("place", "text", True, ask="Where should we meet?", owner_words=True),
    Slot("day", "day", True, ask="Which day is the hike?"),
    Slot("time", "clock", True, ask="What time does it start?"),
    Slot("difficulty", "text", False, owner_words=True)), _plan_hike)
DESCRIBE = toy("item.describe", "change an item's description", (
    Slot("product", "product_ref", True, ask="Which product?"),
    Slot("description", "text", True, ask="What should it say?", owner_words=True)), _plan_describe,
    edits=(("hass/content/products.json", "products[id].description"),), preview="product:x")
STOCK = toy("stock.set", "mark an item's stock", (
    Slot("level", "text", True, ask="Is it in stock, limited or out?"),),
    lambda s, c: [{"op": "product.set_availability", "args": {"id": "photo-product-001", "available": s["level"]}}],
    edits=(("hass/content/products.json", "products[id].available"),), preview="product:x")
PHOTO_ITEM = toy("item.picture", "put this photo on an item", (
    Slot("product", "product_ref", True, ask="Which product is it?"),
    Slot("photo", "attachment", True, from_attachment=True)),
    # a toy plan: the editor needs a stored original for a real set_photo; here the photo slot only has to arrive filled
    lambda s, c: [{"op": "hike.create", "args": {"title": "Photo " + s["photo"][:4], "date": "2026-11-07", "time": "09:00",
                                                  "meetingPoint": "Front door", "rsvpEnabled": False}}], preview="picture")


def registry_of(*skills):
    return Registry(skills={s.name: s for s in skills})


class StubRouter(types.ModuleType):
    """Stands in for hass.skills.router (SKILLS-FW-2, a separate PR) with its signature: ``candidates(text, hints, open_request,
    attachment, skills)`` -> up to three (name, score), best first. By default it backs what the scripted model says for the
    owner's text (the skill, or every skill of its calls, first at 10.0), so the agreement rule stays out of the way; a test
    that wants a split or an outsider sets ``ranking``."""

    def __init__(self, interp):
        super().__init__("hass.skills.router")
        self.interp, self.ranking, self.seen = interp, None, []

    def candidates(self, text, hints=None, open_request=None, attachment=None, skills=()):
        self.seen.append(text)
        if self.ranking is not None:
            return list(self.ranking)
        keys = [k for k in self.interp.mapping if text.endswith(k)]
        reply = self.interp.mapping[max(keys, key=len)] if keys else {}
        names = [c["skill"] for c in reply["calls"]] if "calls" in reply else [reply["skill"]] if "skill" in reply else []
        names = list(dict.fromkeys(names))
        rest = [s.name for s in skills.active() if s.name not in names]
        return [(n, 10.0 if i < len(names) else 1.0) for i, n in enumerate((names + rest)[:3])] if names else []


def skill_reply(name, revises=None, **slots):
    return {"skill": name, "slots": slots, "revises": revises}


MILL = dict(title="Mill Creek hike", place="Mill Creek trailhead", day=SATURDAY, time="08:00", difficulty="easy")


class SkillCase(ConversationTestCase):
    MODE = "both"
    SKILLS = (HIKE_ADD, DESCRIBE)

    def setUp(self):
        super().setUp()
        self.set_settings({**SETTINGS, "skills": {"mode": self.MODE}})
        self.asked = []
        self.interp = Scripted({}, self.asked)
        self.editor = Clocked(self.repo.state, lambda: self.now)
        self.registry = registry_of(*self.SKILLS)
        self.router = StubRouter(self.interp)
        patcher = mock.patch.dict(sys.modules, {"hass.skills.router": self.router})
        patcher.start()
        self.addCleanup(patcher.stop)
        self.conv = self.open()

    def open(self, ed=None):
        return conversation.Conversation(str(self.repo.state), ed or self.editor, self.interp, lambda: self.now,
                                         skills=getattr(self, "registry", None))

    def script(self, text, reply):
        self.interp.mapping[text] = reply

    def nothing_written(self):
        self.assertEqual(self.commits(), 0)
        self.assertEqual(self.conv.db.execute("SELECT COUNT(*) FROM approvals").fetchone()[0], 0)

    def live(self):
        return self.conv.requests.get(CHAT, self.now)

    def table(self, sql="SELECT * FROM open_requests"):
        if not self.conv.db.execute("SELECT 1 FROM sqlite_master WHERE name = 'open_requests'").fetchone(): return []
        return [dict(r) for r in self.conv.db.execute(sql)]


class CompleteRequestTests(SkillCase):
    def test_a_complete_hike_skill_reply_is_a_draft_with_every_slot_and_needs_the_owners_yes(self):
        self.script(LIVE1, skill_reply("hike.add", **MILL))
        draft, reply = self.propose(LIVE1)
        for line in ("A new hike: Mill Creek hike", "the meeting place: Mill Creek trailhead", "the start time: Saturday, Nov 7 at 8 am", "how hard it is: easy"):
            self.assertIn(line, reply)
        self.assertEqual(draft["state"], "proposed")
        self.assertEqual(self.live()["state"], "drafted")
        self.assertEqual(self.live()["draft_code"], draft["code"])
        self.nothing_written()
        self.assertEqual(self.say(f"yes {draft['code']}"), "approved")
        self.assertEqual(self.commits(), 1)
        self.assertEqual(self.live(), None)  # approved: the request is finished

    def test_a_slot_the_owner_did_not_say_is_left_off_and_listed(self):
        self.script(LIVE1, skill_reply("hike.add", **{**MILL, "difficulty": "strenuous"}))
        draft, reply = self.propose(LIVE1)
        self.assertNotIn("strenuous", reply)
        self.assertNotIn("difficulty", json.loads(draft["ops_json"])[0]["args"])
        self.assertIn("Left off", reply)

    def test_defaults_are_shown_as_what_was_set(self):
        dispatch.DERIVERS["toy_difficulty"] = lambda slots, ctx: "easy"
        self.addCleanup(dispatch.DERIVERS.pop, "toy_difficulty")
        # the hikes module (when this process has loaded it) words "hike.add" defaults for the real skill; this toy has no such wording
        patched = mock.patch.dict(dispatch.SET_PHRASES)
        patched.start()
        self.addCleanup(patched.stop)
        dispatch.SET_PHRASES.pop("hike.add", None)
        skill = toy("hike.add", "add a hike", (*HIKE_ADD.slots[:4], Slot("difficulty", "text", False, default="derive:toy_difficulty")), _plan_hike)
        self.registry = registry_of(skill)
        self.conv = self.open()
        self.script(LIVE1, skill_reply("hike.add", **{k: v for k, v in MILL.items() if k != "difficulty"}))
        _, reply = self.propose(LIVE1)
        self.assertIn("I set: difficulty: easy.", reply)


class SetPhrasesTests(SkillCase):
    """D8: a skill words the defaults it chose; the real dispatcher puts those plain phrases in the `I set:` line."""

    def sign_up_skill(self, **kw):  # the hikes default: sign-up off, which the generic wording would render as "signup: False"
        slots = (*HIKE_ADD.slots[:4], Slot("signup", "bool", False, default=False))
        self.registry = registry_of(toy("hike.add", "add a hike", slots, _plan_hike, **kw))
        self.conv = self.open()

    def setUp(self):
        super().setUp()
        # restore the hikes module's own wording afterwards: popping it for good made later modules in the same process
        # (test_skill_hidden_route) see the generic "signup: False" line
        patched = mock.patch.dict(dispatch.SET_PHRASES)
        patched.start()
        self.addCleanup(patched.stop)
        dispatch.SET_PHRASES.pop("hike.add", None)

    def propose_mill(self, **extra):
        slots = {k: v for k, v in MILL.items() if k != "difficulty"}
        self.script(LIVE1, skill_reply("hike.add", **slots, **extra))
        return self.propose(LIVE1)[1]

    def test_the_skills_own_wording_of_a_default_is_the_i_set_line(self):
        seen = []
        dispatch.SET_PHRASES["hike.add"] = lambda slots, ctx: seen.append(dict(slots)) or ["sign-up off"]
        self.sign_up_skill()
        reply = self.propose_mill()
        self.assertIn("I set: sign-up off.", reply)
        self.assertNotIn("signup", reply)
        self.assertNotIn("False", reply)
        self.assertEqual(len(seen), 1)
        self.assertNotIn("signup", seen[0])  # the slots as the owner gave them, before defaults
        self.assertEqual(voice.check(reply, long_ok=True), [])
        self.nothing_written()

    def test_several_phrases_are_joined_and_a_skill_module_can_carry_its_own(self):
        module = types.ModuleType("fake_skill_module")
        module.SET_PHRASES = {"hike.add": lambda slots, ctx: ["sign-up off", "the title Mill Creek hike"]}
        sys.modules["fake_skill_module"] = module
        self.addCleanup(sys.modules.pop, "fake_skill_module")
        plan = lambda slots, ctx: _plan_hike(slots, ctx)
        plan.__module__ = "fake_skill_module"
        self.registry = registry_of(toy("hike.add", "add a hike", (*HIKE_ADD.slots[:4], Slot("signup", "bool", False, default=False)), plan))
        self.conv = self.open()
        self.assertIn("I set: sign-up off; the title Mill Creek hike.", self.propose_mill())

    def test_nothing_set_means_no_line_and_a_value_the_owner_gave_is_not_a_default(self):
        dispatch.SET_PHRASES["hike.add"] = lambda slots, ctx: ["sign-up off"]
        self.sign_up_skill()
        self.assertNotIn("I set", self.propose_mill(signup=True))

    def test_a_skill_that_words_nothing_says_nothing_and_one_without_a_hook_keeps_the_name_and_value_line(self):
        dispatch.SET_PHRASES["hike.add"] = lambda slots, ctx: []
        self.sign_up_skill()
        self.assertNotIn("I set", self.propose_mill())
        del dispatch.SET_PHRASES["hike.add"]
        slots, shown = dispatch.apply_defaults(self.registry.skills["hike.add"], {"title": "T"}, None)
        self.assertEqual(shown, ["signup: False"])

    def test_the_default_is_still_said_when_the_owner_answers_a_missing_detail(self):
        dispatch.SET_PHRASES["hike.add"] = lambda slots, ctx: ["sign-up off"] if "signup" not in slots else []
        self.sign_up_skill()
        self.script(OPEN1, skill_reply("hike.add", **{k: v for k, v in MILL.items() if k not in ("time", "difficulty")}))
        self.assertEqual(self.say(OPEN1), "question")
        self.assertEqual(self.replies(), ["What time does it start?"])
        self.assertNotIn("signup", self.live()["slots"])  # the open request keeps what he said, not what the skill chose
        self.now += timedelta(minutes=2)
        _, reply = self.propose("8am")
        self.assertIn("I set: sign-up off.", reply)
        self.assertEqual(voice.check(reply, long_ok=True), [])
        self.nothing_written()

    def test_queued_calls_keep_owner_slots_and_the_missing_slot_after_defaults(self):
        dispatch.SET_PHRASES["hike.add"] = lambda slots, ctx: ["sign-up off"] if "signup" not in slots else []
        slots = (Slot("title", "text", True, default="Mill Creek hike"), *HIKE_ADD.slots[1:4],
                 Slot("signup", "bool", False, default=False))
        self.registry = registry_of(toy("hike.add", "add a hike", slots, _plan_hike))
        self.conv = self.open()
        text = "add the Mill Creek hike at Mill Creek trailhead and the Pine hike at Pine Saturday"
        calls = [{"skill": "hike.add", "slots": {"place": "Mill Creek trailhead", "day": SATURDAY}},
                 {"skill": "hike.add", "slots": {"title": "Pine hike", "place": "Pine", "day": SATURDAY}}]
        self.script(text, {"calls": calls})
        self.assertEqual(self.say(text), "question")
        self.assertEqual(self.replies(), ["What time does it start?"])
        self.assertEqual(self.live()["asked_slot"], "time")  # not the title filled by a default
        self.assertNotIn("title", self.live()["slots"])
        self.assertNotIn("signup", self.live()["slots"])
        self.assertNotIn("signup", self.live()["calls"][0]["slots"])
        for answer in ("8am", "9am"):
            self.now += timedelta(minutes=1)
            self.conv = self.open()  # persisted waiting and queued calls, not in-memory defaults
            self.assertEqual(self.say(answer), "proposed")
            replies = self.replies()
            self.assertIn("I set: sign-up off.", replies[0].splitlines())
            if answer == "8am":
                self.assertEqual(replies[1:], ["What time does it start?"])
        self.assertEqual(len(self.drafts()), 2)
        self.nothing_written()

    def test_queued_plan_question_does_not_ask_for_a_defaulted_slot(self):
        class PlanQuestion(Exception):
            kind = "question"
            reply = "Which trailhead do you mean: north or south?"

        def plan(slots, ctx):
            raise PlanQuestion()

        slots = (Slot("title", "text", True, default="Mill Creek hike"), *HIKE_ADD.slots[1:4])
        self.registry = registry_of(toy("hike.add", "add a hike", slots, plan))
        self.conv = self.open()
        text = "add hikes at Mill Creek trailhead and Pine Saturday at 8am"
        calls = [{"skill": "hike.add", "slots": {"place": place, "day": SATURDAY, "time": "08:00"}}
                 for place in ("Mill Creek trailhead", "Pine")]
        self.script(text, {"calls": calls})
        self.assertEqual(self.say(text), "question")
        self.assertEqual(self.replies(), [PlanQuestion.reply])
        self.assertIsNone(self.live()["asked_slot"])
        self.assertNotIn("title", self.live()["slots"])
        self.nothing_written()

    def test_a_sign_up_the_owner_gave_before_the_question_is_not_called_a_default(self):
        dispatch.SET_PHRASES["hike.add"] = lambda slots, ctx: ["sign-up off"] if "signup" not in slots else []
        self.sign_up_skill()
        self.script(OPEN1, skill_reply("hike.add", **{k: v for k, v in MILL.items() if k not in ("time", "difficulty")}, signup=True))
        self.assertEqual(self.say(OPEN1), "question")
        self.assertEqual(self.replies(), ["What time does it start?"])
        self.now += timedelta(minutes=2)
        self.assertNotIn("I set", self.propose("8am")[1])


class MultiTurnTests(SkillCase):
    """The live hike texts of 2026-11-08 as multi-turn rows: the answer is joined to what it answers."""

    def test_the_missing_time_is_asked_once_and_the_short_answer_is_read_by_code_without_the_model(self):
        self.script(OPEN1, skill_reply("hike.add", **{k: v for k, v in MILL.items() if k != "time"}))
        self.assertEqual(self.say(OPEN1), "question")
        self.assertEqual(self.replies(), ["What time does it start?"])
        req = self.live()
        self.assertEqual((req["skill"], req["asked_slot"], req["texts"]), ("hike.add", "time", [OPEN1]))
        self.assertEqual(len(self.asked), 1)
        self.now += timedelta(minutes=2)
        draft, reply = self.propose("8am")
        self.assertEqual(len(self.asked), 1)  # no second model call: a clock answer to a clock slot
        self.assertIn("the meeting place: Mill Creek trailhead", reply)
        self.assertEqual(json.loads(draft["ops_json"])[0]["args"]["time"], "08:00")
        self.nothing_written()

    def test_a_text_answer_goes_to_the_model_with_the_whole_request_and_is_merged_by_code(self):
        self.script(FIRST, skill_reply("hike.add", title="Fiscalini Ranch hike", day=SATURDAY, time="08:00", difficulty="easy"))
        self.assertEqual(self.say(FIRST), "question")
        self.assertEqual(self.replies(), ["Where should we meet?"])
        self.script("Fiscalini Ranch", skill_reply("hike.add", place="Fiscalini Ranch"))
        self.assertEqual(self.say("Fiscalini Ranch"), "proposed")
        text, recent = self.asked[-1]
        self.assertEqual((text, recent["skill"], recent["asked_slot"], recent["earlier"]), ("Fiscalini Ranch", "hike.add", "place", [FIRST]))
        self.assertEqual(recent["slots"]["title"], "Fiscalini Ranch hike")
        self.assertEqual(recent["question"], "Where should we meet?")
        self.nothing_written()

    def test_the_owners_earlier_words_count_for_the_owner_words_check_of_a_later_answer(self):
        first = "add a hike Saturday at 8am, called Wilson hike, it is moderate"
        self.script(first, skill_reply("hike.add", title="Wilson hike", day=SATURDAY, time="08:00", difficulty="moderate"))
        self.say(first)
        self.script("the Wilson trailhead", skill_reply("hike.add", place="Wilson trailhead"))
        self.assertEqual(self.say("the Wilson trailhead"), "proposed")  # "wilson" was said in the joined texts; "trailhead" now

    def test_a_vague_value_the_owner_never_said_is_not_kept_as_a_place(self):
        self.script(FIRST, skill_reply("hike.add", title="Beach hike", place="Secret Cove", day=SATURDAY, time="08:00"))
        self.assertEqual(self.say(FIRST), "question")
        self.assertEqual(self.replies(), ["Where should we meet?"])  # "Secret Cove" is not in the owner's words
        self.assertNotIn("place", self.live()["slots"])


class MergeTests(SkillCase):
    def test_a_slot_that_cannot_be_used_is_asked_again_at_most_twice_then_the_request_is_written_down(self):
        self.script(FIRST, skill_reply("hike.add", title="Beach hike", day=SATURDAY, time="08:00"))
        self.say(FIRST)  # asks for the place (question 1)
        self.replies()
        for n in (2, 3):
            self.script(f"huh {n}", skill_reply("hike.add", place=None))
            self.assertEqual(self.say(f"huh {n}"), "question")
            self.assertEqual(self.replies(), ["Where should we meet?"])
        self.script("huh 4", skill_reply("hike.add", place=None))
        self.assertEqual(self.say("huh 4"), "backlog")
        [reply] = self.replies()
        self.assertTrue(reply.startswith("I'm not getting this. Send it in one message, like: toy"), reply)
        self.assertEqual(self.live(), None)
        self.assertEqual(self.conv.db.execute("SELECT reason FROM backlog").fetchall()[0][0], "stuck")
        self.nothing_written()

    def test_an_unknown_slot_name_is_ignored_and_a_new_valid_value_replaces_an_old_one(self):
        self.script(OPEN1, skill_reply("hike.add", **{k: v for k, v in MILL.items() if k != "time"}, capacity=40))
        self.say(OPEN1)
        self.assertNotIn("capacity", self.live()["slots"])
        self.script("make that 10am and call it Mill Creek loop", skill_reply("hike.add", time="10:00", title="Mill Creek loop"))
        self.assertEqual(self.say("make that 10am and call it Mill Creek loop"), "proposed")
        args = json.loads(self.drafts()[-1]["ops_json"])[0]["args"]
        self.assertEqual((args["time"], args["title"]), ("10:00", "Mill Creek loop"))


class CheapAnswerTests(SkillCase):
    SKILLS = (HIKE_ADD, DESCRIBE)

    def ask_for_bread(self):
        self.script("make the bread say tasty", skill_reply("item.describe", product="bread", description="tasty"))
        self.assertEqual(self.say("make the bread say tasty"), "question")
        [reply] = self.replies()
        self.assertTrue(reply.startswith("Which one do you mean:"), reply)
        self.assertEqual(len(self.live()["ask"]["ids"]), 2)

    def test_a_choice_by_number_fills_the_product_without_the_model(self):
        self.ask_for_bread()
        calls = len(self.asked)
        self.assertEqual(self.say("2"), "proposed")
        self.assertEqual(len(self.asked), calls)
        self.assertEqual(json.loads(self.drafts()[-1]["ops_json"])[0]["args"]["id"], "photo-product-122")
        self.nothing_written()

    def test_a_choice_by_name_fills_the_product_and_an_unclear_one_goes_to_the_model(self):
        self.ask_for_bread()
        calls = len(self.asked)
        self.script("the rye one", skill_reply("item.describe", product="Rye bread"))
        self.assertEqual(self.say("the rye one"), "proposed")
        self.assertEqual(len(self.asked), calls)
        self.assertEqual(json.loads(self.drafts()[-1]["ops_json"])[0]["args"]["id"], "photo-product-122")

    def test_a_long_answer_is_never_read_by_code(self):
        self.ask_for_bread()
        calls = len(self.asked)
        long_answer = "the second one please, I think that is the right one, sorry for the confusion earlier today"
        self.script(long_answer, skill_reply("item.describe", product="Rye bread"))
        self.say(long_answer)
        self.assertEqual(len(self.asked), calls + 1)


class SeveralItemsTests(SkillCase):
    def test_combined_proposal_names_the_hike_difficulty_left_off(self):
        text = ("change the honey description to Big Sur honey and add the Mill Creek hike "
                "Saturday at 8am at Mill Creek trailhead")
        self.script(text, {"calls": [
            {"skill": "item.describe", "slots": {"product": "Big Sur Honey Company honey", "description": "Big Sur honey"}},
            {"skill": "hike.add", "slots": MILL},  # the interpreter supplied "easy"; the owner did not
        ]})
        self.assertEqual(self.say(text), "proposed")
        [reply] = self.replies()
        self.assertIn("Left off (you didn't say it): difficulty.", reply.splitlines())
        [draft] = self.drafts()
        ops = json.loads(draft["ops_json"])
        self.assertEqual([op["op"] for op in ops], ["product.edit", "hike.create"])
        self.assertNotIn("difficulty", ops[1]["args"])
        self.nothing_written()

    def test_complete_calls_make_one_draft_and_the_incomplete_one_is_asked_next(self):
        text = "add the Mill Creek hike Saturday 8am at Mill Creek trailhead and change the bread"
        self.script(text, {"calls": [
            {"skill": "hike.add", "slots": {k: v for k, v in MILL.items() if k != "difficulty"}},
            {"skill": "item.describe", "slots": {"product": "bread"}}], "revises": None})
        self.assertEqual(self.say(text), "proposed")
        replies = self.replies()
        self.assertEqual(len(replies), 2)
        self.assertIn("Reply yes to save it", replies[0])
        self.assertTrue(replies[1].startswith("Which one do you mean:"), replies[1])
        self.assertEqual(len([d for d in self.drafts() if d["state"] == "proposed"]), 1)
        req = self.live()
        self.assertEqual((req["skill"], req["asked_slot"]), ("item.describe", "product"))
        self.nothing_written()
        self.assertEqual(self.say("yes"), "approved")  # the draft can be approved while the next question waits

    def test_two_incomplete_calls_are_asked_and_drafted_in_sequence(self):
        text = "add the Mill Creek hike at Mill Creek trailhead and the Fiscalini Ranch hike at Fiscalini parking lot Saturday, easy"
        no_time = {k: v for k, v in MILL.items() if k != "time"}
        fisc = {**no_time, "title": "Fiscalini Ranch hike", "place": "Fiscalini parking lot"}
        self.script(text, {"calls": [{"skill": "hike.add", "slots": no_time}, {"skill": "hike.add", "slots": fisc}], "revises": None})
        self.assertEqual(self.say(text), "question")
        self.assertEqual(self.replies(), ["What time does it start?"])
        self.assertEqual(len(self.live()["calls"]), 1)  # the second call waits in the store
        self.now += timedelta(minutes=1)
        self.assertEqual(self.say("8am"), "proposed")
        replies = self.replies()
        self.assertIn("Mill Creek hike", replies[0])
        self.assertEqual(replies[-1], "What time does it start?")  # the queued call is asked next
        req = self.live()
        self.assertEqual((req["skill"], req["slots"]["title"], req["calls"]), ("hike.add", "Fiscalini Ranch hike", []))
        self.now += timedelta(minutes=1)
        self.conv = self.open()  # a restart between the two answers keeps the queue
        self.assertEqual(self.say("9am"), "proposed")
        self.assertIn("Fiscalini Ranch hike", self.replies()[0])
        self.assertEqual(len([d for d in self.drafts() if d["state"] == "proposed"]), 2)
        self.nothing_written()

    def test_more_than_the_limit_of_calls_is_not_a_skill_reply(self):
        many = {"calls": [{"skill": "hike.add", "slots": {}}] * (dispatch.MAX_CALLS + 1), "revises": None}
        self.assertIsNone(dispatch.checked(many))


class NoneAndUnknownTests(SkillCase):
    def test_none_is_written_down_and_changes_nothing(self):
        self.script("order eggs from the farm", {"skill": "none", "summary": "order eggs from the farm"})
        self.assertEqual(self.say("order eggs from the farm"), "backlog")
        [reply] = self.replies()
        self.assertTrue(reply.startswith("I can't do that yet. I wrote it down as request #1."), reply)
        self.assertEqual(self.say("backlog"), "backlog")
        self.assertIn("1. Nov 2 - order eggs from the farm", self.replies()[0])
        self.nothing_written()

    def test_an_unknown_skill_name_is_written_down_too(self):
        self.script("do the thing", skill_reply("made.up", x=1))
        self.assertEqual(self.say("do the thing"), "backlog")
        self.assertEqual(self.conv.db.execute("SELECT reason FROM backlog").fetchone()[0], "unknown-skill")

    def test_forget_backlog_removes_one_row_and_only_that_row(self):
        for n in (1, 2):
            self.script(f"ask {n}", {"skill": "none", "summary": f"ask {n}"})
            self.say(f"ask {n}")
        self.replies()
        self.assertEqual(self.say("forget backlog.1"), "backlog-forgot")
        self.assertEqual(self.replies(), ["Done. I took that one off the list."])
        self.assertEqual([r[0] for r in self.conv.db.execute("SELECT id FROM backlog")], [2])
        self.assertEqual(self.say("forget backlog.1"), "backlog-none")
        self.assertEqual(self.say("forget backlog.7"), "backlog-none")


class ReviseAndTopicTests(SkillCase):
    def test_a_correction_of_the_same_skill_revises_the_draft_it_made(self):
        self.script(LIVE1, skill_reply("hike.add", **MILL))
        first, _ = self.propose(LIVE1)
        self.now += timedelta(minutes=1)
        self.script("make that 10am", skill_reply("hike.add", time="10:00"))
        self.assertEqual(self.say("make that 10am"), "proposed")
        states = {d["code"]: d["state"] for d in self.drafts()}
        self.assertEqual(states[first["code"]], "rejected")
        self.assertEqual(sum(1 for s in states.values() if s == "proposed"), 1)
        self.nothing_written()

    def test_a_different_complete_request_supersedes_the_open_one_and_status_says_so(self):
        self.script(OPEN1, skill_reply("hike.add", **{k: v for k, v in MILL.items() if k != "time"}))
        self.say(OPEN1)
        self.replies()
        self.script("make the honey say Big Sur honey", skill_reply("item.describe", product="Big Sur Honey Company honey", description="Big Sur honey"))
        self.assertEqual(self.say("make the honey say Big Sur honey"), "proposed")
        old = self.table("SELECT state, skill FROM open_requests WHERE skill = 'hike.add'")
        self.assertEqual([r["state"] for r in old], ["superseded"])
        self.replies()
        self.say("status")
        self.assertIn("Replaced: add a hike", self.replies()[0])

    def test_no_cancels_the_open_request(self):
        self.script(OPEN1, skill_reply("hike.add", **{k: v for k, v in MILL.items() if k != "time"}))
        self.say(OPEN1)
        self.replies()
        self.assertEqual(self.say("no"), "no-target")
        self.assertEqual(self.live(), None)
        self.script("8am", skill_reply("hike.add", time="08:00"))
        self.assertEqual(self.say("8am"), "question")  # starts over: nothing of the cancelled request is left to join
        self.assertEqual(self.live()["slots"], {"time": "08:00"})

    def test_a_cancel_reply_drops_the_request(self):
        self.script(OPEN1, skill_reply("hike.add", **{k: v for k, v in MILL.items() if k != "time"}))
        self.say(OPEN1)
        self.script("scratch that, never mind", {"cancel": True})
        self.assertEqual(self.say("scratch that, never mind"), "cancelled")
        self.assertEqual(self.live(), None)


class StatusTests(SkillCase):
    def test_status_names_the_open_request_in_plain_words(self):
        self.script(OPEN1, skill_reply("hike.add", **{k: v for k, v in MILL.items() if k != "time"}))
        self.say(OPEN1)
        self.replies()
        self.say("status")
        self.assertIn("Open: add a hike, waiting for the time", self.replies()[0])

    def test_status_with_nothing_open_has_no_open_line(self):
        self.say("status")
        self.assertNotIn("Open:", self.replies()[0])


class PhotoTests(SkillCase):
    """Spec 2.7: the photo of a message joins the open request (the store side; the fetch is _photo's, unchanged)."""
    SKILLS = (HIKE_ADD, PHOTO_ITEM)
    SHA = "a" * 64

    def test_a_photo_fills_the_asked_attachment_slot_and_the_request_becomes_a_draft(self):
        self.script("this is for the jam", skill_reply("item.picture", product="Cal Poly strawberry jam"))
        self.assertEqual(self.say("this is for the jam"), "question")  # asks for the photo (the attachment slot)
        self.assertEqual(self.live()["asked_slot"], "photo")
        photo = conversation.Inbound("p2", CHAT, OWNER, "", False, "new", self.now.isoformat(), 1)
        self.assertEqual(self.conv.dispatch.photo(photo, self.now, self.SHA, ""), "proposed")
        self.assertEqual(self.live()["state"], "drafted")
        self.assertEqual(self.live()["slots"]["photo"], self.SHA)
        self.assertEqual(self.live()["attachments"], [self.SHA])

    def test_only_photo_skills_are_offered_for_a_photo_with_no_request(self):
        names = [s.name for s in self.conv.dispatch.photo_skills()]
        self.assertEqual(names, ["item.picture"])

    def test_a_photo_for_a_skill_without_an_attachment_slot_is_asked_about(self):
        how, req = self.conv.requests.bind_attachment(CHAT, "p1", self.SHA, self.now, self.registry)
        self.assertEqual(how, "opened")
        self.script("add a hike", skill_reply("hike.add", title="x"))
        self.assertEqual(self.say("add a hike"), "question")
        self.assertIn("A photo goes with put this photo on an item", self.replies()[0])


class ModeTests(SkillCase):
    MODE = "ops-only"

    def test_ops_only_reads_a_skill_reply_as_unreadable_exactly_as_before_and_makes_no_skill_state(self):
        self.script(LIVE1, skill_reply("hike.add", **MILL))
        self.assertEqual(self.say(LIVE1), "unsupported")
        self.assertEqual(self.replies(), [conversation.UNREADABLE["unsupported"]])
        self.assertEqual(self.table(), [])
        self.assertIsNone(self.conv.dispatch)
        self.nothing_written()

    def test_a_bad_mode_refuses_to_start(self):
        self.set_settings({**SETTINGS, "skills": {"mode": "sometimes"}})
        with self.assertRaises(conversation.ConfigError):
            self.open()
        self.set_settings({**SETTINGS, "houseRender": "yes"})
        with self.assertRaises(conversation.ConfigError):
            self.open()

    def test_the_modes_and_the_house_render_flag_are_read_from_the_host_settings(self):
        self.set_settings({**SETTINGS, "skills": {"mode": "skills-first"}, "houseRender": True})
        conv = self.open()
        self.assertEqual((conv.settings["skillsMode"], conv.settings["houseRender"]), ("skills-first", True))
        self.set_settings(SETTINGS)
        conv = self.open()
        self.assertEqual((conv.settings["skillsMode"], conv.settings["houseRender"]), ("ops-only", False))


class SkillsFirstTests(SkillCase):
    MODE = "skills-first"

    def test_raw_ops_for_something_a_skill_owns_are_not_taken(self):
        self.script("raw", {"ops": [{"op": "hike.create", "args": {"title": "x"}}], "revises": None})
        self.assertEqual(self.say("raw"), "unsupported")
        self.nothing_written()

    def test_raw_ops_nobody_owns_still_work(self):
        from hass.tests.test_conversation import _ops
        self.registry = registry_of(HIKE_ADD)  # no skill owns the product ops
        self.conv = self.open()
        self.script("hours", _ops(("product.edit", {"id": "photo-product-001", "description": "Ripe and creamy."})))
        self.assertEqual(self.say("hours"), "proposed")


class OnlyTheOwnerTests(SkillCase):
    def test_a_stranger_or_another_chat_neither_opens_nor_reads_nor_closes_a_request(self):
        self.script(OPEN1, skill_reply("hike.add", **{k: v for k, v in MILL.items() if k != "time"}))
        self.say(OPEN1)
        self.replies()
        before = self.table()
        self.script("8am", skill_reply("hike.add", time="08:00"))
        self.assertEqual(self.say("8am", sender=STRANGER), "ignored")
        self.assertEqual(self.say("8am", chat="chat-fixture-group"), "ignored")
        self.assertEqual(self.say("no", sender=STRANGER), "ignored")
        self.assertEqual(self.replies(), [])
        self.assertEqual(self.table(), before)
        self.assertEqual(len(self.asked), 1)  # the model was never asked about them
        self.assertIsNone(self.conv.requests.get("someone-else", self.now))


class QueuedCallsTests(SkillCase):
    """RETURN item 2: calls the owner has not finished are kept and asked one at a time, across answers, approvals and restarts."""
    THREE = "add the Mill hike, the Pine hike and the Ocean hike on Saturday"

    def test_a_plain_read_only_skill_keeps_the_old_paths(self):  # AV1109-06: only READ_ONLY_LONG skills get the caption paths
        look = toy("shop.look", "look at the shop", (), lambda s, c: [], edits=(), preview="none", approval="none",
                   live_class="read-only", undo=Undo("none", "none"))
        self.conv.dispatch.registry = registry_of(HIKE_ADD, look)
        self.script("inspect and add", {"calls": [{"skill": "shop.look", "slots": {}}, {"skill": "hike.add", "slots": MILL}], "revises": None})
        self.assertEqual(self.say("inspect and add"), "backlog")  # a read-only call in a batch is written down, as before
        self.assertEqual(self.drafts(), [])
        self.assertNotIn("shop.look", dispatch.READ_ONLY_LONG)
        with mock.patch.dict(dispatch.READ_ONLY, {"shop.look": lambda s, c: "x" * 700}):
            self.script("inspect", skill_reply("shop.look"))
            with self.assertRaisesRegex(voice.VoiceError, "too long for one message"):  # an everyday answer may not run long
                self.say("inspect")
        self.assertIsNone(dispatch.Ctx(None, None, {}, [], None).site_dir)  # the old constructor still works
        self.assertEqual(self.conv.dispatch._ctx(self.now, []).site_dir, self.repo.wt / "storefront-mockup")
        self.nothing_written()

    def three(self):
        calls = [{"skill": "hike.add", "slots": {"title": f"{n} hike", "place": n, "day": SATURDAY}} for n in ("Mill", "Pine", "Ocean")]
        self.script(self.THREE, {"calls": calls, "revises": None})

    def test_three_incomplete_calls_become_three_drafts_asked_one_at_a_time(self):
        self.three()
        self.assertEqual(self.say(self.THREE), "question")
        self.assertEqual(self.replies(), ["What time does it start?"])
        self.assertEqual(len(self.live()["calls"]), 2)
        for time, left in (("8am", 1), ("9am", 0), ("10am", 0)):
            self.now += timedelta(minutes=1)
            self.assertEqual(self.say(time), "proposed")
            replies = self.replies()
            self.assertEqual(len(replies), 1 if time == "10am" else 2, replies)
            if time != "10am":
                self.assertEqual(replies[1], "What time does it start?")
            self.assertEqual(len(self.live()["calls"]), left)
        titles = [json.loads(d["ops_json"])[0]["args"]["title"] for d in self.drafts() if d["state"] == "proposed"]
        self.assertEqual(sorted(titles), ["Mill hike", "Ocean hike", "Pine hike"])
        self.nothing_written()

    def test_the_queue_survives_an_approval_and_a_restart(self):
        self.three()
        self.say(self.THREE)
        self.replies()
        self.assertEqual(self.say("8am"), "proposed")
        self.replies()
        self.conv = self.open()  # the service restarts: the queue is in the store, not in memory
        self.assertEqual(len(self.live()["calls"]), 1)
        self.assertEqual(self.say("yes"), "approved")
        self.replies()
        self.conv = self.open()
        self.assertEqual((self.live()["skill"], self.live()["asked_slot"], len(self.live()["calls"])), ("hike.add", "time", 1))
        self.assertEqual(self.say("9am"), "proposed")
        self.replies()
        self.assertEqual(self.live()["skill"], "hike.add")  # the third is asked now
        self.assertEqual(self.live()["calls"], [])
        self.assertEqual(self.say("10am"), "proposed")
        self.assertEqual(self.commits(), 1)  # only the approved one was ever written

    def test_a_question_that_cannot_be_answered_does_not_lose_the_calls_behind_it(self):
        self.three()
        self.say(self.THREE)
        self.replies()
        for n in range(dispatch.openreq.MAX_UNRESOLVED):  # "banana" is no time: the third time the ask is given up
            self.script(f"banana{n}", skill_reply("hike.add", time=f"banana{n}"))
            self.say(f"banana{n}")
        self.assertEqual(len(self.live()["calls"]), 1)  # the first was written down as stuck; the second is asked, the third waits
        self.assertEqual(self.live()["slots"]["title"], "Pine hike")


class NegationTests(SkillCase):
    """RETURN item 3: an owner-word fact the owner denied is never written."""

    def test_the_word_check_reads_negation_in_one_message_and_across_messages(self):
        yes, no = dispatch.traceable, lambda v, t: not dispatch.traceable(v, t)
        self.assertTrue(no("easy", ["the hike is not easy"]))
        self.assertTrue(no("easy", ["it isn't easy", "meet at 8"]))
        self.assertTrue(no("easy", ["never really easy"]))
        self.assertTrue(no("easy", ["without an easy bit"]))
        self.assertTrue(yes("easy", ["not hard, easy"]))
        self.assertTrue(yes("easy", ["not steep. easy hike"]))
        self.assertTrue(yes("easy", ["the hike is not easy", "sorry, it is easy after all"]))  # the newest mention decides
        self.assertTrue(no("easy", ["easy hike", "no wait, it is not easy"]))
        self.assertTrue(yes("Mill Creek trailhead", ["meet at the Mill Creek trailhead, not the parking lot"]))
        self.assertTrue(no("parking lot", ["meet at the Mill Creek trailhead, not the parking lot"]))
        self.assertTrue(no("steep", ["it is flat"]))  # never said at all

    def test_a_denied_difficulty_is_left_off_the_draft_and_said_so(self):
        text = "add a hike Saturday at 8am, Mill Creek trailhead, not easy"
        self.script(text, skill_reply("hike.add", **MILL))
        draft, reply = self.propose(text)
        self.assertNotIn("difficulty", json.loads(draft["ops_json"])[0]["args"])
        self.assertIn("Left off (you didn't say it): difficulty.", reply)

    def test_a_denied_value_stays_denied_in_a_later_turn_and_a_correction_brings_it_back(self):
        first = "add a hike Saturday at 8am, Mill Creek trailhead, it is not easy"
        self.script(first, skill_reply("hike.add", **{**MILL, "place": "Mill Creek trailhead"}))
        draft, _ = self.propose(first)
        self.assertNotIn("difficulty", json.loads(draft["ops_json"])[0]["args"])
        self.script("sorry, it is easy", skill_reply("hike.add", difficulty="easy"))
        self.assertEqual(self.say("sorry, it is easy"), "proposed")
        self.assertEqual(json.loads(self.drafts()[-1]["ops_json"])[0]["args"]["difficulty"], "easy")


class AgreementTests(SkillCase):
    """RETURN item 4: the router's second opinion is required; without it, or against it, the owner is asked and nothing is drafted."""
    SAYS = "add a hike Saturday at 8am, Mill Creek trailhead, easy"

    def setUp(self):
        super().setUp()
        self.script(self.SAYS, skill_reply("hike.add", **MILL))

    def asked_nothing_drafted(self, question):
        self.assertEqual(self.say(self.SAYS), "question")
        self.assertEqual(self.replies(), [question])
        self.assertEqual([d for d in self.drafts() if d["state"] == "proposed"], [])
        self.assertEqual(self.live()["skill"], None)
        self.nothing_written()

    def test_a_missing_router_asks_instead_of_drafting_and_the_owners_choice_then_stands(self):
        sys.modules["hass.skills.router"] = None  # import fails: the module is absent
        self.asked_nothing_drafted("Do you want to add a hike?")
        self.assertEqual(self.say(self.SAYS), "proposed")  # asked again with the same words: that is the owner's choice

    def test_a_failing_router_asks_too(self):
        def boom(*a, **k):
            raise RuntimeError("router down")
        self.router.candidates = boom
        self.asked_nothing_drafted("Do you want to add a hike?")

    def test_a_pick_outside_the_routers_top_three_is_asked(self):
        self.router.ranking = [("item.describe", 10.0)]
        self.asked_nothing_drafted("Do you want to add a hike, or change an item's description?")

    def test_a_split_leading_pair_is_asked_whichever_was_picked(self):
        self.router.ranking = [("hike.add", 10.0), ("item.describe", 9.5)]
        self.asked_nothing_drafted("Do you want to add a hike, or change an item's description?")

    def test_a_pick_just_behind_the_leader_is_asked(self):
        self.router.ranking = [("item.describe", 10.0), ("hike.add", 9.5)]
        self.asked_nothing_drafted("Do you want to add a hike, or change an item's description?")

    def test_a_clear_agreement_drafts(self):
        self.router.ranking = [("hike.add", 10.0), ("item.describe", 5.0)]
        self.assertEqual(self.say(self.SAYS), "proposed")
        self.assertEqual(self.router.seen, [self.SAYS])

    def test_several_calls_need_the_router_too(self):
        text = "add the Mill hike on Saturday and change the bread"
        self.script(text, {"calls": [{"skill": "hike.add", "slots": {"title": "Mill hike", "place": "Mill", "day": SATURDAY, "time": "08:00"}},
                                     {"skill": "item.describe", "slots": {"product": "bread"}}], "revises": None})
        self.router.ranking = [("hike.add", 10.0)]
        self.assertEqual(self.say(text), "question")
        self.assertEqual(self.replies(), ["Do you want to add a hike, or change an item's description?"])
        self.nothing_written()
        self.assertEqual([d for d in self.drafts() if d["state"] == "proposed"], [])


class MultiCallAgreementTests(SkillCase):
    SKILLS = (HIKE_ADD, DESCRIBE, STOCK)
    TEXT = ("add the Mill Creek hike Saturday at 8am at Mill Creek trailhead, easy, "
            "and the Pine hike at Pine; change the honey description to Big Sur honey")
    QUESTION = "Do you want to add a hike, or change an item's description?"

    def setUp(self):
        super().setUp()
        self.router.ranking = [("hike.add", 10.0), ("item.describe", 9.5), ("stock.set", 1.0)]
        self.calls = {
            "hike.add": {"skill": "hike.add", "slots": MILL},
            "item.describe": {"skill": "item.describe", "slots": {
                "product": "Big Sur Honey Company honey", "description": "Big Sur honey"}},
            "stock.set": {"skill": "stock.set", "slots": {"level": "no"}},
        }

    def call_reply(self, names):
        calls = [self.calls[n] for n in names]
        if names.count("hike.add") > 1:
            calls[-1] = {"skill": "hike.add", "slots": {**MILL, "title": "Pine hike", "place": "Pine"}}
        return {"calls": calls, "revises": None}

    def ask_for(self, names, pid=None):
        self.script(self.TEXT, self.call_reply(names))
        self.assertEqual(self.say(self.TEXT, pid=pid), "question")
        self.assertEqual(self.replies(), [self.QUESTION])
        self.assertIsNone(self.live()["skill"])
        self.assertEqual(self.live()["ask"]["agree"], ["hike.add", "item.describe"])
        self.assertEqual(self.drafts(), [])
        self.nothing_written()

    def test_multi_call_near_tie_missing_runner_up_asks(self):
        self.ask_for(["hike.add", "stock.set"])

    def test_repeated_leader_calls_do_not_settle_tie(self):
        self.ask_for(["hike.add", "hike.add"])

    def test_multi_call_including_both_leaders_proceeds(self):
        # Reversed order plus a further call still includes both leading names.
        self.script(self.TEXT, self.call_reply(["item.describe", "hike.add", "hike.add"]))
        draft, _ = self.propose(self.TEXT)
        self.assertEqual(len(json.loads(draft["ops_json"])), 3)
        self.nothing_written()
        self.assertEqual(self.say(f"yes {draft['code']}"), "approved")
        self.assertEqual(self.commits(), 1)

    def test_third_pick_does_not_hide_runner_up_label(self):
        self.ask_for(["stock.set", "hike.add"])

    def test_unrelated_single_pick_offers_both_leaders(self):
        self.script(self.TEXT, self.calls["stock.set"])
        self.assertEqual(self.say(self.TEXT), "question")
        self.assertEqual(self.replies(), [self.QUESTION])
        self.assertEqual(self.live()["ask"]["agree"], ["hike.add", "item.describe"])
        self.assertEqual(self.drafts(), [])
        self.nothing_written()

    def test_multicall_tie_boundary_and_owner_choice(self):
        self.router.ranking[1] = ("item.describe", 9.0)
        self.ask_for(["hike.add", "hike.add"])
        self.conv = self.open()  # offered names survive reopening the Conversation
        self.script("the hikes please", self.call_reply(["hike.add", "hike.add"]))
        draft, _ = self.propose("the hikes please")
        self.assertEqual(len(json.loads(draft["ops_json"])), 2)
        self.nothing_written()

    def test_just_outside_tie_proceeds(self):
        self.router.ranking[1] = ("item.describe", 8.99)
        self.script(self.TEXT, self.call_reply(["hike.add", "hike.add"]))
        draft, _ = self.propose(self.TEXT)
        self.assertEqual(len(json.loads(draft["ops_json"])), 2)
        self.nothing_written()

    def test_duplicate_message_does_not_count_as_owner_choice(self):
        self.ask_for(["hike.add", "hike.add"], pid="tie-message")
        before = self.live()
        self.assertEqual(self.say(self.TEXT, pid="tie-message"), "duplicate")
        self.assertEqual(self.replies(), [])
        self.assertEqual(self.live(), before)
        self.assertEqual(self.drafts(), [])
        self.nothing_written()

    def test_cancelled_or_expired_choice_does_not_settle_a_new_tie(self):
        self.ask_for(["hike.add", "hike.add"])
        self.assertEqual(self.say("no"), "no-target")
        self.replies()
        self.assertIsNone(self.live())
        self.ask_for(["hike.add", "hike.add"])
        self.now += timedelta(minutes=dispatch.openreq.TTL_MINUTES, seconds=1)
        self.ask_for(["hike.add", "hike.add"])

    def test_stale_offered_names_do_not_authorize_an_unoffered_pick(self):
        self.ask_for(["hike.add", "hike.add"])
        self.ask_for(["stock.set", "hike.add"])


class RouterContractTests(SkillCase):
    """The routing agreement (spec 2.5) uses the FW-2 router contract: candidates(text, hints, open_request, attachment, skills)."""

    def fake_router(self, found):
        import sys
        import types
        seen = []
        mod = types.ModuleType("hass.skills.router")

        def candidates(text, hints=None, open_request=None, attachment=None, skills=()):
            seen.append({"hints": hints, "skills": skills})
            return found if skills else []
        mod.candidates = candidates
        old = sys.modules.get("hass.skills.router")
        sys.modules["hass.skills.router"] = mod
        self.addCleanup(lambda: sys.modules.pop("hass.skills.router", None) if old is None else sys.modules.__setitem__("hass.skills.router", old))
        return seen

    def test_the_registry_is_passed_and_a_near_tie_asks_which_task(self):
        seen = self.fake_router([("item.describe", 4.0), ("hike.add", 3.8)])
        self.script(OPEN1, skill_reply("hike.add", **MILL))
        self.assertEqual(self.say(OPEN1), "question")
        self.assertIs(seen[0]["skills"], self.registry)
        self.assertIsInstance(seen[0]["hints"], dict)
        self.assertEqual(self.replies(), ["Do you want to add a hike, or change an item's description?"])
        self.nothing_written()

    def test_a_near_tie_asks_even_when_the_model_picked_the_leader(self):
        self.fake_router([("hike.add", 4.0), ("item.describe", 3.8)])
        self.script(OPEN1, skill_reply("hike.add", **MILL))
        self.assertEqual(self.say(OPEN1), "question")
        self.assertEqual(self.replies(), ["Do you want to add a hike, or change an item's description?"])
        self.nothing_written()

    def test_the_ten_percent_boundary_for_the_leading_pair(self):
        self.fake_router([("hike.add", 4.4), ("item.describe", 4.0)])  # exactly 10%: tied
        self.script(OPEN1, skill_reply("hike.add", **MILL))
        self.assertEqual(self.say(OPEN1), "question")

    def test_a_lead_over_ten_percent_goes_on_to_the_draft(self):
        self.fake_router([("hike.add", 4.6), ("item.describe", 4.0)])
        self.script(LIVE1, skill_reply("hike.add", **MILL))
        draft, _ = self.propose(LIVE1)
        self.assertEqual(draft["state"], "proposed")

    def test_a_clear_agreement_goes_on_to_the_draft(self):
        self.fake_router([("hike.add", 5.0), ("item.describe", 1.0)])
        self.script(LIVE1, skill_reply("hike.add", **MILL))
        draft, _ = self.propose(LIVE1)
        self.assertEqual(draft["state"], "proposed")

class ShelfCheckQueueTests(SkillCase):
    """RETURN (round 2) item 1: calls waiting behind a change that needs today's shelf check are not lost by the check."""
    SKILLS = (HIKE_ADD, DESCRIBE, STOCK)
    TEXT = "mark the avocados out, then add the Mill hike and the Pine hike on Saturday"

    def hikes(self):
        return [{"skill": "hike.add", "slots": {"title": f"{n} hike", "place": n, "day": SATURDAY}} for n in ("Mill", "Pine")]

    def test_complete_call_needing_the_shelf_check_keeps_the_incomplete_calls_waiting(self):
        self.script(self.TEXT, {"calls": [{"skill": "stock.set", "slots": {"level": "no"}}, *self.hikes()], "revises": None})
        self.assertEqual(self.say(self.TEXT), "question")
        self.assertEqual(self.replies(), [conversation.SHELF_QUESTION])
        self.assertEqual(len(self.live()["calls"]), 2)
        self.conv = self.open()  # a restart in between
        self.assertEqual(len(self.live()["calls"]), 2)
        self.now += timedelta(minutes=1)
        self.assertEqual(self.say("yes"), "proposed")
        replies = self.replies()
        self.assertEqual(len(replies), 2, replies)
        self.assertEqual(replies[1], "What time does it start?")
        self.assertEqual((self.live()["skill"], len(self.live()["calls"])), ("hike.add", 1))
        self.now += timedelta(minutes=1)
        self.assertEqual(self.say("8am"), "proposed")
        self.assertEqual(self.replies()[-1], "What time does it start?")
        self.assertEqual((self.live()["slots"]["title"], self.live()["calls"]), ("Pine hike", []))

    def test_a_no_to_the_shelf_check_still_goes_on_to_the_next_call(self):
        self.script(self.TEXT, {"calls": [{"skill": "stock.set", "slots": {"level": "no"}}, *self.hikes()], "revises": None})
        self.say(self.TEXT)
        self.replies()
        self.now += timedelta(minutes=1)
        self.assertEqual(self.say("no"), "shelf-no")
        self.assertEqual(self.replies()[-1], "What time does it start?")
        self.assertEqual((self.live()["slots"]["title"], len(self.live()["calls"])), ("Mill hike", 1))

    def test_a_queued_call_behind_an_answered_incomplete_call_keeps_waiting_through_the_shelf_check(self):
        calls = [{"skill": "hike.add", "slots": {"title": "Mill hike", "place": "Mill", "day": SATURDAY}},
                 {"skill": "stock.set", "slots": {}}, self.hikes()[1]]
        text = "add the Mill hike, mark the avocados, add the Pine hike"
        self.script(text, {"calls": calls, "revises": None})
        self.say(text)
        self.replies()
        self.assertEqual(self.say("8am"), "proposed")
        self.assertEqual(self.replies()[-1], "Is it in stock, limited or out?")
        self.script("out", skill_reply("stock.set", level="no"))
        self.assertEqual(self.say("out"), "question")  # the shelf check is asked, the Pine hike waits on it
        self.assertEqual(self.replies(), [conversation.SHELF_QUESTION])
        self.assertEqual(len(self.live()["calls"]), 1)
        self.assertEqual(self.say("yes"), "proposed")
        self.assertEqual(self.replies()[-1], "What time does it start?")
        self.assertEqual(self.live()["slots"]["title"], "Pine hike")


class RetainedFactTests(SkillCase):
    """RETURN (round 2) item 2: a stored owner-word fact the owner later denies is dropped, even when the new reply omits it."""

    def test_an_earlier_easy_is_dropped_when_a_later_message_says_not_easy_and_only_the_time_arrives(self):
        self.script(OPEN1, skill_reply("hike.add", title="Mill Creek hike", place="Mill Creek trailhead", day=SATURDAY, difficulty="easy"))
        self.assertEqual(self.say(OPEN1), "question")
        self.assertEqual(self.live()["slots"]["difficulty"], "easy")
        text = "it is not easy; start at 8am"
        self.script(text, skill_reply("hike.add", time="08:00"))  # the model repeats nothing but the time
        self.now += timedelta(minutes=1)
        self.assertEqual(self.say(text), "proposed")
        reply = self.replies()[-1]
        self.assertNotIn("difficulty", json.loads(self.drafts()[-1]["ops_json"])[0]["args"])
        self.assertIn("Left off (you didn't say it): difficulty.", reply)

    def test_a_null_difficulty_in_the_completing_reply_does_not_keep_the_denied_easy(self):
        self.script(OPEN1, skill_reply("hike.add", title="Mill Creek hike", place="Mill Creek trailhead", day=SATURDAY, difficulty="easy"))
        self.assertEqual(self.say(OPEN1), "question")
        text = "it is not easy, we set off at eight sharp"
        self.script(text, skill_reply("hike.add", time="08:00", difficulty=None))
        self.now += timedelta(minutes=1)
        self.assertEqual(self.say(text), "proposed")
        self.assertNotIn("difficulty", json.loads(self.drafts()[-1]["ops_json"])[0]["args"])

    def test_an_earlier_denied_required_place_is_asked_again(self):
        self.script(OPEN1, skill_reply("hike.add", title="Mill Creek hike", place="Mill Creek trailhead", day=SATURDAY))
        self.say(OPEN1)
        text = "not at Mill Creek trailhead after all; start at 8am"
        self.script(text, skill_reply("hike.add", time="08:00"))
        self.now += timedelta(minutes=1)
        self.assertEqual(self.say(text), "question")
        self.assertEqual(self.replies()[-1], "Where should we meet?")
        self.assertNotIn("place", self.live()["slots"])

    def test_the_dropping_is_checked_on_the_cheap_answer_path_too(self):
        slots = dict(title="Mill hike", place="Mill", day=SATURDAY, difficulty="easy")
        self.script("add Mill easy", skill_reply("hike.add", **slots))
        self.say("add Mill easy")
        self.assertEqual(self.live()["asked_slot"], "time")
        self.conv.requests.put(CHAT, "x", self.now, texts=["add Mill easy", "it is not easy"], request_id=self.live()["request_id"],
                               skill="hike.add", slots=slots, asked_slot="time", question="What time does it start?")
        self.now += timedelta(minutes=1)
        self.assertEqual(self.say("8am"), "proposed")
        self.assertNotIn("difficulty", json.loads(self.drafts()[-1]["ops_json"])[0]["args"])


if __name__ == "__main__":
    unittest.main()


class TwoOwnerSkillTests(SkillCase):
    """HASS-LIVE-PLAN-1: with gIsOwner, each owner has their own open request in skills mode."""
    G, GCHAT = "g@example.invalid", "chat-fixture-g"

    def setUp(self):
        super().setUp()
        self.conv.db.close()
        self.set_settings({**SETTINGS, "skills": {"mode": "both"}, "gSenders": [self.G], "gChat": self.GCHAT, "gIsOwner": True})
        self.conv = self.open()
        self.addCleanup(lambda: self.conv.db.close())

    def test_independent_questions_and_short_answers_stay_with_their_own_owner(self):
        mike_open = OPEN1
        g_open = "add a hike Sunday, Mill Creek trailhead, easy"
        self.script(mike_open, skill_reply("hike.add", **{k: v for k, v in MILL.items() if k != "time"}))
        self.script(g_open, skill_reply("hike.add", **{**{k: v for k, v in MILL.items() if k != "time"}, "title": "G hike", "day": "2026-11-08"}))
        self.assertEqual(self.say(mike_open), "question")
        self.assertEqual(self.say(g_open, chat=self.GCHAT, sender=self.G), "question")
        self.assertEqual(self.conv.requests.get(CHAT, self.now)["texts"], [mike_open])  # G's question did not overwrite Mike's
        self.assertEqual(self.conv.requests.get(self.GCHAT, self.now)["texts"], [g_open])
        self.now += timedelta(minutes=1)
        self.say("9am", chat=self.GCHAT, sender=self.G)  # G's short answer fills G's request only
        mike = self.conv.requests.get(CHAT, self.now)
        self.assertEqual((mike["skill"], mike["asked_slot"]), ("hike.add", "time"))
        drafts = [d for d in self.drafts()]
        self.assertEqual([d["chat"] for d in drafts], [self.GCHAT])
        self.assertEqual(json.loads(drafts[0]["ops_json"])[0]["args"]["time"], "09:00")
        self.say("8am")  # Mike's short answer then drafts Mike's own
        self.assertEqual(sorted(d["chat"] for d in self.drafts()), sorted([CHAT, self.GCHAT]))
        self.assertEqual(self.commits(), 0)
