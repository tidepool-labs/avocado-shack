#!/usr/bin/env python3
"""NPP-H: offline acceptance runner for the new-product pipeline (design 3.4).

    python3 -B hass/tests/npp/run_npp.py [--case ID ...] [--strict] [--preview] [--jobs N] [--json]
    python3 -B hass/tests/npp/run_npp.py --update-manifest        # after a reviewed change to cases, tapes or pins
    python3 -B hass/tests/npp/run_npp.py --record --record-to <new-private-file> --max-codex 120 --max-images 30

Replay is deterministic: a virtual clock (never the wall clock), tapes keyed by (asset sha, input sha, ordinal), a tape
miss is a failure, nothing touches the network or a model. Replies go to an in-memory adapter and a "publish" is a commit
in a throwaway writer repo.

A case is split into LAYERS and each layer reports `pass`, `fail`, `gap` or `not-run`:
  seed          the owner's words give the research seed (maker, town, address) the way production reads them
  research      the real S4 `research.research` over a synthetic web (G 2026-11-18 14:00: search only to locate the
                maker's own site; identity must match; facts only from that site, cited and checked against its
                visible text; not confident means no story) plus the sourcing audit in scripts/hass/npp_eval.py
  conversation  question paths through the real Conversation, job runner and production stages
  card          listing or contract path through the picture gate, capture, approval and local commit
A case passes only when every layer it needs passes. `not-run` is never `pass`; `gap` is a known, named contract gap
(KNOWN_GAPS). Exit 0 when nothing failed; `--strict` also fails on any `not-run`/`gap` and on a missing dependency.
"""
import argparse
import base64
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
RUNNER_VERSION = 2
EXPECTED_IDS = tuple(range(1, 39))
# Each taped call finishes this many virtual seconds after it starts (a case may override with `latency`).
LATENCY_S = {"search": 1.0, "fetch": 1.5, "extract": 4.0, "verify": 2.0, "identify": 3.0}
SETTING_KEYS = {"npp": "npp", "houseRender": "houseRender", "photo_polish": "photo_polish", "itemIntake": "itemIntake",
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


def encode(data):
    return base64.b64encode(data).decode('ascii')


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
        "renderer_sha256": sha256((REPO / 'hass' / 'screenshot.cjs').read_bytes()),
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
    for key in ("runner_version", "cases_sha256", "pins_sha256", "assets_sha256", "renderer_commit", "renderer_sha256", "models"):
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

    def __init__(self, directory=TAPES, recorded=None):
        self.entries = {}
        self.sources = {}
        for path in sorted(Path(directory).glob("*.json")):
            if path.name == "MANIFEST.json":
                continue
            self.add(read_json(path))
        if recorded:
            for data in read_json(recorded).values():
                self.add(data)

    def add(self, data):
        self.sources[data['kind']] = data['source']
        for key, entry in data['entries'].items():
            full = f"{data['kind']}:{key}"
            if full in self.entries:
                raise ValueError(f'duplicate tape key {full}')
            self.entries[full] = entry

    def lookup(self, kind, asset, inp, ordinal):
        key = f"{kind}:{asset}:{inp}:{ordinal}"
        if key not in self.entries:
            raise TapeMiss(f"tape miss {kind} ordinal {ordinal} input {inp[:12]} (asset {asset[:12]})")
        return self.entries[key]

    def holds(self, kind, asset, inp):
        return f"{kind}:{asset}:{inp}:0" in self.entries


def photo_bytes(ref):
    scheme, _, name = ref.partition(":")
    return fixture_file(PHOTO_DIRS[scheme], name).read_bytes()


def fixture_file(directory, name):
    root = Path(directory).resolve()
    path = (root / name).resolve(strict=True)
    if not path.is_relative_to(root) or not path.is_file():
        raise ValueError('fixture must be a file inside its corpus')
    return path


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


class TapeUnavailable(Exception):
    """An optional recording is absent, not an assertion pass."""


# Case 26 observer. hass/screenshot.cjs (and so the renderer pin in MANIFEST.json) stays untouched: the live
# replay runs it through card_observer.cjs, which reads the card's img alt and the body of the image resource the
# browser actually loaded, in the same session and at the moment it screenshots the card.
CARD_OBSERVER = HERE / 'card_observer.cjs'
HEX64 = re.compile(r'[0-9a-f]{64}')


def card_image_findings(alt_lacks, versions, delivered, shots, alts):
    """Bind each delivered card PNG to the shown product img alt and the loaded image's SHA-256, both versions.

    versions: {n: npp_versions row}; delivered: {outbox_id: [SHA-256 of each PNG sent to chat]};
    shots: {n: captures whose PNG is that version's card}; alts: {n: imageAlt frozen in that version's draft}.
    Returns (failures, missing): a wrong or stale observation fails, an absent one is only not-run.
    """
    bad, missing = [], []
    for n in (1, 2):
        v = versions.get(n)
        if not v:
            bad.append(f'v{n} was never delivered, so its picture cannot be bound')
            continue
        png = v.get('card_png_sha')
        if delivered.get(v.get('outbox_id')) != [png]:
            bad.append(f'v{n} PNG sent to chat is not its frozen card: want {[png]!r}, got {delivered.get(v.get("outbox_id"))!r}')
        matches = shots.get(n) or []
        if len(matches) > 1:
            bad.append(f'v{n} PNG has {len(matches)} captures, so the shown image is ambiguous')
            continue
        seen = matches[0].get('image') if matches else None
        if not (isinstance(seen, dict) and isinstance(seen.get('alt'), str) and
                all(isinstance(seen.get(k), str) and HEX64.fullmatch(seen[k]) for k in ('image_sha256', 'png_sha256'))):
            missing.append(f'v{n} has no shown-image observation (img alt, loaded image SHA-256) for its delivered PNG')
            continue
        if seen['png_sha256'] != png:
            bad.append(f'v{n} observation is of another PNG: want {png!r}, got {seen["png_sha256"]!r}')
        if seen['image_sha256'] != v.get('image_sha256'):
            bad.append(f'v{n} loaded image SHA-256 is not the delivered image: want {v.get("image_sha256")!r}, '
                       f'got {seen["image_sha256"]!r}')
        if seen['alt'] != alts.get(n):
            bad.append(f'v{n} shown alt is not the frozen alt: want {alts.get(n)!r}, got {seen["alt"]!r}')
        bad.extend(f'v{n} shown alt contains {term}' for term in alt_lacks if term.casefold() in seen['alt'].casefold())
    return bad, missing


def identify_body(photos):
    """What the caption can put into an S2 identify request: nothing. ``Identifier.read`` takes photo bytes only and the
    prompt is pinned (hass/tests/test_npp_stages.py proves both with a recording sink). The photo count is not owner
    text: serialising it as a bare ``1`` made case 13 report its private cost of $1 as a cloud leak."""
    return json.dumps({'stage': 'identify', 'photos': ['<photo>'] * len(photos)})


def stub_body(stage, *payload):
    """The owner-variable input a taped edit-map stub received (his finance-free remainder and the card fields), scanned
    like any cloud body. The copy selector's input is pinned template/phrase IDs only, so it has no owner part."""
    return json.dumps({'stage': stage, 'input': payload}, default=str)


def run_conversation(view, tapes, pinned=None, *, preview=False, recorder=None):
    """Real stages, Conversation and writer, with fixture-only I/O in replay."""
    from unittest.mock import patch
    from hass import conversation, media, npp, photo_polish, sandbox, sandbox_editor
    from hass import preview as renderer
    from hass.npp import research, stages
    from hass.tests import test_npp_job as jf
    from hass.tests.test_conversation import CHAT, OWNER, T0
    from hass.tests.test_editor import git
    from hass.tests.test_npp_undo_journey import _ChatTransport
    from hass.tests.test_preview import BrowserCase

    pinned = pinned or npp.assets()
    asset = pinned[0]['assets']['hass-product-identify/SKILL.md']
    calls, ordinals = Counter(), Counter()
    failures, missing, observed, bodies = [], [], [], []
    live_images = {}  # out png path -> card_observer.cjs observation of the live browser
    inputs = view.get('inputs', {})
    stubs, polish = inputs.get('stubs', {}), inputs.get('polish', {})
    clock, generation, running = VirtualClock(), 0, set()
    world = World(inputs.get('web'), clock, inputs.get('latency'))
    models = Models(stubs, clock, world, inputs.get('latency'))

    def deny(*_a, **_k):
        failures.append('unexpected untaped adapter call')
        raise TapeMiss(failures[-1])

    def replay(kind, pin, digest, create=None, optional=False):
        ordinal = ordinals[kind, digest]
        ordinals[kind, digest] += 1
        try:
            return tapes.lookup(kind, pin, digest, ordinal)['output']
        except TapeMiss as error:
            if create is not None:
                return recorder.record(kind, pin, digest, ordinal, create)
            if optional and (not tapes.holds(kind, pin, digest) or
                             (kind == 'capture' and view['id'] != 24)):
                missing.append(str(error))
                raise TapeUnavailable(str(error)) from error
            failures.append(str(error))  # stages defensively catch exceptions
            raise

    def identify(photos):
        photos = tuple(photos)
        digest = sha256(photos[0]) if len(photos) == 1 else sha256(b''.join(hashlib.sha256(p).digest() for p in photos))
        calls['identify'] += 1
        bodies.append(identify_body(photos))
        if 'identify' in stubs:
            return SimpleNamespace(evidence=stubs['identify'])
        create = (lambda: recorder.identify(pinned, photos)) if recorder else None
        return SimpleNamespace(evidence=replay('s2', asset, digest, create, optional=True))

    def research_fixture(*_args, **kwargs):
        try:
            result = research.research(pinned, search=world.search, fetch=world.fetch, extract=models.extract,
                                       verify=models.verify, clock=clock.monotonic,
                                       **{k: v for k, v in kwargs.items() if k != 'web'})
        except TapeMiss as error:
            failures.append(str(error))
            raise
        failures.extend(eval_module().audit_research(
            result.receipt, result.facts, {url: row[0] for url, row in world.pages.items()},
            queries=world.queries, fetched=world.fetched, sources=json.loads(pinned[1][research.ASSETS + 'sources.json']),
            seed={k: kwargs['owner_' + k] for k in ('maker', 'town', 'url')},
            label={'brand': kwargs['label_brand'], 'confidence': kwargs['label_confidence']}))
        return result

    fx = jf.JobTests()
    fx.setUp()
    fx.transport = _ChatTransport()
    fx.settings.pop('liveSite', None)  # no live verifier, even for live-shaped fixture rows
    fx.settings.update({SETTING_KEYS[k]: v for k, v in view.get('settings', {}).items() if k in SETTING_KEYS})
    try:
        browser = None
        if preview or recorder:
            BrowserCase.make_previewer(SimpleNamespace(repo=fx.repo, env=None))
            browser = renderer.Previewer(fx.repo.wt, viewports=('phone',))
        fx.base = fx.repo.head()
        gate = sandbox.Gate(lambda: {'approvals': 'private'}, lambda: {('site', 'sandbox'): str(fx.repo.wt)})
        render_asset = sha256((REPO / 'hass' / 'screenshot.cjs').read_bytes())

        def capture(files, target, out, assets=None):
            if browser is not None and recorder is None:
                if view['id'] != 26 or not target.get('cardOnly'):
                    return browser.capture(files, target, out, assets=assets)
                import tempfile
                from unittest.mock import patch as patch_script
                with tempfile.TemporaryDirectory(prefix='npp-observe-') as raw:
                    sink = Path(raw) / 'image.json'
                    with patch_script.object(renderer, 'SCRIPT', CARD_OBSERVER):
                        shot = browser.capture(files, {**target, 'observeTo': str(sink)}, out, assets=assets)
                    try:
                        seen = json.loads(sink.read_text())
                    except (OSError, ValueError):
                        seen = None
                if isinstance(seen, dict):
                    live_images[str(out)] = {'alt': seen.get('alt'), 'image_sha256': seen.get('imageSha256'),
                                             'png_sha256': seen.get('pngSha256')}
                return shot
            hashes = {key: sha256(val if isinstance(val, bytes) else val.encode())
                      for key, val in {**files, **(assets or {})}.items()}
            digest = sha256(json.dumps([hashes, target], sort_keys=True).encode())

            def draw():
                shot = browser.capture(files, target, out, assets=assets)
                return {**{k: v for k, v in shot.items() if k != 'png'},
                        'png_b64': encode(Path(shot['png']).read_bytes()) if shot.get('png') else None}

            try:
                # Only the case with a complete versioned capture set expects every
                # ordinal. Other cases can share some rendered inputs without having
                # a complete recording for their own edit/retry sequence.
                shot = dict(replay('capture', render_asset, digest, draw if recorder else None, optional=True))
            except (TapeMiss, TapeUnavailable):
                return {'ok': False, 'png': None, 'error': 'capture tape unavailable'}
            png = shot.pop('png_b64')
            if png:
                out.parent.mkdir(exist_ok=True)
                out.write_bytes(base64.b64decode(png, validate=True))
            return {**shot, 'png': str(out) if png else None}

        def start():
            fx.start()
            fx.conv.editor = sandbox_editor.SiteEditor(fx.repo.state, gate, deny, clock=lambda: fx.now)
            fx.conv.previewer = SimpleNamespace(capture=capture)
            port = npp.stages_for(fx.conv, pinned)
            if port is None:
                raise TapeMiss('the production stages are not composed')
            fx.conv.npp.stages = port
            port.identifier.read = identify
            port.selector = (lambda *_a, **_k: stubs['copy']) if 'copy' in stubs else None

            def mapped(_prompt, _schema, text, fields):
                bodies.append(stub_body('edit_map', text, fields))
                return stubs['edit_map']

            port.mapper = mapped if 'edit_map' in stubs else deny

        def launch(root, sha, *, log=None, **_kwargs):
            calls['image_edit'] += 1
            if generation:
                calls['image_edit_after_restart'] += 1
            epoch = generation
            running.add(sha)

            def complete():
                observe_late = 'polish_late_logged' in view['expect']
                if epoch != generation or (not observe_late and photo_polish.decision(root, sha) is not None):
                    running.discard(sha)
                    return
                source = polish.get('source')
                if source == 'record':
                    web = media.web_copy(root, sha)
                    pin = sha256((photo_polish.MODEL + '\n' + photo_polish.PROMPT).encode())
                    try:
                        data = base64.b64decode(replay('image', pin, web['web_sha256'],
                                               (lambda: recorder.edit(Path(web['path']))) if recorder else None,
                                               optional=True), validate=True)
                    except TapeUnavailable:
                        running.discard(sha)
                        return
                elif source == 'file':
                    data = fixture_file(CASES / 'edits', polish['file'].removeprefix('npp:edits/')).read_bytes()
                elif source == 'error':
                    data = None
                else:
                    deny()

                def transport(_src, out, _timeout):
                    if data is None:
                        return {'ok': False, 'code': 'transport'}
                    out.write_bytes(data)
                    return {'ok': True}

                if observe_late:
                    fx.now = T0 + timedelta(seconds=clock.monotonic())
                    before = outbox_count()
                    decision = photo_polish.decision(root, sha)
                    assert log is not None
                    with patch.object(log, 'record', wraps=log.record) as records:
                        code = photo_polish.run(root, sha, log=log, transport=transport)
                    settle()
                    late.update(logged=any(c.args[:2] == ('error', 'polish-late') for c in records.call_args_list),
                                messages=outbox_count() - before, dropped=code == 'late' and decision is not None
                                and decision == photo_polish.decision(root, sha))
                else:
                    photo_polish.run(root, sha, log=log, transport=transport)

            clock.at(clock.monotonic() + polish.get('latency_s', 0), 1, complete)

        class Sender(_ChatTransport):
            def send_card(self, row, chat, text, png_path, digest):
                attempts[row] += 1
                if self.fail:
                    raise OSError('fixture send outage')
                super().send_card(row, chat, text, png_path, digest)
                delivered.setdefault(row, []).append(sha256(Path(png_path).read_bytes()))
                self.receipts[row] = dict(state='confirmed', png_sha256=digest, provider_guid=f'fixture-card-{row}',
                                          confirmed_at=fx.now.isoformat())

        fx.transport = Sender()
        fx.transport.fail = any(spec.get('retry_send') for spec in view['turns'])
        current = []
        fx.fetch = lambda _pid, count: current[:count]
        attempts, late, captures, delivered = Counter(), {}, {}, {}
        schedule = inputs.get('outbox', {}) if view['id'] == 25 else {}

        def outbox_count():
            return fx.conv.db.execute('SELECT count(*) FROM outbox').fetchone()[0]

        start()

        if view['id'] in (26, 36):
            def observe_capture(files, target, out, assets=None):
                shot = capture(files, target, out, assets=assets)
                if target.get('cardOnly') and shot.get('ok') and shot.get('png'):
                    captures.setdefault(sha256(Path(shot['png']).read_bytes()), []).append({
                        'description': target['description'] if shot['checks'].get('description') is True else None,
                        'text': shot.get('cardText'), 'assets': {p: sha256(b) for p, b in (assets or {}).items()},
                        'image': shot.get('cardImage') or live_images.pop(str(out), None),
                    })
                return shot

            fx.conv.previewer = SimpleNamespace(capture=observe_capture)

        if view['id'] == 36 and fx.conv.npp and fx.conv.npp.stages:
            # Count the actual supplied nonconforming model response, not a local default.
            select = fx.conv.npp.stages.selector
            assert select is not None

            def fabricated_copy(*args, **kwargs):
                calls['copy'] += 1
                return select(*args, **kwargs)

            fx.conv.npp.stages.selector = fabricated_copy

        def flush():
            try:
                if schedule:
                    # Hold transport polling, not the receipt or eligibility gate. Once a
                    # hold expires even a superseded row reaches the real dispatch check.
                    unsent = fx.conv.outbox.unsent
                    def available():
                        for row in unsent():
                            v = fx.conv.db.execute('SELECT n FROM npp_versions WHERE outbox_id=?', (row['id'],)).fetchone()
                            timing = schedule.get(f'v{v[0]}', {}) if v else {}
                            if clock.monotonic() >= timing.get('held_until_s', timing.get('delivered_at_s', 0)):
                                yield row
                    with patch.object(fx.conv.outbox, 'unsent', available):
                        fx.flush()
                else:
                    fx.flush()
            except OSError:
                if not fx.transport.fail:
                    raise

        def settle():
            for _ in range(12):
                flush()
                if fx.scheduler.steps:
                    # The executor may finish after a competing inbound turn or a deadline.
                    future, fn, args = fx.scheduler.steps[0]
                    job_runner = fx.conv.npp
                    if inputs.get('stage_ready_at_s') and job_runner and job_runner.running:
                        segment = job_runner.running[0][0]
                        started = fx.conv.db.execute('SELECT started_by FROM npp_segments WHERE segment_id=?', (segment,)).fetchone()
                        if started and clock.monotonic() < inputs['stage_ready_at_s'].get(started[0], {}).get(fn.__name__, 0):
                            break
                    if fn.__name__ == 'render' and running:
                        break
                    fx.scheduler.steps.pop(0)
                    if missing:
                        future.set_result(None)
                        continue
                    try:
                        future.set_result(fn(*args))
                    except (TapeMiss, TapeUnavailable) as error:
                        future.set_exception(error)
                elif fx.conv.npp is not None and not fx.conv.npp.running:
                    flush()
                    break

        turns = view['turns']
        for index, spec in enumerate(turns):
            def play(spec=spec, index=index):
                nonlocal generation
                fx.now = T0 + timedelta(seconds=clock.monotonic())
                before = len(fx.transport.texts), len(fx.transport.cards), len(fx.transport.previews)
                if spec.get('restart'):
                    generation += 1
                    running.clear()
                    start()
                if spec.get('retry_send'):
                    fx.transport.fail = False
                snapshot = {}
                if schedule:
                    snapshot = dict(approvals=fx.conv.db.execute('SELECT count(*) FROM approvals').fetchone()[0],
                                    npp_approvals=fx.conv.db.execute('SELECT count(*) FROM npp_approvals').fetchone()[0],
                                    commits=int(git(fx.repo.wt, 'rev-list', '--count', f'{fx.base}..HEAD')),
                                    versions={v['n']: v['state'] for v in fx.conv.db.execute('SELECT n,state FROM npp_versions')})
                text = spec.get('text')
                outcome = None
                prior_job = fx.job()
                polish_ready = bool(index == 1 and 'polish_settled_before_answer' in view['expect'] and
                                    prior_job and prior_job['photo_sha'] and
                                    photo_polish.decision(fx.root, prior_job['photo_sha']))
                if text is not None:
                    row = fx.job()
                    current[:] = [photo_bytes(ref) for ref in spec.get('photos', [])]
                    code = row['job_id'] if row else 'none'
                    ref = spec.get('reply_to')
                    version = fx.version(int(ref[1:])) if ref and row else None
                    arrival = fx.now
                    kwargs = {}
                    if spec.get('edit_published_description') and row and row['state'] == 'published':
                        approved = fx.version(row['current_version'])
                        change = fx.conv.editor.show(approved['change_id'])['change']
                        pid = next(r['key'] for r in change['records'] if r['collection'] == 'products')
                        fx.interpreter.mapping[text] = {'revises': None, 'ops': [{'op': 'product.edit', 'args': {
                            'id': pid, 'description': spec['edit_published_description']}}]}
                    if ref:
                        if 'reply_to' not in conversation.Inbound.__dataclass_fields__:
                            missing.append('Conversation.Inbound does not yet carry a reply reference')
                        else:
                            kwargs['reply_to'] = version['transport_message_id'] if version else 'fixture-undelivered'
                    msg = conversation.Inbound(f'fixture-{index}', CHAT, OWNER, text.replace('{code}', code),
                                               received_at=arrival.isoformat(), attachments=len(current), **kwargs)
                    outcome = fx.conv.handle(msg, forwarded_at=arrival)
                settle()
                version = fx.version(fx.job()['current_version']) if fx.job() and fx.job()['current_version'] else None
                posted = fx.conv.npp_posted(version['change_id']) if outcome == 'approved' and version and version['change_id'] else None
                observed.append(dict(turn=index, result=outcome, before=before, posted=posted, polish_ready=polish_ready,
                                     snapshot=snapshot))

            clock.at(spec['at_s'], 0, play)
            # Pump between turns, including while polish is in flight. A restart invalidates queued work.
        horizon = max(t['at_s'] for t in turns) + max(80, view.get('settle_until_s', 0))
        def tick():
            if not (schedule or fx.scheduler.steps or (fx.conv.npp is not None and fx.conv.npp.running) or running):
                return
            fx.now = T0 + timedelta(seconds=clock.monotonic())
            settle()
        with patch.object(stages.research_hermes, 'run', side_effect=research_fixture), \
                patch.object(photo_polish, 'start', side_effect=launch), patch.object(photo_polish, '_running', running):
            for seconds in range(int(horizon) + 1):
                if inputs.get('stage_ready_at_s') or any(t['at_s'] - 1 <= seconds <= t['at_s'] + 80 for t in turns):
                    clock.at(seconds, 2, tick)
            clock.run_until(horizon)
        row = fx.job()
        db = fx.conv.db
        versions = [dict(v) for v in db.execute('SELECT * FROM npp_versions ORDER BY n')]
        state = {
            'state': row['state'] if row else None,
            'draft_rows': db.execute('SELECT count(*) FROM drafts').fetchone()[0],
            'version_rows': sum(v['state'] != 'building' for v in versions),
            'approvals': db.execute('SELECT count(*) FROM approvals').fetchone()[0],
            'commits': int(git(fx.repo.wt, 'rev-list', '--count', f'{fx.base}..HEAD')),
            'cards': len(fx.transport.cards),
        }
        card_rows = list(fx.transport.cards.items())
        turn_by_reply = {r['reply_outbox_id']: r['provider_id'] for r in db.execute(
            'SELECT reply_outbox_id, provider_id FROM npp_turns WHERE reply_outbox_id IS NOT NULL')}
        for index, entry in enumerate(observed):
            a, b, c = entry['before']
            x, y, z = observed[index + 1]['before'] if index + 1 < len(observed) else (
                len(fx.transport.texts), len(fx.transport.cards), len(fx.transport.previews))
            entry['texts'] = fx.transport.texts[a:x]
            entry['cards'] = [v[0] for _, v in card_rows[b:y]]
            entry['card_reply_providers'] = [turn_by_reply.get(row) for row, _ in card_rows[b:y]]
            entry['previews'] = [v[0] for v in fx.transport.previews[c:z]]
            entry['card_sent_at_s'] = [(datetime.fromisoformat(fx.transport.receipts[row]['confirmed_at']) - T0).total_seconds()
                                       for row, _ in card_rows[b:y]]
        if schedule:
            # A delayed delivery belongs to its durable inbound binding, not
            # whichever owner input happened just before transport confirmation.
            for entry in observed:
                for field in ('cards', 'card_reply_providers', 'card_sent_at_s'):
                    entry[field] = []
            for row_id, card in card_rows:
                provider = turn_by_reply.get(row_id)
                if not provider or not re.fullmatch(r'fixture-\d+', provider) or int(provider[8:]) >= len(observed):
                    failures.append('card missing a durable owner-turn binding')
                    continue
                entry = observed[int(provider.removeprefix('fixture-'))]
                entry['cards'].append(card[0])
                entry['card_reply_providers'].append(provider)
                entry['card_sent_at_s'].append((datetime.fromisoformat(fx.transport.receipts[row_id]['confirmed_at']) - T0).total_seconds())
        calls.update(world.calls)
        failures.extend(world.violations)
        gaps = []
        if not missing:
            failures += check_conversation(view['expect'], observed, state, calls, bodies, pinned[2])
            if 'polish_settled_before_answer' in view['expect'] and observed[1]['polish_ready'] != view['expect']['polish_settled_before_answer']:
                failures.append('polish did not settle before the price answer')
            decision = photo_polish.decision(fx.root, row['photo_sha']) if row and row['photo_sha'] else None
            failures += check_card(view, fx, state, versions, decision, gaps, attempts, late, observed, captures,
                                   delivered, missing)
        return failures, {'observed': observed, 'state': state, 'calls': dict(calls), 'missing': sorted(set(missing)), 'gaps': gaps}
    finally:
        fx.doCleanups()


def reply_kind(text, replies):
    from hass.npp import job
    from hass.ops.photos import RETAKE
    if text == job.EXPIRED:
        return "expired"
    if text == RETAKE:
        return "retake"
    if text.startswith("Posted"):
        return "posted"
    if text in replies['guards'].values() or "already saved" in text.lower():
        return "guard"
    if text in replies["questions"].values() or text.endswith("?"):
        return "question"
    return "other"


def check_conversation(expect, observed, state, calls, bodies, replies):
    bad = []
    for want in expect.get("replies", []):
        seen = observed[want['turn']]
        if 'answers_turn' in want and seen['card_reply_providers'] != [f"fixture-{want['answers_turn']}"]:
            bad.append(f"turn {want['turn']}: card does not answer owner turn {want['answers_turn']}")
        if 'sent_by_s' in want and (not seen['card_sent_at_s'] or max(seen['card_sent_at_s']) > want['sent_by_s']):
            bad.append(f"turn {want['turn']}: card confirmation missed deadline {want['sent_by_s']}")
        if 'sent_at_s' in want and seen['card_sent_at_s'] != [want['sent_at_s']]:
            bad.append(f"turn {want['turn']}: expected card confirmation at {want['sent_at_s']}")
        kinds = [(text, reply_kind(text, replies)) for text in seen['texts']]
        kinds += [(text, 'card') for text in seen['cards']]
        # Sandbox acknowledgement is expected instead of an actual live send. Check
        # the real S13 link builder separately, using the committed change ID.
        for text in seen['previews']:
            if text.startswith('To undo that,') and 'to hidden' in text:
                kinds.append((text, 'undo_draft'))
            elif text.startswith('Saved and checked:') and seen['posted']:
                kinds.append((seen['posted'], reply_kind(seen['posted'], replies)))
            elif want.get('legacy_proposal') and 'reply yes ' in text.lower():
                kinds.append((text, 'card'))
            else:
                kinds.append((text, reply_kind(text, replies)))
        texts = [text for text, _ in kinds]
        if len(texts) != want["count"]:
            bad.append(f"turn {want['turn']}: want {want['count']} reply, got {len(texts)}")
            continue
        for text, kind in kinds:
            if kind != want["kind"]:
                bad.append(f"turn {want['turn']}: reply kind {kind!r}, want {want['kind']!r}")
            text = re.sub(r'(?<=yes )[A-Z0-9]{4,12}(?=-\d+)', '<code>', text, flags=re.I)
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
    total = sum(len(o[k]) for o in observed for k in ('texts', 'cards', 'previews'))
    if "total_replies" in expect and total != expect["total_replies"]:
        bad.append(f"total_replies: want {expect['total_replies']}, got {total}")
    if "state" in expect and state["state"] != expect["state"]:
        bad.append(f"state: want {expect['state']}, got {state['state']}")
    if expect.get("draft_rows") == "none" and (state["draft_rows"] or state["version_rows"] or state["cards"]):
        bad.append(f"no_draft: drafts {state['draft_rows']}, versions {state['version_rows']}, cards {state['cards']}")
    if "approval_rows" in expect and state["approvals"] != expect["approval_rows"]:
        bad.append(f"approval_rows: want {expect['approval_rows']}, got {state['approvals']}")
    if "commits" in expect and state["commits"] != expect["commits"]:
        bad.append(f"commits: want {expect['commits']}, got {state['commits']}")
    bad += check_calls(expect, calls)
    for digit in expect.get("cloud_bodies_lack_digits_from", ()):
        if any(digit in re.findall(r"\d+", body) for body in bodies):
            bad.append(f"no_private_values: digit {digit} reached a cloud request body")
    return bad


def check_card(view, fx, state, versions, decision, gaps, attempts, late, observed, captures, delivered=None,
               missing=None):
    """Bind delivery and publish claims to stored versions and actual committed bytes."""
    want, bad = view['expect'], []
    db = fx.conv.db
    versions = {v['n']: v for v in versions}
    latest = versions[max(versions)] if versions else {}
    approved = [v for v in versions.values() if v['state'] == 'approved']

    def same(contract, actual, expected):
        if actual != expected:
            bad.append(f'{contract}: want {expected!r}, got {actual!r}')

    same('terminal', state['state'], view['terminal'])
    for key, actual in [('cards_sent', state['cards']), ('variant', latest.get('image_variant')),
                        ('approved_version', approved[0]['n'] if len(approved) == 1 else None)]:
        if key in want:
            same(key, actual, want[key])
    for version in want.get('versions', []):
        n = version['n']
        if n not in versions:
            bad.append(f'v{n} missing')
            continue
        got = versions[n]
        if 'sent' in version:
            same(f'v{n}.sent', bool(attempts[got['outbox_id']]), version['sent'])
        for key, value in [('delivered', bool(got['delivered_at'])), ('approved', got['state'] == 'approved'),
                           ('superseded', got['state'] == 'superseded'), ('state', got['state'])]:
            if key in version:
                same(f'v{n}.{key}', value, version[key])
    for key, value in want.get('polish_decision', {}).items():
        same(f'polish_decision.{key}', (decision or {}).get(key), value)
    for v in approved:
        path = fx.repo.wt / 'storefront-mockup' / v['image_path']
        if not path.is_file() or sha256(path.read_bytes()) != v['image_sha256']:
            bad.append('published photo does not match the frozen SHA')
        receipt = db.execute('SELECT n,outbox_id,transport_message_id FROM npp_approvals WHERE job_id=? AND n=?',
                             (v['job_id'], v['n'])).fetchone()
        same('approval receipt binds the delivered version', tuple(receipt) if receipt else None,
             (v['n'], v['outbox_id'], v['transport_message_id']))
        approval = db.execute('SELECT draft_hash, approved_at FROM approvals JOIN npp_approvals '
                              'ON approval_id=id WHERE job_id=? AND n=?', (v['job_id'], v['n'])).fetchone()
        same('approval receipt binds the draft hash', approval[0] if approval else None, v['draft_hash'])
        if not (approval and v['delivered_at'] and datetime.fromisoformat(v['delivered_at']) < datetime.fromisoformat(approval[1])):
            bad.append('approval did not follow delivery')
    if 'approved_draft_hash' in want:
        n = int(want['approved_draft_hash'].removeprefix('v'))
        same('approved_draft_hash', approved[0]['draft_hash'] if len(approved) == 1 else None,
             versions.get(n, {}).get('draft_hash'))
    if view['terminal'] == 'published':
        same('exactly one approved version', len(approved), 1)
        same('exactly one local publish commit', state['commits'], 1)
    if 'undo' in want:
        same('undo does not commit', state['commits'], want['undo']['commits'])
        pending = db.execute("SELECT change_id FROM drafts WHERE state='proposed'").fetchall()
        undo = fx.conv.editor.show(pending[0][0]).get('draft', {}) if len(pending) == 1 else {}
        same('undo proposes only a revert of this publish', undo.get('ops'),
             [{'op': 'history.revert', 'args': {'changeId': approved[0]['change_id']}}] if len(approved) == 1 else None)
    if 'sent_at_null_until_s' in want:
        from hass.tests.test_conversation import T0
        out = db.execute('SELECT sent_at FROM outbox WHERE id=?', (versions.get(1, {}).get('outbox_id'),)).fetchone()
        minimum = T0 + timedelta(seconds=want['sent_at_null_until_s'])
        same('outbox not sent before retry', bool(out and out[0] and datetime.fromisoformat(out[0]) >= minimum), True)
        same('retry confirms delivery', bool(versions.get(1, {}).get('delivered_at')), want['v1_delivered_after_retry'])
        same('retry needs fresh yes', not approved, want['v1_needs_fresh_yes'])
    if 'picture_line' in want:
        note = next((text for line, *_ in reversed(list(fx.transport.cards.values()))
                     if (text := re.search(r'picture: [^)]*', line))), None)
        same('picture_line', note[0] if note else None, want['picture_line'])
    if 'install_path_re' in want and not re.search(want['install_path_re'], latest.get('image_path') or ''):
        bad.append('installed image path did not match the fixture pattern')

    if 'segment2_started_at_s' in want:
        from hass.tests.test_conversation import T0
        answer = db.execute('SELECT started_by, accepted_at, deadline_at FROM npp_segments '
                            'ORDER BY segment_id LIMIT 1 OFFSET 1').fetchone()
        when = T0 + timedelta(seconds=want['segment2_started_at_s'])
        cap = fx.conv.npp.pins['segment']['cap_s']
        same('segment 2 starts from the answer with a fresh cap', tuple(answer) if answer else None,
             ('fixture-1', when.isoformat(), (when + timedelta(seconds=cap)).isoformat()))

    contradiction = view['id'] == 31 and want.get('listing') == {'maker_panel': False}
    follows_edit = view['id'] in (19, 21, 26, 32, 36) or contradiction

    def version_record(version):
        found = fx.conv.editor.show(version.get('change_id') or '')
        return found.get('change') or found.get('draft') or {}

    def committed_product(version):
        record = version_record(version)
        pid = next((r['key'] for r in record.get('records', []) if r['collection'] == 'products'), None)
        return fx.repo.product(pid) if pid else {}

    if follows_edit and 'edit_keeps' in want and not bad:
        drafts = [version_record(versions.get(n, {})) for n in (1, 2)]
        def frozen_fields(draft, version):
            records = draft.get('records', [])
            product = next((r['after'] for r in records if r['collection'] == 'products'), {})
            maker = next((r['after'] for r in records if r['collection'] == 'makers'), {})
            return {**product, 'origin': (product.get('supplier'), product.get('producerKey')),
                    'maker_panel': maker, 'story': maker.get('story'), 'picture_bytes': version.get('image_sha256')}
        before, after = [frozen_fields(draft, versions.get(n, {})) for n, draft in enumerate(drafts, 1)]
        if not before.get('name') or not after.get('name'):
            bad.append('missing frozen product records for edit comparison')
        for field in want['edit_keeps']:
            same(f'edit preserves {field}', after.get(field), before.get(field))

    if view['id'] == 32 and len(approved) == 1:
        from decimal import Decimal
        from hass.npp import picture, private_numbers
        product = committed_product(approved[0])
        size = want['listing']['label_size_kept']
        same('equal price retained in committed price field', product.get('sellingPrice'), want['listing']['price'].removeprefix('$') + ' each')
        path = fx.repo.wt / 'storefront-mockup' / approved[0]['image_path']
        read = picture.read_text(path.read_bytes()) if path.is_file() else None
        same('equal label size retained in committed picture', bool(private_numbers.literal_spans(
            ' '.join((read or '').split()), [size])), True)
        private = tuple(Decimal(value) for value in view['inputs']['private'].values())
        for field in ('name', 'description', 'imageAlt'):
            text = product.get(field, '')
            permit = private_numbers.literal_spans(text, [size]) if field == 'name' else ()
            same(f'committed {field} excludes unbound private numbers', private_numbers.problem(text, private, permitted=permit), None)
        # Each form must produce the same expected price/size and pass the
        # real image and card-DOM gates before it can record an approval.

    if contradiction and len(approved) == 1:
        product = committed_product(approved[0])
        same('conflicting maker panel is omitted', bool(product and not product.get('producerKey')), True)
        public = json.dumps(product) + '\n' + '\n'.join(row[0] for row in fx.transport.cards.values())
        for term in want.get('public_lacks', ()):
            same('conflicting maker is absent from public fields and card', term.casefold() in public.casefold(), False)

    newly_covered = set()
    if 'polish_late_logged' in want:
        same('polish late logged', late.get('logged'), want['polish_late_logged'])
        same('late polish left the write-once decision unchanged', late.get('dropped'), True)
        same('messages on late polish', late.get('messages'), want['messages_on_polish_late'])
        hashes = [versions.get(n, {}).get('image_sha256') for n in (1, 2)]
        same('v2 bytes equal v1', bool(hashes[0] and hashes[0] == hashes[1]), want['v2_bytes_equal_v1'])
        newly_covered.update({'polish_late_logged', 'messages_on_polish_late', 'v2_bytes_equal_v1'})
    if view['id'] == 25:
        same('v2 was queued (before supersession)', observed[3]['snapshot']['versions'].get(2), 'queued')
        same('v3 was building at first bare yes', observed[4]['snapshot']['versions'].get(3), 'building')
        same('v3 was delivered at second bare yes', observed[5]['snapshot']['versions'].get(3), 'delivered')
        pending = db.execute("SELECT code, ops_json FROM drafts WHERE state='proposed'").fetchall()
        same('one separate pending F6 draft', len(pending), 1)
        if len(pending) == 1 and len(approved) == 1:
            after = view['turns'][7]['edit_published_description']
            product = committed_product(approved[0])
            same('F6 edit is a new draft with a separate code', bool(pending[0]['code'] and
                 pending[0]['code'] != fx.job()['job_id']), True)
            same('F6 edits the posted product', json.loads(pending[0]['ops_json']),
                 [{'op': 'product.edit', 'args': {'id': product.get('id'), 'description': after}}])
            same('F6 was not applied', product.get('description') == after, False)
        for turn in (4, 5, 6):
            before = observed[turn]['snapshot']
            same(f'approval rows before turn {turn}', before['approvals'], want['approval_rows_before_turn_6'])
            same(f'NPP approval rows before turn {turn}', before['npp_approvals'], want['approval_rows_before_turn_6'])
            same(f'commits before turn {turn}', before['commits'], want['commits_before_turn_6'])
        for n, v in versions.items():
            timing = view['inputs']['outbox'].get(f'v{n}', {})
            if 'delivered_at_s' in timing:
                from hass.tests.test_conversation import T0
                same(f'v{n} durable delivery time', v['delivered_at'],
                     (T0 + timedelta(seconds=timing['delivered_at_s'])).isoformat())
            if 'sends' in timing:
                same(f'v{n} transport attempts', attempts[v['outbox_id']], len(timing['sends']))
        newly_covered.update({'approval_rows_before_turn_6', 'commits_before_turn_6'})

    if view['id'] in (26, 36) and len(approved) == 1:
        product = committed_product(approved[0])
        shots = [captures.get(versions.get(n, {}).get('card_png_sha'), []) for n in (1, 2)]
        if view['id'] == 26:
            from hass import media
            gate = view['inputs']['gate_expect']
            same('polish fidelity rejection code', (decision or {}).get('code'), gate['code'])
            same('polish fidelity accepted', (decision or {}).get('use') == 'polished', gate['ok'])
            photo = fx.job()['photo_sha']
            owner_sha = media.web_copy(fx.root, photo)['web_sha256']
            for n, matches in enumerate(shots, 1):
                v = versions.get(n, {})
                same(f'v{n} owner web copy bytes', v.get('image_sha256'), owner_sha)
                asset = 'storefront-mockup/' + (v.get('image_path') or '')
                same(f'v{n} capture input has owner web copy bytes', [m['assets'].get(asset) for m in matches], [owner_sha])
            alt = product.get('imageAlt', '')
            same('applied alt exists', bool(alt), True)
            for term in want['alt_lacks']:
                same(f'applied alt contains {term}', term.casefold() in alt.casefold(), False)
            frozen_alts = {n: next((r['after'].get('imageAlt') for r in version_record(versions.get(n, {})).get('records', [])
                                    if r['collection'] == 'products'), None) for n in (1, 2)}
            found, absent = card_image_findings(want.get('card_alt_lacks', []), versions, delivered or {},
                                                {n: shots[n - 1] for n in (1, 2)}, frozen_alts)
            bad.extend(found)
            (bad if missing is None else missing).extend(absent)  # no sink for not-run: never a silent pass
            newly_covered.update({'alt_lacks', 'bytes_equal', 'card_alt_lacks'})
        else:
            description = product.get('description')
            same('applied fallback description', description, want['description_equals'])
            for n, matches in enumerate(shots, 1):
                same(f'v{n} browser description equals applied',
                     len(matches) == 1 and description is not None and matches[0]['description'] == description,
                     want['preview_description_equals_applied'])
            card_text = [m['text'] for group in shots for m in group]
            same('captured both product cards’ DOM text', len(card_text) == 2 and all(card_text), True)
            public = json.dumps(version_record(approved[0]).get('records', [])) + json.dumps(card_text) + '\n'.join(
                card[0] for card in fx.transport.cards.values())
            for term in want['public_lacks']:
                same(f'fabricated claim in public listing or card: {term}', term.casefold() in public.casefold(), False)
            newly_covered.update({'description_equals', 'preview_description_equals_applied', 'public_lacks'})

    # Never report a fixture green when its declared contract has no observer.
    covered = {'state', 'replies', 'total_replies', 'draft_rows', 'approval_rows', 'commits', 'calls',
               'checks', 'cards_sent', 'variant', 'versions', 'undo', 'polish_decision', 'approved_version',
               'approved_draft_hash', 'sent_at_null_until_s', 'v1_delivered_after_retry', 'v1_needs_fresh_yes',
               'frozen_sha_equals_committed_file', 'preview_sha_equals_frozen_equals_committed', 'picture_line',
               'install_path_re', 'cloud_bodies_lack_digits_from', 'research'}
    covered.update(newly_covered)
    if 'segment2_started_at_s' in want and want.get('segment_cap_measured_from') == 'answer':
        covered.update({'polish_settled_before_answer', 'segment2_started_at_s', 'segment_cap_measured_from'})
    if follows_edit:
        covered.add('edit_keeps')
    if view['id'] == 32 and len(approved) == 1:
        covered.update({'listing', 'private_in_public', 'same_result_for_spoken_and_digit_forms'})
    if contradiction and len(approved) == 1:
        covered.update({'listing', 'public_lacks'})
    if unsupported := want.keys() - covered:
        gaps.append('unobserved expectations: ' + ', '.join(sorted(unsupported)))
    return bad


# ---------------------------------------------------------------- case driver


def run_case(case_id, tapes=None, pinned=None, preview=False, recorder=None):
    from hass import npp
    pinned = pinned or npp.assets()
    tapes = tapes or Tapes()
    case = load_cases()[case_id]

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
            failures, evidence = run_conversation(view, tapes, pinned, preview=preview, recorder=recorder)
            layer = 'conversation' if view['path'] == 'question' else 'card'
            missing = evidence['missing']
            gaps = evidence['gaps']
            layers[layer] = 'fail' if failures else 'gap' if gaps else 'not-run' if missing else 'pass'
            notes[layer] = failures + missing + gaps
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


def _worker(args):  # top level so a process pool can pickle it
    case_id, preview, directory, recorded = args
    return run_case(case_id, Tapes(directory, recorded), preview=preview)


def run_all(ids, jobs=1, *, preview=False, directory=TAPES, recorder=None, recorded=None):
    ids = sorted(ids)
    if jobs > 1:
        with concurrent.futures.ProcessPoolExecutor(max_workers=jobs) as pool:
            return [row for rows in pool.map(_worker, [(i, preview, directory, recorded) for i in ids]) for row in rows]
    from hass import npp
    pinned, tapes = npp.assets(), Tapes(directory, recorded)
    return [row for case_id in ids for row in run_case(case_id, tapes, pinned, preview, recorder)]


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


class Recorder:
    """Only the attended CLI attaches paid ports; count calls before dispatch."""

    def __init__(self, caps, *, codex=None, images=None):
        from hass import cloud_codex, photo_polish
        self.caps, self.entries = caps, {}
        self.codex = codex if codex is not None else cloud_codex.Runner()
        self.images = images if images is not None else photo_polish.HermesTransport()

    def identify(self, pinned, photos):
        from hass.npp.identify import Identifier

        def request(body):
            self.caps.take('codex')
            return self.codex(body)

        reading = Identifier(pinned, runner=request).read(photos)
        if reading.evidence is None:
            raise TapeMiss('recorded identification did not return schema-valid evidence')
        return reading.evidence

    def edit(self, path):
        import tempfile
        from hass import photo_polish

        with tempfile.TemporaryDirectory(prefix='npp-edit-') as tmp:
            out = Path(tmp) / 'edit.img'
            self.caps.take('images')
            got = self.images(path, out, photo_polish.TIMEOUT_S)
            if not (got.get('ok') and out.is_file() and 0 < out.stat().st_size <= photo_polish.MAX_OUTPUT_BYTES):
                raise TapeMiss('recorded image edit did not return bounded image bytes')
            return encode(out.read_bytes())

    def record(self, kind, pin, digest, ordinal, create):
        rows = self.entries.setdefault(kind, {})
        key = f'{pin}:{digest}:{ordinal}'
        if key not in rows:
            rows[key] = {'output': create()}
        return rows[key]['output']

    def save(self, path):
        # Exclusive file, private from its first byte; never overwrite an existing tape.
        data = {kind: {'kind': kind, 'source': 'attended recording', 'entries': entries}
                for kind, entries in self.entries.items() if entries}
        fd = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
        with os.fdopen(fd, 'w', encoding='utf-8') as handle:
            json.dump(data, handle, sort_keys=True)
            handle.write('\n')


def record_guard(args, environ):
    """Return an error string when --record must not run, else None."""
    if not args.record:
        return None
    if environ.get("HASS_NPP_PRIVATE_HOST") != "1":
        return "--record runs on the private host only (set HASS_NPP_PRIVATE_HOST=1 there); nothing is recorded here"
    if args.max_codex is None or args.max_images is None or args.max_codex < 0 or args.max_images < 0:
        return "--record needs --max-codex and --max-images"
    if args.max_codex > 120 or args.max_images > 30:
        return '--record caps cannot exceed 120 Codex and 30 image calls'
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
    p.add_argument('--record-to', type=Path, help='new private JSON bundle (never writes versioned fixtures)')
    p.add_argument('--recorded', type=Path, help='explicit private JSON recording to overlay in replay')
    return p.parse_args(argv)


def main(argv=None, environ=None):
    args = parse(sys.argv[1:] if argv is None else argv)
    environ = os.environ if environ is None else environ
    if (error := record_guard(args, environ)):
        print(error)
        return 2
    if args.jobs < 1 or (args.record and (not args.record_to or args.jobs != 1 or args.update_manifest)):
        print('record mode needs --record-to, one worker and no manifest update')
        return 2
    if args.update_manifest:
        print(json.dumps(write_manifest(), sort_keys=True))
        return 0
    deps = dependencies()
    missing = [name for name, ok in deps.items() if not ok and (args.strict or args.preview or args.record)]
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
        if args.record and (args.record_to.exists() or args.record_to.resolve().is_relative_to(REPO)
                            or not args.record_to.parent.is_dir()):
            raise ValueError('--record-to must be a new file outside the checkout')
        recorder = Recorder(RecordCaps(args.max_codex, args.max_images)) if args.record else None
        rows = run_all(ids, args.jobs, preview=args.preview, recorder=recorder, recorded=args.recorded)
        if recorder is not None:
            recorder.save(args.record_to)
        if args.recorded:
            fingerprint['recorded_sha256'] = sha256(args.recorded.read_bytes())
    except (ManifestMismatch, ValueError, OSError, RuntimeError) as error:
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
