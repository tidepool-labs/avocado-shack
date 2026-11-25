"""Restored-conversation viewer: order and picture links survive a restore; nothing private is echoed.

Synthetic transcript rows are written with the real hass.transcript writer; the "restore" is a private copy of the
store and media trees, the shape hass.statebackup.restore produces (state dir 0700, transcript 0600, media/originals,
media/npp). No network, no live state, no real names.
"""
import base64
import contextlib
import hashlib
import io
import json
import os
from pathlib import Path
import shutil
import sqlite3
import stat
import subprocess
import sys
import tempfile
import unittest

from hass import transcript

SCRIPT = Path(__file__).resolve().parents[2] / "scripts/hass/restored_chat_view.py"
REPO = SCRIPT.parents[2]
CHAT, SENDER = "fixture-chat-private", "fixture-sender-private"
PNG = base64.b64decode("iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAQAAAC1HAwCAAAAC0lEQVR42mP8/x8AAwMCAO+aB9sAAAAASUVORK5CYII=")
JPEG = b"\xff\xd8\xff\xe0fixture-photo\xff\xd9"
TEXTS = ("fixture-text-one-private", "fixture-text-two-private", "fixture-text-three-private")


def sha(data):
    return hashlib.sha256(data).hexdigest()


def private_dir(parent, name):
    path = Path(parent) / name
    path.mkdir(mode=0o700, parents=True)
    os.chmod(path, 0o700)
    return path


def run(*args):
    done = subprocess.run([sys.executable, "-B", str(SCRIPT), *map(str, args)], capture_output=True, text=True, cwd=REPO)
    return done.returncode, done.stdout + done.stderr


