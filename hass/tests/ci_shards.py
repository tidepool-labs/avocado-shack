#!/usr/bin/env python3
"""CI planner, shard runner and verifier for hass/tests (AV-CI-SHARD-1).

Tiers. "full" runs every hass/tests module, split into stable shards (one matrix job each). It is used for main
pushes, the nightly schedule, manual runs, and any PR that the affected tier cannot map safely. "affected" is for
PRs only: it runs just the modules the changed files can reach, in the quick job.

The rule, applied per changed path (renames count under both names). The first match wins:
  1. .github/**, hass/tests/** other than a test module, hass/__init__.py, hass/ops/** (registry loaded
     dynamically), hass/content/**, hass/templates/**, package-lock.json
                                                     -> FULL (workflow, test infrastructure, shared data)
  2. hass/tests/test*.py                             -> that module, plus every test module that imports it
  3. anything else is matched against the reference graph of tracked code (.py .cjs .mjs .js .sh): Python
     imports, plus every mention of a file's basename or hass.* dotted name. A test module is selected when its
     closure reaches the path, or reaches code that mentions the path's basename, its stem (4+ chars), its top
     directory, or its suffix pattern ("*.md", ".md").
     For Python scripts in scripts/hass/, imports, basename/stem references and matching
     path-qualified globs count; unrelated generic directory and suffix mentions do not.
       a hass/ path that no test reaches            -> FULL (unmapped)
       a hass/ or scripts/hass/ Python module reached by >50% of the tests -> FULL (shared library)
       an unreached path in a known non-hass area   -> nothing (docs, planning, reports, branding, commerce,
         (KNOWN_AREAS) or any *.md                     storefront-mockup and inventory-intake have their own
                                                       checks, which run on every PR)
       any other unreached path                     -> FULL (unmapped)
  4. If the selection weighs more than AFFECTED_MAX_SECONDS of measured test time -> FULL.
The smoke module (this file's own tests) and test_tracked_private (the repo-wide private-file guard) are always in the affected selection, so the runner is exercised on
every PR. Main never relies on this map: push, schedule and dispatch are always FULL.

Commands:
  plan   --event E [--base REV] [--shards N]  prints the plan, its partition and the union proof, and writes
                                              plan/tier/shards to $GITHUB_OUTPUT
  run    --shard K|quick --record-dir D       runs one shard of $HASS_PLAN and writes D/<K>.json and D/<K>.log
         --workers 2 (full only)             packs the shard's modules by measured weight into two local processes.
                                             Tests must use temporary paths and ephemeral ports; do not mutate the checkout.
  verify --record-dir D                       the aggregate: recomputes the plan, checks it against $HASS_PLAN,
                                              then checks the records (every planned module ran exactly once, test
                                              count, verdicts) and reprints failing shard logs
"""
import argparse
import ast
import collections
import fnmatch
import json
import multiprocessing
import os
import re
import subprocess
import sys
import tempfile
import time
import unittest
from concurrent.futures import ProcessPoolExecutor
from pathlib import Path
from typing import cast

TESTS = Path(__file__).resolve().parent
ROOT = TESTS.parents[1]
PREFIX = "hass.tests."
WEIGHTS = TESTS / "ci_weights.json"
DEFAULT_SHARDS = 4
MAX_SHARDS = 8
DEFAULT_WEIGHT = 3  # seconds for a module with no measurement yet
# Allow up to eight measured minutes in quick to avoid the full tier's extra runner queue.
AFFECTED_MAX_SECONDS = 480
SHARED_FRACTION = 0.5
SMOKE = "test_ci_shards"
PRIVACY_GUARD = "test_tracked_private"  # repo-wide: any newly tracked private path must fail every PR, affected or full

FULL_PREFIXES = (".github/", "hass/ops/", "hass/content/", "hass/templates/")
FULL_FILES = {"hass/__init__.py", "package-lock.json"}
KNOWN_AREAS = ("docs/", "planning/", "reports/", "branding/", "commerce/", "storefront-mockup/",
               "inventory-intake/")
