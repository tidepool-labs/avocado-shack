"""Fixture-only tests for scripts/hass/npp_claim_note_reach.py.

Each test names the contract item it pins (see the script's card) and the believable bug that turns it red.
"""

import ast
import contextlib
import dataclasses
import importlib.util
import inspect
import io
from pathlib import Path
import re
import subprocess
import sys
import textwrap
import unittest
from unittest import mock

REPO = Path(__file__).resolve().parents[2]
SCRIPT = REPO / "scripts/hass/npp_claim_note_reach.py"
TRAILER = "FAIL npp_claim_note_reach"
# C7: the live pin at main once the stage wiring landed (H14 claim note): every case reaches the note.
BASELINE = [
    "claim organic writer_input=yes writer_drop=yes card_note=yes",
    "claim health writer_input=yes writer_drop=yes card_note=yes",
    "claim no_claim writer_input=yes writer_drop=yes card_note=yes",
    "PASS npp_claim_note_reach",
]


def load():
    spec = importlib.util.spec_from_file_location("npp_claim_note_reach", SCRIPT)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def run_main(module, **options):
    out, err = io.StringIO(), io.StringIO()
    with contextlib.redirect_stdout(out), contextlib.redirect_stderr(err):
        code = module.main([], **options)
    return code, out.getvalue().splitlines(), err.getvalue()


def run_script(*args):
    return subprocess.run([sys.executable, "-B", str(SCRIPT), *args], cwd=REPO, capture_output=True, text=True, timeout=60)


def snapshot():
    return {str(path.relative_to(REPO)): (path.stat().st_size, path.stat().st_mtime_ns)
            for tree in ("hass", "storefront-mockup") for path in sorted((REPO / tree).rglob("*"))}


def _rebuilt(stages, name, edit):
    """A copy of the real ProductionStages method with one AST edit, compiled in memory (nothing on disk)."""
    tree = ast.parse(textwrap.dedent(inspect.getsource(getattr(stages.ProductionStages, name))))
    edit(tree)
    ast.fix_missing_locations(tree)
    namespace = dict(vars(stages))
    exec(compile(tree, f"<overlay {name}>", "exec"), namespace)
    return namespace[name]


def _expression(text):
    return ast.parse(text, mode="eval").body


def _drop_claims_from_plan(tree):
    for node in ast.walk(tree):
        if isinstance(node, ast.Dict) and any(isinstance(k, ast.Constant) and k.value == "labelClaims" for k in node.keys):
            index = next(i for i, k in enumerate(node.keys) if isinstance(k, ast.Constant) and k.value == "labelClaims")
            del node.keys[index], node.values[index]
            return
    raise AssertionError("listing projection moved")


def _unpass_claims_and_note(tree):
    function = tree.body[0]
    for node in ast.walk(function):
        if isinstance(node, ast.Call) and ast.unparse(node.func) == "copy.Context":
            kept = [k for k in node.keywords if k.arg != "label_claims"]
            if len(kept) == len(node.keywords):
                raise AssertionError("label_claims keyword moved")
            node.keywords = kept
            break
    else:
        raise AssertionError("Context call moved")
    for index, node in enumerate(function.body):
        if isinstance(node, ast.If) and ast.unparse(node.test) == "written.dropped":
            del function.body[index]
            return
    raise AssertionError("note parts moved")


def reference_stages(module, *, unused_tokens=False):
    """The production ProductionStages now carries S2's visible_claims through the Plan into Context and composes the
    Writer's omission into claim_left_off. With unused_tokens, a copy with that wiring cut out (in memory) where only a
    method nothing calls names the tokens: the behavioural probe must stay red on it."""
    stages = module.stages
    if not unused_tokens:
        return stages.ProductionStages

    def unused(self, ctx, written):
        return ctx.label_claims, written.dropped, "claim_left_off"
    return type("Disconnected", (stages.ProductionStages,), {
        "_unused": unused,
        "start_plan": _rebuilt(stages, "start_plan", _drop_claims_from_plan),
        "render_listing": _rebuilt(stages, "render_listing", _unpass_claims_and_note)})


def clear_dropped(written):
    return dataclasses.replace(written, dropped=())


class ClaimNoteReachTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.module = load()

    def test_c1_full_pass(self):
        # C1: with the claim carried through, exit 0 and the last line is PASS. Fails if the PASS line or code is wrong.
        code, lines, err = run_main(self.module, stages_class=reference_stages(self.module))
        self.assertEqual((code, err), (0, ""))
        self.assertEqual(lines[-1], "PASS npp_claim_note_reach")
        self.assertEqual(len(lines), 4)

    def fake(self, **flags):
        rows = [(label, *(flags.get(label, (True, True, True))), "") for label in ("organic", "health", "no_claim")]
        return mock.patch.object(self.module, "probe", return_value=rows)

    def assert_findings(self, flags, reasons):
        with self.fake(**flags):
            code, lines, _ = run_main(self.module)
        self.assertEqual(code, 1)
        self.assertEqual([line for line in lines if line.startswith("FAIL")], [*(f"FAIL {r}" for r in reasons), TRAILER])
        self.assertEqual(lines[-1], TRAILER)

    def test_c2_findings_trailer(self):
        # C2: every finding is ordered, exit 1, and the trailer is last. Fails if the order or trailer drifts.
        self.assert_findings({"health": (False, False, False)},
                             ["label-claims-unpassed", "writer-drop-mismatch", "claim-note-mismatch"])

    def test_c2_1_label_claims_unpassed(self):
        # C2.1: only a Writer-input mismatch. Fails if input is not judged independently of drop and note.
        self.assert_findings({"organic": (False, True, True)}, ["label-claims-unpassed"])

    def test_c2_2_writer_drop_mismatch(self):
        # C2.2: only an omission mismatch.
        self.assert_findings({"health": (True, False, True)}, ["writer-drop-mismatch"])

    def test_c2_3_claim_note_mismatch(self):
        # C2.3: only a note mismatch (a control that gains a left-off part also counts).
        self.assert_findings({"no_claim": (True, True, False)}, ["claim-note-mismatch"])

    def test_c2_4_check_error(self):
        # C2.4: an incomplete probe prints only check-error and the trailer, with no exception text.
        broken = (
            mock.patch.object(self.module, "probe", side_effect=RuntimeError("secret-detail")),
            mock.patch.object(self.module.stages.ProductionStages, "render_listing", return_value=None),  # no Card
            mock.patch.object(self.module.stages.ProductionStages, "start_plan", return_value=None),  # no Plan
        )
        for patcher in broken:
            with self.subTest(patcher=str(patcher)), patcher:
                code, lines, err = run_main(self.module)
            self.assertEqual((code, lines, err), (1, ["FAIL check-error", TRAILER], ""))

    def test_c3_usage_exit_2(self):
        # C3: argparse's exit 2 and an empty stdout for any argument.
        # --help and -h must not print help and exit 0 (a bug if argparse's automatic help is left on).
        for args in (("extra",), ("--unknown",), ("--help",), ("-h",)):
            with self.subTest(args=args):
                result = run_script(*args)
                self.assertEqual((result.returncode, result.stdout), (2, ""))
                self.assertIn("usage:", result.stderr)

    def test_c4_read_only(self):
        # C4: the run writes nothing under hass/ or storefront-mockup/ (e.g. a stray card PNG or .pyc).
        before = snapshot()
        result = run_script()
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(snapshot(), before)

    def test_c5_output_shape(self):
        # C5: only the fixed line forms on stdout, nothing on stderr; no claim or note text leaks.
        shapes = [re.compile(r"claim (organic|health|no_claim) writer_input=(yes|no) writer_drop=(yes|no) card_note=(yes|no)"),
                  re.compile(r"(FAIL (label-claims-unpassed|writer-drop-mismatch|claim-note-mismatch|check-error)|"
                             r"FAIL npp_claim_note_reach|PASS npp_claim_note_reach)")]
        unpatched = run_script()
        code, lines, err = run_main(self.module, stages_class=reference_stages(self.module))
        for lines, err in ((unpatched.stdout.splitlines(), unpatched.stderr), (lines, err)):
            self.assertEqual(err, "")
            self.assertTrue(all(any(s.fullmatch(line) for s in shapes) for line in lines), lines)
            for leak in ("Wildflower", "Organic", "immune", "left off", "unconfirmed"):
                self.assertNotIn(leak, "\n".join(lines))

    def test_c6_fixture(self):
        # C6: a reference overlay that carries the claim and composes the Writer's omission goes all-yes, and the note
        # follows the Writer's safe output. Fails if the probe cannot go green, cannot tell the two labels apart, or
        # passes with a hardcoded/unconditional note.
        reference = reference_stages(self.module)
        rows = self.module.probe(reference)
        self.assertEqual([row[:4] for row in rows], [("organic", True, True, True), ("health", True, True, True),
                                                     ("no_claim", True, True, True)])
        notes = {row[0]: row[4].split("; ") for row in rows}
        self.assertIn("left off: unconfirmed origin or organic wording", notes["organic"])
        self.assertIn("left off: immune support", notes["health"])
        self.assertFalse([p for p in notes["no_claim"] if p.startswith("left off: ")])
        self.assertNotIn("left off: immune support", notes["organic"])
        # Same reference, Writer's omission cleared: the claim cases lose the note; the control still matches.
        rows = self.module.probe(reference, clear_dropped)
        self.assertEqual([row[:4] for row in rows], [("organic", True, False, False), ("health", True, False, False),
                                                     ("no_claim", True, True, True)])
        # Old source-token checks pass on a disconnected overlay; the behavioural probe must stay red.
        rows = self.module.probe(reference_stages(self.module, unused_tokens=True))
        self.assertEqual([row[:4] for row in rows], [("organic", False, False, False), ("health", False, False, False),
                                                     ("no_claim", True, True, True)])

    def test_c8_one_printed_claim_read_at_two_widths_is_one_claim(self):
        # C8: S2 may read the same printed claim as 'Immune' and 'Immune support'. Bug it catches: both reach the Writer,
        # and the owner note says 'left off: health or award wording, immune support' for one claim on the label.
        widest = self.module.stages._widest_claims
        self.assertEqual(widest(["Immune", "Immune support"]), ["Immune support"])
        self.assertEqual(widest(["Organic", "USDA Organic", "Non-GMO", "non-gmo"]), ["USDA Organic", "Non-GMO"])
        self.assertEqual(widest(["Immune support", "Supports immunity"]), ["Immune support", "Supports immunity"])
        self.assertEqual(widest(["Raw", "Unfiltered", "", "!!"]), ["Raw", "Unfiltered"])
        self.assertEqual(widest(["support", "Immune support"]), ["Immune support"])  # not only a prefix

    def test_c7_live_pins(self):
        # C7: live pin at main: both claim cases and the control all-yes, no findings, exit 0.
        result = run_script()
        self.assertEqual((result.returncode, result.stdout.splitlines(), result.stderr), (0, BASELINE, ""))
        self.assertEqual(result.stdout.splitlines()[-1], "PASS npp_claim_note_reach")


if __name__ == "__main__":
    unittest.main()
