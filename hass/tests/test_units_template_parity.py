"""Offline CLI contracts with disposable Git and installed-unit fixtures."""

import hashlib
import importlib.util
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest


SCRIPT = Path(__file__).resolve().parents[2] / "scripts/hass/units_template_parity.py"
SPEC = importlib.util.spec_from_file_location("units_template_parity", SCRIPT)
assert SPEC is not None and SPEC.loader is not None
PARITY = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(PARITY)
SERVICE = "hass-fixture.service"
TIMER = "hass-fixture.timer"
SERVICE_BYTES = b"[Service]\nType=oneshot\n"
TIMER_BYTES = b"[Timer]\nOnBootSec=1min\n"
PASS = "PASS units_template_parity"
FAIL = "FAIL units_template_parity"


class UnitsTemplateParityTests(unittest.TestCase):
    def setUp(self):
        self.root = Path(self.enterContext(tempfile.TemporaryDirectory())).resolve()
        self.repo = self.root / "checkout"
        self.installed = self.root / "installed"
        self.templates = self.repo / "deploy/hass"
        self.templates.mkdir(parents=True)
        self.installed.mkdir()
        self.env = dict(os.environ, GIT_CONFIG_NOSYSTEM="1", GIT_CONFIG_GLOBAL=os.devnull)
        self.git("init", "--quiet", "--template=", "--object-format=sha1")

    def git(self, *args):
        return subprocess.run(
            ["git", "-C", str(self.repo), *args], env=self.env, check=True,
            stdout=subprocess.PIPE, stderr=subprocess.PIPE, timeout=10,
        ).stdout.decode().strip()

    def commit(self):
        self.git("add", "--", "deploy/hass/")
        self.git("-c", "user.name=Fixture", "-c", "user.email=fixture@example.invalid",
                 "commit", "--quiet", "-m", "Synthetic unit templates")
        return self.git("rev-parse", "HEAD")

    def unit(self, name=SERVICE, content=SERVICE_BYTES):
        (self.templates / name).write_bytes(content)
        (self.installed / name).write_bytes(content)

    def invoke(self, commit, *, repo=None, installed=None, extra=()):
        return self.cli("--repo", str(repo or self.repo), "--commit", commit,
                        "--installed", str(installed or self.installed), *extra)

    def cli(self, *args):
        assert PARITY.__file__ is not None
        return subprocess.run(
            [sys.executable, "-B", PARITY.__file__, *args], cwd=self.root, env=self.env,
            capture_output=True, text=True, timeout=10,
        )

    def assert_report(self, result, code, *lines):
        self.assertEqual(result.returncode, code, result.stderr)
        self.assertEqual(result.stderr, "")
        self.assertEqual(result.stdout, "\n".join((*lines, PASS if code == 0 else FAIL)) + "\n")

    def assert_usage(self, result, last):
        self.assertEqual(result.returncode, 2)
        self.assertEqual(result.stdout, "")
        self.assertTrue(result.stderr.startswith("usage:"))
        self.assertEqual(result.stderr.splitlines()[-1], f"{SCRIPT.name}: error: {last}")

    def test_c1_full_pass(self):
        # Reading HEAD/worktree instead of the selected commit, or ignoring
        # symlinks and the extra unit, would change the report.
        self.unit()
        (self.templates / TIMER).write_bytes(TIMER_BYTES)
        target = self.root / "unit-target"
        target.write_bytes(TIMER_BYTES)
        (self.installed / TIMER).symlink_to(target)
        (self.installed / "hass-extra.service").write_bytes(b"fixture\n")
        selected = self.commit()
        (self.templates / SERVICE).write_bytes(b"new revision\n")
        self.commit()
        (self.templates / TIMER).write_bytes(b"local edit\n")
        self.assert_report(self.invoke(selected), 0, f"same {SERVICE}",
                           f"note symlink {TIMER}", f"same {TIMER}",
                           "note extra hass-extra.service")

    def test_c2_1_not_git(self):
        # Merely validating that --repo names a directory isn't enough.
        self.unit()
        self.assert_report(self.invoke(self.commit(), repo=self.installed), 1, "FAIL not-git")

    def test_c2_2_bad_commit(self):
        # Git accepts rev expressions, short SHAs, and peeled tags, but this CLI doesn't.
        (self.templates / "README.md").write_text("Synthetic non-unit\n")
        nested = self.templates / "nested"
        nested.mkdir()
        (nested / TIMER).write_bytes(TIMER_BYTES)
        empty_templates = self.commit()
        self.unit()
        sha = self.commit()
        blob = self.git("rev-parse", f"HEAD:deploy/hass/{SERVICE}")
        self.git("-c", "user.name=Fixture", "-c", "user.email=fixture@example.invalid",
                 "tag", "-m", "Synthetic tag", "fixture-tag", sha)
        tag = self.git("rev-parse", "fixture-tag")
        for token in ("HEAD", sha[:12], sha.upper(), "0" * 40, blob, tag):
            with self.subTest(token=token):
                self.assert_report(self.invoke(token), 1, "FAIL bad-commit")

        # The selected commit needs a qualifying template. Comparing an empty
        # roster would otherwise pass and report the installed service as extra.
        self.assert_report(self.invoke(empty_templates), 1, "FAIL bad-commit")

    def test_c2_3_no_installed(self):
        # A file and a nonexistent path each fail as the directory, not as a unit.
        self.unit()
        sha = self.commit()
        for path in (self.installed / SERVICE, self.root / "absent"):
            with self.subTest(path=path.name):
                self.assert_report(self.invoke(sha, installed=path), 1, "FAIL no-installed")

    def test_c2_4_missing_unit(self):
        # Missing units cannot produce a partial pass; a broken link is also noted.
        (self.templates / SERVICE).write_bytes(SERVICE_BYTES)
        sha = self.commit()
        self.assert_report(self.invoke(sha), 1, f"FAIL missing-unit {SERVICE}")
        (self.installed / SERVICE).symlink_to("absent")
        self.assert_report(self.invoke(sha), 1, f"note symlink {SERVICE}",
                           f"FAIL missing-unit {SERVICE}")

    def test_c2_5_differs(self):
        # Text normalization or checking only common lines would hide byte drift.
        self.unit(content=b"[Service]\n\xff\nlast\n")
        sha = self.commit()
        for content, first_line in (
            (b"[Timer]\n\x00\nother\n", 1),
            (b"[Service]\n\xfe\nother\n", 2),
            (b"[Service]\n\xff\nlast", 3),
            (b"[Service]\n\xff\n", 3),
            (b"[Service]\n\xff\nlast\n\n", 4),
            (b"[Service]\r\n\xff\r\nlast\r\n", 1),
        ):
            with self.subTest(content=content):
                (self.installed / SERVICE).write_bytes(content)
                self.assert_report(self.invoke(sha), 1, f"FAIL differs {SERVICE} {first_line}")

    def test_c3_usage_exit_2(self):
        # Usage errors must stop at parsing, not become status-1 findings.
        self.unit()
        sha = self.commit()
        for result, last in (
            (self.cli(), "the following arguments are required: --repo, --commit, --installed"),
            (self.invoke(sha, extra=("--unknown",)), "unrecognized arguments"),
            (self.cli("--repo"), "argument --repo: expected one argument"),
        ):
            self.assert_usage(result, last)

    def test_c4_read_only(self):
        # A checkout, index write, or installed repair changes the input inventory.
        self.unit()
        (self.templates / TIMER).write_bytes(TIMER_BYTES)
        selected = self.commit()
        self.unit(content=b"different\n")
        self.commit()

        def snapshot():
            return {
                path.relative_to(self.root): (
                    (path.read_bytes(), path.stat().st_mtime_ns) if path.is_file() else None
                )
                for path in self.root.rglob("*")
            }

        before = snapshot()
        self.assert_report(self.invoke(selected), 1, f"FAIL differs {SERVICE} 1",
                           f"FAIL missing-unit {TIMER}")
        self.assertEqual(snapshot(), before)

    def test_c5_no_private_values(self):
        # A unified diff, Git stderr, or echoing invalid arguments would leak canaries.
        payload = b"fixture-message-canary\nfixture-chat-canary\nfixture-sender-canary\n"
        self.unit(content=payload)
        sha = self.commit()
        bad_sha = hashlib.sha1(b"synthetic missing object", usedforsecurity=False).hexdigest()
        digest = hashlib.sha256(payload).hexdigest()
        (self.installed / SERVICE).write_bytes(f"{digest}\n".encode())
        drift = self.invoke(sha)
        bad_commit = self.invoke(bad_sha)
        not_git = self.invoke(sha, repo=self.root / "absent")
        usage = self.invoke(sha, extra=("--unknown", str(self.installed)))
        for result in (drift, bad_commit, not_git, usage):
            for canary in (*payload.decode().splitlines(), sha, bad_sha, digest, str(self.root)):
                self.assertNotIn(canary, result.stdout + result.stderr)
        self.assert_report(drift, 1, f"FAIL differs {SERVICE} 1")
        self.assert_report(bad_commit, 1, "FAIL bad-commit")
        self.assert_report(not_git, 1, "FAIL not-git")
        self.assert_usage(usage, "unrecognized arguments")

    def test_c6_only_unit_files(self):
        # A broad tree scan would require a README, a socket, or nested files.
        self.unit()
        for name in ("README.md", "hass-fixture.socket", "hass-fixture.service.bak"):
            (self.templates / name).write_bytes(b"ignored\n")
            (self.installed / name).write_bytes(b"different but ignored\n")
        (self.templates / "sub.timer").mkdir()
        (self.templates / "sub.timer" / TIMER).write_bytes(b"nested\n")
        (self.installed / "hass-directory.timer").mkdir()
        (self.installed / "other.service").write_bytes(b"ignored extra\n")
        self.assert_report(self.invoke(self.commit()), 0, f"same {SERVICE}")


if __name__ == "__main__":
    unittest.main()
