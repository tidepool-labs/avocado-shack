"""Offline contracts for the Clover readiness command."""
import builtins
import io
import json
import os
import runpy
import sqlite3
import sys
import tempfile
from contextlib import closing, redirect_stderr, redirect_stdout
from datetime import datetime, timedelta, timezone
from pathlib import Path
from unittest import mock

from hass.clover import cache, credential
from hass.clover.config import from_settings
from hass.clover.journal import Journal
from hass.tests.test_clover_client import NoNetwork


SCRIPT = Path(__file__).resolve().parents[2] / "scripts/hass/clover_write_readiness.py"
NOW = datetime(2032, 3, 4, tzinfo=timezone.utc)
READS = tuple(NOW - timedelta(minutes=30 * i) for i in range(49, 0, -1))
TOKEN_BYTES = b"fixture-only contents, not a usable token"
ITEM = "SYNTHETICITEM"


class ReadinessTests(NoNetwork):
    def setUp(self):
        super().setUp()
        workspace = os.environ.get("HERMES_KANBAN_WORKSPACE")
        folder = self.enterContext(tempfile.TemporaryDirectory(dir=workspace))
        self.root = Path(folder).resolve()
        self.host = self.root / "host.json"
        self.token = self.root / "fake-write-file"
        self.token.write_bytes(TOKEN_BYTES)
        self.token.chmod(0o600)
        self.settings = dict(environment="sandbox", merchantId="FAKEMERCH01",
                             tokenFile=str(self.root / "fake-read-file"), writeTokenFile=str(self.token),
                             writes=False, liveApproved=False, dailyWriteCap=5)
        self.save_host()
        self.config = from_settings(self.settings)
        self.cache_path = cache.path_for(self.root)
        self.cache_path.parent.mkdir(mode=0o700)
        with closing(sqlite3.connect(self.cache_path)) as db:
            db.executescript(cache.SCHEMA)
            db.executemany("INSERT INTO meta VALUES (?, ?)", (
                ("environment", self.config.environment), ("merchantId", self.config.merchant_id),
                ("schema", cache.SCHEMA_VERSION), ("lastResult", "ok"), ("failures", "0"),
                ("lastAttempt", READS[-1].isoformat()), ("asOf", READS[-1].isoformat()),
            ))
            db.commit()
        self.cache_path.chmod(0o600)
        self.history(READS)
        self.journal = Journal(self.root, self.config)
        self.add_change("create_item")
        self.add_change("set_hidden")

    def save_host(self):
        host = {"state": str(self.root), "clover": self.settings, "secretFile": str(self.root / "unused"),
                "runtimeCommit": "0" * 40, "listen": "127.0.0.1:8080", "allowedPeers": [],
                "approvals": "hold", "interpreter": {"url": "http://127.0.0.1:9000", "model": "fixture"}}
        self.host.write_text(json.dumps(host), encoding="utf-8")
        self.host.chmod(0o600)

    def history(self, times, *, result="ok", failures=0):
        with closing(sqlite3.connect(self.cache_path)) as db, db:
            db.execute("DROP TABLE snapshots")
            db.execute("CREATE TABLE snapshots(taken TEXT, id TEXT, stock TEXT, PRIMARY KEY(taken, id))")
            db.executemany("INSERT INTO snapshots VALUES (?, ?, '0')", [(t.isoformat(), cache.READ_MARK) for t in times])
            db.executemany("UPDATE meta SET value=? WHERE key=?", [(result, "lastResult"), (failures, "failures")])

    def add_change(self, kind, *, item=ITEM, status="applied", hidden=True):
        item_id = None if kind == "create_item" else item
        draft = {"kind": kind, "item_id": item_id, "after": {"hidden": hidden} if kind == "set_hidden" else {}}
        result = {**draft, "result_item_id": item}
        with self.journal.locked() as db:
            number = db.execute("SELECT count(*) FROM changes").fetchone()[0]
            db.execute("INSERT INTO changes VALUES (?, ?, 'fake-owner', 'fake-chat', ?, ?, '2032-03-04', ?)",
                       (f"fixture-{number}", json.dumps(draft), number + 600, status, json.dumps(result)))

    def cli(self, *, now: str | None = NOW.isoformat(), host: Path | None = None):
        argv = [str(SCRIPT), "--host", str(self.host if host is None else host)]
        if now is not None:
            argv += ["--now", now]
        stdout, stderr = io.StringIO(), io.StringIO()
        with (mock.patch.object(sys, "argv", argv), mock.patch.object(sys, "path", sys.path[:]),
              mock.patch.object(sys, "dont_write_bytecode", True), redirect_stdout(stdout), redirect_stderr(stderr),
              self.assertRaises(SystemExit) as outcome):
            runpy.run_path(str(SCRIPT), run_name="__main__")
        text = stdout.getvalue()
        self.assertEqual(stderr.getvalue(), "")
        self.assertEqual(len(text.splitlines()), 1, text)
        self.assertTrue(text.endswith("\n"))
        self.assertNotIn(str(self.root), text)
        self.assertNotIn(TOKEN_BYTES.decode(), text)
        self.assertNotIn(ITEM, text)
        self.assertNotIn(self.config.merchant_id, text)
        return outcome.exception.code, json.loads(text)

    def test_c1_output_and_exit(self):
        # C1: a warning must exit 0, a failed check 1, and unreadable input 2 without a traceback or path.
        code, output = self.cli()
        self.assertEqual((code, output), (0, {"result": "pass", "checks": {
            "read_only_day": "ok", "write_token_file": "ok", "settings": "ok", "daily_cap": "ok",
            "testitem": "warn_missing_stock"}}))
        code, output = self.cli(now=(NOW + timedelta(seconds=1)).isoformat())
        self.assertEqual((code, output["result"]), (1, "fail"))
        for code, failed in (self.cli(host=self.root / "missing-host"), self.cli(now="not an ISO date")):
            self.assertEqual((code, failed["result"]), (2, "fail"))
            self.assertEqual(failed["checks"].keys(), output["checks"].keys())
        self.cache_path.write_bytes(b"not SQLite")
        code, output = self.cli(now=None)
        self.assertEqual((code, output["result"], output["checks"]["read_only_day"]), (2, "fail", "unreadable"))

    def test_c2_read_only_day(self):
        # C2: min/max alone would miss a gap; age alone would miss short history or a failed latest pull.
        cases = (
            ("boundary pass", READS, "ok", 0, "ok"),
            ("old gap outside run", (READS[0] - timedelta(hours=2), *READS), "ok", 0, "ok"),
            ("gap", READS[:20] + READS[21:], "ok", 0, "coverage"),
            ("short", READS[1:], "ok", 0, "coverage"),
            ("stale", tuple(t - timedelta(seconds=1) for t in READS), "ok", 0, "stale"),
            ("future", (*READS, NOW + timedelta(seconds=1)), "ok", 0, "stale"),
            ("last attempt failed", READS, "unreachable", 0, "last_attempt"),
            ("failure counter nonzero", READS, "ok", 1, "last_attempt"),
        )
        for label, times, result, failures, word in cases:
            with self.subTest(label=label):
                self.history(times, result=result, failures=failures)
                code, output = self.cli()
                self.assertEqual((code, output["checks"]["read_only_day"]), (int(word != "ok"), word))
        with closing(sqlite3.connect(self.cache_path)) as db, db:
            db.execute("UPDATE meta SET value='ok' WHERE key='lastResult'")
            db.execute("UPDATE meta SET value='0' WHERE key='failures'")
            db.execute("UPDATE meta SET value='DECOYMERCHANT' WHERE key='merchantId'")
        self.assertEqual(self.cli()[1]["checks"]["read_only_day"], "identity")

    def test_c3_token_by_stat_only(self):
        # C3: calling load_token or opening the path directly would touch bytes; reusing the read token must fail.
        def deny_token(opener):
            def check(path, *args, **kwargs):
                if not isinstance(path, int) and Path(os.fsdecode(path)).name in {self.token.name, "fake-read-file"}:
                    self.fail("attempt to open a token file")
                return opener(path, *args, **kwargs)
            return check

        with (mock.patch("builtins.open", side_effect=deny_token(builtins.open)),
              mock.patch("io.open", side_effect=deny_token(io.open)),
              mock.patch("os.open", side_effect=deny_token(os.open)),
              mock.patch.object(credential, "inspect", wraps=credential.inspect) as inspected):
            self.assertEqual(self.cli()[1]["checks"]["write_token_file"], "ok")
            inspected.assert_called_once_with(str(self.token))
            self.token.chmod(0o644)
            code, output = self.cli()
            self.assertEqual((code, output["checks"]["write_token_file"]), (1, "mode"))
            self.token.chmod(0o600)
            os.link(self.token, str(self.settings["tokenFile"]))
            code, output = self.cli()
            self.assertEqual((code, output["checks"]["write_token_file"]), (1, "same_file"))
        self.settings["tokenFile"] = self.settings["writeTokenFile"]
        self.save_host()
        code, output = self.cli()
        self.assertEqual((code, output["checks"]["write_token_file"]), (1, "same_file"))

    def test_c4_settings_cap_testitem(self):
        # C4: defaults cannot stand in for explicit settings; unrelated/reversed/draft changes don't prove TESTITEM.
        for key in ("writes", "liveApproved", "writeTokenFile"):
            with self.subTest(key=key):
                value = self.settings.pop(key)
                self.save_host()
                code, output = self.cli()
                self.assertEqual((code, output["checks"]["settings"]), (1, "missing"))
                self.settings[key] = value
        self.assertEqual(self.cli()[1]["checks"]["testitem"], "warn_missing_stock")
        self.add_change("set_stock", item="DECOYITEM")
        self.add_change("set_stock", status="intent")
        self.assertEqual(self.cli()[1]["checks"]["testitem"], "warn_missing_stock")
        self.add_change("set_stock")
        self.assertEqual(self.cli()[1]["checks"]["testitem"], "ok")
        for cap in (6, None):
            with self.subTest(cap=cap):
                if cap is None:
                    self.settings.pop("dailyWriteCap")
                else:
                    self.settings["dailyWriteCap"] = cap
                self.save_host()
                code, output = self.cli()
                self.assertEqual((code, output["checks"]["daily_cap"]), (1, "over_cap"))
        self.settings["dailyWriteCap"] = 5
        self.save_host()
        for changes in (
            [("set_hidden", {}), ("create_item", {})],
            [("create_item", {}), ("set_hidden", {"item": "DECOYITEM"})],
            [("create_item", {}), ("set_hidden", {"status": "draft"})],
            [("create_item", {"status": "failed"}), ("set_hidden", {})],
            [("create_item", {}), ("set_hidden", {"hidden": False})],
        ):
            with self.subTest(changes=changes):
                with self.journal.locked() as db:
                    db.executescript("DROP TABLE changes; CREATE TABLE changes("
                                     "code TEXT PRIMARY KEY, draft TEXT, sender TEXT, chat TEXT,"
                                     "expires REAL, status TEXT, day TEXT, result TEXT);")
                for kind, kwargs in changes:
                    self.add_change(kind, **kwargs)
                code, output = self.cli()
                self.assertEqual((code, output["checks"]["testitem"]), (1, "missing_proof"))

    def test_c5_read_only(self):
        # C5: a default SQLite open or Journal.locked would write; even a checkpointed WAL DB must not gain sidecars.
        with closing(sqlite3.connect(self.journal.path)) as db:
            self.assertEqual(db.execute("PRAGMA journal_mode=WAL").fetchone(), ("wal",))

        def snapshot():
            return {p: (p.stat().st_mtime_ns, p.read_bytes() if p.is_file() and p != self.token else None)
                    for p in (self.root, *self.root.rglob("*"))}

        def no_write(opener):
            def guard(path, mode="r", *args, **kwargs):
                if isinstance(mode, int):
                    allowed = not mode & (os.O_WRONLY | os.O_RDWR | os.O_CREAT | os.O_TRUNC | os.O_APPEND)
                else:
                    allowed = not any(flag in mode for flag in "wax+")
                self.assertTrue(allowed, "attempt to open a file for writing")
                return opener(path, mode, *args, **kwargs)
            return guard

        before = snapshot()
        with (mock.patch("builtins.open", side_effect=no_write(builtins.open)),
              mock.patch("io.open", side_effect=no_write(io.open)),
              mock.patch("os.open", side_effect=no_write(os.open)),
              mock.patch.object(sqlite3, "connect", wraps=sqlite3.connect) as connect):
            self.assertEqual(self.cli()[0], 0)
            self.assertEqual(connect.call_count, 2)
            for call in connect.call_args_list:
                self.assertTrue(call.args[0].startswith("file:"))
                self.assertIn("mode=ro", call.args[0])
                self.assertIs(call.kwargs.get("uri"), True)
        self.assertEqual(snapshot(), before)
        with closing(sqlite3.connect(self.journal.path)) as db, db:
            db.execute("UPDATE changes SET status='intent'")
            db.commit()
            before = snapshot()
            code, output = self.cli()
            self.assertEqual((code, output["checks"]["testitem"]), (2, "unreadable"))
            self.assertEqual(snapshot(), before)
