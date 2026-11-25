"""Fixture-only CLI tests for the health-check-id vs SUPPORT.md index check.

Every fixture repo is built in a TemporaryDirectory with synthetic ids only.
Each test method name starts with the CONTRACT item it pins (C1-C7).
"""

import ast
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest


SCRIPT = Path(__file__).resolve().parents[2] / "scripts/hass/support_id_index.py"
HEALTH = "hass/health.py"
SUPPORT = "docs/hass/SUPPORT.md"
PASS = "PASS support_id_index"
FAIL = "FAIL support_id_index"

HEALTH_HEAD = "def _problem(check, detail):\n    return (check, detail)\n\n\ndef run(problems, info):\n"
# The shape of health.py's real loop: one call site, the id bound from row data.
DYNAMIC_LOOP = (
    "    for check, table in ((\"outbox-stuck\", \"outbox\"), (\"apply-stuck\", \"drafts\")):\n"
    "        problems.append(_problem(check, table))\n"
)


def call(check, detail="synthetic detail"):
    return f"    problems.append(_problem({check!r}, {detail!r}))\n"


def health_source(*statements):
    return HEALTH_HEAD + "".join(statements) + "    return problems\n"


def support_source(*ids, extra=""):
    sections = "".join(f"### `{name}`\n- **Means:** synthetic.\n\n" for name in ids)
    return f"# Support\n\nProse.\n\n## Problems\n\n{sections}{extra}"