KNOWN_ROOT_FILES = {"BUILD_LEDGER.md", "README.md", "README.txt", "AGENTS.md", "HERMES_HANDOFF.txt"}
CODE_SUFFIXES = (".py", ".cjs", ".mjs", ".js", ".sh")
MAX_CODE_BYTES = 2_000_000
FILE_RE = re.compile(r"[\w.-]+\.(?:py|cjs|mjs|js|sh)\b")
DOTTED_RE = re.compile(r"\bhass(?:\.\w+)+")
PATH_GLOB_RE = re.compile(r"[\w./*?\[\]-]+")


# ---------------------------------------------------------------- inventory
def all_modules(tests=TESTS):
    """Short names of every module unittest discovery loads from hass/tests: test*.py at the top level and in
    package subdirectories (a directory with __init__.py), the same walk as TestLoader.discover."""
    names = []
    for dirpath, dirnames, filenames in os.walk(tests):
        d = Path(dirpath)
        if d != tests and not (d / "__init__.py").exists():
            dirnames[:] = []
            continue
        dirnames.sort()
        rel = d.relative_to(tests).parts
        for f in sorted(filenames):
            if f.startswith("test") and f.endswith(".py"):
                names.append(".".join(rel + (f[:-3],)))
    return sorted(names)


def load_weights(path=WEIGHTS):
    """Measured seconds per module; {} on any defect (sharding still works, only balance suffers)."""
    try:
        data = json.loads(Path(path).read_text(encoding="utf-8"))
        seconds = data["seconds"]
        if not isinstance(seconds, dict) or not all(
                isinstance(k, str) and type(v) is int and v >= 1 for k, v in seconds.items()):
            raise ValueError("seconds must map module names to ints >= 1")
        return seconds
    except (OSError, ValueError, KeyError, TypeError) as error:
        print(f"::warning::shard weights unavailable ({error}); every module weighs {DEFAULT_WEIGHT}s", flush=True)
        return {}


def weight(name, weights):
    return weights.get(name, DEFAULT_WEIGHT)


def partition(names, count, weights):
    """Stable shards: heaviest first onto the lightest shard (ties: lower index), names sorted within a shard.
    The same names, count and weights always give the same shards; every name lands in exactly one shard."""
    count = max(1, min(count, len(names)))
    bins, loads = [[] for _ in range(count)], [0] * count
    for name in sorted(set(names), key=lambda n: (-weight(n, weights), n)):
        i = min(range(count), key=lambda k: (loads[k], k))
        bins[i].append(name)
        loads[i] += weight(name, weights)
    return [sorted(b) for b in bins]


def union_proof(expected, shards):
    """(ok, lines): the shard lists must cover `expected` exactly once each."""
    seen = collections.Counter(n for shard in shards for n in shard)
    union, want = set(seen), set(expected)
    missing, extra = sorted(want - union), sorted(union - want)
    dupes = sorted(n for n, c in seen.items() if c > 1)
    ok = not (missing or extra or dupes)
    lines = [f"union proof: expected {len(want)} modules; shard union {len(union)} modules from "
             f"{sum(seen.values())} assignments in {len(shards)} shard(s); missing {len(missing)}, extra {len(extra)}, "
             f"duplicated {len(dupes)} -> {'IDENTICAL' if ok else 'DIFFERENT'}"]
    for label, items in (("missing", missing), ("extra", extra), ("duplicated", dupes)):
        if items:
            lines.append(f"  {label}: {' '.join(items)}")
    return ok, lines


# ---------------------------------------------------------------- reference graph
def tracked(root=ROOT):
    out = subprocess.run(["git", "ls-files", "-z"], cwd=root, capture_output=True, check=True).stdout
    return sorted(p for p in out.decode("utf-8", "surrogateescape").split("\0") if p)


def dotted(path):
    parts = path[:-3].split("/")
    return ".".join(parts[:-1] if parts[-1] == "__init__" else parts)


def hass_script(path):
    return path.startswith("scripts/hass/") and path.endswith(".py")


def resolve(name, mods):
    """Longest dotted prefix of name that is a tracked hass module, or None."""
    parts = name.split(".")
    for i in range(len(parts), 0, -1):
        hit = mods.get(".".join(parts[:i]))
        if hit:
            return hit
    return None


