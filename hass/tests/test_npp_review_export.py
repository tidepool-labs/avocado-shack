"""Offline contract tests for the review export CLI and its shared redactor."""

import json
from pathlib import Path
import stat
import subprocess
import sys
import tempfile
import unittest

from hass.npp.evidence import Evidence
from scripts.hass.npp_review_export import redact


SCRIPT = Path(__file__).resolve().parents[2] / "scripts/hass/npp_review_export.py"
DAY = "2031-02-03"
NO_EVIDENCE = dict(stages=None, fallbacks=None, drifted_steps=None, failed_checks=None, approval_role=None)


class NppReviewExportTests(unittest.TestCase):
    def setUp(self):
        self.root = Path(self.enterContext(tempfile.TemporaryDirectory()))
        self.source = self.root / "source.jsonl"
        self.receipts = self.root / "receipts"
        self.receipts.mkdir()
        self.out = self.root / "review.jsonl"
        self.events()

    def run_cli(self, *extra, out=None):
        return subprocess.run(
            [sys.executable, "-B", str(SCRIPT), "--export", str(self.source), "--receipts", str(self.receipts),
             "--since", DAY, "--out", str(out or self.out), *extra],
            capture_output=True, text=True, check=False, timeout=15, cwd=self.root,
        )

    def assert_pass(self, result, events, jobs):
        self.assertEqual(result.returncode, 0, result.stderr or result.stdout)
        self.assertEqual(result.stderr, "")
        self.assertEqual(result.stdout.splitlines()[-1], f"PASS npp_review_export {events} events {jobs} jobs")

    def events(self, *overrides):
        with self.source.open("w", encoding="utf-8") as source:
            for override in overrides:
                event = dict(utc=f"{DAY}T08:45:00+00:00", chat="sample-chat-b", sender="sample-sender",
                             direction="in", kind="text", text="Try a shorter title", attachments=[],
                             disposition="question", provider_id="sample-provider", reply_to="sample-reply")
                source.write(json.dumps(event | override) + "\n")

    def receipt(self, job="feed", **override):
        path = self.receipts / job / "receipt.json"
        path.parent.mkdir(exist_ok=True)
        row = dict(job_id=job, state="card_out", segments=[dict(accepted_at=f"{DAY}T08:45:00+00:00",
                   ended_at=None, outcome=None)], versions=[dict(n=2, state="building", image_variant=None),
                   dict(n=1, state="delivered", image_variant="raw", image_sha256="unused-digest")])
        path.write_text(json.dumps(row | override), encoding="utf-8")
        return path

    def test_c1_shape(self):
        # C1: reject field passthrough, time/order drift, aliases sorted by ID, or flattened versions.
        self.events(dict(utc="2031-02-02T23:59:00Z", chat="old-chat"),
                    dict(kind="photo", attachments=["photo-hash-a", "photo-hash-b"]),
                    dict(chat="sample-chat-a", utc="2031-02-04T01:00:00Z", direction="out", disposition="queued"),
                    dict(direction="out", text="Use this title", disposition="queued"))
        self.receipt()
        self.assert_pass(self.run_cli(), 3, 1)
        first = dict(day=DAY, chat="chat-1", dir="in", kind="photo", text_redacted="Try a shorter title",
                     attachments=2, disposition="question")
        self.assertEqual([json.loads(line) for line in self.out.read_text().splitlines()], [
            first, first | dict(day="2031-02-04", chat="chat-2", dir="out", kind="text", attachments=0,
                                disposition="queued"),
            first | dict(dir="out", kind="text", text_redacted="Use this title", attachments=0, disposition="queued"),
            dict(job="feed", state="card_out", segments=1, versions=[dict(n=2, state="building", image_variant=None),
                 dict(n=1, state="delivered", image_variant="raw")], summary=NO_EVIDENCE | dict(
                     segment_s=[None], slow=False, edits=0, questions=0, evidence="missing")),
        ])

    def test_c2_redaction(self):
        # C2: replacing digits only leaves whole spoken amounts, contacts and street names in the review.
        reserved_phone = "(" + "202" + ") " + "555" + "-" + "0147"
        # A fixed TLD list misses bare URLs; a digit-only suffix is still a number, not a host.
        urls = ("listing.example.shop/path", "shop.example.boutique", "http://a.b.museum/x?y=1",
                "sub.domain.co.uk", "shop.example.museum:8443?mode=preview#section")
        cases = [
            ("83471", "<n>"), ("12,345.67", "<n>"), ("３９８", "<n>"), ("A892Z", "A<n>Z"),
            ("3.50", "<n>"),
            ("twenty five", "<n>"), ("three fifty", "<n>"), ("NINETY-NINE", "<n>"),
            ("half a dozen", "<n>"), ("two hundred", "<n> <n>"),
            ("3 bucks", "<n> <money>"), ("$75.41", "<money><n>"), ("USD twenty", "<money> <n>"),
            ("fake+listing@example.invalid", "<email>"),
            (reserved_phone, "<phone>"), ("+1 " + reserved_phone + " ext. 89", "<phone>"),
            ("https://listing.example.invalid/p/77?secret=sample", "<url>"),
            ("www.listing.example.invalid/p", "<url>"), ("listing.example.invalid/p", "<url>"),
            *((url, "<url>") for url in urls),
            # ASCII-only matching misses IDNs in the final label or throughout the host.
            ("shop.example.みんな/path", "<url>"), ("пример.рф/x", "<url>"),
            ("814 Quorble Wisp Street Apt B", "<address>"), ("Quorble Wisp Street", "<address>"),
            ("Use the softer title", "Use the softer title"),
        ]
        for private, expected in cases:
            with self.subTest(text=private):
                self.assertEqual(redact(private), expected)

        cost, qty = "$75.41", "twenty five"
        email, street = "fake+listing@example.invalid", "814 Quorble Wisp Street Apt B"
        chat, sender = "synthetic-chat-key", "synthetic-sender-key"
        longer_sender = sender + "-extended"
        path_url = f"listing.example.shop/{chat}/{sender}"
        self.events(dict(chat=chat, sender=sender, text=f"cost {cost}; qty {qty}; call {reserved_phone}; "
                         f"email {email}; {street}", cost=cost, quantity=qty),
                    dict(chat=chat, sender="sample-bot", direction="out", text=f"Review {chat}; note from {sender}."),
                    # Token-boundary checks miss identity echoes in surrounding text and metadata.
                    dict(chat=chat, sender=longer_sender, kind=f"pre{chat.upper()}post",
                         disposition=f"{sender}post pre{chat}",
                         text=f"pre{sender.upper()}post {longer_sender}'s path/{chat} {chat}@example.invalid {path_url}"))
        self.receipt(cost=cost, quantity=qty, chat=chat, sender=sender,
                     segments=[dict(contact=email, address=street)])
        result = self.run_cli()
        self.assert_pass(result, 3, 1)
        rendered = self.out.read_bytes()
        output_bytes = (rendered + result.stdout.encode() + result.stderr.encode()).lower()
        for canary in (cost, "75.41", qty, reserved_phone, email, street, "Quorble Wisp", chat, sender,
                       longer_sender, path_url, *urls):
            with self.subTest(canary=canary):
                self.assertNotIn(canary.encode().lower(), output_bytes)
        one, two, three, _ = map(json.loads, rendered.splitlines())
        self.assertEqual(one["text_redacted"], "cost <money><n>; qty <n>; call <phone>; email <email>; <address>")
        self.assertEqual(two["text_redacted"], "Review <id>; note from <id>.")
        self.assertEqual(three["chat"], "chat-1")
        self.assertEqual(three["kind"], "pre<id>post")
        self.assertEqual(three["disposition"], "<id>post pre<id>")
        self.assertEqual(three["text_redacted"], "pre<id>post <id>'s path/<id> <email> <url>")

        # Short identities must redact echoes without breaking contacts or the emitted markers.
        for field, identity in (("sender", "email"), ("chat", "url"), ("sender", "id"), ("chat", "n")):
            with self.subTest(field=field, identity=identity):
                text = (f"{identity.upper()}; {identity}@example.invalid; "
                        f"listing.example.invalid/{identity} ; shop.example.みんな/{identity} ; "
                        f"{reserved_phone}; 3.50; five")
                self.events({field: identity, "text": text})
                self.assert_pass(self.run_cli("--force"), 1, 1)
                redacted = json.loads(self.out.read_text().splitlines()[0])["text_redacted"]
                self.assertNotIn("<<", redacted)
                self.assertEqual(redacted, "<id>; <email>; <url> ; <url> ; <phone>; <n>; <n>")

    def test_c3_private_output(self):
        # C3: catch stale/wide modes, silent clobber, and a worktree reached through an alias.
        self.events({})
        self.assert_pass(self.run_cli(), 1, 0)
        self.assertEqual(stat.S_IMODE(self.out.stat().st_mode), 0o600)
        previous = self.out.read_bytes()
        self.events(dict(text="A different title"))
        result = self.run_cli()
        self.assertEqual((result.returncode, result.stdout), (1, "FAIL output-exists\n"))
        self.assertEqual(self.out.read_bytes(), previous)
        self.out.chmod(0o644)
        self.assert_pass(self.run_cli("--force"), 1, 0)
        self.assertNotEqual(self.out.read_bytes(), previous)
        self.assertEqual(stat.S_IMODE(self.out.stat().st_mode), 0o600)

        # Marker fixtures mirror normal and linked worktrees without needing Git subprocesses.
        for linked in (False, True):
            work = self.root / ("linked" if linked else "checkout")
            nested = work / "ignored"
            nested.mkdir(parents=True)
            if linked:
                (work / ".git").write_text("gitdir: ../synthetic-gitdir\n")
            else:
                (work / ".git").mkdir()
            alias = self.root / (work.name + "-alias")
            alias.symlink_to(nested, target_is_directory=True)
            for parent in (nested, alias):
                with self.subTest(parent=parent.name):
                    out = parent / "review.jsonl"
                    result = self.run_cli("--force", out=out)
                    self.assertEqual((result.returncode, result.stdout), (1, "FAIL output-in-worktree\n"))
                    self.assertFalse(out.exists())

    def test_c4_bad_receipt(self):
        # C4: an intact job still exports if a nearby receipt has the wrong shape; no receipt is repaired in place.
        good = self.receipt()
        bad = self.receipt("bade", versions=[dict(n=True, state="delivered", image_variant="raw")])
        malformed = self.receipt("dead")
        malformed.write_text("{not-json")
        self.events({})
        inputs = (good, bad, malformed, self.source)
        before = [(path.read_bytes(), path.stat().st_mtime_ns) for path in inputs]
        result = self.run_cli()
        self.assert_pass(result, 1, 1)
        self.assertEqual(result.stdout.splitlines()[:-1], ["NOTE bad-receipt bade", "NOTE bad-receipt dead"])
        self.assertEqual(json.loads(self.out.read_text().splitlines()[-1])["job"], "feed")
        self.assertEqual([(path.read_bytes(), path.stat().st_mtime_ns) for path in inputs], before)
        result = self.run_cli("--force", out=bad)
        self.assertEqual((result.returncode, result.stdout.splitlines()[-1]), (1, "FAIL output-is-input"))
        self.assertEqual(bad.read_bytes(), before[1][0])

    def test_c5_exit(self):
        # C5: distinguish a valid empty export, invalid inputs, and argument parser failures.
        self.assert_pass(self.run_cli(), 0, 0)
        self.assertEqual(self.out.read_bytes(), b"")
        self.out.unlink()
        for content in (b'{"sample-malformed"', b'[]\n', b'\xff', b'{"utc":"2031-02-03"}\n'):
            with self.subTest(content=content):
                self.source.write_bytes(content)
                result = self.run_cli()
                self.assertEqual((result.returncode, result.stdout, result.stderr), (1, "FAIL bad-export\n", ""))
                self.assertFalse(self.out.exists())
        self.source.unlink()
        result = self.run_cli()
        self.assertEqual((result.returncode, result.stdout), (1, "FAIL bad-export\n"))
        for args in (("--since", "2031-02-30"), ("--since", "20310203"), ("--unknown",)):
            with self.subTest(args=args):
                result = self.run_cli(*args)
                self.assertEqual((result.returncode, result.stdout), (2, ""))
                self.assertIn("usage:", result.stderr)
                self.assertFalse(self.out.exists())

    def jobs(self):
        return {row["job"]: row for row in map(json.loads, self.out.read_text().splitlines())}

    def test_c6_job_summary(self):
        # C6: catch counting every version (or only state "delivered") as delivered, -1 edits with none
        # delivered, ">= 75" or offset-blind slow math, any-instead-of-count questions, duplicate or
        # non-drifted steps, a later passing rerun hiding a failed check, and negative durations.
        def at(clock, zone="Z"):
            return f"{DAY}T{clock}{zone}"

        def segment(start, end, outcome):
            return dict(accepted_at=start, ended_at=end, outcome=outcome)

        def version(n, state, delivered_at=None):
            return dict(n=n, state=state, image_variant="raw", delivered_at=delivered_at)

        doc = Evidence()
        doc.stage("S1", 0, 400, "ok")
        doc.stage("S2", 400, 6400, "fallback", "label-local")
        doc.stage("S6", 6400, 81400, "fallback", "polish-late")
        doc.model("identify", "vision-pin", "vision-other")
        doc.model("copy", "copy-pin", "copy-pin")
        doc.model("identify", "vision-pin", "vision-third")
        doc.model("verify", "verify-pin", None)
        for code in ("picture-raw", "label-local", "picture-raw"):
            doc.fallback(code)
        doc.check("length", "fail")
        doc.check("length", "pass")
        doc.check("claims", "pass")
        doc.check("private-price", "fail", "no-match")
        doc.approval(4, "Mike", at("09:06:00"), "change-1", "abcdef1")
        # Newest segment and version first, as the job runner writes receipts.
        self.receipt("c0de", state="approved", evidence=doc.doc(), segments=[
            segment(at("09:10:00"), None, None),
            segment(at("09:05:00"), at("09:05:08"), "card"),
            segment(at("09:00:00"), at("09:01:15.5"), "card"),
            segment(at("00:50:00", "-08:00"), at("08:51:10"), "question"),
            segment(at("08:40:00"), at("08:40:05+00:00", ""), "question"),
        ], versions=[version(5, "building"), version(4, "approved", at("09:05:09")),
                     version(3, "superseded", at("09:01:16")), version(2, "superseded"),
                     version(1, "superseded", at("08:52:00"))])
        self.receipt("beef", versions=[version(1, "queued")],
                     segments=[segment(at("10:00:00"), at("10:01:15"), "card")])
        self.receipt("cafe", evidence=Evidence().doc())
        self.receipt("dead", segments=[segment(at("10:00:05"), at("10:00:00"), "card")])
        result = self.run_cli()
        self.assert_pass(result, 0, 3)
        self.assertEqual(result.stdout.splitlines()[:-1], ["NOTE bad-receipt dead"])
        jobs = self.jobs()
        self.assertEqual(sorted(jobs), ["beef", "c0de", "cafe"])
        self.assertEqual(jobs["c0de"]["summary"], dict(
            segment_s=[None, 8.0, 75.5, 70.0, 5.0], slow=True,
            stages=[dict(stage="S1", ms=400, outcome="ok"), dict(stage="S2", ms=6000, outcome="fallback"),
                    dict(stage="S6", ms=75000, outcome="fallback")],
            fallbacks=["label-local", "picture-raw"], drifted_steps=["identify"],
            failed_checks=["length", "private-price"], approval_role="Mike",
            edits=2, questions=2, evidence="recorded"))
        self.assertEqual(jobs["beef"]["summary"], NO_EVIDENCE | dict(
            segment_s=[75.0], slow=False, edits=0, questions=0, evidence="missing"))
        self.assertEqual(jobs["cafe"]["summary"], dict(
            segment_s=[None], slow=False, stages=[], fallbacks=[], drifted_steps=[], failed_checks=[],
            approval_role=None, edits=0, questions=0, evidence="recorded"))

    def test_c7_bad_evidence(self):
        # C7: catch dropping the whole job, failing the run, or keeping parts of an invalid record
        # (its approval role, or a private value that the schema refused).
        good = Evidence()
        good.fallback("picture-raw")
        email = "fake+listing@example.invalid"
        private = good.doc() | dict(fallbacks=[email, "picture-raw"],
                                    approval=dict(version=1, role="G", approved_at=0, change_id="change-1",
                                                  draft_hash="abcdef1"))
        self.receipt("abcd", evidence=good.doc())
        self.receipt("babe", evidence="$75.41")
        self.receipt("bade", evidence=private)
        self.receipt("bead", evidence=dict(evidence_version=1, cost="$75.41"))
        result = self.run_cli()
        self.assert_pass(result, 0, 4)
        self.assertEqual(result.stdout.splitlines()[:-1],
                         ["NOTE bad-evidence babe", "NOTE bad-evidence bade", "NOTE bad-evidence bead"])
        jobs = self.jobs()
        self.assertEqual(jobs["abcd"]["summary"]["fallbacks"], ["picture-raw"])
        for job in ("babe", "bade", "bead"):
            with self.subTest(job=job):
                self.assertEqual(jobs[job]["versions"], jobs["abcd"]["versions"])
                self.assertEqual(jobs[job]["summary"], NO_EVIDENCE | dict(
                    segment_s=[None], slow=False, edits=0, questions=0, evidence="bad"))
        rendered = (self.out.read_bytes() + result.stdout.encode()).lower()
        for canary in (email, "75.41"):
            with self.subTest(canary=canary):
                self.assertNotIn(canary.encode(), rendered)

    def test_c8_evidence_name_redaction(self):
        # C8: schema-valid names used to bypass the export's privacy redactor.
        canaries = ("75.41", "listing.example.invalid", "usd", "three-fifty", "listing.xn--fixture-9za")
        for field in ("fallbacks", "failed_checks", "drifted_steps"):
            with self.subTest(field=field):
                doc = Evidence()
                for name in (*canaries, "label-local"):
                    if field == "fallbacks":
                        doc.fallback(name)
                    elif field == "failed_checks":
                        doc.check(name, "fail")
                    else:
                        doc.model(name, "sample-pin", "sample-other")
                self.receipt(evidence=doc.doc())
                result = self.run_cli("--force")
                self.assert_pass(result, 0, 1)
                summary = self.jobs()["feed"]["summary"]
                self.assertEqual(summary["evidence"], "recorded")
                self.assertIn("label-local", summary[field])
                output = self.out.read_text() + result.stdout + result.stderr
                for name in canaries:
                    with self.subTest(name=name):
                        self.assertNotIn(name, output)
                self.assertEqual(summary[field], ["[redacted]"] * len(canaries) + ["label-local"])


if __name__ == "__main__":
    unittest.main()
