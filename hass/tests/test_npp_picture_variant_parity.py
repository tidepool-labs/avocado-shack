"""Offline CLI contract for the picture-variant parity report."""

from contextlib import redirect_stderr, redirect_stdout
import importlib.util
import io
from pathlib import Path
import subprocess
import sys
from tempfile import TemporaryDirectory
import unittest
from unittest.mock import patch

from hass import npp
from hass.npp import picture


REPO = Path(__file__).resolve().parents[2]
SCRIPT = REPO / "scripts/hass/npp_picture_variant_parity.py"
PASS = "PASS npp_picture_variant_parity"
FAIL = "FAIL npp_picture_variant_parity"
PHOTOS = "hass/ops/photos.py"
JOB = "hass/npp/job.py"
STAGES = "hass/npp/stages.py"
SELECT = '''\
def select_variant(cleaned=None, house=False):
    data, ext = b"", "webp"
    variant = "raw"
    if cleaned:
        variant, data, ext = "polished", cleaned, "jpg"
    elif house:
        variant, data, ext = "house", data, "jpg"
    return variant, data, ext
'''
FINISH = '''\
class Jobs:
    def unrelated(self, result):
        return result.variant in ("decoy",)

    def finish(self, result):
        return result.variant in ("raw", "house", "polished")
'''
RENDER = '''\
class ProductionStages:
    def render_listing(self, frozen):
        parts = {}
        if frozen.note:
            parts["picture_own_photo" if frozen.variant == "raw" else "picture_house"] = {}
        return Card(compose(self.replies, parts))
'''
NOTES = {"raw": "fixture raw note", "house": "fixture house note"}
PARTS = {"picture_own_photo": "fixture raw note", "picture_house": "fixture house note"}


