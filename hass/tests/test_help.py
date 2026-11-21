"""AV1537-03, AV1052-12 (H17/H25): `help` replies HELP_TEXT, a short grouped index of every owner command, and `help <command>`
that command's full lines; both kept in step with the parsers. The verb set is test_commands_doc.parser_verbs() (imported, never copied). Run: python3 -B -m unittest hass.tests.test_help
"""

import re
import unittest
from datetime import timedelta

from hass import capabilities, conversation, voice
from hass.chat import commands
from hass.tests.test_commands_doc import parser_verbs, verb
from hass.tests.test_conversation import GROUP, STRANGER, T0, ConversationTestCase, _ops
from hass.tests.test_editor import HOURS, NEW_HOURS

CAPABILITY = ("what can you do", "what do you do", "what can I say")
MODES = ("ops-only", "both", "skills-first")
LINES = voice.plain(conversation.HELP_TEXT).splitlines()
ENTRIES = commands.HELP_ENTRIES


def examples(entries=ENTRIES):
    """(entry name, example) for every marked example in every entry's lines."""
    return [(e[0], ex) for e in entries for ln in e[3] for ex in re.findall("\ue000(.*?)\ue001", ln)]


def coverage_problems(entries, verbs):
    """What is wrong between the help entries and the parsers' verbs; computed from the parsers, not from the entries."""
    out = [f"example does not parse as {n}'s own command: {ex}" for n, ex in examples(entries) if verb(ex) is None]
    got = {n: {verb(ex) for m, ex in examples(entries) if m == n} for n in {e[0] for e in entries}}
    for v in sorted(verbs):
        owners = [n for n, vs in got.items() if v in vs]
        if len(owners) != 1: out.append(f"parser verb {v} has {len(owners)} entries")
    out += [f"entry {n} has no parser verb" for n, vs in got.items() if not vs - {None}]
    return out


def index_names(lines):
    """{group: [names]} read back from the grouped index lines (continuation lines start with two spaces)."""
    out, group = {}, None
    for line in lines:
        if line.startswith("  ") and group: out[group] += [n.strip() for n in line.split(",") if n.strip()]
        elif re.match(r"(Drafts|Look up|Notes|Control):", line):
            group, rest = line.split(":", 1)
            out[group] = [n.strip() for n in rest.split(",") if n.strip()]
    return out


