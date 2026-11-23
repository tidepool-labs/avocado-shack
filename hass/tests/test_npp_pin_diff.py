"""Exercise the pin-diff CLI against disposable, synthetic Git repositories."""

import hashlib
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile
import unittest


SCRIPT = Path(__file__).resolve().parents[2] / "scripts/hass/npp_pin_diff.py"
ASSETS = "hass/npp/assets"
PINS = "hass/npp/pins.json"
NAME = "nested/.sample data"
PAYLOAD = b"synthetic baseline bytes\x00\r\n\xff"


def digest(data):
    return hashlib.sha256(data).hexdigest()


class NppPinDiffTests(unittest.TestCase):
    def setUp(self):
        temp = tempfile.TemporaryDirectory()
        self.addCleanup(temp.cleanup)
        self.root = Path(temp.name).resolve()
        self.repo = self.root / "fixture"
        self.repo.mkdir()
        self.env = {key: value for key, value in os.environ.items() if not key.startswith("GIT_")}
        self.env.update(GIT_CONFIG_GLOBAL=os.devnull, GIT_CONFIG_NOSYSTEM="1",
                        GIT_CEILING_DIRECTORIES=str(self.root), GIT_ALLOW_PROTOCOL="")
        self.git("init", "-q", "--template=", "--initial-branch=fixture")
        self.git("config", "user.name", "Fixture")
        self.git("config", "user.email", "fixture@example.invalid")
        self.git("config", "core.autocrlf", "false")
        self.write(f"{ASSETS}/{NAME}", PAYLOAD)
        self.pins({NAME: digest(PAYLOAD)})
        self.base = self.commit()

    def git(self, *args):
        return subprocess.run(["git", "-C", str(self.repo), *args], env=self.env,
                              check=True, capture_output=True, timeout=10).stdout

    def write(self, name, data):
        path = self.repo / name
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(data)

    def pins(self, assets, **fields):
        self.write(PINS, json.dumps({"assets": assets, **fields}).encode())

    def commit(self):
        self.git("add", "-A")
        self.git("commit", "-q", "--allow-empty", "-m", "synthetic fixture commit")
        return self.git("rev-parse", "HEAD").decode().strip()

    def cli(self, *args):
        return subprocess.run([sys.executable, "-B", str(SCRIPT), *args], cwd=self.root,
                              env=self.env, capture_output=True, text=True, timeout=10)

    def compare(self, *, repo=None, base=None, head="HEAD"):
        return self.cli("--repo", str(self.repo if repo is None else repo),
                        f"--base={self.base if base is None else base}", f"--head={head}")

    def assert_result(self, result, code):
        self.assertEqual(result.returncode, code, result.stderr)
        self.assertEqual(result.stderr, "")
        lines = result.stdout.splitlines()
        self.assertTrue(lines)
        self.assertEqual(lines[-1], "PASS npp_pin_diff" if code == 0 else "FAIL npp_pin_diff")
        return lines

    def assert_findings(self, result, *reasons):
        lines = self.assert_result(result, 1)
        self.assertEqual([line for line in lines[:-1] if line.startswith("FAIL ")],
                         [f"FAIL {reason}" for reason in reasons])

    def test_c1_full_pass(self):
        # A suffix filter, text hashing, or a work-tree-only reader would miss this blob.
        bare = self.root / "bare.git"
        shutil.copytree(self.repo / ".git", bare)
        self.git("config", "--file", str(bare / "config"), "core.bare", "true")
        for repo in (self.repo, bare):
            with self.subTest(bare=repo == bare):
                lines = self.assert_result(self.compare(repo=repo), 0)
                self.assertEqual(lines, ["assets 1", "assets-changed 0", "pins-changed no", "PASS npp_pin_diff"])

    def test_c2_1_not_a_repo(self):
        # Probe errors must not fall through into revision resolution.
        plain = self.root / "plain"
        plain.mkdir()
        self.assert_findings(self.compare(repo=plain, base="missing-ref", head="missing-ref"), "not-a-repo")

    def test_c2_2_bad_rev(self):
        # An existing blob object isn't a commit, and neither failing operand may be mislabeled.
        blob = self.git("rev-parse", f"HEAD:{ASSETS}/{NAME}").decode().strip()
        for rev in ("missing-ref", blob, "--not-a-revision-option"):
            for side in ("base", "head"):
                with self.subTest(side=side, existing_object=rev == blob):
                    self.assert_findings(self.compare(**{side: rev}), f"bad-rev {side}")

    def test_c2_3_pins_unreadable(self):
        # Missing, unparsable, and wrong-shaped pins must not be mistaken for an empty pin map.
        self.git("rm", "-q", "--", PINS)
        self.assert_findings(self.compare(head=self.commit()), "pins-unreadable")
        for raw in (b"not-json", b"\xff", b"[]", b"{}", b'{"assets": []}', b'{"assets": {}, "other": NaN}'):
            with self.subTest(raw=raw):
                self.write(PINS, raw)
                self.assert_findings(self.compare(head=self.commit()), "pins-unreadable")

    def test_c2_4_pin_stale(self):
        # Checking just that the pin key exists would miss the edited blob.
        self.write(f"{ASSETS}/{NAME}", b"different fixture bytes")
        self.assert_findings(self.compare(head=self.commit()), f"pin-stale {NAME}")

    def test_c2_5_pin_missing(self):
        # Checking only keys in pins.json would miss a new unpinned asset.
        new = "nested/fixture-extra"
        self.write(f"{ASSETS}/{new}", b"another synthetic asset")
        self.assert_findings(self.compare(head=self.commit()), f"pin-missing {new}")

    def test_c2_6_pin_orphan(self):
        # Checking only the new tree's names would miss the leftover pin on deletion.
        self.git("rm", "-q", "--", f"{ASSETS}/{NAME}")
        result = self.compare(head=self.commit())
        self.assert_findings(result, f"pin-orphan {NAME}")
        self.assertEqual(result.stdout.splitlines()[:4],
                         ["assets 0", "assets-changed 1", f"asset-changed {NAME}", "pins-changed no"])

    def test_c3_usage_exit_2(self):
        # Usage failures must not enter Git lookup or emit the exit-1 finding marker.
        for args in (("--repo", str(self.repo)), ("--repo", "--base", self.base, "--head", "HEAD"),
                     ("--repo", str(self.repo), "--base", self.base, "--head", "HEAD", "--unknown")):
            with self.subTest(argument_count=len(args)):
                result = self.cli(*args)
                self.assertEqual(result.returncode, 2)
                self.assertEqual(result.stdout, "")  # No last stdout line for C3.
                self.assertTrue(result.stderr.splitlines()[-1].startswith("npp_pin_diff.py: error: "))

    def test_c4_read_only(self):
        # Comparing names alone misses in-place rewrites and transient output creation.
        def snapshot():
            return {path.relative_to(self.root): (path.stat().st_mtime_ns,
                                                  path.read_bytes() if path.is_file() else None)
                    for path in [self.root, *self.root.rglob("*")]}

        before = snapshot()
        self.assert_result(self.compare(), 0)
        self.assertEqual(snapshot(), before)

    def test_c5_no_private_values(self):
        # Values would escape via a raw JSON/blob diff, verbose findings, or Git/argparse errors.
        message = "fixture-only-canary-message"
        chat = "fixture-only-canary-chat"
        sender = "fixture-only-canary-sender"
        lookup = "fixture-only-canary-revision"
        private_id = "fixture-only-canary-full-id"
        self.pins({NAME: digest(PAYLOAD)}, steps={"sample": {"note": message, "context": [chat, sender, private_id]}})
        self.write(f"{ASSETS}/{NAME}", message.encode())
        head = self.commit()
        result = self.compare(head=head)
        self.assert_findings(result, f"pin-stale {NAME}")
        self.assertIn("step-changed sample context", result.stdout.splitlines())
        self.assertIn("step-changed sample note", result.stdout.splitlines())
        unresolved = self.compare(head=lookup)
        self.assert_findings(unresolved, "bad-rev head")
        usage = self.cli("--repo", str(self.repo), "--base", self.base, "--head", head, "--" + sender)
        self.assertEqual(usage.returncode, 2)
        self.assertEqual(usage.stdout, "")
        output = "".join(r.stdout + r.stderr for r in (result, unresolved, usage))
        for canary in (message, chat, sender, lookup, private_id, self.base, head, digest(PAYLOAD),
                       digest(message.encode()), str(self.root), str(self.repo)):
            self.assertTrue(canary not in output, "private fixture value escaped")

    def test_c6_changed_and_repinned(self):
        # A validator that reads base pins, treats change notices as failures, or reports
        # whole JSON objects rather than changed fields would reject or misreport this edit.
        self.pins({NAME: digest(PAYLOAD)}, steps={"sample": {"removed": None, "kept": [2], "type": True,
                                                             "object": {"b": 2, "a": 1}}})
        base = self.commit()
        edited = b"replacement\r\n\x00\xff"
        added = "nested/fixture-é"
        self.write(f"{ASSETS}/{NAME}", edited)
        self.write(f"{ASSETS}/{added}", edited)
        self.pins({NAME: digest(edited), added: digest(edited)},
                  steps={"sample": {"added": None, "kept": [2], "type": 1, "object": {"a": 1, "b": 2}}})
        lines = self.assert_result(self.compare(base=base, head=self.commit()), 0)
        self.assertEqual(lines, ["assets 2", "assets-changed 2", f"asset-changed {NAME}",
                                 f"asset-changed {added}", "pins-changed yes", "step-changed sample added",
                                 "step-changed sample removed", "step-changed sample type", "PASS npp_pin_diff"])

    def test_c7_git_untouched(self):
        # Checking out either revision or reading from the index/work tree would fail.
        edited = b"committed head fixture"
        self.write(f"{ASSETS}/{NAME}", edited)
        self.pins({NAME: digest(edited)})
        head = self.commit()
        self.git("branch", "other", self.base)
        self.git("switch", "-q", "other")
        self.write(f"{ASSETS}/{NAME}", b"staged fixture")
        self.git("add", "--", f"{ASSETS}/{NAME}")
        self.write(f"{ASSETS}/{NAME}", b"unstaged fixture")
        self.write(PINS, b"unstaged non-JSON fixture")

        def snapshot():
            return (self.git("status", "--porcelain=v1"), self.git("rev-parse", "HEAD"),
                    self.git("for-each-ref"), (self.repo / ".git/index").read_bytes(),
                    (self.repo / f"{ASSETS}/{NAME}").read_bytes(), (self.repo / PINS).read_bytes())

        before = snapshot()
        self.assertIn(b"MM ", before[0])
        self.assertNotEqual(before[1].decode().strip(), head)
        self.assert_result(self.compare(head=head), 0)
        self.assertEqual(snapshot(), before)


if __name__ == "__main__":
    unittest.main()
