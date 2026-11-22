"""Fixture-only CLI contracts for the offline interpreter prompt report."""

from contextlib import redirect_stderr, redirect_stdout
import importlib.util
import io
import json
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import patch


SCRIPT = Path(__file__).resolve().parents[2] / "scripts/hass/prompt_size_report.py"
PASS = "PASS prompt_size_report"
FAIL = "FAIL prompt_size_report"
DESCRIPTION = "Synthetic café description canary."
STORY = "Synthetic maker story canary."


class PromptSizeReportTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        spec = importlib.util.spec_from_file_location("prompt_size_report", SCRIPT)
        assert spec is not None and spec.loader is not None
        cls.tool = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(cls.tool)

    def setUp(self):
        scratch = tempfile.TemporaryDirectory()
        self.addCleanup(scratch.cleanup)
        self.root = Path(scratch.name).resolve()
        self.content = self.root / "synthetic-content"
        self.content.mkdir()
        self.write_content()

    def write_content(self, count=1, description=DESCRIPTION):
        products = []
        for number in range(1, count + 1):
            product_id = f"photo-product-{number:03d}"
            products.append({
                "id": product_id, "name": f"Fixture Jam {number}",
                "brand": "Fixture Maker", "displayBrand": "Fixture Maker",
                "category": "pantry", "image": f"assets/products/{product_id}.webp",
                "description": description, "status": "active", "producerKey": "harbor-lane",
            })
        documents = {
            "products": {"products": products},
            "makers": {"makers": {"harbor-lane": {
                "name": "Fixture Maker", "place": "Testville, California", "story": STORY,
            }}},
            "community": {
                "club": {"clubName": "Fixture Club", "organizer": "Fixture Organizer",
                         "intendedSender": "club@example.com", "emailConnected": False},
                "events": [], "routeIdeas": [],
            },
            "store": {"name": "Fixture Store", "streetAddress": "1 Example Lane",
                      "town": "Testville, California",
                      "hours": ["Monday-Friday 9am-5pm", "Closed Saturday-Sunday"]},
        }
        for name, data in documents.items():
            (self.content / f"{name}.json").write_text(
                json.dumps({"schemaVersion": 1, **data}, ensure_ascii=False), encoding="utf-8",
            )

    def cli(self, *args):
        return subprocess.run(
            [sys.executable, "-B", str(SCRIPT), *args], cwd=self.root,
            capture_output=True, text=True, timeout=15,
        )

    def invoke(self, *options):
        return self.cli("--content", str(self.content), *options)

    def run_main(self, *options):
        with redirect_stdout(io.StringIO()) as stdout, redirect_stderr(io.StringIO()) as stderr:
            code = self.tool.main(["--content", str(self.content), *options])
        return subprocess.CompletedProcess([], code, stdout.getvalue(), stderr.getvalue())

    def assert_report(self, result, code, *findings):
        self.assertEqual(result.returncode, code, result.stderr)
        self.assertEqual(result.stderr, "")
        lines = result.stdout.splitlines()
        self.assertEqual(lines[-1:], [PASS if code == 0 else FAIL])
        self.assertEqual([line for line in lines[:-1] if line.startswith("FAIL ")],
                         [f"FAIL {finding}" for finding in findings])
        return lines[:-1 - len(findings)]

    def test_c1_full_pass(self):
        # A missing metric, changed ordering, or char-based size corrupts the report.
        content = self.tool.load_and_validate(self.content, None)
        prompt = self.tool.interpreter_prompt.build(self.tool.load_registry(), content)
        size = len(prompt.encode("utf-8"))
        cap = self.tool.interpreter_prompt.PROMPT_MAX_BYTES
        self.assertGreater(size, len(prompt))
        self.assertEqual(self.assert_report(self.invoke(), 0), [
            f"bytes {size}", f"max {cap}", f"headroom {cap - size}",
            f"lines {len(prompt.splitlines())}", "products 1", "makers 1", "omitted 0",
        ])

    def test_c2_findings_trailer(self):
        # A fail-fast size check would hide the omission finding on the same run.
        builder = self.tool.interpreter_prompt
        with patch.object(builder, "build", return_value="x" * builder.PROMPT_MAX_BYTES
                          + f" | {builder.OMITTED}\n") as build:
            result = self.run_main("--max-omitted", "0")
        size = len(build.return_value.encode("utf-8"))
        self.assert_report(result, 1, f"over-max {size}", "omitted-over 1")

    def test_c2_1_unsafe_input(self):
        # Following a directory symlink, or validating a non-directory, is a regression.
        alias = self.root / "alias"
        alias.symlink_to(self.content, target_is_directory=True)
        for path in (alias, self.content / "products.json", self.root / "missing"):
            with self.subTest(path=path.name):
                self.assertEqual(self.assert_report(self.cli("--content", str(path)), 1,
                                                   "unsafe-input"), [])

    def test_c2_2_content_invalid(self):
        # Invalid schema and undecodable JSON must both produce only the named finding.
        for raw in (b'{"schemaVersion": 2}', b"\xff"):
            with self.subTest(raw=raw):
                (self.content / "store.json").write_bytes(raw)
                self.assertEqual(self.assert_report(self.invoke(), 1, "content-invalid"), [])

    def test_c2_3_build_error(self):
        # A builder exception cannot be a pass or expose the exception's private message.
        with patch.object(self.tool.interpreter_prompt, "build", side_effect=RuntimeError(STORY)):
            self.assertEqual(self.assert_report(self.run_main(), 1, "build-error"), [])

    def test_c2_4_over_max(self):
        # Compare byte length, with equality passing and one extra byte failing.
        builder = self.tool.interpreter_prompt
        cap = builder.PROMPT_MAX_BYTES
        at_cap = "é" + "x" * (cap - 2)
        with patch.object(builder, "build", return_value=at_cap):
            self.assertIn("headroom 0", self.assert_report(self.run_main(), 0))
        with patch.object(builder, "build", return_value=at_cap + "x"):
            self.assertIn("headroom -1", self.assert_report(self.run_main(), 1, f"over-max {cap + 1}"))

    def test_c2_5_omitted_over(self):
        # Count exact stripped fields, not lines, prose, quoted markers, or substrings.
        builder = self.tool.interpreter_prompt
        marker = builder.OMITTED
        prompt = (f"Rule: no {marker} values.\n{marker}\n"
                  f"row | prose with {marker} | \"{marker}\" | {marker}-suffix\n"
                  f"maker |   {marker}  | {marker}\nproduct | {marker}\n")
        with patch.object(builder, "build", return_value=prompt):
            for limit, code, findings in (("3", 0, ()), ("2", 1, ("omitted-over 3",))):
                with self.subTest(limit=limit):
                    self.assertIn("omitted 3", self.assert_report(self.run_main("--max-omitted", limit),
                                                                code, *findings))

    def test_c3_usage_exit_2(self):
        # Parser errors must not become report findings or accept invalid integer limits.
        for options in (None, ("--unknown",), ("--max-omitted", "-1"),
                        ("--max-omitted", "1.5"), ("--max-omitted", "no")):
            with self.subTest(options=options):
                result = self.cli() if options is None else self.invoke(*options)
                self.assertEqual(result.returncode, 2)
                self.assertEqual(result.stdout, "")  # no last stdout line on usage errors
                self.assertTrue(result.stderr.startswith("usage:"))

    def test_c4_read_only(self):
        # Rewriting an input with identical bytes or leaving a sidecar must be detected.
        def snapshot():
            return (self.content.stat().st_mtime_ns, {
                path.relative_to(self.content): (path.stat().st_mtime_ns,
                                                 None if path.is_dir() else path.read_bytes())
                for path in self.content.rglob("*")
            })

        before = snapshot()
        self.assert_report(self.invoke(), 0)
        self.assertEqual(snapshot(), before)

    def test_c5_no_private_values(self):
        # Prompt dumps, validation details and argparse's default arg echo would leak data.
        def assert_private(result):
            for value in (DESCRIPTION, STORY, "Fixture Maker", "photo-product-001", str(self.content)):
                self.assertNotIn(value, result.stdout + result.stderr)

        passed = self.invoke()
        assert_private(passed)
        self.assert_report(passed, 0)
        (self.content / "products.json").write_text(
            json.dumps({"schemaVersion": 1, DESCRIPTION: STORY, "products": []}), encoding="utf-8",
        )
        invalid = self.invoke()
        assert_private(invalid)
        self.assert_report(invalid, 1, "content-invalid")
        usage = self.invoke("--unknown", str(self.content))
        assert_private(usage)
        self.assertEqual((usage.returncode, usage.stdout), (2, ""))

    def test_c6_minimal(self):
        # Unconditionally counting the rule prose as omissions fails this zero limit.
        lines = self.assert_report(self.invoke("--max-omitted", "0"), 0)
        report = dict(line.split(" ", 1) for line in lines)
        self.assertEqual(report["omitted"], "0")
        self.assertGreater(int(report["headroom"]), 0)

    def test_c7_crowded(self):
        # Counting only source texts, rather than marker fields in the built prompt, misses real omissions.
        self.write_content(300, "Sweet jam." * 30)
        lines = self.assert_report(self.invoke(), 0)
        report = dict(line.split(" ", 1) for line in lines)
        self.assertEqual(report["products"], "300")
        self.assertGreater(int(report["omitted"]), 0)
        self.assertEqual(self.assert_report(self.invoke("--max-omitted", "0"), 1,
                                           f"omitted-over {report['omitted']}"), lines)


if __name__ == "__main__":
    unittest.main()
