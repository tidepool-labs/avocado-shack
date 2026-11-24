"""Offline checks for the owner guide against the shipped reply and command copy."""

import json
from pathlib import Path
import re
from types import SimpleNamespace
import unittest
from unittest.mock import Mock

from hass.chat.commands import help_detail, parse_command, parse_keyword, q
from hass.conversation import Conversation

ROOT = Path(__file__).resolve().parents[2]
GUIDE = ROOT / "docs/hass/NPP-OWNER-GUIDE.md"
TEMPLATES = ROOT / "hass/npp/assets/hass-npp-reply/reply-templates.json"
MARKER = re.compile(rb"<!-- hass-line: (/[^\s]+) -->")
COMMAND_QUOTES = {"/commands/help_listing", "/commands/status"}
EXAMPLE = re.compile(
    r"^Example only: card code `(?P<code>4ed1)`, first tag `(?P=code)-(?P<first>1)`, "
    r"next tag `(?P=code)-(?P<next>2)`, price `(?P<price>\$[0-9]+\.[0-9]{2})`, "
    r"item link `(?P<url>https://example\.com/\?item=[a-z0-9-]+#market)`\.$",
    re.MULTILINE,
)


class NPPOwnerGuideTests(unittest.TestCase):
    def setUp(self):
        self.raw = GUIDE.read_bytes()
        self.guide = self.raw.decode("utf-8")

    def example(self):
        examples = list(EXAMPLE.finditer(self.guide))
        self.assertEqual(len(examples), 1, "Declare one set of examples in the guide")
        return examples[0].groupdict()

    def quotes(self):
        # Keep the quote bytes as written, including any stray spaces or CRs.
        lines = self.raw.split(b"\n")
        index = 0
        while index < len(lines):
            line = lines[index]
            if b"hass-line:" in line:
                marker = MARKER.fullmatch(line)
                if marker is None:
                    self.fail(f"Bad marker at line {index + 1}")
                index += 1
                quote = []
                while index < len(lines) and lines[index].startswith(b"> "):
                    quote.append(lines[index][2:])
                    index += 1
                self.assertTrue(quote, "Put the quote directly after its marker")
                yield marker[1].decode("utf-8"), b"\n".join(quote)
                continue
            elif line.lstrip().startswith(b">"):
                self.fail(f"Unmarked quote at line {index + 1}")
            index += 1

    def command_quote(self, pointer):
        quotes = [quote for key, quote in self.quotes() if key == pointer]
        self.assertEqual(len(quotes), 1, f"Quote {pointer} exactly once")
        return quotes[0].decode("utf-8")

    def test_c1_quotes_match_templates(self):
        # C1: a changed template or a retyped quote must not silently drift.
        quotes = [(pointer, quote) for pointer, quote in self.quotes() if pointer not in COMMAND_QUOTES]
        self.assertTrue(quotes)
        templates = json.loads(TEMPLATES.read_bytes())
        example = self.example()
        versions = iter((example["first"], example["next"]))
        for pointer, quote in quotes:
            with self.subTest(pointer=pointer, quote=quote):
                template = templates
                for token in pointer[1:].split("/"):
                    template = template[token.replace("~1", "/").replace("~0", "~")]
                values = {"code": example["code"], "url": example["url"]}
                if "{n}" in template:
                    values["n"] = next(versions)
                self.assertEqual(quote, template.format(**values).encode("utf-8"))

    def test_c2_required_lines_present(self):
        # C2: dropping a key reply must fail even if all surviving quotes match.
        templates = json.loads(TEMPLATES.read_bytes())
        pointers = {pointer for pointer, _ in self.quotes()}
        self.assertLessEqual({
            "/prompts/ready", "/guards/replaced", "/guards/which_card",
            "/guards/not_ready", "/confirm/posted",
        }, pointers)
        self.assertTrue(pointers.intersection(
            f"/questions/{name}" for name in templates["questions"] if not name.startswith("ask_edit_")
        ), "Quote at least one missing-info question")

    def test_c3_phrases_accepted(self):
        # C3: check the typed examples, not a separate copy of the commands.
        # The parsers accept the canonical words as well as the phrase aliases.
        for heading, parse, verb in (
            ("Undo", parse_command, "undo"),
            ("Cancel a card", parse_keyword, "reject"),
        ):
            with self.subTest(heading=heading):
                section = self.guide.split(f"\n## {heading}\n", 1)[1].split("\n## ", 1)[0]
                phrases = re.findall(r"`([^`\n]+)`", section)
                self.assertTrue(phrases, f"No command shown under {heading}")
                for phrase in phrases:
                    self.assertEqual(parse(phrase), (verb, None), phrase)

    def test_c4_plain_and_short(self):
        # C4: catch a growing handout, stray numbers or pasted contact details.
        self.assertLessEqual(len(self.guide.splitlines()), 60)
        self.assertLessEqual(len(self.guide), 4500)
        self.assertNotIn("@", self.guide)
        example = self.example()
        code = example["code"]
        allowed = (f"{code}-{example['first']}", f"{code}-{example['next']}",
                   code, example["price"], example["url"])
        tokens = "|".join(map(re.escape, allowed))
        remaining = re.sub(rf"(?<!\w)(?:{tokens})(?!\w)", "", self.guide)
        # A phone number would leave digits too; no separate format list needed.
        self.assertFalse(any(char.isdigit() for char in remaining), "Use only the declared example numbers")

    def test_c5_help_quote(self):
        # C5: catch a missing help line or wording that no longer matches the command.
        quote = self.command_quote("/commands/help_listing")
        # Markdown hard breaks preserve the reply's lines. Inline code represents
        # the internal command marks, which Hass removes before sending.
        reply = re.sub(r"`([^`\n]+)`", lambda match: q(match[1]), quote.replace("\\\n", "\n"))
        self.assertEqual(reply, help_detail("listing"))

    def test_c6_status_quote(self):
        # C6: catch stale wording or a tag that names the wrong card version.
        example = self.example()
        jobs = Mock()
        jobs.active.return_value = {
            "state": "card_out", "job_id": example["code"], "current_version": int(example["next"]),
        }
        # Run the real status branch with only state and reply I/O stubbed.
        conv = Mock(_forwarded=None, _asker="fixture-owner")
        conv._status.return_value = "Fixture status summary."
        msg = SimpleNamespace(text="status", chat="fixture-chat")
        result = Conversation._npp_turn(conv, jobs, msg, None, parse_command(msg.text))
        self.assertEqual(result, ("status", None))
        conv._reply.assert_called_once()
        line = conv._reply.call_args.args[0].partition("\n")[0]
        self.assertEqual(self.command_quote("/commands/status"), line)