class SupportIdIndexTests(unittest.TestCase):
    def setUp(self):
        temporary = tempfile.TemporaryDirectory()
        self.addCleanup(temporary.cleanup)
        self.root = Path(temporary.name).resolve()
        self.repo = self.root / "repo"

    def build(self, health=None, support=None):
        for relative, text in ((HEALTH, health), (SUPPORT, support)):
            if text is not None:
                path = self.repo / relative
                path.parent.mkdir(parents=True, exist_ok=True)
                path.write_text(text, encoding="utf-8")
        self.repo.mkdir(exist_ok=True)

    def run_cli(self, *options, repo=True):
        argv = [sys.executable, "-B", str(SCRIPT)]
        if repo:
            argv += ["--repo", str(self.repo)]
        return subprocess.run(argv + list(options), cwd=self.root,
                              capture_output=True, text=True, timeout=20)

    def assert_lines(self, result, code, lines):
        self.assertEqual(result.stderr, "")
        self.assertEqual(result.stdout.splitlines(), lines)
        self.assertEqual(result.returncode, code)

    def assert_findings(self, result, lines):
        # C2: every finding run exits 1 and ends with the failure trailer.
        self.assert_lines(result, 1, lines + [FAIL])
        self.assertNotIn(PASS, result.stdout)

    # ---- C1 ----------------------------------------------------------------
    def test_c1_full_pass(self):
        # Believable bug: a clean run exiting non-zero, or a missing/extra trailer.
        self.build(health_source(call("alpha"), call("beta")), support_source("alpha", "beta"))
        result = self.run_cli()
        self.assert_lines(result, 0, ["ids code 2", "ids doc 2", PASS])
        self.assertNotIn("FAIL", result.stdout)

    # ---- C2 ----------------------------------------------------------------
    def test_c2_1_no_file(self):
        # Believable bug: a traceback, or comparing ids when one input is absent.
        good_health = health_source(call("alpha"))
        good_support = support_source("beta")
        cases = (
            ("health", None, good_support, [f"FAIL no-file {HEALTH}"]),
            ("support", good_health, None, [f"FAIL no-file {SUPPORT}"]),
            ("both", None, None, [f"FAIL no-file {HEALTH}", f"FAIL no-file {SUPPORT}"]),
        )
        for name, health, support, lines in cases:
            with self.subTest(name), tempfile.TemporaryDirectory() as other:
                self.repo = Path(other).resolve() / "repo"
                self.build(health, support)
                self.assert_findings(self.run_cli(), lines)
        with self.subTest("missing repo directory"):
            self.repo = self.root / "absent"
            self.assert_findings(self.run_cli(), [f"FAIL no-file {HEALTH}", f"FAIL no-file {SUPPORT}"])
        with self.subTest("directory in place of a file"), tempfile.TemporaryDirectory() as other:
            self.repo = Path(other).resolve() / "repo"
            self.build(None, good_support)
            (self.repo / HEALTH).mkdir(parents=True)
            self.assert_findings(self.run_cli(), [f"FAIL no-file {HEALTH}"])

    def test_c2_2_bad_python(self):
        # Believable bug: importing/running health.py, or reporting id findings
        # (here undocumented/stale ids) after a parse failure.
        bad_sources = {
            "syntax": "def broken(:\n",
            "nul byte": "x = 1\x00\n",
            "bad encoding": "name = '\xff'\n".encode("latin-1"),
        }
        for name, source in bad_sources.items():
            with self.subTest(name), tempfile.TemporaryDirectory() as other:
                self.repo = Path(other).resolve() / "repo"
                self.build(None, support_source("stale-one"))
                (self.repo / HEALTH).parent.mkdir(parents=True, exist_ok=True)
                data = source if isinstance(source, bytes) else source.encode()
                (self.repo / HEALTH).write_bytes(data)
                self.assert_findings(self.run_cli(), ["FAIL bad-python"])

    def test_c2_3_undocumented(self):
        # Believable bug: matching only some heading forms, or skipping the
        # check when an unresolved call exists.
        extra = "## `level-two`\n#### `level-four`\nSee `in-prose` and ### `inline` here.\n### `trailing` text\n"
        health = health_source(call("alpha"), call("level-two"), call("level-four"),
                               call("in-prose"), call("inline"), call("trailing"))
        self.build(health, support_source("alpha", extra=extra))
        self.assert_findings(self.run_cli(), [
            "ids code 6", "ids doc 1",
            "FAIL undocumented in-prose", "FAIL undocumented inline",
            "FAIL undocumented level-four", "FAIL undocumented level-two",
            "FAIL undocumented trailing",
        ])
        with self.subTest("still reported with unresolved calls"):
            self.build(health_source(call("alpha"), call("lonely"), DYNAMIC_LOOP),
                       support_source("alpha"))
            self.assert_findings(self.run_cli(), [
                "ids code 2", "ids doc 1", "FAIL undocumented lonely",
                "FAIL unresolved-dynamic 1",
            ])

    def test_c2_4_stale_doc(self):
        # Believable bug: a heading for a retired check goes unreported.
        self.build(health_source(call("alpha")), support_source("alpha", "retired", "gone"))
        self.assert_findings(self.run_cli(), [
            "ids code 1", "ids doc 3", "FAIL stale-doc gone", "FAIL stale-doc retired",
        ])

    def test_c2_5_unresolved_dynamic(self):
        # Believable bug: reporting the two real loop ids as stale, counting
        # possible runtime ids instead of call sites, or printing a success trailer.
        docs = support_source("outbox-stuck", "apply-stuck")
        with self.subTest("main-shaped loop"):
            self.build(health_source(DYNAMIC_LOOP), docs)
            result = self.run_cli()
            self.assert_findings(result, ["ids code 0", "ids doc 2", "FAIL unresolved-dynamic 1"])
            self.assertEqual(result.stdout.count("FAIL unresolved-dynamic 1"), 1)
            self.assertNotIn("stale-doc", result.stdout)
        with self.subTest("literal id with heading omitted"):
            self.build(health_source(DYNAMIC_LOOP, call("lonely")), docs)
            self.assert_findings(self.run_cli(), [
                "ids code 1", "ids doc 2", "FAIL undocumented lonely",
                "FAIL unresolved-dynamic 1",
            ])
        with self.subTest("counts sites, one line"):
            sites = (
                "    problems.append(_problem(name, 'a'))\n"            # variable
                "    problems.append(_problem(f'x-{name}', 'b'))\n"      # f-string
                "    problems.append(_problem('x' + name, 'c'))\n"       # expression
                "    problems.append(_problem(*args))\n"                 # starred
                "    problems.append(_problem(check='kw'))\n"            # keyword only
                "    problems.append(_problem())\n"                      # no arguments
                "    problems.append(_problem(7, 'd'))\n"                # not a string
                "    problems.append(_problem('has space', 'e'))\n"      # not an id
            )
            self.build(health_source(sites, DYNAMIC_LOOP), docs)
            self.assert_findings(self.run_cli(), ["ids code 0", "ids doc 2", "FAIL unresolved-dynamic 9"])
        with self.subTest("other callables are not _problem call sites"):
            other = ("    problems.append(helper._problem(name, 'a'))\n"
                     "    problems.append(other_problem(name, 'b'))\n")
            self.build(health_source(other, call("alpha")), support_source("alpha"))
            self.assert_lines(self.run_cli(), 0, ["ids code 1", "ids doc 1", PASS])

    # ---- C3 ----------------------------------------------------------------
    def test_c3_usage_exit_2(self):
        # Believable bug: a custom usage code, or usage text on stdout.
        self.build(health_source(call("alpha")), support_source("alpha"))
        for name, options, repo in (("missing --repo", (), False),
                                    ("unknown flag", ("--no-such-flag",), True),
                                    ("--repo without value", ("--repo",), False)):
            with self.subTest(name):
                result = self.run_cli(*options, repo=repo)
                self.assertEqual(result.returncode, 2)
                self.assertEqual(result.stdout, "")
                self.assertIn("usage:", result.stderr)

    # ---- C4 ----------------------------------------------------------------
    def snapshot(self):
        state = {}
        for path in sorted(self.root.rglob("*")):
            info = path.stat()
            data = path.read_bytes() if path.is_file() else None
            state[path.relative_to(self.root)] = (data, info.st_mtime_ns)
        return state

    def test_c4_read_only(self):
        # Believable bug: touching, rewriting or creating anything (a cache or
        # report file) in the repo tree, whatever the outcome.
        scenarios = (
            ("pass", health_source(call("alpha")), support_source("alpha")),
            ("findings", health_source(call("alpha")), support_source("beta")),
            ("bad python", "def broken(:\n", support_source("beta")),
            ("unresolved", health_source(DYNAMIC_LOOP), support_source("outbox-stuck")),
        )
        for name, health, support in scenarios:
            with self.subTest(name), tempfile.TemporaryDirectory() as other:
                self.root = Path(other).resolve()
                self.repo = self.root / "repo"
                self.build(health, support)
                for path in (self.repo / HEALTH, self.repo / SUPPORT):
                    os.utime(path, ns=(1_000_000_000, 1_000_000_000))  # an old, distinctive time
                before = self.snapshot()
                self.run_cli()
                self.assertEqual(self.snapshot(), before)

    # ---- C5 ----------------------------------------------------------------
    def test_c5_no_private_values(self):
        # Believable bug: echoing message text, other ids/digests, or the input
        # path (also via a parse error or argparse text).
        canaries = ("canary-message-text", "canary-chat-value", "canary-sender-value",
                    "canary-other-id", "canary-digest-0123456789abcdef", "canary-prose-id",
                    "canary_variable_name", "canary-comment")
        health = (
            "# canary-comment\n"
            "CHAT = 'canary-chat-value'\n"
            "SENDER = 'canary-sender-value'\n"
            + health_source(
                call("alpha", "canary-message-text"),
                call("undocumented-one", "canary-digest-0123456789abcdef"),
                "    other('canary-other-id')\n",
                "    problems.append(_problem(canary_variable_name, 'x'))\n",
            )
        )
        support = support_source("alpha", "stale-one",
                                 extra="Text `canary-prose-id` and canary-message-text.\n")
        scenarios = {
            "findings": (health, support),
            "bad python": (health + "def broken(:\n", support),
            "pass": (health_source(call("alpha", "canary-message-text")),
                     support_source("alpha", extra="canary-prose-id\n")),
        }
        forbidden = canaries + (str(self.root), str(self.repo), self.root.name)
        for name, (health_text, support_text) in scenarios.items():
            with self.subTest(name):
                self.build(health_text, support_text)
                result = self.run_cli()
                for canary in forbidden:
                    self.assertNotIn(canary, result.stdout + result.stderr)
        with self.subTest("no-file"):
            self.repo = self.root / "canary-missing-dir"
            result = self.run_cli()
            self.assertEqual(result.returncode, 1)
            for canary in forbidden + ("canary-missing-dir",):
                self.assertNotIn(canary, result.stdout + result.stderr)

    # ---- C6 ----------------------------------------------------------------
    def test_c6_sorted_unique(self):
        # Believable bug: discovery-order or repeated ids, or groups out of C2 order.
        self.build(
            health_source(call("zulu"), call("alpha"), call("mike"), call("zulu"), call("alpha")),
            support_source("yankee", "bravo", "bravo", "delta", "yankee"),
        )
        self.assert_findings(self.run_cli(), [
            "ids code 3", "ids doc 3",
            "FAIL undocumented alpha", "FAIL undocumented mike", "FAIL undocumented zulu",
            "FAIL stale-doc bravo", "FAIL stale-doc delta", "FAIL stale-doc yankee",
        ])
        with self.subTest("unresolved group last"):
            self.build(health_source(call("zulu"), DYNAMIC_LOOP, call("alpha"), call("zulu")),
                       support_source("outbox-stuck"))
            self.assert_findings(self.run_cli(), [
                "ids code 2", "ids doc 1",
                "FAIL undocumented alpha", "FAIL undocumented zulu",
                "FAIL unresolved-dynamic 1",
            ])
        with self.subTest("missing inputs in C2.1 order"):
            self.repo = self.root / "none"
            self.assert_findings(self.run_cli(), [f"FAIL no-file {HEALTH}", f"FAIL no-file {SUPPORT}"])

    # ---- C7 ----------------------------------------------------------------
    def test_c7_known_id_counts(self):
        # Believable bug: counting call sites instead of distinct ids, counting
        # non-heading mentions, or printing counts after the findings.
        health = health_source(
            call("alpha"), call("alpha"), call("beta"),
            "    info.append(_problem('gamma', 'nested'))\n",
            "    problems.append(helper._problem('not-bare', 'x'))\n",
            "    label = 'not-a-call'\n",
        )
        support = support_source("alpha", "alpha", "beta", "gamma", "extra", extra="`beta` in prose\n")
        self.build(health, support)
        result = self.run_cli()
        self.assert_findings(result, ["ids code 3", "ids doc 4", "FAIL stale-doc extra"])
        with self.subTest("partial count when unresolved"):
            self.build(health_source(call("alpha"), DYNAMIC_LOOP), support_source("alpha"))
            self.assert_lines(self.run_cli(), 1,
                              ["ids code 1", "ids doc 1", "FAIL unresolved-dynamic 1", FAIL])
        with self.subTest("no count lines for invalid inputs"):
            self.build("def broken(:\n", support_source("alpha"))
            self.assertNotIn("ids ", self.run_cli().stdout)

    # ---- S1 ----------------------------------------------------------------
    def test_s1_imports_stay_offline_stdlib(self):
        # Believable bug: a network or subprocess import slipping into the script.
        tree = ast.parse(SCRIPT.read_text(encoding="utf-8"))
        modules = set()
        for node in ast.walk(tree):
            if isinstance(node, ast.Import):
                modules.update(alias.name.split(".")[0] for alias in node.names)
            elif isinstance(node, ast.ImportFrom):
                modules.add((node.module or "").split(".")[0])
        self.assertEqual(modules & {"socket", "urllib", "http", "requests", "subprocess", "hass"}, set())


if __name__ == "__main__":
    unittest.main()
