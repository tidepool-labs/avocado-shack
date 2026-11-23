"""NPP-H: the offline acceptance runner, the sourcing audit, the judge calibration and the weekly metrics.

Each test names the contract it verifies. Fixtures only: no model, network, live Hass, host.json or Clover.
"""
import copy
import importlib.util
import json
import sys
import tempfile
import unittest
from datetime import datetime, timedelta, timezone
from pathlib import Path
from unittest.mock import patch

from hass import npp

ROOT = Path(__file__).resolve().parents[2]


def _load(name, path):
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module
    spec.loader.exec_module(module)
    return module


run_npp = _load("npp_run_under_test", ROOT / "hass" / "tests" / "npp" / "run_npp.py")
ev = _load("npp_eval", ROOT / "scripts" / "hass" / "npp_eval.py")
metrics = _load("npp_metrics_under_test", ROOT / "scripts" / "hass" / "npp_metrics.py")


def view_of(case_id, variant=None):
    case = run_npp.load_cases()[case_id]
    return next(v for name, v in run_npp.case_views(case) if name == variant)


class VersioningTests(unittest.TestCase):
    def test_all_38_cases_load_and_the_manifest_pins_cases_tapes_and_pins(self):
        # Contract: assets, cases and tapes are versioned together (design 4a/4d); a case is never deleted.
        self.assertEqual(sorted(run_npp.load_cases()), list(range(1, 39)))
        self.assertEqual(run_npp.check_manifest()["runner_version"], run_npp.RUNNER_VERSION)

    def test_a_changed_tape_is_refused_until_the_manifest_is_rewritten(self):
        # Contract: results are reproducible, so a silently edited tape must not replay.
        with tempfile.TemporaryDirectory() as tmp:
            for path in (run_npp.TAPES).glob("*.json"):
                (Path(tmp) / path.name).write_bytes(path.read_bytes())
            tape = Path(tmp) / "s2.json"
            tape.write_text(tape.read_text().replace("Honey", "Honeyed"))
            with patch.object(run_npp, "TAPES", Path(tmp)):
                with self.assertRaises(run_npp.ManifestMismatch):
                    run_npp.check_manifest()

    def test_the_run_records_the_pins_it_depends_on(self):
        # Contract (design 4d): the report names pins, asset set, model ids and the renderer commit (null until recorded).
        got = run_npp.fingerprints()
        for key in ("pins_sha256", "assets_sha256", "cases_sha256", "models", "renderer_commit"):
            self.assertIn(key, got)
        self.assertEqual(got["models"]["judge"], ["gpt-6.2-sol", "medium"])


class ClockAndTapeTests(unittest.TestCase):
    def test_virtual_clock_runs_events_in_time_then_stage_order(self):
        # Contract (design 3.4): ties are broken by stage order, so cap and race cases are exact.
        clock, seen = run_npp.VirtualClock(), []
        clock.at(10, 2, lambda: seen.append("late-stage"))
        clock.at(10, 1, lambda: seen.append("early-stage"))
        clock.at(5, 9, lambda: seen.append("first"))
        clock.run_until(10)
        self.assertEqual(seen, ["first", "early-stage", "late-stage"])
        self.assertEqual(clock.monotonic(), 10)
        with self.assertRaises(ValueError):
            clock.advance(-1)

    def test_a_tape_miss_is_a_failure_never_a_guess(self):
        # Contract (design 3.4): a call the tape does not hold fails the run.
        with self.assertRaises(run_npp.TapeMiss):
            run_npp.Tapes().lookup("s2", "0" * 64, "1" * 64, 0)
        clock = run_npp.VirtualClock()
        world = run_npp.World({"search": {}, "pages": {}, "forbid_fetch": []}, clock)
        with self.assertRaises(run_npp.TapeMiss):
            world.search("Nobody official site", 5, 10)
        with self.assertRaises(run_npp.TapeMiss):
            run_npp.Models({}, clock, world).extract("Nobody", {}, 10)
        with self.assertRaises(run_npp.TapeMiss):
            world.fetch("https://unknown.example/", 10)

    def test_tape_latency_moves_the_virtual_clock_not_the_wall_clock(self):
        # Contract (design 3.4): each taped call completes at start + its recorded seconds.
        clock = run_npp.VirtualClock()
        world = run_npp.World({"search": {"Q": [{"url": "https://a.example/"}]}, "pages": {}, "forbid_fetch": []}, clock,
                              {"search": 7.5})
        self.assertEqual(world.search("Q", 5, 10), ["https://a.example/"])
        self.assertEqual(clock.monotonic(), 7.5)


