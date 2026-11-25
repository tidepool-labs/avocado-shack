"""AV-CI-SHARD-1: the hass/tests CI planner (hass/tests/ci_shards.py): stable shards, the union proof, the
changed-files -> test-modules map with its FULL fallbacks, and the aggregate verdict."""
import contextlib
import io
import json
import os
import shutil
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path
from unittest import mock

from hass.tests import ci_shards as cs


def graph(files):
    """build_graph over an in-memory tree written to a temp dir."""
    tmp = tempfile.TemporaryDirectory()
    root = Path(tmp.name)
    for rel, text in files.items():
        p = root / rel
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text(text)
    texts, edges = cs.build_graph(root, sorted(files))
    tmp.cleanup()
    return texts, edges


TREE = {
    "hass/__init__.py": '"""pkg"""\n',
    "hass/leaf.py": "VALUE = 1\n",
    "hass/mid.py": "from hass import leaf\n",
    "hass/hub.py": "from . import mid\n",
    "hass/runner.py": "import subprocess\nsubprocess.run(['node', 'hass/screen.cjs'])\n",
    "hass/screen.cjs": "const env = require('./qa-env.cjs');\n",
    "hass/qa-env.cjs": "module.exports = {};\n",
    "hass/lonely.py": "X = 2\n",
    "hass/prose.py": '"""Mentions lonely.py in a docstring only."""\n# and lonely.py in a comment\n',
    "hass/tests/__init__.py": "",
    "hass/tests/test_leaf.py": "from hass.leaf import VALUE\n",
    "hass/tests/test_hub.py": "from hass import hub\n",
    "hass/tests/test_shot.py": "from hass import runner\n",
    "hass/tests/test_doc.py": "DOC = 'docs/hass/GUIDE.md'\n",
    "hass/tests/test_prose.py": "from hass import prose\n",
    "hass/tests/test_reuse.py": "from hass.tests.test_leaf import VALUE\n",
}
MODULES = sorted(Path(p).stem for p in TREE if p.startswith("hass/tests/test_"))


class PartitionTest(unittest.TestCase):
    def test_every_module_once_and_stable(self):
        names = [f"test_{i:03d}" for i in range(40)]
        weights = {n: (i * 7) % 13 + 1 for i, n in enumerate(names)}
        shards = cs.partition(names, 4, weights)
        self.assertEqual(len(shards), 4)
        ok, lines = cs.union_proof(names, shards)
        self.assertTrue(ok, lines)
        self.assertEqual(shards, cs.partition(list(reversed(names)), 4, weights))  # input order never matters
        loads = [sum(weights[n] for n in s) for s in shards]
        self.assertLessEqual(max(loads) - min(loads), max(weights.values()))

    def test_more_shards_than_modules(self):
        self.assertEqual(cs.partition(["test_a", "test_b"], 4, {}), [["test_a"], ["test_b"]])

    def test_union_proof_names_each_difference(self):
        ok, lines = cs.union_proof(["a", "b", "c"], [["a", "b"], ["b", "d"]])
        self.assertFalse(ok)
        text = "\n".join(lines)
        self.assertIn("DIFFERENT", text)
        self.assertIn("missing: c", text)
        self.assertIn("extra: d", text)
        self.assertIn("duplicated: b", text)


class ParallelRunTest(unittest.TestCase):
    def test_all_workers_must_run_and_a_failed_worker_fails_the_shard(self):
        # A dropped lane, shared temporary root, or ignored unittest failure must not pass.
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            tests = root / "hass" / "tests"
            tests.mkdir(parents=True)
            (tests / "__init__.py").touch()
            (tests.parent / "__init__.py").touch()
            runner = tests / "ci_shards.py"
            shutil.copyfile(cs.__file__, runner)
            names = ["test_a", "test_b"]
            for name in names:
                (tests / f"{name}.py").write_text(
                    "import os, tempfile, unittest\n"
                    "from pathlib import Path\n"
                    "class Work(unittest.TestCase):\n"
                    "    def test_one(self):\n"
                    "        root = Path(os.environ['CI20_TEST_ROOT'])\n"
                    "        (root / __name__).write_text(tempfile.gettempdir())\n"
                    "        self.assertFalse((root / 'fail').exists() and __name__.endswith('test_b'))\n",
                    encoding="utf-8",
                )
            for should_fail in (False, True):
                with self.subTest(should_fail=should_fail):
                    if should_fail:
                        (root / "fail").touch()
                    rec = root / f"record-{should_fail}"
                    run = subprocess.run([sys.executable, "-B", str(runner), "run", "--shard", "0",
                                          "--workers", "2", "--record-dir", str(rec)],
                                         cwd=root, capture_output=True, text=True, timeout=20,
                                         env={**os.environ, "CI20_TEST_ROOT": tmp,
                                              "HASS_PLAN": json.dumps({"tier": "full", "shards": [names]})})
                    self.assertEqual(run.returncode, int(should_fail), run.stdout + run.stderr)
                    result = json.loads((rec / "0.json").read_text())
                    self.assertEqual((result["modules"], result["tests_run"]), (names, 2))
                    self.assertEqual((result["ok"], result["failures"]), (not should_fail, int(should_fail)))
                    self.assertNotEqual(*(root.joinpath(f"hass.tests.{name}").read_text() for name in names))
                    if should_fail:
                        self.assertIn("=" * 70 + "\nFAIL: test_one (hass.tests.test_b", (rec / "0.log").read_text())