class RestoredChatViewTests(unittest.TestCase):
    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp())
        self.addCleanup(shutil.rmtree, self.tmp, True)
        self.card = PNG + b"card-a"
        self.state = private_dir(self.tmp, "state")
        for direction, kind, text, shas in (("in", "photo", TEXTS[0], [sha(JPEG)]), ("out", "text", TEXTS[1], []),
                                            ("out", "photo", TEXTS[2], [sha(self.card)])):
            transcript.append(self.state, **transcript.event(CHAT, SENDER if direction == "in" else "hass", direction,
                                                              kind, text, attachments=shas,
                                                              provider_id=f"p-{text}" if direction == "in" else None))
        self.export = self.tmp / "before.jsonl"
        with contextlib.redirect_stdout(io.StringIO()) as out:
            transcript.main(["export", "--state", str(self.state), "--since", "2000-01-01"])
        self.export.write_text(out.getvalue(), encoding="utf-8")
        self.media = private_dir(self.tmp, "media")
        original = private_dir(self.media, f"originals/{sha(JPEG)[:2]}")
        (original / f"{sha(JPEG)}.jpg").write_bytes(JPEG)
        (original / f"{sha(JPEG)}.json").write_text("{}")
        cards = private_dir(self.media, "npp/abcd1234")
        (cards / f"card-{sha(self.card)}.png").write_bytes(self.card)
        (cards / "receipt.json").write_text("{}")

    def restored(self):
        """A private copy, as a restore leaves it; the original store is never the thing under test."""
        state, media = private_dir(self.tmp, "restored"), self.tmp / "restored-media"
        shutil.copyfile(self.state / transcript.NAME, state / transcript.NAME)
        os.chmod(state / transcript.NAME, 0o600)
        shutil.copytree(self.media, media)
        return state, media

    def assertQuiet(self, output):
        for private in (CHAT, SENDER, *TEXTS, sha(JPEG), sha(self.card), str(self.tmp), "p-fixture"):
            self.assertNotIn(private, output)

    def test_restored_order_and_picture_links_pass_and_nothing_private_is_printed(self):
        state, media = self.restored()
        code, output = run("--state", state, "--media", media, "--reference", self.export)
        self.assertEqual((code, output.strip()), (0, "PASS restored_chat_view events=3 attachments=2 linked=2 reference=matched"))
        self.assertQuiet(output)

    def test_without_reference_only_internal_order_is_claimed(self):
        state, media = self.restored()
        code, output = run("--state", state, "--media", media)
        self.assertEqual(code, 0)
        self.assertIn("reference=none", output)

    def test_a_reordered_or_shortened_reference_is_a_failure(self):
        state, media = self.restored()
        lines = self.export.read_text().splitlines()
        for name, content, where in (("swapped", [lines[1], lines[0], lines[2]], 0), ("short", lines[:2], 2)):
            ref = self.tmp / f"{name}.jsonl"
            ref.write_text("\n".join(content) + "\n")
            code, output = run("--state", state, "--media", media, "--reference", ref)
            self.assertEqual(code, 1, name)
            self.assertIn(f"reference-differs-at-event-{where}", output)
            self.assertQuiet(output)

    def test_a_missing_picture_is_counted_not_named(self):
        state, media = self.restored()
        (media / "npp/abcd1234" / f"card-{sha(self.card)}.png").unlink()
        code, output = run("--state", state, "--media", media)
        self.assertEqual(code, 1)
        self.assertIn("attachments-missing-1", output)
        self.assertQuiet(output)

    def test_pictures_are_needed_when_messages_name_them(self):
        state, _media = self.restored()
        code, output = run("--state", state)
        self.assertEqual(code, 1)
        self.assertIn("media-not-given", output)

    def test_a_picture_whose_bytes_do_not_match_its_name_is_refused(self):
        state, media = self.restored()
        (media / "npp/abcd1234" / f"card-{sha(self.card)}.png").write_bytes(PNG + b"another-card")
        code, output = run("--state", state, "--media", media)
        self.assertEqual(code, 1)
        self.assertIn("bad-bytes", output)

    def test_an_unexpected_file_in_the_media_tree_is_refused(self):
        state, media = self.restored()
        (media / "npp/abcd1234/notes.txt").write_text("x")
        code, output = run("--state", state, "--media", media)
        self.assertEqual(code, 1)
        self.assertIn("bad-name", output)

    def test_a_link_inside_the_media_tree_is_refused_even_to_a_matching_file(self):
        state, media = self.restored()
        outside = self.tmp / "outside-copy.png"
        outside.write_bytes(self.card)
        target = media / "npp/abcd1234" / f"card-{sha(self.card)}.png"
        target.unlink()
        target.symlink_to(outside)
        code, output = run("--state", state, "--media", media)
        self.assertEqual(code, 1)
        self.assertIn("link", output)
        self.assertIn("attachments-missing-1", output)  # the link is never followed or counted as restored

    def test_a_linked_media_root_state_dir_or_transcript_is_refused(self):
        state, media = self.restored()
        linked_media = self.tmp / "media-link"
        linked_media.symlink_to(media)
        linked_state = self.tmp / "state-link"
        linked_state.symlink_to(state)
        other = private_dir(self.tmp, "other")
        shutil.copyfile(state / transcript.NAME, self.tmp / "t.sqlite3")
        (other / transcript.NAME).symlink_to(self.tmp / "t.sqlite3")
        for args in (("--state", state, "--media", linked_media), ("--state", linked_state, "--media", media),
                     ("--state", other, "--media", media)):
            code, output = run(*args)
            self.assertEqual(code, 1, args)
            self.assertTrue(output.startswith("FAIL restored_chat_view"), output)
            self.assertQuiet(output)

    def test_open_modes_are_refused(self):
        state, media = self.restored()
        os.chmod(state / transcript.NAME, 0o644)
        self.assertEqual(run("--state", state, "--media", media)[0], 1)
        os.chmod(state / transcript.NAME, 0o600)
        os.chmod(media, 0o755)
        code, output = run("--state", state, "--media", media)
        self.assertEqual(code, 1)
        self.assertIn("media-not-private", output)

    def test_stray_arguments_are_not_echoed(self):
        code, output = run("--state", "fixture-private-path", "--nope", "fixture-secret")
        self.assertEqual(code, 2)
        self.assertNotIn("fixture-secret", output)
        self.assertNotIn("fixture-private-path", output)

    def test_local_page_is_private_holds_the_pictures_and_stays_out_of_git(self):
        state, media = self.restored()
        page = private_dir(self.tmp, "view") / "chat.html"
        code, output = run("--state", state, "--media", media, "--page", page)
        self.assertEqual(code, 0, output)
        self.assertQuiet(output)
        self.assertEqual(stat.S_IMODE(page.stat().st_mode), 0o600)
        html = page.read_text(encoding="utf-8")
        self.assertEqual(html.count("<img "), 2)
        self.assertEqual([html.index(t) for t in TEXTS], sorted(html.index(t) for t in TEXTS))  # same order as the store
        self.assertIn(base64.b64encode(self.card).decode(), html)
        # The page never lands in the repository or in the restored roots, and an existing file is kept without --force.
        for bad in (REPO / ".restored-view-test.html", state / "page.html", media / "page.html"):
            code, output = run("--state", state, "--media", media, "--page", bad)
            self.assertEqual(code, 1, bad)
            self.assertFalse(bad.exists())
        code, _ = run("--state", state, "--media", media, "--page", page)
        self.assertEqual(code, 1)
        self.assertEqual(run("--state", state, "--media", media, "--page", page, "--force")[0], 0)

    def test_a_link_in_any_ancestor_of_the_state_or_media_path_is_refused(self):
        state, media = self.restored()
        hop = self.tmp / "hop"
        hop.symlink_to(self.tmp)
        for args in (("--state", hop / state.name, "--media", media), ("--state", state, "--media", hop / media.name)):
            code, output = run(*args)
            self.assertEqual(code, 1, args)
            self.assertTrue(output.startswith("FAIL restored_chat_view"), output)
            self.assertQuiet(output)

    @unittest.skipIf(os.getuid() == 0, "root reads any folder")
    def test_an_unreadable_media_folder_fails_closed(self):
        state, media = self.restored()
        locked = media / "npp/abcd1234"
        os.chmod(locked, 0)
        self.addCleanup(os.chmod, locked, 0o700)
        code, output = run("--state", state, "--media", media)
        self.assertEqual(code, 1)
        self.assertIn("media-unreadable", output)

    def test_a_store_of_the_wrong_shape_is_a_label_not_a_traceback(self):
        partial = "CREATE TABLE events(id INTEGER PRIMARY KEY, attachments TEXT NOT NULL)"
        for name, ddl in (("no-id", "CREATE TABLE events(utc TEXT, attachments TEXT)"), ("no-table", "CREATE TABLE other(a)"),
                          ("empty-no-columns-needed", "CREATE TABLE events(a)"), ("empty-id-attachments-only", partial),
                          ("bad-json", None)):
            state = private_dir(self.tmp, name)
            db = sqlite3.connect(state / transcript.NAME)
            if ddl:
                db.execute(ddl)
                if name == "no-id":
                    db.execute("INSERT INTO events VALUES ('2000-01-01', '[]')")
            else:
                db.executescript(transcript.SCHEMA)
                db.execute("INSERT INTO events(utc,chat,sender,direction,kind,text,attachments,disposition)"
                           " VALUES('u','c','s','in','text','t','not json','queued')")
            db.commit()
            db.close()
            os.chmod(state / transcript.NAME, 0o600)
            code, output = run("--state", state)
            self.assertEqual((code, output.strip()), (1, "FAIL restored_chat_view transcript-unsafe-or-unreadable"), name)

    def test_a_png_named_picture_with_other_bytes_is_never_counted_as_restored(self):
        state, media = self.restored()
        fake = b"not-a-picture"
        transcript.append(self.state, **transcript.event(CHAT, "hass", "out", "photo", TEXTS[2], attachments=[sha(fake)]))
        shutil.copyfile(self.state / transcript.NAME, state / transcript.NAME)
        (media / "npp/abcd1234" / f"card-{sha(fake)}.png").write_bytes(fake)  # right digest, not a picture
        code, output = run("--state", state, "--media", media, "--page", self.tmp / "p.html")
        self.assertEqual(code, 1)
        self.assertIn("bad-bytes", output)
        self.assertIn("attachments-missing-1", output)
        self.assertFalse((self.tmp / "p.html").exists())

    def test_no_page_is_written_when_a_check_fails(self):
        state, media = self.restored()
        (media / "npp/abcd1234" / f"card-{sha(self.card)}.png").unlink()
        page = private_dir(self.tmp, "view") / "chat.html"
        self.assertEqual(run("--state", state, "--media", media, "--page", page)[0], 1)
        self.assertFalse(page.exists())

    def with_editor_shot(self, data=None):
        """A restored state whose transcript also names an editor preview kept under state/screenshots (named by change id)."""
        shot = PNG + b"editor-preview" if data is None else data
        transcript.append(self.state, **transcript.event(CHAT, "hass", "out", "photo", "fixture-preview-private",
                                                          attachments=[sha(PNG + b"editor-preview")]))
        state, media = self.restored()
        shots = private_dir(state, "screenshots")
        (shots / "chg-0123456789ab-proposal.png").write_bytes(shot)
        os.chmod(shots / "chg-0123456789ab-proposal.png", 0o600)
        return state, media, shots

    def test_an_editor_preview_in_the_state_screenshots_dir_counts_as_restored(self):
        state, media, _shots = self.with_editor_shot()
        with contextlib.redirect_stdout(io.StringIO()) as out:
            transcript.main(["export", "--state", str(self.state), "--since", "2000-01-01"])
        ref = self.tmp / "with-shot.jsonl"
        ref.write_text(out.getvalue(), encoding="utf-8")
        code, output = run("--state", state, "--media", media, "--reference", ref)
        self.assertEqual((code, output.strip()), (0, "PASS restored_chat_view events=4 attachments=3 linked=3 reference=matched"))
        self.assertQuiet(output)
        page = private_dir(self.tmp, "view") / "chat.html"
        self.assertEqual(run("--state", state, "--media", media, "--page", page)[0], 0)
        self.assertEqual(page.read_text(encoding="utf-8").count("<img "), 3)
        self.assertEqual(run("--state", state)[0], 1)  # without --media the media pictures are still unlinked

    def test_a_missing_or_changed_editor_preview_is_not_verified(self):
        state, media, shots = self.with_editor_shot(b"not-a-picture")
        code, output = run("--state", state, "--media", media)
        self.assertEqual(code, 1)
        self.assertIn("bad-bytes", output)
        self.assertIn("attachments-missing-1", output)
        (shots / "chg-0123456789ab-proposal.png").unlink()
        code, output = run("--state", state, "--media", media)
        self.assertEqual(code, 1)
        self.assertIn("attachments-missing-1", output)
        self.assertQuiet(output)

    def test_a_linked_editor_preview_or_screenshots_dir_is_refused(self):
        state, media, shots = self.with_editor_shot()
        outside = self.tmp / "outside-preview.png"
        outside.write_bytes(PNG + b"editor-preview")
        (shots / "chg-0123456789ab-proposal.png").unlink()
        (shots / "chg-0123456789ab-proposal.png").symlink_to(outside)
        code, output = run("--state", state, "--media", media)
        self.assertEqual(code, 1)
        self.assertIn("link", output)
        self.assertIn("attachments-missing-1", output)  # never followed, never counted
        shutil.rmtree(shots)
        shots.symlink_to(self.tmp)
        code, output = run("--state", state, "--media", media)
        self.assertEqual(code, 1)
        self.assertIn("link", output)
        self.assertQuiet(output)


if __name__ == "__main__":
    unittest.main()
