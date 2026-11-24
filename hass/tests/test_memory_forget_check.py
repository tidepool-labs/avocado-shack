"""Offline CLI contract tests using only synthetic SQLite stores."""

from contextlib import closing, redirect_stderr, redirect_stdout
import importlib.util
import io
import os
from pathlib import Path
import shutil
import sqlite3
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import patch

from hass.memory import TABLE


SCRIPT = Path(__file__).resolve().parents[2] / "scripts/hass/memory_forget_check.py"
STORE = "conversation.sqlite3"
INSERT = ("INSERT INTO memory(key, value, superseded_at, forgotten_at, kind, source, approved_change, created_at) "
          "VALUES (?, ?, ?, ?, 'fact', 'owner-approved:fixture-source', 'fixture-change', 'created')")
PASS = "PASS memory_forget_check"
FAIL = "FAIL memory_forget_check"


class MemoryForgetCheckTests(unittest.TestCase):
    def setUp(self):
        temp = tempfile.TemporaryDirectory()
        self.addCleanup(temp.cleanup)
        self.root = Path(temp.name).resolve()
        self.state = self.root / "fixture-state"
        self.state.mkdir()
        self.scratch = self.root / "fixture-temp"
        self.scratch.mkdir()
        self.store = self.state / STORE

    def seed(self, *rows, wal=False):
        with closing(sqlite3.connect(self.store)) as db, db:
            if wal:
                self.assertEqual(db.execute("PRAGMA journal_mode=WAL").fetchone(), ("wal",))
            db.execute(TABLE)
            db.executemany(INSERT, rows)

    def cli(self, *args, **env):
        return subprocess.run([sys.executable, "-B", str(SCRIPT), *map(str, args)], cwd=self.root,
                              capture_output=True, text=True, timeout=10,
                              env={**os.environ, "TMPDIR": str(self.scratch), **env})

    def run_check(self, state=None, **env):
        return self.cli("--state", self.state if state is None else state, **env)

    def assert_report(self, result, *lines, code=0):
        self.assertEqual(result.returncode, code)
        self.assertEqual(result.stderr, "")
        self.assertEqual(result.stdout, "\n".join((*lines, FAIL if code else PASS)) + "\n")
        self.assertEqual(list(self.scratch.iterdir()), [])

    def snapshot(self):
        # Include directories to catch transient writes that clean up their files.
        return {path.relative_to(self.state): (path.stat().st_mtime_ns,
                                                None if path.is_dir() else path.read_bytes())
                for path in [self.state, *self.state.rglob("*")]}

    def test_c1_full_pass(self):
        # Superseded, forgotten, and lookalike cost keys must not inflate active cost counts.
        self.seed(("cost.synthetic-product", "old", "corrected", None),
                  ("cost.synthetic-product", "new", None, None),
                  ("cost.forgotten", "", None, "forgotten"),
                  ("costlike.synthetic", "ordinary", None, None))
        self.assert_report(self.run_check(), "rows 4", "keys 3", "active 2", "forgotten-keys 1", "cost-keys-active 1")

    def test_c2_1_unsafe_state(self):
        # is_dir/is_file alone accept links; exists alone misses dangling links.
        state_link = self.root / "state-alias"
        state_link.symlink_to(self.state, target_is_directory=True)
        state_file = self.root / "state-file"
        state_file.touch()
        for state in (state_link, state_file, self.root / "missing-state"):
            with self.subTest(state=state.name):
                self.assert_report(self.run_check(state), "FAIL unsafe-state", code=1)
        for kind in ("directory", "link", "dangling"):
            with self.subTest(store=kind), tempfile.TemporaryDirectory(dir=self.root) as temp:
                state = Path(temp)
                store = state / STORE
                if kind == "directory":
                    store.mkdir()
                else:
                    store.symlink_to(state_file if kind == "link" else state / "missing")
                self.assert_report(self.run_check(state), "FAIL unsafe-state", code=1)

    def test_c2_2_unblanked(self):
        # Counting only forgotten rows, the first forget, or affected keys gives the wrong total.
        self.seed(("fixture-key", "residue", "corrected", None),
                  ("fixture-key", "", None, "first-forget"),
                  ("fixture-key", " ", None, "second-forget"),
                  ("fixture-key", "new fact", None, None),
                  ("other-key", "unrelated fact", None, None))
        self.assert_report(self.run_check(), "rows 5", "keys 2", "active 2", "forgotten-keys 1", "cost-keys-active 0",
                           "FAIL unblanked 2", code=1)

    def test_c2_3_multiple_active(self):
        # Count keys for the finding, but rows for the active and cost figures.
        self.seed(*[("cost.synthetic-duplicate", "duplicate", None, None)] * 3,
                  ("fixture-key", "old", "corrected", None), ("fixture-key", "new", None, None))
        self.assert_report(self.run_check(), "rows 5", "keys 2", "active 4", "forgotten-keys 0", "cost-keys-active 3",
                           "FAIL multiple-active 1", code=1)

    def test_c2_4_not_sqlite(self):
        # SQLite must not interpret unusable sidecars as absent or skip broken schemas.
        self.store.write_bytes(b"not a database")
        self.assert_report(self.run_check(), f"FAIL not-sqlite {STORE}", code=1)
        for column in ("id", "key", "value", "superseded_at", "forgotten_at"):
            with self.subTest(missing_column=column), tempfile.TemporaryDirectory(dir=self.root) as temp:
                with closing(sqlite3.connect(Path(temp) / STORE)) as db:
                    db.execute(TABLE)
                    db.execute(f"ALTER TABLE memory DROP COLUMN {column}" if column != "id" else
                               "ALTER TABLE memory RENAME COLUMN id TO wrong_id")
                self.assert_report(self.run_check(temp), f"FAIL not-sqlite {STORE}", code=1)
        for suffix in ("-wal", "-journal"):
            for kind in ("directory", "link", "dangling"):
                with self.subTest(suffix=suffix, kind=kind), tempfile.TemporaryDirectory(dir=self.root) as temp:
                    state = Path(temp)
                    with closing(sqlite3.connect(state / STORE)) as db:
                        db.execute(TABLE)
                    sidecar = state / (STORE + suffix)
                    if kind == "directory":
                        sidecar.mkdir()
                    else:
                        sidecar.symlink_to(self.store if kind == "link" else state / "missing")
                    self.assert_report(self.run_check(state), f"FAIL not-sqlite {STORE}", code=1)

    def test_c2_5_temp_unavailable(self):
        # No safe fallback: do not create a copy inside state or report bad SQLite.
        self.seed()
        spec = importlib.util.spec_from_file_location("memory_forget_check", SCRIPT)
        assert spec is not None and spec.loader is not None
        checker = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(checker)
        stdout, stderr = io.StringIO(), io.StringIO()
        before = self.snapshot()
        with patch.object(checker, "_temp_candidates", return_value=[self.state, self.root / "missing"]), \
                redirect_stdout(stdout), redirect_stderr(stderr):
            code = checker.main(["--state", str(self.state)])
        self.assertEqual(code, 1)
        self.assertEqual(stdout.getvalue(), f"FAIL temp-unavailable\n{FAIL}\n")
        self.assertEqual(stderr.getvalue(), "")
        self.assertEqual(self.snapshot(), before)

    def test_c3_usage_exit_2(self):
        # Usage errors are argparse errors, not ordinary findings or partial reports.
        for args in ((), ("--state",), ("--state", self.state, "--unknown", self.store)):
            with self.subTest(args=args):
                result = self.cli(*args)
                self.assertEqual(result.returncode, 2)
                self.assertEqual(result.stdout, "")
                self.assertIn("usage:", result.stderr)
                self.assertNotIn(str(self.root), result.stderr)

    def test_c4_read_only(self):
        # Opening the original WAL-mode database even read-only can create sidecars.
        self.seed(("fixture-key", "fixture-value", None, None), wal=True)
        self.assertEqual(list(self.state.iterdir()), [self.store])
        before = self.snapshot()
        self.assert_report(self.run_check(), "rows 1", "keys 1", "active 1", "forgotten-keys 0", "cost-keys-active 0")
        self.assertEqual(self.snapshot(), before)

    def test_c5_no_private_values(self):
        # Exercise both findings in one run; no private detail belongs in the diagnostic.
        self.seed(("fixture-key-canary", "fixture-forgotten-value", None, "forgotten"),
                  *[("cost.fixture-cost-canary", "fixture-active-value", None, None)] * 2)
        result = self.run_check()
        self.assert_report(result, "rows 3", "keys 2", "active 2", "forgotten-keys 1", "cost-keys-active 2",
                           "FAIL unblanked 1", "FAIL multiple-active 1", code=1)
        for canary in ("fixture-key-canary", "cost.fixture-cost-canary", "fixture-forgotten-value",
                       "fixture-active-value", "fixture-source", "fixture-change", str(self.root), str(self.store)):
            self.assertNotIn(canary, result.stdout + result.stderr)

    def test_c6_absent_pass(self):
        # Neither an absent file nor a valid database without the optional table is a finding.
        self.assert_report(self.run_check(), "memory absent")
        self.assertFalse(self.store.exists())
        with closing(sqlite3.connect(self.store)) as db:
            db.execute("CREATE TABLE other (id INTEGER)")
        self.assert_report(self.run_check(), "memory absent")

    def test_c7_forget_then_readd(self):
        # A corrected post-forget row is newer too; use the id cutoff, not active status.
        self.seed(("cost.synthetic-returning", "", "corrected", None),
                  ("cost.synthetic-returning", "", None, "forgotten"),
                  ("cost.synthetic-returning", "later value", "corrected", None),
                  ("cost.synthetic-returning", "latest value", None, None))
        self.assert_report(self.run_check(), "rows 4", "keys 1", "active 1", "forgotten-keys 1", "cost-keys-active 1")

    def test_c8_wal_rows_counted(self):
        # A committed WAL-only row disappears if the copy omits the WAL.
        producer = self.root / "fixture-producer.sqlite3"
        with closing(sqlite3.connect(producer)) as db:
            db.execute("PRAGMA journal_mode=WAL")
            db.execute("PRAGMA wal_autocheckpoint=0")
            db.execute(TABLE)
            self.assertEqual(db.execute("PRAGMA wal_checkpoint(TRUNCATE)").fetchone(), (0, 0, 0))
            with db:
                db.execute(INSERT, ("fixture-wal-key", "fixture-wal-value", None, None))
            shutil.copyfile(producer, self.store)
            self.assert_report(self.run_check(), "rows 0", "keys 0", "active 0", "forgotten-keys 0", "cost-keys-active 0")
            shutil.copyfile(str(producer) + "-wal", str(self.store) + "-wal")
        # A directory at -shm is deliberate: it must not be copied or validated.
        (self.state / (STORE + "-shm")).mkdir()
        before = self.snapshot()
        self.assert_report(self.run_check(), "rows 1", "keys 1", "active 1", "forgotten-keys 0", "cost-keys-active 0")
        self.assertEqual(self.snapshot(), before)

    def test_c9_tmpdir_inside_input(self):
        # gettempdir writes a probe; creating and cleaning scratch in state also changes its mtime.
        self.seed(("fixture-key", "fixture-value", None, None))
        nested = self.state / "nested"
        nested.mkdir()
        alias = self.root / "alias"
        alias.symlink_to(nested, target_is_directory=True)
        before = self.snapshot()
        for tmpdir in (self.state, nested, alias):
            with self.subTest(tmpdir=tmpdir.name):
                result = self.run_check(TMPDIR=str(tmpdir), TEMP=str(self.scratch), TMP="")
                self.assert_report(result, "rows 1", "keys 1", "active 1", "forgotten-keys 0", "cost-keys-active 0")
                self.assertEqual(self.snapshot(), before)