def python_strings(tree):
    """Every string constant in a parsed module except docstrings, joined: the paths, module names and globs the
    code can act on. Comments and docstrings only describe; counting them linked nearly every module to every
    other through prose like "see sitegen.py"."""
    docs = set()
    for node in ast.walk(tree):
        if isinstance(node, (ast.Module, ast.ClassDef, ast.FunctionDef, ast.AsyncFunctionDef)) and node.body:
            first = node.body[0]
            if isinstance(first, ast.Expr) and isinstance(first.value, ast.Constant) \
                    and isinstance(first.value.value, str):
                docs.add(id(first.value))
    return "\n".join(n.value for n in ast.walk(tree)
                     if isinstance(n, ast.Constant) and isinstance(n.value, str) and id(n) not in docs)


def build_graph(root=ROOT, files=None):
    """(texts, edges). texts: what each tracked code file can act on (Python: its non-docstring string constants;
    a file that does not parse, and JS/shell: the whole text). edges: the code files each one references."""
    files = tracked(root) if files is None else files
    code = [p for p in files if p.endswith(CODE_SUFFIXES) and (root / p).is_file()
            and (root / p).stat().st_size <= MAX_CODE_BYTES]
    raw = {p: (root / p).read_text(encoding="utf-8", errors="replace") for p in code}
    trees, texts = {}, {}
    for p, text in raw.items():
        tree = None
        if p.endswith(".py"):
            try:
                tree = ast.parse(text, filename=p)
            except SyntaxError:
                tree = None
        trees[p] = tree
        texts[p] = python_strings(tree) if tree is not None else text
    by_base = collections.defaultdict(set)
    for p in code:
        by_base[p.rsplit("/", 1)[-1]].add(p)
    mods = {dotted(p): p for p in code if p.startswith("hass/") and p.endswith(".py")}
    script_imports = collections.defaultdict(set)
    for p in code:
        if hass_script(p):
            script_imports[dotted(p)].add(p)
            # Standalone scripts can also be imported after adding their directory to sys.path.
            script_imports[Path(p).stem].add(p)
    by_stem = collections.defaultdict(set)
    for name, p in mods.items():
        by_stem[name.rsplit(".", 1)[-1]].add(p)
    edges = {}
    for p, text in texts.items():
        refs = set()
        for base in FILE_RE.findall(text):
            refs |= by_base.get(base, set())
        for name in DOTTED_RE.findall(text):
            hit = resolve(name, mods)
            if hit:
                refs.add(hit)
        tree = trees[p]
        if tree is not None:
            for node in ast.walk(tree):
                names = []
                if isinstance(node, ast.Import):
                    names = [a.name for a in node.names]
                elif isinstance(node, ast.ImportFrom):
                    base = node.module or ""
                    if node.level:
                        pkg = dotted(p).split(".")
                        pkg = pkg if p.endswith("__init__.py") else pkg[:-1]
                        pkg = pkg[:len(pkg) - (node.level - 1)]
                        base = ".".join(pkg + ([node.module] if node.module else []))
                    names = [base] + [f"{base}.{a.name}" for a in node.names]
                for name in names:
                    hit = resolve(name, mods)
                    if hit:
                        refs.add(hit)
                    # `import conversation` after a sys.path edit: match on the last component too.
                    refs |= by_stem.get(name.rsplit(".", 1)[-1], set())
                    refs |= script_imports.get(name, set())
        refs.discard(p)
        edges[p] = refs
    return texts, edges


def closures(tests, edges):
    out = {}
    for t in tests:
        seen, todo = {t}, [t]
        while todo:
            for nxt in edges.get(todo.pop(), ()):
                if nxt not in seen:
                    seen.add(nxt)
                    todo.append(nxt)
        out[t] = seen
    return out


def tokens(path):
    base = path.rsplit("/", 1)[-1]
    stem, dot, suffix = base.rpartition(".")
    stem = stem if dot else base
    out = {base}
    if len(stem) >= 4:
        out.add(stem)
    if hass_script(path):
        return out | {stem}
    top = path.split("/", 1)[0]
    if "/" in path and top != "hass":
        out.add(top)
    if dot and suffix:
        out |= {f"*.{suffix}", f'".{suffix}"', f"'.{suffix}'"}
    return out


def test_path(name):
    return "hass/tests/" + name.replace(".", "/") + ".py"


