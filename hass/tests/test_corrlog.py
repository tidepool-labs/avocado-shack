"""HASS-VOICE-1 tests: the correspondence log (hass/corrlog.py) and the rows the conversation writes into it.

1. The log itself: append-only day files, row fields, kinds, reason codes, the 80-character excerpt with numbers, addresses
   and links blanked, 90-day retention, never raising on a bad folder, the last-ten list and the weekly line.
2. The moments that write a row: a slow reply, a question asked again, Mike saying no or "that's wrong", a held-back message.
3. G only: `problems` and `weekly` answer only the numbers in settings gSenders; gSenders can never overlap ownerSenders;
   Mike's morning report never carries the weekly line.
Synthetic only: temporary folders, throwaway repo, injected clock; nothing is sent.
Run: python3 -B -m unittest hass.tests.test_corrlog
"""
import contextlib
import io
import json
import os
import multiprocessing
import socket
from unittest import mock
import tempfile
import unittest
from datetime import datetime, timedelta, timezone
from pathlib import Path

from hass import conversation, corrlog, morning_report, relay, voice
from hass.tests.test_conversation import CHAT, OWNER, SETTINGS, T0, ConversationTestCase

G = "g@example.invalid"
NOW = datetime(2026, 11, 8, 18, 0, tzinfo=timezone.utc)


class LogCase(unittest.TestCase):
    def setUp(self):
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        self.state = Path(tmp.name)
        self.now = NOW
        self.log = corrlog.CorrLog(self.state, lambda: self.now)

    def files(self):
        return sorted(p.name for p in (self.state / corrlog.FOLDER).iterdir())

    def lines(self):
        return [json.loads(x) for p in sorted((self.state / corrlog.FOLDER).iterdir()) for x in p.read_text("utf-8").splitlines()]


class LogFile(LogCase):
    def test_a_row_has_the_agreed_fields_and_nothing_else(self):
        self.assertTrue(self.log.record("could-not-do", "no-skill", msg="provider-msg-1", reply=7, excerpt="can you order boxes", seconds=3.14159))
        [row] = self.lines()
        self.assertEqual(set(row), {"at", "kind", "reason", "msg", "reply", "excerpt", "seconds"})
        self.assertEqual((row["kind"], row["reason"], row["excerpt"], row["seconds"]), ("could-not-do", "no-skill", "can you order boxes", 3.1))
        self.assertEqual(row["at"], "2026-11-08T18:00:00+00:00")
        self.assertEqual(len(row["msg"]), 12)  # one-way short id, never the provider id
        self.assertNotIn("provider-msg-1", json.dumps(row))
        self.assertEqual(len(row["reply"]), 12)

    def test_unavailable_seconds_do_not_spoil_the_saved_event(self):
        # A nonfinite JSON token breaks strict readers; float overflow used to drop the whole event.
        def reject_constant(token):
            raise ValueError(f"non-JSON constant: {token}")

        def record(seconds):
            return self.log.record("error", "save-failed", seconds=seconds,
                                   msg="fixture-msg", reply="fixture-reply", excerpt="email fixture@example.invalid")

        self.assertTrue(record(2.5))
        path = self.log.dir / "2026-11-08.jsonl"

        def read_last():
            raw = path.read_text("utf-8").splitlines()[-1]
            return json.loads(raw, parse_constant=reject_constant)

        healthy = read_last()
        self.assertEqual(healthy["seconds"], 2.5)
        self.assertEqual(healthy["excerpt"], "email [address]")
        untimed = {key: value for key, value in healthy.items() if key != "seconds"}
        unavailable = {"infinity": float("inf"), "negative infinity": float("-inf"), "nan": float("nan"),
                       "overflow": 10**400, "absent": None, "boolean": True}
        for case, seconds in unavailable.items():
            with self.subTest(case=case):
                self.assertTrue(record(seconds))
                self.assertEqual(read_last(), untimed)

        self.assertEqual(self.log.rows(), [healthy] + [untimed] * len(unavailable))
        summary = corrlog.weekly_line(self.log)
        self.assertIn(f"something went wrong ({1 + len(unavailable)} times;", summary)
        saved = path.read_text("utf-8")
        for private in ("fixture-msg", "fixture-reply", "fixture@example.invalid"):
            self.assertNotIn(private, saved)
            self.assertNotIn(private, summary)

    def test_every_kind_is_accepted_and_an_unknown_kind_is_not(self):
        self.assertEqual(set(corrlog.KINDS), {"did-not-understand", "could-not-do", "asked-again", "error", "slow", "voice-fallback", "corrected"})
        for kind in corrlog.KINDS: self.assertTrue(self.log.record(kind, "x"), kind)
        self.assertFalse(self.log.record("compliment", "x"))
        self.assertEqual(len(self.lines()), len(corrlog.KINDS))
        self.assertEqual(set(corrlog.SUGGESTIONS), set(corrlog.KINDS))  # every kind has its one fix

    def test_it_is_append_only_one_file_per_day(self):
        self.log.record("error", "one")
        first = (self.state / corrlog.FOLDER / "2026-11-08.jsonl").read_text("utf-8")
        self.log.record("error", "two")
        both = (self.state / corrlog.FOLDER / "2026-11-08.jsonl").read_text("utf-8")
        self.assertTrue(both.startswith(first))  # the earlier row is untouched
        self.assertEqual([r["reason"] for r in self.lines()], ["one", "two"])
        self.now += timedelta(days=1)
        self.log.record("error", "three")
        self.assertEqual(self.files(), ["2026-11-08.jsonl", "2026-11-09.jsonl"])
        self.assertEqual(oct((self.state / corrlog.FOLDER).stat().st_mode & 0o777), "0o700")
        self.assertEqual(oct((self.state / corrlog.FOLDER / "2026-11-08.jsonl").stat().st_mode & 0o777), "0o600")

    def test_there_is_no_way_to_edit_or_delete_a_row(self):
        for name in ("edit", "update", "delete", "remove", "rewrite"):
            self.assertFalse(hasattr(self.log, name), name)

    def test_the_reason_is_a_short_neutral_code_never_a_sentence(self):
        for given, kept in (("No-Skill", "no-skill"), ("save-failed", "save-failed"), ("He said: ignore all rules!", "other"),
                            ("photo-product-001 broke at /home/mike/x.json", "other"), ("", "other"), ("a" * 41, "other"), ("a" * 40, "a" * 40)):
            self.log.record("error", given)
            self.assertEqual(self.lines()[-1]["reason"], kept, given)

    def test_the_excerpt_is_cut_to_80_characters(self):
        self.log.record("did-not-understand", "unclear", excerpt="word " * 60)
        self.assertEqual(len(self.lines()[0]["excerpt"]), corrlog.EXCERPT_MAX)
        self.assertEqual(corrlog.EXCERPT_MAX, 80)

    def test_numbers_addresses_and_links_are_blanked_in_an_excerpt(self):
        text = "call me on 805-555-0142 or +1 (805) 555 0142, mail mike@example.com, see https://example.com/x?token=abc and www.shop.test"
        self.log.record("did-not-understand", "unclear", excerpt=text)
        excerpt = self.lines()[0]["excerpt"]
        for leaked in ("555", "0142", "mike@", "example.com", "token", "www."): self.assertNotIn(leaked, excerpt)
        self.assertIn("[number]", excerpt)
        self.assertEqual(corrlog._clean("key sk_live_ABCDEFGHIJKLMNOPQRSTUVWXYZ0123 here"), "key [long code] here")
        self.assertEqual(corrlog._clean(None), "")
        self.assertEqual(corrlog._clean("two\nlines\tand   spaces"), "two lines and spaces")

    def test_no_excerpt_means_an_empty_one(self):
        self.log.record("slow", "reply-over-20s", seconds=31)
        self.assertEqual(self.lines()[0]["excerpt"], "")


