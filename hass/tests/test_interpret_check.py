"""NB-AV-01 tests: interpreter output checked against the ops registry before the editor sees it.

The pure check runs against the production registry; the conversation tests reuse the H05 fixture conversation
(ConversationTestCase) with the production registry or the test-only fixture ops.
Run: python3 -m unittest hass.tests.test_interpret_check -v
"""

import unittest

from hass import conversation, interpret_check
from hass.ops import load_registry
from hass.skills.acceptance_run import RecordedInterpreter
from hass.tests.test_conversation import ConversationTestCase, _ops
from hass.tests.test_editor import HOURS, _req

REGISTRY = load_registry()
AGAIN = interpret_check.AGAIN


def ask(ops, revises=None, pending=()):
    return interpret_check.check({"ops": ops, "revises": revises}, REGISTRY, pending)


def call(op, **args):
    return {"op": op, "args": args}


def recorded_listing_ops():
    return [call("product.edit", id="photo-product-001", name="Hass")]


class CheckTests(unittest.TestCase):
    def assertAsks(self, out, *parts):
        self.assertEqual(set(out), {"question"}, out)
        for part in parts: self.assertIn(part, out["question"])

    def test_valid_result_is_returned_unchanged(self):
        result = {"ops": [call("hike.update", id="h1", capacity=10, rsvpEnabled=True)], "revises": "beef"}
        self.assertIs(interpret_check.check(result, REGISTRY, {"beef"}), result)
        for passthrough in ({"question": "Which day?"}, {"unsupported": "Sorry."}):
            self.assertIs(interpret_check.check(passthrough, REGISTRY, ()), passthrough)

    def test_recorded_listing_edit_with_null_revises_passes_unchanged(self):
        saved = {"ops": recorded_listing_ops(), "revises": None}
        reply = RecordedInterpreter([saved]).interpret("Rename the listing", [])
        self.assertIs(interpret_check.check(reply, REGISTRY, ()), reply)
        self.assertEqual(reply, saved)

    def test_malformed_recorded_edit_envelope_asks_without_details(self):
        # Saved replies can bypass upstream shape validation; assuming a list or
        # indexing missing revises would raise instead of asking one question.
        ops = recorded_listing_ops()
        for name, saved in (
            ("missing revises", {"ops": ops}),
            ("non-list ops", {"ops": 7, "revises": None}),
            ("non-string revises", {"ops": ops, "revises": ["fixture detail"]}),
        ):
            with self.subTest(name=name):
                reply = RecordedInterpreter([saved]).interpret("Rename the listing", [])
                self.assertEqual(interpret_check.check(reply, REGISTRY, ()),
                                 {"question": "I couldn't read part of that message. Could you say it another way?"})

    def test_unknown_op_and_unknown_argument_are_named(self):
        self.assertEqual(ask([call("product.colour", id="p1")]), {"question": (
            "I can't do that kind of change from chat yet, so nothing changed. Say help to see what I can change.")})
        self.assertAsks(ask([call("product.edit", id="p1", colour="green")]), "I can't do that kind of change from chat yet")
        # a later call is checked too: the first problem wins, in call order
        self.assertAsks(ask([call("product.edit", id="p1"), call("hike.nope")]), "I can't do that kind of change from chat yet")

    def test_wrong_kind_names_the_field(self):
        cases = [(call("hike.update", id="h1", capacity="ten"), "I need the guest limit as a whole number"),
                 (call("hike.update", id="h1", capacity=True), "I need the guest limit as a whole number"),
                 (call("hike.update", id="h1", capacity=2.5), "I need the guest limit as a whole number"),
                 (call("hike.update", id="h1", rsvpEnabled="yes"), "I need whether guests can sign up as yes or no"),
                 (call("hike.update", id="h1", rsvpEnabled=1), "I need whether guests can sign up as yes or no"),
                 (call("store.set_hours", hours="9-5 daily"), "I need the opening hours as a list of words"),
                 (call("store.set_hours", hours=["9-5", 7]), "I need the opening hours as a list of words"),
                 (call("product.edit", id=7), "I need a detail as words"),
                 (call("product.edit", id="p1", producerKey=None), "I need the maker as words")]
        for bad, text in cases:
            with self.subTest(bad=bad):
                self.assertEqual(ask([bad]), {"question": f"{text}. {AGAIN}"})
        self.assertIsNot(ask([call("hike.update", id="h1", capacity=0, rsvpEnabled=False)]).get("ops"), None)

    def test_revises_must_name_a_waiting_draft(self):
        ops = [call("store.set_hours", hours=["9-5"])]
        self.assertEqual(ask(ops, "beef"), {"question": "I can't find that change any more. Could you tell me the change again?"})
        self.assertAsks(ask(ops, "beef", {"cafe", "beefcafe"}), "I can't find that change any more")
        self.assertIn("ops", ask(ops, "beef", {"beef"}))
        self.assertIn("ops", ask(ops, None, ()))

    def test_empty_ops_and_bad_call_shapes(self):
        self.assertEqual(ask([]), {"question": "I couldn't find a change in that message. What would you like to change?"})
        for bad in ({"op": "product.edit", "args": {"id": "p1"}, "why": "owner asked"}, {"op": "product.edit"},
                    {"op": 3, "args": {}}, {"op": "product.edit", "args": ["id"]}, "product.edit", None):
            with self.subTest(bad=bad):
                self.assertEqual(ask([call("product.edit", id="p1"), bad]),
                                 {"question": f"I couldn't read part of that message. {AGAIN}"})

    def test_long_name_with_control_characters_is_cut_and_cleaned(self):
        name = "x" * 250 + "\n\r\t\x1b\x7f\x85" + "y" * 244
        for out in (ask([call(name)]), ask([call("product.edit", **{name: "v"})]),
                    ask([call("store.set_hours", hours=["ok"])], revises=name)):
            text = out["question"]
            self.assertLessEqual(len(text), 200, text)
            self.assertFalse(any(ord(c) < 32 or 127 <= ord(c) < 160 for c in text), repr(text))
            self.assertEqual(interpret_check._clean(name), "x" * 37 + "...")
            self.assertNotIn(name, text)