class HelpTextTests(unittest.TestCase):
    def test_grouped_index_complete_unique_and_phone_width(self):
        self.assertLessEqual(len(LINES), 14)
        for line in LINES:
            self.assertLessEqual(len(line), 70, line)
            self.assertFalse(set(line) & set("*_`#"), line)  # plain text, no markdown
        names = index_names(LINES)
        self.assertEqual(list(names), ["Drafts", "Look up", "Notes", "Control"])
        flat = [n for group in names.values() for n in group]
        self.assertEqual(sorted(flat), sorted(e[0] for e in ENTRIES))  # every entry once, no extra name
        self.assertEqual(LINES[-1], "Send help <command> for an example: help undo")
        self.assertIsNone(verb(re.search(r'"([^"]+)"', LINES[0])[1]))  # the plain-words example is a change
        self.assertIn('"Stop showing the eggs as sold out"', LINES[0])  # AV1622-05

    def test_every_parser_verb_has_one_entry_and_every_example_parses_back(self):
        self.assertEqual(coverage_problems(ENTRIES, parser_verbs()), [])
        self.assertEqual({verb(ex) for _, ex in examples()}, parser_verbs())  # incl. alias and help; no extra verb
        self.assertEqual(len(commands.HELP_WORDS), sum(1 + len(e[2]) for e in ENTRIES))  # a word reaches one entry only
        for name, word in ((e[0], w) for e in ENTRIES for w in e[2]):
            self.assertEqual(conversation.parse_command(f"help {word}"), ("help", word))
            self.assertEqual(commands.HELP_WORDS[word], name)

    def test_missing_entry_or_bad_example_fails(self):
        self.assertIn("parser verb undo has 0 entries", coverage_problems([e for e in ENTRIES if e[0] != "undo"], parser_verbs()))
        self.assertIn("parser verb pause has 0 entries", coverage_problems([e for e in ENTRIES if e[0] != "stop changes"], parser_verbs()))
        self.assertIn("parser verb photos has 0 entries", coverage_problems([e for e in ENTRIES if e[0] != "photos to take"], parser_verbs()))
        bad = ENTRIES + (("again2", "Drafts", (), (commands.q("please undo it all") + " - x",)),)
        self.assertIn("example does not parse as again2's own command: please undo it all", coverage_problems(bad, parser_verbs()))
        self.assertIn("parser verb undo has 2 entries", coverage_problems(ENTRIES + (("undo2", "Drafts", (), (commands.q("undo") + " - x",)),), parser_verbs()))

    def test_detail_lines_are_complete_and_short(self):
        for e in ENTRIES:
            for word in (e[0], *e[2]):
                detail = commands.help_detail(word)
                self.assertEqual(detail, "\n".join(e[3]), word)
                for line in voice.plain(detail).splitlines(): self.assertLessEqual(len(line), 70, line)
        self.assertEqual(voice.plain(commands.help_detail("undo")), 'undo - take back the last change\nundo a1b2 - take back that one')
        unknown = voice.plain(commands.help_detail("a1b2")).splitlines()
        self.assertEqual(unknown[0], "Unknown command. Send help with one of:")
        self.assertEqual(unknown[1:], LINES[1:-1])  # the same wrapped grouped names
        self.assertNotIn("a1b2", "\n".join(unknown))

    def test_one_post_line_names_product_and_maker(self):
        """AV1937-10: the post entry names a product and a maker; nothing is posted; no <id> placeholder; its examples parse as post."""
        lines = voice.plain(commands.help_detail("post")).splitlines()
        self.assertEqual(lines, ["post Hass avocado - a caption to copy for a product", "post maker fixture-farm - a caption to copy for a maker",
                                 "post notice - a caption for the home page notice",  # AV1104-07
                                 "post today - a caption for what you checked today"])  # AV1104-08
        self.assertEqual([verb(ex) for w, ex in examples() if w == "post"], ["post", "post", "post", "post"])
        self.assertEqual(conversation.parse_command("post maker fixture-farm"), ("post", "maker fixture-farm"))

    def test_help_wordings_parse_and_lookalikes_do_not(self):
        for text in ("help", "Help!", "commands.", "?", " HELP ", "Commands!"):
            self.assertEqual(conversation.parse_command(text), ("help", None), text)
        for text in ("help undo", "HELP Undo!", "  help undo ", "help undo."):
            self.assertEqual(conversation.parse_command(text), ("help", "undo"), text)
        self.assertEqual(conversation.parse_command("help a1b2"), ("help", "a1b2"))  # an unknown name is still help
        self.assertEqual(conversation.parse_command("Help Photos To Take"), ("help", "photos to take"))
        self.assertEqual(conversation.read_command("help undo?"), ("help", "undo"))
        for text in ("help me with avocados", "??", "what?", "command", "help undo it now please", "help photos to"):
            self.assertIsNone(verb(text), text)
        self.assertEqual(conversation.read_command("help?"), ("help", None))  # AV1352-05: a read-only command

    def test_capability_phrases_parse_as_help_without_capture_group_drift(self):
        for text in CAPABILITY:
            for variant in (text, text.upper(), f"  {text}  ", text + "!", text + ".", text + "?"):
                if variant.endswith("?") and variant.count("?") > 1: continue
                with self.subTest(text=variant):
                    self.assertEqual(conversation.parse_command(variant), ("help", None))
        self.assertEqual(commands.COMMAND_RE.groups, 27)  # no capture group added (AV1052-05: shelf is groups 24/25; AV2137-06: costs is 26; AV2137-07: held is 27)
        self.assertEqual(conversation.parse_command("history eggs"), ("history", "eggs"))
        self.assertEqual(conversation.parse_command("show a1b2"), ("show", "a1b2"))
        self.assertEqual(conversation.parse_command("post eggs"), ("post", "eggs"))
        self.assertEqual(conversation.parse_command("status"), ("status", None))

    def test_capability_help_is_whole_message_only(self):
        for text in ("what can you do about eggs", "what do you do with this", "what can I say about the shop",
                     "please what can you do", "what can you do??", "what can you do now"):
            with self.subTest(text=text):
                self.assertIsNone(verb(text))


