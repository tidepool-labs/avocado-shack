"""Synthetic receipts exercising the scenario checker's file and CLI contract."""

from contextlib import redirect_stderr, redirect_stdout
import importlib.util
import io
import json
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest


SCRIPT = Path(__file__).resolve().parents[2] / "scripts/hass/pilot_scenario_check.py"
SPEC = importlib.util.spec_from_file_location("pilot_scenario_check", SCRIPT)
assert SPEC is not None and SPEC.loader is not None
CHECK = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(CHECK)
MARKER = "synthetic-private-marker"
STAMP = "2000-01-01T00:00:00+00:00"


def version(number):
    return {"version": number, "draft_hash": str(number) * 64,
            "change_id": f"{MARKER}-change-{number}", "base": f"{MARKER}-base",
            "photo_sha256": "a" * 64, "card_png_sha256": str(number + 2) * 64}


def reply(kind, *, question=None, draft=None, outbox_id=1):
    png = draft["card_png_sha256"] if draft is not None else None
    return {"kind": kind, "outbox_id": outbox_id, "question_id": question,
            "version": draft["version"] if draft is not None else None,
            "card_png_sha256": png,
            "delivery": {"state": "confirmed" if png else "untracked",
                         "png_sha256": png, "confirmed_at": STAMP if png else None}}


def segment(number, *replies):
    return {"inbound_id": f"{MARKER}-inbound-{number}", "received_at": STAMP,
            "replies": list(replies)}


def fixture(listing, price_question="ask_price"):
    v1, v2 = version(1), version(2)
    card1, card2 = reply("card", draft=v1), reply("card", draft=v2, outbox_id=2)
    versions, segments, approved = [v1], [segment(1, card1)], v1
    if listing == 2:
        segments = [segment(1, reply("question", question=price_question)),
                    segment(2, reply("card", draft=v1, outbox_id=2))]
    elif listing == 3:
        versions, segments, approved = [v1, v2], [segment(1, card1), segment(2, card2)], v2
    segments.append(segment(len(segments) + 1, reply("posted", outbox_id=3)))
    return {
        "schema": "hass-pilot-receipt/1", "listing": listing,
        "segments": segments, "versions": versions,
        "approval": {key: approved[key] for key in ("version", "draft_hash", "change_id", "base")}
        | {"inbound_id": segments[-1]["inbound_id"], "accepted_at": STAMP},
        "publish": {"change_id": approved["change_id"], "commit": "c" * 40,
                    "live_verified": True},
        "privacy": {"text": "pass", "dom": "pass", "picture": "pass"},
        "provenance": "omitted", "stops": [], "elapsed_seconds": 0,
    }


