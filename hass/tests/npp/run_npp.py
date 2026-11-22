#!/usr/bin/env python3
"""NPP-H: offline acceptance runner for the new-product pipeline (design 3.4).

    python3 -B hass/tests/npp/run_npp.py [--case ID ...] [--strict] [--preview] [--jobs N] [--json]
    python3 -B hass/tests/npp/run_npp.py --update-manifest        # after a reviewed change to cases, tapes or pins
    python3 -B hass/tests/npp/run_npp.py --record --max-codex 120 --max-images 30   # private host only

Replay is deterministic: a virtual clock (never the wall clock), tapes keyed by (asset sha, input sha, ordinal), a tape
miss is a failure, nothing touches the network or a model. Replies go to an in-memory adapter and a "publish" is a commit
in a throwaway writer repo.

A case is split into LAYERS and each layer reports `pass`, `fail`, `gap` or `not-run`:
  seed          the owner's words give the research seed (maker, town, address) the way production reads them
  research      the real S4 `research.research` over a synthetic web (G 2026-11-18 14:00: search only to locate the
                maker's own site; identity must match; facts only from that site, cited and checked against its
                visible text; not confident means no story) plus the sourcing audit in scripts/hass/npp_eval.py
  conversation  the real Conversation, job runner and production stages over a taped S2 reading (question paths)
  card          picture edit, card capture, approval, publish (needs a recorded image-edit tape or --preview)
A case passes only when every layer it needs passes. `not-run` is never `pass`; `gap` is a known, named contract gap
(KNOWN_GAPS). Exit 0 when nothing failed; `--strict` also fails on any `not-run`/`gap` and on a missing dependency.
"""
import argparse
import concurrent.futures
import hashlib
import heapq
import importlib.util
import json
import os
import re
import shutil
import sys
from collections import Counter
from datetime import datetime, timedelta, timezone
from pathlib import Path
from types import SimpleNamespace

HERE = Path(__file__).resolve().parent
REPO = HERE.parents[2]
if str(REPO) not in sys.path:
    sys.path.insert(0, str(REPO))

CASES = HERE / "cases"
TAPES = HERE / "tapes"
PHOTO_DIRS = {"npp": CASES / "photos", "chaos": REPO / "hass" / "tests" / "chaos" / "photos"}
RUNNER_VERSION = 1
EXPECTED_IDS = tuple(range(1, 39))
# Each taped call finishes this many virtual seconds after it starts (a case may override with `latency`).
LATENCY_S = {"search": 1.0, "fetch": 1.5, "extract": 4.0, "verify": 2.0, "identify": 3.0}
SETTING_KEYS = {"npp": "npp", "houseRender": "houseRender", "photo_polish": "photoPolish", "itemIntake": "itemIntake",
                "approvalTtlSeconds": "approvalTtlSeconds"}  # liveSite is a hostname setting, not a flag

# An injected instruction is dropped by whichever S4 check fires first: the hedge/instruction markers or "the quote does
# not name the maker". The contract (case 31a) is that it is dropped with an audit reason from this class.
DROP_REASONS = {"quote-does-not-name-maker": {"quote-does-not-name-maker", "negation-past-or-hedge-marker"}}

# Contract gaps that are real and named, so a layer reports `gap` (never a silent pass, never a CI failure).
KNOWN_GAPS = {
    "seed": ("production reads the research seed only from 'based in <town>' or 'town: <town>' clauses and a bare "
             "https address (hass/npp/stages.py _site_words), while the NPP cases give 'made by <maker>, <town>' and an "
             "address inside the caption. Until one of them changes, no case research starts from the case's own words."),
}


class TapeMiss(AssertionError):
    """The code asked for something the tape or the synthetic world does not hold: always a failure."""


class ManifestMismatch(ValueError):
    pass


def sha256(data):
    return hashlib.sha256(data).hexdigest()


def read_json(path):
    return json.loads(Path(path).read_text(encoding="utf-8"))


def load_module(name, path):
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module
    spec.loader.exec_module(module)
    return module


def eval_module():
    return sys.modules.get("npp_eval") or load_module("npp_eval", REPO / "scripts" / "hass" / "npp_eval.py")


