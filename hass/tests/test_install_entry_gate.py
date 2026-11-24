"""Offline entry-gate cases against disposable Git histories."""

from contextlib import redirect_stderr, redirect_stdout
import importlib.util
import io
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest


SCRIPT = Path(__file__).resolve().parents[2] / "scripts/hass/install_entry_gate.py"
SPEC = importlib.util.spec_from_file_location("install_entry_gate", SCRIPT)
assert SPEC is not None and SPEC.loader is not None
GATE = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(GATE)
PRIVATE = "synthetic-private-marker"
TREE_PATH = f"nested/{PRIVATE} [literal].txt"


class InstallEntryGateTests(unittest.TestCase):
    def setUp(self):
        temp = tempfile.TemporaryDirectory()
        self.addCleanup(temp.cleanup)
        root = Path(temp.name)
        self.repo = root / f"{PRIVATE}-repo"
        self.repo.mkdir()
        self.units = root / f"{PRIVATE}-units.json"
        self.env = {key: value for key, value in os.environ.items() if not key.startswith("GIT_")}
        self.env.update(GIT_CONFIG_GLOBAL=os.devnull, GIT_CONFIG_NOSYSTEM="1", GIT_ALLOW_PROTOCOL="")
        self.git("init", "--quiet", "--template=", "--object-format=sha1")
        path = self.repo / TREE_PATH
        path.parent.mkdir()
        path.write_text(PRIVATE, encoding="utf-8")
        self.git("add", "--", TREE_PATH)
        self.tree = self.git("write-tree")
        self.base = self.commit("fixture base")

    def git(self, *args):
        return subprocess.run(
            ["git", "-C", str(self.repo), "-c", "user.name=Fixture", "-c", "user.email=fixture@example.invalid",
             "-c", "commit.gpgSign=false", *args], env=self.env, capture_output=True,
            text=True, check=True, timeout=10,
        ).stdout.strip()

    def commit(self, subject, *parents, tree=None):
        parent_args = [item for parent in parents for item in ("-p", parent)]
        return self.git("commit-tree", tree or self.tree, *parent_args, "-m", subject)

    def merge(self, pr, first=None, second=None):
        first = first or self.base
        second = second or self.commit(f"fixture branch {pr}", first)
        return self.commit(f"Merge pull request #{pr} from a/{PRIVATE}", first, second)

    def invoke(self, target, units, *, raw=False, cli=False, repo=None):
        payload = units if raw else json.dumps(units).encode("ascii")
        self.units.write_bytes(payload)
        args = ["--repo", str(repo or self.repo), "--target", target, "--units", str(self.units)]
        if cli:
            result = subprocess.run([sys.executable, "-B", str(SCRIPT), *args],
                                    capture_output=True, text=True, check=False, timeout=10)
            code, out, err = result.returncode, result.stdout, result.stderr
        else:
            stdout, stderr = io.StringIO(), io.StringIO()
            with redirect_stdout(stdout), redirect_stderr(stderr):
                code = GATE.main(args)
            out, err = stdout.getvalue(), stderr.getvalue()
        self.assertNotIn(PRIVATE, out + err)
        self.assertNotIn("Traceback", out + err)
        self.assertEqual(self.units.read_bytes(), payload)
        return code, out, err

    def test_cli_reports_full_first_parent_merge_shas_at_pinned_target(self):
        # An all-parent walk sees the side merge for B; a HEAD walk sees another C.
        first = self.merge(73101)
        side_merge = self.merge(73101, second=self.commit("distinct side branch", self.base))
        side = self.commit("side tip", side_merge)
        second = self.merge(73102, first, side)
        newer = self.merge(73102, second)
        self.git("update-ref", "HEAD", newer)
        # Absence in the checkout is not absence in the target tree.
        (self.repo / TREE_PATH).unlink()
        status_before = self.git("status", "--porcelain")
        result = self.invoke(second, {"B": {"pr": 73101, "paths": [TREE_PATH, "nested"]},
                                      "C": {"pr": 73102, "paths": [TREE_PATH]}}, cli=True)
        self.assertEqual(result, (0,
                                 f"B: PR #73101; {first}; ancestor: yes; path 1: present; path 2: present\n"
                                 f"C: PR #73102; {second}; ancestor: yes; path 1: present\n", ""))
        self.assertEqual(self.git("rev-parse", "HEAD"), newer)
        self.assertEqual(self.git("status", "--porcelain"), status_before)
        self.assertFalse((self.repo / TREE_PATH).exists())

    def test_no_merge_rejects_lookalike_subjects_and_non_merges(self):
        # Drop --merges, use a substring, or omit the trailing-space boundary and this falsely passes.
        other = self.merge(731030)
        branch = self.commit("fixture branch", other)
        lookalike = self.commit(f"prefix Merge pull request #73103 from a/{PRIVATE}", other, branch)
        single = self.commit(f"Merge pull request #73103 from a/{PRIVATE}", lookalike)
        target = self.commit(f"Merge pull request #73103x from a/{PRIVATE}", single, branch)
        self.assertEqual(self.invoke(target, {"D": {"pr": 73103, "paths": [TREE_PATH]}}),
                         (1, "D: PR #73103; no merge found; path 1: present\n", ""))
        self.assertEqual(self.invoke(self.base, {"D": {"pr": 73103, "paths": [TREE_PATH]}}),
                         (1, "D: PR #73103; no merge found; path 1: present\n", ""))

    def test_duplicate_merges_do_not_pick_a_winner(self):
        # A first/last match selector silently produces an ambiguous gate SHA.
        target = self.merge(73104, self.merge(73104))
        self.assertEqual(self.invoke(target, {"E": {"pr": 73104, "paths": [TREE_PATH]}}),
                         (1, "E: PR #73104; duplicate merges found; path 1: present\n", ""))

    def test_known_merge_without_paths_refuses(self):
        # all([]) would let a unique merge pass without proving any retained path.
        target = self.merge(73108)
        self.assertEqual(self.invoke(target, {"B": {"pr": 73108, "paths": []}}, cli=True),
                         (2, "", "error: malformed units JSON: known pr requires at least one path\n"))
        self.assertEqual(self.invoke(target, {"B": {"pr": None, "paths": []}}),
                         (1, "B: PR null; FILL-IN open\n", ""))

    def test_missing_literal_path_and_open_pr_both_fail(self):
        # Worktree lookup or Git pathspec expansion accepts a path absent from the pinned tree.
        target = self.merge(73105)
        absent = f"nested/{PRIVATE}-untracked.txt"
        (self.repo / absent).touch()
        self.assertEqual(self.invoke(target, {"F": {"pr": 73105, "paths": [absent, "nested/*", TREE_PATH]}}),
                         (1, f"F: PR #73105; {target}; ancestor: yes; path 1: missing; path 2: missing; "
                             "path 3: present\n", ""))
        # A skipped open PR must not make the kit look ready, even with present paths.
        self.assertEqual(self.invoke(target, {"G": {"pr": None, "paths": [TREE_PATH]},
                                              "H": {"pr": 73105, "paths": [TREE_PATH]}}),
                         (1, f"G: PR null; FILL-IN open; path 1: present\n"
                             f"H: PR #73105; {target}; ancestor: yes; path 1: present\n", ""))

    def test_cli_errors_redact_argument_values_and_input_filenames(self):
        # Argparse and file-open diagnostics ordinarily echo untrusted values.
        args = ["--repo", str(self.repo), "--target", self.base, "--units", str(self.units)]
        stderr = io.StringIO()
        with redirect_stderr(stderr):
            self.assertEqual(GATE.main(args), 2)
            with self.assertRaises(SystemExit) as error:
                GATE.main([*args, f"--{PRIVATE}"])
        self.assertEqual(error.exception.code, 2)
        self.assertIn("could not read units JSON", stderr.getvalue())
        self.assertIn("invalid arguments", stderr.getvalue())
        self.assertNotIn(PRIVATE, stderr.getvalue())

    def test_target_must_be_an_available_commit_without_echoing_input(self):
        # A tree/blob/tag, unresolved hash or revision expression is not the requested commit object.
        blob = self.git("rev-parse", f"{self.base}:{TREE_PATH}")
        self.git("tag", "-a", "fixture-tag", self.base, "-m", PRIVATE)
        tag = self.git("rev-parse", "fixture-tag")
        for target in ("0" * 40, self.tree, blob, tag, f"{self.base}^{{commit}}", PRIVATE):
            with self.subTest(target=target):
                code, out, err = self.invoke(target, {"H": {"pr": 73106, "paths": [TREE_PATH]}})
                self.assertEqual((code, out), (2, ""))
                self.assertIn("unknown target or target is not a commit", err)

    def test_malformed_json_and_schema_fail_without_echoing_values(self):
        # Permissive JSON or schema parsing could silently replace or omit a gate, or echo raw values.
        for raw in (
            f'{{"{PRIVATE}":'.encode(), b"\xff", b"[]", b"{}",
            f'{{"B":{{"pr":1,"paths":[]}},"B":{{"pr":null,"paths":["{PRIVATE}"]}}}}'.encode(),
            b'{"B":{"pr":1,"pr":2,"paths":[]}}',
            json.dumps({PRIVATE: {"pr": 1, "paths": []}}).encode(),
            json.dumps({"B": {"pr": 1, "paths": [], "extra": PRIVATE}}).encode(),
            b'{"B":{"paths":[]}}', b'{"B":{"pr":1}}', b'{"B":null}',
            b'{"B":{"pr":true,"paths":[]}}', b'{"B":{"pr":-1,"paths":[]}}',
            b'{"B":{"pr":1.0,"paths":[]}}', b'{"B":{"pr":NaN,"paths":[]}}',
            json.dumps({"B": {"pr": PRIVATE, "paths": []}}).encode(),
            json.dumps({"B": {"pr": 1, "paths": PRIVATE}}).encode(),
            *(json.dumps({"B": {"pr": 1, "paths": [path]}}).encode()
              for path in (None, "", f"/{PRIVATE}", f"../{PRIVATE}", f"{PRIVATE}\x00", "\ud800")),
        ):
            with self.subTest(raw=raw):
                code, out, err = self.invoke(self.base, raw, raw=True)
                self.assertEqual((code, out), (2, ""))
                self.assertIn("malformed units JSON", err)

    def test_checkout_failures_are_named_and_redacted(self):
        # Raw Git diagnostics expose the repo name; a shallow history cannot establish uniqueness.
        units = {"B": {"pr": 73107, "paths": [TREE_PATH]}}
        code, out, err = self.invoke(self.base, units, repo=self.repo / PRIVATE)
        self.assertEqual((code, out), (2, ""))
        self.assertIn("--repo must name a local Git checkout", err)
        (self.repo / ".git/shallow").write_text(self.base + "\n", encoding="ascii")
        code, out, err = self.invoke(self.base, units)
        self.assertEqual((code, out), (2, ""))
        self.assertIn("shallow checkout", err)
        (self.repo / ".git/shallow").unlink()
        # Even a local checkout with all fixture objects must not attempt lazy network fetches.
        self.git("config", "remote.fixture.promisor", "true")
        code, out, err = self.invoke(self.base, units)
        self.assertEqual((code, out), (2, ""))
        self.assertIn("partial-clone configuration offline", err)
