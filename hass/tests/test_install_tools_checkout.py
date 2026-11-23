"""Offline CLI tests against a disposable, locally cloned Git checkout."""

from contextlib import redirect_stderr, redirect_stdout
from hashlib import sha256
import importlib.util
from io import StringIO
from pathlib import Path
import subprocess
from tempfile import TemporaryDirectory
import unittest


SCRIPT = Path(__file__).resolve().parents[2] / "scripts/hass/install_tools_checkout.py"
SPEC = importlib.util.spec_from_file_location("install_tools_checkout", SCRIPT)
assert SPEC is not None and SPEC.loader is not None
checkout = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(checkout)

ORIGIN = "https://example.invalid/tools"
PRIVATE = "synthetic-private-marker"
TOOLS = {
    "scripts/hass/install_z.py": b"# second\n",
    "scripts/hass/install_a.py": f"# {PRIVATE}\n".encode(),
}


class InstallToolsCheckoutTests(unittest.TestCase):
    def setUp(self):
        temporary = TemporaryDirectory()
        self.addCleanup(temporary.cleanup)
        self.root = Path(temporary.name)
        source = self.root / "source"
        source.mkdir()
        self.git(source, "init", "--quiet")
        for path, content in {**TOOLS, "scripts/hass/other.py": b"# not a tool\n"}.items():
            file = source / path
            file.parent.mkdir(parents=True, exist_ok=True)
            file.write_bytes(content)
        self.git(source, "add", "--all")
        self.git(source, "commit", "--quiet", "--message", "fixture")
        self.repo = self.root / PRIVATE
        self.git(self.root, "clone", "--quiet", "--local", str(source), str(self.repo))
        self.git(self.repo, "remote", "set-url", "origin", ORIGIN + ".git/")
        self.sha = self.git(self.repo, "rev-parse", "HEAD").strip()

    @staticmethod
    def git(cwd, *args):
        return subprocess.run(
            ["git", "-c", "user.name=Fixture", "-c", "user.email=fixture@example.invalid",
             "-c", "commit.gpgsign=false", "-c", "core.hooksPath=/dev/null", *args],
            cwd=cwd, check=True, capture_output=True, text=True,
        ).stdout

    def invoke(self, *, sha=None, repo=None, origin=ORIGIN, extra=()):
        stdout, stderr = StringIO(), StringIO()
        argv = ["--repo", str(self.repo if repo is None else repo),
                "--sha", self.sha if sha is None else sha, "--remote-url", origin, *extra]
        with redirect_stdout(stdout), redirect_stderr(stderr):
            try:
                status = checkout.main(argv)
            except SystemExit as error:
                status = error.code
        # Git diagnostics, argv, raw paths, SHAs and file contents stay private.
        for private in (PRIVATE, str(self.root), self.sha, origin):
            if private:
                self.assertNotIn(private, stdout.getvalue() + stderr.getvalue())
        return status, stdout.getvalue().splitlines(), stderr.getvalue()

    def assert_failed(self, *reasons, **kwargs):
        lines = [*(f"FAIL {reason}" for reason in reasons), "FAIL install_tools_checkout"]
        self.assertEqual(self.invoke(**kwargs), (1, lines, ""))

    def test_checkout_requires_selected_tool_bytes(self):
        # Porcelain can be quiet for an assume-unchanged helper. A hash of
        # only the checkout would then certify edited bytes under the pin.
        expected = [f"install_tool {path} {sha256(TOOLS[path]).hexdigest()[:12]}"
                    for path in sorted(TOOLS)]
        expected.append("PASS install_tools_checkout")
        self.assertEqual(self.invoke(origin=ORIGIN + "/"), (0, expected, ""))

        path = "scripts/hass/install_z.py"  # The earlier helper still matches.
        self.git(self.repo, "update-index", "--assume-unchanged", "--", path)
        (self.repo / path).write_bytes(b"# changed fixture\n")
        self.assertEqual(self.git(self.repo, "status", "--porcelain", "--untracked-files=all"), "")
        self.assert_failed("dirty")  # Asserts no partial receipt rows.

    def test_empty_selected_helper_set_refuses(self):
        # A clean commit without helpers is not a complete checkout receipt.
        self.git(self.repo, "rm", "--quiet", "--", *TOOLS)
        self.git(self.repo, "commit", "--quiet", "--message", "no tools")
        self.sha = self.git(self.repo, "rev-parse", "HEAD").strip()
        self.assert_failed("dirty")

    def test_invalid_sha_is_a_named_failure(self):
        # Neither argparse's exit 2 nor rev-parse abbreviation is a valid pin.
        for sha in (PRIVATE, "", self.sha[:12], "A" * 40, self.sha + "\n"):
            with self.subTest(sha=sha):
                self.assert_failed("bad-sha", sha=sha)

    def test_not_git_for_plain_or_missing_directory(self):
        # An unreadable cwd or a non-checkout must not print a Git traceback.
        for repo in (self.root, self.root / "missing"):
            with self.subTest(repo=repo.name):
                self.assert_failed("not-git", repo=repo)

    def test_different_commit(self):
        # A resolvable, clean HEAD is insufficient unless it equals the pin.
        self.git(self.repo, "commit", "--quiet", "--allow-empty", "--message", "next")
        self.assert_failed("head-mismatch")

    def test_modified_tracked_file(self):
        # A checker that only compares HEAD and origin misses working-tree edits.
        (self.repo / next(iter(TOOLS))).write_text(PRIVATE, encoding="utf-8")
        self.assert_failed("dirty")

    def test_untracked_file_and_multiple_findings(self):
        # Explicit untracked mode must override local status configuration.
        self.git(self.repo, "config", "status.showUntrackedFiles", "no")
        (self.repo / "scripts" / PRIVATE).touch()
        self.assert_failed("dirty")
        self.git(self.repo, "remote", "remove", "origin")
        self.assert_failed("dirty", "no-remote")

    def test_missing_origin(self):
        # An absent remote is distinct from a different configured origin.
        self.git(self.repo, "remote", "remove", "origin")
        self.assert_failed("no-remote")

    def test_wrong_or_malformed_remote(self):
        # Do not echo the remote, ignore extra suffixes, or accept an empty pin.
        self.git(self.repo, "remote", "set-url", "origin", f"{ORIGIN}/{PRIVATE}")
        self.assert_failed("wrong-remote")
        self.git(self.repo, "remote", "set-url", "origin", ORIGIN + ".git//")
        self.assert_failed("wrong-remote")
        self.assert_failed("wrong-remote", origin="")

    def test_clean_but_unreadable_tool_never_emits_partial_digests(self):
        # A tracked link must not hash an external or missing target.
        file = self.repo / "scripts/hass/install_z.py"
        file.unlink()
        file.symlink_to(PRIVATE)
        self.git(self.repo, "add", "--all")
        self.git(self.repo, "commit", "--quiet", "--message", "replace with link")
        self.sha = self.git(self.repo, "rev-parse", "HEAD").strip()
        self.assert_failed("dirty")

        # Git can check a symlink out as an ordinary file of identical bytes.
        # Byte equality alone must not qualify that non-ordinary tree entry.
        self.git(self.repo, "config", "core.symlinks", "false")
        file.unlink()
        file.write_bytes(PRIVATE.encode())
        self.assertEqual(self.git(self.repo, "status", "--porcelain", "--untracked-files=all"), "")
        self.assert_failed("dirty")

    def test_usage_error_keeps_argparse_exit_code_without_echoing_values(self):
        # An unknown flag is usage, not a checkout finding or a data echo.
        code, lines, stderr = self.invoke(extra=(f"--{PRIVATE}",))
        self.assertEqual((code, lines), (2, []))
        self.assertIn("usage: install_tools_checkout", stderr)
