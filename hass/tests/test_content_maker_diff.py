"""Exercise the maker diff CLI with synthetic local Git histories only."""

from contextlib import redirect_stderr, redirect_stdout
import importlib.util
from io import StringIO
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import patch


SCRIPT = Path(__file__).resolve().parents[2] / "scripts/hass/content_maker_diff.py"
SPEC = importlib.util.spec_from_file_location("content_maker_diff", SCRIPT)
assert SPEC is not None and SPEC.loader is not None
CLI = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(CLI)


class ContentMakerDiffTests(unittest.TestCase):
    def setUp(self):
        temporary = tempfile.TemporaryDirectory()
        self.addCleanup(temporary.cleanup)
        self.root = Path(temporary.name).resolve()
        self.repo = self.root / "fixture-repo"
        self.repo.mkdir()
        self.env = {
            key: value for key, value in os.environ.items() if not key.startswith("GIT_")
        }
        self.env.update(GIT_CONFIG_NOSYSTEM="1", GIT_CONFIG_GLOBAL=os.devnull,
                        GIT_CEILING_DIRECTORIES=str(self.root), GIT_ALLOW_PROTOCOL="")
        self.git("init", "--quiet", "--template=")
        self.git("config", "user.name", "Fixture")
        self.git("config", "user.email", "fixture@example.invalid")
        self.path = self.repo / "hass/content/makers.json"
        self.path.parent.mkdir(parents=True)

    def git(self, *args):
        return subprocess.run(
            ["git", "-C", str(self.repo), *args], env=self.env,
            check=True, capture_output=True, text=True, timeout=10,
        ).stdout.strip()

    def revision(self, makers):
        if makers is None:
            self.path.unlink(missing_ok=True)
        else:
            raw = makers if isinstance(makers, bytes) else json.dumps({"makers": makers}).encode()
            self.path.write_bytes(raw)
        self.git("add", "-A")
        self.git("commit", "--quiet", "--allow-empty", "-m", "fixture snapshot")
        return self.git("rev-parse", "HEAD")

    def args(self, start, end, *extra, repo=None):
        return ["--repo", str(self.repo if repo is None else repo), "--from", start,
                "--to", end, *extra]

    def command(self, *args):
        return subprocess.run(
            [sys.executable, "-B", str(SCRIPT), *args], cwd=self.root, env=self.env,
            capture_output=True, text=True, timeout=10,
        )

    def invoke(self, start, end, *extra, repo=None):
        return self.command(*self.args(start, end, *extra, repo=repo))

    def assert_report(self, result, *info, failures=()):
        self.assertEqual(result.stderr, "")
        self.assertEqual(result.returncode, 1 if failures else 0)
        marker = "FAIL" if failures else "PASS"
        self.assertEqual(result.stdout.splitlines(), [
            *info, *(f"FAIL {reason}" for reason in failures), f"{marker} content_maker_diff",
        ])

    def test_c1_full_pass(self):
        # Catch count/order mistakes and any comparison against the working tree.
        start = self.revision({"old": {"name": "Original"}})
        end = self.revision({"old": {"name": "Renamed"}, "zeta": {}, "alpha": {}})
        self.path.write_text("not the committed JSON", encoding="utf-8")
        self.assert_report(self.invoke(start[:12], end, "--allow", "alpha"),
                           "makers-from 1", "makers-to 3", "added 2",
                           "added alpha", "added zeta", "changed old name")

    def test_c2_1_unsafe_repo(self):
        # A pre-resolve before checking the symlink would accept the clone alias.
        commit = self.revision({})
        alias = self.root / "clone-alias"
        alias.symlink_to(self.repo, target_is_directory=True)
        for path in (alias, self.path, self.root / "missing"):
            with self.subTest(path=path.name):
                self.assert_report(self.invoke(commit, commit, repo=path), failures=("unsafe-repo",))

    def test_c2_2_not_a_repo(self):
        # A valid directory without a Git repository is not an unsafe path.
        empty = self.root / "empty"
        empty.mkdir()
        self.assert_report(self.invoke("0000000", "0000000", repo=empty), failures=("not-a-repo",))

    def test_c2_3_bad_commit(self):
        # Both endpoints must resolve to commits; a blob hash is insufficient.
        commit = self.revision({})
        blob = self.git("rev-parse", "HEAD:hass/content/makers.json")
        unknown = "0" * 40
        for start, end, reasons in (
            (unknown, commit, ("bad-commit from",)),
            (commit, blob, ("bad-commit to",)),
            (unknown, blob, ("bad-commit from", "bad-commit to")),
        ):
            with self.subTest(start=start, end=end):
                self.assert_report(self.invoke(start, end), failures=reasons)

    def test_c2_4_not_ancestor(self):
        # The same valid endpoints in reverse order must not be compared.
        start = self.revision({})
        end = self.revision({"new": {}})
        self.assert_report(self.invoke(end, start), failures=("not-ancestor",))

    def test_c2_5_git_error(self):
        # A successful existence check followed by a failed read isn't absence/bad JSON.
        commit = self.revision({})
        real_run = subprocess.run

        def fail_show(command, **kwargs):
            if command[3] == "show":
                return subprocess.CompletedProcess(command, 128, b"", str(self.repo).encode())
            return real_run(command, **kwargs)

        stdout, stderr = StringIO(), StringIO()
        with (patch.dict(os.environ, self.env, clear=True),
              patch.object(CLI.subprocess, "run", side_effect=fail_show),
              redirect_stdout(stdout), redirect_stderr(stderr)):
            code = CLI.main(self.args(commit, commit))
        result = subprocess.CompletedProcess([], code, stdout.getvalue(), stderr.getvalue())
        self.assert_report(result, failures=("git-error",))

    def test_c2_6_makers_absent(self):
        # A missing file at either endpoint isn't an empty makers object.
        absent_from = self.revision(None)
        present = self.revision({})
        absent_to = self.revision(None)
        self.assert_report(self.invoke(absent_from, present), failures=("makers-absent from",))
        self.assert_report(self.invoke(present, absent_to), failures=("makers-absent to",))
        self.assert_report(self.invoke(absent_from, absent_to),
                           failures=("makers-absent from", "makers-absent to"))

    def test_c2_7_bad_json(self):
        # Replacement decoding, last-key-wins, and fallback-to-empty all fail here.
        good = self.revision({})
        for raw in (b'{"makers":{"x":{"place":"\xff"}}}', b'{"makers":',
                    b'{"makers":{},"makers":{}}', b'{"makers":{"x":{"place":1,"place":2}}}',
                    b'{"makers":{"x":{"place":NaN}}}', b'[]', b'{}', b'{"makers":[]}'):
            with self.subTest(raw=raw):
                bad = self.revision(raw)
                self.assert_report(self.invoke(good, bad), failures=("bad-json to",))
                following = self.revision({})
                self.assert_report(self.invoke(bad, following), failures=("bad-json from",))
                good = following

    def test_c2_8_maker_removed(self):
        # Removals are counted by key, not net change in the total.
        start = self.revision({"z-old": {}, "a-old": {}, "kept": {}})
        end = self.revision({"kept": {}, "new-one": {}, "new-two": {}})
        self.assert_report(self.invoke(start, end), "makers-from 3", "makers-to 3", "added 2",
                           "added new-one", "added new-two", "removed a-old", "removed z-old",
                           failures=("maker-removed 2",))

    def test_c2_9_origin_changed(self):
        # Count makers, not changed fields; missing versus null is also a difference.
        start = self.revision({"both": {"url": "https://first.invalid", "story": "First",
                                         "place": "First", "name": "First"},
                               "url-only": {"url": None}, "gone": {}})
        end = self.revision({"both": {"hidden": True, "url": "https://second.invalid",
                                       "place": "Second", "name": "Second"}, "url-only": {}})
        self.assert_report(self.invoke(start, end), "makers-from 3", "makers-to 2", "added 0",
                           "changed both name,place,story,url,hidden", "removed gone",
                           "changed url-only url", failures=("maker-removed 1", "origin-changed 2"))

    def test_c3_usage_exit_2(self):
        # Reject revision expressions or option-like values before touching Git.
        commit = self.revision({})
        valid = self.args(commit, commit)
        for argv in (valid[:-2], [*valid, "--unexpected"],
                     *(self.args(bad, commit) for bad in
                       ("HEAD", "abcdef", "ABCDEF0", "a" * 41, "abcdef0^", "--help")),
                     [*valid[:-2], "--to=-abcdef0"]):
            with self.subTest(argv=argv):
                result = self.command(*argv)
                self.assertEqual(result.returncode, 2)
                self.assertEqual(result.stdout, "")
                self.assertTrue(result.stderr.startswith("usage: "))

    def test_c4_read_only(self):
        # Snapshot the worktree and .git, including directory entries and mtimes.
        def snapshot():
            return {path.relative_to(self.root): (path.stat().st_mtime_ns,
                    path.read_bytes() if path.is_file() else None)
                    for path in (self.root, *self.root.rglob("*"))}

        start = self.revision({})
        end = self.revision({"new": {}})
        before = snapshot()
        self.assert_report(self.invoke(start, end),
                           "makers-from 0", "makers-to 1", "added 1", "added new")
        self.assertEqual(snapshot(), before)

    def test_c5_no_private_values(self):
        # Don't echo raw Git stderr, malformed argument text or changed field values.
        old = {"place": "canary-place-before", "story": "canary-story-before",
               "url": "https://canary-before.invalid"}
        new = {"place": "canary-place-after", "story": "canary-story-after",
               "url": "https://canary-after.invalid"}
        start = self.revision({"maker": old})
        end = self.revision({"maker": new})
        result = self.invoke(start, end)
        self.assert_report(result, "makers-from 1", "makers-to 1", "added 0",
                           "changed maker place,story,url", failures=("origin-changed 1",))
        empty = self.root / "canary-not-a-repo"
        empty.mkdir()
        not_repo = self.invoke(start, end, repo=empty)
        self.assert_report(not_repo, failures=("not-a-repo",))
        usage = self.command(*self.args(str(self.repo), end))
        self.assertEqual((usage.returncode, usage.stdout), (2, ""))
        for run in (result, not_repo, usage):
            for marker in (*old.values(), *new.values(), str(self.root)):
                self.assertNotIn(marker, run.stdout + run.stderr)

    def test_c6_endpoint_rule(self):
        # A history walk would flag the intermediate place change.
        start = self.revision({"maker": {"place": "First"}})
        self.revision({"maker": {"place": "Second"}})
        end = self.revision({"maker": {"place": "First"}})
        self.assert_report(self.invoke(start, end), "makers-from 1", "makers-to 1", "added 0")

    def test_c7_story_not_finding(self):
        # Editorial and visibility changes still appear, but do not fail the run.
        start = self.revision({"story-only": {"story": "First"}, "hidden-only": {}})
        end = self.revision({"story-only": {"story": "Second"}, "hidden-only": {"hidden": True}})
        self.assert_report(self.invoke(start, end), "makers-from 2", "makers-to 2", "added 0",
                           "changed hidden-only hidden", "changed story-only story")

    def test_c8_allow_key(self):
        # Exact repeatable exceptions cover both removal and change, not prefixes.
        start = self.revision({"maker": {"place": "First"}, "gone": {}, "maker-extra": {}})
        end = self.revision({"maker": {"place": "Second"}, "maker-extra": {"hidden": True}})
        self.assert_report(self.invoke(start, end, "--allow", "maker", "--allow", "gone"),
                           "makers-from 3", "makers-to 2", "added 0", "allowed gone",
                           "allowed maker", "changed maker-extra hidden")
