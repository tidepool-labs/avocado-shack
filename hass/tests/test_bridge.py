"""BL-AV-3 (H08 prep) tests: BlueBubbles event -> Inbound, sealed envelope, loopback-only redacting sender.
No network (fake transport); synthetic fixtures. Run: python3 -m unittest discover -s hass/tests -t . -v"""

import copy, json, os, tempfile, unittest, uuid  # noqa: E401
from dataclasses import replace
from pathlib import Path
from unittest import mock
from urllib.parse import parse_qs, urlsplit

from hass import bridge
from hass.bridge import BridgeError, BlueBubblesSender, Drop, EnvelopeError, normalize, seal, unseal
from hass.conversation import Inbound
from hass.fixture_chat import FixtureAdapter
from hass.tests.test_conversation import OWNER, SETTINGS, STRANGER, ConversationTestCase

FIXTURES = Path(__file__).resolve().parent / "fixtures" / "bridge"
OWNER_CHAT = "iMessage;-;owner@example.invalid"
PASSWORD = "fixture-password-not-real"
KEY, NONCE, NOW = b"k" * 32, "ab" * 16, 1793638800
BASE = "http://127.0.0.1:1234"


def event(name):
    return json.loads((FIXTURES / f"{name}.json").read_text("utf-8"))


class FakeTransport:
    """Records each request; plays back statuses ("oserror" raises an OSError quoting the full URL)."""
    def __init__(self, *statuses):
        self.calls, self.statuses = [], list(statuses)

    def __call__(self, url, body, headers, timeout):
        self.calls.append({"url": url, "body": json.loads(body), "headers": headers, "timeout": timeout})
        status = self.statuses.pop(0) if self.statuses else 200
        if status == "oserror": raise OSError(f"connection refused: {url}")
        return status


def password_file(test, mode=0o600):
    folder = tempfile.TemporaryDirectory(prefix="hass-bridge-")
    test.addCleanup(folder.cleanup)
    path = Path(folder.name) / "password"
    path.write_text(PASSWORD + "\n", "utf-8")
    path.chmod(mode)
    return path


class NormalizeTests(unittest.TestCase):
    def test_owner_text_echo_and_edit(self):
        self.assertEqual(normalize(event("new-message")), Inbound(
            provider_id="FAKE-0000-0000-0000-000000000001", chat=OWNER_CHAT, sender=OWNER, text="desc",
            from_me=False, kind="new", received_at="2026-11-02T17:00:00+00:00"))
        echo = normalize(event("from-me"))
        self.assertEqual((echo.from_me, echo.sender, echo.kind), (True, OWNER, "new"))
        self.assertEqual(normalize(event("updated-message")).kind, "edited")
        stranger = normalize(event("stranger"))
        self.assertEqual((stranger.sender, stranger.from_me), (STRANGER, False))

    def test_named_drops(self):
        def variant(change):
            ev = event("new-message")
            change(ev, ev["data"])
            return ev
        cases = {
            "group chat": (event("group-chat"), "group-or-unknown-chat"),
            "two chats": (variant(lambda e, d: d["chats"].append({"guid": "iMessage;-;other@example.invalid"})),
                          "group-or-unknown-chat"),
            "no chat": (variant(lambda e, d: d.update(chats=[])), "group-or-unknown-chat"),
            "chat without guid": (variant(lambda e, d: d.update(chats=[{}])), "group-or-unknown-chat"),
            "unknown type": (variant(lambda e, d: e.update(type="typing-indicator")), "unsupported-event"),
            "missing guid": (variant(lambda e, d: d.pop("guid")), "malformed"),
            "string dateCreated": (variant(lambda e, d: d.update(dateCreated="1793638800000")), "malformed"),
            "bool dateCreated": (variant(lambda e, d: d.update(dateCreated=True)), "malformed"),
            "huge dateCreated": (variant(lambda e, d: d.update(dateCreated=10 ** 30)), "malformed"),
            "string isFromMe": (variant(lambda e, d: d.update(isFromMe="false")), "malformed"),
            "inbound without handle": (variant(lambda e, d: d.update(handle=None)), "malformed"),
            "from-me null handle": (variant(lambda e, d: d.update(isFromMe=True, handle=None)), "malformed"),
            "from-me absent handle": (variant(lambda e, d: (d.update(isFromMe=True), d.pop("handle"))), "malformed"),
            "from-me blank": (variant(lambda e, d: d.update(isFromMe=True, handle={"address": ""})), "malformed"),
            "lone surrogate text": (variant(lambda e, d: d.update(text=json.loads('"desc\\ud800"'))), "malformed"),
            "null text": (variant(lambda e, d: d.update(text=None)), "malformed"),
            "missing attachments": (variant(lambda e, d: d.pop("attachments")), "malformed"),
            "no data": (variant(lambda e, d: e.pop("data")), "malformed"),
        }
        for name, (ev, reason) in cases.items():
            with self.subTest(name):
                self.assertEqual(normalize(ev), Drop(reason))
        self.assertEqual(normalize(event("attachment")), Inbound(  # H12 part 1: no longer a drop; Conversation replies
            provider_id="FAKE-0000-0000-0000-000000000006", chat=OWNER_CHAT, sender=OWNER, text="",
            received_at="2026-11-02T17:01:00+00:00", attachments=1))
        for junk in (None, [], {"type": 1}):
            self.assertEqual(normalize(junk), Drop("malformed"))


