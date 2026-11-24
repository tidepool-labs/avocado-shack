"""Offline contract tests for the endpoint store-fact checker."""

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
from unittest.mock import patch


SCRIPT = Path(__file__).resolve().parents[2] / "scripts/hass/content_store_diff.py"
STORE_PATH = "hass/content/store.json"
PASS = "PASS content_store_diff"
FAIL = "FAIL content_store_diff"


class ContentStoreDiffTests(unittest.TestCase):
    def setUp(self):
        temporary = tempfile.TemporaryDirectory()
        self.addCleanup(temporary.cleanup)
        self.root = Path(temporary.name).resolve()
        self.repo = self.root / "clone"
        self.repo.mkdir()
        self.env = {key: value for key, value in os.environ.items() if not key.startswith("GIT_")}
        self.env.update(GIT_CONFIG_NOSYSTEM="1", GIT_CONFIG_GLOBAL=str(self.root / "no-config"),
                        GIT_ALLOW_PROTOCOL="", GIT_CONFIG_SYSTEM=str(self.root / "no-config"))
        self.git("init", "--quiet", "--object-format=sha1")
        self.store = self.repo / STORE_PATH
        self.store.parent.mkdir(parents=True)

    def git(self, *args):
        return subprocess.run(
            ["git", "-C", str(self.repo), "-c", "user.name=Fixture",
             "-c", "user.email=fixture@example.invalid", *args],
            capture_output=True, text=True, check=True, timeout=10, env=self.env,
        ).stdout.strip()

    def commit(self, document=None):
        if document is not None:
            raw = document if isinstance(document, bytes) else json.dumps(document).encode("utf-8")
            self.store.write_bytes(raw)
            self.git("add", "--", STORE_PATH)
        self.git("commit", "--quiet", "--allow-empty", "-m", "Fixture endpoint")
        return self.git("rev-parse", "HEAD")

    def arguments(self, before, after, *options, repo=None):
        return ["--repo", str(self.repo if repo is None else repo),
                "--from", before, "--to", after, *options]

    def cli(self, *args):
        return subprocess.run([sys.executable, "-B", str(SCRIPT), *args], cwd=self.root,
                              capture_output=True, text=True, timeout=10, env=self.env)

    def invoke(self, before, after, *options, repo=None):
        return self.cli(*self.arguments(before, after, *options, repo=repo))

    def assert_report(self, result, code, *lines):
        # Exact output also pins the final summary and precludes extra diagnostics.
        self.assertEqual(result.returncode, code)
        self.assertEqual(result.stdout, "".join(line + "\n" for line in lines))
        self.assertEqual(result.stderr, "")

    def assert_usage(self, result):
        self.assertEqual(result.returncode, 2)
        self.assertEqual(result.stdout, "")
        self.assertTrue(result.stderr.startswith("usage:"))

    def test_c1_full_pass(self):
        # Equal JSON must pass despite formatting, key order and different commits.
        before = self.commit(b'{"name":"fixture","hours":[],"notice":{"b":2,"a":1}}')
        after = self.commit(b'{ "notice": {"a":1.0,"b":2}, "hours": [], "name": "fixture" }')
        self.assert_report(self.invoke(before[:7], after), 0, PASS)

    def test_c2_1_unsafe_repo(self):
        # is_dir alone follows a symlink to an otherwise valid clone.
        sha = self.commit({})
        alias = self.root / "alias"
        alias.symlink_to(self.repo, target_is_directory=True)
        for repo in (alias, self.store, self.root / "missing"):
            with self.subTest(kind=repo.name):
                self.assert_report(self.invoke(sha, sha, repo=repo), 1, "FAIL unsafe-repo", FAIL)

    def test_c2_2_not_a_repo(self):
        # A directory isn't necessarily a Git repo.
        ordinary = self.root / "ordinary"
        ordinary.mkdir()
        self.assert_report(self.invoke("1111111", "2222222", repo=ordinary), 1,
                           "FAIL not-a-repo", FAIL)

    def test_c2_3_bad_commit(self):
        # Verifying just one revision or accepting a blob as an endpoint is unsafe.
        sha = self.commit({})
        blob = self.git("rev-parse", f"HEAD:{STORE_PATH}")
        unknown = "0" * 40
        for before, after, sides in (
            (unknown, sha, ("from",)), (sha, blob, ("to",)), (blob, unknown, ("from", "to")),
        ):
            with self.subTest(sides=sides):
                self.assert_report(self.invoke(before, after), 1,
                                   *(f"FAIL bad-commit {side}" for side in sides), FAIL)

    def test_c2_4_not_ancestor(self):
        # Reversing a range must not turn the requested check into a different comparison.
        older = self.commit({})
        newer = self.commit({"notice": "fixture"})
        self.assert_report(self.invoke(newer, older), 1, "FAIL not-ancestor", FAIL)

    def test_c2_5_git_error(self):
        # A failed show after a successful presence check isn't a missing or invalid file.
        sha = self.commit({})
        spec = importlib.util.spec_from_file_location("content_store_diff", SCRIPT)
        assert spec is not None and spec.loader is not None
        module = importlib.util.module_from_spec(spec)
        with patch.object(sys, "path", sys.path.copy()):
            spec.loader.exec_module(module)
        real_run = subprocess.run
        for command in ("show", "merge-base"):
            with self.subTest(command=command):
                def fail_selected(argv, **kwargs):
                    if argv[3] == command and (command != "show" or not replies):
                        replies.append(argv[3])
                        return subprocess.CompletedProcess(argv, 128, b"", os.fsencode(self.repo))
                    return real_run(argv, **kwargs)

                replies = []
                stdout, stderr = io.StringIO(), io.StringIO()
                with (patch.dict(os.environ, self.env, clear=True),
                      patch.object(module.subprocess, "run", side_effect=fail_selected),
                      redirect_stdout(stdout), redirect_stderr(stderr)):
                    code = module.main(self.arguments(sha, sha))
                self.assertEqual(replies, [command])
                result = subprocess.CompletedProcess([], code, stdout.getvalue(), stderr.getvalue())
                self.assert_report(result, 1, "FAIL git-error", FAIL)

    def test_c2_6_store_absent(self):
        # A checkout file cannot substitute for a missing commit blob.
        first = self.commit()
        present = self.commit({})
        self.git("read-tree", "--empty")  # Stage a missing file; keep the checkout file.
        last = self.commit()
        for before, after, sides in (
            (first, present, ("from",)), (present, last, ("to",)), (first, last, ("from", "to")),
        ):
            with self.subTest(sides=sides):
                self.assert_report(self.invoke(before, after), 1,
                                   *(f"FAIL store-absent {side}" for side in sides), FAIL)

    def test_c2_7_bad_json(self):
        # A last-wins decoder, permissive constants or implicit decoding could accept these.
        for raw in (b'{"name":', b'{"name":"\xff"}', b'[]', b'{"x":NaN}',
                    b'{"name":"a","name":"b"}', b'{"x":{"key":1,"\\u006bey":2}}'):
            with self.subTest(raw=raw):
                good = self.commit({})
                bad = self.commit(raw)
                fixed = self.commit({})
                self.assert_report(self.invoke(good, bad), 1, "FAIL bad-json to", FAIL)
                self.assert_report(self.invoke(bad, fixed), 1, "FAIL bad-json from", FAIL)

    def test_c2_8_store_fact_changed(self):
        # Check all five facts, including a removed key and an added null.
        before = self.commit({"name": "First", "streetAddress": "Address A", "town": "Town A",
                              "hours": ["Fixture A"]})
        after = self.commit({"name": "Second", "streetAddress": "Address B", "town": "Town B",
                             "phone": None})
        self.assert_report(self.invoke(before, after, "--allow", "town"), 1,
                           "fact-changed name", "fact-changed streetAddress", "allowed town",
                           "fact-changed hours", "fact-changed phone", "FAIL store-fact-changed 4", FAIL)

    def test_c3_usage_exit_2(self):
        # Argparse must reject aliases, revision expressions and out-of-range lengths.
        for arguments in (
            (), self.arguments("1234567", "abcdef0", "--unexpected"),
            ("--repo", str(self.repo), "--from", "-1234567", "--to", "abcdef0"),
            *[self.arguments(rev, "abcdef0") for rev in
              ("HEAD", "ABCDEF0", "123456", "1" * 41, "1234567^", "1234567\n")],
            self.arguments("1234567", "HEAD"),
        ):
            with self.subTest(arguments=arguments):
                self.assert_usage(self.cli(*arguments))

    def test_c4_read_only(self):
        # A checkout-based comparison could overwrite the dirty file or modify .git.
        before = self.commit({"name": "fixture"})
        after = self.commit({"name": "fixture", "notice": "fixture"})
        self.store.write_bytes(b"not the committed endpoint")

        def snapshot():
            return {path.relative_to(self.root): (path.stat().st_mtime_ns,
                    path.read_bytes() if path.is_file() else None)
                    for path in (self.root, *self.root.rglob("*"))}

        saved = snapshot()
        self.assert_report(self.invoke(before, after), 0, "changed notice", PASS)
        self.assertEqual(snapshot(), saved)

    def test_c5_no_private_values(self):
        # Diff values, parser errors, and raw Git diagnostics must not reach either stream.
        document = {"streetAddress": "fixture-street-marker", "town": "fixture-town-marker",
                    "phone": "fixture-phone-marker", "hours": ["fixture-hours-marker"]}
        canaries = (document["streetAddress"], document["town"], document["phone"],
                    *document["hours"], str(self.root), str(self.repo), str(self.store))
        before = self.commit(document)
        after = self.commit({})
        result = self.invoke(before, after)
        self.assert_report(result, 1, "fact-changed streetAddress", "fact-changed town",
                           "fact-changed hours", "fact-changed phone", "FAIL store-fact-changed 4", FAIL)
        g1_failure = self.invoke(before, after, repo=self.root)
        self.assert_report(g1_failure, 1, "FAIL not-a-repo", FAIL)
        usage = self.invoke(before, after, f"--unknown={self.repo}", "--allow", document["phone"])
        self.assert_usage(usage)
        for output in (result, g1_failure, usage):
            for canary in canaries:
                self.assertNotIn(canary, output.stdout + output.stderr)

    def test_c6_endpoint_rule(self):
        # Scanning intermediate commits would flag the transient phone change.
        before = self.commit({"phone": "fixture-original"})
        self.commit({"phone": "fixture-transient"})
        after = self.commit({"phone": "fixture-original"})
        self.assert_report(self.invoke(before, after), 0, PASS)
        help_result = self.cli("--help")
        self.assertEqual(help_result.returncode, 0)
        self.assertIn("a value changed and changed back is not reported", help_result.stdout)

    def test_c7_other_keys_info(self):
        # A fact-only comparator misses key changes; a flat diff may count them as findings.
        before = self.commit({"name": "fixture", "retired": None, "specials": [True]})
        after = self.commit({"specials": [1], "name": "fixture", "notice": "fixture", "extra": None})
        self.assert_report(self.invoke(before, after), 0, "changed extra", "changed notice",
                           "changed retired", "changed specials", PASS)

    def test_c8_allow_field(self):
        # One or multiple specific exceptions are allowed; an informational key is not.
        before = self.commit({"hours": ["Fixture A"], "phone": "fixture-a"})
        hours_only = self.commit({"hours": ["Fixture B"], "phone": "fixture-a"})
        both = self.commit({"hours": ["Fixture B"], "phone": "fixture-b"})
        self.assert_report(self.invoke(before, hours_only, "--allow", "hours"), 0, "allowed hours", PASS)
        self.assert_report(self.invoke(before, both, "--allow", "hours", "--allow", "phone"),
                           0, "allowed hours", "allowed phone", PASS)
        self.assert_usage(self.invoke(before, hours_only, "--allow", "intro"))


if __name__ == "__main__":
    unittest.main()