# ---------------------------------------------------------------- virtual time


class VirtualClock:
    """Seconds since the case began. Ties are broken by stage order, then insertion order."""
    EPOCH = datetime(2026, 11, 20, 17, 0, tzinfo=timezone.utc)

    def __init__(self):
        self.t = 0.0
        self._queue = []
        self._serial = 0

    def monotonic(self):
        return self.t

    def now(self):
        return self.EPOCH + timedelta(seconds=self.t)

    def advance(self, seconds):
        if seconds < 0:
            raise ValueError("time does not run backwards")
        self.t += seconds
        return self.t

    def at(self, when, order, fn):
        heapq.heappush(self._queue, (when, order, self._serial, fn))
        self._serial += 1

    def run_until(self, when):
        while self._queue and self._queue[0][0] <= when:
            at, _, _, fn = heapq.heappop(self._queue)
            self.t = max(self.t, at)
            fn()
        self.t = max(self.t, when)


# ---------------------------------------------------------------- cases, tapes, manifest


def load_cases(directory=CASES):
    cases = {}
    for path in sorted(Path(directory).glob("case-*.json")):
        case = read_json(path)
        for key in ("id", "slug", "path", "terminal", "expect"):
            if key not in case:
                raise ValueError(f"{path.name}: missing {key}")
        if not (case.get("turns") or case.get("variants")):
            raise ValueError(f"{path.name}: no turns")
        if case["id"] in cases:
            raise ValueError(f"{path.name}: duplicate id {case['id']}")
        cases[case["id"]] = case
    missing = [i for i in EXPECTED_IDS if i not in cases]
    if missing:
        raise ValueError(f"missing case ids {missing}: a case is never deleted")
    return cases


def case_views(case):
    """One view per independent run: the case alone, or each variant merged over it (shallow)."""
    if not case.get("variants"):
        return [(None, case)]
    views = []
    for variant in case["variants"]:
        view = dict(case)
        view["turns"] = variant.get("turns", case.get("turns"))
        view["inputs"] = {**case.get("inputs", {}), **variant.get("inputs", {})}
        view["expect"] = {**case.get("expect", {}), **variant.get("expect", {})}
        views.append((variant["id"], view))
    return views


def tree_digest(directory, patterns):
    digest = hashlib.sha256()
    for pattern in patterns:
        for path in sorted(Path(directory).glob(pattern)):
            digest.update(path.relative_to(directory).as_posix().encode() + b"\0" + path.read_bytes() + b"\0")
    return digest.hexdigest()


def fingerprints(pinned=None):
    """Everything a result depends on, so a later run can be reproduced or told apart."""
    from hass import npp
    pins, files, _ = pinned or npp.assets()
    out = {
        "runner_version": RUNNER_VERSION,
        "cases_sha256": tree_digest(CASES, ("case-*.json", "pages/*", "photos/*", "edits/*")),
        "tapes_sha256": tree_digest(TAPES, ("*.json",)) if TAPES.is_dir() else None,
        "pins_sha256": sha256((REPO / "hass" / "npp" / "pins.json").read_bytes()),
        "assets_sha256": sha256(json.dumps(pins["assets"], sort_keys=True).encode()),
        "renderer_commit": pins.get("renderer", {}).get("commit"),
        "models": {step: [spec.get("model"), spec.get("effort")] for step, spec in sorted(pins["steps"].items())},
    }
    return out


def manifest_path():
    return TAPES / "MANIFEST.json"


def tape_files():
    return sorted(p for p in TAPES.glob("*.json") if p.name != "MANIFEST.json")


