"""Offline contract tests of the pilot publish footprint CLI."""

from contextlib import redirect_stdout
import importlib.util
import io
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import patch


SCRIPT = Path(__file__).resolve().parents[2] / "scripts/hass/npp_publish_footprint.py"
SPEC = importlib.util.spec_from_file_location("npp_publish_footprint", SCRIPT)
assert SPEC is not None and SPEC.loader is not None
CLI = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(CLI)
PASS = "PASS npp_publish_footprint"
FAIL = "FAIL npp_publish_footprint"
PRODUCTS = '{"products": []}\n'
LISTING = '{"products": [{"image": "assets/products/photo-fixture.webp"}]}\n'
PATTERNS = "# expected publish paths\n\nproducts.json\nassets/products/photo-*.webp\n"
OTHER = "notes.txt"
BASE_NOTES = "original fixture notes\n"


class PublishFootprintTests(unittest.TestCase):
    def setUp(self):
        temporary = tempfile.TemporaryDirectory()
        self.addCleanup(temporary.cleanup)
        self.root = Path(temporary.name).resolve()
        self.repo = self.root / "repo-canary"
        self.repo.mkdir()
        self.allow = self.root / "allow-canary.txt"
        self.allow.write_text(PATTERNS, encoding="utf-8")
        self.env = {key: value for key, value in os.environ.items() if not key.startswith("GIT_")}
        self.env.update(GIT_CEILING_DIRECTORIES=str(self.root), GIT_CONFIG_NOSYSTEM="1",
                        GIT_CONFIG_GLOBAL=os.devnull)
        self.git("init", "-q", "--template=", "-b", "main")
        self.write("products.json", PRODUCTS)
        self.write(OTHER, BASE_NOTES)
        self.before = self.commit("base")
        self.write("products.json", LISTING)
        self.write("assets/products/photo-fixture.webp", "fixture image bytes")
        # A parent-like message line is not part of the parent list.
        self.after = self.commit("publish\n\nparent " + self.before)

    def write(self, name, text):
        target = self.repo / name
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(text, encoding="utf-8")

    def git(self, *args, author=("t", "t@example.invalid")):
        return subprocess.run(
            ["git", "-C", str(self.repo), "-c", f"user.name={author[0]}",
             "-c", f"user.email={author[1]}", *args], env=self.env,
            capture_output=True, check=True, timeout=10,
        ).stdout

    def commit(self, message, author=("t", "t@example.invalid")):
        self.git("add", "--all")
        self.git("commit", "-q", "--no-gpg-sign", "--allow-empty", "-m", message, author=author)
        return self.git("rev-parse", "HEAD").decode("ascii").strip()

    def args(self, **options):
        values = {"repo": self.repo, "from": self.before, "to": self.after, "allow": self.allow}
        values.update(options)
        return [f"--{name}={value}" for name, value in values.items()]

    def invoke(self, *argv):
        return subprocess.run([sys.executable, "-B", str(SCRIPT), *argv],
                              cwd=self.root, env=self.env, capture_output=True, text=True,
                              check=False, timeout=15)

    def main(self, **options):
        stdout = io.StringIO()
        with patch.dict(os.environ, self.env, clear=True), redirect_stdout(stdout):
            code = CLI.main(self.args(**options))
        return subprocess.CompletedProcess([], code, stdout.getvalue(), "")

    def assert_pass(self, result):
        self.assertEqual(result.returncode, 0)
        self.assertEqual(result.stdout.splitlines()[-1:], [PASS])
        self.assertEqual(result.stderr, "")

    def assert_failure(self, result, reason):
        self.assertEqual(result.returncode, 1)
        lines = result.stdout.splitlines()
        self.assertEqual(lines[-1:], [FAIL])
        self.assertEqual([line for line in lines if line.startswith("FAIL ")],
                         [f"FAIL {reason}", FAIL])
        self.assertNotIn(PASS, lines)
        self.assertEqual(result.stderr, "")
        return lines

    def test_c1_full_pass(self):
        # Named revs must resolve before Git compares their SHAs; counts are sorted by status.
        result = self.invoke(*self.args(**{"from": "main^", "to": "main"}))
        self.assert_pass(result)
        self.assertEqual(result.stdout.splitlines(), ["changed 2", "status A 1", "status M 1", "allowed 2", PASS])

    def test_c2_1_not_a_repo(self):
        # A failed Git probe cannot be treated as an empty footprint, nor can a repo symlink pass.
        plain = self.root / "plain"
        plain.mkdir()
        alias = self.root / "repo-link"
        alias.symlink_to(self.repo, target_is_directory=True)
        for path in (self.root / "absent", alias, self.allow, plain):
            with self.subTest(path=path.name):
                self.assert_failure(self.invoke(*self.args(repo=path)), "not-a-repo")

    def test_c2_2_bad_rev(self):
        # Refuse unsafe revs even in --to before probing the repo; keep Git's resolution failure separate.
        for which in ("from", "to"):
            for rev in ("--version", "HEAD ^", "HEAD\u2003^", "HEAD\n^", "HEAD\x1f", "HEAD\x85"):
                with self.subTest(which=which, rev=rev), patch.object(CLI.subprocess, "run") as run:
                    self.assert_failure(self.main(**{which: rev}), f"bad-rev {which}")
                    run.assert_not_called()
            with self.subTest(which=which, rev="unresolved"):
                self.assert_failure(self.invoke(*self.args(**{which: "no-such-rev"})), f"bad-rev {which}")

    def test_c2_3_not_ancestor(self):
        # Reversing the same commit pair is not valid ancestry, not merely a multi-commit publish.
        result = self.invoke(*self.args(**{"from": self.after, "to": self.before}))
        self.assert_failure(result, "not-ancestor")

    def test_c2_4_git_error(self):
        # Inject failures at Git's boundary without a real 60-second wait or damaged .git directory.
        actual_run = subprocess.run
        faults = [
            (0, "timeout"), (1, "timeout"), (2, "timeout"),
            (3, "timeout"), (4, "timeout"), (5, "timeout"),
            (3, "exit"), (4, "exit"), (5, "exit"),
            (4, "invalid-parent"), (4, "missing-separator"),
        ]
        for stage, fault in faults:
            calls = []

            def git_with_fault(argv, **kwargs):
                calls.append(argv[3])
                if len(calls) - 1 != stage:
                    return actual_run(argv, **kwargs)
                if fault == "timeout":
                    raise subprocess.TimeoutExpired(argv, kwargs["timeout"])
                if fault == "exit":
                    return subprocess.CompletedProcess(argv, 128, b"")
                result = actual_run(argv, **kwargs)
                if fault == "invalid-parent":
                    result.stdout = result.stdout.replace(b"parent " + self.before.encode(), b"parent broken", 1)
                else:
                    result.stdout = result.stdout.partition(b"\n\n")[0]
                return result

            with self.subTest(stage=stage, fault=fault), patch.object(CLI.subprocess, "run", side_effect=git_with_fault):
                self.assertEqual(self.assert_failure(self.main(), "git-error"), ["FAIL git-error", FAIL])
                self.assertEqual(len(calls), stage + 1)

    def test_c2_5_bad_allow(self):
        # An empty or partly invalid policy must not silently become a valid policy.
        alias = self.root / "allow-link"
        alias.symlink_to(self.allow)
        for path in (self.root / "missing-allow", alias):
            with self.subTest(path=path.name):
                self.assert_failure(self.invoke(*self.args(allow=path)), "bad-allow")
        for raw in (b"# only a comment\n\n", b"products.json\n\xff", b"products.json\n/assets/*\n",
                    b"products.json\nassets/../*\n", b"products.json\nfoo\0bar\n"):
            with self.subTest(raw=raw):
                self.allow.write_bytes(raw)
                self.assert_failure(self.invoke(*self.args()), "bad-allow")

    def test_c2_6_no_change(self):
        # An empty but genuine child commit is not a clean publish.
        empty = self.commit("empty")
        result = self.invoke(*self.args(**{"from": self.after, "to": empty}))
        self.assertEqual(self.assert_failure(result, "no-change"), ["changed 0", "allowed 0", "FAIL no-change", FAIL])

    def test_c2_7_unexpected(self):
        # fnmatchcase must not broaden a pattern to allow a case-variant path.
        self.write("Products.json", LISTING)
        tip = self.commit("wrong case")
        result = self.invoke(*self.args(**{"from": self.after, "to": tip}))
        lines = self.assert_failure(result, "unexpected 1")
        self.assertEqual(lines[:3], ["changed 1", "status A 1", "allowed 0"])

    def test_c2_8_not_single_publish(self):
        # A reverted out-of-policy edit disappears from the endpoint diff, not from the history.
        self.write(OTHER, "transient change\n")
        self.commit("out of policy")
        self.write(OTHER, BASE_NOTES)
        restored = self.commit("restore")
        diff = self.git("diff", "--name-only", "-z", self.before, restored, "--")
        self.assertEqual(diff.split(b"\0"), [b"assets/products/photo-fixture.webp", b"products.json", b""])
        self.git("switch", "-q", "-c", "side", self.before)
        self.write("side.txt", "separate history\n")
        self.commit("side")
        self.git("switch", "-q", "main")
        self.git("merge", "-q", "--no-ff", "--no-edit", "side")
        merge = self.git("rev-parse", "HEAD").decode("ascii").strip()
        self.assertEqual(self.git("rev-parse", "HEAD^1").strip(), restored.encode("ascii"))
        for before, after in ((self.before, restored), (restored, merge), (self.after, self.after)):
            with self.subTest(before=before, after=after), patch.object(CLI.subprocess, "run", wraps=subprocess.run) as run:
                result = self.main(**{"from": before, "to": after})
                self.assertEqual(self.assert_failure(result, "not-single-publish"),
                                 ["FAIL not-single-publish", FAIL])
                self.assertNotIn("diff", [call.args[0][3] for call in run.call_args_list])

    def test_c3_usage_exit_2(self):
        # Argparse errors must not become findings or produce report output.
        args = self.args()
        for argv in (args[:-1], [*args, "--unknown"], [*args[:1], "--from", "--invalid", *args[2:]]):
            with self.subTest(argv=argv):
                result = self.invoke(*argv)
                self.assertEqual(result.returncode, 2)
                self.assertEqual(result.stdout, "")
                self.assertTrue(result.stderr.startswith("usage:"))

    def test_c4_read_only(self):
        # A worktree/index-based implementation could count this staged change or refresh .git/index.
        self.write(OTHER, "staged, not committed\n")
        self.git("add", OTHER)

        def snapshot():
            paths = [self.allow, self.repo, *self.repo.rglob("*")]
            return {p: (p.stat().st_mtime_ns, p.read_bytes() if p.is_file() else None) for p in paths}

        saved = snapshot()
        result = self.invoke(*self.args())
        self.assert_pass(result)
        self.assertEqual(result.stdout.splitlines()[0], "changed 2")
        self.assertEqual(snapshot(), saved)

    def test_c5_no_private_values(self):
        # Dumping cat-file output, a content diff, or raw diagnostics would disclose a canary.
        author = ("fixture author canary", "fixture-email-canary@example.invalid")
        content = "fixture content canary"
        self.write(OTHER, content)
        tip = self.commit("private fields fixture", author=author)
        finding = self.invoke(*self.args(**{"from": self.after, "to": tip}))
        self.assert_failure(finding, "unexpected 1")
        passing = self.invoke(*self.args())
        self.assert_pass(passing)
        not_repo = self.invoke(*self.args(repo=self.root))
        self.assert_failure(not_repo, "not-a-repo")
        usage = self.invoke(*self.args(), str(self.repo), str(self.allow))
        self.assertEqual((usage.returncode, usage.stdout), (2, ""))
        for result in (finding, passing, not_repo, usage):
            for canary in (str(self.root), str(self.repo), str(self.allow), *author, content):
                self.assertNotIn(canary, result.stdout + result.stderr)

    def test_c6_expected_footprint_pass(self):
        # The listing pair passes against its two patterns with no checkout at all.
        clone = self.root / "unpopulated"
        self.git("clone", "-q", "--no-checkout", "--local", str(self.repo), str(clone))
        self.assertFalse((clone / "products.json").exists())
        result = self.invoke(*self.args(repo=clone))
        self.assert_pass(result)
        self.assertEqual(result.stdout.splitlines(), ["changed 2", "status A 1", "status M 1", "allowed 2", PASS])
        self.assertFalse((clone / "products.json").exists())

    def test_c7_unexpected_listed(self):
        # A newline path must remain one JSON-escaped output line, with the modified status.
        name = "notes\nlog.txt"
        baseline = self.before
        self.git("switch", "-q", "-c", "new-line", baseline)
        self.write(name, "initial\n")
        before = self.commit("base with newline path")
        self.write("products.json", LISTING)
        self.write("assets/products/photo-fixture.webp", "fixture image bytes")
        self.write(name, "changed\n")
        after = self.commit("publish with out-of-policy change")
        result = self.invoke(*self.args(**{"from": before, "to": after}))
        self.assertEqual(self.assert_failure(result, "unexpected 1"), [
            "changed 3", "status A 1", "status M 2", "allowed 2",
            'unexpected M "notes\\nlog.txt"', "FAIL unexpected 1", FAIL,
        ])


if __name__ == "__main__":
    unittest.main()