class InventoryTest(unittest.TestCase):
    def test_walk_matches_discovery_rules(self):
        with tempfile.TemporaryDirectory() as tmp:
            t = Path(tmp)
            for rel in ("test_a.py", "tests_b.py", "helper.py", "pkg/__init__.py", "pkg/test_c.py",
                        "fixtures/test_not_a_package.py"):
                (t / rel).parent.mkdir(parents=True, exist_ok=True)
                (t / rel).write_text("")
            self.assertEqual(cs.all_modules(t), ["pkg.test_c", "test_a", "tests_b"])

    def test_real_tree_full_plan_covers_every_module(self):
        modules = cs.all_modules()
        self.assertIn("test_ci_shards", modules)
        plan = cs.make_plan("push", "HEAD^1", cs.DEFAULT_SHARDS, cs.load_weights(), modules)
        self.assertEqual(plan["tier"], "full")
        self.assertEqual(len(plan["shards"]), cs.DEFAULT_SHARDS)
        ok, lines = cs.union_proof(modules, plan["shards"])
        self.assertTrue(ok, lines)


class GraphTest(unittest.TestCase):
    def setUp(self):
        self.texts, self.edges = graph(TREE)

    def test_imports_relative_imports_and_mentions(self):
        self.assertIn("hass/leaf.py", self.edges["hass/mid.py"])
        self.assertIn("hass/mid.py", self.edges["hass/hub.py"])  # from . import mid
        self.assertIn("hass/screen.cjs", self.edges["hass/runner.py"])  # a path in a string constant
        self.assertIn("hass/qa-env.cjs", self.edges["hass/screen.cjs"])  # require() in JS
        self.assertIn("hass/tests/test_leaf.py", self.edges["hass/tests/test_reuse.py"])

    def test_docstrings_and_comments_are_not_references(self):
        self.assertNotIn("hass/lonely.py", self.edges["hass/prose.py"])

    def sel(self, *paths):
        return cs.select(list(paths), MODULES, self.texts, self.edges)

    def test_changed_module_selects_tests_that_reach_it(self):
        self.assertEqual(self.sel("hass/leaf.py"), ({"test_leaf", "test_hub", "test_reuse"}, None))
        self.assertEqual(self.sel("hass/qa-env.cjs"), ({"test_shot"}, None))  # test -> runner -> screen -> qa-env

    def test_changed_test_module_selects_itself_and_its_importers(self):
        self.assertEqual(self.sel("hass/tests/test_leaf.py"), ({"test_leaf", "test_reuse"}, None))

    def test_docs_are_mapped_by_mention(self):
        self.assertEqual(self.sel("docs/hass/GUIDE.md"), ({"test_doc"}, None))
        self.assertEqual(self.sel("docs/hass/OTHER.md"), ({"test_doc"}, None))  # its directory is named
        self.assertEqual(self.sel("planning/notes.md"), (set(), None))  # known area, no test reads it
        self.assertEqual(self.sel("BUILD_LEDGER.md"), (set(), None))

    def test_full_suite_fallbacks(self):
        for path in (".github/workflows/check.yml", "hass/tests/run_parallel.py", "hass/tests/fixtures/x.json",
                     "hass/tests/ci_weights.json", "hass/__init__.py", "hass/ops/catalog.py", "hass/content/a.json",
                     "hass/templates/page.html", "package-lock.json",
                     "hass/lonely.py",  # a hass module no test reaches
                     "hass/new_file.txt",  # an unmapped hass path
                     "toplevel.cfg", "newarea/thing.py", "scripts/hass/unreferenced.py"):
            with self.subTest(path=path):
                selected, why = self.sel("hass/leaf.py", path)
                self.assertIsNone(selected)
                self.assertTrue(why.startswith(path), why)

    def test_shared_library_runs_everything(self):
        files = dict(TREE)
        for i in range(10):
            files[f"hass/tests/test_more{i}.py"] = "from hass import hub\n"
        texts, edges = graph(files)
        modules = sorted(Path(p).stem for p in files if p.startswith("hass/tests/test_"))
        selected, why = cs.select(["hass/mid.py"], modules, texts, edges)
        self.assertIsNone(selected)
        self.assertIn("shared library", why)