class PictureVariantParityTests(unittest.TestCase):
    def setUp(self):
        temporary = TemporaryDirectory(dir=REPO)
        self.addCleanup(temporary.cleanup)
        self.root = Path(temporary.name)
        spec = importlib.util.spec_from_file_location("picture_variant_parity", SCRIPT)
        assert spec is not None and spec.loader is not None
        self.script = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(self.script)

    def fixture(self, photos: str | None = SELECT, job: str | None = FINISH, notes=NOTES, parts=PARTS,
                *, stages: str | None = RENDER):
        out, err = io.StringIO(), io.StringIO()
        with TemporaryDirectory(dir=self.root) as temporary:
            root = Path(temporary)
            for name, source in ((PHOTOS, photos), (JOB, job), (STAGES, stages)):
                if source is not None:
                    path = root / name
                    path.parent.mkdir(parents=True, exist_ok=True)
                    path.write_text(source, encoding="utf-8")
            with (patch.object(self.script, "ROOT", root), patch.object(picture, "_NOTES", notes),
                  patch.object(npp, "assets", return_value=({}, {}, {"brackets": {"parts": parts}})),
                  redirect_stdout(out), redirect_stderr(err)):
                code = self.script.main([])
        return code, out.getvalue(), err.getvalue()

    def cli(self, *args):
        result = subprocess.run([sys.executable, "-B", str(SCRIPT), *args], cwd=self.root,
                                capture_output=True, text=True, timeout=15)
        return result.returncode, result.stdout, result.stderr

    def assert_report(self, result, code, trailer, reasons=()):
        status, out, err = result
        self.assertEqual(status, code, out + err)
        self.assertEqual(err, "")
        lines = out.splitlines()
        self.assertTrue(lines)
        self.assertEqual(lines[-1], trailer)
        self.assertEqual([line for line in lines[:-1] if line.startswith("FAIL ")], list(reasons))
        return lines

    def test_c1_full_pass(self):
        # Accepted fallback variants should not require a note for polished.
        self.assert_report(self.fixture(), 0, PASS)

    def test_c2_findings_trailer(self):
        # Accumulate independent findings instead of returning after the first one.
        job = FINISH.replace('"raw", "house", "polished"', '"raw", "polished"')
        self.assert_report(self.fixture(job=job, notes={**NOTES, "extra": "fixture"},
                                       parts={**PARTS, "picture_own_photo": "changed"}), 1, FAIL,
                           ("FAIL variant-not-accepted house", "FAIL note-without-variant extra",
                            "FAIL note-words-differ picture_own_photo"))

    def test_c2_1_variant_not_accepted(self):
        # A new tuple arm is a choice; repeated sites for it produce just one finding.
        photos = SELECT.replace("    return", '''\
    if condition:
        variant, data, ext = "square", data, "jpg"
    elif other_condition:
        variant = "square"
    else:
        variant = "wide"
    return''')
        self.assert_report(self.fixture(photos=photos), 1, FAIL,
                           ("FAIL variant-not-accepted square", "FAIL variant-not-accepted wide"))

    def test_c2_2_note_without_variant(self):
        # An allowed job variant still cannot justify a note if photos never choose it.
        job = FINISH.replace('"polished")', '"polished", "square")')
        self.assert_report(self.fixture(job=job, notes={**NOTES, "square": "fixture"}), 1, FAIL,
                           ("FAIL note-without-variant square",))

    def test_c2_3_note_words_differ(self):
        # Compare exact words for each part, including whitespace and missing keys.
        lines = self.assert_report(self.fixture(parts={"picture_own_photo": PARTS["picture_own_photo"] + " "}),
                                   1, FAIL, ("FAIL note-words-differ picture_own_photo",
                                             "FAIL note-words-differ picture_house"))
        self.assertIn("variants note_words=differ", lines)

    def test_c2_3_swapped_renderer_parts(self):
        # Correct pinned words alone do not prove the renderer uses the right part.
        swapped = RENDER.replace('"picture_own_photo" if frozen.variant == "raw" else "picture_house"',
                                 '"picture_house" if frozen.variant == "raw" else "picture_own_photo"')
        lines = self.assert_report(self.fixture(stages=swapped), 1, FAIL,
                                   ("FAIL note-words-differ picture_house",
                                    "FAIL note-words-differ picture_own_photo"))
        self.assertIn("variants note_words=differ", lines)

    def test_c2_4_variants_not_found(self):
        # Refuse missing, ambiguous, or partly nonliteral evidence; never take the first match.
        duplicate_gate = FINISH.replace("        return result.variant in (\"raw\"",
                                        "        if result.variant in (\"decoy\",): pass\n"
                                        "        return result.variant in (\"raw\"")
        for path, changes in (
            (PHOTOS, {"photos": SELECT.replace("select_variant", "decoy")}),
            (PHOTOS, {"photos": SELECT * 2}),
            (PHOTOS, {"photos": SELECT.replace('"house", data', 'computed, data')}),
            (JOB, {"job": FINISH.replace('("raw", "house", "polished")', "allowed")}),
            (JOB, {"job": duplicate_gate}),
            (STAGES, {"stages": RENDER.replace('else "picture_house"', 'else dynamic_part')}),
            (STAGES, {"stages": RENDER.replace('if frozen.note:', 'if not frozen.note:')}),
            (STAGES, {"stages": RENDER.replace('else "picture_house"', 'else "picture_own_photo"')}),
            (STAGES, {"stages": RENDER.replace('        return Card', '        parts = {}\n        return Card')}),
        ):
            with self.subTest(path=path, changes=changes):
                self.assert_report(self.fixture(**changes), 1, FAIL, (f"FAIL variants-not-found {path}",))

    def test_c2_5_parse_error(self):
        # Unreadable and syntactically invalid files share one terse finding, not a traceback.
        for changes in ({"photos": None}, {"job": "class Jobs:\n"}, {"photos": None, "job": "class Jobs:\n"},
                        {"stages": None}, {"stages": "class ProductionStages:\n"}):
            with self.subTest(changes=changes):
                self.assert_report(self.fixture(**changes), 1, FAIL, ("FAIL parse-error",))

    def test_c3_usage_exit_2(self):
        # Even argparse's usual help switches and end marker are not supported inputs.
        for arg in ("fixture", "--unknown", "-h", "--help", "--"):
            with self.subTest(arg=arg):
                status, out, err = self.cli(arg)
                self.assertEqual(status, 2)
                self.assertEqual(out, "")
                self.assertIn("usage:", err)
                self.assertIn(": error: ", err.splitlines()[-1])

    def test_c4_read_only(self):
        # A CLI import or future output cache must not write into either input tree.
        def snapshot():
            entries = {}
            for name in ("hass", "storefront-mockup"):
                tree = REPO / name
                for path in (tree, *tree.rglob("*")):
                    stat = path.lstat()
                    entries[path.relative_to(REPO)] = (stat.st_size, stat.st_mtime_ns)
            return entries

        before = snapshot()
        self.assert_report(self.cli(), 0, PASS)
        self.assertEqual(snapshot(), before)

    def test_c5_output_shape(self):
        # Findings cannot emit explanatory prose or extra lines into machine-readable output.
        lines = self.assert_report(self.fixture(parts={**PARTS, "picture_house": "changed"}), 1, FAIL,
                                   ("FAIL note-words-differ picture_house",))
        self.assertEqual(lines, ["variants chosen=house,polished,raw", "variants accepted=house,polished,raw",
                                 "variants noted=house,raw", "variants note_words=differ",
                                 "FAIL note-words-differ picture_house", FAIL])

    def test_c6_fixture(self):
        # Read the live module's dict at invocation, not a copied or cached inventory.
        with patch.dict(picture._NOTES, {"retro": "x"}):
            out, err = io.StringIO(), io.StringIO()
            with redirect_stdout(out), redirect_stderr(err):
                status = self.script.main([])
        self.assert_report((status, out.getvalue(), err.getvalue()), 1, FAIL,
                           ("FAIL note-without-variant retro",))

    def test_c7_live_pins(self):
        # The checked-in selector, gate, note dict, and pinned templates agree on this base.
        lines = self.assert_report(self.cli(), 0, PASS)
        self.assertEqual(lines, ["variants chosen=house,polished,raw", "variants accepted=house,polished,raw",
                                 "variants noted=house,raw", "variants note_words=same", PASS])