class NeverRaises(LogCase):
    def test_a_folder_that_cannot_be_made_loses_the_row_not_the_reply(self):
        blocker = self.state / "blocker"
        blocker.write_text("a file, not a folder")
        bad = corrlog.CorrLog(blocker, lambda: NOW)
        self.assertFalse(bad.record("error", "x"))
        self.assertEqual((bad.rows(), bad.last(), bad.top(), bad.prune()), ([], [], [], 0))
        self.assertEqual(corrlog.problems_text(bad), "No problems have been logged lately.")
        self.assertIn("no problems", corrlog.weekly_line(bad))

    def test_a_missing_state_folder_is_fine(self):
        gone = corrlog.CorrLog(self.state / "nope" / "deeper", lambda: NOW)
        self.assertFalse(gone.record("error", "x"))
        self.assertEqual(gone.rows(), [])

    def test_a_clock_that_fails_does_not_raise(self):
        def boom(): raise RuntimeError("clock")
        self.assertFalse(corrlog.CorrLog(self.state, boom).record("error", "x"))

    def test_a_symlinked_day_file_is_not_followed(self):
        (self.state / corrlog.FOLDER).mkdir()
        elsewhere = self.state / "elsewhere.txt"
        elsewhere.write_text("keep")
        os.symlink(elsewhere, self.state / corrlog.FOLDER / "2026-11-08.jsonl")
        self.assertFalse(self.log.record("error", "x"))
        self.assertEqual(elsewhere.read_text(), "keep")

    def test_damaged_lines_and_stray_files_are_skipped(self):
        self.log.record("error", "good")
        day = self.state / corrlog.FOLDER / "2026-11-08.jsonl"
        with open(day, "a", encoding="utf-8") as f:
            f.write("not json\n[1, 2]\n" + json.dumps({"kind": "bogus", "at": NOW.isoformat()}) + "\n"
                    + json.dumps({"kind": "error", "at": "yesterday-ish"}) + "\n"
                    + json.dumps({"kind": "error", "at": "2026-11-08T10:00:00"}) + "\n")  # no time zone: not trusted
        (self.state / corrlog.FOLDER / "notes.txt").write_text("hello")
        self.assertEqual([r["reason"] for r in self.log.rows()], ["good"])


    def _write(self, rows, when=None):
        when = when or self.now
        day = self.state / corrlog.FOLDER
        day.mkdir(exist_ok=True)
        path = day / f"{when:%Y-%m-%d}.jsonl"
        path.write_text("".join(json.dumps(r) + "\n" for r in rows), encoding="utf-8")
        return path

    def _mixed(self, when=None):
        at = (when or self.now).isoformat()
        good = lambda reason: {"at": at, "kind": "error", "reason": reason}
        bad = [{"at": at, "kind": k, "reason": "CANARY"} for k in ([], {}, ["error"], {"error": 1})]
        return [good("first")] + bad + [good("last")], [good("first"), good("last")]

    def test_container_kind_lines_skip_and_continue(self):
        mixed, accepted = self._mixed()
        path = self._write(mixed)
        before = path.read_bytes()
        self.assertEqual(self.log.rows(), accepted)
        self.assertEqual(path.read_bytes(), before)

    def test_non_string_kind_controls(self):
        at = NOW.isoformat()
        rows = [{"at": at, "kind": k, "reason": "x"} for k in (None, 5, True, "bogus")] + [{"at": at, "reason": "x"}]
        kept = [{"at": at, "kind": k, "reason": "x"} for k in corrlog.KINDS]
        self._write(rows + kept)
        self.assertEqual(self.log.rows(), kept)

    def test_support_formatters_ignore_only_bad_kind_rows(self):
        mixed, accepted = self._mixed()
        self._write(mixed)
        ref = self.state / "ref"
        (ref / corrlog.FOLDER).mkdir(parents=True)
        (ref / corrlog.FOLDER / f"{NOW:%Y-%m-%d}.jsonl").write_text("".join(json.dumps(r) + "\n" for r in accepted), encoding="utf-8")
        other = corrlog.CorrLog(ref, lambda: NOW)
        for fn in (corrlog.problems_text, corrlog.weekly_line):
            self.assertEqual(fn(self.log), fn(other))
            self.assertNotIn("CANARY", fn(self.log))
        self.assertIn("first", corrlog.problems_text(self.log))

    def test_cli_reports_survive_container_kinds(self):
        now = datetime.now(timezone.utc)
        mixed, accepted = self._mixed(now)
        path = self._write(mixed, now)
        before = path.read_bytes()
        ref = Path(tempfile.mkdtemp(dir=self.state))
        (ref / corrlog.FOLDER).mkdir()
        (ref / corrlog.FOLDER / path.name).write_text("".join(json.dumps(r) + "\n" for r in accepted), encoding="utf-8")
        members = sorted(p.name for p in self.state.rglob("*"))
        for what in ("problems", "weekly"):
            got = []
            for state in (self.state, ref):
                out, err = io.StringIO(), io.StringIO()
                with contextlib.redirect_stdout(out), contextlib.redirect_stderr(err):
                    self.assertEqual(corrlog.main([what, "--state", str(state)]), 0)
                self.assertEqual(err.getvalue(), "")
                got.append(out.getvalue())
            self.assertEqual(got[0], got[1])
            self.assertNotIn("CANARY", got[0])
            self.assertNotIn("No problems", got[0])
        self.assertEqual(path.read_bytes(), before)
        self.assertEqual(sorted(p.name for p in self.state.rglob("*")), members)

    BAD_EXCERPTS = ([], ["synthetic-canary"], {}, {"a": 1}, None, False, True, 0, 5)

    def _excerpt_rows(self, when=None):
        at = (when or self.now).isoformat()
        good = lambda: {"at": at, "kind": "error", "reason": "healthy-control", "excerpt": "synthetic control"}
        bad = [{"at": at, "kind": "error", "reason": "malformed-excerpt", "excerpt": e} for e in self.BAD_EXCERPTS]
        return [good()] + bad + [good()], [good(), good()]

    def test_non_string_excerpt_rows_skip_and_continue(self):
        mixed, accepted = self._excerpt_rows()
        path = self._write(mixed)
        before = path.read_bytes()
        self.assertEqual(self.log.rows(), accepted)
        self.assertEqual(path.read_bytes(), before)

    def test_missing_empty_and_text_excerpts_remain_accepted(self):
        at = NOW.isoformat()
        kept = [{"at": at, "kind": "error", "reason": "x"}, {"at": at, "kind": "error", "reason": "x", "excerpt": ""},
                {"at": at, "kind": "error", "reason": "x", "excerpt": "café ünï"}]
        self._write(kept)
        self.assertEqual(self.log.rows(), kept)

    def test_bad_excerpt_does_not_change_problems_or_weekly(self):
        mixed, accepted = self._excerpt_rows()
        self._write(mixed)
        ref = self.state / "ref"
        (ref / corrlog.FOLDER).mkdir(parents=True)
        (ref / corrlog.FOLDER / f"{NOW:%Y-%m-%d}.jsonl").write_text("".join(json.dumps(r) + "\n" for r in accepted), encoding="utf-8")
        other = corrlog.CorrLog(ref, lambda: NOW)
        for fn in (corrlog.problems_text, corrlog.weekly_line):
            self.assertEqual(fn(self.log), fn(other))
            self.assertNotIn("synthetic-canary", fn(self.log))
        self.assertIn("2 times", corrlog.weekly_line(self.log))

    def test_cli_problems_and_weekly_survive_bad_excerpts(self):
        now = datetime.now(timezone.utc)
        mixed, accepted = self._excerpt_rows(now)
        path = self._write(mixed, now)
        before = path.read_bytes()
        ref = Path(tempfile.mkdtemp(dir=self.state))
        (ref / corrlog.FOLDER).mkdir()
        (ref / corrlog.FOLDER / path.name).write_text("".join(json.dumps(r) + "\n" for r in accepted), encoding="utf-8")
        members = sorted(p.name for p in self.state.rglob("*"))
        for what in ("problems", "weekly"):
            got = []
            for state in (self.state, ref):
                out, err = io.StringIO(), io.StringIO()
                with contextlib.redirect_stdout(out), contextlib.redirect_stderr(err):
                    self.assertEqual(corrlog.main([what, "--state", str(state)]), 0)
                self.assertEqual(err.getvalue(), "")
                got.append(out.getvalue())
            self.assertEqual(got[0], got[1])
        self.assertEqual(path.read_bytes(), before)
        self.assertEqual(sorted(p.name for p in self.state.rglob("*")), members)

    DEEP_ARRAY = "[" * 100000 + "0" + "]" * 100000
    DEEP_OBJECT = '{"a":' * 100000 + "0" + "}" * 100000

    def _deep_file(self, when, lines):
        day = self.state / corrlog.FOLDER
        day.mkdir(exist_ok=True)
        path = day / f"{when:%Y-%m-%d}.jsonl"
        path.write_text("\n".join(lines) + "\n", encoding="utf-8")
        return path

    def test_decoder_excessive_lines_skip_and_continue_across_files(self):
        good = lambda when, reason: json.dumps({"at": when.isoformat(), "kind": "error", "reason": reason})
        yesterday = self.now - timedelta(days=1)
        p1 = self._deep_file(yesterday, [good(yesterday, "first"), self.DEEP_ARRAY, good(yesterday, "second")])
        p2 = self._deep_file(self.now, [self.DEEP_OBJECT, good(self.now, "last")])
        before = (p1.read_bytes(), p2.read_bytes())
        self.assertEqual([r["reason"] for r in self.log.rows()], ["first", "second", "last"])
        self.assertEqual(self.log.last()[0]["reason"], "last")
        self.assertTrue(self.log.top())
        self.assertEqual((p1.read_bytes(), p2.read_bytes()), before)

    def test_decoder_excessive_input_formatters_match_accepted_only(self):
        at = self.now.isoformat()
        row = json.dumps({"at": at, "kind": "error", "reason": "good"})
        self._deep_file(self.now, [row, self.DEEP_ARRAY, row])
        ref = self.state / "ref"
        (ref / corrlog.FOLDER).mkdir(parents=True)
        (ref / corrlog.FOLDER / f"{self.now:%Y-%m-%d}.jsonl").write_text(row + "\n" + row + "\n", encoding="utf-8")
        other = corrlog.CorrLog(ref, lambda: NOW)
        for fn in (corrlog.problems_text, corrlog.weekly_line):
            self.assertEqual(fn(self.log), fn(other))
        self.assertIn("good", corrlog.problems_text(self.log))

    def test_cli_survives_decoder_excessive_input(self):
        now = datetime.now(timezone.utc)
        row = json.dumps({"at": now.isoformat(), "kind": "error", "reason": "good"})
        path = self._deep_file(now, [row, self.DEEP_ARRAY, row])
        before = path.read_bytes()
        for what in ("problems", "weekly"):
            out, err = io.StringIO(), io.StringIO()
            with contextlib.redirect_stdout(out), contextlib.redirect_stderr(err):
                self.assertEqual(corrlog.main([what, "--state", str(self.state)]), 0)
            self.assertEqual(err.getvalue(), "")
            self.assertNotIn("No problems", out.getvalue())
        self.assertEqual(path.read_bytes(), before)

    def test_only_decoder_recursion_is_caught(self):
        at = self.now.isoformat()
        row = json.dumps({"at": at, "kind": "error", "reason": "good", "extra": {"n": [[1]]}})
        self._deep_file(self.now, [row, "BOOM", row])
        real = json.loads
        def fake(raw, *a, **k):
            if raw == "BOOM": raise RecursionError
            return real(raw, *a, **k)
        with mock.patch.object(corrlog.json, "loads", fake):
            rows = self.log.rows()
        self.assertEqual(len(rows), 2)
        self.assertEqual(rows[0]["extra"], {"n": [[1]]})
        def boom(raw, *a, **k): raise RuntimeError("other")
        with mock.patch.object(corrlog.json, "loads", boom):
            with self.assertRaises(RuntimeError):
                self.log.rows()


