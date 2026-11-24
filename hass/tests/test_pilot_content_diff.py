"""Exercise the pilot report against tiny, offline Git histories."""

import contextlib
import importlib.util
import io
import json
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest


SCRIPT = Path(__file__).resolve().parents[2] / "scripts/hass/pilot_content_diff.py"
CATALOG = "hass/content/products.json"
PASS = "PASS pilot_content_diff"
FAIL = "FAIL pilot_content_diff"


class PilotContentDiffTests(unittest.TestCase):
    def setUp(self):
        self.root = Path(self.enterContext(tempfile.TemporaryDirectory()))
        self.repo = self.root / "synthetic writer"
        self.repo.mkdir()
        self.catalog = self.repo / CATALOG
        self.catalog.parent.mkdir(parents=True)
        self.git("init", "-q", "--object-format=sha1")
        self.empty = self.commit_raw()

    def git(self, *args):
        result = subprocess.run(
            ["git", "-C", str(self.repo), "-c", "user.name=Fixture",
             "-c", "user.email=fixture@example.invalid", "-c", "commit.gpgsign=false",
             "-c", "tag.gpgsign=false", "-c", f"core.hooksPath={self.root / 'no-hooks'}", *args],
            check=True, capture_output=True, text=True, timeout=10,
        )
        return result.stdout.strip()

    def commit_raw(self, raw=None):
        if raw is not None:
            self.catalog.write_bytes(raw)
            self.git("add", "--", CATALOG)
        self.git("commit", "-qm", "fixture", "--allow-empty")
        return self.git("rev-parse", "HEAD")

    def commit(self, *products):
        return self.commit_raw(json.dumps({"products": products}).encode())

    def invoke(self, old, new, *flags, repo=None):
        return subprocess.run(
            [sys.executable, "-B", str(SCRIPT), "--repo", str(repo or self.repo),
             f"--from={old}", f"--to={new}", *flags],
            cwd=self.root, capture_output=True, text=True, timeout=10,
        )

    def assert_result(self, result, last, *lines):
        self.assertEqual(result.returncode, 0 if last == PASS else 1, result.stderr)
        self.assertEqual(result.stdout, "\n".join((*lines, last, "")))
        self.assertEqual(result.stderr, "")

    def test_c1_full_pass(self):
        # Working-tree reads, row-order diffs, unsorted output, and missed field removals fail.
        old = self.commit(
            {"id": "remove-z"}, {"id": "change-z", "flag": True},
            {"id": "same", "detail": {"left": 1, "right": 2}},
            {"id": "remove-a"}, {"id": "change-a", "zeta": "before", "beta": None},
        )
        new = self.commit(
            {"id": "add-z"}, {"id": "change-z", "flag": 1},
            {"id": "change-a", "zeta": "after", "alpha": None}, {"id": "add-a"},
            {"id": "same", "detail": {"right": 2, "left": 1}},
        )
        self.catalog.write_bytes(b"not the committed catalog")
        self.assert_result(
            self.invoke(old, new, "--expect-added", "2"), PASS,
            "added add-a", "added add-z", "removed remove-a", "removed remove-z",
            "changed change-a alpha beta zeta", "changed change-z flag", "added-total 2",
        )

    def test_c2_1_not_git(self):
        # The repo finding takes precedence over unusable commit arguments.
        self.assert_result(self.invoke("bad", "bad", repo=self.root), FAIL, "FAIL not-git")

    def test_c2_2_bad_commit(self):
        # Refs, uppercase, short hashes, unknown hashes and non-commit objects are not SHAs here.
        good = self.commit()
        blob = self.git("rev-parse", f"HEAD:{CATALOG}")
        self.git("tag", "-a", "fixture", "-m", "fixture", good)
        tag = self.git("rev-parse", "refs/tags/fixture")
        for bad in ("HEAD", "A" * 40, good[:12], "0" * 40, blob, tag):
            with self.subTest(bad=bad):
                self.assert_result(self.invoke(bad, good), FAIL, "FAIL bad-commit from")
                self.assert_result(self.invoke(good, bad), FAIL, "FAIL bad-commit to")
        self.assert_result(self.invoke("HEAD", blob), FAIL, "FAIL bad-commit from", "FAIL bad-commit to")

    def test_c2_3_not_ancestor(self):
        # Sharing a parent is not enough, and direction matters even on one branch.
        parent = self.commit()
        child = self.commit({"id": "fixture-left"})
        sibling = self.git("commit-tree", f"{parent}^{{tree}}", "-p", parent, "-m", "sibling")
        for left, right in ((child, sibling), (child, parent)):
            self.assert_result(self.invoke(left, right), FAIL, "FAIL not-ancestor")

    def test_c2_4_no_content(self):
        # Do not default a missing blob to an empty product list or consult current files.
        present = self.commit()
        absent = self.git("commit-tree", f"{self.empty}^{{tree}}", "-p", present, "-m", "absent")
        self.assert_result(self.invoke(self.empty, present), FAIL, "FAIL no-content from")
        self.assert_result(self.invoke(present, absent), FAIL, "FAIL no-content to")

    def test_c2_5_bad_content(self):
        # A permissive loader or dict overwrite could turn malformed input into valid findings.
        good = self.commit()
        for raw in (
            b"{invalid", b"\xff", b"[]", b"{}", b'{"products":null}',
            b'{"products":{}}', b'{"products":["fixture"]}', b'{"products":[{}]}',
            b'{"products":[{"id":1}]}', b'{"products":[{"id":"x"},{"id":"x"}]}',
            b'{"products":[{"id":"x","field":NaN}]}',
        ):
            with self.subTest(raw=raw):
                bad = self.commit_raw(raw)
                self.assert_result(self.invoke(good, bad), FAIL, "FAIL bad-content to")
        valid_again = self.commit()
        self.assert_result(self.invoke(bad, valid_again), FAIL, "FAIL bad-content from")
        self.assert_result(self.invoke(self.empty, bad), FAIL, "FAIL no-content from", "FAIL bad-content to")

    def test_c2_6_added_count(self):
        # Compare to additions, not total products, and report the actual count.
        old = self.commit({"id": "existing-fixture"})
        new = self.commit({"id": "new-fixture"}, {"id": "existing-fixture"})
        self.assert_result(self.invoke(old, new, "--expect-added", "2"), FAIL,
                           "added new-fixture", "added-total 1", "FAIL added-count 1")

    def test_exact_catalog_effect(self):
        # A matching added count can hide the wrong ID or a collateral edit.
        # Undo must hide this formerly active row, not merely add zero rows.
        other = {"id": "existing-fixture", "status": "active", "detail": {"label": "same"}}
        edited = {**other, "detail": {"label": "changed"}}
        target = {"id": "pilot-fixture", "status": "active", "available": "yes"}
        # history.revert retains a new product as hidden and drops its stock fields;
        # see the applied writer fixture in test_undo_new_item.
        held = {"id": target["id"], "status": "hidden"}
        old = self.commit(other)
        forward = ("--expect-product", "forward", target["id"])
        inverse = ("--expect-product", "inverse", target["id"])
        wrong = self.commit(other, {**target, "id": "wrong-fixture"})
        collateral = self.commit(edited, target)
        for end, line in ((wrong, "added wrong-fixture"), (collateral, "added pilot-fixture")):
            with self.subTest(diagnostic=line):
                legacy = self.invoke(old, end, "--expect-added", "1")
                self.assertEqual(legacy.returncode, 0, legacy.stderr)
                self.assertIn(line, legacy.stdout)
                self.assertIn("added-total 1", legacy.stdout)
        new = self.commit(target, other)  # catalog ordering does not matter
        undone = self.commit(other, held)
        self.assert_result(self.invoke(old, new, *forward), PASS, "added pilot-fixture", "added-total 1")
        self.assert_result(self.invoke(new, undone, *inverse), PASS,
                           "changed pilot-fixture available status", "added-total 0")
        for label, start, end, flags, reason in (
            ("wrong forward ID", old, wrong, forward, "expected-product-forward"),
            ("edited another on post", old, collateral, forward, "other-products-changed"),
            ("not active on post", old, undone, forward, "expected-product-forward"),
            ("already present", collateral, new, forward, "expected-product-forward"),
            ("still active", new, self.commit({**other, "status": "hidden"}, target),
             inverse, "expected-product-inverse"),
            ("edited another on undo", new, self.commit(edited, held), inverse, "other-products-changed"),
            ("lost another on undo", new, self.commit(held), inverse, "other-products-changed"),
            ("added another on undo", new, self.commit(other, held, {"id": "extra-fixture"}),
             inverse, "other-products-changed"),
            ("not the writer undo form", new, self.commit(other), inverse, "expected-product-inverse"),
            # Contract: the inverse is the writer's exact form (the forward record, hidden, minus
            # available/available_on). Bug caught: any hidden row passed, so an altered
            # description or a retained stock word went unnoticed.
            ("undo altered another field", new, self.commit(other, {**held, "description": "edited"}),
             inverse, "expected-product-inverse"),
            ("undo kept the stock word", new, self.commit(other, {**held, "available": "yes"}),
             inverse, "expected-product-inverse"),
            ("undo dropped another field", self.commit(other, {**target, "name": "Fixture"}),
             self.commit(other, held), inverse, "expected-product-inverse"),
            ("already hidden", undone, undone, inverse, "expected-product-inverse"),
            ("missing target in both", old, old, inverse, "expected-product-inverse"),
        ):
            with self.subTest(case=label):
                result = self.invoke(start, end, *flags)
                self.assertEqual(result.returncode, 1, result.stderr)
                lines = result.stdout.splitlines()
                self.assertIn(f"FAIL {reason}", lines)
                self.assertEqual(lines[-1], FAIL)
                self.assertEqual(result.stderr, "")
        self.assert_result(self.invoke(undone, new, *inverse), FAIL, "FAIL not-ancestor")

    def test_c3_usage_exit_2(self):
        # Named findings must not absorb argparse failures or echo rejected values.
        spec = importlib.util.spec_from_file_location("pilot_content_diff", SCRIPT)
        assert spec is not None and spec.loader is not None
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)
        valid = ["--repo", str(self.repo), "--from", self.empty, "--to", self.empty]
        for args in (valid[:-2], valid + ["--unexpected", str(self.root)],
                     valid + ["--expect-added", str(self.root)],
                     valid + ["--expect-product", str(self.root), "fixture"],
                     valid + ["--expect-product", "forward"]):
            with self.subTest(args=args[-2:]):
                stdout, stderr = io.StringIO(), io.StringIO()
                with contextlib.redirect_stdout(stdout), contextlib.redirect_stderr(stderr):
                    with self.assertRaises(SystemExit) as raised:
                        module.main(args)
                self.assertEqual(raised.exception.code, 2)
                self.assertEqual(stdout.getvalue(), "")
                self.assertIn("usage:", stderr.getvalue())
                self.assertNotIn(str(self.root), stderr.getvalue())

    def test_c4_read_only(self):
        # A checkout, refresh, or output artifact changes the snapshot, even under .git.
        old = self.commit()
        new = self.commit({"id": "new-fixture"})
        self.catalog.write_bytes(b"dirty writer input")

        def snapshot():
            return {
                path.relative_to(self.root): None if path.is_dir() else
                (path.stat().st_mtime_ns, path.read_bytes())
                for path in self.root.rglob("*")
            }

        before = snapshot()
        self.assert_result(self.invoke(old, new), PASS, "added new-fixture", "added-total 1")
        self.assertEqual(snapshot(), before)

    def test_c5_no_private_values(self):
        # Both success and validation errors must suppress source values and Git diagnostics.
        private = {"message": "fixture-only-message-marker", "chat": "fixture-chat-marker",
                   "sender": "fixture-sender-marker", "externalId": "fixture-full-id-marker",
                   "digest": "f0" * 32, "path": str(self.repo)}
        old = self.commit({"id": "public-fixture", **private})
        new = self.commit({"id": "public-fixture"})
        malformed = self.commit_raw(json.dumps({"products": [private]}).encode() + b"!")
        changed = self.invoke(old, new)
        wrong_target = self.invoke(old, new, "--expect-product", "forward", str(self.root))
        invalid = self.invoke(new, malformed)
        no_repo = self.invoke(old, new, repo=self.root / "synthetic absent checkout")
        self.assert_result(changed, PASS, "changed public-fixture chat digest externalId message path sender",
                           "added-total 0")
        self.assert_result(invalid, FAIL, "FAIL bad-content to")
        self.assert_result(no_repo, FAIL, "FAIL not-git")
        self.assert_result(wrong_target, FAIL, "changed public-fixture chat digest externalId message path sender",
                           "added-total 0", "FAIL expected-product-forward", "FAIL other-products-changed")
        for result in (changed, wrong_target, invalid, no_repo):
            for canary in (*private.values(), str(self.root), old, new, malformed):
                self.assertNotIn(canary, result.stdout + result.stderr)

    def test_c6_removed_is_informational(self):
        # A removal alone is a pass; it never offsets or fails an added-count check.
        old = self.commit({"id": "removed-fixture"})
        new = self.commit()
        for flags in ((), ("--expect-added", "0")):
            self.assert_result(self.invoke(old, new, *flags), PASS,
                               "removed removed-fixture", "added-total 0")
        self.assert_result(self.invoke(old, new, "--expect-added", "1"), FAIL,
                           "removed removed-fixture", "added-total 0", "FAIL added-count 0")
