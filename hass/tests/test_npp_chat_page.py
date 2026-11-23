"""Exercise the offline chat-page CLI with synthetic transcript and image copies."""

import base64
import hashlib
from html import escape, unescape
from html.parser import HTMLParser
import json
import os
from pathlib import Path
import re
import shutil
import stat
import subprocess
import sys
import tempfile
import unittest

from hass.npp.evidence import Evidence


SCRIPT = Path(__file__).resolve().parents[2] / "scripts/hass/npp_chat_page.py"
CHAT = "fixture-chat-private"
SENDER = "fixture-sender-private"
TEXT = "fixture-text-private"
PNG = base64.b64decode(
    "iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAQAAAC1HAwCAAAAC0lEQVR42mP8/x8AAwMCAO+aB9sAAAAASUVORK5CYII="
)
JPEG = b"\xff\xd8\xff\xe0fixture-photo\xff\xd9"  # Signature fixture; no decoder needed.


class PageTags(HTMLParser):
    def __init__(self, page):
        super().__init__()
        self.tags = []
        self.feed(page)

    def handle_starttag(self, tag, attrs):
        self.tags.append((tag, dict(attrs)))

    def attrs(self, tag):
        return [attrs for name, attrs in self.tags if name == tag]


def event(id=1, **changes):
    return dict(id=id, utc="2000-01-01T00:00:00Z", chat=CHAT, sender=SENDER,
                direction="in", kind="text", text=TEXT, attachments=[], disposition="queued",
                provider_id=None, reply_to=None, draft_code=None) | changes


# sha256 of the page HRM-01 (d69c1333, before --receipts existed) wrote for the C10 fixture.
PAGE_BEFORE_RECEIPTS = "c67cf1b32b857072bb3e3ed4413e42ee51fde3db24622631bb91b63d3b1d1af4"


def card(tag):
    return PNG + tag  # Still a PNG by signature; each tag gives a distinct card digest.


def version(n, card_sha, state, delivered_at=None):
    # The row shape hass/npp/job.py write_receipts stores under "versions".
    return dict(n=n, listing_sha="0" * 64, image_variant=None, image_sha256=None, change_id=None,
                draft_hash=None, card_png_sha=card_sha, outbox_id=n, delivered_at=delivered_at,
                state=state)


def labels(page):
    """Version labels of each message bubble, in page order."""
    bubbles = page.split("</main>", 1)[0].split("<article")[1:]
    return [re.findall(r'<div class="version">([^<]*)</div>', bubble) for bubble in bubbles]


def boxes(page):
    """Per-job receipt boxes as (job, bad, items), in page order."""
    return [(job, bool(bad), re.findall(r"<li>([^<]*)</li>", items)) for bad, job, items in
            re.findall(r'<section class="receipt( bad)?" data-job="([0-9a-f]+)">(.*?)</section>', page, re.S)]


