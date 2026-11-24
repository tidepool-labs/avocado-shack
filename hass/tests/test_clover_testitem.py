"""TESTITEM readiness and attended chat rehearsal, entirely on fixtures."""
import io
import json
import os
import re
import runpy
import sqlite3
import sys
import tempfile
from contextlib import closing, redirect_stdout, redirect_stderr
from pathlib import Path
from unittest import mock

from hass import voice
from hass.clover import cache
from hass.clover.apply import ApplyEngine
from hass.clover.chat import TillDesk
from hass.clover.client import CloverWriteClient
from hass.clover.config import from_settings
from hass.clover.credential import Token
from hass.clover.journal import Journal
from hass.tests.clover_fake import FakeClover
from hass.tests.test_clover_client import FAKE_TOKEN, MID, NoNetwork
from hass.tests.test_clover_write_readiness import ITEM, NOW, READS, SCRIPT

RUNBOOK = SCRIPT.parents[2] / "docs/hass/CLOVER-TESTITEM.md"
CATEGORY = {"id": "FAKECAT000001", "name": "Fixture Pantry"}
OWNER = {"sender": "fake-owner", "chat": "fake-private-chat"}
CATEGORY_REQUEST = {"method": "POST", "path": "/category_items"}


class TestitemTests(NoNetwork):
    def setUp(self):
        super().setUp()
        folder = self.enterContext(tempfile.TemporaryDirectory(dir=os.environ.get("HERMES_KANBAN_WORKSPACE")))
        self.root = Path(folder).resolve()
        self.host = self.root / "fixture-host.json"
        token = self.root / "fixture-write-token"
        token.touch(mode=0o600)
        token.write_text(FAKE_TOKEN, encoding="utf-8")
        self.settings = dict(environment="sandbox", merchantId=MID, tokenFile=str(self.root / "fixture-read-token"),
                             writeTokenFile=str(token), writes=True, liveApproved=True, dailyWriteCap=5,
                             categoryMap={"pantry": CATEGORY["name"]})
        self.host.touch(mode=0o600)
        self.host.write_text(json.dumps({"state": str(self.root), "clover": self.settings}), encoding="utf-8")
        self.config = from_settings(self.settings)
        path = cache.path_for(self.root)
        path.parent.mkdir(mode=0o700)
        path.touch(mode=0o600)
        with closing(sqlite3.connect(path)) as db, db:
            db.executescript(cache.SCHEMA)
            db.executemany("INSERT INTO meta VALUES (?, ?)", (
                ("environment", "sandbox"), ("merchantId", MID), ("schema", cache.SCHEMA_VERSION),
                ("lastResult", "ok"), ("failures", "0"),
            ))
            db.executemany("INSERT INTO snapshots(taken, id, stock) VALUES (?, ?, '0')",
                           [(t.isoformat(), cache.READ_MARK) for t in READS])
        self.journal = Journal(self.root, self.config)
        self.serial = 0

    def add(self, kind, *, item=ITEM, status="applied", hidden=True, requests=()):
        self.serial += 1
        draft = {"kind": kind, "item_id": None if kind == "create_item" else item,
                 "requests": requests, "after": {"hidden": hidden, "stock": "8877"}}
        with self.journal.locked() as db:
            db.execute("INSERT INTO changes VALUES (?, ?, ?, ?, ?, ?, ?, ?)", (
                str(self.serial), json.dumps(draft), OWNER["sender"], OWNER["chat"], 0, status, "2032-03-04",
                json.dumps({**draft, "result_item_id": item}),
            ))

    def cli(self, *flags):
        stdout, stderr = io.StringIO(), io.StringIO()
        argv = [str(SCRIPT), "--host", str(self.host), "--now", NOW.isoformat(), *flags]
        with (mock.patch.object(sys, "argv", argv), mock.patch.object(sys, "path", sys.path[:]),
              mock.patch.object(sys, "dont_write_bytecode", True), redirect_stdout(stdout), redirect_stderr(stderr),
              self.assertRaises(SystemExit) as exit_info):
            runpy.run_path(str(SCRIPT), run_name="__main__")
        self.assertEqual(stderr.getvalue(), "")
        text = stdout.getvalue()
        self.assertEqual(len(text.splitlines()), 1)
        for private in (str(self.root), FAKE_TOKEN, MID, ITEM, "OTHERFIXTURE", CATEGORY["id"], "8877"):
            self.assertNotIn(private, text)
        return exit_info.exception.code, json.loads(text)

    def test_c1_check(self):
        # C1: an unscoped join or an 'ever hidden' check would certify incomplete or superseded proof.
        def expect(word):
            code, output = self.cli("--for", "inventory")
            self.assertEqual((code, output["result"], output["checks"]["testitem_inventory"]),
                             (0, "pass", "ok") if word == "ok" else (1, "fail", word))

        self.add("create_item", status="failed", requests=(CATEGORY_REQUEST,))
        expect("no-create")
        self.add("create_item", item="OTHERFIXTURE", requests=({**CATEGORY_REQUEST, "method": "GET"},))
        self.add("set_stock", item="OTHERFIXTURE")
        self.add("set_hidden", item="OTHERFIXTURE")
        expect("no-category")
        self.add("create_item", requests=(CATEGORY_REQUEST,))
        self.add("set_stock", status="intent")
        expect("no-count")
        self.add("set_stock")
        self.add("set_hidden", status="draft")
        expect("not-hidden")
        self.add("set_hidden")
        expect("ok")
        self.add("set_hidden", hidden=False)
        expect("not-hidden")
        self.add("set_hidden")
        self.add("set_price")
        expect("not-hidden")
        self.add("set_hidden")
        self.add("set_hidden", hidden=False, status="failed")
        before = self.journal.path.read_bytes(), self.journal.path.parent.stat().st_mtime_ns
        expect("ok")
        self.assertEqual((self.journal.path.read_bytes(), self.journal.path.parent.stat().st_mtime_ns), before)

    def test_c2_opt_in(self):
        # C2: treating the new word like a legacy required check would break the previous warning/pass.
        self.add("create_item")
        self.add("set_hidden")
        for flags, code, result in (((), 0, "pass"), (("--for", "inventory"), 1, "fail")):
            with self.subTest(flags=flags):
                self.assertEqual(self.cli(*flags), (code, {"result": result, "checks": {
                    "read_only_day": "ok", "write_token_file": "ok", "settings": "ok", "daily_cap": "ok",
                    "testitem": "warn_missing_stock", "testitem_inventory": "no-category",
                }}))

    @staticmethod
    def sentences():
        return re.findall(r"^\d+\. `([^`]+)`", RUNBOOK.read_text(encoding="utf-8"), re.M)

    def test_c3_runbook_sentences(self):
        # C3: a plausible paraphrase could stop matching TillDesk's fixed command grammar.
        desk = TillDesk(self.root, self.settings, engine=ApplyEngine(self.root, self.config, None,
                                                                     mike=tuple(OWNER.values())))
        self.assertEqual([desk.parse(line) for line in self.sentences()], [
            ("till", "new", "TESTITEM, 1.23, pantry", None),
            ("till", "set", "testitem", "7"),
            ("till", "hide", "testitem", "hide"),
        ])

    def test_c4_fake_till_rehearsal(self):
        # C4: accepting the syntax alone would miss a dropped category link or a count that never reaches the till.
        fake = FakeClover(merchant=MID, categories=(CATEGORY,))
        self.enterContext(mock.patch.dict("hass.clover.client.HOSTS", {"sandbox": "https://till.invalid"}))
        engine = ApplyEngine(self.root, self.config,
                             lambda token: CloverWriteClient(MID, token, fake, min_interval=0, max_retries=0),
                             mike=tuple(OWNER.values()), clock=NOW.timestamp)
        desk = TillDesk(self.root, self.settings, engine=engine)
        expected = (("Category: Fixture Pantry", "is in it, SKU"),
                    ("Count: not counted", "now shows 7"),
                    ("Hide TESTITEM", "is hidden"))
        for line, (preview_word, readback_word) in zip(self.sentences(), expected, strict=True):
            preview = desk.answer(desk.parse(line), NOW, **OWNER)
            self.assertIn(preview_word, preview)
            approvals = re.findall(r"Reply yes ([0-9a-f]{8})", voice.plain(preview))
            self.assertEqual(len(approvals), 1, preview)
            (code,) = approvals
            self.assertEqual(desk.first(f"yes {code}", **OWNER), ("yes", code))
            reply, site_ops = desk.approve(code, **OWNER)
            self.assertTrue(reply.startswith("Done, and I read the till back:"), reply)
            self.assertIn(readback_word, reply)
            self.assertEqual(site_ops, ())
        client = CloverWriteClient(MID, Token(FAKE_TOKEN), fake, min_interval=0, max_retries=0)
        (item,) = client.list_items()
        self.assertEqual(item["name"], "TESTITEM")
        self.assertIs(item["hidden"], True)
        self.assertEqual(item["categories"]["elements"], [CATEGORY])
        self.assertEqual(item["itemStock"]["quantity"], 7)
        self.assertEqual(fake.register_search("TESTITEM"), [])
        self.assertEqual([method for method, _, _ in fake.log if method != "GET"], ["POST", "POST", "PUT", "POST"])
        code, output = self.cli("--for", "inventory")
        self.assertEqual((code, output["result"], output["checks"]["testitem_inventory"]), (0, "pass", "ok"))
