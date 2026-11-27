"""RF1920-1 (H16/H20) tests: editor._writer_lock opens <state>/writer.lock only as a regular, non-link file.

A symlink (dangling, to a file or to a folder), FIFO, socket or folder there is UnsafeState "writer lock is not a
regular file" (CLI unsafe-state, exit 2), and nothing is created or changed through a link. Temp state dirs as
test_editor builds them. Run: python3 -m unittest hass.tests.test_writer_lock_entry -v
"""

import contextlib, io, json, os, shutil, signal, socket, stat, tempfile, time, unittest  # noqa: E401
from pathlib import Path
from unittest.mock import patch

from hass import editor, install, statebackup
from hass.tests.test_editor import HOURS, NEW_HOURS, EditorTestCase, _req

MSG = "writer lock is not a regular file"


class WriterLockEntryTests(EditorTestCase):
    def setUp(self):
        self.r = self.repo()
        self.lock, self.tmp = self.r.state / "writer.lock", self.r.state.parent
        self.draft = self.r.prepare(_req((HOURS, {"hours": NEW_HOURS})))["draft"]
        self.head = self.r.head()

    def assertUnsafe(self, call):
        signal.signal(signal.SIGALRM, lambda *_: self.fail("writer lock open blocked"))
        self.addCleanup(signal.signal, signal.SIGALRM, signal.SIG_DFL)
        signal.alarm(5)
        start = time.monotonic()
        try:
            with self.assertRaises(editor.UnsafeState) as caught:
                call()
        finally:
            signal.alarm(0)
        self.assertLess(time.monotonic() - start, 5)
        self.assertEqual(str(caught.exception), MSG)
        self.assertNotIn(str(self.tmp), str(caught.exception))
        self.assertEqual((self.r.head(), self.r.status()), (self.head, ""))  # nothing applied

    def apply(self):
        return self.r.apply(self.draft)

    def recover(self):
        return editor.recover(state=str(self.r.state))

    def install(self):
        return install.install(self.draft["change_id"], state=str(self.r.state))

    def test_link_to_a_missing_outside_path_is_refused_and_never_created(self):
        target = self.tmp / "outside.lock"
        self.lock.symlink_to(target)
        for call in (self.apply, self.recover, self.install):
            with self.subTest(call=call.__name__):
                self.assertUnsafe(call)
                self.assertFalse(os.path.lexists(target))  # was: created by O_CREAT through the link
                self.assertTrue(self.lock.is_symlink())

    def test_link_to_an_existing_outside_file_is_refused_and_the_file_unchanged(self):
        target = self.tmp / "outside.lock"
        target.write_bytes(b"other state dir lock\n")
        os.chmod(target, 0o644)
        os.utime(target, ns=(1_700_000_000_000_000_000, 1_700_000_000_000_000_000))
        before = os.stat(target)
        self.lock.symlink_to(target)
        for call in (self.apply, self.recover, self.install):
            with self.subTest(call=call.__name__):
                self.assertUnsafe(call)
        after = os.stat(target)
        self.assertEqual(target.read_bytes(), b"other state dir lock\n")
        self.assertEqual((after.st_mtime_ns, after.st_mode), (before.st_mtime_ns, before.st_mode))

    def test_link_to_a_folder_is_refused(self):
        (self.tmp / "outside-dir").mkdir()
        self.lock.symlink_to(self.tmp / "outside-dir", target_is_directory=True)
        self.assertUnsafe(self.apply)
        self.assertEqual(os.listdir(self.tmp / "outside-dir"), [])

    @unittest.skipUnless(hasattr(os, "mkfifo"), "needs os.mkfifo")
    def test_fifo_is_refused_quickly_by_apply_recover_and_install(self):
        os.mkfifo(self.lock, 0o600)
        for call in (self.apply, self.recover, self.install):
            with self.subTest(call=call.__name__):
                self.assertUnsafe(call)
                self.assertTrue(stat.S_ISFIFO(os.lstat(self.lock).st_mode))

    @unittest.skipUnless(hasattr(socket, "AF_UNIX"), "needs unix sockets")
    def test_socket_is_refused(self):
        self.assert_socket_refused()

    def assert_socket_refused(self):
        sock = socket.socket(socket.AF_UNIX)
        self.addCleanup(sock.close)
        # Relative bind: an absolute TMPDIR-based path can exceed sun_path (~107 bytes).
        with contextlib.chdir(self.lock.parent):
            sock.bind(self.lock.name)
        self.assertTrue(stat.S_ISSOCK(os.lstat(self.lock).st_mode))
        self.assertUnsafe(self.apply)

    @unittest.skipUnless(hasattr(socket, "AF_UNIX"), "needs unix sockets")
    def test_socket_is_refused_under_a_long_tmpdir(self):
        # A deep TMPDIR (e.g. a nested shard/stage scratch) must not break or skip the socket case.
        deep = Path(tempfile.mkdtemp(prefix="hass-long-tmpdir-"))
        self.addCleanup(shutil.rmtree, deep, True)
        deep = deep / ("d" * 60)
        deep.mkdir()
        with patch.object(tempfile, "tempdir", str(deep)):
            self.r = self.repo()
        self.lock, self.tmp = self.r.state / "writer.lock", self.r.state.parent
        self.draft = self.r.prepare(_req((HOURS, {"hours": NEW_HOURS})))["draft"]
        self.head = self.r.head()
        self.assertGreater(len(os.fsencode(self.lock)), 107)  # too long for an absolute bind
        self.assert_socket_refused()

    def test_folder_is_one_unsafe_state_cli_line_not_io_error(self):
        self.lock.mkdir(mode=0o700)
        for argv in (["apply", self.draft["change_id"], "--hash", self.draft["draft_hash"]], ["recover"]):
            with self.subTest(cmd=argv[0]):
                out, err = io.StringIO(), io.StringIO()
                with contextlib.redirect_stdout(out), contextlib.redirect_stderr(err):
                    code = editor.main([*argv, "--state", str(self.r.state)])
                self.assertEqual((code, out.getvalue().count("\n")), (2, 1), out.getvalue())
                self.assertEqual(json.loads(out.getvalue()), {"result": "unsafe-state", "problems": [MSG]})
                self.assertNotIn("Traceback", out.getvalue() + err.getvalue())
                self.assertNotIn(str(self.tmp), out.getvalue())
        self.assertEqual(os.listdir(self.lock), [])

    def test_missing_lock_is_created_0600_and_a_second_holder_is_busy(self):
        self.assertFalse(os.path.lexists(self.lock))
        self.assertEqual(self.apply()["result"], "applied")
        st = os.lstat(self.lock)
        self.assertTrue(stat.S_ISREG(st.st_mode))
        self.assertEqual(stat.S_IMODE(st.st_mode), 0o600)
        other = self.r.prepare(_req((HOURS, {"hours": ["Open daily 8am–8pm"]})))["draft"]
        head = self.r.head()
        with editor._writer_lock(self.r.state) as held:
            self.assertTrue(held)
            self.assertEqual(self.r.apply(other)["result"], "busy")
            self.assertEqual(self.recover(), {"result": "busy"})
            self.assertEqual(install.install(other["change_id"], state=str(self.r.state)), {"result": "busy"})
        self.assertEqual(self.r.head(), head)
        self.assertEqual(self.r.apply(other)["result"], "applied")  # a regular lock keeps working

    def test_statebackup_create_still_names_the_linked_lock(self):
        out, target = self.tmp / "backups", self.tmp / "outside.lock"
        out.mkdir(mode=0o700)
        self.lock.symlink_to(target)
        got = statebackup.create(str(self.r.state), str(out))
        self.assertEqual(got["result"], "refused", got)
        self.assertIn("symlink: writer.lock", got["problems"])
        self.assertEqual((os.listdir(out), os.path.lexists(target)), ([], False))


if __name__ == "__main__":
    unittest.main()