class EnvelopeTests(unittest.TestCase):
    def setUp(self):
        self.msg = normalize(event("new-message"))
        self.env = seal(self.msg, KEY, nonce=NONCE, now=NOW)

    def refused(self, envelope, now=NOW, seen=None):
        with self.assertRaises(EnvelopeError) as ctx:
            unseal(envelope, KEY, now=now, seen=set() if seen is None else seen)
        return ctx.exception.code

    def test_round_trip_and_replay(self):
        seen = set()
        self.assertEqual(unseal(json.loads(json.dumps(self.env)), KEY, now=NOW + 300, seen=seen), self.msg)
        self.assertEqual(seen, {NONCE})
        self.assertEqual(self.refused(self.env, seen=seen), "replay")
        # Adding an internal reply reference must not change the v1 Mac body or MAC.
        with_ref = replace(self.msg, reply_to="fixture-card-guid")
        self.assertEqual(seal(with_ref, KEY, nonce=NONCE, now=NOW), self.env)
        self.assertEqual(self.refused({**self.env, "body": {**self.env["body"], "reply_to": "fixture-card-guid"}}), "shape")

    def test_tampered_stale_and_misshapen_envelopes(self):
        flipped = copy.deepcopy(self.env)
        flipped["body"]["text"] = "deSc"
        extra, missing, v2 = dict(self.env, extra=1), dict(self.env), dict(self.env, v=2)
        del missing["nonce"]
        cases = {"flipped body byte": (flipped, "mac"), "wrong key": (seal(self.msg, b"x" * 32, nonce=NONCE, now=NOW),
                                                                       "mac"),
                 "extra key": (extra, "shape"), "missing key": (missing, "shape"), "v 2": (v2, "version"),
                 "v true": (dict(self.env, v=True), "version"), "short nonce": (dict(self.env, nonce="ab"), "shape"),
                 "body field type": ({**self.env, "body": {**self.env["body"], "from_me": 0}}, "shape")}
        for name, (env, code) in cases.items():
            with self.subTest(name):
                self.assertEqual(self.refused(env), code)
        for now in (NOW + 301, NOW - 301):  # a refused envelope does not burn its nonce
            self.assertEqual((self.refused(self.env, now=now, seen=(seen := set())), seen), ("stale", set()), now)

    def test_short_key_is_refused(self):
        self.assertRaises(ValueError, seal, self.msg, b"k" * 31, nonce=NONCE, now=NOW)
        self.assertRaises(ValueError, unseal, self.env, b"k" * 31, now=NOW, seen=set())

    def test_unicode_round_trips_and_a_lone_surrogate_is_shape_not_a_crash(self):
        msg, bad, seen = replace(self.msg, text="aguacate \U0001f951 ñ"), copy.deepcopy(self.env), set()
        self.assertEqual(unseal(seal(msg, KEY, nonce=NONCE, now=NOW), KEY, now=NOW, seen=set()), msg)
        bad["body"]["text"] = json.loads('"desc\\ud800"')  # original MAC kept, as an attacker would
        self.assertEqual((self.refused(bad, seen=seen), seen), ("shape", set()))


