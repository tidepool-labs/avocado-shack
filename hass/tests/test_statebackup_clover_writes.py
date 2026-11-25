"""HCI-16: the state backup carries the till write state (journal, bundles, link table and receipts).

Fixtures only: synthetic rows in throwaway sqlite stores under the test's temp dir, no till, no token, no network
(sockets are patched through NoNetwork; the test fails if one is touched).
"""

import contextlib, fcntl, hashlib, io, json, os, shutil, sqlite3, threading  # noqa: E401
from datetime import timedelta
from pathlib import Path
from unittest import mock

from hass import statebackup
from hass.editor import UnsafeState
from hass.tests.test_clover_client import NoNetwork
from hass.tests.test_statebackup import STAMP, BackupTestCase, tree

JOURNAL, BUNDLES, LINKS, CACHE = statebackup.JOURNAL, statebackup.BUNDLES, statebackup.LINKS, statebackup.CLOVER
RECEIPT = "clover/receipts/2026-11-02-0a1b2c3d.json"
LOCKS = ("clover/journal.lock", "clover/bundles.lock")
TILL = (JOURNAL, BUNDLES, LINKS, RECEIPT)
TABLES = {JOURNAL: "changes", BUNDLES: "bundles"}

class TillWriteStateBackupTests(NoNetwork, BackupTestCase):
    def make_till(self, locks=True):
        state = self.repo.state
        (state / "clover" / "receipts").mkdir(parents=True, exist_ok=True)
        for folder in ("clover", "clover/receipts"): os.chmod(state / folder, 0o700)
        for rel, table in TABLES.items():
            with contextlib.closing(sqlite3.connect(state / rel)) as db, db:
                db.execute(f"CREATE TABLE {table} (code TEXT PRIMARY KEY, row TEXT)")
                db.execute(f"INSERT INTO {table} VALUES ('a1b2c3d4', 'synthetic {table} row')")
        (state / LINKS).write_text(json.dumps({"synthetic-product": {"cloverId": "FAKE-ITEM-1"}}), "utf-8")
        (state / RECEIPT).write_text(json.dumps({"code": "0a1b2c3d", "state": "applied"}) + "\n", "utf-8")
        for lock in LOCKS if locks else (): (state / lock).write_bytes(b"")
        for rel in (*TILL, *(LOCKS if locks else ())): os.chmod(state / rel, 0o600)

    def rows(self, path, table):
        with contextlib.closing(sqlite3.connect(f"{Path(path).as_uri()}?mode=ro", uri=True)) as db:
            return db.execute(f"SELECT code, row FROM {table} ORDER BY code").fetchall()

    def backup_at(self, minutes=0):
        made = statebackup.create(str(self.repo.state), str(self.bk), now=STAMP + timedelta(minutes=minutes))
        self.assertEqual(made["result"], "ok", made)
        return Path(made["backup"])

    def cli(self, *argv):  # (exit code, the last JSON line), in process
        buf = io.StringIO()
        with contextlib.redirect_stdout(buf): code = statebackup.main([str(a) for a in argv])
        return code, json.loads(buf.getvalue().splitlines()[-1])

    def assert_till_copy(self, root, source=None):
        """Every till file under `root` has the source's content, 0600 files, 0700 folders, and no lock file came along."""
        source = source or self.repo.state
        for rel in TILL:
            self.assertEqual((root / rel).stat().st_mode & 0o777, 0o600, rel)
            if rel in TABLES: self.assertEqual(self.rows(root / rel, TABLES[rel]), self.rows(source / rel, TABLES[rel]), rel)
            else: self.assertEqual((root / rel).read_bytes(), (source / rel).read_bytes(), rel)
        for folder in ("clover", "clover/receipts"): self.assertEqual((root / folder).stat().st_mode & 0o777, 0o700, folder)
        for lock in LOCKS: self.assertFalse(os.path.lexists(root / lock), lock)

    # Contract C1: create snapshots journal + bundles under each store's own flock and copies links.json and every
    # receipt, never a lock file, with 0700 folders and 0600 files. Bug caught: the stores are snapshotted without the
    # flock (a torn copy of a write in flight), a store or the receipts are left out, or a lock file is copied.
    def test_c1_create_carries(self):
        self.make_till()
        seen, real = [], statebackup._snapshot
        def spy(src, dst):
            lock = Path(src).with_suffix(".lock")
            if lock.exists():  # only the till stores have a lock file next to them
                fd = os.open(lock, os.O_RDWR)
                try:
                    with self.assertRaises(BlockingIOError): fcntl.flock(fd, fcntl.LOCK_EX | fcntl.LOCK_NB)  # held by create
                finally: os.close(fd)
                seen.append(Path(src).name)
            real(src, dst)
        with mock.patch.object(statebackup, "_snapshot", spy):
            code, made = self.cli("create", "--state", self.repo.state, "--out", self.bk)
        self.assertEqual((code, made["result"]), (0, "ok"), made)
        self.assertEqual(sorted(seen), ["bundles.sqlite3", "journal.sqlite3"])
        backup = Path(made["backup"])
        self.assertLessEqual(set(TILL), set(self.files(backup)))
        self.assertFalse([rel for rel in self.files(backup) if rel.endswith(".lock")])
        self.assertEqual(made["files"], len(self.files(backup)))
        self.assert_till_copy(backup)
        self.assertEqual(self.cli("verify", backup), (0, {"result": "ok", "files": len(self.files(backup))}))
        new, drilled = self.tmp / "restored", self.tmp / "drilled"
        self.assertEqual(self.cli("restore", backup, "--into", new, "--worktree", self.drill_wt)[0], 0)
        self.assert_till_copy(new)
        code, out = self.cli("drill", backup, "--into", drilled, "--worktree", self.drill_wt)
        self.assertEqual((code, out["result"]), (0, "ok"), out)
        self.assert_till_copy(drilled)

    # Contract C1 (lock files are skipped): a state whose till has only started (lock files, no store yet) backs up as
    # if there were no clover folder. Bug caught: the lock files are copied or the scan refuses them as unknown.
    def test_c1_lock_files_alone_are_skipped(self):
        (self.repo.state / "clover").mkdir(mode=0o700)
        for lock in LOCKS: (self.repo.state / lock).write_bytes(b"")
        for lock in LOCKS: os.chmod(self.repo.state / lock, 0o600)
        backup = self.backup_at()
        self.assertFalse([rel for rel in self.files(backup) if rel.startswith("clover")])
        self.assertEqual(statebackup.verify(str(backup))["result"], "ok")

    # Contract C1 (while holding each store's own flock): a write in flight must not be copied half done. Bug caught:
    # create waits forever or snapshots anyway; here it answers `busy`, exits 1 and leaves no partial backup behind.
    def test_c1_busy_while_a_till_write_holds_the_lock(self):
        self.make_till()
        fd = os.open(self.repo.state / "clover/bundles.lock", os.O_RDWR)
        self.addCleanup(os.close, fd)
        fcntl.flock(fd, fcntl.LOCK_EX)
        with mock.patch.object(statebackup, "LOCK_WAIT", 0.1):
            code, out = self.cli("create", "--state", self.repo.state, "--out", self.bk)
        self.assertEqual((code, out), (1, {"result": "busy", "problems": [f"till store in use: {BUNDLES}"]}))
        self.assertEqual(os.listdir(self.bk), [])

    # Contract C1 (stray sidecar vs writer in flight): a till writer holds the store's flock for its whole transaction,
    # and sqlite's rollback journal (<store>-journal) exists only during it. Bug caught: the scan refuses that sidecar
    # before the flock is tried, so a write in flight answers `refused` instead of `busy`, or a finished write is lost.
    def test_c1_journal_sidecar_is_judged_under_the_store_lock(self):
        self.make_till()
        state = self.repo.state
        for store in (JOURNAL, BUNDLES):
            sidecar, lock = state / (store + "-journal"), state / (store[:-len("sqlite3")] + "lock")
            with self.subTest(store=store, case="writer holds the lock past LOCK_WAIT"):
                sidecar.write_bytes(b"hot")
                fd = os.open(lock, os.O_RDWR)
                fcntl.flock(fd, fcntl.LOCK_EX)
                try:
                    with mock.patch.object(statebackup, "LOCK_WAIT", 0.1):
                        code, out = self.cli("create", "--state", state, "--out", self.bk)
                finally: os.close(fd)
                self.assertEqual((code, out), (1, {"result": "busy", "problems": [f"till store in use: {store}"]}))
                self.assertEqual(os.listdir(self.bk), [])
            with self.subTest(store=store, case="writer finishes inside LOCK_WAIT"):
                fd = os.open(lock, os.O_RDWR)
                fcntl.flock(fd, fcntl.LOCK_EX)
                def finish(fd=fd, sidecar=sidecar):
                    sidecar.unlink()  # a committed write deletes its journal, then releases the lock
                    os.close(fd)
                timer = threading.Timer(0.3, finish)
                timer.start()
                code, out = self.cli("create", "--state", state, "--out", self.bk)
                timer.join()
                self.assertEqual((code, out["result"]), (0, "ok"), out)
                self.assertFalse([rel for rel in self.files(Path(out["backup"])) if rel.endswith("-journal")])
                self.assert_till_copy(Path(out["backup"]))
            with self.subTest(store=store, case="no writer: the sidecar is a stray"):
                sidecar.write_bytes(b"hot")
                self.assertEqual(self.cli("create", "--state", state, "--out", self.bk),
                                 (1, {"result": "refused", "problems": [f"unknown entry: clover/{sidecar.name}"]}))
                sidecar.unlink()
            shutil.rmtree(self.bk); self.bk.mkdir(mode=0o700)  # noqa: E702 - one backup per stamp

    # Contract C1 (a stray with no store to coordinate with): a sidecar whose store is absent has no writer to wait for.
    # Bug caught: the lock coordination also swallows it (or creates the lock file for a till that never wrote).
    def test_c1_journal_sidecar_without_its_store_is_refused(self):
        self.make_till(locks=False)
        (self.repo.state / BUNDLES).unlink()
        (self.repo.state / "clover/bundles.sqlite3-journal").write_bytes(b"x")
        self.assertEqual(self.cli("create", "--state", self.repo.state, "--out", self.bk),
                         (1, {"result": "refused", "problems": ["unknown entry: clover/bundles.sqlite3-journal"]}))
        self.assertFalse((self.repo.state / "clover/bundles.lock").exists())

    # Contract C1 (own flock, private modes): a lock file that is not a private regular file is the writer's own refusal
    # too. Bug caught: create locks and trusts a world-writable lock file another user could hold forever.
    def test_c1_unsafe_lock_file_stops_the_backup(self):
        self.make_till()
        os.chmod(self.repo.state / LOCKS[0], 0o666)
        with self.assertRaises(UnsafeState): statebackup.create(str(self.repo.state), str(self.bk))
        self.assertEqual(os.listdir(self.bk), [])

    # Contract C2: everything else in clover/ and clover/receipts/ stays refused by name. Bug caught: the new names are
    # matched by prefix or loosely, so a -journal/-wal sidecar, a temp file, a folder or a link slips into a backup.
    def test_c2_unknown_refused(self):
        self.make_till()
        state = self.repo.state
        def touch(path): path.write_text("x", "utf-8")
        def link(path): path.symlink_to(state / LINKS)
        cases = [(rel, touch, "unknown entry") for rel in (
            "clover/journal.sqlite3-journal", "clover/journal.sqlite3-wal", "clover/bundles.sqlite3-journal",
            "clover/bundles.sqlite3-wal", "clover/links.json.bak", "clover/.link-tmp", "clover/notes.txt",
            "clover/receipts/notes.txt", "clover/receipts/2026-11-02-0A1B2C3D.json", "clover/receipts/2026-11-02-0a1b2c3.json",
            "clover/receipts/2026-11-02-0a1b2c3d.json-journal", "clover/receipts/tmpab12cd34",
            "clover/receipts/2026-1-02-0a1b2c3d.json")]
        cases += [("clover/reports", lambda p: p.mkdir(), "unknown entry"), ("clover/receipts/nested", lambda p: p.mkdir(), "unknown entry"),
                  ("clover/other-link", link, "symlink"), ("clover/receipts/2026-11-03-aaaaaaaa.json", link, "symlink")]
        for rel, how, kind in cases:
            with self.subTest(rel=rel):
                how(state / rel)
                self.assertEqual(self.cli("create", "--state", state, "--out", self.bk),
                                 (1, {"result": "refused", "problems": [f"{kind}: {rel}"]}))
                (state / rel).rmdir() if (state / rel).is_dir() and not (state / rel).is_symlink() else (state / rel).unlink()
        with self.subTest(rel="lock as a link"):  # a symlinked lock is refused, not followed and not skipped
            (state / LOCKS[1]).unlink()
            link(state / LOCKS[1])
            self.assertEqual(statebackup.create(str(state), str(self.bk)), {"result": "refused", "problems": [f"symlink: {LOCKS[1]}"]})
            (state / LOCKS[1]).unlink()
            (state / LOCKS[1]).write_bytes(b"")
            os.chmod(state / LOCKS[1], 0o600)
        with self.subTest(rel="receipts as a link"):
            (state / "clover/receipts").rename(state / "clover/receipts-real")
            (state / "clover/receipts").symlink_to(state / "clover/receipts-real")
            self.assertEqual(statebackup.create(str(state), str(self.bk))["problems"], ["symlink: clover/receipts", "unknown entry: clover/receipts-real"])
            (state / "clover/receipts").unlink()
            (state / "clover/receipts-real").rename(state / "clover/receipts")
        self.assertEqual(os.listdir(self.bk), [])  # every refusal left nothing behind
        self.assertEqual(statebackup.create(str(state), str(self.bk))["result"], "ok")

    # Contract C3: verify hashes and mode-checks the new files and runs the sqlite integrity check on both new stores.
    # Bug caught: the new rels are listed but skipped by verify, so a changed byte, a loose mode or a corrupt store
    # (consistent with its manifest hash) passes and a restore later loses the undo journal.
    def test_c3_verify(self):
        self.make_till()
        backup = self.backup_at()
        self.assertEqual(self.cli("verify", backup), (0, {"result": "ok", "files": len(self.files(backup))}))
        for rel in TILL:
            path, good = backup / rel, (backup / rel).read_bytes()
            with self.subTest(changed_byte=rel):
                path.write_bytes(good[:-1] + bytes([good[-1] ^ 1]))
                self.assertEqual(self.cli("verify", backup), (1, {"result": "corrupt", "problems": [f"hash mismatch: {rel}"]}))
                path.write_bytes(good)
            with self.subTest(mode=rel):
                os.chmod(path, 0o644)
                self.assertEqual(self.cli("verify", backup), (1, {"result": "corrupt", "problems": [f"mode: {rel}"]}))
                os.chmod(path, 0o600)
        with self.subTest(mode="receipts folder"):
            os.chmod(backup / "clover/receipts", 0o755)
            self.assertEqual(statebackup.verify(str(backup)), {"result": "corrupt", "problems": ["mode: clover/receipts"]})
            os.chmod(backup / "clover/receipts", 0o700)
        manifest = backup / statebackup.MANIFEST
        doc, garbage = json.loads(manifest.read_text("utf-8")), b"not a database" * 64
        for rel in TABLES:
            with self.subTest(integrity=rel):
                path, good = backup / rel, (backup / rel).read_bytes()
                path.write_bytes(garbage)
                manifest.write_text(json.dumps({**doc, "files": {**doc["files"], rel: hashlib.sha256(garbage).hexdigest()}}), "utf-8")
                self.assertEqual(self.cli("verify", backup), (1, {"result": "corrupt", "problems": [f"integrity check failed: {rel}"]}))
                path.write_bytes(good)
                manifest.write_text(json.dumps(doc), "utf-8")
        with self.subTest(extra="a lock file in the backup"):
            (backup / LOCKS[0]).write_bytes(b"")
            os.chmod(backup / LOCKS[0], 0o600)
            self.assertEqual(statebackup.verify(str(backup)), {"result": "corrupt", "problems": [f"unlisted: {LOCKS[0]}"]})
            (backup / LOCKS[0]).unlink()
        self.assertEqual(statebackup.verify(str(backup))["result"], "ok")

    # Contract C4: restore and drill put the till files into a NEW dir with the same modes and never write into an
    # existing one; diff lists them like other files. Bug caught: restore skips the clover folder or the receipts
    # sub-folder (a restore loses the undo journal), gives them default modes, or writes into a dir that exists.
    def test_c4_restore(self):
        self.make_till()
        old = self.backup_at()
        new, drilled = self.tmp / "restored", self.tmp / "drilled"
        code, out = self.cli("restore", old, "--into", new, "--worktree", self.drill_wt)
        self.assertEqual((code, out["result"]), (0, "ok"), out)
        self.assertEqual(sorted(p for p in tree(new) if p.startswith("clover")), sorted(["clover", "clover/receipts", *TILL]))
        self.assert_till_copy(new)
        code, out = self.cli("drill", old, "--into", drilled, "--worktree", self.drill_wt)
        self.assertEqual((code, out["result"]), (0, "ok"), out)
        self.assertEqual(sorted(p for p in tree(drilled) if p.startswith("clover")), sorted(["clover", "clover/receipts", *TILL]))
        self.assert_till_copy(drilled)
        for existing in (new, drilled):  # a dir that exists is never written into
            before = tree(existing)
            self.assertEqual(self.cli("restore", old, "--into", existing, "--worktree", self.drill_wt),
                             (1, {"result": "refused", "problems": ["restore dir already exists; left untouched"]}))
            code, out = self.cli("drill", old, "--into", existing, "--worktree", self.drill_wt)
            self.assertEqual((code, out["result"], out["step"]), (1, "refused", "restore"))
            self.assertEqual(tree(existing), before)
        # diff: the till files are listed by rel and hash like every other file.
        with contextlib.closing(sqlite3.connect(self.repo.state / JOURNAL)) as db, db:
            db.execute("INSERT INTO changes VALUES ('b2c3d4e5', 'synthetic second row')")
        (self.repo.state / "clover/receipts/2026-11-03-1b2c3d4e.json").write_text("{}\n", "utf-8")
        os.chmod(self.repo.state / "clover/receipts/2026-11-03-1b2c3d4e.json", 0o600)
        newer = self.backup_at(5)
        extra = "clover/receipts/2026-11-03-1b2c3d4e.json"
        code, out = self.cli("diff", old, newer)
        self.assertEqual(code, 0)
        self.assertEqual(out["added"], [extra])
        self.assertEqual(out["removed"], [])
        self.assertIn(JOURNAL, out["changed"])
        self.assertFalse({LINKS, RECEIPT} & set(out["changed"]))
        code, back = self.cli("diff", newer, old)  # what a restore of OLD would lose: the newer receipt
        self.assertEqual((code, back["removed"]), (0, [extra]))

    # Contract C5: a state with no clover folder, an empty one or only cache.sqlite3 backs up exactly as before.
    # Bug caught: the till scan lists stores that are not there, or the lock code creates journal.lock/bundles.lock
    # in a state that never had a till write.
    def test_c5_unchanged(self):
        state = self.repo.state
        base = set(self.files(self.backup_at(0)))
        self.assertFalse([rel for rel in base if rel.startswith("clover")])
        self.assertFalse((self.bk / f"hass-state-{STAMP.strftime('%Y%m%dT%H%M%SZ')}" / "clover").exists())
        (state / "clover").mkdir(mode=0o700)  # empty folder: nothing to carry
        empty = self.backup_at(1)
        self.assertEqual(set(self.files(empty)), base)
        self.assertFalse((empty / "clover").exists())
        with contextlib.closing(sqlite3.connect(state / CACHE)) as db, db:  # cache only
            db.execute("CREATE TABLE item (id TEXT, name TEXT)")
            db.execute("INSERT INTO item VALUES ('A1', 'synthetic one')")
        os.chmod(state / CACHE, 0o600)
        cache_only = self.backup_at(2)
        self.assertEqual(set(self.files(cache_only)), base | {CACHE})
        self.assertEqual(os.listdir(state / "clover"), ["cache.sqlite3"])  # no lock file was made for a till that never wrote
        self.assertEqual(sorted(p for p in tree(cache_only) if p.startswith("clover")), ["clover", CACHE])
        self.assertEqual(self.cli("verify", cache_only), (0, {"result": "ok", "files": len(base) + 1}))
        new = self.tmp / "restored"
        self.assertEqual(self.cli("restore", cache_only, "--into", new, "--worktree", self.drill_wt)[0], 0)
        self.assertEqual(sorted(p for p in tree(new) if p.startswith("clover")), ["clover", CACHE])