class ResearchDecisionTests(unittest.TestCase):
    """G 2026-11-18 14:00: search only to locate the maker's own site; identity must match; facts only from that site,
    cited and checked against visible page text; not confident means no story."""

    def run_view(self, case_id, variant=None):
        failures, evidence = run_npp.run_research(view_of(case_id, variant))
        return failures, evidence

    def test_the_five_research_cases_hold_their_expectations_and_the_audit(self):
        # Contract: cases 29, 30, 31, 37, 38 replay the real S4 stage and pass every expectation and every audit rule.
        for case_id, variants in ((29, [None]), (30, [None]), (31, ["a", "b"]), (37, ["a", "b"]), (38, [None])):
            for variant in variants:
                with self.subTest(case=case_id, variant=variant):
                    self.assertEqual(self.run_view(case_id, variant)[0], [])

    def test_a_wrong_town_site_and_two_passing_sites_leave_no_story(self):
        # Contract (case 37): a same-name maker in the wrong town fails identity; two passing domains is not confident.
        _, wrong = self.run_view(37, "a")
        self.assertEqual(wrong["result"].facts, ())
        self.assertEqual([r["reason"] for r in wrong["result"].receipt["identity"]], ["different-base-town"])
        _, two = self.run_view(37, "b")
        self.assertEqual((two["result"].facts, two["result"].receipt["outcome"]), ((), "two-passing-domains"))
        self.assertEqual(two["world"].calls["extract"], 0)

    def test_a_directory_or_retailer_page_never_supplies_a_story(self):
        # Contract (case 38): a denied site is never fetched and a retailer page fails 'own site'; extraction never runs.
        _, got = self.run_view(38)
        rows = {r["url"]: r for r in got["result"].receipt["identity"]}
        self.assertEqual(rows["https://www.yelp.com/biz/miners-paso-robles"]["reason"], "denied-domain")
        self.assertNotIn("https://www.yelp.com/biz/miners-paso-robles", got["world"].fetched)
        self.assertEqual((got["result"].facts, got["world"].calls["extract"]), ((), 0))

    def test_the_label_brand_that_contradicts_the_owner_stops_research_before_any_search(self):
        # Contract (case 31b): the maker's identity must match the label or the owner's words; else no research.
        _, got = self.run_view(31, "b")
        self.assertEqual(got["result"].receipt["outcome"], "label-mismatch")
        self.assertEqual((got["world"].calls["search"], got["world"].calls["fetch"]), (0, 0))

    def test_only_quotes_found_in_visible_text_are_kept_and_cited(self):
        # Contract (case 30): kept facts carry url, quote and retrieval day; negated and past quotes are dropped.
        _, got = self.run_view(30)
        self.assertEqual(sorted((f["slot"], f["value"]) for f in got["result"].facts), [("makes", "dried figs"), ("nature", "orchard")])
        for fact in got["result"].facts:
            self.assertTrue(fact["url"] and fact["quote"] and fact["retrieved"])

    def test_the_runner_fails_a_case_whose_expectation_the_code_does_not_meet(self):
        # Contract: an expectation that the real stage does not satisfy is reported, not waved through.
        view = copy.deepcopy(view_of(30))
        view["expect"]["research"]["kept_facts"] = [{"slot": "makes", "value": "certified organic figs"}]
        failures, _ = run_npp.run_research(view)
        self.assertTrue(any(f.startswith("kept_facts") for f in failures), failures)


