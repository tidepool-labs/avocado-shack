"""Exercise the offline checker at the selector's serialized request boundary."""

from contextlib import redirect_stderr, redirect_stdout
from dataclasses import replace
import importlib.util
import io
import json
from pathlib import Path
import subprocess
import sys
from tempfile import TemporaryDirectory
import unittest
from unittest.mock import patch


ROOT = Path(__file__).resolve().parents[2]
SCRIPT = ROOT / "scripts/hass/npp_selector_body_privacy.py"
PASS = "PASS npp_selector_body_privacy"
FAIL = "FAIL npp_selector_body_privacy"
COUNTS = ["case A requests=1", "case B requests=1", "case C requests=1"]

spec = importlib.util.spec_from_file_location("npp_selector_body_privacy", SCRIPT)
assert spec is not None and spec.loader is not None
checker = importlib.util.module_from_spec(spec)
spec.loader.exec_module(checker)
copy = checker.copy


def patch_transport(transform):
    """Run the real selector; observe or mutate only what reaches its fake sink."""
    selector = copy.codex_selector

    def wrapped(transport):
        def relay(url, body, headers, timeout):
            return transport(url, transform(body), headers, timeout)
        return selector(transport=relay)

    return patch.object(copy, "codex_selector", wrapped)


class SelectorBodyPrivacyTests(unittest.TestCase):
    def cli(self, *args):
        with TemporaryDirectory() as scratch:
            return subprocess.run([sys.executable, "-B", str(SCRIPT), *args], cwd=scratch,
                                  text=True, capture_output=True, timeout=10)

    def run_main(self):
        out, err = io.StringIO(), io.StringIO()
        with redirect_stdout(out), redirect_stderr(err):
            status = checker.main([])
        self.assertEqual(err.getvalue(), "")
        return status, out.getvalue().splitlines()

    def test_c1_full_pass(self):
        # A false alarm on the pinned prompt or an incorrect success code breaks the CLI.
        result = self.cli()
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(result.stdout.splitlines()[-1], PASS)

    def test_c2_findings_trailer(self):
        # A bad request can violate both rules; the first finding must not mask the rest.
        with patch_transport(lambda body: body + b"\nplonkwise"):
            self.assertEqual(self.run_main(), (1, COUNTS + [
                "FAIL value-in-body A 3", "FAIL options-shape A",
                "FAIL value-in-body B 3", "FAIL options-shape B",
                "FAIL value-in-body C 3", "FAIL options-shape C", FAIL,
            ]))

    def test_c2_1_value_in_body(self):
        # A leak in the prompt (outside options) must be caught once per index, regardless of case.
        selector = copy.codex_selector

        def prepend_private_words(transport):
            select = selector(transport=transport)

            def wrapped(step, prompt, schema, options):
                return select(step, "VEXMOOR vexmoor 8642\n" + prompt, schema, options)
            return wrapped

        with patch.object(copy, "codex_selector", prepend_private_words):
            self.assertEqual(self.run_main(), (1, COUNTS + [
                f"FAIL value-in-body {case} {index}" for case in "ABC" for index in (2, 5)
            ] + [FAIL]))

    def test_c2_2_no_request(self):
        # Early rejection by the real writer is not evidence of a private payload.
        write = copy.Writer.write

        def reject_brand_case(writer, ctx, select):
            if ctx.brand:
                ctx = replace(ctx, kind="unsupported")
            return write(writer, ctx, select)

        with patch.object(copy.Writer, "write", reject_brand_case):
            self.assertEqual(self.run_main(), (1, [COUNTS[0], "case B requests=0", COUNTS[2],
                                                   "FAIL no-request B", FAIL]))

    def test_c2_3_options_shape(self):
        # Distinct transport regressions, none relying on a sentinel leak to fail.
        for name, transform, cases in (
            ("non-json", lambda _body: b"not JSON", "ABC"),
            ("no marker", lambda body: body.replace(b"Eligible IDs:", b"Choices:"), "ABC"),
            ("missing key", lambda body: body.replace(b"phrase_ids", b"phrases"), "ABC"),
            ("bad fact ID", lambda body: body.replace(b"official-makes", b"official-makes2"), "A"),
        ):
            with self.subTest(name=name), patch_transport(transform):
                self.assertEqual(self.run_main(), (1, COUNTS + [
                    f"FAIL options-shape {case}" for case in cases
                ] + [FAIL]))

    def test_c2_4_check_error(self):
        # A late write failure must fail closed even if the captured request was clean.
        write = copy.Writer.write

        def fail_after_sending(writer, ctx, select):
            write(writer, ctx, select)
            raise RuntimeError("synthetic diagnostic must not be printed")

        with patch.object(copy.Writer, "write", fail_after_sending):
            self.assertEqual(self.run_main(), (1, COUNTS + ["FAIL check-error", FAIL]))
        with patch.object(copy, "Writer", side_effect=RuntimeError("synthetic diagnostic")):
            self.assertEqual(self.run_main(), (1, ["FAIL check-error", FAIL]))

    def test_c3_usage_exit_2(self):
        # Silent argument acceptance would make a mistyped invocation look qualified.
        for arg in ("unexpected", "--unknown", "--help", "--"):
            with self.subTest(arg=arg):
                result = self.cli(arg)
                self.assertEqual((result.returncode, result.stdout), (2, ""))
                self.assertTrue(result.stderr.startswith("usage: "))

    def test_c4_read_only(self):
        # Catch payload dumps and asset rewrites, including new files or directories.
        def snapshot():
            entries = {}
            for name in ("hass", "storefront-mockup"):
                tree = ROOT / name
                for path in (tree, *tree.rglob("*")):
                    stat = path.lstat()
                    entries[path.relative_to(ROOT)] = (stat.st_size, stat.st_mtime_ns)
            return entries

        before = snapshot()
        result = self.cli()
        self.assertEqual((result.returncode, result.stdout.splitlines()[-1]), (0, PASS))
        self.assertEqual(snapshot(), before)

    def test_c5_output_shape(self):
        # Extra debugging on a successful run must not reveal the captured body.
        result = self.cli()
        self.assertEqual((result.returncode, result.stdout, result.stderr),
                         (0, "\n".join([*COUNTS, PASS, ""]), ""))

    def test_c6_fixture(self):
        # Mutate the real projection; the serializer must carry exactly what is checked.
        options = copy.Writer._options

        def leak_item(writer, ctx):
            return {**options(writer, ctx), "item": ctx.item}

        with patch.object(copy.Writer, "_options", leak_item):
            self.assertEqual(self.run_main(), (1, COUNTS + [
                "FAIL value-in-body A 0", "FAIL options-shape A",
                "FAIL value-in-body B 0", "FAIL options-shape B",
                "FAIL value-in-body C 8", "FAIL options-shape C", FAIL,
            ]))

    def test_c7_live_pins(self):
        # A dropped fact ID or a retry on the fake 500 would change baseline coverage.
        bodies = []

        def observe(body):
            bodies.append(body)
            return body

        with patch_transport(observe):
            self.assertEqual(self.run_main(), (0, COUNTS + [PASS]))
        self.assertEqual(len(bodies), 3)
        content = json.loads(bodies[0])["messages"][0]["content"]
        options = json.loads(content.rsplit("\nEligible IDs: ", 1)[1])
        self.assertEqual(options["fact_ids"], {"makes": "official-makes", "founded": "official-founded"})