def select(paths, modules, texts, edges, notes=None):
    """(selected short names, None) or (None, reason for FULL). See the module docstring for the rule."""
    files = {test_path(m): m for m in modules}
    reach = closures(list(files), edges)
    reached_by = collections.defaultdict(set)
    for t, seen in reach.items():
        for f in seen:
            reached_by[f].add(files[t])
    selected = set()
    for path in paths:
        if path.startswith(FULL_PREFIXES) or path in FULL_FILES:
            return None, f"{path}: workflow, test infrastructure or shared data"
        if path.startswith("hass/tests/") and path not in files:
            return None, f"{path}: test infrastructure (not a current test module)"
        hit = set(reached_by.get(path, ()))
        toks = tokens(path)
        is_script = hass_script(path)
        if is_script:
            # A longer name such as other_X is not a reference to X. Generic tokens like
            # "scripts" would otherwise fan out through ordinary shared QA helpers.
            ref = re.compile(r"(?<!\w)(?:" + "|".join(map(re.escape, sorted(toks))) + r")(?!\w)")
            mentions = {f for f, text in texts.items() if ref.search(text) or any(
                "/" in pattern and any(c in pattern for c in "*?[") and fnmatch.fnmatchcase(path, pattern)
                for pattern in PATH_GLOB_RE.findall(text))}
        else:
            mentions = {f for f, text in texts.items() if any(t in text for t in toks)}
        for f in mentions:
            hit |= reached_by.get(f, set())
        if path in files:
            hit.add(files[path])
        in_hass = path.startswith("hass/")
        if (in_hass or is_script) and path.endswith(".py") and len(hit) > SHARED_FRACTION * len(modules):
            return None, f"{path}: shared library, reached by {len(hit)} of {len(modules)} test modules"
        if not hit:
            if in_hass:
                return None, f"{path}: unmapped (no test module reaches it)"
            if not (path.startswith(KNOWN_AREAS) or path in KNOWN_ROOT_FILES or path.endswith(".md")):
                return None, f"{path}: unmapped path"
        if notes is not None:
            notes.append(f"  {path} -> {len(hit)} module(s)" + (
                f": {' '.join(sorted(hit)[:12])}" + (" ..." if len(hit) > 12 else "") if hit else ""))
        selected |= hit
    return selected, None


def changed_paths(base, root=ROOT):
    out = subprocess.run(["git", "diff", "--name-only", "--no-renames", "-z", base, "HEAD"], cwd=root,
                         capture_output=True, check=True).stdout
    return sorted(p for p in out.decode("utf-8", "surrogateescape").split("\0") if p)


def count_tests(names):
    sys.path.insert(0, str(ROOT))
    return unittest.defaultTestLoader.loadTestsFromNames([PREFIX + n for n in names]).countTestCases()


def make_plan(event, base, shards, weights, modules=None):
    """The plan dict; prints the reasoning. Deterministic for the same tree, event, base and shard count."""
    modules = all_modules() if modules is None else modules
    if not modules:
        raise SystemExit("no hass/tests test*.py modules found; refusing an empty plan")
    shards = max(1, min(int(shards), MAX_SHARDS))
    tier, reason, selected = "full", f"event {event} always runs the full suite", None
    if event == "pull_request":
        try:
            paths = changed_paths(base)
            print(f"changed paths ({len(paths)}) against {base}:", flush=True)
            for p in paths:
                print(f"  {p}", flush=True)
            texts, edges = build_graph()
            notes = []
            selected, why = select(paths, modules, texts, edges, notes)
            for line in notes:
                print(line, flush=True)
            if selected is None:
                reason = why
            else:
                selected.add(SMOKE)
                selected.update({PRIVACY_GUARD} & set(modules))
                cost = sum(weight(n, weights) for n in selected)
                if cost > AFFECTED_MAX_SECONDS:
                    selected, reason = None, (f"affected selection ({cost}s measured) is over "
                                              f"{AFFECTED_MAX_SECONDS}s affected-tier budget")
                else:
                    tier, reason = "affected", f"{len(selected)} affected module(s), {cost}s measured"
        except (OSError, ValueError, subprocess.CalledProcessError) as error:
            reason = f"affected mapping unavailable ({error})"
    if tier == "full":
        groups = partition(modules, shards, weights)
        expected_set = modules
    else:
        groups = [sorted(selected)]
        expected_set = sorted(selected)
    return {"tier": tier, "reason": reason, "event": event, "shards": groups,
            "modules": len(expected_set)}


