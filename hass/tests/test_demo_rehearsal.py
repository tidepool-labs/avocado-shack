"""HASS-DEMO-REHEARSAL-1 (A4): the owner demo script (02-DEMO-PLAN steps 1-16; steps 9-10 read the recorded till fixture, read-only) as a reproducible offline run.

hass/tests/fixtures/demo/g-demo.jsonl is replayed by scripts/hass/demo_rehearsal.py through the real Conversation, Editor,
sitegen and claims on a throwaway writer worktree with recorded interpreter replies. No model, no network, no browser.
`--live` (the GPU interpreter) is operator only and is only checked here for what it refuses.
Run: python3 -m unittest hass.tests.test_demo_rehearsal -v
"""
import copy
import importlib.util
import io
import os
import tempfile
import unittest
from contextlib import redirect_stderr, redirect_stdout
from pathlib import Path
from unittest import mock

from hass.content_model import REPO_ROOT

SCRIPT = REPO_ROOT / "scripts" / "hass" / "demo_rehearsal.py"
spec = importlib.util.spec_from_file_location("demo_rehearsal", SCRIPT)
assert spec is not None and spec.loader is not None
demo = importlib.util.module_from_spec(spec)
spec.loader.exec_module(demo)

# What 02-DEMO-PLAN promises and main does not do yet (each is a named gap, never a silent pass).
KNOWN_GAPS = {"s11-notice-live": "PLAN-11", "s14-pause-please": "QA1-02"}


class Run:
    results = None

    @classmethod
    def get(cls):
        if cls.results is None:
            world, rows = demo.load_fixture()
            cls.world, cls.rows = world, rows
            cls.results, cls.preview = demo.run(world, rows)
        return cls.results