class PathAdmission(LogCase):
    def bounded(self, operation):
        """A regression must fail, not leave a test runner stuck opening a pipe."""
        ctx = multiprocessing.get_context("fork")
        parent, child = ctx.Pipe(duplex=False)
        def run():
            try: child.send(operation())
            finally: child.close()
        process = ctx.Process(target=run)
        process.start()
        child.close()
        try:
            self.assertTrue(parent.poll(3), "correspondence I/O blocked")
            result = parent.recv()
            process.join(3)
            self.assertEqual(process.exitcode, 0)
            return result
        finally:
            if process.is_alive():
                process.terminate()
                process.join()
            parent.close()

    def foreign_row(self):
        return json.dumps({"at": NOW.isoformat(), "kind": "corrected", "reason": "foreign",
                           "excerpt": "foreign synthetic excerpt"}) + "\n"

    def test_unsafe_correspondence_directories_are_never_traversed(self):
        outside = self.state / "outside"
        outside.mkdir()
        (outside / "2026-11-08.jsonl").write_text(self.foreign_row())
        (outside / "2025-01-01.jsonl").write_text("old synthetic bytes")
        before = {p.name: p.read_bytes() for p in outside.iterdir()}
        for kind in ("linked", "dangling", "file", "missing"):
            with self.subTest(kind=kind):
                state = self.state / kind
                state.mkdir()
                self.log = corrlog.CorrLog(state, lambda: self.now)
                if kind == "linked": self.log.dir.symlink_to(outside, target_is_directory=True)
                if kind == "dangling": self.log.dir.symlink_to(self.state / "absent", target_is_directory=True)
                if kind == "file": self.log.dir.write_text("blocker")
                self.assertEqual((self.log.rows(), self.log.last(), self.log.top(), self.log.prune()), ([], [], [], 0))
                if kind != "missing":
                    self.assertFalse(self.log.record("error", "x"))
                    self.assertEqual({p.name: p.read_bytes() for p in outside.iterdir()}, before)
                    self.assertFalse((self.state / "absent").exists())
                    if kind == "file": self.assertEqual(self.log.dir.read_text(), "blocker")
                    else: self.assertTrue(self.log.dir.is_symlink())
                    self.log.dir.unlink()
                else: self.assertFalse(self.log.dir.exists())

    def test_linked_day_files_are_not_read_or_reported(self):
        self.assertTrue(self.log.record("error", "local"))
        foreign = self.state / "foreign"
        foreign.write_text(self.foreign_row())
        for name in ("2026-11-07.jsonl", "2025-01-01.jsonl"):
            (self.log.dir / name).symlink_to(foreign)
        self.assertEqual([r["reason"] for r in self.log.rows()], ["local"])
        self.assertNotIn("foreign", corrlog.problems_text(self.log))
        self.assertNotIn(corrlog.KINDS["corrected"], corrlog.weekly_line(self.log))
        self.now -= timedelta(days=1)
        self.assertFalse(self.log.record("error", "x"))
        self.assertEqual(self.log.prune(), 0)
        self.assertTrue((self.log.dir / "2025-01-01.jsonl").is_symlink())
        self.assertEqual(foreign.read_text(), self.foreign_row())

    def test_nonregular_day_files_do_not_block(self):
        self.log.dir.mkdir()
        day = self.log.dir / "2026-11-08.jsonl"
        for kind in ("fifo", "directory", "socket"):
            with self.subTest(kind=kind):
                if kind == "fifo": os.mkfifo(day)
                elif kind == "directory": day.mkdir()
                else:
                    sock = socket.socket(socket.AF_UNIX)
                    self.addCleanup(sock.close)
                    with contextlib.chdir(self.log.dir): sock.bind(day.name)
                try:
                    for read in (False, True):
                        with self.subTest(read=read):
                            result = self.bounded(self.log.rows if read else lambda: self.log.record("error", "x"))
                            self.assertEqual(result, [] if read else False)
                finally:
                    if kind == "directory": day.rmdir()
                    else: day.unlink()

    def test_fifo_swapped_in_at_open_time_does_not_block(self):
        self.log.dir.mkdir()
        day = self.log.dir / "2026-11-08.jsonl"
        real_open = os.open
        def operation(read):
            day.write_text(self.foreign_row())
            def swap(path, flags, *args, **kwargs):
                if Path(path) == day:
                    day.unlink()
                    os.mkfifo(day)
                return real_open(path, flags, *args, **kwargs)
            with mock.patch.object(corrlog.os, "open", side_effect=swap):
                return self.log.rows() if read else self.log.record("error", "x")
        for read in (False, True):
            with self.subTest(read=read):
                try:
                    self.assertEqual(self.bounded(lambda: operation(read)), [] if read else False)
                finally: day.unlink(missing_ok=True)

    def test_refused_descriptors_are_closed_without_reading_or_writing(self):
        self.log.dir.mkdir()
        (self.log.dir / "2026-11-08.jsonl").write_text(self.foreign_row())
        for read in (False, True):
            with self.subTest(read=read), mock.patch.object(corrlog.os, "open", return_value=321), \
                 mock.patch.object(corrlog.os, "fstat", return_value=self.log.dir.stat()), \
                 mock.patch.object(corrlog.os, "close") as close, \
                 mock.patch.object(corrlog.os, "read") as read_bytes, \
                 mock.patch.object(corrlog.os, "write") as write_bytes:
                self.assertEqual(self.log.rows() if read else self.log.record("error", "x"), [] if read else False)
                close.assert_called_once_with(321)
                read_bytes.assert_not_called()
                write_bytes.assert_not_called()

    def test_unreadable_disappeared_and_replacement_decoded_day_files(self):
        self.log.dir.mkdir()
        day = self.log.dir / "2026-11-08.jsonl"
        day.write_bytes(self.foreign_row().encode().replace(b"foreign synthetic", b"\xff synthetic"))
        self.assertIn("\ufffd", self.log.rows()[0]["excerpt"])
        for error in (PermissionError, FileNotFoundError):
            with self.subTest(error=error), mock.patch.object(corrlog.os, "open", side_effect=error):
                self.assertEqual(self.log.rows(), [])
                self.assertFalse(self.log.record("error", "x"))


