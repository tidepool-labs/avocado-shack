"""RF1750-3 tests: hass/retention.py refuses a database that is not a regular file (FIFO, folder, socket, link).

The refusal is exit 2 with stdout empty, decided by lstat before anything opens, so a FIFO never blocks the report and
the state dir is left exactly as it was. A missing database stays "unavailable" (exit 1). Reuses the test_retention
temp fixture (never the real private state). Run: python3 -B -m unittest hass.tests.test_retention_paths -v
"""
import contextlib, hashlib, json, os, socket, stat, threading, unittest  # noqa: E401
from pathlib import Path

from hass.tests import test_retention as base

BOUND_S = 5


def tree(root) -> dict:
    """Every path under root -> (file type, sha256 of a regular file's bytes); lstat only, so a FIFO is never read."""
    out = {}
    for dirpath, dirs, files in os.walk(root):
        for name in (*dirs, *files):
            path = os.path.join(dirpath, name)
            kind = stat.S_IFMT(os.lstat(path).st_mode)
            digest = hashlib.sha256(Path(path).read_bytes()).hexdigest() if kind == stat.S_IFREG else None
            out[path] = (kind, digest)
    return out


class RetentionPathsTest(unittest.TestCase):
    setUp, run_main = base.RetentionTest.setUp, base.RetentionTest.run_main

    def bounded(self, *args):
        """run_main in a thread: a regression that opens a FIFO fails here instead of hanging the suite."""
        box = {}
        worker = threading.Thread(target=lambda: box.update(result=self.run_main(*args)), daemon=True)
        worker.start()
        worker.join(BOUND_S)
        if worker.is_alive():
            for name in (base.retention.CONV, base.retention.INBOX):  # give the blocked reader a writer, then EOF
                path = self.state / name
                if path.is_fifo(): os.close(os.open(path, os.O_WRONLY | os.O_NONBLOCK))
            worker.join(BOUND_S)
            self.fail(f"report still running after {BOUND_S}s: it opened a FIFO")
        return box["result"]

    def assert_unsafe(self, name, *extra):
        before = tree(self.tmp)
        code, out, err = self.bounded("--state", str(self.state), "--days", str(base.DAYS), *extra)
        self.assertEqual((code, out), (2, ""), err)
        self.assertIn("retention: unsafe:", err)
        self.assertIn(name, err)
        self.assertEqual(tree(self.tmp), before)  # nothing created, changed or removed
        return err

    def replace(self, name):
        (self.state / name).unlink()
        return self.state / name

    @unittest.skipUnless(hasattr(os, "mkfifo"), "no FIFOs on this platform")
    def test_fifo_inbox_is_refused_without_opening_it(self):
        os.mkfifo(self.replace("inbox.sqlite3"), 0o600)
        self.assert_unsafe("inbox.sqlite3")

    @unittest.skipUnless(hasattr(os, "mkfifo"), "no FIFOs on this platform")
    def test_fifo_conversation_is_refused_too(self):
        os.mkfifo(self.replace("conversation.sqlite3"), 0o600)
        self.assert_unsafe("conversation.sqlite3")

    def test_folder_conversation_is_refused(self):
        self.replace("conversation.sqlite3").mkdir(mode=0o700)
        self.assert_unsafe("conversation.sqlite3")

    def test_dangling_symlink_conversation_is_refused(self):
        self.replace("conversation.sqlite3").symlink_to(self.tmp / "nowhere.sqlite3")
        self.assert_unsafe("conversation.sqlite3")
        self.assertFalse((self.tmp / "nowhere.sqlite3").exists())  # the link was never followed into a new file

    @unittest.skipUnless(hasattr(socket, "AF_UNIX"), "no Unix sockets on this platform")
    def test_socket_inbox_is_refused(self):
        sock = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
        self.addCleanup(sock.close)
        path = self.replace("inbox.sqlite3")
        # Relative bind: an absolute TMPDIR-based path can exceed sun_path (~107 bytes).
        with contextlib.chdir(path.parent):
            sock.bind(path.name)
        self.assert_unsafe("inbox.sqlite3")

    def test_both_missing_stay_unavailable_exit_1(self):
        for name in ("inbox.sqlite3", "conversation.sqlite3"): self.replace(name)
        code, out, err = self.bounded("--state", str(self.state), "--days", str(base.DAYS))
        doc = json.loads(out)
        self.assertEqual((code, doc["inbox"], doc["messages"], err), (1, "unavailable", "unavailable", ""))
        self.assertFalse(any((self.state / n).exists() for n in ("inbox.sqlite3", "conversation.sqlite3")))

    def test_regular_databases_give_the_unchanged_report(self):
        oldest = base.OLD.date().isoformat()
        want = {"days": base.DAYS, "cutoff": base.AT.isoformat(),
                "inbox": {"done": 1, "history": 1, "pending": 0, "oldest": oldest},
                "messages": {"rows": 1, "oldest": oldest}, "outbox": {"sent": 1, "unsent": 1, "oldest": oldest},
                "drafts": {"closed": 2, "open": 1}, "approvals": {"rows": 0, "oldest": None},
                "memory": {"forgotten": 0, "superseded": 0, "oldest": None}, "screenshots": {"files": 1, "bytes": 7},
                "media": None, "backups": None, "webOrphans": None, "deletes": 0}
        code, out, err = self.bounded("--state", str(self.state), "--days", str(base.DAYS))
        self.assertEqual((code, out, err), (0, json.dumps(want) + "\n", ""))

    @unittest.skipUnless(hasattr(os, "mkfifo"), "no FIFOs on this platform")
    def test_bad_days_with_a_fifo_is_still_a_usage_error(self):
        os.mkfifo(self.replace("inbox.sqlite3"), 0o600)
        for days in ("0", "x"):
            code, out, err = self.bounded("--state", str(self.state), "--days", days)
            self.assertEqual((code, out), (2, ""), days)
            self.assertIn("--days must be a whole number", err)
            self.assertNotIn("unsafe", err)