class OfflineRehearsal(unittest.TestCase):
    def test_fixture_refuses_a_start_without_an_offset(self):
        # astimezone() on a naive datetime silently uses the host's time zone.
        with tempfile.TemporaryDirectory() as tmp:
            fixture = Path(tmp) / "clock.jsonl"
            fixture.write_text('{"world": {"start": "2026-11-16T00:30:00", "ttl_seconds": 1800}}\n', "utf-8")
            with self.assertRaises(demo.RehearsalError) as error:
                demo.load_fixture(fixture)
        self.assertEqual(str(error.exception), "fixture line 1: world.start must be an ISO time with an offset")

    def test_equivalent_aware_starts_set_the_same_shop_clock(self):
        # Offsets must not be stripped or reinterpreted as UTC (including across midnight).
        with tempfile.TemporaryDirectory() as tmp:
            fixture = Path(tmp) / "clock.jsonl"
            for start in ("2026-11-16T00:30:00Z", "2026-11-15T16:30:00-08:00", "2026-11-16T06:00:00+05:30"):
                with self.subTest(start=start):
                    fixture.write_text(f'{{"world": {{"start": "{start}", "ttl_seconds": 1800}}}}\n', "utf-8")
                    world, _ = demo.load_fixture(fixture)
                    self.assertEqual(world["start"], start)
                    shop = demo.Shop(world)
                    try:
                        self.assertEqual(shop.now.isoformat(), "2026-11-16T00:30:00+00:00")
                    finally:
                        shop.close()

    def test_every_row_passes_and_the_gaps_are_the_named_ones(self):
        results = Run.get()
        bad = [(r.row["id"], r.problems) for r in results if r.status == "FAIL"]
        self.assertEqual(bad, [])
        gaps = {r.row["id"]: r.row["known_gap"] for r in results if r.status == "GAP"}
        self.assertEqual(gaps, KNOWN_GAPS)  # a gap that now passes is reported PASS: delete its known_gap field

    def test_s02_is_code_help_with_no_known_gap_or_model_call(self):  # AV2007-04
        res = {r.row["id"]: r for r in Run.get()}["s02-what-can-you-do"]
        self.assertEqual((res.status, res.problems), ("PASS", []))
        self.assertNotIn("known_gap", res.row)
        self.assertEqual(res.row["expect"]["model_calls"], 0)

    def test_the_demo_steps_are_all_there(self):
        Run.get()
        steps = {r["step"] for r in Run.rows}
        self.assertEqual(steps, set(range(1, 17)))
        ids = {r["id"] for r in Run.rows}
        for needed in ("s16-stranger", "s14-reused-code", "s14-yes-while-paused", "s07-undo-yes", "s12-undo-yes",
                       "s09-how-many", "s09-low-stock", "s09-sold-out", "s09-plural", "s10-price", "s10-received"):
            self.assertIn(needed, ids)

    TILL = {"s09-how-many": "Hass avocado: 40 in the till.", "s09-low-stock": "Sold out: Eggs, dozen. 1 item(s) have no count in the till, so I can't tell.",
            "s09-sold-out": "No, Heirloom tomatoes is not sold out: 7.5 in the till.",
            "s09-plural": "I can't find exactly that. The closest is Hass avocado: 40 in the till.",
            "s10-price": "I can read the till but I can't change it yet.", "s10-received": "I can read the till but I can't change it yet."}

    def test_till_rows_are_exact_read_only_and_never_reach_the_model(self):
        by_id = {r.row["id"]: r for r in Run.get()}
        with mock.patch("socket.create_connection", side_effect=AssertionError("network")), \
                mock.patch("hass.clover.credential.load_token", side_effect=AssertionError("token")):
            world, rows = demo.load_fixture()
            demo.run(world, rows, only={"s09-plural"})
        for key, reply in self.TILL.items():
            with self.subTest(row=key):
                self.assertEqual(by_id[key].replies, [reply])
                self.assertEqual(by_id[key].status, "PASS", by_id[key].problems)
                expect = next(r for r in Run.rows if r["id"] == key)["expect"]
                self.assertEqual((expect["model_calls"], expect.get("commit")), (0, None))

    def test_till_rows_quote_no_price(self):
        by_id = {r.row["id"]: r for r in Run.get()}
        for key in self.TILL:
            joined = " ".join(by_id[key].replies)
            for price in ("$", "12.50", "1.50", "7.00", "11.00", "3.99"): self.assertNotIn(price, joined, key)

    def test_the_till_is_only_attached_for_till_rows(self):
        by_id = {r.row["id"]: r for r in Run.get()}
        self.assertNotEqual(by_id["s15-whats-sold-out"].disposition, "till-read")
        self.assertEqual(by_id["s15-whats-sold-out"].disposition, "answer")
        self.assertEqual(by_id["s15-whats-sold-out"].status, "PASS")
        self.assertNotIn("known_gap", by_id["s15-whats-sold-out"].row)  # AV2007-03 fixed ROUTER-15: the row PASSes now
        world, rows = demo.load_fixture()
        shop = demo.Shop(world)
        try:
            shop.say(next(r for r in rows if r["id"] == "s09-how-many"), "how many hass avocado")
            self.assertIsNone(shop.conv.till)
        finally: shop.close()

    def test_a_till_row_without_world_till_is_refused(self):
        row = '{"id": "x", "step": 9, "say": "low stock", "till": %s, "expect": {"disposition": "till-read"}}\n'
        world = '{"world": {"start": "2026-11-16T09:00:00-08:00", "ttl_seconds": 1800%s}}\n'
        for label, text in (("no world till", world % "" + row % "true"), ("till yes", world % ', "till": true' + row % '"yes"')):
            with self.subTest(label), tempfile.TemporaryDirectory() as tmp:
                bad = Path(tmp) / "bad.jsonl"
                bad.write_text(text, "utf-8")
                err = io.StringIO()
                with redirect_stderr(err), redirect_stdout(io.StringIO()): code = demo.main(["--fixture", str(bad)])
                self.assertEqual(code, 2)
                self.assertIn("fixture line 2", err.getvalue())

    def test_the_stranger_gets_no_reply_and_no_model_call(self):
        by_id = {r.row["id"]: r for r in Run.get()}
        for key in ("s16-stranger", "s16-stranger-yes"):
            self.assertEqual((by_id[key].disposition, by_id[key].replies), ("ignored", []))
        self.assertEqual(Run.rows[[r["id"] for r in Run.rows].index("s16-stranger")]["expect"]["model_calls"], 0)

    def test_undo_rows_restore_the_marked_tree_and_every_saved_change_was_checked(self):
        by_id = {r.row["id"]: r for r in Run.get()}
        undone = [r for r in Run.rows if "restores" in r]
        self.assertEqual({r["id"] for r in undone}, {"s07-undo-yes", "s12-undo-yes"})
        for row in undone: self.assertTrue(by_id[row["id"]].ok, by_id[row["id"]].problems)
        for r in Run.get():
            if r.row["expect"].get("commit"): self.assertTrue(r.checked, r.row["id"])  # the result picture was made and checked
            if r.row["expect"].get("preview", {}).get("proposal"): self.assertTrue(r.made, r.row["id"])

    def test_the_table_names_every_row_and_the_qa_id_of_a_gap(self):
        text = demo.table(Run.get(), Run.preview, live=False)
        self.assertIn("s16-stranger", text)
        self.assertIn("GAP (QA1-02)", text)
        self.assertIn("0 FAIL", text)


