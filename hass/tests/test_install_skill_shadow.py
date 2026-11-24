"""Fixture-only contract tests for the offline skill-shadow checker."""

from contextlib import redirect_stderr, redirect_stdout
import hashlib
import importlib.util
import io
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch


SCRIPT = Path(__file__).resolve().parents[2] / "scripts/hass/install_skill_shadow.py"
SPEC = importlib.util.spec_from_file_location("install_skill_shadow", SCRIPT)
assert SPEC is not None and SPEC.loader is not None
CHECK = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(CHECK)
MARKER = "synthetic-private-marker"
CONTENT = MARKER.encode() + b"\r\n"
DIGEST = hashlib.sha256(CONTENT).hexdigest()


class InstallSkillShadowTests(unittest.TestCase):
    def setUp(self):
        temporary = tempfile.TemporaryDirectory()
        self.addCleanup(temporary.cleanup)
        self.base = Path(temporary.name).resolve() / MARKER
        self.base.mkdir()
        self.roster = self.base / "roots.json"

    def root(self, name):
        path = self.base / name
        path.mkdir()
        return path

    def copy(self, directory, data=CONTENT):
        directory.mkdir(parents=True, exist_ok=True)
        leaf = directory / "SKILL.md"
        leaf.write_bytes(data)
        return leaf

    def run_check(self, roster=None, *, raw=None, options=("--skill", "maintain")):
        if roster is not None:
            raw = json.dumps(roster).encode()
        if raw is not None:
            self.roster.write_bytes(raw)
        out, err = io.StringIO(), io.StringIO()
        with redirect_stdout(out), redirect_stderr(err):
            code = CHECK.main(["--roots", str(self.roster), *options])
        self.assertEqual(err.getvalue(), "")
        self.assert_private(out.getvalue())
        return code, out.getvalue().splitlines()

    def assert_private(self, text):
        self.assertNotIn(str(self.base), text)
        self.assertNotIn(MARKER, text)
        self.assertNotIn(DIGEST, text)
        self.assertNotIn("/", text)

    def assert_failed(self, result, *lines):
        self.assertEqual(result, (1, [*lines, "FAIL install_skill_shadow"]))

    def winner(self, profile="pilot", skill="maintain", index=0, digest=DIGEST):
        return f"{profile} {skill} winner root[{index}] sha256 {digest[:12]}"

    def test_profile_precedence_one_category_level_and_read_only_pass(self):
        # Flattening roots, recursing deeper, or hashing text rather than bytes changes this result.
        first, second = self.root("first"), self.root("second")
        self.copy(first / "cat" / "maintain")
        review = b"different fixture bytes"
        self.copy(second / "review", review)
        review_digest = hashlib.sha256(review).hexdigest()
        self.copy(second / "cat" / "nested" / "maintain", b"not a candidate")
        self.copy(first / "cat" / "nested" / "review", b"not a candidate")
        self.roster.write_text(json.dumps({"pilot-a": [str(first), str(second)],
                                          "pilot_b": [str(second), str(first)]}), encoding="utf-8")

        def snapshot():
            return {p: (p.stat().st_mtime_ns, None if p.is_dir() else p.read_bytes())
                    for p in self.base.rglob("*")}

        before = snapshot()
        self.assertEqual(self.run_check(options=("--skill", "maintain", "--skill", "review",
                                                 "--expect-sha256", f"maintain={DIGEST.upper()}")),
                         (0, [self.winner("pilot-a"), self.winner("pilot-a", "review", 1, review_digest),
                              self.winner("pilot_b", index=1),
                              self.winner("pilot_b", "review", digest=review_digest),
                              "PASS install_skill_shadow"]))
        self.assertEqual(snapshot(), before)

    def test_shadows_count_even_when_bytes_match(self):
        # A first-match-only scan, digest deduplication, or stopping at one shadow misses copies.
        first, second, third = (self.root(name) for name in ("first", "second", "third"))
        self.copy(first / "maintain")
        self.copy(second / "category" / "maintain", b"older bytes")
        self.copy(third / "maintain")
        self.assert_failed(self.run_check({"pilot": [str(first), str(second), str(third)]}),
                           self.winner(), "FAIL shadow pilot maintain root[1]",
                           "FAIL shadow pilot maintain root[2]")

    def test_ambiguity_in_winning_or_lower_root(self):
        # Choosing by listing order or overlooking ambiguous lower roots hides duplicate candidates.
        first, second = self.root("first"), self.root("second")
        self.copy(first / "maintain")
        self.copy(second / "maintain")
        self.copy(second / "category" / "maintain")
        self.assert_failed(self.run_check({"pilot": [str(second)]}), "FAIL ambiguous pilot maintain")
        self.assert_failed(self.run_check({"pilot": [str(first), str(second)]}), self.winner(),
                           "FAIL ambiguous pilot maintain", "FAIL shadow pilot maintain root[1]",
                           "FAIL shadow pilot maintain root[1]")

    def test_missing_skill_is_not_a_pass(self):
        # A nearby skill or an empty search list cannot stand in for the requested skill.
        root = self.root("root")
        self.copy(root / "other")
        for roots in ([str(root)], []):
            with self.subTest(roots=roots):
                self.assert_failed(self.run_check({"pilot": roots}), "FAIL missing pilot maintain")

    def test_symlinked_roots_skill_directories_and_files_are_rejected(self):
        # Following aliases accepts the wrong source; exists() alone also misses dangling links.
        # A leaf-only lstat (or resolve before checking) accepts a real skills
        # directory reached through an aliased profile as the roster winner.
        profile = self.root("profile")
        skills = profile / "skills"
        self.copy(skills / "maintain")
        lower = self.root("lower")
        self.assertEqual(self.run_check({"pilot": [str(skills), str(lower)]}),
                         (0, [self.winner(), "PASS install_skill_shadow"]))
        profile_alias = self.base / "profile-alias"
        profile_alias.symlink_to(profile, target_is_directory=True)
        # A refused higher-priority root must not promote the lower copy.
        self.copy(lower / "maintain")
        for raw, reason in ((str(profile_alias / "skills"), "symlink"),
                            (f"{profile}/./skills", "bad-roots"),
                            (f"{skills}/../skills", "bad-roots")):
            with self.subTest(reason=reason, component=raw.split("/")[-2]):
                self.assert_failed(self.run_check({"pilot": [raw, str(lower)]}), f"FAIL {reason}")

        target = self.copy(self.base / "target")
        root_alias = self.base / "alias"
        root_alias.symlink_to(target.parent, target_is_directory=True)
        self.assert_failed(self.run_check({"pilot": [str(root_alias) + "/"]}), "FAIL symlink")
        root = self.root("root")
        (root / "maintain").symlink_to(target.parent, target_is_directory=True)
        self.assert_failed(self.run_check({"pilot": [str(root)]}), "FAIL symlink")
        category = root / "cat"
        category.mkdir()
        (root / "maintain").unlink()
        (category / "maintain").mkdir()
        leaf = category / "maintain" / "SKILL.md"
        leaf.symlink_to(target)
        self.assert_failed(self.run_check({"pilot": [str(root)]}), "FAIL symlink")
        target.unlink()
        self.assert_failed(self.run_check({"pilot": [str(root)]}), "FAIL symlink")

    def test_symlinked_category_dir(self):
        # Skipping a category alias gives a false PASS; following it can report a shadow instead.
        first = self.root("first")
        self.copy(first / "maintain")
        for has_skill in (True, False):
            with self.subTest(has_skill=has_skill):
                second = self.root(f"second-{has_skill}")
                target = self.root(f"target-{has_skill}")
                if has_skill:
                    self.copy(target / "maintain", b"older bytes")
                (second / "cat").symlink_to(target, target_is_directory=True)
                self.assert_failed(self.run_check({"pilot": [str(first), str(second)]}),
                                   "FAIL symlink", self.winner())

    def test_relative_root_is_not_resolved_against_cwd(self):
        self.assert_failed(self.run_check({"pilot": [f"{MARKER}/root"]}), "FAIL not-absolute")

    def test_invalid_profile_and_skill_labels_are_redacted(self):
        # A path-like --skill must fail validation, not become a filesystem lookup or a usage error.
        self.assert_failed(self.run_check({f"{MARKER}/label": []}), "FAIL bad-label")
        self.assert_failed(self.run_check({"pilot": []}, options=("--skill", f"../{MARKER}")),
                           "FAIL bad-label")

    def test_pin_compares_full_hash_and_invalid_pin_input_fails(self):
        # A digest comparison using only the displayed prefix would accept this pin.
        root = self.root("root")
        self.copy(root / "maintain")
        roster = {"pilot": [str(root)]}
        wrong = DIGEST[:-1] + ("0" if DIGEST[-1] != "0" else "1")
        self.assert_failed(self.run_check(roster, options=("--skill", "maintain",
                                                          "--expect-sha256", f"maintain={wrong}")),
                           self.winner(), "FAIL sha-mismatch pilot maintain")
        for value, reason in ((MARKER, "bad-roots"), (f"maintain={DIGEST[:12]}", "bad-roots"),
                              (f"../{MARKER}={DIGEST}", "bad-label")):
            with self.subTest(value=value):
                self.assert_failed(self.run_check(roster, options=("--skill", "maintain",
                                                                  "--expect-sha256", value)),
                                   f"FAIL {reason}", self.winner())

    def test_bad_roots_covers_malformed_or_unreadable_input(self):
        # Invalid shape, duplicate keys, decode and filesystem errors cannot be silent or tracebacks.
        self.assert_failed(self.run_check(), "FAIL bad-roots")
        for payload in (b"[", b"[]", b"{}", b"\xff", b'{"pilot":[],"pilot":[]}',
                        b'{"pilot":"not a list"}', b'{"pilot":[null]}'):
            with self.subTest(payload=payload):
                self.assert_failed(self.run_check(raw=payload), "FAIL bad-roots")
        root = self.root("root")
        leaf = self.copy(root / "maintain")
        with patch.object(Path, "open", autospec=True, side_effect=self.deny_open(leaf)):
            self.assert_failed(self.run_check({"pilot": [str(root)]}), "FAIL bad-roots")
        self.assert_failed(self.run_check({"pilot": [str(root / "nonexistent")]}), "FAIL bad-roots")

    @staticmethod
    def deny_open(target):
        original = Path.open

        def open_path(path, *args, **kwargs):
            if path == target:
                raise PermissionError(str(path))
            return original(path, *args, **kwargs)

        return open_path

    def test_usage_error_remains_argparse_exit_two_and_redacted(self):
        # Turning missing options into check failures or echoing extra argv breaks the CLI contract.
        out, err = io.StringIO(), io.StringIO()
        with redirect_stdout(out), redirect_stderr(err), self.assertRaises(SystemExit) as raised:
            CHECK.main(["--roots", str(self.roster), "--skill", "maintain", str(self.base)])
        self.assertEqual(raised.exception.code, 2)
        self.assertEqual(out.getvalue(), "")
        self.assertIn("usage: install_skill_shadow.py", err.getvalue())
        self.assert_private(err.getvalue())


if __name__ == "__main__":
    unittest.main()