class Retention(LogCase):
    def test_day_files_older_than_90_days_are_deleted_whole(self):
        for days_ago in (0, 30, 89, 90, 91, 200):
            self.now = NOW - timedelta(days=days_ago)
            self.log.record("error", f"d{days_ago}")
        self.now = NOW
        (self.state / corrlog.FOLDER / "notes.txt").write_text("not a day file: left alone")
        self.assertEqual(self.log.prune(), 2)  # 91 and 200 days old
        self.assertEqual(len(self.files()), 5)  # four day files and the stray file
        self.assertIn("notes.txt", self.files())
        self.assertEqual(corrlog.RETENTION_DAYS, 90)

    def test_writing_a_row_deletes_old_day_files_without_anyone_running_prune(self):
        self.now = NOW - timedelta(days=100)
        self.log.record("error", "old")
        self.assertEqual(len(self.files()), 1)
        self.now = NOW
        self.log.record("error", "new")  # the first row of a new day removes the 100-day-old file
        self.assertEqual(self.files(), [f"{NOW.astimezone(timezone.utc):%Y-%m-%d}.jsonl"])
        self.assertEqual([r["reason"] for r in self.log.rows()], ["new"])

    def test_rows_older_than_90_days_are_not_read_even_before_pruning(self):
        self.now = NOW - timedelta(days=120)
        self.log.record("error", "old")
        self.now = NOW - timedelta(days=10)
        self.log.record("error", "recent")
        self.now = NOW
        self.assertEqual([r["reason"] for r in self.log.rows()], ["recent"])

    def test_prune_leaves_a_symlink_alone(self):
        (self.state / corrlog.FOLDER).mkdir()
        elsewhere = self.state / "elsewhere.txt"
        elsewhere.write_text("keep")
        os.symlink(elsewhere, self.state / corrlog.FOLDER / "2025-01-01.jsonl")
        self.assertEqual(self.log.prune(), 0)
        self.assertTrue(elsewhere.exists())

    IMPOSSIBLE = ("2026-02-30.jsonl", "2025-02-29.jsonl", "2026-00-01.jsonl", "0000-01-01.jsonl", "2026-13-01.jsonl")

    def plant_impossible(self):
        folder = self.state / corrlog.FOLDER
        folder.mkdir(mode=0o700, exist_ok=True)
        for i, name in enumerate(self.IMPOSSIBLE):
            (folder / name).write_text(f"unknown-{i}\n")
            (folder / name).chmod(0o640)
        return folder

    def test_prune_skips_impossible_calendar_names_and_continues(self):
        folder = self.plant_impossible()
        (folder / "2026-01-01.jsonl").write_text("old\n")  # a valid expired day, wherever the scan meets it
        (folder / "2026-08-10.jsonl").write_text("cutoff day\n")  # NOW 2026-11-08 minus 90 days: kept
        self.assertEqual(self.log.prune(), 1)
        self.assertEqual(self.files(), sorted(self.IMPOSSIBLE + ("2026-08-10.jsonl",)))
        for i, name in enumerate(self.IMPOSSIBLE):
            self.assertEqual((folder / name).read_text(), f"unknown-{i}\n")
            self.assertEqual((folder / name).stat().st_mode & 0o777, 0o640)
        self.assertEqual(self.log.prune(), 0)

    def test_first_daily_record_survives_invalid_day_file(self):
        folder = self.plant_impossible()
        (folder / "2026-01-01.jsonl").write_text("old\n")
        self.assertTrue(self.log.record("error", "first"))
        self.assertTrue(self.log.record("error", "second"))
        today = folder / "2026-11-08.jsonl"
        self.assertEqual([json.loads(x)["reason"] for x in today.read_text("utf-8").splitlines()], ["first", "second"])
        self.assertEqual(today.stat().st_mode & 0o777, 0o600)
        self.assertEqual(self.files(), sorted(self.IMPOSSIBLE + ("2026-11-08.jsonl",)))
        self.now = NOW + timedelta(days=1)  # a new UTC day scans again and still writes its first row
        self.assertTrue(self.log.record("error", "third"))
        self.assertEqual(json.loads((folder / "2026-11-09.jsonl").read_text("utf-8"))["reason"], "third")
        self.assertEqual((folder / "2026-02-30.jsonl").read_text(), "unknown-0\n")

    def test_prune_calendar_boundaries_and_valid_leap_day(self):
        folder = self.state / corrlog.FOLDER
        folder.mkdir(mode=0o700)
        self.now = datetime(2028, 5, 29, 12, 0, tzinfo=timezone.utc)  # cutoff day 2028-02-29, a real leap day
        for name in ("2028-02-28.jsonl", "2028-02-29.jsonl", "2028-03-01.jsonl", "2028-05-30.jsonl", "2027-02-29.jsonl"):
            (folder / name).write_text("x\n")
        self.assertEqual(self.log.prune(), 1)  # only 2028-02-28 is valid and strictly older
        self.assertEqual(self.files(), ["2027-02-29.jsonl", "2028-02-29.jsonl", "2028-03-01.jsonl", "2028-05-30.jsonl"])
        self.now = datetime(2028, 5, 30, 12, 0, tzinfo=timezone.utc)  # the valid leap day is now one day too old
        self.assertEqual(self.log.prune(), 1)
        self.assertEqual(self.files(), ["2027-02-29.jsonl", "2028-03-01.jsonl", "2028-05-30.jsonl"])

    def test_prune_cli_with_invalid_day_name_keeps_fixed_output(self):
        folder = self.plant_impossible()
        old = (datetime.now(timezone.utc) - timedelta(days=200)).strftime("%Y-%m-%d.jsonl")
        (folder / old).write_text("old\n")
        for expected in ("Deleted 1 old day files.\n", "Deleted 0 old day files.\n"):
            out, err = io.StringIO(), io.StringIO()
            with contextlib.redirect_stderr(err):
                self.assertEqual(corrlog.main(["prune", "--state", str(self.state)], out=out), 0)
            self.assertEqual(err.getvalue(), "")
            self.assertEqual(out.getvalue(), expected)
        self.assertEqual(self.files(), sorted(self.IMPOSSIBLE))
        self.assertEqual((folder / "2026-02-30.jsonl").read_text(), "unknown-0\n")