class ScriptPlanTest(unittest.TestCase):
    PATH = "scripts/hass/install_probe.py"
    TEST = "test_install_probe"
    MODULES = [cs.SMOKE, cs.PRIVACY_GUARD, TEST, "test_other", "test_qa"]

    def plan(self, consumer, additional_consumers=False):
        # The shared helper deliberately mentions the directory, a glob in a *different*
        # directory, and a longer filename: none is a dependency on install_probe.py.
        files = {self.PATH: "VALUE = 1\n", "hass/qa_helpers.py":
                 "SCRIPTS = 'scripts'\nPATTERN = 'hass/ops/*.py'\nNAME = 'other_install_probe.py'\n"}
        for module in self.MODULES:
            files[cs.test_path(module)] = "from hass import qa_helpers\n"
        files[cs.test_path(self.TEST)] += consumer
        if additional_consumers:
            files[cs.test_path("test_other")] += "import scripts.hass.install_probe\n"
            files[cs.test_path("test_qa")] += "from install_probe import VALUE\n"
        texts, edges = graph(files)
        with mock.patch.object(cs, "changed_paths", return_value=[self.PATH]), \
                mock.patch.object(cs, "build_graph", return_value=(texts, edges)), \
                contextlib.redirect_stdout(io.StringIO()):
            return cs.make_plan("pull_request", "base", 4, {}, self.MODULES)

    def test_script_selects_its_consumer_not_users_of_shared_qa_helpers(self):
        # Catches both broad token fan-out and dropping an import-only or literal-only consumer.
        for consumer in ("from scripts.hass import install_probe\n", "import install_probe\n",
                         "PATH = 'scripts/hass/install_probe.py'\n", "NAME = 'install_probe'\n"):
            with self.subTest(consumer=consumer):
                plan = self.plan(consumer)
                self.assertEqual(plan["tier"], "affected", plan["reason"])
                self.assertEqual(plan["shards"], [sorted([cs.SMOKE, cs.PRIVACY_GUARD, self.TEST])])

    def test_script_selects_matching_directory_glob_not_unrelated_glob(self):
        files = {
            self.PATH: "VALUE = 1\n",
            cs.test_path(self.TEST): "import scripts.hass.install_probe\n",
            cs.test_path("test_other"): "PATTERN = 'scripts/hass/*.py'\n",
            cs.test_path("test_qa"): "PATTERN = 'hass/ops/*.py'\n",
        }
        texts, edges = graph(files)
        selected, reason = cs.select([self.PATH], self.MODULES, texts, edges)
        self.assertIsNone(reason)
        self.assertEqual(selected, {self.TEST, "test_other"})

    def test_script_used_by_majority_is_full_even_below_budget(self):
        # Catches treating widely imported scripts like local scripts just because they are cheap.
        plan = self.plan("from scripts.hass import install_probe\n", additional_consumers=True)
        self.assertEqual(plan["tier"], "full")
        self.assertIn("shared library, reached by 3 of 5", plan["reason"])
        self.assertTrue(cs.union_proof(self.MODULES, plan["shards"])[0])


def record(key, modules, tests, ok=True):
    return {"shard": key, "modules": modules, "tests_run": tests, "ok": ok, "failures": 0 if ok else 1,
            "errors": 0, "skipped": 0, "seconds": 1.0}