class ProductionConversationTests(ConversationTestCase):
    """The production registry (editor registry None), as the live conversation runs."""

    def setUp(self):
        super().setUp()
        self.editor = conversation.Editor(self.repo.state)
        self.conv = self.open()

    def asked(self, text, mapping):
        self.interp.mapping[text] = mapping
        self.assertEqual(self.say(text), "question")
        [reply] = self.replies()
        disposition = self.conv.db.execute("SELECT disposition FROM messages WHERE provider_id = ?",
                                           (f"m{self.n}",)).fetchone()[0]
        self.assertEqual(disposition, "question")
        self.assertEqual((self.drafts(), sorted((self.repo.state / "drafts").glob("*.json"))), ([], []))
        return reply

    def test_registry_problems_ask_before_any_draft(self):
        self.assertIn("I can't do that kind of change from chat yet", self.asked("colour", _ops(("product.colour", {"id": "photo-product-001"}))))
        self.assertIn("I can't do that kind of change from chat yet", self.asked("edit", _ops(("product.edit", {"id": "photo-product-001",
                                                                                         "colour": "green"}))))
        self.assertIn("I need the guest limit as a whole number",
                      self.asked("cap", _ops(("hike.update", {"id": "h1", "capacity": "ten"}))))
        self.assertIn("I couldn't find a change", self.asked("empty", {"ops": [], "revises": None}))
        self.assertIn("I can't find that change any more", self.asked("rev", {**_ops(("product.edit", {"id": "photo-product-001",
                                                                                        "name": "Hass"})),
                                                               "revises": "beef"}))
        self.assertEqual(self.commits(), 0)

    def test_value_problems_still_reach_the_editor(self):
        self.interp.mapping["maker"] = _ops(("product.edit", {"id": "photo-product-001", "producerKey": "no-such-maker"}))
        self.assertEqual(self.say("maker"), "not-drafted")
        [reply] = self.replies()
        self.assertTrue(reply.startswith("I couldn't make that change, so nothing changed."), reply)
        self.assertIn("Could you say it another way?", reply)


class FixtureConversationTests(ConversationTestCase):
    def test_waiting_needs_details_code_still_fills(self):
        self.interp.mapping["start"] = {"ops": _req((HOURS, {}))["ops"], "revises": None}
        self.assertEqual(self.say("start"), "needs-details")
        self.replies()
        [pending] = self.drafts()
        self.interp.mapping["stale"] = {**_ops((HOURS, {"hours": ["Daily 8am–7pm"]})), "revises": "beef"}
        self.assertEqual(self.say("stale"), "question")
        self.assertEqual(self.replies(), ["I can't find that change any more. Could you tell me the change again?"])
        self.interp.mapping["done"] = {**_ops((HOURS, {"hours": ["Daily 8am–7pm"]})), "revises": pending["code"]}
        self.assertEqual(self.say("done"), "proposed")
        self.replies()
        [filled] = self.drafts()
        self.assertEqual((filled["row_id"], filled["code"], filled["state"]), (pending["row_id"], pending["code"],
                                                                               "proposed"))

    def test_test_registry_is_the_one_checked(self):
        self.interp.mapping["prod"] = _ops(("product.edit", {"id": "photo-product-001", "name": "Hass"}))
        self.assertEqual(self.say("prod"), "question")
        self.assertIn("I can't do that kind of change from chat yet, so nothing changed. Say help to see what I can change.", self.replies()[0])


if __name__ == "__main__":
    unittest.main()