def show_plan(plan, weights, modules):
    print(f"tier: {plan['tier']} ({plan['reason']})", flush=True)
    for i, g in enumerate(plan["shards"]):
        key = "quick" if plan["tier"] == "affected" else str(i)
        print(f"shard {key}: {len(g)} modules, {sum(weight(n, weights) for n in g)}s measured: {' '.join(g)}",
              flush=True)
    expected = modules if plan["tier"] == "full" else sorted(set().union(*map(set, plan["shards"])))
    if plan["tier"] == "full":
        print(f"full list: {len(modules)} modules from hass/tests (the unittest discovery walk)", flush=True)
    ok, lines = union_proof(expected, plan["shards"])
    for line in lines:
        print(line, flush=True)
    return ok


def cmd_plan(a):
    weights = load_weights()
    modules = all_modules()
    plan = make_plan(a.event, a.base, a.shards, weights, modules)
    expected = modules if plan["tier"] == "full" else plan["shards"][0]
    plan["tests"] = count_tests(expected)
    if plan["tier"] == "full":
        found = unittest.defaultTestLoader.discover(str(TESTS), top_level_dir=str(ROOT)).countTestCases()
        print(f"tests: {plan['tests']} in the listed modules; unittest discovery finds {found}", flush=True)
        if found != plan["tests"]:
            print("::error::the module list and unittest discovery disagree", flush=True)
            return 1
    else:
        print(f"tests: {plan['tests']} in the selected modules", flush=True)
    if not show_plan(plan, weights, modules):
        print("::error::shard union differs from the expected module list", flush=True)
        return 1
    text = json.dumps(plan, separators=(",", ":"), sort_keys=True)
    out = os.environ.get("GITHUB_OUTPUT")
    if out:
        keys = ["quick"] if plan["tier"] == "affected" else [str(i) for i in range(len(plan["shards"]))]
        with open(out, "a", encoding="utf-8") as fh:
            fh.write(f"plan={text}\ntier={plan['tier']}\nshards={json.dumps(keys)}\n")
    return 0


# ---------------------------------------------------------------- run
class Tee:
    def __init__(self, *streams):
        self.streams = streams

    def write(self, s):
        for st in self.streams:
            st.write(s)
            st.flush()
        return len(s)

    def flush(self):
        for st in self.streams:
            st.flush()


class TimedResult(unittest.TextTestResult):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.seconds, self._t = {}, time.perf_counter()

    def startTest(self, test):
        self._t = time.perf_counter()
        super().startTest(test)

    def stopTest(self, test):
        super().stopTest(test)
        mod = type(test).__module__
        self.seconds[mod] = self.seconds.get(mod, 0.0) + time.perf_counter() - self._t


def read_plan():
    raw = os.environ.get("HASS_PLAN", "")
    plan = json.loads(raw)
    if not isinstance(plan, dict) or plan.get("tier") not in ("full", "affected") \
            or not isinstance(plan.get("shards"), list):
        raise ValueError("HASS_PLAN is not a plan")
    return plan


def shard_keys(plan):
    return ["quick"] if plan["tier"] == "affected" else [str(i) for i in range(len(plan["shards"]))]


def run_modules(names, stream):
    sys.path.insert(0, str(ROOT))
    suite = unittest.defaultTestLoader.loadTestsFromNames([PREFIX + n for n in names])
    runner = unittest.TextTestRunner(stream=stream, verbosity=2, resultclass=TimedResult)
    result = cast(TimedResult, runner.run(suite))
    return {"modules": names, "tests_run": result.testsRun, "failures": len(result.failures),
            "errors": len(result.errors), "skipped": len(result.skipped),
            "unexpected_successes": len(result.unexpectedSuccesses),
            "ok": result.wasSuccessful() and result.testsRun > 0,
            "module_seconds": {k[len(PREFIX):] if k.startswith(PREFIX) else k: round(v, 1)
                               for k, v in sorted(result.seconds.items())}}


def run_worker(names, log_path):
    # Keep both Python's tempfile cache and child commands inside this worker's own TMPDIR.
    prior, cached = os.environ.get("TMPDIR"), tempfile.tempdir
    with tempfile.TemporaryDirectory(prefix="w") as tmp:
        os.environ["TMPDIR"] = tempfile.tempdir = tmp
        try:
            with log_path.open("w", encoding="utf-8") as log:
                return run_modules(names, log)
        finally:
            tempfile.tempdir = cached
            if prior is None:
                os.environ.pop("TMPDIR", None)
            else:
                os.environ["TMPDIR"] = prior