class WeightReaderTest(unittest.TestCase):
    """load_weights over real temporary JSON files: a defect means {} plus ONE fixed warning, never an exception."""
    WARNING = (f"::warning::shard weights unavailable (seconds must map module names to ints >= 1); "
               f"every module weighs {cs.DEFAULT_WEIGHT}s\n")

    def setUp(self):
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        self.dir = Path(tmp.name)

    def read(self, raw, name="weights.json"):
        """(result, stdout) of cs.load_weights on a file holding `raw` (text); raw None = absent file."""
        path = self.dir / name
        if raw is not None:
            path.write_text(raw, encoding="utf-8")
        out = io.StringIO()
        with contextlib.redirect_stdout(out):
            result = cs.load_weights(path)
        return result, out.getvalue()

    def test_non_mapping_seconds_warns_and_falls_back(self):
        for seconds in ("[]", "[1, 2]", "null", "3", '"slow"', "true", "false"):
            with self.subTest(seconds=seconds):
                raw = '{"seconds": %s}' % seconds
                path = self.dir / "weights.json"
                path.write_text(raw, encoding="utf-8")
                before = (path.read_bytes(), path.stat().st_mode)
                result, out = self.read(raw)
                self.assertEqual(result, {})
                self.assertEqual(out, self.WARNING)
                self.assertEqual((path.read_bytes(), path.stat().st_mode), before)

    def test_valid_weight_maps_are_unchanged(self):
        high, low = cs.DEFAULT_WEIGHT + 40, 1
        for data in ({}, {"test_a": high}, {"test_z": low, "test_a": high, "test_m": cs.DEFAULT_WEIGHT},
                     {"test_a": high, "test_z": low, "test_m": cs.DEFAULT_WEIGHT}):
            with self.subTest(data=data):
                result, out = self.read(json.dumps({"seconds": data}))
                self.assertEqual(result, data)
                self.assertEqual(out, "")

    def test_existing_invalid_weights_keep_fallback(self):
        cases = {"absent": None, "malformed": "{not json", "root-null": "null", "root-list": "[]",
                 "missing-seconds": "{}", "zero": '{"seconds": {"test_a": 0}}',
                 "negative": '{"seconds": {"test_a": -2}}', "bool": '{"seconds": {"test_a": true}}',
                 "string": '{"seconds": {"test_a": "9"}}'}
        for label, raw in cases.items():
            with self.subTest(case=label):
                result, out = self.read(raw, name=f"{label}.json")
                self.assertEqual(result, {})
                self.assertEqual(out.count("::warning::shard weights unavailable"), 1)
                self.assertEqual(out.count("\n"), 1)

    def test_default_weight_fallback_plan_covers_every_module_once(self):
        modules = ["test_d", "test_b", "test_a", "test_c", "test_e"]
        weights, _ = self.read('{"seconds": []}')
        self.assertEqual(weights, {})
        plan = cs.make_plan("push", "base", 2, weights, modules)
        self.assertEqual(plan["tier"], "full")
        self.assertEqual(plan["modules"], len(modules))
        ok, lines = cs.union_proof(sorted(modules), plan["shards"])
        self.assertTrue(ok, lines)
        self.assertIn("IDENTICAL", lines[0])
        # equal default weights: heaviest-first ties break by name onto the lightest shard (lower index first)
        self.assertEqual(plan["shards"], [["test_a", "test_c", "test_e"], ["test_b", "test_d"]])
        again = cs.make_plan("push", "base", 2, weights, list(reversed(modules)))
        self.assertEqual(again["shards"], plan["shards"])