class HelpConversationTests(ConversationTestCase):
    def state(self):
        db = self.conv.db
        has_control = db.execute("SELECT 1 FROM sqlite_master WHERE name = 'control'").fetchone()
        return (self.drafts(), db.execute("SELECT * FROM approvals").fetchall(), self.commits(), self.editor.applies,
                db.execute("SELECT * FROM control").fetchall() if has_control else [])

    def test_help_replies_the_list_and_changes_nothing(self):
        for text in ("help", "Help!", "commands.", "?"):
            with self.subTest(text=text):
                self.assertEqual(self.say(text), "help")
                self.assertEqual(self.replies(), [voice.plain(conversation.HELP_TEXT + "\n\n" + capabilities.help_section())])
        self.assertEqual((self.say("help", pid="m1"), self.replies()), ("duplicate", []))  # a resent help: no reply
        self.assertEqual(self.state(), ([], [], 0, 0, []))

    def test_help_detail_replies_only_that_command_and_changes_nothing(self):
        def boom(*a, **k): raise AssertionError("the interpreter was called")
        self.interp.interpret = boom
        for text, word in (("help undo", "undo"), ("Help YES!", "yes"), ("help remember", "remember"), ("help stop changes", "stop changes"),
                           ("help no", "no"), ("help undo?", "undo")):
            with self.subTest(text=text):
                self.assertEqual(self.say(text), "help")
                self.assertEqual(self.replies(), [voice.plain(commands.help_detail(word))])
        self.assertEqual(self.say("help undo", pid="dup-help-1"), "help")
        self.replies()
        self.assertEqual((self.say("help undo", pid="dup-help-1"), self.replies()), ("duplicate", []))
        self.assertEqual(self.state(), ([], [], 0, 0, []))

    def test_unknown_help_name_lists_the_names_without_echo(self):
        self.assertEqual(self.say("help a1b2"), "help")
        [reply] = self.replies()
        self.assertEqual(reply, voice.plain(commands.help_detail("a1b2")))
        self.assertTrue(reply.startswith("Unknown command. Send help with one of:\nDrafts: yes, no"))
        self.assertNotIn("a1b2", reply)
        self.assertEqual(self.state(), ([], [], 0, 0, []))

    def test_help_detail_while_paused_lapsed_and_never_approves(self):
        draft, _reply = self.propose("hours")
        self.assertEqual(self.say("pause changes"), "pause")
        self.replies()
        self.now = T0 + timedelta(seconds=601)  # lapsed; no other message has swept it yet
        before = self.state()
        for text in ("help yes", "help undo", "help stop changes", "help nonsense"):
            self.assertEqual(self.say(text), "help")
            self.assertEqual(len(self.replies()), 1)
        self.assertEqual(self.state(), before)
        self.assertEqual((self.drafts()[0]["state"], self.editor.applies), ("proposed", 0))
        self.assertEqual(self.say(f"yes {draft['code']}"), "no-target")  # a later message still expires it
        self.assertEqual(self.drafts()[0]["state"], "expired")

    def test_stranger_group_and_sentence_help_detail(self):
        self.assertEqual(self.say("help undo", sender=STRANGER), "ignored")
        self.assertEqual(self.say("help undo", chat=GROUP), "ignored")
        self.assertEqual(self.replies(), [])
        self.interp.mapping["help me with undo"] = _ops((HOURS, {"hours": NEW_HOURS}))
        self.assertEqual(self.say("help me with undo"), "proposed")  # a sentence still goes to the interpreter

    def test_help_uses_the_injected_registry_not_a_copied_inventory(self):
        from dataclasses import replace
        from types import SimpleNamespace
        from hass.skills import load_skills
        from hass.skills.model import Registry
        skill = replace(load_skills().skills['item.hide'], label='hide something special')
        self.conv.dispatch = SimpleNamespace(registry=Registry({skill.name: skill}))
        before = self.state()
        self.assertEqual(self.say('help'), 'help')
        [reply] = self.replies()
        self.assertIn('hide something special - ', reply)
        self.assertNotIn('bring a hidden product back - ', reply)
        self.assertEqual(self.state(), before)

    def test_help_sentence_goes_to_the_interpreter(self):
        self.interp.mapping["help me with avocados"] = _ops((HOURS, {"hours": NEW_HOURS}))
        self.assertEqual(self.say("help me with avocados"), "proposed")
        self.assertNotEqual(self.replies(), [voice.plain(conversation.HELP_TEXT + "\n\n" + capabilities.help_section())])

    def test_help_does_not_expire_a_lapsed_proposal(self):
        draft, _reply = self.propose("hours")
        self.now = T0 + timedelta(seconds=601)  # lapsed; no other message has swept it yet
        before = self.state()
        self.assertEqual(self.say("help"), "help")
        self.assertEqual((self.replies(), self.state()), ([voice.plain(conversation.HELP_TEXT + "\n\n" + capabilities.help_section())], before))
        self.assertEqual(self.drafts()[0]["state"], "proposed")
        self.assertEqual(self.say(f"yes {draft['code']}"), "no-target")  # a later message still expires it
        self.assertEqual(self.drafts()[0]["state"], "expired")

    def test_help_while_paused_writes_no_approval_or_control_row(self):
        draft, _reply = self.propose("hours")
        self.assertEqual(self.say("pause changes"), "pause")
        self.replies()
        before = self.state()
        self.assertEqual(self.say("Help!"), "help")
        self.assertEqual((self.replies(), self.state()), ([voice.plain(conversation.HELP_TEXT + "\n\n" + capabilities.help_section())], before))
        self.assertEqual((self.drafts()[0]["state"], self.editor.applies), ("proposed", 0))

    def test_stranger_or_group_help_is_ignored_without_a_reply(self):
        self.assertEqual(self.say("help", sender=STRANGER), "ignored")
        self.assertEqual(self.say("help", chat=GROUP), "ignored")
        self.assertEqual(self.replies(), [])