class RowsReallyAssert(unittest.TestCase):
    """A fixture that stopped checking would pass for ever: each mutation below must turn its row red."""

    def mutated(self, row_id, change):
        world, rows = demo.load_fixture()
        rows = [change(copy.deepcopy(r)) if r["id"] == row_id else r for r in rows]
        results, _ = demo.run(world, rows, only={row_id})
        [res] = results
        return res

    def test_a_missing_reply_fragment_fails(self):
        res = self.mutated("s01-status", lambda r: {**r, "expect": {**r["expect"], "reply_has": ["a sentence Hass never says"]}})
        self.assertEqual((res.status, [c for c, _ in res.problems]), ("FAIL", ["wrong-reply"]))

    def test_a_stranger_who_gets_a_reply_fails(self):
        res = self.mutated("s16-stranger", lambda r: {k: v for k, v in r.items() if k != "as"})  # the owner's own words get an answer
        self.assertEqual(res.status, "FAIL")
        self.assertIn("wrong-count", [c for c, _ in res.problems])

    def test_whats_sold_out_is_pass_not_a_known_gap(self):
        res = {r.row["id"]: r for r in Run.get()}["s15-whats-sold-out"]
        self.assertEqual(res.status, "PASS")
        self.assertNotIn("known_gap", res.row)

    def test_a_wrong_saved_change_fails(self):
        def change(r):
            r["expect"]["diff"] = [{**r["expect"]["diff"][0], "after": "no"}] + r["expect"]["diff"][1:]
            return r
        res = self.mutated("s06-yes", change)
        self.assertIn("wrong-diff", [c for c, _ in res.problems])

    def test_an_undo_that_leaves_something_behind_must_declare_it(self):
        res = self.mutated("s07-undo-yes", lambda r: {**r, "residue": [{"file": "hass/content/products.json", "path": "products[photo-product-001].description"}]})
        self.assertEqual((res.status, [c for c, _ in res.problems]), ("FAIL", ["undo-not-identical"]))

    def test_a_message_that_wrote_before_its_yes_would_be_caught(self):
        res = self.mutated("s06-yes", lambda r: {**r, "expect": {k: v for k, v in r["expect"].items() if k not in ("commit", "files", "diff")}})
        self.assertIn("write-before-yes", [c for c, _ in res.problems])

    def test_a_till_reply_that_quotes_a_count_it_should_not_fails(self):
        res = self.mutated("s09-how-many", lambda r: {**r, "expect": {**r["expect"], "reply_lacks": ["40"]}})
        self.assertEqual((res.status, [c for c, _ in res.problems]), ("FAIL", ["wrong-reply"]))

    def test_a_known_gap_that_fails_is_a_gap_not_a_fail(self):
        res = self.mutated("s14-pause-please", lambda r: r)
        self.assertEqual((res.status, res.row["known_gap"]), ("GAP", "QA1-02"))
        res = self.mutated("s14-pause-please", lambda r: {k: v for k, v in r.items() if k != "known_gap"})
        self.assertEqual(res.status, "FAIL")


class LiveRefusals(unittest.TestCase):
    def run_main(self, argv, env=None):
        out, err = io.StringIO(), io.StringIO()
        with mock.patch.dict(os.environ, env or {}), redirect_stdout(out), redirect_stderr(err):
            code = demo.main(argv)
        return code, out.getvalue(), err.getvalue()

    def test_live_refuses_under_ci(self):
        for var in ("CI", "GITHUB_ACTIONS"):
            with self.subTest(var=var):
                code, out, err = self.run_main(["--live", "--url", "http://127.0.0.1:1", "--model", "m"], {var: "true"})
                self.assertEqual((code, out), (2, ""))
                self.assertIn("refuses to run under CI", err)

    def test_live_needs_a_loopback_url_and_a_model(self):
        env = {"CI": "", "GITHUB_ACTIONS": ""}
        self.assertEqual(self.run_main(["--live"], env)[0], 2)
        code, _out, err = self.run_main(["--live", "--url", "http://example.com", "--model", "m"], env)
        self.assertEqual(code, 2)
        self.assertIn("loopback", err)

    def test_a_bad_fixture_is_refused_naming_the_line(self):
        with tempfile.TemporaryDirectory() as tmp:
            bad = Path(tmp) / "bad.jsonl"
            bad.write_text('{"world": {"start": "2026-11-16T09:00:00-08:00", "ttl_seconds": 1800}}\n{"id": "x", "step": 1, "say": "status"}\n', "utf-8")
            code, _out, err = self.run_main(["--fixture", str(bad)])
        self.assertEqual(code, 2)
        self.assertIn("fixture line 2", err)

    def test_live_wrapper_asks_the_interpreter_for_rows_that_reach_it(self):
        world, rows = demo.load_fixture()
        asked = []

        class Stub:
            last_error = None

            def interpret(self, text, pending, *a, **k):
                asked.append(text)
                return {"unsupported": "Sorry, I can't do that yet."}
        built = []

        def build(content_dir):
            built.append(Path(content_dir).name)
            return Stub()
        keep = [r for r in rows if r["id"] in ("s01-status", "s06-describe")]
        results, _ = demo.run(world, keep, live=build)
        self.assertEqual(asked, ["change the description of Hass avocado to Ripe now, and good on toast."])
        self.assertEqual(built, ["content"])
        self.assertIn("LIVE", demo.table(results, "recorded", True))
        self.assertTrue(results[0].ok, results[0].problems)  # `status` never reaches the model


if __name__ == "__main__":
    unittest.main()
