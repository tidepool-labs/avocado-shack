"""Numbered CLI contracts for the offline town wording report."""

from contextlib import redirect_stderr, redirect_stdout
import importlib.util
import io
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import patch


SCRIPT = Path(__file__).resolve().parents[2] / "scripts/hass/npp_town_wording_check.py"
SPEC = importlib.util.spec_from_file_location("npp_town_wording_check", SCRIPT)
assert SPEC is not None and SPEC.loader is not None
checker = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(checker)
PASS = "PASS npp_town_wording_check"
FAIL = "FAIL npp_town_wording_check"


class TownWordingCheckTests(unittest.TestCase):
    def setUp(self):
        temporary = tempfile.TemporaryDirectory()
        self.addCleanup(temporary.cleanup)
        self.root = Path(temporary.name).resolve()
        self.places = self.root / "fixture-places.txt"

    def cli(self, *args):
        result = subprocess.run(
            [sys.executable, "-B", str(SCRIPT), *map(str, args)],
            cwd=self.root, capture_output=True, text=True, timeout=10,
        )
        return result.returncode, result.stdout, result.stderr

    def in_process(self, *args):
        stdout, stderr = io.StringIO(), io.StringIO()
        with redirect_stdout(stdout), redirect_stderr(stderr):
            status = checker.main(list(map(str, args)))
        return status, stdout.getvalue(), stderr.getvalue()

    def assert_run(self, result, status, trailer):
        code, stdout, stderr = result
        self.assertEqual(code, status)
        self.assertEqual(stderr, "")
        lines = stdout.splitlines()
        self.assertTrue(lines)
        self.assertEqual(lines[-1], trailer)
        return lines[:-1]

    def assert_finding(self, result, reason):
        lines = self.assert_run(result, 1, FAIL)
        self.assertEqual([line for line in lines if line.startswith("FAIL ")], [f"FAIL {reason}"])
        return [line for line in lines if not line.startswith("FAIL ")]

    def test_c1_full_pass(self):
        # A successful check must have the PASS trailer, not just a zero status.
        self.places.write_bytes(b"  \n")
        self.assert_run(self.cli("--places", self.places), 0, PASS)

    def test_c2_findings_trailer(self):
        # A validation short circuit must not omit the common failure trailer.
        self.assertEqual(self.assert_finding(self.cli("--places", self.places), "unsafe-input"), [])

    def test_c2_1_unsafe_input(self):
        # Following an input symlink would accept its correctly typed target.
        self.places.touch()
        file_link = self.root / "file-link"
        file_link.symlink_to(self.places)
        content = self.root / "content"
        content.mkdir()
        dir_link = self.root / "dir-link"
        dir_link.symlink_to(content, target_is_directory=True)
        for flag, source in (("--places", file_link), ("--places", content),
                             ("--content", dir_link), ("--content", self.places)):
            with self.subTest(flag=flag, input_name=source.name):
                self.assert_finding(self.cli(flag, source), "unsafe-input")

    def test_c2_2_unreadable_input(self):
        # Lossy decoding or swallowing an open failure would silently skip input.
        self.places.write_bytes(b"\xff")
        self.assert_finding(self.cli("--places", self.places), "unreadable-input")
        with patch.object(Path, "open", side_effect=PermissionError("fixture open failure")):
            self.assert_finding(self.in_process("--places", self.places), "unreadable-input")

    def test_c2_3_too_large(self):
        # The exact byte boundary is allowed; reading only a prefix is not.
        self.places.write_bytes(b" " * 65536)
        self.assert_run(self.cli("--places", self.places), 0, PASS)
        self.places.write_bytes(b" " * 65537)
        self.assert_finding(self.cli("--places", self.places), "too-large")

    def test_c2_4_too_many_lines(self):
        # The line limit counts blank physical lines before filtering them out.
        self.places.write_bytes(b"\r\n" * 500)
        self.assert_run(self.cli("--places", self.places), 0, PASS)
        self.places.write_bytes(b"\r\n" * 500 + b" ")
        self.assert_finding(self.cli("--places", self.places), "too-many-lines")

    def test_c2_5_content_invalid(self):
        # An existing directory is not sufficient; the loader must succeed.
        (self.root / "products.json").write_bytes(b"{")
        self.assert_finding(self.cli("--content", self.root), "content-invalid")

    def test_c2_6_check_error(self):
        # A broken predicate must not be reported as normal non-acceptance.
        self.places.write_bytes(b"Example Hollow\n")
        for module, name in ((checker.stages, "_site_words"), (checker.makers, "rule_town_state")):
            with self.subTest(check=name):
                with patch.object(module, name, side_effect=RuntimeError("fixture check failure")):
                    self.assert_finding(self.in_process("--places", self.places), "check-error")

    def test_c2_7_disagree(self):
        # Agreement to reject is informational, unlike a one-sided acceptance.
        self.places.write_bytes(b"?\n")
        self.assertIn("neither 1", self.assert_run(self.cli("--places", self.places), 0, PASS))
        self.places.write_bytes(b"?\nExample Hollow, CA\n")
        lines = self.assert_finding(self.cli("--places", self.places), "disagree 1")
        self.assertIn("editor-only 1", lines)
        self.assertIn("neither 1", lines)

    def test_c3_usage_exit_2(self):
        # Optional-group or implicit path fallback would bypass usage handling.
        self.places.touch()
        for args in ((), ("--places", self.places, "--unknown"), ("--places",), ("--content",),
                     ("--places", self.places, "--content", self.root)):
            with self.subTest(option_count=len(args)):
                code, stdout, stderr = self.cli(*args)
                self.assertEqual(code, 2)
                self.assertEqual(stdout, "")
                self.assertTrue(stderr.startswith("usage:"))

    def test_c4_read_only(self):
        # In-place normalization or creating a report would change the snapshot.
        self.places.write_bytes(b" Example Hollow, CA \r\n")
        content = self.root / "content"
        content.mkdir()
        for name, payload in {
            "products": b', "products": []',
            "makers": b', "makers": {"fixture": {"place": "Example Hollow, CA"}}',
            "community": b"", "store": b"",
        }.items():
            (content / f"{name}.json").write_bytes(b'{"schemaVersion": 1' + payload + b"}\n")

        def snapshot():
            return {path.relative_to(self.root): (path.stat().st_mtime_ns,
                                                   path.read_bytes() if path.is_file() else None)
                    for path in (self.root, *self.root.rglob("*"))}

        before = snapshot()
        self.assert_finding(self.cli("--places", self.places), "disagree 1")
        self.assertEqual(snapshot(), before)
        self.assert_finding(self.cli("--content", content), "disagree 1")
        self.assertEqual(snapshot(), before)

    def test_c5_no_private_values(self):
        # A per-place finding, raw exception, or argparse error could echo inputs.
        place = "Synthetic Beacon Hollow, CA"
        self.places.write_text(place, encoding="utf-8")
        report = self.cli("--places", self.places)
        self.assert_finding(report, "disagree 1")
        with patch.object(checker.content_model, "load_content",
                          side_effect=ValueError(f"{self.root}: {place}")):
            invalid = self.in_process("--content", self.root)
        self.assert_finding(invalid, "content-invalid")
        usage = self.cli("--places", self.places, self.root, place)
        self.assertEqual(usage[:2], (2, ""))
        for _, stdout, stderr in (report, invalid, usage):
            for canary in (place, str(self.places), str(self.root)):
                self.assertTrue(canary not in stdout + stderr, "input leaked")

    def test_c6_empty_list(self):
        # Stripped blank rows should never reach either rule as an empty town.
        self.places.write_bytes(b"\n\t\r\n \n")
        lines = self.assert_run(self.cli("--places", self.places), 0, PASS)
        self.assertEqual(lines, ["places 0", "both 0", "npp-only 0", "editor-only 0", "neither 0"])

    def test_c7_two_forms(self):
        # Normalizing the comma or treating a Refusal as an error hides the split.
        self.places.write_bytes(b" Watsonville\n\n\tWatsonville, CA \n")
        lines = self.assert_finding(self.cli("--places", self.places), "disagree 2")
        self.assertEqual(lines, ["places 2", "both 0", "npp-only 1", "editor-only 1", "neither 0"])

    def test_c8_live_places(self):
        # Pin the integration result on the checked-in catalog, not runtime data.
        result = self.cli("--content", checker.content_model.CONTENT_DIR)
        lines = self.assert_finding(result, "disagree 23")
        self.assertEqual(lines, ["places 26", "both 0", "npp-only 3", "editor-only 20", "neither 3"])
