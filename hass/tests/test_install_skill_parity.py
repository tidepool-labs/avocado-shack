"""Fixture-only CLI tests for the attended skill parity check."""

import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest

SCRIPT = Path(__file__).resolve().parents[2] / "scripts/hass/install_skill_parity.py"
MAINTAIN, REVIEW = "hass-npp-maintain", "hass-npp-review"


class InstallSkillParityTests(unittest.TestCase):
    def setUp(self):
        self.root = Path(self.enterContext(tempfile.TemporaryDirectory())).resolve(strict=True)
        self.repo = self.root / "release-checkout"
        self.repo.mkdir()
        self.env = {
            "PATH": os.environ.get("PATH", os.defpath),
            "HOME": str(self.root),
            "GIT_CONFIG_NOSYSTEM": "1",
            "GIT_CONFIG_GLOBAL": os.devnull,
            "GIT_ALLOW_PROTOCOL": "",
        }
        self.git("init", "--quiet", "--template=")
        self.roots = {}
        self.sources = {}
        for skill, contents in ((MAINTAIN, b"maintain\r\n"), (REVIEW, b"review\xff\n")):
            source = self.repo / "docs/hass/skills" / skill / "SKILL.md"
            source.parent.mkdir(parents=True)
            source.write_bytes(contents)
            self.sources[skill] = source
            installed = self.root / "operator-resolved" / skill
            installed.mkdir(parents=True)
            (installed / "SKILL.md").write_bytes(contents)
            self.roots[skill] = str(installed)
        self.commit = self.snapshot()
        self.roster = self.root / "private-roster.json"

    def git(self, *args):
        return subprocess.run(
            ["git", "-c", "user.name=Fixture", "-c", "user.email=fixture@example.invalid",
             *args], cwd=self.repo, env=self.env, capture_output=True, check=True,
        ).stdout.decode().strip()

    def snapshot(self):
        self.git("add", "docs")
        self.git("commit", "--quiet", "-m", "fixture skill snapshot")
        return self.git("rev-parse", "HEAD")

    def check_cli(self, roster, code, *lines, commit=None, raw=False, repo=None):
        self.roster.write_text(roster if raw else json.dumps(roster), encoding="utf-8")
        result = subprocess.run(
            [sys.executable, "-B", str(SCRIPT), "--repo", str(repo or self.repo),
             "--commit", self.commit if commit is None else commit, "--roster", str(self.roster)],
            env=self.env, capture_output=True, text=True, timeout=10,
        )
        self.assertNotIn(str(self.root), result.stdout + result.stderr)
        self.assertEqual(result.stderr, "")
        self.assertEqual(result.returncode, code, result.stdout)
        self.assertCountEqual(result.stdout.splitlines(), lines)

    def test_uses_selected_commit_not_head_or_worktree_and_does_not_write(self):
        # A HEAD/worktree reader or text-mode reader cannot pass these bytes.
        self.sources[MAINTAIN].write_bytes(b"later commit\n")
        self.snapshot()
        self.sources[REVIEW].write_bytes(b"dirty worktree\n")
        installed = {Path(root) / "SKILL.md" for root in self.roots.values()}
        before = {path: (path.stat().st_mtime_ns, path.read_bytes()) for path in installed}
        self.check_cli({"first": self.roots, "second": self.roots}, 0,
                       f"PASS first {MAINTAIN}", f"PASS first {REVIEW}",
                       f"PASS second {MAINTAIN}", f"PASS second {REVIEW}")
        self.assertEqual({path: (path.stat().st_mtime_ns, path.read_bytes()) for path in installed}, before)
        self.assertEqual(self.sources[REVIEW].read_bytes(), b"dirty worktree\n")

    def test_missing_entry_in_one_profile_cannot_be_covered_by_another(self):
        # A union-only roster validator would accept the omitted profile row.
        self.check_cli({"complete": self.roots, "partial": {REVIEW: self.roots[REVIEW]}}, 1,
                       f"PASS complete {MAINTAIN}", f"PASS complete {REVIEW}",
                       f"FAIL partial {MAINTAIN}: missing roster entry", f"PASS partial {REVIEW}")

    def test_invalid_rosters_fail_without_echoing_values(self):
        # Empty, malformed, duplicate and path-shaped labels must not pass or leak.
        for roster in ("{}", "{invalid", '{"p": {}, "p": {}}',
                       json.dumps({str(self.root): self.roots})):
            with self.subTest(roster=roster):
                self.check_cli(roster, 1, "FAIL: invalid, empty or unreadable roster", raw=True)

    def test_stale_bytes_fail_even_if_normalized_text_matches(self):
        # A text-mode comparison would erase the only difference (CRLF vs LF).
        (Path(self.roots[MAINTAIN]) / "SKILL.md").write_bytes(b"maintain\n")
        self.check_cli({"p": self.roots}, 1, f"FAIL p {MAINTAIN}: bytes differ", f"PASS p {REVIEW}")

    def test_unresolved_skill_ancestor_refuses(self):
        # A no-follow open on just the final directory accepts this alias:
        # the final directory and SKILL.md are the same ones as in the direct control.
        installed = Path(self.roots[MAINTAIN])
        alias = self.root / "ancestor-alias"
        alias.symlink_to(installed.parent, target_is_directory=True)
        self.check_cli({"p": self.roots}, 0, f"PASS p {MAINTAIN}", f"PASS p {REVIEW}")
        self.check_cli({"p": {**self.roots, MAINTAIN: str(alias / installed.name)}}, 1,
                       f"FAIL p {MAINTAIN}: cannot read a regular file", f"PASS p {REVIEW}")

    def test_noncanonical_root_spelling_refuses(self):
        # Normalizing the roster string silently would accept these alternate spellings.
        root = self.roots[MAINTAIN]
        for kind, spelling in (("relative", root[1:]), ("double-leading-slash", "/" + root),
                               ("repeated-separator", root.replace("/operator-resolved", "//operator-resolved")),
                               ("trailing-separator", root + "/"), ("dot", root + "/."),
                               ("dot-dot", root + "/../" + MAINTAIN)):
            with self.subTest(kind=kind):
                self.check_cli({"p": {**self.roots, MAINTAIN: spelling}}, 1,
                               f"FAIL p {MAINTAIN}: invalid root", f"PASS p {REVIEW}")

    def test_missing_and_nonregular_leaf_fail_without_reading_targets(self):
        # is_file/open can follow a matching link, or block opening a FIFO.
        leaf = Path(self.roots[MAINTAIN]) / "SKILL.md"
        leaf.unlink()
        self.check_cli({"p": self.roots}, 1,
                       f"FAIL p {MAINTAIN}: missing root or file", f"PASS p {REVIEW}")
        for kind in ("symlink", "fifo", "directory"):
            with self.subTest(kind=kind):
                if kind == "symlink":
                    leaf.symlink_to(self.sources[MAINTAIN])
                elif kind == "fifo":
                    os.mkfifo(leaf)
                else:
                    leaf.mkdir()
                try:
                    self.check_cli({"p": self.roots}, 1,
                                   f"FAIL p {MAINTAIN}: not a regular file", f"PASS p {REVIEW}")
                finally:
                    leaf.rmdir() if kind == "directory" else leaf.unlink()

    def test_noncommit_and_noncheckout_inputs_do_not_fall_back(self):
        # Git revision syntax, abbreviated IDs and an enclosing repo are not pins.
        for commit, repo in (("HEAD", self.repo), (self.commit[:12], self.repo),
                             (self.commit, self.sources[MAINTAIN].parent)):
            with self.subTest(commit=commit, repo=repo):
                self.check_cli({"p": self.roots}, 1,
                               "FAIL: cannot resolve the exact release commit locally",
                               commit=commit, repo=repo)


if __name__ == "__main__":
    unittest.main()