def run_parallel(names, stream, rec, workers):
    groups = partition(names, workers, load_weights())
    # Merge only after every subprocess returns; a crash cannot yield a successful shard record.
    with tempfile.TemporaryDirectory(prefix="workers-", dir=rec) as tmp:
        logs = [Path(tmp) / f"{i}.log" for i in range(len(groups))]
        with ProcessPoolExecutor(max_workers=len(groups), mp_context=multiprocessing.get_context("spawn")) as pool:
            results = list(pool.map(run_worker, groups, logs))
        for path in logs:
            with path.open(encoding="utf-8") as log:
                for part in iter(lambda: log.read(64 * 1024), ""):
                    stream.write(part)
    ran = [r["modules"] for r in results]
    if ran != groups or not union_proof(names, ran)[0]:
        raise ValueError("worker modules differ from the shard plan")
    timing = collections.Counter()
    for result in results:
        timing.update(result["module_seconds"])
    return {"modules": names, "ok": all(r["ok"] for r in results), "module_seconds": dict(timing),
            **{key: sum(r[key] for r in results)
               for key in ("tests_run", "failures", "errors", "skipped", "unexpected_successes")}}


def cmd_run(a):
    plan = read_plan()
    keys = shard_keys(plan)
    if a.shard not in keys:
        print(f"::error::shard {a.shard} is not in this plan ({keys})", flush=True)
        return 1
    names = plan["shards"][keys.index(a.shard)]
    known = set(all_modules())
    unknown = sorted(set(names) - known)
    if unknown or not names or len(names) != len(set(names)):
        print(f"::error::shard {a.shard}: empty, duplicate, or unknown modules {unknown}", flush=True)
        return 1
    rec = Path(a.record_dir)
    rec.mkdir(parents=True, exist_ok=True)
    print(f"hass shard {a.shard} ({plan['tier']}): {len(names)} modules: {' '.join(names)}", flush=True)
    t0 = time.perf_counter()
    with open(rec / f"{a.shard}.log", "w", encoding="utf-8") as log:
        stream = Tee(sys.stdout, log)
        if a.workers > 1 and plan["tier"] == "full" and len(names) > 1:
            record = run_parallel(names, stream, rec, a.workers)
        else:
            record = run_modules(names, stream)
    record.update(shard=a.shard, tier=plan["tier"], seconds=round(time.perf_counter() - t0, 1))
    (rec / f"{a.shard}.json").write_text(json.dumps(record, indent=1, sort_keys=True), encoding="utf-8")
    print(f"hass shard {a.shard}: ran {record['tests_run']} tests in {record['seconds']}s, "
          f"{'OK' if record['ok'] else 'FAILED'}", flush=True)
    return 0 if record["ok"] else 1