class ForG(LogCase):
    def fill(self, kinds):
        for i, kind in enumerate(kinds):
            self.now = NOW + timedelta(minutes=i)
            self.log.record(kind, f"r{i}", excerpt=f"he wrote {i}" if i % 2 else None)

    def test_problems_lists_the_last_ten_newest_first(self):
        self.fill(["error"] * 15)
        text = corrlog.problems_text(self.log)
        lines = text.splitlines()
        self.assertEqual(lines[0], "The last 10 problems, newest first:")
        self.assertEqual(len(lines), 11)
        self.assertIn("(r14)", lines[1])  # newest first
        self.assertIn("(r5)", lines[10])
        self.assertNotIn("(r4)", text)

    def test_problems_is_plain_words_for_one_row_and_for_none(self):
        self.assertEqual(corrlog.problems_text(self.log), "No problems have been logged lately.")
        self.log.record("slow", "reply-over-20s")
        text = corrlog.problems_text(self.log)
        self.assertIn("The last 1 problem, newest first:", text)
        self.assertIn("a reply took more than 20 seconds", text)
        self.assertIn("Sun Nov 8, 10:00 am", text)  # shop time, written naturally
        self.assertEqual(voice.check(text, long_ok=True, ids_ok=True), [])

    def test_problems_shows_what_he_wrote_but_not_numbers(self):
        self.log.record("did-not-understand", "unclear", excerpt="order 12 boxes, call 805 555 0142")
        text = corrlog.problems_text(self.log)
        self.assertIn("He wrote:", text)
        self.assertNotIn("0142", text)

    def test_weekly_is_the_three_most_common_with_one_fix_each(self):
        self.fill(["error"] * 4 + ["did-not-understand"] * 3 + ["slow"] * 2 + ["corrected"])
        line = corrlog.weekly_line(self.log)
        self.assertEqual(self.log.top(), [("error", 4), ("did-not-understand", 3), ("slow", 2)])
        for kind, n in (("error", 4), ("did-not-understand", 3), ("slow", 2)):
            self.assertIn(f"{corrlog.KINDS[kind]} ({n} times; try: {corrlog.SUGGESTIONS[kind]})", line)
        self.assertNotIn(corrlog.KINDS["corrected"], line)  # only three
        self.assertEqual(line.count("try:"), 3)
        self.assertLess(line.index("something went wrong"), line.index("I did not understand"))

    def test_weekly_counts_only_the_last_seven_days_and_ties_are_stable(self):
        self.now = NOW - timedelta(days=9)
        for _ in range(5): self.log.record("error", "old")
        self.now = NOW
        self.log.record("slow", "a")
        self.log.record("could-not-do", "b")
        self.assertEqual(self.log.top(), [("could-not-do", 1), ("slow", 1)])
        line = corrlog.weekly_line(self.log)
        self.assertNotIn("something went wrong", line)
        self.assertIn("(1 time; try:", line)

    def test_weekly_with_nothing_logged_says_so(self):
        self.assertEqual(corrlog.weekly_line(self.log), "Talking with Mike this week: no problems logged.")

    def test_the_command_line_reads_the_same_text(self):
        self.fill(["error", "slow"])
        for what, text in (("problems", corrlog.problems_text), ("weekly", corrlog.weekly_line)):
            out = io.StringIO()
            with contextlib.redirect_stdout(out):
                self.assertEqual(corrlog.main([what, "--state", str(self.state)]), 0)
            self.assertTrue(out.getvalue().strip())