class NppChatPageTests(unittest.TestCase):
    def setUp(self):
        temporary = tempfile.TemporaryDirectory()
        self.addCleanup(temporary.cleanup)
        self.root = Path(temporary.name).resolve()
        self.inputs = self.root / "input"
        self.inputs.mkdir()
        self.copy = self.inputs / "pictures"
        self.copy.mkdir()
        self.export = self.inputs / "events.jsonl"
        self.out = self.root / "page.html"
        self.export_events(event())

    def export_events(self, *events):
        self.export.write_text("".join(json.dumps(row) + "\n" for row in events), encoding="utf-8")

    def run_cli(self, *args, out=None, umask=-1, required=True):
        command = [sys.executable, "-B", str(SCRIPT)]
        if required:
            command += ["--export", str(self.export), "--attachments", str(self.copy),
                        "--out", str(self.out if out is None else out)]
        result = subprocess.run([*command, *args], cwd=self.root, capture_output=True,
                                text=True, timeout=10, umask=umask)
        for private in (str(self.root), str(SCRIPT), CHAT, SENDER, TEXT):
            self.assertNotIn(private, result.stdout + result.stderr)
        return result

    def assert_pass(self, result, count=1):
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        self.assertEqual(result.stderr, "")
        self.assertEqual(result.stdout.splitlines()[-1], f"PASS npp_chat_page {count} events")
        return self.out.read_text(encoding="utf-8")

    def assert_fail(self, result, reason):
        self.assertEqual((result.returncode, result.stderr), (1, ""))
        self.assertEqual(result.stdout.splitlines(), [f"FAIL {reason}", "FAIL npp_chat_page"])

    def attachment(self, data, filename="{sha}", contents=None):
        sha = hashlib.sha256(data).hexdigest()
        (self.copy / filename.format(sha=sha)).write_bytes(data if contents is None else contents)
        return sha

    def receipt(self, job, versions, **changes):
        # Pass evidence=... to add that key; leave it out for a receipt written before HRM-03.
        folder = self.receipts / job
        folder.mkdir(parents=True, exist_ok=True)
        record = dict(job_id=job, state="open", versions=versions) | changes
        (folder / "receipt.json").write_text(json.dumps(record), encoding="utf-8")

    @staticmethod
    def tree(root):
        return {path: (path.lstat().st_mtime_ns, os.readlink(path) if path.is_symlink()
                       else path.read_bytes() if path.is_file() else None)
                for path in (root, *root.rglob("*"))}

    def test_c1_page_order_and_escape(self):
        # A reader that trusts file order, drops a chat filter, or treats text as markup fails here.
        self.export_events(event(10, direction="out", text='last <img src="nope"> & "quote"'),
                           event(4, chat="fixture-other-chat", text="unselected message"),
                           event(2, utc="<when>", sender="<fixture-speaker>", text="first <script>"))
        page = self.assert_pass(self.run_cli(), count=3)
        self.assertIn("unselected message", page)
        page = self.assert_pass(self.run_cli("--chat", CHAT, "--force"), count=2)
        tags = PageTags(page)
        self.assertEqual(tags.attrs("article"), [{"class": "bubble in"}, {"class": "bubble out"}])
        self.assertLess(page.index("first &lt;script&gt;"), page.index("last &lt;img"))
        self.assertIn("&lt;fixture-speaker&gt; · &lt;when&gt;", page)
        self.assertIn("&lt;img src=&quot;nope&quot;&gt; &amp; &quot;quote&quot;", page)
        self.assertNotIn("unselected message", page)
        self.assertFalse(tags.attrs("script") or tags.attrs("img"))
        self.assertRegex(page, r"\.in\s*\{[^}]*margin-right: auto")
        self.assertRegex(page, r"\.out\s*\{[^}]*margin-left: auto")

    def test_c2_attachments_verified(self):
        # A matching name, a plausible header, or a correct hash alone is not verification.
        png = self.attachment(PNG, "card-{sha}.png")
        jpg = self.attachment(JPEG)
        self.attachment(JPEG, contents=b"bad alias")  # A bad bare file cannot mask a valid copy.
        self.attachment(JPEG, "{sha}.bin")
        bare = self.attachment(JPEG + b"bare fixture")
        wrong = self.attachment(PNG + b"expected", "{sha}.png", contents=PNG)
        not_image = self.attachment(b"<svg>not an image</svg>", "card-{sha}.png")
        truncated = self.attachment(b"\x89PNG", "{sha}.png")
        absent = "0" * 64
        missing = (wrong, not_image, truncated, absent)
        self.export_events(event(1, kind="photo", attachments=[png, jpg, bare, *missing]),
                           event(2, direction="out", attachments=[absent]))
        result = self.run_cli()
        page = self.assert_pass(result, count=2)
        tags = PageTags(page)
        images = [attrs["src"] for attrs in tags.attrs("img")]
        self.assertEqual(len(images), 3)
        for uri, mime, data in zip(images, ("png", "jpeg", "jpeg"), (PNG, JPEG, JPEG + b"bare fixture")):
            prefix, encoded = uri.split(",", 1)
            self.assertEqual(prefix, f"data:image/{mime};base64")
            self.assertEqual(base64.b64decode(encoded, validate=True), data)
        for sha in missing:
            self.assertIn(f"picture {sha[:8]} not in copy", page)
        self.assertCountEqual(result.stdout.splitlines()[:-1],
                              [f"NOTE missing-attachment {sha[:8]}" for sha in missing])
        self.assertFalse(any("href" in attrs for _, attrs in tags.tags))
        self.assertNotIn(str(self.copy), page)
        self.assertRegex(page, r"img\s*\{[^}]*max-width: 100%")

    def test_c3_markers(self):
        # Mark the actual outbound lines, not an inbound yes or the whole multi-line bubble.
        png = self.attachment(PNG, "card-{sha}.png")
        self.export_events(event(1, text="yes fade-2\nPosted: inbound"),
                           event(2, direction="out", text="Fixture edit\nReply yes fade-2, or edit.",
                                 attachments=[png]),
                           event(3, direction="out", text="Posted: https://example.invalid/card"))
        page = self.assert_pass(self.run_cli(), count=3)
        header = page.split("</header>", 1)[0]
        self.assertIn("1 messages in · 2 messages out · 1 pictures", header)
        self.assertIn('<div class="message">yes fade-2</div>', page)
        self.assertIn('<div class="message">Posted: inbound</div>', page)
        self.assertIn('<div class="message">Fixture edit</div>', page)
        self.assertIn('<div class="message marker approval">Reply yes fade-2, or edit.</div>', page)
        self.assertIn('<div class="message marker posted">Posted: https://example.invalid/card</div>', page)

    def test_c4_private_output(self):
        # A direct open can inherit a wide mode, clobber by default, or follow aliases into git.
        for umask in (0o000, 0o777):
            with self.subTest(umask=umask):
                page = self.assert_pass(self.run_cli(out=self.out.name, umask=umask))
                self.assertIn(TEXT, page)
                self.assertEqual(stat.S_IMODE(self.out.stat().st_mode), 0o600)
                self.out.unlink()
        self.out.write_bytes(b"prior fixture output")
        self.out.chmod(0o644)
        self.assert_fail(self.run_cli(), "output exists (use --force)")
        self.assertEqual(self.out.read_bytes(), b"prior fixture output")
        self.assertEqual(stat.S_IMODE(self.out.stat().st_mode), 0o644)
        self.assert_pass(self.run_cli("--force"))
        self.assertEqual(stat.S_IMODE(self.out.stat().st_mode), 0o600)
        for linked in (False, True):
            with self.subTest(linked=linked):
                worktree = self.root / ("linked" if linked else "checkout")
                nested = worktree / "nested" / "deep"
                nested.mkdir(parents=True)
                marker = worktree / ".git"
                if linked:
                    marker.write_text("gitdir: synthetic\n", encoding="utf-8")
                else:
                    marker.mkdir()
                alias = self.root / f"alias-{linked}"
                alias.symlink_to(nested, target_is_directory=True)
                for parent in (nested, alias):
                    dest = parent / "private.html"
                    self.assert_fail(self.run_cli("--force", out=dest), "output inside git worktree")
                    self.assertFalse(dest.exists())
        leaf = self.root / "linked-output.html"
        leaf.symlink_to(self.out)
        saved = self.out.read_bytes()
        self.assert_fail(self.run_cli("--force", out=leaf), "output must be a regular file")
        self.assertTrue(leaf.is_symlink())
        self.assertEqual(self.out.read_bytes(), saved)

    def test_c5_bad_input(self):
        # Bad rows after a good row must not leave even a partial private page.
        self.export.unlink()
        self.assert_fail(self.run_cli(), "export unavailable")
        self.assertFalse(self.out.exists())
        good = json.dumps(event()) + "\n"
        for bad, reason in ((TEXT, "invalid export JSON"), ('{"id":2}', "missing-field utc line 2"),
                            ("[]", "invalid event"),
                            (json.dumps(event(2, attachments=["../not-a-hash"])), "invalid event")):
            with self.subTest(reason=reason):
                self.export.write_text(good + bad + "\n", encoding="utf-8")
                self.assert_fail(self.run_cli(), reason)
                self.assertFalse(self.out.exists())
        # A renderer that checks only fields it displays can miss disposition.
        for field in ("id", "utc", "chat", "sender", "direction", "kind", "text",
                      "attachments", "disposition"):
            with self.subTest(missing=field):
                incomplete = event(2)
                del incomplete[field]
                self.export_events(event(), incomplete)
                self.assert_fail(self.run_cli(), f"missing-field {field} line 2")
                self.assertFalse(self.out.exists())

    def test_c6_read_only(self):
        # Neither rendering nor a forced output pointed back into a copy may mutate it.
        self.copy = self.copy.rename(self.root / "pictures")  # Check each input root independently.
        png = self.attachment(PNG, "{sha}.png")
        self.export_events(event(kind="photo", attachments=[png]))

        def snapshot():
            return {path.relative_to(self.root): (path.stat().st_mtime_ns,
                     path.read_bytes() if path.is_file() else None)
                    for root in (self.inputs, self.copy) for path in (root, *root.rglob("*"))}

        before = snapshot()
        self.assert_pass(self.run_cli())
        self.assertEqual(snapshot(), before)
        for dest in (self.export, self.copy / "new.html", self.copy / f"{png}.png"):
            with self.subTest(forced=dest.relative_to(self.root)):
                self.assert_fail(self.run_cli("--force", out=dest), "out-inside-input")
                self.assertEqual(snapshot(), before)

        # An exact-file check misses sibling output, and a lexical check misses aliases.
        alias = self.root / "input-alias"
        alias.symlink_to(self.inputs, target_is_directory=True)
        for dest in (self.inputs / "page.html", self.copy / "page.html",
                     self.copy / ".." / "input" / "dotdot.html", alias / "aliased.html"):
            with self.subTest(destination=dest.relative_to(self.root)):
                self.assert_fail(self.run_cli(out=dest), "out-inside-input")
                self.assertFalse(dest.exists())
                self.assertEqual(snapshot(), before)

    def test_c7_usage(self):
        # Usage failures must not be mistaken for input failures or echo private values.
        for args in ((), ("--unrecognized", CHAT, str(self.root)), ("--chat",)):
            with self.subTest(args=args):
                result = self.run_cli(*args, required=bool(args))
                self.assertEqual((result.returncode, result.stdout), (2, ""))
                self.assertIn("usage: npp_chat_page", result.stderr)
                self.assertFalse(self.out.exists())

    def test_c8_version_labels(self):
        # Only an exact, unambiguous-or-flagged full card digest on an outbound bubble earns a label:
        # not a near digest, an inbound copy, a card-less version, or a receipt that fails its checks.
        self.receipts = self.root / "receipts"
        first, second, final, other, twin, near, orphan = (
            self.attachment(card(tag.encode()), "card-{sha}.png") for tag in "1234567")
        at = "2000-01-01T00:0{}:00+00:00".format
        self.receipt("abcd", [version(4, None, "building"), version(3, final, "approved", at(3)),
                              version(2, second, "superseded", at(2)), version(1, first, "superseded")])
        self.receipt("beef", [version(1, other, "delivered", at(4))])
        self.receipt("cafe", [version(1, twin, "superseded", at(5)), version(2, twin, "delivered", at(6))])
        self.receipt("d00d", [version(1, near[:-1] + ("1" if near[-1] == "0" else "0"), "delivered", at(7))])
        self.receipt("dead", [version(1, orphan, "delivered", at(8))], job_id="beef")  # Copied under another job.
        self.receipt("0bad", [version(1, orphan, "sent", at(8))])
        self.receipt("1bad", [version(1, orphan, "delivered", at(8)), version(1, orphan, "delivered", at(8))])
        self.receipt("2bad", [version(1, orphan.upper(), "delivered", at(8))])
        self.receipt("3bad", [version(1, orphan, "delivered", "2000-01-01T00:08:00")])  # No zone.
        (self.receipts / "4bad").mkdir()  # A link out of the copy, even to a well-formed receipt.
        outside = self.root / "outside-receipt.json"
        outside.write_text(json.dumps(dict(job_id="4bad", versions=[version(1, orphan, "delivered", at(8))])),
                           encoding="utf-8")
        (self.receipts / "4bad" / "receipt.json").symlink_to(outside)
        (self.receipts / "notes").mkdir()  # Not a job folder: ignored.
        self.export_events(event(1, direction="out", attachments=[first]),
                           event(2, direction="out", attachments=[second]),
                           event(3, kind="photo", attachments=[second]),
                           event(4, direction="out", attachments=[final, other]),
                           event(5, direction="out", attachments=[twin]),
                           event(6, direction="out", attachments=[near, orphan]))
        before = self.tree(self.receipts)
        result = self.run_cli("--receipts", str(self.receipts))
        page = self.assert_pass(result, count=6)
        self.assertEqual(labels(page), [
            ["abcd-1 superseded · not delivered"],
            ["abcd-2 superseded · 2000-01-01T00:02:00+00:00"],
            [],
            ["abcd-3 approved · 2000-01-01T00:03:00+00:00", "beef-1 delivered · 2000-01-01T00:04:00+00:00"],
            ["cafe-1 superseded · 2000-01-01T00:05:00+00:00", "cafe-2 delivered · 2000-01-01T00:06:00+00:00"],
            [],
        ])
        bubbles = page.split("<article")[1:]
        self.assertIn("card matches 2 versions", bubbles[4])
        self.assertEqual(page.count("card matches"), 1)
        bad = [f"{n}bad" for n in range(5)] + ["dead"]
        self.assertEqual(result.stdout.splitlines()[:-1],
                         [f"NOTE bad-receipt {job}" for job in bad] + [f"NOTE ambiguous-card {twin[:8]}"])
        self.assertEqual([(job, flag) for job, flag, _ in boxes(page)],
                         [(job, job in bad) for job in sorted([*bad, "abcd", "beef", "cafe", "d00d"])])
        self.assertTrue(all(items == ["receipt unreadable"] for job, flag, items in boxes(page) if flag))
        self.assertEqual(self.tree(self.receipts), before)
        for dest in (self.receipts / "page.html", self.receipts / "abcd" / "page.html"):
            with self.subTest(destination=dest.relative_to(self.root)):
                self.assert_fail(self.run_cli("--receipts", str(self.receipts), "--force", out=dest),
                                 "out-inside-input")
                self.assertEqual(self.tree(self.receipts), before)
        self.assert_fail(self.run_cli("--receipts", str(self.root / "absent"), "--force"), "receipts unavailable")

    def test_c9_evidence_box(self):
        # A box shows validated evidence only; an invalid record is named, never partly shown.
        self.receipts = self.root / "receipts"
        full = Evidence()
        for code in ("plain-photo", "no-research"):
            full.fallback(code)
        full.approval(2, "Mike", "2000-01-01T00:00:00Z", "chg-1", "a" * 64)
        full.publish("chg-1", "b" * 40, "seen")
        hidden = Evidence()
        hidden.fallback("fixture-hidden")
        hidden.publish("chg-9", None, "pending")
        broken = hidden.doc()
        broken["publish"]["live_verify"] = "<b>fixture-unvalidated</b>"
        self.receipt("abcd", [], evidence=full.doc())
        self.receipt("beef", [], evidence=Evidence().doc())
        self.receipt("cafe", [], evidence=broken)
        self.receipt("d00d", [])
        self.receipt("e0e0", [], evidence=None)
        result = self.run_cli("--receipts", str(self.receipts))
        page = self.assert_pass(result)
        self.assertEqual(result.stdout.splitlines(), ["NOTE bad-evidence cafe", "PASS npp_chat_page 1 events"])
        self.assertEqual(boxes(page), [
            ("abcd", False, ["fallbacks: no-research, plain-photo", "approval role: Mike",
                             "publish change id: chg-1", "live_verify: seen"]),
            ("beef", False, ["fallbacks: none", "approval role: none", "publish change id: none",
                             "live_verify: none"]),
            ("cafe", True, ["bad evidence: failed validation"]),
            ("d00d", False, ["no evidence recorded"]),
            ("e0e0", False, ["no evidence recorded"]),
        ])
        for unvalidated in ("fixture-hidden", "chg-9", "fixture-unvalidated", "pending"):
            self.assertNotIn(unvalidated, page)

    def test_c11_without_evidence_module(self):
        # Isolate the CLI from the upstream module as on main before HRM-03.
        root = self.root / "isolated"
        script = root / "scripts/hass/npp_chat_page.py"
        script.parent.mkdir(parents=True)
        shutil.copyfile(SCRIPT, script)
        package = root / "hass/npp"
        package.mkdir(parents=True)
        (root / "hass/__init__.py").touch()
        (package / "__init__.py").touch()
        command = [sys.executable, "-I", str(script), "--export", str(self.export),
                   "--attachments", str(self.copy), "--out", str(self.out)]
        result = subprocess.run(command, cwd=self.root, capture_output=True, text=True, timeout=10)
        self.assert_pass(result)
        self.out.unlink()
        self.receipts = self.root / "receipts"
        self.receipt("abcd", [], evidence={"private": "not validated"})
        result = subprocess.run([*command, "--receipts", str(self.receipts)], cwd=self.root,
                                capture_output=True, text=True, timeout=10)
        self.assert_fail(result, "evidence validator unavailable")
        self.assertFalse(self.out.exists())

    def test_c10_no_receipts_unchanged(self):
        # Pinned to HRM-01's own bytes for this fixture, so any leak of receipt markup or CSS fails.
        png = self.attachment(PNG, "card-{sha}.png")
        jpg = self.attachment(JPEG)
        self.export_events(event(1, kind="photo", attachments=[jpg]),
                           event(2, direction="out", text="Fixture card\nReply yes abcd-1, or edit.",
                                 attachments=[png, "0" * 64]),
                           event(3, direction="out", text="Posted: https://example.invalid/card"))
        result = self.run_cli()
        self.assert_pass(result, count=3)
        self.assertEqual(result.stdout, "NOTE missing-attachment 00000000\nPASS npp_chat_page 3 events\n")
        self.assertEqual(hashlib.sha256(self.out.read_bytes()).hexdigest(), PAGE_BEFORE_RECEIPTS)

    def test_c11_redact_text(self):
        # Scrubbing only incoming messages or escaping before scrubbing leaks one of these lines.
        from scripts.hass.npp_review_export import redact

        incoming = 'Fixture caption <mark> & "$74.32"\nMailbox: redaction@example.invalid'
        outgoing = "Reply yes fade-2\nPosted: https://example.invalid/redaction"
        self.export_events(event(text=incoming), event(2, direction="out", text=outgoing))
        page = self.assert_pass(self.run_cli("--redact"), count=2)
        messages = re.findall(r'<div class="message[^"]*">([^<]*)</div>', page)
        self.assertEqual(messages, [escape(line) for text in (incoming, outgoing)
                                    for line in redact(text).split("\n")])
        for marker in ('class="message marker approval"', 'class="message marker posted"',
                       "&lt;money&gt;", "&lt;email&gt;", "&lt;url&gt;"):
            self.assertIn(marker, page)
        self.assertFalse(PageTags(page).attrs("mark"))

    def test_c12_photos_dropped(self):
        # A MIME-only restriction leaks inbound PNG photos; a digest-only cache can re-show a card inbound.
        photo = self.attachment(JPEG)
        owner_png = self.attachment(card(b"fixture surroundings"), "{sha}.png")
        public_png = self.attachment(PNG, "card-{sha}.png")
        missing = "f" * 64
        self.export_events(event(1, direction="out", attachments=[public_png]),
                           event(2, kind="photo", attachments=[photo, owner_png, public_png, missing]))
        result = self.run_cli("--redact")
        page = self.assert_pass(result, count=2)
        self.assertEqual(page.count("Owner photo omitted"), 4)
        (image,) = PageTags(page).attrs("img")
        prefix, encoded = image["src"].split(",", 1)
        self.assertEqual(prefix, "data:image/png;base64")
        self.assertEqual(base64.b64decode(encoded, validate=True), PNG)
        self.assertIn("1 messages in · 1 messages out · 1 pictures", page)
        self.assertEqual(result.stdout, "PASS npp_chat_page 2 events\n")
        for sha in (photo, owner_png, missing):
            self.assertNotIn(sha[:8], page)

    def test_c13_canaries(self):
        # Check the entire artifact, not just visible text: identities can leak via metadata,
        # echoed text, filtered-out senders, and escaped attributes or receipt fields.
        inbound, outbound = 'Fixture<Sender>&One', "Fixture-Hass-Sender"
        other_chat, other_sender = "fixture-other-strasse", "Ｆixture-Other-Actor"
        # re.I misses multi-character case folds in either direction; a folded
        # offset applied directly to the original text would corrupt the cue.
        unicode_sender = "Fixture-Straße-Sender"
        legacy_echo = outbound.replace("i", "ı")  # Keep the previous re.I coverage too.
        email, url, address = ("canary@example.invalid", "https://example.invalid/private-canary",
                               "42 Imaginary Street")
        phone, amount, count = "202-555-0148", "73.38", "2193"
        at = "2098-02-03T04:05:06+00:00"
        job = "c13cafe"
        public_png = self.attachment(PNG, "card-{sha}.png")
        self.export_events(
            event(2, direction="out", sender=outbound, utc=at, attachments=[public_png], text=(
                f"Public reply cue\nEcho {inbound} {outbound} {legacy_echo} {CHAT.upper()} "
                f"{other_chat} fixture-other-actor\n"
                f"Maß! {unicode_sender.upper()} / Fixture-Other-Straße! Keep Case\n"
                f"Mailbox: {email}\nPosted: {url}\nShip to: {address}\nCall: {phone}")),
            event(1, sender=inbound, utc=at, text=f"Public caption cue\nCost ${amount}\nCount {count}",
                  provider_id="fixture-canary-provider", reply_to="fixture-canary-reply",
                  draft_code="fixture-canary-draft", disposition="fixture-canary-disposition"),
            event(3, chat=other_chat, sender=other_sender, text="unselected fixture cue"),
            event(4, sender=unicode_sender, text="Another public cue"))
        self.receipts = self.root / "receipts"
        evidence = Evidence()
        evidence.fallback("fixture-other-actor")
        self.receipt(job, [version(1, public_png, "approved", at)],
                     evidence=evidence.doc(), extra="fixture-canary-receipt")
        for show_all in (True, False):
            with self.subTest(show_all=show_all):
                args = () if show_all else ("--chat", CHAT, "--force")
                result = self.run_cli("--redact", "--receipts", str(self.receipts), *args)
                page = self.assert_pass(result, count=4 if show_all else 3)
                self.assertLess(page.index("Public caption cue"), page.index("Public reply cue"))
                self.assertEqual("unselected fixture cue" in page, show_all)
                self.assertIn("fallbacks: &lt;id&gt;", page)
                self.assertIn("1-1 approved · delivered", page)
                self.assertIn("Redacted Hass conversation", page)
                self.assertFalse(PageTags(page).attrs("a"))
                surface = (unescape(page) + result.stdout + result.stderr).casefold()
                for canary in (unicode_sender, other_chat, CHAT, inbound, outbound, legacy_echo,
                               other_sender, "fixture-other-actor",
                               email, url, "private-canary", address, phone, amount, count, at, job,
                               "fixture-canary-", str(self.root)):
                    self.assertNotIn(canary.casefold(), surface)
                self.assertIn("Maß! &lt;id&gt; / &lt;id&gt;! Keep Case", page)


if __name__ == "__main__":
    unittest.main()
