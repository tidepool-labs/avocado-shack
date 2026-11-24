"""Offline contract tests for the pilot window's digest-only report."""

from contextlib import closing, redirect_stderr, redirect_stdout
from hashlib import sha256
import importlib.util
from io import StringIO
from pathlib import Path
import sqlite3
from tempfile import TemporaryDirectory
import unittest
from unittest.mock import patch

from hass.conversation import SCHEMA


SCRIPT = Path(__file__).resolve().parents[2] / "scripts/hass/pilot_sender_check.py"
SPEC = importlib.util.spec_from_file_location("pilot_sender_check", SCRIPT)
assert SPEC is not None and SPEC.loader is not None
check = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(check)

START = "2030-01-01T12:00:00Z"
END = "2030-01-01T13:00:00Z"
ALLOWED_CHAT = "fixture-chat-é"
OTHER_CHAT = "fixture-chat-other"
DISPOSITION = "fixture-disposition"
MESSAGE_TEXT = "fixture-message-body"


def digest(chat):
    return sha256(chat.encode("utf-8")).hexdigest()[:12]


class PilotSenderCheckTests(unittest.TestCase):
    def setUp(self):
        directory = TemporaryDirectory()
        self.addCleanup(directory.cleanup)
        # URI delimiters in the filename must not alter the open options.
        self.store = Path(directory.name) / "fixture?#.sqlite"
        with closing(sqlite3.connect(self.store)) as db, db:
            db.executescript(SCHEMA)
            db.execute("INSERT INTO outbox(chat, text, attachments, created_at) VALUES (?, ?, '[]', ?)",
                       (OTHER_CHAT, MESSAGE_TEXT, START))
        self.private = {ALLOWED_CHAT, OTHER_CHAT, DISPOSITION, MESSAGE_TEXT, str(self.store)}

    def add_message(self, key, time, chat):
        provider_id = f"fixture-provider-{key}"
        self.private.add(provider_id)
        with closing(sqlite3.connect(self.store)) as db, db:
            db.execute("INSERT INTO messages VALUES (?, ?, ?)", (provider_id, DISPOSITION, time))
            if chat is not None:
                db.execute("INSERT INTO message_chats VALUES (?, ?)", (provider_id, chat))

    def invoke(self, *extra, start=START, end=END, allowed=None, usage=False):
        opts = ["--conversation", str(self.store), "--from", start, "--to", end]
        if not usage:
            opts += ["--allow", digest(ALLOWED_CHAT) if allowed is None else allowed]
        out, err = StringIO(), StringIO()
        with redirect_stdout(out), redirect_stderr(err):
            try:
                status = check.main([*opts, *extra])
            except SystemExit as exc:
                status = exc.code
        for value in self.private:
            self.assertNotIn(value, out.getvalue() + err.getvalue())
        return status, out.getvalue().splitlines(), err.getvalue()

    def assert_report(self, result, status, *lines):
        final = "PASS" if status == 0 else "FAIL"
        self.assertEqual(result, (status, [*lines, f"{final} pilot_sender_check"], ""))

    def test_counts_only_messages_in_half_open_window_by_instant(self):
        # Lexical filtering, a closed end, or using the outbox changes these totals.
        second_chat = "fixture-chat-second"
        self.private.add(second_chat)
        self.add_message("before", "2030-01-01T12:59:59.999999+01:00", OTHER_CHAT)
        self.add_message("start", "2030-01-01T07:00:00-05:00", ALLOWED_CHAT)
        self.add_message("middle", "2030-01-01T13:15:00+01:00", ALLOWED_CHAT)
        self.add_message("second", "2030-01-01T12:59:59.999999Z", second_chat)
        self.add_message("end", "2030-01-01T14:00:00+01:00", OTHER_CHAT)
        self.add_message("after", "2030-01-01T08:01:00-05:00", None)
        self.assert_report(
            self.invoke("--allow", digest(second_chat), start="2030-01-01T13:00:00+01:00"), 0,
            *sorted([f"chat {digest(ALLOWED_CHAT)} messages 2 allowed",
                     f"chat {digest(second_chat)} messages 1 allowed"]),
        )

    def test_other_chat_reports_counts_and_one_finding_per_digest(self):
        # Checking only a representative message, or reporting each repeat, fails.
        self.add_message("allow", START, ALLOWED_CHAT)
        self.add_message("other-a", START, OTHER_CHAT)
        self.add_message("other-b", START, OTHER_CHAT)
        for selection in ((), ("--expect-chat", digest(ALLOWED_CHAT))):
            with self.subTest(selection=selection):
                self.assert_report(
                    self.invoke(*selection), 1,
                    *sorted([f"chat {digest(ALLOWED_CHAT)} messages 1 allowed",
                             f"chat {digest(OTHER_CHAT)} messages 2 other"]),
                    f"FAIL other-chat {digest(OTHER_CHAT)}",
                )

    def test_unattributed_messages_are_counted_despite_other_chat_rows(self):
        # An inner join silently loses these, or a wrong join assigns them a chat.
        self.add_message("with-chat", START, ALLOWED_CHAT)
        self.add_message("orphan-a", START, None)
        self.add_message("orphan-b", START, None)
        for selection in ((), ("--expect-chat", digest(ALLOWED_CHAT))):
            with self.subTest(selection=selection):
                self.assert_report(self.invoke(*selection), 1,
                                   f"chat {digest(ALLOWED_CHAT)} messages 1 allowed", "FAIL unattributed 2")

    def test_bad_digest_is_a_finding_not_a_usage_error(self):
        # Do not normalize uppercase, accept a prefix, or ignore a second bad flag.
        for invalid in ("ABCDEF012345", "abcdef01234", "abcdef01234g", "abcdef012345\n", ""):
            with self.subTest(invalid=invalid):
                self.assert_report(self.invoke("--allow", invalid), 1, "FAIL bad-digest")

    def test_bad_argument_time_is_a_finding_not_a_usage_error(self):
        # Reject unparseable times and naive times on either endpoint.
        for field in ("start", "end"):
            for invalid in ("fixture-time-invalid", "2030-01-01T12:30:00", ""):
                with self.subTest(field=field, invalid=invalid):
                    self.assert_report(self.invoke(start=invalid if field == "start" else START,
                                                   end=invalid if field == "end" else END),
                                       1, "FAIL bad-time")

    def test_bad_store_timestamp_cannot_be_silently_skipped(self):
        # NULL, naive, and malformed rows cannot be proven outside the window.
        for invalid in (None, "2030-01-01T12:30:00", "fixture-time-invalid"):
            with self.subTest(invalid=invalid):
                self.add_message("bad-clock", invalid, ALLOWED_CHAT)
                self.assert_report(self.invoke(), 1, "FAIL bad-time")
                with closing(sqlite3.connect(self.store)) as db, db:
                    db.execute("DELETE FROM messages")
                    db.execute("DELETE FROM message_chats")

    def test_empty_window_requires_ordered_bounds_not_nonzero_traffic(self):
        # Equality through an offset and backwards bounds must fail; silence is OK.
        self.assert_report(self.invoke(end="2030-01-01T07:00:00-05:00"), 1, "FAIL empty-window")
        self.assert_report(self.invoke(end="2030-01-01T11:59:59Z"), 1, "FAIL empty-window")
        self.assert_report(self.invoke(), 0)

    def test_selected_owner_chat_must_appear(self):
        # A clean allowlist is not evidence of the selected chat: accepting
        # silence, any allowed row, or an end-boundary row would falsely pass.
        expected, other = digest(ALLOWED_CHAT), digest(OTHER_CHAT)
        allow_other = ("--allow", other)
        select = (*allow_other, "--expect-chat", expected)
        other_line = f"chat {other} messages 1 allowed"
        missing = "FAIL missing-expected-chat"
        with self.subTest(case="empty selection"):
            self.assert_report(self.invoke(*select), 1, missing)
        self.add_message("other-allowed", START, OTHER_CHAT)
        with self.subTest(case="only the other allowed chat"):
            self.assert_report(self.invoke(*allow_other), 0, other_line)
            self.assert_report(self.invoke(*select), 1, other_line, missing)
        self.add_message("end", END, ALLOWED_CHAT)
        with self.subTest(case="expected chat at excluded boundary"):
            self.assert_report(self.invoke(*select), 1, other_line, missing)
        self.add_message("start", START, ALLOWED_CHAT)
        with self.subTest(case="expected chat inside window"):
            self.assert_report(self.invoke(*select), 0,
                               *sorted([other_line, f"chat {expected} messages 1 allowed"]))

    def test_expected_chat_must_be_one_valid_allowed_digest(self):
        # Do not let --expect-chat extend the allowlist or silently pick the
        # last of multiple values. Invalid arguments must not echo raw input.
        expected = digest(ALLOWED_CHAT)
        self.add_message("expected", START, ALLOWED_CHAT)
        for options, finding in (
            (("--expect-chat", ALLOWED_CHAT), "bad-digest"),
            (("--expect-chat", digest(OTHER_CHAT)), "expected-chat-not-allowed"),
            (("--expect-chat", expected, "--expect-chat", expected), "multiple-expected-chats"),
        ):
            with self.subTest(finding=finding):
                self.assert_report(self.invoke(*options), 1, f"FAIL {finding}")

    def test_missing_tables_report_each_fixed_name(self):
        # A schema check must distinguish missing tables from an empty result set.
        with closing(sqlite3.connect(self.store)) as db, db:
            db.execute("DROP TABLE message_chats")
        self.assert_report(self.invoke(), 1, "FAIL missing-table message_chats")
        with closing(sqlite3.connect(self.store)) as db, db:
            db.execute("DROP TABLE messages")
        self.assert_report(self.invoke(), 1, "FAIL missing-table messages",
                           "FAIL missing-table message_chats")

    def test_opens_existing_store_with_a_read_only_connection(self):
        # Unchanged bytes alone would not distinguish a read from a write-capable open.
        real_connect = sqlite3.connect
        before = self.store.read_bytes()

        def connect(*args, **kwargs):
            db = real_connect(*args, **kwargs)
            with self.assertRaisesRegex(sqlite3.OperationalError, "readonly"):
                db.execute("CREATE TABLE write_probe(value TEXT)")
            return db

        with patch.object(check.sqlite3, "connect", side_effect=connect):
            self.assert_report(self.invoke(), 0)
        self.assertEqual(self.store.read_bytes(), before)

    def test_unreadable_or_malformed_store_fails_without_leaking_errors(self):
        # A missing file must not be created. SQLite errors must not escape.
        self.store.unlink()
        self.assert_report(self.invoke(), 1)
        self.assertFalse(self.store.exists())
        self.store.write_bytes(b"fixture-not-sqlite")
        self.assert_report(self.invoke(), 1)
        self.assertEqual(self.store.read_bytes(), b"fixture-not-sqlite")

    def test_missing_required_option_is_argparse_usage_error(self):
        # A missing flag (rather than a provided invalid value) keeps exit 2.
        status, lines, err = self.invoke(usage=True)
        self.assertEqual((status, lines), (2, []))
        self.assertIn("usage:", err)
        self.assertIn("--allow", err)


if __name__ == "__main__":
    unittest.main()