class VerifyTest(unittest.TestCase):
    MODS = ["test_a", "test_b", "test_c"]
    FULL = {"tier": "full", "reason": "push", "event": "push", "shards": [["test_a", "test_c"], ["test_b"]],
            "tests": 5}
    NEEDS = {"quick": {"result": "success"}, "site": {"result": "success"}, "hass": {"result": "success"}}

    def run_verify(self, plan=None, needs=None, records=None, recomputed=None):
        plan = plan or self.FULL
        records = records if records is not None else {"0": record("0", ["test_a", "test_c"], 3),
                                                       "1": record("1", ["test_b"], 2)}
        recomputed = plan if recomputed is None else recomputed
        problems, _ = cs.verify(plan, recomputed, needs or self.NEEDS, records, {}, self.MODS)
        return problems

    def test_all_shards_ran_everything_once(self):
        self.assertEqual(self.run_verify(), [])

    def test_missing_record_fails(self):
        problems = self.run_verify(records={"0": record("0", ["test_a", "test_c"], 3)})
        self.assertTrue(any("shard 1: no record" in p for p in problems), problems)
        self.assertTrue(any("executed shard union differs" in p for p in problems), problems)

    def test_failed_shard_fails(self):
        problems = self.run_verify(records={"0": record("0", ["test_a", "test_c"], 3),
                                            "1": record("1", ["test_b"], 2, ok=False)})
        self.assertIn("shard 1: failed", problems)

    def test_plan_that_drops_a_module_fails(self):
        plan = dict(self.FULL, shards=[["test_a"], ["test_b"]], tests=4)
        problems = self.run_verify(plan=plan, records={"0": record("0", ["test_a"], 2),
                                                       "1": record("1", ["test_b"], 2)})
        self.assertIn("planned shard union differs from the expected module list", problems)

    def test_test_count_and_job_results_are_checked(self):
        problems = self.run_verify(records={"0": record("0", ["test_a", "test_c"], 2),
                                            "1": record("1", ["test_b"], 2)})
        self.assertIn("ran 4 tests, planned 5", problems)
        problems = self.run_verify(needs=dict(self.NEEDS, hass={"result": "skipped"}))
        self.assertIn("job hass result skipped, expected success", problems)
        problems = self.run_verify(needs=dict(self.NEEDS, site={"result": "failure"}))
        self.assertIn("job site result failure, expected success", problems)

    def test_recomputed_plan_must_match(self):
        other = dict(self.FULL, tier="affected", shards=[["test_a"]])
        problems = self.run_verify(recomputed=other)
        self.assertIn("the plan recomputed here differs from the quick job's plan", problems)

    def test_affected_tier_runs_in_quick_and_skips_shards(self):
        plan = {"tier": "affected", "reason": "x", "event": "pull_request", "shards": [["test_b"]], "tests": 2}
        needs = dict(self.NEEDS, hass={"result": "skipped"})
        self.assertEqual(self.run_verify(plan=plan, needs=needs, records={"quick": record("quick", ["test_b"], 2)}),
                         [])
        problems = self.run_verify(plan=plan, needs=self.NEEDS, records={"quick": record("quick", ["test_b"], 2)})
        self.assertIn("job hass result success, expected skipped", problems)

    def test_affected_plan_always_runs_the_private_file_guard(self):
        modules = sorted(set(MODULES) | {cs.SMOKE, cs.PRIVACY_GUARD})
        texts, edges = graph(TREE)
        with mock.patch.object(cs, "changed_paths", return_value=["branding/customer-export.db"]), \
                mock.patch.object(cs, "build_graph", return_value=(texts, edges)):
            plan = cs.make_plan("pull_request", "base", 4, {}, modules)
        self.assertEqual(plan["tier"], "affected")
        self.assertIn(cs.PRIVACY_GUARD, plan["shards"][0])

    def test_affected_cost_budget_boundary(self):
        modules = [cs.SMOKE, cs.PRIVACY_GUARD, "test_leaf", "test_other"]
        for cost, tier in ((240, "affected"), (241, "affected"),
                           (480, "affected"), (481, "full")):
            with self.subTest(cost=cost), \
                    mock.patch.object(cs, "changed_paths", return_value=["hass/leaf.py"]), \
                    mock.patch.object(cs, "build_graph", return_value=({}, {
                        cs.test_path("test_leaf"): {"hass/leaf.py"}})):
                weights = {cs.SMOKE: 1, cs.PRIVACY_GUARD: 1, "test_leaf": cost - 2}
                plan = cs.make_plan("pull_request", "base", 4, weights, modules)
                self.assertEqual(plan["tier"], tier)
                expected = modules if tier == "full" else modules[:3]
                self.assertTrue(cs.union_proof(expected, plan["shards"])[0])

    def test_non_pr_events_ignore_affected_budget(self):
        modules = [cs.SMOKE, cs.PRIVACY_GUARD, "test_leaf"]
        for event in ("push", "schedule", "workflow_dispatch"):
            with self.subTest(event=event), mock.patch.object(cs, "changed_paths") as changed:
                plan = cs.make_plan(event, "base", 4, {}, modules)
                self.assertEqual(plan["tier"], "full")
                self.assertTrue(cs.union_proof(modules, plan["shards"])[0])
                changed.assert_not_called()


if __name__ == "__main__":
    unittest.main()
