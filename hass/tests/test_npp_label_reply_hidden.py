"""Offline drift guard for scripts/hass/npp_label_reply_hidden.py (no network, fixtures only).

Each test names the CONTRACT item it pins; the believable bug is a later change to
label_reader's reply lines that names a hidden maker or held product, or alters a pinned line.
"""

import contextlib
import importlib.util
import io
import os
from pathlib import Path
import subprocess
import sys
import unittest
from unittest import mock

from hass import label_reader, voice

ROOT = Path(__file__).resolve().parents[2]
SCRIPT = ROOT / "scripts/hass/npp_label_reply_hidden.py"
TRAILER_PASS = "PASS npp_label_reply_hidden"
TRAILER_FAIL = "FAIL npp_label_reply_hidden"

# C2.1 trigger: a maker line that ignores the hidden flag.
IGNORES_HIDDEN = (lambda found, makers: (
    lambda names: f" I know the maker as {voice.quote(names[0])}." if len(names) == 1 else ""
)([m["name"] for m in makers.values() if label_reader.catalog._same(m["name"], found.get("brand", ""))]))


def load():
    spec = importlib.util.spec_from_file_location("npp_label_reply_hidden_under_test", SCRIPT)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def run_main(patches=()):
    """Run main() in-process with the given mock patches; every patch is undone on exit."""
    module = load()
    out = io.StringIO()
    with contextlib.ExitStack() as stack:
        for patch in patches:
            stack.enter_context(patch)
        with contextlib.redirect_stdout(out):
            code = module.main([])
    return code, out.getvalue().splitlines()


def finds(lines):
    return [line for line in lines if line.startswith("FAIL ") and line != TRAILER_FAIL]


def snapshot():
    state = {}
    for tree in ("hass", "storefront-mockup"):
        for dirpath, dirnames, filenames in os.walk(ROOT / tree):
            for name in dirnames + filenames:
                path = Path(dirpath, name)
                info = path.lstat()
                state[str(path)] = (info.st_size, info.st_mtime_ns)
    return state


