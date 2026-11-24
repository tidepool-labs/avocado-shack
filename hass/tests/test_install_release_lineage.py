"""Exercise the release-lineage CLI against disposable, offline Git histories."""

import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest


CLI = Path(__file__).resolve().parents[2] / "scripts/hass/install_release_lineage.py"
RUNTIME = "runtime/handler.py"
LITERAL = "runtime/rule[1].txt"


class InstallReleaseLineageTests(unittest.TestCase):
    def setUp(self):
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        self.root = Path(tmp.name)
        self.repo = self.root / "repo"
        self.repo.mkdir()
        self.manifest = self.root / "manifest.json"
        self.env = {key: value for key, value in os.environ.items() if not key.startswith("GIT_")}
        self.env.update(GIT_CONFIG_GLOBAL=os.devnull, GIT_CONFIG_NOSYSTEM="1", GIT_ALLOW_PROTOCOL="")
        self.git("init", "--initial-branch=main", "--object-format=sha1", "--template=")
        self.git("commit", "--allow-empty", "-m", "base")
        self.base = self.git("rev-parse", "HEAD")
        self.git("switch", "-c", "work")
        (self.repo / "runtime").mkdir()
        (self.repo / RUNTIME).write_text("fixture runtime contents\n", encoding="utf-8")
        (self.repo / LITERAL).write_text("fixture rule contents\n", encoding="utf-8")
        self.git("add", "runtime")
        self.git("commit", "-m", "add runtime")
        self.git("switch", "main")
        self.git("merge", "--no-ff", "work", "-m", "reviewed merge")
        self.merge = self.git("rev-parse", "HEAD")

    def git(self, *args):
        return subprocess.run(
            ["git", "-C", str(self.repo), "-c", "user.name=Fixture", "-c", "user.email=fixture@example.invalid",
             *args], env=self.env, check=True, capture_output=True, text=True,
        ).stdout.strip()

    def check(self, target=None, *, gates=None, paths=None):
        self.manifest.write_text(json.dumps({
            "gates": {"reviewed": self.merge} if gates is None else gates,
            "paths": [RUNTIME, LITERAL] if paths is None else paths,
        }), encoding="utf-8")
        return self.run_cli(self.merge if target is None else target)

    def run_cli(self, target):
        return subprocess.run(
            [sys.executable, "-B", str(CLI), "--repo", str(self.repo), "--target", target,
             "--manifest", str(self.manifest)], env=self.env, capture_output=True, text=True,
        )

    def test_all_gates_and_literal_tree_paths_present(self):
        # Target differs from HEAD and one path contains pathspec metacharacters.
        self.git("switch", "--detach", self.base)
        before = {p.relative_to(self.repo): p.read_bytes() for p in self.repo.rglob("*") if p.is_file()}
        result = self.check(gates={"first": self.base, "reviewed": self.merge})
        self.assertEqual(result.returncode, 0, result.stderr + result.stdout)
        for label in ("first", "reviewed"):
            self.assertRegex(result.stdout, rf"Gate '{label}' [a-f0-9]+: object present=yes; ancestor=yes")
        for path in (RUNTIME, LITERAL):
            self.assertIn(f"Path {path!r}: present=yes", result.stdout)
        self.assertIn("does not check CI or review approval", result.stdout)
        self.assertNotIn("fixture runtime contents", result.stdout + result.stderr)
        self.assertEqual(before, {p.relative_to(self.repo): p.read_bytes()
                                  for p in self.repo.rglob("*") if p.is_file()})

    def test_named_release_file_must_be_a_regular_blob(self):
        # A later commit can replace a file with a link or directory without
        # changing its tree path or losing the reviewed merge from its ancestry.
        entry = self.repo / RUNTIME
        for kind, expected_exit, status in (
            ("ordinary", 0, "yes"),
            ("executable", 0, "yes"),
            ("symlink", 1, "no (not a regular file blob)"),
            ("directory", 1, "no (not a regular file blob)"),
        ):
            with self.subTest(kind=kind):
                if kind == "executable":
                    self.git("update-index", "--chmod=+x", RUNTIME)
                elif kind == "symlink":
                    entry.unlink()
                    entry.symlink_to(Path(LITERAL).name)
                    self.git("add", "--", RUNTIME)
                elif kind == "directory":
                    entry.unlink()
                    entry.mkdir()
                    (entry / "child").touch()
                    self.git("add", "--", RUNTIME)
                if kind != "ordinary":
                    self.git("commit", "-m", kind)
                result = self.check(self.git("rev-parse", "HEAD"))
                self.assertIn(f"Gate 'reviewed' {self.merge}: object present=yes; ancestor=yes", result.stdout)
                self.assertIn(f"Path {LITERAL!r}: present=yes", result.stdout)
                self.assertEqual(result.returncode, expected_exit, result.stdout + result.stderr)
                self.assertIn(f"Path {RUNTIME!r}: present={status}\n", result.stdout)

    def test_missing_object_is_not_a_found_nonancestor(self):
        missing = "1" * 40
        result = self.check(gates={"missing": missing, "reviewed": self.merge})
        self.assertEqual(result.returncode, 1)
        self.assertIn(f"Gate 'missing' {missing}: object present=no; ancestor=no", result.stdout)
        self.assertIn(f"Gate 'reviewed' {self.merge}: object present=yes; ancestor=yes", result.stdout)
        self.assertIn(f"Path {RUNTIME!r}: present=yes", result.stdout)

    def test_side_branch_merge_exists_but_is_not_an_ancestor(self):
        self.git("switch", "-c", "side", self.base)
        self.git("merge", "--no-ff", "work", "-m", "side-only merge")
        side_merge = self.git("rev-parse", "HEAD")
        self.git("switch", "main")
        result = self.check(gates={"side": side_merge})
        self.assertEqual(result.returncode, 1)
        self.assertIn(f"Gate 'side' {side_merge}: object present=yes; ancestor=no", result.stdout)
        self.assertIn(f"Path {RUNTIME!r}: present=yes", result.stdout)

    def test_reverted_merge_is_still_an_ancestor_but_its_files_are_gone(self):
        self.git("revert", "--no-edit", "-m", "1", self.merge)
        (self.repo / "runtime").mkdir()
        (self.repo / "runtime/rule1.txt").touch()  # A tracked wildcard-style lookalike is not the exact path.
        self.git("add", "runtime/rule1.txt")
        self.git("commit", "-m", "add a differently named rule after rollback")
        target = self.git("rev-parse", "HEAD")
        (self.repo / RUNTIME).touch()  # A restored worktree file is not part of the selected tree.
        result = self.check(target)
        self.assertEqual(result.returncode, 1)
        self.assertIn(f"Gate 'reviewed' {self.merge}: object present=yes; ancestor=yes", result.stdout)
        for path in (RUNTIME, LITERAL):
            self.assertIn(f"Path {path!r}: present=no", result.stdout)

    def test_target_and_manifest_require_complete_literal_commit_ids(self):
        # Refs, Git revision expressions, abbreviations and wrong lengths must not resolve.
        for bad in ("HEAD", "main", self.merge[:12], self.merge[:-1], self.merge + "0",
                    "f" * 64, "g" + self.merge[1:], self.merge + "^{commit}", self.merge + "\n", ""):
            with self.subTest(bad=bad):
                for result in (self.check(bad), self.check(gates={"bad": bad})):
                    self.assertEqual(result.returncode, 2)
                    self.assertIn("full 40-digit hexadecimal commit SHA", result.stderr)
        for bad in (False, 123, None):
            with self.subTest(bad=bad):
                self.assertEqual(self.check(gates={"bad": bad}).returncode, 2)
        result = self.check(self.merge.upper(), gates={"reviewed": self.merge.upper()})
        self.assertEqual(result.returncode, 0, result.stderr + result.stdout)

    def test_object_ids_must_name_commits_not_trees_or_tags(self):
        self.git("tag", "-a", "fixture-tag", "-m", "tag")
        for oid in (self.git("rev-parse", "HEAD^{tree}"), self.git("rev-parse", "fixture-tag")):
            with self.subTest(oid=oid):
                self.assertEqual(self.check(oid).returncode, 2)
                result = self.check(gates={"not-commit": oid})
                self.assertEqual(result.returncode, 1)
                self.assertIn("object present=yes; ancestor=no (not a commit)", result.stdout)

    def test_duplicate_gate_keys_cannot_silently_drop_a_requirement(self):
        self.manifest.write_text(
            '{"gates":{"A":"' + "1" * 40 + '","A":"' + self.merge + '"},"paths":["' + RUNTIME + '"]}',
            encoding="utf-8",
        )
        result = self.run_cli(self.merge)
        self.assertEqual(result.returncode, 2)
        self.assertIn("duplicate JSON key", result.stderr)

    def test_partial_clone_config_is_refused_before_object_checks(self):
        self.git("config", "remote.fixture.promisor", "true")
        result = self.check(gates={"missing": "1" * 40})
        self.assertEqual(result.returncode, 2)
        self.assertIn("partial-clone configuration", result.stderr)
        self.assertNotIn("Gate ", result.stdout)


if __name__ == "__main__":
    unittest.main()