class AuditTests(unittest.TestCase):
    """The audit is the offline enforcement of the decision; each rule is shown to catch a planted violation."""

    def setUp(self):
        failures, got = run_npp.run_research(view_of(30))
        self.assertEqual(failures, [])
        world, result = got["world"], got["result"]
        self.args = dict(receipt=copy.deepcopy(result.receipt), facts=tuple(dict(f) for f in result.facts),
                         pages={u: p for u, (p, _) in world.pages.items()}, queries=list(world.queries),
                         fetched=list(world.fetched), sources=json.loads(got["pinned"][1]["hass-maker-research/sources.json"]),
                         seed=dict(got["seed"]), label=None)

    def audit(self, **change):
        args = {**self.args, **change}
        return ev.audit_research(args.pop("receipt"), args.pop("facts"), args.pop("pages"), **args)

    def test_clean_run_has_no_violation(self):
        self.assertEqual(self.audit(), [])

    def test_search_used_for_more_than_locating_is_caught(self):
        self.assertTrue(any("locating" in p for p in self.audit(queries=["Miners best price 4 bucks"])))

    def test_search_after_the_owner_gave_the_address_is_caught(self):
        self.assertTrue(any("owner gave" in p for p in self.audit(queries=["Miners Paso Robles official site"])))

    def test_a_quote_that_is_not_visible_text_is_caught(self):
        facts = tuple({**f, "quote": "Miners makes award-winning figs."} for f in self.args["facts"])
        self.assertTrue(any("visible text" in p for p in self.audit(facts=facts)))

    def test_visible_quote_does_not_authorize_an_unsupported_town_or_predicate(self):
        # Contract: even a verbatim visible sentence cannot authorize an invented town
        # or reassign a verified phrase to a different slot.
        fact = self.args["facts"][0]
        self.assertIn("kept fact value is not supported by its visible quote",
                      self.audit(facts=[{**fact, "slot": "town", "value": "Invented Town"}]))
        self.assertIn("kept fact has no matching supported extraction receipt",
                      self.audit(facts=[{**fact, "slot": "town"}]))

    def test_a_fact_without_a_citation_is_caught(self):
        facts = tuple({**f, "url": ""} for f in self.args["facts"])
        self.assertTrue(any("lacks its url" in p for p in self.audit(facts=facts)))

    def test_facts_from_a_page_never_fetched_are_caught(self):
        facts = tuple({**f, "url": "https://elsewhere.example/about"} for f in self.args["facts"])
        self.assertTrue(any("never fetched" in p for p in self.audit(facts=facts)))

    def test_facts_kept_on_a_not_confident_outcome_are_caught(self):
        receipt = copy.deepcopy(self.args["receipt"])
        receipt["outcome"] = "two-passing-domains"
        self.assertTrue(any("withheld" in p for p in self.audit(receipt=receipt)))

    def test_facts_when_two_sites_pass_are_caught(self):
        receipt = copy.deepcopy(self.args["receipt"])
        receipt["identity"].append({"url": "https://other-miners.example/", "passed": True, "reason": "official"})
        self.assertTrue(any("exactly one" in p for p in self.audit(receipt=receipt)))

    def test_fetching_a_denied_site_is_caught(self):
        receipt = copy.deepcopy(self.args["receipt"])
        receipt["identity"].append({"url": "https://www.yelp.com/biz/x", "passed": False, "reason": "denied-domain"})
        self.assertTrue(any("denied" in p for p in self.audit(receipt=receipt, fetched=["https://www.yelp.com/biz/x"])))

    def test_research_that_ignores_a_contradicting_label_is_caught(self):
        seed = {**self.args["seed"], "maker": "Miners"}
        got = self.audit(seed=seed, label={"brand": "Quarry Lane", "confidence": 0.9})
        self.assertTrue(any("contradicts" in p for p in got))