class PilotScenarioCheckTests(unittest.TestCase):
    def setUp(self):
        temp = tempfile.TemporaryDirectory()
        self.addCleanup(temp.cleanup)
        self.path = Path(temp.name) / f"{MARKER}.json"

    def invoke(self, receipt=None, *, raw=None, argv=None):
        if raw is None and receipt is not None:
            raw = json.dumps(receipt).encode("utf-8")
        if raw is not None:
            self.path.write_bytes(raw)
        stdout, stderr = io.StringIO(), io.StringIO()
        with redirect_stdout(stdout), redirect_stderr(stderr):
            status = CHECK.main([str(self.path)] if argv is None else argv)
        output = stdout.getvalue()
        self.assertEqual(stderr.getvalue(), "")
        self.assertNotIn(MARKER, output)
        if raw is not None:
            self.assertEqual(self.path.read_bytes(), raw)
        return status, output

    def assert_fails(self, receipt, *reasons):
        self.assertEqual(self.invoke(receipt), (1, "".join(f"FAIL {r}\n" for r in reasons)))

    def test_clean_listing_patterns_pass(self):
        # Dispatch must accept all three patterns and both allowed initial price IDs.
        for receipt in (fixture(1), fixture(2), fixture(2, "ask_price_unit"), fixture(3)):
            with self.subTest(listing=receipt["listing"]):
                self.assertEqual(self.invoke(receipt), (0, "PASS\n"))

    def test_listing_one_rejects_questions_anywhere_and_requires_one_version(self):
        # Looking only at the first segment would miss a question on a later inbound.
        receipt = fixture(1)
        receipt["segments"].append(segment(3, reply("question", question="ask_unit")))
        self.assert_fails(receipt, "listing-1-question")
        for versions in ([], [version(1), version(2)]):
            with self.subTest(version_count=len(versions)):
                receipt = fixture(1)
                receipt["versions"] = versions
                self.assert_fails(receipt, "listing-1-version-count")

    def test_listing_two_requires_only_one_allowed_price_question_first(self):
        # Checking only the first reply's ID would admit a card or guard alongside it.
        price = reply("question", question="ask_price")
        for first in ([], [reply("question", question="ask_unit")],
                      [reply("other", question="ask_price")],
                      [price, reply("card", draft=version(1), outbox_id=4)],
                      [price, reply("guard", outbox_id=4)]):
            with self.subTest(first=first):
                receipt = fixture(2)
                receipt["segments"][0]["replies"] = first
                self.assert_fails(receipt, "listing-2-initial-price-question")

    def test_listing_two_needs_a_later_segment_with_one_card(self):
        # Neither no card nor two cards in the only candidate segment suffices.
        for replies in ([], [reply("card", draft=version(1), outbox_id=n) for n in (2, 4)]):
            with self.subTest(card_count=len(replies)):
                receipt = fixture(2)
                receipt["segments"][1]["replies"] = replies
                self.assert_fails(receipt, "listing-2-later-card")

    def test_listing_two_rejects_repeat_even_after_the_card(self):
        # Scan every later segment and every kind, not just the card's segment or questions.
        for initial, kind in (("ask_price", "question"), ("ask_price_unit", "other")):
            with self.subTest(initial=initial, kind=kind):
                receipt = fixture(2, initial)
                receipt["segments"].append(segment(4, reply(kind, question=initial)))
                self.assert_fails(receipt, "listing-2-repeated-price-question")
        receipt = fixture(2)
        receipt["segments"].append(segment(4, reply("question", question="ask_edit_source")))
        self.assertEqual(self.invoke(receipt), (0, "PASS\n"))

    def test_listing_three_rejects_question_in_initial_segment(self):
        # A confirmed card does not excuse a question in the same initial segment.
        receipt = fixture(3)
        receipt["segments"][0]["replies"].append(reply("question", question="ask_identity"))
        self.assert_fails(receipt, "listing-3-initial-question")

    def test_listing_three_requires_both_version_rows_and_confirmed_cards(self):
        # A version row and a card reply are distinct; a nonconfirmed or mistyped reply isn't proof.
        for number in (1, 2):
            reason = f"listing-3-v{number}-delivered-card"
            receipt = fixture(3)
            del receipt["versions"][number - 1]
            self.assert_fails(receipt, reason)
            for key, value in (("kind", "other"), ("version", None), ("state", "pending"),
                               ("state", "unconfirmed"), ("state", "failed"), ("state", "untracked")):
                with self.subTest(version=number, field=key, value=value):
                    receipt = fixture(3)
                    card = receipt["segments"][number - 1]["replies"][0]
                    (card["delivery"] if key == "state" else card)[key] = value
                    self.assert_fails(receipt, reason)

    def test_listing_three_binds_confirmation_to_the_version_card_digest(self):
        # A confirmed state alone, or two agreeing hashes for another card, proves nothing.
        cases = (("no-card-hash", None, "expected"),
                 ("no-delivery-hash", "expected", None),
                 ("wrong-card-hash", "other", "expected"),
                 ("wrong-delivery-hash", "expected", "other"),
                 ("both-null", None, None),
                 ("both-for-other-version", "other", "other"))
        for number in (1, 2):
            for case, card_hash, delivered_hash in cases:
                with self.subTest(version=number, case=case):
                    receipt = fixture(3)
                    hashes = {"expected": receipt["versions"][number - 1]["card_png_sha256"],
                              "other": receipt["versions"][2 - number]["card_png_sha256"],
                              None: None}
                    card = receipt["segments"][number - 1]["replies"][0]
                    card["card_png_sha256"] = hashes[card_hash]
                    card["delivery"]["png_sha256"] = hashes[delivered_hash]
                    self.assert_fails(receipt, f"listing-3-v{number}-delivered-card")

        receipt = fixture(3)
        receipt["versions"][0]["card_png_sha256"] = "a" * 64
        card = receipt["segments"][0]["replies"][0]
        card["card_png_sha256"] = "A" * 64
        card["delivery"]["png_sha256"] = "a" * 64
        self.assertEqual(self.invoke(receipt), (0, "PASS\n"))

    def test_listing_three_reports_changed_photo_v1_publish_and_wrong_approval(self):
        # Compare the photo (not the card) hash, join publication by change ID, require v2 approval.
        receipt = fixture(3)
        receipt["versions"][1]["photo_sha256"] = "b" * 64
        self.assert_fails(receipt, "listing-3-photo-changed")
        receipt = fixture(3)
        receipt["publish"]["change_id"] = receipt["versions"][0]["change_id"]
        self.assert_fails(receipt, "listing-3-v1-published")
        receipt["approval"]["version"] = 1
        self.assert_fails(receipt, "listing-3-v1-published", "listing-3-v2-approval")
        receipt = fixture(3)
        receipt["publish"] = None
        self.assertEqual(self.invoke(receipt), (0, "PASS\n"))
        receipt["approval"] = None
        self.assert_fails(receipt, "listing-3-v2-approval")

    def test_scenario_does_not_check_delivery_or_approval_timing(self):
        # An earlier approval timestamp is the ordering checker's concern, not this one's.
        receipt = fixture(3)
        receipt["approval"]["accepted_at"] = "1999-12-31T23:59:59+00:00"
        self.assertEqual(self.invoke(receipt), (0, "PASS\n"))

    def test_malformed_receipts_have_one_redacted_diagnostic_and_exit_two(self):
        # Last-key-wins decoding, loose scalar checks, or exception logging would break this.
        self.assertEqual(self.invoke(), (2, "FAIL malformed-receipt\n"))
        marker = json.dumps(MARKER).encode()
        valid = json.dumps(fixture(3)).encode()
        for raw in (b"[" + marker + b";", b"\xff" + marker, b"[]", valid + b"{}",
                    valid.replace(b'"listing": 3', b'"listing": 3, "listing": 3'),
                    valid.replace(b'"outbox_id": 1', b'"outbox_id": 1, "outbox_id": 1'),
                    valid.replace(b'"elapsed_seconds": 0', b'"elapsed_seconds": NaN')):
            with self.subTest(raw=raw):
                self.assertEqual(self.invoke(raw=raw), (2, "FAIL malformed-receipt\n"))
        for key, bad in (("listing", True), ("listing", 1.0), ("listing", 4),
                         ("schema", MARKER), ("versions", [None]), ("approval", []),
                         ("publish", True), ("privacy", {}), ("provenance", MARKER),
                         ("stops", [None]), ("elapsed_seconds", False)):
            with self.subTest(field=key):
                self.assertEqual(self.invoke(fixture(3) | {key: bad}),
                                 (2, "FAIL malformed-receipt\n"))
        for key, bad in (("received_at", "2000-01-01T00:00:00"), ("replies", [False])):
            receipt = fixture(3)
            receipt["segments"][0][key] = bad
            self.assertEqual(self.invoke(receipt), (2, "FAIL malformed-receipt\n"))
        receipt = fixture(3)
        receipt["versions"][1]["photo_sha256"] = MARKER
        self.assertEqual(self.invoke(receipt), (2, "FAIL malformed-receipt\n"))
        del receipt["segments"]
        self.assertEqual(self.invoke(receipt), (2, "FAIL malformed-receipt\n"))
        self.assertEqual(self.invoke(argv=[MARKER, MARKER]), (2, "FAIL usage\n"))

    def test_script_entrypoint_propagates_failure_status_without_private_values(self):
        # Calling main alone would not catch a missing sys.exit or noisy script entrypoint.
        receipt = fixture(3)
        receipt["approval"]["version"] = 1
        raw = json.dumps(receipt).encode()
        self.path.write_bytes(raw)
        result = subprocess.run([sys.executable, "-B", str(SCRIPT), str(self.path)],
                                capture_output=True, text=True, timeout=10)
        self.assertEqual((result.returncode, result.stdout, result.stderr),
                         (1, "FAIL listing-3-v2-approval\n", ""))
        self.assertEqual(self.path.read_bytes(), raw)