class Moments(ConversationTestCase):
    """The conversation writes a row at each problem moment, and only for those."""

    def kinds(self):
        return [(r["kind"], r["reason"]) for r in self.conv.log.rows()]

    def test_a_slow_reply_is_logged_when_it_leaves(self):
        self.say("hours")  # a draft reply, stored now
        self.now += timedelta(seconds=corrlog.SLOW_SECONDS + 15)
        self.replies()
        self.assertIn(("slow", "reply-over-20s"), self.kinds())
        [slow] = [r for r in self.conv.log.rows() if r["kind"] == "slow"]
        self.assertGreater(slow["seconds"], corrlog.SLOW_SECONDS)

    def test_a_quick_reply_is_not_logged(self):
        self.say("hours")
        self.now += timedelta(seconds=corrlog.SLOW_SECONDS - 5)
        self.replies()
        self.assertNotIn("slow", [k for k, _ in self.kinds()])

    def test_a_question_asked_again_is_logged(self):
        self.say("when?")
        self.replies()
        self.assertEqual(self.kinds(), [])
        self.now += timedelta(minutes=1)
        self.say("when?")
        self.assertIn(("asked-again", "same-question"), self.kinds())

    def test_a_question_asked_a_long_time_later_is_not_logged(self):
        self.say("when?")
        self.now += timedelta(hours=2)
        self.say("when?")
        self.assertNotIn("asked-again", [k for k, _ in self.kinds()])

    def test_saying_no_is_logged_as_a_correction(self):
        draft, _reply = self.propose("hours")
        self.assertEqual(self.say("no"), "rejected")
        self.assertIn(("corrected", "said-no"), self.kinds())

    def test_thats_wrong_is_logged_as_a_correction(self):
        self.propose("hours")
        self.say("that's wrong")
        self.assertIn(("corrected", "owner-corrected"), self.kinds())

    def test_not_what_i_meant_is_logged_as_a_correction(self):
        self.propose("hours")
        self.say("not what I meant")
        self.assertIn(("corrected", "owner-corrected"), self.kinds())

    def test_an_ordinary_happy_path_logs_nothing(self):
        self.propose("hours")
        self.say("yes")
        self.replies()
        self.assertEqual(self.kinds(), [])

    def test_something_it_cannot_do_is_logged_as_could_not_do(self):
        self.say("unknown thing")  # the fixture interpreter answers "Sorry, I can't do that yet."
        self.assertIn(("could-not-do", "no-skill"), self.kinds())

    def test_a_held_back_message_is_logged_as_a_voice_fallback(self):
        self.conv.outbox.strict = False
        self.conv.outbox.add(CHAT, "The interpreter failed closed on photo-product-001.")
        [row] = self.conv.log.rows()
        self.assertEqual(row["kind"], "voice-fallback")
        self.assertNotIn("photo-product-001", json.dumps(row))

    def test_no_row_holds_more_than_the_agreed_fields(self):
        self.say("hours")
        self.now += timedelta(seconds=60)
        self.replies()
        self.say("that's wrong")
        for row in self.conv.log.rows():
            self.assertLessEqual(set(row), {"at", "kind", "reason", "msg", "reply", "excerpt", "seconds"})
            self.assertLessEqual(len(row["excerpt"]), corrlog.EXCERPT_MAX)

    def test_the_log_lives_in_the_state_folder_only(self):
        self.say("that's wrong")
        self.assertTrue((self.repo.state / corrlog.FOLDER).is_dir())