class RunnerTests(unittest.TestCase):
    def test_question_cases_replay_through_the_real_conversation_with_no_draft(self):
        # Contract (cases 18a/b, 20, 22, 33): one reply, no draft/approval/commit, no image edit or research call.
        tapes = run_npp.Tapes()
        for case_id in (18, 20, 22, 33):
            for row in run_npp.run_case(case_id, tapes):
                with self.subTest(case=case_id, variant=row["variant"]):
                    self.assertEqual((row["layers"], row["result"]), ({"conversation": "pass"}, "pass"), row["notes"])

    def test_a_question_reply_that_is_not_the_template_fails_the_case(self):
        # Contract: the runner compares against the reply template, so a changed question is a failure.
        view = copy.deepcopy(view_of(18, "a"))
        view["expect"]["replies"][0]["source"] = "hass-npp-reply questions.ask_price"
        failures, _ = run_npp.run_conversation(view, run_npp.Tapes())
        self.assertTrue(any("template" in f or "kind" in f for f in failures), failures)

    def test_a_case_that_could_not_run_is_not_run_never_pass(self):
        # Contract (design 3.4): a case the replay cannot run is reported `not-run`, never `pass`.
        self.assertEqual(run_npp.overall({"research": "pass", "card": "not-run"}), "not-run")
        self.assertEqual(run_npp.overall({"research": "pass", "seed": "gap"}), "not-run")
        self.assertEqual(run_npp.overall({"research": "pass", "card": "fail"}), "fail")
        row, = run_npp.run_case(1)
        self.assertEqual(row["result"], "not-run")

    def test_taped_honey_card_survives_restart_and_approves_only_the_delivered_version(self):
        # Case 24: the real stages must reach a frozen/receipted card, survive restart,
        # then commit exactly the delivered draft and propose (not apply) its undo.
        row, = run_npp.run_case(24)
        self.assertEqual(row['result'], 'pass', row['notes'])

    def test_strict_fails_on_not_run_and_default_does_not(self):
        # Contract (design 3.4): --strict never skips; the CI replay lists not-run without failing.
        with patch("builtins.print"):
            self.assertEqual(run_npp.main(["--case", "1"]), 0)
            self.assertEqual(run_npp.main(["--case", "1", "--strict"]), 1)

    def test_the_owner_seed_is_only_his_own_words(self):
        # Contract (G 11-18): maker, town and an address come from the owner's words, nothing is inferred.
        self.assertEqual(run_npp.owner_seed(view_of(30)),
                         {"maker": "Miners", "town": "Paso Robles", "url": "https://minersfigs.example/about"})
        self.assertEqual(run_npp.owner_seed(view_of(13)), {"maker": "", "town": "", "url": ""})

    def test_the_production_seed_passes_and_third_party_facts_are_refused(self):
        # A production parser that drops the town must not be masked by the isolated research stub.
        row, = run_npp.run_case(38)
        self.assertEqual((row["layers"]["seed"], row["layers"]["research"]), ("pass", "pass"))

    def test_record_mode_is_private_host_only_and_capped(self):
        # Contract (design 3.4): --record re-records on the private host only, within --max-codex/--max-images.
        args = run_npp.parse(["--record", "--max-codex", "120", "--max-images", "30"])
        self.assertIn("private host", run_npp.record_guard(args, {}))
        self.assertIsNone(run_npp.record_guard(args, {"HASS_NPP_PRIVATE_HOST": "1"}))
        self.assertIn("--max-codex", run_npp.record_guard(run_npp.parse(["--record"]), {"HASS_NPP_PRIVATE_HOST": "1"}))
        caps = run_npp.RecordCaps(1, 0)
        caps.take("codex")
        with self.assertRaises(RuntimeError):
            caps.take("codex")
        with self.assertRaises(RuntimeError):
            caps.take("images")

    def test_image_record_cap_refuses_a_second_transport_call_and_round_trips_bytes(self):
        # A cap is enforced at dispatch, not merely counted in the report after spend.
        calls = []
        original = Path('synthetic.jpg')

        def edit(src, out, timeout):
            calls.append((src, timeout))
            out.write_bytes(b'synthetic edited bytes')
            return {'ok': True}

        recorder = run_npp.Recorder(run_npp.RecordCaps(0, 1), images=edit, codex=lambda _: self.fail('unexpected Codex'))
        key = ('image', 'a' * 64, 'b' * 64, 0)
        recorder.record(*key, lambda: recorder.edit(original))
        with self.assertRaisesRegex(RuntimeError, 'record cap reached for images'):
            recorder.edit(original)
        self.assertEqual(len(calls), 1)
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / 'image-tape.json'
            recorder.save(path)
            entry = run_npp.Tapes(recorded=path).lookup(*key)
            self.assertEqual(run_npp.base64.b64decode(entry['output']), b'synthetic edited bytes')

    def test_strict_names_the_missing_dependency(self):
        # Contract (design 3.4): --strict fails, never skips, when a dependency is missing.
        with patch.object(run_npp, "dependencies", return_value={"pillow": True, "tesseract": False}), patch("builtins.print") as shown:
            self.assertEqual(run_npp.main(["--strict", "--case", "1"]), 2)
        self.assertIn("tesseract", shown.call_args[0][0])


