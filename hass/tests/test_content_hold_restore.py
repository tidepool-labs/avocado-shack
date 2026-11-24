"""Offline contract tests for the held-product endpoint report."""

from contextlib import redirect_stderr, redirect_stdout
import importlib.util
import io
import json
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest
from unittest import mock


SCRIPT = Path(__file__).resolve().parents[2] / "scripts/hass/content_hold_restore.py"
PRODUCTS = "hass/content/products.json"
PASS = "PASS content_hold_restore"
FAIL = "FAIL content_hold_restore"


def product(pid, status, **fields):
    return {"id": pid, "status": status, **fields}


def snapshot(root):
    # Include directory entries and mtimes, not just the checked-out content.
    return {
        path.relative_to(root): (path.stat().st_mtime_ns,
                                 path.read_bytes() if path.is_file() else None)
        for path in (root, *root.rglob("*"))
    }


class ContentHoldRestoreTests(unittest.TestCase):
    def setUp(self):
        temporary = tempfile.TemporaryDirectory()
        self.addCleanup(temporary.cleanup)
        self.root = Path(temporary.name).resolve()
        self.repo = self.root / "fixture-repo"
        self.repo.mkdir()
        self.git("init", "--quiet", "--template=")
        self.git("config", "user.name", "Fixture")
        self.git("config", "user.email", "fixture@example.invalid")
        self.git("config", "commit.gpgsign", "false")
        self.git("config", "core.hooksPath", str(self.root / "no-hooks"))
        self.file = self.repo / PRODUCTS
        self.file.parent.mkdir(parents=True)

    def git(self, *args):
        return subprocess.run(["git", "-C", str(self.repo), *args], check=True,
                              text=True, capture_output=True, timeout=10).stdout.strip()

    def commit(self, rows=None, *, raw=None):
        if rows is not None:
            raw = json.dumps({"products": rows}).encode("utf-8")
        if raw is not None:
            self.file.write_bytes(raw)
            self.git("add", "--", PRODUCTS)
        self.git("commit", "--quiet", "--allow-empty", "-m", "Synthetic snapshot")
        return self.git("rev-parse", "HEAD")

    def args(self, before, after, repo=None):
        return ["--repo", str(self.repo if repo is None else repo),
                "--from", before, "--to", after]

    def cli(self, *args):
        return subprocess.run([sys.executable, "-B", str(SCRIPT), *args], cwd=self.root,
                              capture_output=True, text=True, timeout=10)

    def run_report(self, before, after, repo=None):
        return self.cli(*self.args(before, after, repo))

    def assert_pass(self, result):
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(result.stderr, "")
        lines = result.stdout.splitlines()
        self.assertTrue(lines)
        self.assertEqual(lines[-1], PASS)
        self.assertFalse(any(line.startswith("FAIL ") for line in lines))
        return lines

    def assert_fail(self, result, *reasons):
        self.assertEqual(result.returncode, 1, result.stderr)
        self.assertEqual(result.stderr, "")
        lines = result.stdout.splitlines()
        self.assertTrue(lines)
        self.assertEqual(lines[-1], FAIL)
        self.assertEqual([line for line in lines[:-1] if line.startswith("FAIL ")],
                         [f"FAIL {reason}" for reason in reasons])
        return lines

    def test_c1_full_pass(self):
        # Counting malformed rows as held or misclassifying drops/new holds breaks the report.
        before = self.commit([product("kept", "held"), product("dropped", "held"),
                              product("newly", "active"), None, {"status": "held"}])
        after = self.commit([product("newly", "held"), product("kept", "held"),
                             product(4, "held")])
        self.assertEqual(self.assert_pass(self.run_report(before[:12], after)), [
            "held-from 2", "held-to 2", "note hold-dropped 1", "note newly-held 1",
            "note malformed 3", "note invalid-id 0", PASS,
        ])

    def test_c2_1_unsafe_repo(self):
        # A directory check alone follows symlinks into otherwise valid repositories.
        rev = self.commit([])
        alias = self.root / "alias"
        alias.symlink_to(self.repo, target_is_directory=True)
        for repo in (alias, f"{alias}/", self.file, self.root / "missing"):
            with self.subTest(repo=repo):
                self.assert_fail(self.run_report(rev, rev, repo), "unsafe-repo")

    def test_c2_2_not_a_repo(self):
        # A real directory that is not a repo must not be reported as a bad revision.
        self.assert_fail(self.run_report("123abcd", "123abcd", self.root), "not-a-repo")

    def test_c2_3_bad_commit(self):
        # A blob resolves as an object, not a commit; two bad REVs need two findings.
        rev = self.commit([])
        blob = self.git("hash-object", PRODUCTS)
        missing = "0" * 40
        for before, after, reasons in (
            (missing, rev, ("bad-commit from",)),
            (rev, blob, ("bad-commit to",)),
            (blob, missing, ("bad-commit from", "bad-commit to")),
        ):
            with self.subTest(reasons=reasons):
                self.assert_fail(self.run_report(before, after), *reasons)

    def test_c2_4_not_ancestor(self):
        # Two valid objects alone do not make a forward range.
        early = self.commit([])
        late = self.commit([product("sample", "held")])
        self.assert_fail(self.run_report(late, early), "not-ancestor")

    def test_c2_5_git_error(self):
        # A successful cat-file probe does not make a later show failure "absent".
        before = self.commit([])
        after = self.commit([])
        spec = importlib.util.spec_from_file_location("content_hold_restore", SCRIPT)
        assert spec is not None and spec.loader is not None
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)
        real_run = subprocess.run

        def fail_show(args, **kwargs):
            if args[3] == "show":
                return subprocess.CompletedProcess(args, 128, b"", str(self.repo).encode())
            return real_run(args, **kwargs)

        out, err = io.StringIO(), io.StringIO()
        with mock.patch.object(module.subprocess, "run", side_effect=fail_show), \
                redirect_stdout(out), redirect_stderr(err):
            code = module.main(self.args(before, after))
        self.assert_fail(subprocess.CompletedProcess([], code, out.getvalue(), err.getvalue()),
                         "git-error")

    def test_c2_6_products_absent(self):
        # Absence on either side cannot be treated as an empty catalog.
        empty = self.commit()
        present = self.commit([])
        empty_tree = self.git("rev-parse", f"{empty}^{{tree}}")
        absent_again = self.git("commit-tree", empty_tree, "-p", present, "-m", "Empty snapshot")
        for before, after, reasons in (
            (empty, present, ("products-absent from",)),
            (present, absent_again, ("products-absent to",)),
            (empty, empty, ("products-absent from", "products-absent to")),
        ):
            with self.subTest(reasons=reasons):
                self.assert_fail(self.run_report(before, after), *reasons)

    def test_c2_7_bad_json(self):
        # Default parsing accepts duplicate keys (even escaped aliases) and NaN.
        good = self.commit([])
        for raw in (b'{"products":["\xff"]}', b'{', b'{}', b'[]', b'{"products":{}}',
                    rb'{"products":[{"status":"held","st\u0061tus":"active"}]}',
                    b'{"products":[NaN]}'):
            with self.subTest(raw=raw):
                bad = self.commit(raw=raw)
                self.assert_fail(self.run_report(good, bad), "bad-json to")
                good = self.commit([])
                self.assert_fail(self.run_report(bad, good), "bad-json from")

    def test_c2_8_restored_from_hold(self):
        # Use two restores out of order to catch a missing or repeated finding and bad sort.
        before = self.commit([product("z-sample", "held"), product("a-sample", "held")])
        after = self.commit([product("z-sample", "active"), product("a-sample", "active")])
        self.assertEqual(self.assert_fail(self.run_report(before, after), "restored-from-hold 2"), [
            "held-from 2", "held-to 0", "restored a-sample active", "restored z-sample active",
            "note hold-dropped 0", "note newly-held 0", "note malformed 0", "note invalid-id 0",
            "FAIL restored-from-hold 2", FAIL,
        ])

    def test_c3_usage_exit_2(self):
        # Branch names, option-looking strings and malformed hashes must fail before git.
        valid = self.args("123abcd", "123abcd")
        for args in (valid[:-2], valid[2:], valid[:2] + valid[4:], valid + ["--unknown"],
                     *[valid[:-1] + [rev] for rev in ("HEAD", "123ABCd", "123abc", "a" * 41,
                                                    "123abcd\n", "-123abcd")],
                     valid[:3] + ["HEAD"] + valid[4:]):
            with self.subTest(args=args):
                result = self.cli(*args)
                self.assertEqual(result.returncode, 2)
                self.assertEqual(result.stdout, "")  # No last stdout line on usage errors.
                self.assertTrue(result.stderr.startswith("usage:"))
                self.assertIn(": error:", result.stderr.splitlines()[-1])

    def test_c4_read_only(self):
        # Checkout-based comparison can disturb dirty bytes, the index or transient entries.
        before = self.commit([product("sample", "held")])
        after = self.commit([product("sample", "hidden")])
        self.file.write_bytes(b"dirty worktree fixture")
        original = snapshot(self.root)
        lines = self.assert_pass(self.run_report(before, after))
        self.assertIn("held-to-hidden sample", lines)
        self.assertEqual(snapshot(self.root), original)

    def test_c5_no_private_values(self):
        # A debug dump of either endpoint or unsanitized Git errors leaks private data.
        hold = {key: f"SYNTHETIC {key.upper()} CANARY"
                for key in ("reason", "source", "evidence", "record")}
        names = ["SYNTHETIC HELD NAME", "SYNTHETIC HELD DESCRIPTION",
                 "SYNTHETIC ACTIVE NAME", "SYNTHETIC ACTIVE DESCRIPTION"]
        before = self.commit([product("sample", "held", hold=hold,
                                      name=names[0], description=names[1])])
        after = self.commit([product("sample", "active", name=names[2], description=names[3])])
        restored = self.run_report(before, after)
        self.assertIn("restored sample active", self.assert_fail(restored, "restored-from-hold 1"))
        non_repo = self.run_report(before, after, self.root)
        self.assert_fail(non_repo, "not-a-repo")
        for result in (restored, non_repo):
            for canary in (*hold.values(), *names, str(self.root), str(self.repo), str(self.file)):
                self.assertNotIn(canary, result.stdout)
                self.assertNotIn(canary, result.stderr)

    def test_c6_endpoint_rule(self):
        # A history walk would report the intermediate restore even though it was reverted.
        held = self.commit([product("sample", "held")])
        self.commit([product("sample", "active")])
        held_again = self.commit([product("sample", "held")])
        lines = self.assert_pass(self.run_report(held, held_again))
        self.assertEqual(lines[:2], ["held-from 1", "held-to 1"])
        self.assertFalse(any(line.startswith("restored ") for line in lines))

    def test_c7_held_to_hidden(self):
        # Leaving held for hidden is reportable, but not a return to active listings.
        before = self.commit([product("z-sample", "held"), product("a-sample", "held")])
        after = self.commit([product("z-sample", "hidden"), product("a-sample", "hidden")])
        lines = self.assert_pass(self.run_report(before, after))
        self.assertEqual(lines[:4], ["held-from 2", "held-to 0", "held-to-hidden a-sample",
                                     "held-to-hidden z-sample"])
        self.assertFalse(any(line.startswith("restored ") for line in lines))

    def test_c8_same_commit(self):
        # A strict-ancestor check would reject identical endpoints.
        rev = self.commit([product("sample", "held")])
        lines = self.assert_pass(self.run_report(rev, rev))
        self.assertEqual(lines[:2], ["held-from 1", "held-to 1"])
        self.assertFalse(any(line.startswith("restored ") for line in lines))

    def test_c9_invalid_id_not_printed(self):
        # Accepting arbitrary strings would expose the planted name and report a fake restore.
        canary = "SYNTHETIC PRODUCT NAME CANARY"
        before = self.commit([product(canary, "held")])
        after = self.commit([product(canary, "active")])
        result = self.run_report(before, after)
        self.assertEqual(self.assert_pass(result), [
            "held-from 0", "held-to 0", "note hold-dropped 0", "note newly-held 0",
            "note malformed 0", "note invalid-id 2", PASS,
        ])
        self.assertNotIn(canary, result.stdout)
        self.assertNotIn(canary, result.stderr)