class GOnly(ConversationTestCase):
    def setUp(self):
        super().setUp()
        self.set_settings({**SETTINGS, "gSenders": [G], "gChat": "chat-g"})
        self.conv = self.open()
        self.conv.log.record("error", "save-failed")
        self.conv.log.record("slow", "reply-over-20s")

    def test_problems_from_g_gets_the_list(self):
        self.assertEqual(self.say("problems", chat="chat-g", sender=G), "g-problems")
        [reply] = self.replies()
        self.assertTrue(reply.startswith("The last 2 problems, newest first:"), reply)

    def test_weekly_from_g_gets_the_week(self):
        self.assertEqual(self.say("weekly", chat="chat-g", sender=G), "g-weekly")
        [reply] = self.replies()
        self.assertIn("most common problems were", reply)

    def test_problems_from_any_other_number_gets_no_answer(self):
        for sender in ("stranger@example.invalid", "+18055550100"):
            for word in ("problems", "weekly"):
                self.say(word, chat="chat-x", sender=sender)
                self.assertEqual(self.replies(), [], (sender, word))
        self.assertEqual(self.conv.db.execute("SELECT COUNT(*) FROM outbox").fetchone()[0], 0)

    def test_mike_asking_for_problems_gets_no_list(self):
        self.say("problems")  # Mike's own number is an owner sender, not a G sender
        for reply in self.replies(): self.assertNotIn("most common", reply) or self.assertNotIn("newest first", reply)
        self.say("weekly")
        for reply in self.replies(): self.assertNotIn("newest first", reply)

    def test_g_is_not_an_owner_and_cannot_approve_changes(self):
        draft, _reply = self.propose("hours")
        self.say("yes", chat="chat-g", sender=G)
        self.replies()
        self.assertEqual(self.drafts()[-1]["state"], "proposed")
        self.assertEqual(self.commits(), 0)

    def test_g_overlapping_the_owner_is_a_config_error(self):
        for g in ([OWNER], [G, OWNER], [OWNER.upper()]):
            with self.subTest(g=g):
                self.set_settings({**SETTINGS, "gSenders": g})
                with self.assertRaises(conversation.ConfigError):
                    self.open()

    def test_g_senders_must_be_a_list_of_addresses(self):
        for g in ("g@example.invalid", 5, [5], [None], {"a": 1}):
            with self.subTest(g=g):
                self.set_settings({**SETTINGS, "gSenders": g})
                with self.assertRaises(conversation.ConfigError):
                    self.open()

    def test_without_g_senders_nobody_gets_the_list(self):
        self.set_settings(SETTINGS)
        self.conv = self.open()
        self.say("problems", chat="chat-g", sender=G)
        self.assertEqual(self.replies(), [])

    def test_g_asking_in_mikes_chat_gets_no_answer_and_mike_sees_nothing(self):
        for word in ("problems", "weekly"):
            self.assertEqual(self.say(word, chat=CHAT, sender=G), "ignored")
        self.assertEqual(self.replies(), [])
        self.assertEqual(self.conv.db.execute("SELECT COUNT(*) FROM outbox").fetchone()[0], 0)

    def test_g_asking_in_any_other_chat_gets_no_answer(self):
        self.assertEqual(self.say("problems", chat="some-other-chat", sender=G), "ignored")
        self.assertEqual(self.replies(), [])

    def test_the_answer_goes_to_gs_chat_only(self):
        self.say("problems", chat="chat-g", sender=G)
        self.conv.flush(self.out)
        self.assertEqual([m["chat"] for m in self.out.sent], ["chat-g"])

    def test_g_chat_must_be_set_and_must_be_gs_own_one_to_one_chat(self):
        for chat in (None, "", CHAT, "x;+;group", f"x;-;{OWNER}", 5):
            with self.subTest(chat=chat):
                self.set_settings({**SETTINGS, "gSenders": [G], **({} if chat is None else {"gChat": chat})})
                with self.assertRaises(conversation.ConfigError):
                    self.open()
        self.set_settings({**SETTINGS, "gSenders": [G], "gChat": f"any;-;{G}"})
        self.open()
        self.set_settings({**SETTINGS, "gChat": "chat-g"})
        with self.assertRaises(conversation.ConfigError):
            self.open()


class GDelivery(ConversationTestCase):
    """The real relay sender: G's chat is delivered text only; every other chat is still refused; a G reply that cannot be
    sent never holds up the one for Mike."""
    GCHAT = "chat-g"

    def setUp(self):
        super().setUp()
        self.set_settings({**SETTINGS, "gSenders": [G], "gChat": self.GCHAT})
        self.conv = self.open()
        self.conv.log.record("error", "save-failed")
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        self.store = relay.RelayStore(Path(tmp.name))

    def sender(self, g_chat):
        return relay.RelaySender(self.store, CHAT, lambda: 1, None, g_chat)

    def queued(self):
        return [tuple(r) for r in self.store.db.execute("SELECT chat, text FROM relay ORDER BY id")]

    def test_g_reply_and_owner_reply_both_go_through_the_relay(self):
        self.say("problems", chat=self.GCHAT, sender=G)
        self.say("status")
        self.assertEqual(self.conv.flush(self.sender(self.GCHAT)), 2)
        self.assertEqual([c for c, _ in self.queued()], [self.GCHAT, CHAT])

    def test_the_relay_refuses_other_chats_and_pictures_for_g(self):
        sender = self.sender(self.GCHAT)
        for chat, attachments in (("somebody-else", ()), (self.GCHAT, ("a.png",))):
            with self.assertRaises(relay.RelayRefused):
                sender.send(chat, "hello", attachments)
        with self.assertRaises(relay.RelayRefused):
            self.sender(None).send(self.GCHAT, "hello")
        with self.assertRaises(relay.RelayRefused):
            self.sender(CHAT).send("somebody-else", "hello")
        self.assertEqual(self.queued(), [])

    def test_g_replies_that_nobody_collects_never_crowd_out_mikes(self):
        sender = self.sender(self.GCHAT)
        for n in range(relay.G_PENDING_MAX):
            sender.send(self.GCHAT, f"problems {n}")
        self.say("problems", chat=self.GCHAT, sender=G)
        self.say("status")
        self.assertEqual(self.conv.flush(sender), 1)  # G's third is dropped, Mike's goes
        self.assertEqual([c for c, _ in self.queued()].count(self.GCHAT), relay.G_PENDING_MAX)
        self.assertEqual([c for c, _ in self.queued()][-1], CHAT)

    def test_a_g_reply_that_cannot_be_sent_does_not_block_mikes_reply(self):
        self.say("problems", chat=self.GCHAT, sender=G)
        self.say("status")
        self.assertEqual(self.conv.flush(self.sender(None)), 1)  # a relay that does not know G's chat refuses its row
        self.assertEqual([c for c, _ in self.queued()], [CHAT])
        self.assertEqual(self.conv.db.execute("SELECT COUNT(*) FROM outbox WHERE sent_at IS NULL").fetchone()[0], 0)

    def test_a_refused_owner_reply_still_stops_the_queue(self):
        self.say("status")
        with self.assertRaises(relay.RelayRefused):
            self.conv.flush(relay.RelaySender(self.store, "some-other-chat", lambda: 1))
        self.assertEqual(self.conv.db.execute("SELECT COUNT(*) FROM outbox WHERE sent_at IS NULL").fetchone()[0], 1)