def conversation_settings(case):
    import json
    return json.loads((case.repo.state / "config.json").read_text("utf-8"))["settings"]


class CapabilityHelpTests(ConversationTestCase):
    state = HelpConversationTests.state

    def mode(self, mode):
        self.set_settings({**conversation_settings(self), "skillsMode": mode})
        self.conv = self.open()

    def test_capability_questions_reply_help_in_every_mode_without_model(self):
        def boom(*a, **k): raise AssertionError("the interpreter was called")
        self.interp.interpret = boom
        for mode in MODES:
            self.mode(mode)
            for text in CAPABILITY + ("what can you do?",):
                with self.subTest(mode=mode, text=text):
                    self.assertEqual(self.say(text), "help")
                    self.assertEqual(self.replies(), [voice.plain(conversation.HELP_TEXT + "\n\n" + capabilities.help_section())])

    def test_capability_help_keeps_paused_lapsed_and_open_request_state(self):
        draft, _reply = self.propose("hours")
        self.assertEqual(self.say("pause changes"), "pause")
        self.replies()
        self.now = T0 + timedelta(seconds=601)
        before = self.state()
        for text in CAPABILITY:
            self.assertEqual(self.say(text), "help")
            self.assertEqual((len(self.replies()), self.state()), (1, before))
        self.assertEqual((self.drafts()[0]["state"], self.editor.applies), ("proposed", 0))

    def test_capability_help_duplicate_and_foreign_chat(self):
        self.assertEqual(self.say("what can you do?", pid="c1"), "help")
        self.replies()
        self.assertEqual((self.say("what can you do?", pid="c1"), self.replies()), ("duplicate", []))
        self.assertEqual(self.say("what can you do", sender=STRANGER), "ignored")
        self.assertEqual(self.say("what can you do", chat=GROUP), "ignored")
        self.assertEqual(self.replies(), [])