class JudgeTests(unittest.TestCase):
    def setUp(self):
        self.rubric, self.pinned = ev.load_rubric()
        self.dims = [d["id"] for d in self.rubric["dimensions"]]
        self.good, self.bad, self.cards = ev.calibration_set(self.pinned)

    def scores(self, value):
        return {d: value for d in self.dims}

    def runs(self, good=4.5, bad=1.5):
        return {item: [self.scores(good if item in self.good else bad)] * 3 for item in [*self.good, *self.bad]}

    def test_calibration_set_is_the_twelve_goldens_and_the_synthetic_bad_cards(self):
        # Contract (design 3.3): 12 good goldens plus bad cards, all present in the hash-pinned assets.
        self.assertEqual((len(self.good), len(self.bad)), (12, 4))
        self.assertEqual(set(self.cards), {*self.good, *self.bad})

    def test_calibration_passes_only_on_the_three_run_thresholds(self):
        # Contract (design 3.3): every run good >= 4.0, bad <= 2.5, spread <= 0.5, 3 runs each.
        ok, why = ev.calibrate(self.runs(), self.good, self.bad, self.rubric)
        self.assertEqual((ok, why), (True, []))
        for label, runs in (
            ("good run low", {**self.runs(), self.good[0]: [self.scores(4.5), self.scores(4.5), self.scores(3.0)]}),
            ("bad run high", {**self.runs(), self.bad[0]: [self.scores(1.0), self.scores(1.0), self.scores(3.0)]}),
            ("spread", {**self.runs(), self.good[1]: [self.scores(5), self.scores(5), self.scores(4)]}),
            ("two runs only", {**self.runs(), self.good[2]: [self.scores(5)] * 2}),
        ):
            with self.subTest(label):
                self.assertFalse(ev.calibrate(runs, self.good, self.bad, self.rubric)[0])

    def test_an_item_passes_on_mean_and_no_weak_dimension(self):
        # Contract (design 3.3): mean >= 4.0 with no dimension below 3.
        self.assertTrue(ev.judge_pass(self.scores(4), self.rubric))
        weak = {**self.scores(5), self.dims[0]: 2}
        self.assertFalse(ev.judge_pass(weak, self.rubric))
        self.assertFalse(ev.judge_pass({self.dims[0]: 5}, self.rubric))

    def test_pairwise_and_asset_change_gates(self):
        # Contract (design 3.3, 4d): pairwise accuracy <= 70 %; no case regresses by more than 0.5; mean >= 4.0.
        self.assertTrue(ev.pairwise_consistent(8, 12, self.rubric))
        self.assertFalse(ev.pairwise_consistent(9, 12, self.rubric))
        self.assertTrue(ev.asset_change_gate({"a": 4.5, "b": 4.2}, {"a": 4.2, "b": 4.3}, self.rubric)[0])
        self.assertFalse(ev.asset_change_gate({"a": 4.8}, {"a": 4.2}, self.rubric)[0])

    def test_calibration_failures_do_not_mix_with_weekly_metrics_in_either_order(self):
        # A shared output path puts three-field calibration rows in metrics.tsv (or gives it the wrong header).
        version = ev.judge_version(self.pinned[1]["hass-style-judge/rubric.json"], self.pinned[0])
        for calibration_first in (True, False):
            with self.subTest(calibration_first=calibration_first), tempfile.TemporaryDirectory() as tmp:
                scores, out = Path(tmp) / "scores.json", Path(tmp) / "metrics.tsv"
                calibration = out.with_name("calibration.tsv")
                judge_args = ["--judge", "--calibrate", "--scores", str(scores), "--metrics", str(out)]
                metrics_args = ["--receipts", tmp, "--week", "2026-W47", "--out", str(out)]
                with patch("builtins.print"):
                    scores.write_text(json.dumps({"judge_version": version, "runs": self.runs()}))
                    self.assertEqual(ev.main(judge_args), 0)
                    self.assertFalse(calibration.exists())
                    scores.write_text(json.dumps({"judge_version": version, "runs": self.runs(good=3.0)}))
                    if calibration_first:
                        self.assertEqual(ev.main(judge_args), 1)
                    self.assertEqual(metrics.main(metrics_args), 0)
                    if not calibration_first:
                        self.assertEqual(ev.main(judge_args), 1)

                header, row = [line.split("\t") for line in out.read_text().splitlines()]
                self.assertEqual(header, metrics.COLUMNS)
                self.assertEqual((len(row), row[0]), (len(header), "2026-W47"))
                cal_header, cal_row = [line.split("\t") for line in calibration.read_text().splitlines()]
                self.assertEqual(cal_header, ["calibration", "judge_version", "reason"])
                self.assertEqual(cal_row[:2], ["failed", version])
                self.assertEqual(len(cal_row), 3)
                self.assertIn("good item scored", cal_row[2])

    def test_scores_for_another_judge_version_are_not_accepted(self):
        # Contract: recorded scores replay only for the judge version (rubric + pinned model) they were made with.
        with tempfile.TemporaryDirectory() as tmp:
            scores = Path(tmp) / "scores.json"
            scores.write_text(json.dumps({"judge_version": "other", "runs": {}}))
            with patch("builtins.print"):
                self.assertEqual(ev.main(["--judge", "--calibrate", "--scores", str(scores)]), 1)

    def test_live_judging_is_private_host_only(self):
        # Contract (design 3.3): the judge runs on the private host; nothing is sent from CI.
        with patch("builtins.print"):
            self.assertEqual(ev.main(["--judge", "--calibrate", "--live"], environ={}), 2)

    def test_the_codex_scorer_demands_exactly_the_rubric_dimensions(self):
        # Contract: the judge's reply is checked by code before use (design 4a).
        good = {"ok": True, "text": json.dumps(self.scores(4))}
        scorer = ev.CodexScorer(self.rubric, self.pinned[0], runner=lambda request: good)
        self.assertEqual(scorer({"card": 1}), self.scores(4))
        wrong = ev.CodexScorer(self.rubric, self.pinned[0], runner=lambda request: {"ok": True, "text": json.dumps({"voice": 5})})
        with self.assertRaises(ValueError):
            wrong({"card": 1})
        down = ev.CodexScorer(self.rubric, self.pinned[0], runner=lambda request: {"ok": False})
        with self.assertRaises(RuntimeError):
            down({"card": 1})


