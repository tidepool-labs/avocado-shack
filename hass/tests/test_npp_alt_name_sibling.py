"""Exercise the offline S5 alt-name sibling checker against fixtures and pins."""

from contextlib import redirect_stderr, redirect_stdout
import importlib.util
from io import StringIO
import json
from pathlib import Path
import subprocess
import sys
from tempfile import TemporaryDirectory
import unittest
from unittest.mock import patch

from hass import content_model, npp
from hass.npp import copy


ROOT = Path(__file__).resolve().parents[2]
SCRIPT = ROOT / "scripts/hass/npp_alt_name_sibling.py"
ASSET = "hass-listing-copy/copy-templates.json"
PASS = "PASS npp_alt_name_sibling"
FAIL = "FAIL npp_alt_name_sibling"
SPEC = importlib.util.spec_from_file_location("npp_alt_name_sibling", SCRIPT)
assert SPEC is not None and SPEC.loader is not None
checker = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(checker)


def row(template_id, **rules):
    return {"id": template_id, "field": "name", "kinds": ["fresh"], **rules}


class AltNameSiblingTests(unittest.TestCase):
    def invoke(self, *args):
        with TemporaryDirectory() as work:
            result = subprocess.run([sys.executable, "-B", str(SCRIPT), *args], cwd=work,
                                    capture_output=True, text=True, timeout=10)
        return result.returncode, result.stdout.splitlines(), result.stderr

    def run_main(self):
        out, err = StringIO(), StringIO()
        with redirect_stdout(out), redirect_stderr(err):
            code = checker.main([])
        return code, out.getvalue().splitlines(), err.getvalue()

    def run_fixture(self, templates):
        with TemporaryDirectory() as work:
            fixture = Path(work) / "copy-templates.json"
            fixture.write_text(json.dumps({"templates": templates}), encoding="utf-8")
            with patch.object(npp, "assets", return_value=({}, {ASSET: fixture.read_bytes()}, {})) as load:
                result = self.run_main()
            load.assert_called_once_with()
        return result

    def assert_status(self, result, code, trailer):
        actual, lines, stderr = result
        self.assertEqual(actual, code)
        self.assertEqual(stderr, "")
        self.assertEqual(lines[-1:], [trailer])
        return lines[:-1]

    def test_c1_full_pass(self):
        # Extra eligibility on the plain twin must not fail the one-way coverage check.
        sized = row("fixture-size", categories=["fruit"], variants=["raw"])
        lines = self.assert_status(self.run_fixture([row("fixture"), sized]), 0, PASS)
        self.assertEqual(lines, ["twin fixture-size base=fixture cases=20 mismatched=0"])

    def test_c2_findings_trailer(self):
        # One finding must not hide a later pair's failure or replace the final verdict.
        templates = [row("missing-size"), row("wrong", field="story"), row("wrong-size")]
        lines = self.assert_status(self.run_fixture(templates), 1, FAIL)
        self.assertEqual([line for line in lines if line.startswith("FAIL ")],
                         ["FAIL twin-missing missing-size", "FAIL twin-field wrong-size"])

    def test_c2_1_twin_missing(self):
        # A failed lookup must not skip the sized template.
        lines = self.assert_status(self.run_fixture([row("fixture-size")]), 1, FAIL)
        self.assertEqual(lines, ["twin fixture-size base=- cases=0 mismatched=0",
                                 "FAIL twin-missing fixture-size"])

    def test_c2_2_twin_field(self):
        # The right id and eligibility alone are not enough for S5's name render.
        templates = [row("fixture", field="imageAlt"), row("fixture-size")]
        lines = self.assert_status(self.run_fixture(templates), 1, FAIL)
        self.assertEqual(lines, ["twin fixture-size base=fixture cases=20 mismatched=0",
                                 "FAIL twin-field fixture-size"])

    def test_c2_3_twin_narrower(self):
        # Check both variants and the category exclusion, without flagging ineligible sized cases.
        sized = row("fixture-size", categories=["fruit", "vegetables"], categories_except=["fruit"])
        twin = row("fixture", variants=["raw"])
        with (patch.object(content_model, "CATEGORIES", ("fruit", "vegetables", "eggs")),
              patch.object(copy, "eligible", wraps=copy.eligible) as eligible):
            lines = self.assert_status(self.run_fixture([twin, sized]), 1, FAIL)
        self.assertEqual(eligible.call_count, 12)
        self.assertEqual(lines, ["twin fixture-size base=fixture cases=6 mismatched=1",
                                 "FAIL twin-narrower fixture-size fresh vegetables house"])

    def test_c2_4_check_error(self):
        # A loader failure must neither become a traceback nor produce a clean report.
        with patch.object(npp, "assets", side_effect=OSError("fixture load error")) as load:
            lines = self.assert_status(self.run_main(), 1, FAIL)
        load.assert_called_once_with()
        self.assertEqual(lines, ["FAIL check-error"])
        with patch.object(copy, "eligible", side_effect=ValueError("fixture check error")):
            lines = self.assert_status(self.run_fixture([row("fixture"), row("fixture-size")]), 1, FAIL)
        self.assertEqual(lines, ["FAIL check-error"])

    def test_c3_usage_exit_2(self):
        # Unsupported options (even help or a bare delimiter) must not run the check.
        for argument in ("extra", "--unknown", "--help", "--"):
            with self.subTest(argument=argument):
                code, lines, stderr = self.invoke(argument)
                self.assertEqual(code, 2)
                self.assertEqual(lines, [])
                self.assertEqual(stderr.splitlines()[-1],
                                 f"npp_alt_name_sibling.py: error: unrecognized arguments: {argument}")

    def test_c4_read_only(self):
        # Catch persistent writes, including generated or overwritten catalog files.
        def snapshot():
            entries = {}
            for tree in (ROOT / "hass", ROOT / "storefront-mockup"):
                for path in (tree, *tree.rglob("*")):
                    stat = path.lstat()
                    entries[path.relative_to(ROOT)] = (stat.st_size, stat.st_mtime_ns)
            return entries

        before = snapshot()
        self.assert_status(self.invoke(), 0, PASS)
        self.assertEqual(snapshot(), before)

    def test_c5_output_shape(self):
        # No debug/banner noise belongs in the CLI report, even when a finding exists.
        for broken in (False, True):
            with self.subTest(broken=broken):
                templates = [row("fixture"), row("fixture-size")]
                if broken:
                    templates.append(row("missing-size"))
                lines = self.assert_status(self.run_fixture(templates), int(broken), FAIL if broken else PASS)
                expected = ["twin fixture-size base=fixture cases=20 mismatched=0"]
                if broken:
                    expected += ["twin missing-size base=- cases=0 mismatched=0",
                                 "FAIL twin-missing missing-size"]
                self.assertEqual(lines, expected)

    def test_c6_fixture(self):
        # A real template minus one kind must flag every shelf/variant for exactly that kind.
        _, files, _ = npp.assets()
        templates = json.loads(files[ASSET])["templates"]
        twin = next(row for row in templates if row["id"] == "name-item")
        kinds = twin["kinds"]
        twin["kinds"] = [kind for kind in kinds if kind != "fresh"]
        lines = self.assert_status(self.run_fixture(templates), 1, FAIL)
        self.assertEqual([line for line in lines if line.startswith("FAIL ")], [
            f"FAIL twin-narrower name-item-size fresh {category} {variant}"
            for category in content_model.CATEGORIES for variant in ("raw", "house")
        ])
        self.assertIn("twin name-item-size base=name-item cases=80 mismatched=20", lines)
        twin["kinds"] = kinds
        self.assert_status(self.run_fixture(templates), 0, PASS)

    def test_c7_live_pins(self):
        # Pin the measured live inventory so losing a pair cannot look like a clean check.
        _, files, _ = npp.assets()
        templates = json.loads(files[ASSET])["templates"]
        self.assertEqual(len(templates), 26)
        by_id = {row["id"]: row for row in templates}
        self.assertEqual({key for key in by_id if key.endswith("-size")},
                         {"name-brand-item-size", "name-item-size"})
        for base in ("name-brand-item", "name-item"):
            sized, twin = by_id[base + "-size"], by_id[base]
            self.assertEqual(twin["field"], "name")
            for key in ("field", "kinds", "categories", "categories_except", "variants"):
                self.assertEqual(sized.get(key), twin.get(key), (base, key))
        lines = self.assert_status(self.invoke(), 0, PASS)
        self.assertCountEqual(lines, [
            "twin name-brand-item-size base=name-brand-item cases=80 mismatched=0",
            "twin name-item-size base=name-item cases=80 mismatched=0",
        ])