class SenderTests(unittest.TestCase):
    def setUp(self):
        self.pw = password_file(self)

    def test_request_has_documented_path_body_and_fresh_temp_guid(self):
        fake = FakeTransport()
        sender = BlueBubblesSender(BASE, self.pw, fake)
        sender.send(OWNER_CHAT, "hello", [])
        sender.send(OWNER_CHAT, "again", ())
        first, second = fake.calls
        url = urlsplit(first["url"])
        self.assertEqual((url.scheme, url.netloc, url.path), ("http", "127.0.0.1:1234", "/api/v1/message/text"))
        self.assertEqual(parse_qs(url.query), {"password": [PASSWORD]})
        self.assertEqual({k: v for k, v in first["body"].items() if k != "tempGuid"},
                         {"chatGuid": OWNER_CHAT, "message": "hello", "method": "apple-script"})
        self.assertEqual(uuid.UUID(first["body"]["tempGuid"]).version, 4)
        self.assertNotEqual(first["body"]["tempGuid"], second["body"]["tempGuid"])
        self.assertEqual((first["headers"], first["timeout"]), ({"Content-Type": "application/json"}, 10))
        self.assertNotIn(PASSWORD, repr(sender))

    def test_failures_never_leak_the_query_or_password(self):
        for status, code in ((500, "http-error"), (302, "http-error"), ("oserror", "transport-error")):
            with self.subTest(status=status):
                with self.assertRaises(BridgeError) as ctx:
                    BlueBubblesSender(BASE, self.pw, FakeTransport(status)).send(OWNER_CHAT, "hi", [])
                err = ctx.exception
                self.assertEqual((err.code, err.status), (code, status if code == "http-error" else None))
                self.assertIn("/api/v1/message/text", str(err))
                for text in (str(err), repr(err), repr(err.args), repr(err.__cause__), repr(err.__context__)):
                    self.assertNotIn(PASSWORD, text)
                    self.assertNotIn("?", text)

    def test_unsafe_targets_and_files_are_refused(self):
        with mock.patch.object(bridge._OPENER, "open") as opener, mock.patch("urllib.request.urlopen") as urlopen:
            for url in ("http://192.0.2.1:1234", "https://example.com", "http://127.0.0.1", "ftp://127.0.0.1:1234",
                        "http://127.0.0.1.example.com:1234", "http://user:pw@127.0.0.1:1234",
                        "http://localhost:1234/api?x=1", None):
                with self.subTest(url=url), self.assertRaises(ValueError):
                    BlueBubblesSender(url, self.pw)
            self.assertEqual((opener.call_count, urlopen.call_count), (0, 0))
        for mode in (0o644, 0o640, 0o604):
            with self.subTest(mode=oct(mode)), self.assertRaises(ValueError):
                BlueBubblesSender(BASE, password_file(self, mode))
        link = self.pw.with_name("link")
        os.symlink(self.pw, link)
        for path in (link, self.pw.parent, self.pw.with_name("missing")):
            with self.subTest(path=path.name), self.assertRaises(ValueError):
                BlueBubblesSender(BASE, path)
        self.assertIsInstance(BlueBubblesSender("https://localhost:1234/", self.pw), BlueBubblesSender)

    def test_attachments_are_sent_as_a_note_and_lost_password_is_refused_without_a_request(self):
        fake = FakeTransport()
        sender = BlueBubblesSender(BASE, self.pw, fake)
        sender.send(OWNER_CHAT, "photo", ["/tmp/fixture.png"])
        [call] = fake.calls
        self.assertEqual(call["body"]["message"], "photo\n" + bridge.PICTURE_NOTE)
        self.assertNotIn("fixture.png", json.dumps(call))
        self.pw.chmod(0o644)
        for attachments in ([], ["/tmp/fixture.png"]):
            with self.subTest(attachments=attachments), self.assertRaises(BridgeError) as ctx:
                sender.send(OWNER_CHAT, "hi", attachments)
            self.assertEqual((ctx.exception.code, len(fake.calls)), ("password-unreadable", 1))


class ConversationBridgeTests(ConversationTestCase):
    def setUp(self):
        super().setUp()
        self.set_settings({**SETTINGS, "ownerChat": OWNER_CHAT})
        self.conv.db.close()
        self.conv = self.open()

    def test_normalized_events_match_the_fixture_jsonl(self):
        names = ["new-message", "new-message", "from-me", "updated-message", "stranger"]
        inbound = [normalize(event(n)) for n in names]
        folder = tempfile.TemporaryDirectory(prefix="hass-bridge-")
        self.addCleanup(folder.cleanup)
        jsonl = Path(folder.name) / "events.jsonl"
        jsonl.write_text("".join(json.dumps({"id": m.provider_id, "chat": m.chat, "sender": m.sender, "text": m.text,
                                             "fromMe": m.from_me, "kind": m.kind, "at": m.received_at}) + "\n"
                                 for m in inbound), "utf-8")
        self.assertEqual(FixtureAdapter(jsonl).inbound(), inbound)
        self.assertEqual([self.conv.handle(m) for m in inbound],
                         ["proposed", "duplicate", "echo", "not-read", "ignored"])

    def test_failed_send_stays_unsent_until_the_next_flush(self):
        self.assertEqual(self.conv.handle(normalize(event("new-message"))), "proposed")
        fake = FakeTransport(500)
        sender = BlueBubblesSender(BASE, password_file(self), fake)
        with self.assertRaises(BridgeError):
            self.conv.flush(sender)
        self.assertEqual(len(self.conv.outbox.unsent()), 1)
        self.assertEqual(self.conv.flush(sender), 1)
        self.assertEqual(self.conv.outbox.unsent(), [])
        first, second = fake.calls
        self.assertEqual(first["body"]["message"], second["body"]["message"])
        self.assertTrue(second["body"]["message"].startswith("Here's the change I'd make:"))
        self.assertEqual(second["body"]["chatGuid"], OWNER_CHAT)