class MikesReport(unittest.TestCase):
    def run_report(self, for_g=False):
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        state = Path(tmp.name)
        corrlog.CorrLog(state, lambda: datetime.now(timezone.utc)).record("error", "save-failed")
        content = state / "content"
        content.mkdir()
        for name, doc in (("products", {"schemaVersion": 1, "products": []}), ("makers", {"schemaVersion": 1, "makers": {}}),
                          ("community", {"schemaVersion": 1}), ("store", {"schemaVersion": 1})):
            (content / f"{name}.json").write_text(json.dumps(doc), encoding="utf-8")
        out = io.StringIO()
        self.assertEqual(morning_report.main((["--for-g", str(state)] if for_g else []), content_dir=content, out=out), 0)
        return out.getvalue()

    def test_mikes_report_never_contains_the_weekly_line(self):
        text = self.run_report()
        self.assertNotIn("Talking with Mike", text)
        self.assertNotIn("most common problems", text)
        self.assertEqual(voice.check(text.strip(), long_ok=True), [])

    def test_g_gets_the_weekly_line_after_the_report(self):
        text = self.run_report(for_g=True)
        self.assertIn("Talking with Mike this week", text)
        self.assertIn("something went wrong (1 time; try:", text)

    def test_the_morning_report_has_no_weekly_option_that_mike_can_reach(self):
        # --for-g is a command-line flag for G's run on the box; nothing in the chat code passes it.
        source = (Path(conversation.__file__)).read_text("utf-8")
        self.assertNotIn("for-g", source)
        self.assertNotIn("weekly_line", source.split("def _for_g")[0])


class EventTimeOrder(LogCase):
    def put(self, name, *items):
        folder = self.state / corrlog.FOLDER
        folder.mkdir(mode=0o700, exist_ok=True)
        with open(folder / name, "a", encoding="utf-8") as f:
            for at, reason in items: f.write(json.dumps({"at": at, "kind": "error", "reason": reason}) + "\n")

    def reasons(self, rows): return [r["reason"] for r in rows]

    def test_clock_rollback_does_not_displace_latest_problem(self):
        self.now = datetime(2026, 11, 8, 12, 0, tzinfo=timezone.utc)
        self.log.record("error", "later")
        self.now = datetime(2026, 11, 8, 10, 0, tzinfo=timezone.utc)
        self.log.record("error", "earlier")
        self.now = NOW
        self.assertEqual(self.reasons(self.log.rows()), ["earlier", "later"])
        self.assertEqual(self.reasons(self.log.last(1)), ["later"])
        text = corrlog.problems_text(self.log, 1)
        self.assertIn("(later)", text)
        self.assertNotIn("(earlier)", text)

    def test_rows_sort_instants_across_files_and_offsets(self):
        self.put("2026-11-07.jsonl", ("2026-11-08T09:30:00+00:00", "b"))
        self.put("2026-11-08.jsonl", ("2026-11-08T10:00:00+01:00", "a"), ("2026-11-07T20:00:00+00:00", "z"), ("2026-11-08T11:00:00+00:00", "c"))
        rows = self.log.rows()
        self.assertEqual(self.reasons(rows), ["z", "a", "b", "c"])
        self.assertEqual(rows[1]["at"], "2026-11-08T10:00:00+01:00")  # spelling untouched
        self.assertEqual(self.reasons(self.log.last(2)), ["c", "b"])

    def test_equal_instants_preserve_scan_ties(self):
        self.put("2026-11-08.jsonl", ("2026-11-08T10:00:00+00:00", "one"), ("2026-11-08T11:00:00+01:00", "two"))
        self.put("2026-11-09.jsonl", ("2026-11-08T10:00:00Z", "three"), ("2026-11-08T09:00:00+00:00", "first"))
        self.assertEqual(self.reasons(self.log.rows()), ["first", "one", "two", "three"])
        self.assertEqual(self.reasons(self.log.last(4)), ["three", "two", "one", "first"])

    def test_cli_problems_is_newest_first_without_rewriting(self):
        now = datetime.now(timezone.utc)
        self.put("x.jsonl")  # stray file, ignored
        self.put(now.strftime("%Y-%m-%d") + ".jsonl",
                 ((now - timedelta(minutes=10)).isoformat(), "newer"), ((now - timedelta(minutes=50)).isoformat(), "older"),
                 ((now - timedelta(minutes=30)).isoformat(), "mid"))
        path = self.state / corrlog.FOLDER / (now.strftime("%Y-%m-%d") + ".jsonl")
        before = path.read_bytes()
        out, err = io.StringIO(), io.StringIO()
        with contextlib.redirect_stderr(err):
            self.assertEqual(corrlog.main(["problems", "--state", str(self.state)], out=out), 0)
        lines = out.getvalue().splitlines()
        self.assertEqual(lines[0], "The last 3 problems, newest first:")
        self.assertEqual([l.rsplit("(", 1)[1][:-2] for l in lines[1:]], ["newer", "mid", "older"])
        self.assertEqual(err.getvalue(), "")
        self.assertEqual(path.read_bytes(), before)
        self.assertEqual(self.log.top(7, 3), [("error", 3)])

    def test_filtering_precedes_sort_and_empty_behavior_stays(self):
        self.assertEqual(corrlog.problems_text(self.log), "No problems have been logged lately.")
        self.put("2026-11-08.jsonl", ("2026-11-08T12:00:00", "naive"), ("garbage", "bad"), ("2026-11-08T12:00:00+00:00", "ok"))
        self.put("2026-05-01.jsonl", ("2026-05-01T12:00:00+00:00", "old"))
        self.assertEqual(self.reasons(self.log.rows()), ["ok"])


class SafeFolder(unittest.TestCase):
    def test_the_state_backup_does_not_take_the_log(self):
        from hass import statebackup
        source = Path(statebackup.__file__).read_text("utf-8")
        self.assertNotIn(corrlog.FOLDER, source)  # it lists the files it takes; the log is not one of them


if __name__ == "__main__":
    unittest.main()