class MetricsTests(unittest.TestCase):
    def receipt(self, job, outcomes, variants, approved=None, pins=None):
        versions = [{"n": n + 1, "image_variant": v, "state": "approved" if approved == n + 1 else "superseded"}
                    for n, v in enumerate(variants)]
        base = datetime(2026, 11, 20, 17, 0, tzinfo=timezone.utc)
        segments = [{"accepted_at": (base + timedelta(minutes=5 * i)).isoformat(),
                     "ended_at": (base + timedelta(minutes=5 * i, seconds=sec)).isoformat(),
                     "outcome": outcome} for i, (outcome, sec) in enumerate(outcomes)]
        return {"job_id": job, "versions": versions, "segments": list(reversed(segments)), "asset_pins": pins or {}}

    def test_the_weekly_row_is_computed_from_receipts_and_unknowns_stay_n_a(self):
        # Contract (design 4e): the nine weekly figures; a figure the receipts cannot give is n/a, never zero.
        pins = {"a": "1"}
        receipts = [
            self.receipt("aaaa", [("card", 40)], ["polished"], approved=1, pins=pins),
            self.receipt("bbbb", [("question", 5), ("card", 80)], ["raw", "raw"], approved=2, pins=pins),
            self.receipt("cccc", [("render-failed", 30), ("card", 50)], ["polished"], approved=1, pins={"a": "2"}),
            {"job_id": "dddd", "versions": [], "segments": [{"accepted_at": "2026-11-20T17:00:00+00:00",
                                                              "ended_at": "2026-11-20T17:00:02+00:00", "outcome": "question"}]},
        ]
        row = metrics.compute(receipts, pins=pins)
        self.assertEqual((row["jobs"], row["listings"]), (4, 3))
        self.assertAlmostEqual(row["first_card_pass_rate"], 2 / 3)
        self.assertAlmostEqual(row["approved_no_edit_share"], 2 / 3)
        self.assertAlmostEqual(row["edits_per_listing"], 1 / 3)
        self.assertAlmostEqual(row["questions_per_listing"], 1 / 3)
        self.assertAlmostEqual(row["fallback_picture"], 2 / 4)
        self.assertEqual((row["time_to_card_p50_s"], row["time_to_card_p90_s"]), (50.0, 80.0))
        self.assertEqual(row["pin_drift_jobs"], 1)
        self.assertIsNone(row["judge_mean"])
        self.assertIsNone(row["guard_replies_per_listing"])
        self.assertIn("p90", row["targets_missed"])
        self.assertIn("picture_fallback", row["targets_missed"])

    def test_findings_and_judge_figures_fill_the_columns_the_receipts_lack(self):
        # Contract (design 4e): wording/maker fallbacks, guard replies, repeats and judge scores come from the weekly inputs.
        row = metrics.compute([self.receipt("aaaa", [("card", 20)], ["polished"], approved=1)],
                              findings={"fallback": {"wording": 1, "maker": 0}, "guard_replies": 2, "repeat_incidents": 1},
                              judge={"mean": 4.0, "min": 3.5})
        self.assertEqual((row["fallback_wording"], row["fallback_maker"], row["guard_replies_per_listing"]), (1.0, 0.0, 2.0))
        self.assertIn("repeat_incidents", row["targets_missed"])
        self.assertIn("judge_mean", row["targets_missed"])

    def test_metrics_cli_counts_only_receipts_created_in_the_requested_iso_week(self):
        # Labeling an unfiltered aggregate mixes other weeks' jobs and fallbacks into the report.
        with tempfile.TemporaryDirectory() as tmp:
            for job, created_at, variant in (("aaaa", "2027-01-01T17:00:00+00:00", "polished"),
                                             ("bbbb", "2027-01-04T17:00:00+00:00", "raw"),
                                             ("cccc", None, "raw")):
                folder = Path(tmp) / job
                folder.mkdir()
                receipt = self.receipt(job, [], [variant])
                (folder / "receipt.json").write_text(json.dumps(dict(receipt, created_at=created_at)))
            with patch("builtins.print") as printed:
                self.assertEqual(metrics.main(["--receipts", tmp, "--week", "2026-W53",
                                               "--out", str(Path(tmp) / "metrics.tsv")]), 0)
            row = json.loads(printed.call_args.args[0])
            self.assertEqual((row["week"], row["jobs"], row["listings"], row["fallback_picture"]),
                             ("2026-W53", 1, 1, 0.0))

    def test_the_row_is_appended_to_a_tsv_with_one_header(self):
        # Contract (design 4e): metrics.tsv is append-only with a single header line.
        with tempfile.TemporaryDirectory() as tmp:
            out = Path(tmp) / "reports" / "metrics.tsv"
            row = metrics.compute([])
            metrics.write_row(out, "2026-W47", row)
            metrics.write_row(out, "2026-W48", row)
            lines = out.read_text().splitlines()
            self.assertEqual(len(lines), 3)
            self.assertEqual(lines[0].split("\t"), metrics.COLUMNS)
            self.assertEqual(lines[1].split("\t")[0], "2026-W47")
            self.assertIn("n/a", lines[1])

    def test_receipts_are_read_from_the_job_folders(self):
        # Contract: receipts are <mediaRoot>/npp/<job>/receipt.json; other files are ignored.
        with tempfile.TemporaryDirectory() as tmp:
            folder = Path(tmp) / "abcd1234"
            folder.mkdir()
            (folder / "receipt.json").write_text(json.dumps({"job_id": "abcd1234", "versions": [], "segments": []}))
            (folder / "card-x.png").write_bytes(b"x")
            self.assertEqual([r["job_id"] for r in metrics.load_receipts(tmp)], ["abcd1234"])


if __name__ == "__main__":
    unittest.main()