# ---------------------------------------------------------------- verify (aggregate job 'check')
def verify(plan, recomputed, needs, records, logs, modules):
    """(problems, lines). records: {key: record dict}; logs: {key: text}; needs: the workflow `needs` context."""
    problems, lines = [], []
    tier = plan.get("tier")
    for job, want in (("quick", ("success",)), ("site", ("success",)),
                      ("hass", ("success",) if tier == "full" else ("skipped",))):
        got = (needs.get(job) or {}).get("result")
        lines.append(f"job {job}: {got}")
        if got not in want:
            problems.append(f"job {job} result {got}, expected {' or '.join(want)}")
    if recomputed is not None:
        same = {k: plan.get(k) for k in ("tier", "shards")} == {k: recomputed.get(k) for k in ("tier", "shards")}
        lines.append(f"plan recomputed in this job: {'same' if same else 'DIFFERENT'} "
                     f"(tier {recomputed.get('tier')}, {len(recomputed.get('shards', []))} shard(s))")
        if not same:
            problems.append("the plan recomputed here differs from the quick job's plan")
    planned = plan.get("shards") or []
    expected = modules if tier == "full" else sorted({n for g in planned for n in g})
    ok, proof = union_proof(expected, planned)
    lines += ["planned " + p for p in proof]
    if not ok:
        problems.append("planned shard union differs from the expected module list")
    keys = shard_keys(plan) if tier in ("full", "affected") else []
    ran = []
    for key, group in zip(keys, planned):
        r = records.get(key)
        if r is None:
            problems.append(f"shard {key}: no record (did it run?)")
            continue
        if r.get("modules") != group:
            problems.append(f"shard {key}: ran a different module list than planned")
        ran.append(r.get("modules") or [])
        lines.append(f"shard {key}: {len(r.get('modules') or [])} modules, {r.get('tests_run')} tests, "
                     f"failures {r.get('failures')}, errors {r.get('errors')}, skipped {r.get('skipped')}, "
                     f"{r.get('seconds')}s, {'ok' if r.get('ok') else 'FAILED'}")
        if not r.get("ok"):
            problems.append(f"shard {key}: failed")
    extra = sorted(set(records) - set(keys))
    if extra:
        problems.append(f"records from shards not in the plan: {extra}")
    ok, proof = union_proof(expected, ran)
    lines += ["executed " + p for p in proof]
    if not ok:
        problems.append("executed shard union differs from the expected module list")
    total = sum(int(r.get("tests_run") or 0) for k, r in records.items() if k in keys)
    lines.append(f"tests: {total} ran, {plan.get('tests')} planned")
    if total != plan.get("tests"):
        problems.append(f"ran {total} tests, planned {plan.get('tests')}")
    return problems, lines


def cmd_verify(a):
    problems, lines = [], []
    try:
        plan = read_plan()
    except (ValueError, json.JSONDecodeError) as error:
        print(f"::error::no usable plan from the quick job ({error})", flush=True)
        return 1
    needs = json.loads(os.environ.get("HASS_NEEDS") or "{}")
    weights = load_weights()
    modules = all_modules()
    recomputed = None
    try:
        recomputed = make_plan(plan.get("event", ""), a.base, a.shards, weights, modules)
    except (SystemExit, Exception) as error:  # noqa: BLE001 - any failure here is reported, never hidden
        problems.append(f"could not recompute the plan ({error})")
    records, logs = {}, {}
    rec = Path(a.record_dir)
    for p in sorted(rec.glob("*.json")) if rec.is_dir() else []:
        try:
            records[p.stem] = json.loads(p.read_text(encoding="utf-8"))
        except (OSError, ValueError) as error:
            problems.append(f"record {p.name} unreadable ({error})")
        log = p.with_suffix(".log")
        logs[p.stem] = log.read_text(encoding="utf-8", errors="replace") if log.exists() else ""
    more, lines = verify(plan, recomputed, needs, records, logs, modules)
    problems += more
    print(f"tier: {plan.get('tier')} ({plan.get('reason')})", flush=True)
    for line in lines:
        print(line, flush=True)
    # Reprint failing shard output in this job's log as well, so a failing `check` names its failing test ids
    # (bin/mergegate.py reads FAIL:/ERROR: headers from the log of every failed check).
    for key, r in sorted(records.items()):
        if not r.get("ok"):
            print(f"\n===== failing shard {key}: unittest output =====", flush=True)
            print(logs.get(key, "(no log)"), flush=True)
    for p in problems:
        print(f"::error::{p}", flush=True)
    print("check: " + ("OK" if not problems else f"FAILED ({len(problems)} problem(s))"), flush=True)
    return 1 if problems else 0


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = ap.add_subparsers(dest="cmd", required=True)
    p = sub.add_parser("plan")
    p.add_argument("--event", required=True)
    p.add_argument("--base", default="HEAD^1")
    p.add_argument("--shards", type=int, default=DEFAULT_SHARDS)
    r = sub.add_parser("run")
    r.add_argument("--shard", required=True)
    r.add_argument("--record-dir", required=True)
    r.add_argument("--workers", type=int, choices=(1, 2), default=1)
    v = sub.add_parser("verify")
    v.add_argument("--record-dir", required=True)
    v.add_argument("--base", default="HEAD^1")
    v.add_argument("--shards", type=int, default=DEFAULT_SHARDS)
    a = ap.parse_args(argv)
    return {"plan": cmd_plan, "run": cmd_run, "verify": cmd_verify}[a.cmd](a)


if __name__ == "__main__":
    sys.exit(main())