def write_manifest():
    data = fingerprints()
    data["tape_files"] = {p.name: sha256(p.read_bytes()) for p in tape_files()}
    data.pop("tapes_sha256")
    manifest_path().write_text(json.dumps(data, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    return data


def check_manifest():
    """Cases, tapes and pins are versioned together: a change to any of them must re-record the manifest in the same PR."""
    recorded = read_json(manifest_path())
    now = fingerprints()
    problems = []
    for key in ("runner_version", "cases_sha256", "pins_sha256", "assets_sha256", "renderer_commit", "models"):
        if recorded.get(key) != now[key]:
            problems.append(f"{key} differs from tapes/MANIFEST.json")
    held = {p.name: sha256(p.read_bytes()) for p in tape_files()}
    if held != recorded.get("tape_files"):
        problems.append("tape files differ from tapes/MANIFEST.json")
    if problems:
        raise ManifestMismatch("; ".join(problems) + " (run --update-manifest in the PR that changes them)")
    return now


class Tapes:
    """Replay store keyed by (kind, asset sha, input sha, ordinal). A miss is a failure, never a guess."""

    def __init__(self, directory=TAPES):
        self.entries = {}
        self.sources = {}
        for path in sorted(Path(directory).glob("*.json")):
            if path.name == "MANIFEST.json":
                continue
            data = read_json(path)
            self.sources[data["kind"]] = data["source"]
            for key, entry in data["entries"].items():
                self.entries[f"{data['kind']}:{key}"] = entry

    def lookup(self, kind, asset, inp, ordinal):
        key = f"{kind}:{asset}:{inp}:{ordinal}"
        if key not in self.entries:
            raise TapeMiss(f"tape miss {kind} ordinal {ordinal} input {inp[:12]} (asset {asset[:12]})")
        return self.entries[key]

    def holds(self, kind, asset, inp):
        return f"{kind}:{asset}:{inp}:0" in self.entries


def photo_bytes(ref):
    scheme, _, name = ref.partition(":")
    return (PHOTO_DIRS[scheme] / name).read_bytes()


# ---------------------------------------------------------------- expectations


def count_ok(want, got):
    if isinstance(want, list):
        return want[0] <= got <= want[1]
    return got == want


def check_calls(expect, calls):
    bad = []
    for kind, want in (expect.get("calls") or {}).items():
        if not count_ok(want, calls.get(kind, 0)):
            bad.append(f"calls.{kind}: want {want}, got {calls.get(kind, 0)}")
    return bad


# ---------------------------------------------------------------- research layer (real S4 over a synthetic web)

MADE_BY = re.compile(r"\bmade by (?P<maker>[A-Z][\w'’&-]*(?: [A-Z][\w'’&-]*)*)(?:, (?P<town>[A-Z][a-z]+(?: [A-Z][a-z]+)*))?")
ADDRESS = re.compile(r"https://[^\s,;]+")


def owner_seed(view):
    """The owner's own words in the case: maker, town and an address he typed. Nothing is inferred."""
    text = " ".join(t["text"] for t in view["turns"][:1])
    found = MADE_BY.search(text)
    address = ADDRESS.search(text)
    return {"maker": found["maker"] if found else "", "town": (found["town"] or "") if found else "",
            "url": address[0].rstrip(".") if address else ""}


class World:
    """The synthetic web of a case. Search is for locating the site only; every address must be in the world."""

    def __init__(self, spec, clock, latency=None):
        self.spec = spec or {"search": {}, "pages": {}, "forbid_fetch": []}
        self.clock = clock
        self.latency = {**LATENCY_S, **(latency or {})}
        self.calls = Counter()
        self.queries, self.fetched, self.violations, self.unlisted = [], [], [], []
        self.pages = {}

    def search(self, query, limit, seconds):
        self.calls["search"] += 1
        self.queries.append(query)
        self.clock.advance(self.latency["search"])
        if any(ch.isdigit() for ch in query):
            raise ValueError("unsafe search query")  # what hass.npp.research_hermes.Web.search does
        if query not in self.spec["search"]:
            raise TapeMiss(f"search tape miss: {query!r}")
        return [row["url"] for row in self.spec["search"][query]][:limit]

    def fetch(self, url, seconds):
        from hass import maker_site
        from hass.npp import research
        self.calls["fetch"] += 1
        self.fetched.append(url)
        self.clock.advance(self.latency["fetch"])
        if url in self.spec.get("forbid_fetch", ()):
            self.violations.append(f"fetched a forbidden address: {url}")
            raise maker_site.PageError("address")
        if url not in self.spec["pages"]:
            # An About page the site links to but the case does not list is simply unavailable (the real stage then
            # reads the pages it has). An address on a site the world does not hold at all is a tape miss.
            known = {research._site(u) for u in self.spec["pages"]}
            if research._site(url) in known:
                self.unlisted.append(url)
                raise maker_site.PageError("unreadable")
            raise TapeMiss(f"fetch tape miss: {url}")
        page = self.spec["pages"][url]
        markup = (CASES / page["file"]).read_text(encoding="utf-8")
        parsed = research.parse_page(url, page["retrieved"], markup)
        self.pages[url] = (parsed, markup)
        return parsed


class Models:
    def __init__(self, stubs, clock, world, latency=None):
        self.stubs, self.clock, self.world = stubs or {}, clock, world
        self.latency = {**LATENCY_S, **(latency or {})}

    def extract(self, name, pages, seconds):
        self.world.calls["extract"] += 1
        self.clock.advance(self.latency["extract"])
        if "extract" not in self.stubs:
            raise TapeMiss("extract was called but the case tapes none")
        return {"facts": [dict(row) for row in self.stubs["extract"]]}

    def verify(self, name, slot, value, quote, seconds):
        self.world.calls["verify"] += 1
        self.clock.advance(self.latency["verify"])
        verdict = self.stubs.get("verify")
        if isinstance(verdict, dict):
            return next((v for key, v in verdict.items() if key != "default" and key in quote), verdict.get("default"))
        return verdict


def run_research(view, pinned=None):
    """Run the real research stage on the case's world. Returns (layer result, evidence for the audit)."""
    from hass import npp
    from hass.npp import research
    pinned = pinned or npp.assets()
    clock = VirtualClock()
    inputs = view.get("inputs", {})
    latency = inputs.get("latency")
    world = World(inputs.get("web"), clock, latency)
    models = Models(inputs.get("stubs"), clock, world, latency)
    seed = owner_seed(view)
    identify = (inputs.get("stubs") or {}).get("identify") or {}
    result = research.research(
        pinned, search=world.search, fetch=world.fetch, extract=models.extract, verify=models.verify,
        owner_maker=seed["maker"], owner_town=seed["town"], owner_url=seed["url"],
        label_brand=identify.get("brand_on_label") or "", label_confidence=(identify.get("confidence") or {}).get("brand", 0.0),
        clock=clock.monotonic)
    evidence = {"result": result, "world": world, "seed": seed, "pinned": pinned, "clock": clock}
    failures = check_research(view["expect"], evidence)
    failures += [f"audit: {p}" for p in eval_module().audit_research(
        result.receipt, result.facts, {u: p for u, (p, _) in world.pages.items()}, queries=world.queries,
        fetched=world.fetched, sources=json.loads(pinned[1][research.ASSETS + "sources.json"]),
        seed=seed, label={"brand": identify.get("brand_on_label") or "",
                          "confidence": (identify.get("confidence") or {}).get("brand", 0.0)})]
    failures += world.violations
    return failures, evidence


def check_research(expect, evidence):
    result, world, seed = evidence["result"], evidence["world"], evidence["seed"]
    receipt, bad = result.receipt, []
    want = expect.get("research") or {}
    calls = {"search": world.calls["search"], "fetch": world.calls["fetch"], "extract": world.calls["extract"],
             "verify": world.calls["verify"]}
    bad += check_calls(expect, calls)
    if "located_official_site" in want:
        domain = receipt.get("chosen_domain")
        wanted = want["located_official_site"].split("//", 1)[1].split("/")[0].removeprefix("www.")
        if domain != wanted:
            bad.append(f"located_official_site: want {wanted}, got {domain}")
    if "queries_each_match" in want:
        forms = {" ".join(f.format(maker=seed["maker"], town=seed["town"]).split()) for f in want["queries_each_match"]}
        if not receipt["queries"] or not set(receipt["queries"]) <= forms:
            bad.append(f"queries_each_match: {receipt['queries']} not within {sorted(forms)}")
    if want.get("queries_lack_digits") and any(ch.isdigit() for q in receipt["queries"] for ch in q):
        bad.append("queries_lack_digits: a query carries a digit")
    if "owner_stated_url" in want:
        if seed["url"] != want["owner_stated_url"]:
            bad.append(f"owner_stated_url: seed took {seed['url']!r}")
        if receipt["queries"]:
            bad.append("owner_stated_url: a search ran although the owner gave the address")
    if "kept_facts" in want:
        got = sorted((f["slot"], f["value"]) for f in result.facts)
        wanted = sorted((f["slot"], f["value"]) for f in want["kept_facts"])
        if got != wanted:
            bad.append(f"kept_facts: want {wanted}, got {got}")
    if "dropped" in want:
        got = sorted((r["slot"], r.get("reason")) for r in receipt["facts"] if not r["kept"])
        wanted = sorted((d["slot"], d["reason"]) for d in want["dropped"])
        if len(got) != len(wanted) or any(g[0] != w[0] or g[1] not in DROP_REASONS.get(w[1], {w[1]})
                                          for g, w in zip(got, wanted)):
            bad.append(f"dropped: want {wanted}, got {got}")
    if "identity" in want:
        got = {row["url"]: row for row in receipt["identity"]}
        for row in want["identity"]:
            seen = got.get(row["url"])
            if seen is None:
                bad.append(f"identity: no check for {row['url']}")
                continue
            if seen["passed"] != row["passed"] or ("reason" in row and seen["reason"] != row["reason"]):
                bad.append(f"identity {row['url']}: want {row}, got {seen}")
            if row.get("fetched") is False and row["url"] in world.fetched:
                bad.append(f"identity {row['url']}: fetched although it must not be")
    if "not_confident" in want:
        if receipt.get("outcome") != want["not_confident"] or result.facts:
            bad.append(f"not_confident: want {want['not_confident']} with no facts, got {receipt.get('outcome')} with {len(result.facts)}")
    if "story" in expect and expect["story"] is None and result.story_facts:
        bad.append("story: facts reached the story slots although none is expected")
    return bad


def has_research(view):
    """A case with a synthetic web (even an empty one, which must see zero calls) exercises the research stage."""
    return view.get("inputs", {}).get("web") is not None


# ---------------------------------------------------------------- conversation layer (question paths)


def run_conversation(view, tapes, pinned=None):
    """Real Conversation, job runner and production stages; only the S2 reading, the clock and the transport are taped."""
    from unittest.mock import patch
    from hass import npp, photo_polish, sandbox, sandbox_editor
    from hass.npp import job, stages
    from hass.tests import test_npp_job as jf
    from hass.tests.test_conversation import T0
    pinned = pinned or npp.assets()
    asset = pinned[0]["assets"]["hass-product-identify/SKILL.md"]
    calls = Counter()
    ordinals = Counter()
    bodies = []
    failures = []

    def deny(*_a, **_k):
        raise TapeMiss("a stage reached for something this question case tapes none of")

    fx = jf.JobTests()
    fx.setUp()
    fx.settings.update({SETTING_KEYS[k]: v for k, v in view.get("settings", {}).items() if k in SETTING_KEYS})
    fx.start()
    try:
        gate = sandbox.Gate(lambda: {"approvals": "private"}, lambda: {("site", "sandbox"): str(fx.repo.wt)})
        fx.conv.editor = sandbox_editor.SiteEditor(fx.repo.state, gate, deny, clock=lambda: fx.now)
        fx.conv.previewer = SimpleNamespace(capture=deny)
        port = npp.stages_for(fx.conv, pinned)
        if port is None:
            return ["stages_for returned None: the production stages are not composed"], {}
        fx.conv.npp.stages = port

        def identify(photos):
            found = []
            for data in photos:
                digest = sha256(data)
                entry = tapes.lookup("s2", asset, digest, ordinals[digest])
                ordinals[digest] += 1
                calls["identify"] += 1
                bodies.append(json.dumps({"images": 1}))
                found.append(entry["output"])
            return SimpleNamespace(evidence=found[0])

        port.identifier.read = identify
        port.selector = None
        port.mapper = deny
        current = {"photos": []}
        fx.fetch = lambda _pid, count: current["photos"][:count]

        def counted(name):
            def fail(*_a, **_k):
                calls[name] += 1
                raise TapeMiss(f"{name} was called in a case that must not call it")
            return fail

        observed = []
        clock = VirtualClock()
        turns = view["turns"]

        def play(index, spec):
            def run():
                code = fx.job()["job_id"] if fx.job() else "none"
                fx.now = T0 + timedelta(seconds=spec["at_s"])
                current["photos"] = [photo_bytes(p) for p in spec.get("photos", [])]
                before = len(fx.transport.texts)
                outcome = fx.say(spec["text"].replace("{code}", code), photos=len(current["photos"]))
                fx.work()
                observed.append({"turn": index, "result": outcome, "texts": fx.transport.texts[before:]})
            return run

        with patch.object(stages.research_hermes, "run", side_effect=counted("research")), \
                patch.object(stages.photo_polish, "start", side_effect=counted("image_edit")), \
                patch.object(stages.picture, "read_text", return_value=""):
            for index, spec in enumerate(turns):
                clock.at(spec["at_s"], 0, play(index, spec))
            clock.run_until(max(spec["at_s"] for spec in turns) + float(view.get("settle_until_s", 0)))
        row = fx.job()
        db = fx.conv.db
        state = {
            "state": row["state"] if row else None,
            "draft_rows": db.execute("SELECT count(*) FROM drafts").fetchone()[0],
            "version_rows": db.execute("SELECT count(*) FROM npp_versions WHERE state NOT IN ('building')").fetchone()[0],
            "approvals": db.execute("SELECT count(*) FROM approvals").fetchone()[0],
            "commits": 0 if fx.repo.head() == fx.base else 1,
            "cards": len(fx.transport.cards),
        }
        failures += check_conversation(view["expect"], observed, state, calls, bodies, pinned[2], turns)
        return failures, {"observed": observed, "state": state, "calls": dict(calls)}
    finally:
        fx.doCleanups()


def reply_kind(text, replies):
    from hass.npp import job
    if text == job.EXPIRED:
        return "expired"
    if text in replies["questions"].values() or text.endswith("?"):
        return "question"
    return "other"


def check_conversation(expect, observed, state, calls, bodies, replies, turns):
    bad = []
    for want in expect.get("replies", []):
        texts = observed[want["turn"]]["texts"] if want["turn"] < len(observed) else []
        if len(texts) != want["count"]:
            bad.append(f"turn {want['turn']}: want {want['count']} reply, got {len(texts)}")
            continue
        for text in texts:
            if reply_kind(text, replies) != want["kind"]:
                bad.append(f"turn {want['turn']}: reply kind {reply_kind(text, replies)!r}, want {want['kind']!r}")
            for needle in want.get("has_all", ()):
                if needle not in text:
                    bad.append(f"turn {want['turn']}: reply lacks {needle!r}")
            for needle in want.get("lacks", ()):
                if needle in text:
                    bad.append(f"turn {want['turn']}: reply holds {needle!r}")
            source = want.get("source", "")
            if source.startswith("hass-npp-reply questions."):
                if text != replies["questions"][source.rsplit(".", 1)[1]]:
                    bad.append(f"turn {want['turn']}: not the {source} template")
    if "total_replies" in expect and sum(len(o["texts"]) for o in observed) != expect["total_replies"]:
        bad.append(f"total_replies: want {expect['total_replies']}, got {sum(len(o['texts']) for o in observed)}")
    if "state" in expect and state["state"] != expect["state"]:
        bad.append(f"state: want {expect['state']}, got {state['state']}")
    if expect.get("draft_rows") == "none" and (state["draft_rows"] or state["version_rows"] or state["cards"]):
        bad.append(f"no_draft: drafts {state['draft_rows']}, versions {state['version_rows']}, cards {state['cards']}")
    if "approval_rows" in expect and state["approvals"] != expect["approval_rows"]:
        bad.append(f"approval_rows: want {expect['approval_rows']}, got {state['approvals']}")
    if "commits" in expect and state["commits"] != expect["commits"]:
        bad.append(f"commits: want {expect['commits']}, got {state['commits']}")
    bad += check_calls(expect, {"image_edit": calls["image_edit"], "search": 0, "fetch": 0, "extract": 0}
                       | ({"search": calls["research"]} if calls["research"] else {}))
    digits = [d for text in turns for d in re.findall(r"\d", text["text"])] if expect.get("cloud_bodies_lack_digits_from") else []
    for digit in expect.get("cloud_bodies_lack_digits_from", ()):
        if any(digit in re.findall(r"\d+", body) for body in bodies):
            bad.append(f"no_private_values: digit {digit} reached a cloud request body")
    del digits
    return bad


# ---------------------------------------------------------------- case driver


def card_reason(view):
    polish = (view.get("inputs", {}).get("polish") or {}).get("source")
    if polish == "record":
        return "the real image edit is taped on the private host only (polish.source=record)"
    if view["path"] == "question" and view["terminal"] == "retake":
        return "raw-conditions picture stage needs recorded picture reads and a card capture tape"
    return "no card-capture tape and no --preview renderer in this run (private host: run_npp.py --strict --preview)"


def run_case(case_id, tapes=None, pinned=None, preview=False):
    from hass import npp
    pinned = pinned or npp.assets()
    tapes = tapes or Tapes()
    case = load_cases()[case_id]
    asset = pinned[0]["assets"]["hass-product-identify/SKILL.md"]
    rows = []
    for variant, view in case_views(case):
        layers = {}
        notes = {}
        try:
            if has_research(view):
                seed = owner_seed(view)
                failures, _ = run_research(view, pinned)
                layers["research"] = "fail" if failures else "pass"
                notes["research"] = failures
                if seed["maker"] and (seed["town"] or seed["url"]) and (view["expect"].get("research") or {}):
                    from hass.npp import stages as production
                    town, url = production._site_words(seed["maker"], [t["text"] for t in view["turns"][:1]])
                    gap = (seed["town"] and not town) or (seed["url"] and url != seed["url"])
                    layers["seed"] = "gap" if gap else "pass"
                    if gap:
                        notes["seed"] = [KNOWN_GAPS["seed"]]
            if view["path"] == "question" and view["terminal"] in ("asking", "expired"):
                have = all(tapes.holds("s2", asset, sha256(photo_bytes(p))) for t in view["turns"] for p in t.get("photos", [])
                           ) and any(t.get("photos") for t in view["turns"])
                if have:
                    failures, _ = run_conversation(view, tapes, pinned)
                    layers["conversation"] = "fail" if failures else "pass"
                    notes["conversation"] = failures
            if view["path"] != "question" or view["terminal"] not in ("asking", "expired") or "conversation" not in layers:
                layers["card"] = "not-run"
                notes["card"] = [card_reason(view)]
        except TapeMiss as miss:
            layers["tape"] = "fail"
            notes["tape"] = [str(miss)]
        rows.append({"id": case_id, "variant": variant, "slug": case["slug"], "path": view["path"],
                     "terminal": view["terminal"], "layers": layers, "notes": {k: v for k, v in notes.items() if v},
                     "result": overall(layers)})
    return rows


def overall(layers):
    values = set(layers.values())
    if "fail" in values:
        return "fail"
    if values == {"pass"}:
        return "pass"
    return "not-run"


def _worker(case_id):  # top level so a process pool can pickle it
    return run_case(case_id)


def run_all(ids, jobs=1):
    ids = sorted(ids)
    if jobs > 1:
        with concurrent.futures.ProcessPoolExecutor(max_workers=jobs) as pool:
            return [row for rows in pool.map(_worker, ids) for row in rows]
    from hass import npp
    pinned, tapes = npp.assets(), Tapes()
    return [row for case_id in ids for row in run_case(case_id, tapes, pinned)]


# ---------------------------------------------------------------- dependencies and record mode


def dependencies():
    found = {}
    try:
        import PIL  # noqa: F401
        found["pillow"] = True
    except ImportError:
        found["pillow"] = False
    found["tesseract"] = shutil.which("tesseract") is not None
    node = os.environ.get("NODE") or shutil.which("node")
    found["node22"] = False
    if node:
        import subprocess
        try:
            version = subprocess.run([node, "--version"], capture_output=True, text=True, timeout=10).stdout.strip()
            found["node22"] = bool(re.match(r"v(2[2-9]|[3-9]\d)\.", version))
        except (OSError, subprocess.SubprocessError):
            pass
    try:
        from hass import preview
        found["playwright"] = bool(preview.Previewer(str(REPO)).env.get("PLAYWRIGHT_MODULE"))
    except Exception:  # no stage detail: the dependency is simply absent
        found["playwright"] = False
    return found


class RecordCaps:
    """Re-recording is private-host only and bounded: a call past a cap is refused, never silently allowed."""

    def __init__(self, max_codex, max_images):
        self.left = {"codex": max_codex, "images": max_images}
        self.used = Counter()

    def take(self, kind):
        if self.left[kind] <= 0:
            raise RuntimeError(f"record cap reached for {kind}")
        self.left[kind] -= 1
        self.used[kind] += 1


def record_guard(args, environ):
    """Return an error string when --record must not run, else None."""
    if not args.record:
        return None
    if environ.get("HASS_NPP_PRIVATE_HOST") != "1":
        return "--record runs on the private host only (set HASS_NPP_PRIVATE_HOST=1 there); nothing is recorded here"
    if args.max_codex is None or args.max_images is None or args.max_codex < 0 or args.max_images < 0:
        return "--record needs --max-codex and --max-images"
    return None


# ---------------------------------------------------------------- command line


def parse(argv):
    p = argparse.ArgumentParser(description="NPP offline acceptance runner")
    p.add_argument("--case", type=int, action="append", help="case id (repeatable)")
    p.add_argument("--preview", action="store_true", help="use the real card renderer (Node 22 + Playwright)")
    p.add_argument("--strict", action="store_true", help="fail on a missing dependency, a not-run or a gap")
    p.add_argument("--jobs", type=int, default=1)
    p.add_argument("--json", action="store_true", help="print the whole report as one JSON document")
    p.add_argument("--update-manifest", action="store_true")
    p.add_argument("--record", action="store_true")
    p.add_argument("--max-codex", type=int)
    p.add_argument("--max-images", type=int)
    return p.parse_args(argv)


def main(argv=None, environ=None):
    args = parse(sys.argv[1:] if argv is None else argv)
    environ = os.environ if environ is None else environ
    if (error := record_guard(args, environ)):
        print(error)
        return 2
    if args.record:
        print("record mode is wired to the private host runner only; no recorder is attached in this checkout")
        return 2
    if args.update_manifest:
        print(json.dumps(write_manifest(), sort_keys=True))
        return 0
    deps = dependencies()
    missing = [name for name, ok in deps.items() if not ok and (args.strict or args.preview)]
    if missing:
        print(json.dumps({"error": "dependency missing", "missing": missing}))
        return 2
    try:
        fingerprint = check_manifest()
        ids = args.case or list(EXPECTED_IDS)
        unknown = [i for i in ids if i not in EXPECTED_IDS]
        if unknown:
            print(f"unknown case ids {unknown}")
            return 2
        rows = run_all(ids, args.jobs)
    except (ManifestMismatch, ValueError) as error:
        print(json.dumps({"error": str(error)}))
        return 2
    counts = Counter(row["result"] for row in rows)
    layers = Counter(f"{name}:{state}" for row in rows for name, state in row["layers"].items())
    summary = {"summary": {"runs": len(rows), **{k: counts.get(k, 0) for k in ("pass", "fail", "not-run")},
                           "layers": dict(sorted(layers.items())), "dependencies": deps, "preview": args.preview,
                           "fingerprint": fingerprint}}
    if args.json:
        print(json.dumps({"cases": rows, **summary}, sort_keys=True))
    else:
        for row in rows:
            print(json.dumps(row, sort_keys=True))
        print(json.dumps(summary, sort_keys=True))
    bad = counts.get("fail", 0) or (args.strict and (counts.get("not-run", 0) or counts.get("pass", 0) != len(rows)))
    return 1 if bad else 0


if __name__ == "__main__":
    sys.exit(main())