class NppLabelReplyHiddenTests(unittest.TestCase):
    def test_c1_full_pass(self):
        # A pass must exit 0 and end on the exact PASS trailer, with 11 case lines first.
        code, lines = run_main()
        self.assertEqual(code, 0)
        self.assertEqual(lines[-1], TRAILER_PASS)
        self.assertEqual(len(lines), 12)
        result = subprocess.run([sys.executable, "-B", str(SCRIPT)], cwd=ROOT, capture_output=True,
                                text=True, timeout=30)
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(result.stdout.splitlines()[-1], TRAILER_PASS)

    def test_c2_findings_trailer(self):
        # Any finding exits 1 and the last line is the exact FAIL trailer.
        code, lines = run_main([mock.patch.object(label_reader, "_maker_line", IGNORES_HIDDEN)])
        self.assertEqual(code, 1)
        self.assertEqual(lines[-1], TRAILER_FAIL)

    def test_c2_1_hidden_or_held_shown(self):
        # A maker line that ignores the hidden flag names the hidden maker (case 2).
        code, lines = run_main([mock.patch.object(label_reader, "_maker_line", IGNORES_HIDDEN)])
        self.assertEqual(code, 1)
        self.assertEqual(finds(lines), ["FAIL hidden-or-held-shown 2", "FAIL line-changed 2"])
        self.assertEqual(lines[-1], TRAILER_FAIL)
        # Findings print right after their case line, hidden-or-held-shown first.
        at = lines.index("FAIL hidden-or-held-shown 2")
        self.assertTrue(lines[at - 1].startswith("case 2 maker="))
        self.assertEqual(lines[at + 1], "FAIL line-changed 2")

    def test_c2_1b_held_product_shown(self):
        # A product line that also names held products must flag case 8 (the held jam).
        def shows_held(found, products):
            twin = label_reader.catalog._twin(
                type("C", (), {"products": products}), found["name"], found["brand"]) if "brand" in found else None
            return f" {voice.quote(twin['name'])} is already on the website." if twin else ""
        code, lines = run_main([mock.patch.object(label_reader, "_product_line", shows_held)])
        self.assertEqual(code, 1)
        self.assertIn("FAIL hidden-or-held-shown 8", lines)
        self.assertEqual(lines[-1], TRAILER_FAIL)

    def test_c2_2_line_changed(self):
        # Any wording change shows as line-changed, never silently accepted.
        code, lines = run_main([mock.patch.object(voice, "quote", lambda s: s)])
        self.assertEqual(code, 1)
        self.assertTrue(finds(lines))
        self.assertTrue(all(line.startswith("FAIL line-changed ") for line in finds(lines)))
        self.assertEqual(lines[-1], TRAILER_FAIL)

    def test_c2_3_check_error(self):
        # A raising repo call is one named FAIL, no exception text, and no further case runs.
        def boom(*_args):
            raise RuntimeError("secret detail")
        code, lines = run_main([mock.patch.object(label_reader, "_maker_line", boom)])
        self.assertEqual(code, 1)
        self.assertEqual(lines, ["FAIL check-error", TRAILER_FAIL])
        # Failing at a later (product) case: earlier cases printed, later ones not.
        code, lines = run_main([mock.patch.object(label_reader, "_product_line", boom)])
        self.assertEqual(code, 1)
        self.assertEqual(lines[-2:], ["FAIL check-error", TRAILER_FAIL])
        self.assertEqual(lines.count("FAIL check-error"), 1)
        self.assertEqual(sum(line.startswith("case ") for line in lines), 6)

    def test_c3_usage_exit_2(self):
        # argparse's own exit 2 for a positional or unknown flag, nothing on stdout.
        for extra in (["positional"], ["--nope"]):
            with self.subTest(extra=extra):
                result = subprocess.run([sys.executable, "-B", str(SCRIPT), *extra], cwd=ROOT,
                                        capture_output=True, text=True, timeout=30)
                self.assertEqual(result.returncode, 2)
                self.assertEqual(result.stdout, "")

    def test_c4_read_only(self):
        # The run creates or changes no file under hass/ or storefront-mockup/.
        before = snapshot()
        result = subprocess.run([sys.executable, "-B", str(SCRIPT)], cwd=ROOT, capture_output=True,
                                text=True, timeout=30)
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(snapshot(), before)

    def test_c5_output_shape(self):
        # Only case lines, FAIL findings of the named forms, and the trailer; stderr empty.
        result = subprocess.run([sys.executable, "-B", str(SCRIPT)], cwd=ROOT, capture_output=True,
                                text=True, timeout=30)
        self.assertEqual(result.stderr, "")
        lines = result.stdout.splitlines()
        self.assertEqual(lines[-1], TRAILER_PASS)
        for index, line in enumerate(lines[:-1]):
            self.assertRegex(line, rf"^case {index} (maker|product)=")
        # And with findings and an error, every line still has a named form.
        shapes = r"^(case \d+ (maker|product)=.*|FAIL (hidden-or-held-shown|line-changed) \d+|FAIL check-error|(PASS|FAIL) npp_label_reply_hidden)$"
        for patch in (mock.patch.object(label_reader, "_maker_line", IGNORES_HIDDEN),
                      mock.patch.object(voice, "quote", lambda s: s)):
            _code, mutated = run_main([patch])
            for line in mutated:
                self.assertRegex(line, shapes)

    def test_c6_fixture(self):
        # Without voice marks the quoted lines (0, 1, 6, 7) change and nothing else.
        code, lines = run_main([mock.patch.object(voice, "quote", lambda s: s)])
        self.assertEqual(code, 1)
        self.assertEqual(finds(lines), [f"FAIL line-changed {i}" for i in (0, 1, 6, 7)])
        self.assertEqual(lines[-1], TRAILER_FAIL)

    def test_c7_live_pins(self):
        # The eleven measured lines, exactly, in order, with no finding.
        module = load()
        code, lines = run_main()
        self.assertEqual(code, 0)
        self.assertEqual(lines[:-1], module.EXPECTED)
        self.assertEqual(lines[:-1], [
            "case 0 maker=' I know the maker as \\ue000Cedar Row Apiary\\ue001.'",
            "case 1 maker=' I know the maker as \\ue000Cedar Row Apiary\\ue001.'",
            "case 2 maker=''",
            "case 3 maker=''",
            "case 4 maker=''",
            "case 5 maker=''",
            "case 6 product=' \\ue000Wildflower Honey\\ue001 is already on the website."
            " Reply with that name if you want to update it instead.'",
            "case 7 product=' \\ue000Rye Loaf\\ue001 is already saved, but hidden from the website."
            " Reply with that name if you want to update it instead.'",
            "case 8 product=''",
            "case 9 product=''",
            "case 10 product=''",
        ])
        self.assertEqual(lines[-1], TRAILER_PASS)
        self.assertEqual(module.MUST_SILENT, (2, 8))


if __name__ == "__main__":
    unittest.main()
