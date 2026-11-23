"""Fixture-only CLI contract for install-kit citation ranges."""

import os
from pathlib import Path
import subprocess
import sys
from tempfile import TemporaryDirectory
import unittest


SCRIPT = Path(__file__).resolve().parents[2] / "scripts/hass/install_citation_drift.py"
SCOPE = "Only file and range existence were checked; semantic equivalence was not checked."


class InstallCitationDriftTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        scratch = TemporaryDirectory(prefix="citation-drift-")
        cls.addClassCleanup(scratch.cleanup)
        cls.root = Path(scratch.name)
        cls.repo = cls.root / "checkout"
        cls.repo.mkdir()
        cls.git("init", "--quiet", "--object-format=sha1")
        (cls.repo / "docs").mkdir()
        (cls.repo / "docs/fixture.txt").write_bytes(b"one\r\ntwo\nthree")
        (cls.repo / "terminated.txt").write_bytes(b"one\n\n")
        (cls.repo / "byte-lines.txt").write_bytes(b"one\rtwo\x0bthree\xff")
        (cls.repo / "empty.txt").touch()
        (cls.repo / "refs [1]: notes.txt").write_bytes(b"example\n")
        (cls.repo / "run.sh").write_bytes(b"example\n")
        (cls.repo / "alias").symlink_to("docs/fixture.txt")
        cls.git("add", "--all")
        cls.git("update-index", "--chmod=+x", "run.sh")
        cls.git("commit", "--quiet", "-m", "Fixture without gitlink")
        cls.previous = cls.git("rev-parse", "HEAD")
        cls.git("update-index", "--add", "--cacheinfo", f"160000,{cls.previous},linked")
        (cls.repo / "head-only.txt").write_bytes(b"later\n")
        cls.git("add", "head-only.txt")
        cls.git("commit", "--quiet", "-m", "Selected fixture")
        cls.commit = cls.git("rev-parse", "HEAD")

    @classmethod
    def git(cls, *args):
        return subprocess.check_output(
            ["git", "-C", str(cls.repo), "-c", "user.name=Fixture",
             "-c", "user.email=fixture@example.invalid", "-c", "commit.gpgsign=false",
             "-c", "core.hooksPath=/dev/null", *args], text=True,
        ).strip()

    def cli(self, *refs, commit=None, env=None):
        return subprocess.run(
            [sys.executable, "-B", str(SCRIPT), "--repo", str(self.repo),
             "--commit", self.commit if commit is None else commit, "--", *refs],
            cwd=self.root, env=env, text=True, capture_output=True, check=False,
        )

    def test_inclusive_ranges_count_blob_lines_not_newline_only_or_splitlines(self):
        # Missing a final LF, inventing a line after LF, or treating CR/VT as LF changes these outcomes.
        good = self.cli("docs/fixture.txt:1–3", "terminated.txt:2-2", "byte-lines.txt:1-1",
                        "refs [1]: notes.txt:1-1", "run.sh:1-1")
        self.assertEqual(good.returncode, 0, good.stdout + good.stderr)
        self.assertEqual(good.stdout.count("\nOK "), 5)
        self.assertIn(SCOPE, good.stdout)
        bad = self.cli("docs/fixture.txt:1-4", "terminated.txt:3-3", "empty.txt:1-1",
                       "byte-lines.txt:2-2")
        self.assertEqual(bad.returncode, 1, bad.stdout + bad.stderr)
        for lines in (3, 2, 0, 1):
            self.assertIn(f"too short ({lines} lines;", bad.stdout)

    def test_reports_all_missing_and_non_regular_entries(self):
        # Looking up raw blobs by commit:path alone accepts the symlink's target text as a line.
        result = self.cli("absent:1-1", "docs:1-1", "alias:1-1", "linked:1-1", "run.sh:1-1")
        self.assertEqual(result.returncode, 1, result.stdout + result.stderr)
        self.assertIn("'absent:1-1': missing", result.stdout)
        for path in ("docs", "alias", "linked"):
            self.assertIn(f"'{path}:1-1': not a regular file", result.stdout)
        self.assertIn("OK 'run.sh:1-1'", result.stdout)
        self.assertIn(SCOPE, result.stdout)

    def test_worktree_replacement_cannot_extend_selected_blob(self):
        # A reader of the worktree would pass this exact one-line-over-EOF reference.
        path = self.repo / "docs/fixture.txt"
        self.addCleanup(path.write_bytes, path.read_bytes())
        path.write_bytes(b"one\ntwo\nthree\nfour\n")
        result = self.cli("docs/fixture.txt:4-4")
        self.assertEqual(result.returncode, 1, result.stdout + result.stderr)
        self.assertIn("too short (3 lines; needs line 4)", result.stdout)

    def test_reads_the_selected_commit_even_when_head_differs(self):
        # Always checking HEAD would see a file introduced after the selected commit.
        self.assertEqual(self.cli("head-only.txt:1-1").returncode, 0)
        result = self.cli("head-only.txt:1-1", commit=self.previous)
        self.assertEqual(result.returncode, 1, result.stdout + result.stderr)
        self.assertIn("missing from the selected commit", result.stdout)

    def test_replacement_ref_cannot_substitute_blob(self):
        # Ordinary cat-file honors refs/replace unless explicitly disabled.
        original = self.git("rev-parse", f"{self.commit}:empty.txt")
        replacement = self.git("rev-parse", f"{self.commit}:terminated.txt")
        self.git("replace", original, replacement)
        self.addCleanup(self.git, "replace", "-d", original)
        result = self.cli("empty.txt:1-1")
        self.assertEqual(result.returncode, 1, result.stdout + result.stderr)
        self.assertIn("too short (0 lines; needs line 1)", result.stdout)

    def test_rejects_invalid_ranges_and_non_relative_paths(self):
        # Reject malformed input before lookup, even when a normalized path would exist.
        # Echoing a rejected operand could expose pasted text in shared CLI evidence.
        marker = "SYNTHETIC_PRIVATE_VALUE"
        invalid = ("run.sh", "run.sh:0-1", "run.sh:2-1", "run.sh:-1-2", "run.sh:1",
                   "run.sh:1-2junk", "/run.sh:1-1", "./run.sh:1-1", "docs/../run.sh:1-1",
                   "docs//fixture.txt:1-1", ":1-1")
        result = self.cli(marker, "run.sh:1-1", *invalid)
        self.assertEqual(result.returncode, 1, result.stdout + result.stderr)
        self.assertNotIn(marker, result.stdout + result.stderr)
        self.assertIn("OK 'run.sh:1-1'", result.stdout)
        self.assertEqual(result.stdout.count(": invalid citation"), 1 + len(invalid))
        for ordinal in (1, *range(3, len(invalid) + 3)):
            self.assertIn(f"FAIL citation #{ordinal}: invalid citation", result.stdout)

    def test_requires_available_full_commit_not_revision_or_other_object(self):
        # A generic revision parser can silently allow a branch, abbreviated ID or non-commit.
        blob = self.git("rev-parse", f"{self.commit}:run.sh")
        self.git("-c", "tag.gpgSign=false", "tag", "-a", "fixture-tag", "-m", "Fixture tag")
        tag = self.git("rev-parse", "fixture-tag")
        for value in ("HEAD", self.commit[:12], "0" * 40, blob, tag):
            with self.subTest(value=value[:12]):
                result = self.cli("run.sh:1-1", commit=value)
                self.assertEqual(result.returncode, 2, result.stdout + result.stderr)
                self.assertIn("--commit", result.stderr)
                self.assertEqual(result.stdout, "")

    def test_checkout_argument_wins_over_inherited_git_dir(self):
        # An ambient Git command context can otherwise redirect an explicit checkout.
        env = dict(os.environ, GIT_DIR=str(self.root / "not-the-checkout"))
        result = self.cli("run.sh:1-1", env=env)
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        self.assertIn("OK 'run.sh:1-1'", result.stdout)


if __name__ == "__main__":
    unittest.main()
