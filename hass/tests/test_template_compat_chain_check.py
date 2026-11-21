"""Offline contract tests for the template compatibility chain report."""

from contextlib import redirect_stderr, redirect_stdout
import importlib.util
import io
from pathlib import Path
import subprocess
import sys
from tempfile import TemporaryDirectory
import unittest
from unittest.mock import patch

from hass import template_compat


REPO = Path(__file__).resolve().parents[2]
SCRIPT = REPO / "scripts/hass/template_compat_chain_check.py"
MARKET = "hass/templates/home/market.html"
PASS = "PASS template_compat_chain_check"
FAIL = "FAIL template_compat_chain_check"

spec = importlib.util.spec_from_file_location("template_compat_chain_check", SCRIPT)
assert spec is not None and spec.loader is not None
checker = importlib.util.module_from_spec(spec)
spec.loader.exec_module(checker)


class TemplateCompatChainCheckTests(unittest.TestCase):
    def setUp(self):
        temporary = TemporaryDirectory(dir=REPO)
        self.addCleanup(temporary.cleanup)
        self.root = Path(temporary.name)
        self.repo = self.root / "synthetic-checkout"
        self.repo.mkdir()
        self.market = self.repo / MARKET
        self.real_bytes = (REPO / MARKET).read_bytes()

    def write_market(self, data):
        self.market.parent.mkdir(parents=True, exist_ok=True)
        self.market.write_bytes(data)

    def run_cli(self, *args):
        return subprocess.run(
            [sys.executable, "-B", str(SCRIPT), *args], cwd=self.root,
            capture_output=True, text=True, timeout=10,
        )

    def run_main(self, repo=None):
        stdout, stderr = io.StringIO(), io.StringIO()
        with redirect_stdout(stdout), redirect_stderr(stderr):
            code = checker.main(["--repo", str(self.repo if repo is None else repo)])
        return subprocess.CompletedProcess([], code, stdout.getvalue(), stderr.getvalue())

    def assert_report(self, result, code, trailer, *findings):
        self.assertEqual(result.returncode, code)
        self.assertEqual(result.stderr, "")
        lines = result.stdout.splitlines()
        self.assertEqual(lines[-1:], [trailer])
        self.assertEqual([line for line in lines[:-1] if line.startswith("FAIL ")], list(findings))
        return lines

    def test_c1_full_pass(self):
        # Direct invocation must locate the Hass package without relying on the working directory.
        self.write_market(self.real_bytes)
        self.assert_report(self.run_cli("--repo", str(self.repo)), 0, PASS)

    def test_c2_findings_trailer(self):
        # A missing first path must not skip later checks or suppress the final status.
        other = "hass/templates/sample.html"
        rows = template_compat.TEMPLATE_EDITS + ((other, "a" * 64, "b" * 64, "x", "y"),)
        with patch.object(checker, "TEMPLATE_EDITS", rows):
            self.assert_report(self.run_main(), 1, FAIL, f"FAIL missing {MARKET}", f"FAIL missing {other}")

    def test_c2_1_unsafe_input(self):
        # is_dir() alone would accept the symlink; an absent root isn't a missing template.
        alias = self.root / "alias"
        alias.symlink_to(self.repo, target_is_directory=True)
        plain = self.root / "plain"
        plain.touch()
        for candidate in (alias, plain, self.root / "absent"):
            with self.subTest(candidate=candidate.name):
                lines = self.assert_report(self.run_main(candidate), 1, FAIL, "FAIL unsafe-input")
                self.assertEqual(lines, ["FAIL unsafe-input", FAIL])

    def test_c2_2_missing(self):
        # Neither an existing non-file nor an alias to a valid file is an acceptable source.
        reason = f"FAIL missing {MARKET}"
        self.assert_report(self.run_main(), 1, FAIL, reason)
        target = self.root / "target.html"
        target.write_bytes(self.real_bytes)
        self.market.parent.mkdir(parents=True)
        self.market.symlink_to(target)
        self.assert_report(self.run_main(), 1, FAIL, reason)
        self.market.rename(self.market.with_name("alias.html"))
        self.market.mkdir()
        self.assert_report(self.run_main(), 1, FAIL, reason)
        # Keep a valid file behind a directory alias as well.
        self.market.rename(self.market.with_name("not-a-file"))
        self.write_market(self.real_bytes)
        past_home = self.market.parent.with_name("copied-home")
        self.market.parent.rename(past_home)
        self.market.parent.symlink_to(past_home, target_is_directory=True)
        self.assert_report(self.run_main(), 1, FAIL, reason)

    def test_c2_3_unrecorded_edit(self):
        # A valid-looking file at the right path is not proof its bytes are recorded.
        self.write_market(b"<main>synthetic replacement</main>")
        self.assert_report(self.run_main(), 1, FAIL,
                           f"FAIL unrecorded-edit {MARKET}", f"FAIL broken-chain {MARKET} 0")

    def test_c2_4_broken_chain(self):
        # Break only the older span; a checker that stops after the first link misses it.
        self.write_market(self.real_bytes)
        rows = tuple((*row[:4], row[4] + "synthetic damage") if row[1].startswith("de5bf19d31cd") else row
                     for row in template_compat.TEMPLATE_EDITS)
        with patch.object(checker, "TEMPLATE_EDITS", rows), patch.object(template_compat, "TEMPLATE_EDITS", rows):
            lines = self.assert_report(self.run_main(), 1, FAIL, f"FAIL broken-chain {MARKET} 1")
        self.assertIn(f"path {MARKET} current-recorded yes", lines)
        self.assertIn("steps 1", lines)

        # A known older version can start the walk, but it is not the current head.
        previous = template_compat.previous_bytes(MARKET, self.real_bytes)
        self.assertIsNotNone(previous)
        self.write_market(previous)
        lines = self.assert_report(self.run_main(), 1, FAIL, f"FAIL broken-chain {MARKET} 1")
        self.assertIn(f"path {MARKET} current-recorded no", lines)

    def test_c3_usage_exit_2(self):
        # Syntax errors must not become data findings or print a report trailer.
        for args, error in (
            ((), "the following arguments are required: --repo"),
            (("--repo",), "argument --repo: expected one argument"),
            (("--repo", str(self.repo), "--unknown"), "unrecognized arguments"),
        ):
            with self.subTest(error=error):
                result = self.run_cli(*args)
                self.assertEqual(result.returncode, 2)
                self.assertEqual(result.stdout, "")
                self.assertEqual(result.stderr.splitlines()[-1], f"{SCRIPT.name}: error: {error}")

    def test_c4_read_only(self):
        # Even rewriting identical bytes or staging a transient output changes metadata.
        self.write_market(self.real_bytes)

        def snapshot():
            return {path.relative_to(self.root): (path.stat().st_mtime_ns,
                                                 path.read_bytes() if path.is_file() else None)
                    for path in (self.root, *self.root.rglob("*"))}

        before = snapshot()
        self.assert_report(self.run_cli("--repo", str(self.repo)), 0, PASS)
        self.assertEqual(snapshot(), before)

    def test_c5_no_private_values(self):
        # Debug output and exception/argument diagnostics must not dump the data they inspect.
        self.write_market(self.real_bytes)
        success = self.run_cli("--repo", str(self.repo))
        self.assert_report(success, 0, PASS)
        comment = "<!-- synthetic-private-comment -->"
        self.write_market(self.real_bytes + comment.encode())
        edited = self.run_cli("--repo", str(self.repo))
        self.assert_report(edited, 1, FAIL, f"FAIL unrecorded-edit {MARKET}", f"FAIL broken-chain {MARKET} 0")
        usage = self.run_cli("--repo", str(self.repo), str(self.market))
        self.assertEqual(usage.returncode, 2)
        self.assertEqual(usage.stdout, "")
        self.assertEqual(usage.stderr.splitlines()[-1], f"{SCRIPT.name}: error: unrecognized arguments")
        with patch.object(checker, "TEMPLATE_EDITS", ((str(self.market), "a" * 64, "b" * 64, "x", "y"),)):
            invalid_path = self.run_main()
        self.assertEqual(self.assert_report(invalid_path, 1, FAIL, "FAIL unsafe-input"), ["FAIL unsafe-input", FAIL])
        spans = [span for row in template_compat.TEMPLATE_EDITS for span in row[3:] if span]
        for result in (success, edited, usage, invalid_path):
            for marker in (comment, str(self.repo), str(self.market), *spans):
                self.assertFalse(marker in result.stdout + result.stderr, "report exposed an input value")

    def test_c6_real_chain(self):
        # Pin the observed versions and order, not just an aggregate count or success flag.
        self.write_market(self.real_bytes)
        lines = self.assert_report(self.run_main(), 0, PASS)
        self.assertEqual(lines, [f"path {MARKET} current-recorded yes", "step 0 af71aa5aa59a",
                                 "step 1 de5bf19d31cd", "step 2 4ae952157505", "steps 2", "recorded 2", PASS])
        self.assertIsNone(template_compat.previous_bytes("hass/templates/other.html", self.real_bytes))

    def test_c7_one_byte_edit(self):
        # Even a trailing newline, invisible to a normalizing hash, invalidates the chain.
        self.write_market(self.real_bytes + b"\n")
        lines = self.assert_report(self.run_main(), 1, FAIL,
                                   f"FAIL unrecorded-edit {MARKET}", f"FAIL broken-chain {MARKET} 0")
        self.assertIn(f"path {MARKET} current-recorded no", lines)
