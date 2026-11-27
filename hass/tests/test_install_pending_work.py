"""Fixture-only tests for the attended operator's pending-work checker."""

from contextlib import closing, redirect_stderr, redirect_stdout
import importlib.util
import io
from pathlib import Path
import sqlite3
import tempfile
import unittest
from unittest.mock import patch

from hass import conversation, inbox, relay


SCRIPT = Path(__file__).resolve().parents[2] / "scripts/hass/install_pending_work.py"
SPEC = importlib.util.spec_from_file_location("install_pending_work", SCRIPT)
assert SPEC is not None and SPEC.loader is not None
CHECKER = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(CHECKER)

CHAT = "synthetic-chat-key"
TEXT = "synthetic-text-marker"
PAYLOAD = '{"marker":"synthetic-payload-marker"}'
ATTACHMENTS = '["synthetic-attachment-marker"]'
STAMP = "2000-01-01T00:00:00Z"
ZERO_COUNTS = ["outbox_unsent 0", "relay_unacked 0", "card_receipt_pending 0", "inbound_pending 0"]


class InstallPendingWorkTests(unittest.TestCase):
    def setUp(self):
        self.root = Path(self.enterContext(tempfile.TemporaryDirectory()))

    def create(self, path, schema):
        with closing(sqlite3.connect(path)) as db:
            db.executescript(schema)

    def change(self, path, sql, values=()):
        with closing(sqlite3.connect(path)) as db, db:
            db.execute(sql, values)

    def done_stores(self, root):
        conversation_path = root / "conversation #?.sqlite3"
        self.create(conversation_path, conversation.SCHEMA)
        self.change(conversation_path,
                    "INSERT INTO outbox(chat,text,attachments,created_at,sent_at) VALUES (?,?,?,?,?)",
                    (CHAT, TEXT, ATTACHMENTS, STAMP, STAMP))
        inbox_path = root / "inbox.sqlite3"
        self.create(inbox_path, inbox.SCHEMA)
        self.change(inbox_path,
                    "INSERT INTO inbound(provider_id,received_at,payload,state,enqueued_at) VALUES (?,?,?,?,?)",
                    ("synthetic-provider-key", STAMP, PAYLOAD, "done", STAMP))
        self.change(inbox_path,
                    "INSERT INTO inbound(provider_id,received_at,payload,state,enqueued_at) VALUES (?,?,?,?,?)",
                    ("synthetic-history-key", STAMP, PAYLOAD, "history", STAMP))
        with closing(relay.RelayStore(root).db) as db:
            db.execute("INSERT INTO relay(chat,text,pictures,created_at,handed_at,acked_at) VALUES (?,?,0,1,2,3)",
                       (CHAT, TEXT))
            db.execute("INSERT INTO card_receipt(outbox_id,relay_id,png_sha256,state) VALUES (1,1,?,'confirmed')",
                       ("0" * 64,))
        return {"conversation": conversation_path, "relay": root / "relay.sqlite3", "inbox": inbox_path}

    def check(self, code, lines, stores=None, *, complete=False, partial=False):
        argv = ["--complete"] if complete else []
        argv.extend(arg for store, path in (stores or {}).items() for arg in (f"--{store}", str(path)))
        stdout, stderr = io.StringIO(), io.StringIO()
        with redirect_stdout(stdout), redirect_stderr(stderr):
            result = CHECKER.main(argv)
        for marker in (CHAT, TEXT, "synthetic-payload-marker", "synthetic-attachment-marker",
                       "synthetic-provider-key", str(self.root)):
            self.assertNotIn(marker, stdout.getvalue() + stderr.getvalue())
        self.assertEqual(result, code)
        self.assertEqual(stderr.getvalue(), "")
        final = "FAIL" if code else "PARTIAL PASS" if partial else "PASS"
        self.assertEqual(stdout.getvalue(), "\n".join([*lines, f"{final} install_pending_work", ""]))

    def test_done_stores_pass_read_only(self):
        # A writable open can leave bytes identical, so check the actual URI as well.
        stores = self.done_stores(self.root)
        before = {path: path.read_bytes() for path in stores.values()}
        with patch.object(CHECKER.sqlite3, "connect", wraps=sqlite3.connect) as connect:
            self.check(0, ZERO_COUNTS, stores)
        self.assertEqual(len(connect.call_args_list), 3)
        self.assertEqual({call.args[0] for call in connect.call_args_list},
                         {path.absolute().as_uri() + "?mode=ro" for path in before})
        self.assertTrue(all(call.kwargs.get("uri") is True for call in connect.call_args_list))
        self.assertEqual({path: path.read_bytes() for path in before}, before)

    def test_complete_clearance_requires_all_stores(self):
        # Merely counting the supplied stores could clear an install with no relay evidence.
        stores = self.done_stores(self.root)
        self.check(1, ["FAIL missing-store relay", "outbox_unsent 0", "inbound_pending 0"],
                   {"conversation": stores["conversation"], "inbox": stores["inbox"]}, complete=True)
        self.check(0, ZERO_COUNTS, stores, complete=True)

    def test_each_pending_kind_blocks_independently(self):
        # A wrong predicate, missed queue, or swapped label must fail on its own.
        for index, (store, sql) in enumerate((
            ("conversation", "UPDATE outbox SET sent_at = NULL"),
            ("relay", "UPDATE relay SET acked_at = NULL"),
            ("relay", "UPDATE card_receipt SET state = 'pending'"),
            ("inbox", "UPDATE inbound SET state = 'pending' WHERE state = 'done'"),
        )):
            name = ZERO_COUNTS[index].split()[0]
            with self.subTest(check=name), tempfile.TemporaryDirectory(dir=self.root) as directory:
                stores = self.done_stores(Path(directory))
                self.change(stores[store], sql)
                expected = ZERO_COUNTS.copy()
                expected[index:index + 1] = [f"{name} 1", f"FAIL pending {name}"]
                self.check(1, expected, stores, complete=True)

    def test_schema_findings_do_not_hide_other_checks(self):
        # Distinguish an absent table from an absent column and keep checking later stores.
        malformed = self.root / "relay.sqlite3"
        self.create(malformed, "CREATE TABLE card_receipt(other TEXT);")
        inbound = self.root / "inbox.sqlite3"
        self.create(inbound, inbox.SCHEMA)
        self.check(1, ["FAIL missing-table relay", "FAIL missing-column card_receipt.state", "inbound_pending 0"],
                   {"relay": malformed, "inbox": inbound})

    def test_only_supplied_store_is_counted(self):
        # An omitted store is neither read by default nor cleared by a diagnostic pass.
        inbound = self.root / "inbox.sqlite3"
        self.create(inbound, inbox.SCHEMA)
        self.check(0, ["inbound_pending 0"], {"inbox": inbound}, partial=True)

    def test_unusable_files_fail_without_echoing_inputs(self):
        # No input details or raw SQLite errors, even when no query succeeds.
        garbage = self.root / TEXT
        garbage.write_text(PAYLOAD, encoding="utf-8")
        empty = self.root / "empty.sqlite3"
        empty.touch()
        missing = self.root / "absent.sqlite3"
        for path in (garbage, empty, missing, self.root):
            with self.subTest(path=path.name):
                self.check(1, ["FAIL not-sqlite"], {"conversation": path})
        self.assertFalse(missing.exists())

    def test_no_store_is_a_named_failure(self):
        # Do not let vacuous zero counts pass or let argparse turn this into exit 2.
        self.check(1, ["FAIL no-store"])

    def test_argparse_usage_error_keeps_exit_two(self):
        # A flag without FILE is still an argparse syntax error, not a finding.
        stdout, stderr = io.StringIO(), io.StringIO()
        with redirect_stdout(stdout), redirect_stderr(stderr), self.assertRaises(SystemExit) as raised:
            CHECKER.main(["--inbox"])
        self.assertEqual(raised.exception.code, 2)
        self.assertEqual(stdout.getvalue(), "")
        self.assertIn("usage:", stderr.getvalue())
