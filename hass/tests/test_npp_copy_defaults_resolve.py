"""Offline contract tests for the NPP default-template reference check."""

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

from hass import npp


ROOT = Path(__file__).resolve().parents[2]
SCRIPT = ROOT / "scripts/hass/npp_copy_defaults_resolve.py"
ASSET = "hass-listing-copy/copy-templates.json"
PASS = "PASS npp_copy_defaults_resolve"
FAIL = "FAIL npp_copy_defaults_resolve"
LIVE_SUMMARY = "defaults refs=18 name=name-item imageAlt=alt-name description=10 story=6"


class CopyDefaultsResolveTests(unittest.TestCase):
    def setUp(self):
        temporary = tempfile.TemporaryDirectory(dir=ROOT)
        self.addCleanup(temporary.cleanup)
        self.temp = Path(temporary.name)
        spec = importlib.util.spec_from_file_location(SCRIPT.stem, SCRIPT)
        assert spec is not None and spec.loader is not None
        self.tool = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(self.tool)

    def fixture(self):
        return {
            "defaults": {
                "name": "fixture-name",
                "imageAlt": "fixture-alt",
                "description": {"food": ["fixture-desc"]},
                "story": {"order": ["fixture-story"]},
            },
            "templates": [
                {"id": "fixture-name", "field": "name"},
                {"id": "fixture-alt", "field": "imageAlt"},
                {"id": "fixture-desc", "field": "description"},
                {"id": "fixture-story", "field": "story"},
            ],
        }

    def invoke(self):
        stdout, stderr = io.StringIO(), io.StringIO()
        with redirect_stdout(stdout), redirect_stderr(stderr):
            code = self.tool.main([])
        return code, stdout.getvalue(), stderr.getvalue()

    def invoke_fixture(self, document):
        source = self.temp / "copy-templates.json"
        source.write_text(json.dumps(document), encoding="utf-8")
        with patch.object(npp, "assets", return_value=({}, {ASSET: source.read_bytes()}, {})) as loader:
            result = self.invoke()
        loader.assert_called_once_with()
        return result

    def cli(self, *args):
        result = subprocess.run([sys.executable, "-B", str(SCRIPT), *args], cwd=self.temp,
                                capture_output=True, text=True, timeout=10)
        return result.returncode, result.stdout, result.stderr

    def assert_report(self, result, code, trailer):
        actual_code, stdout, stderr = result
        self.assertEqual(actual_code, code, stderr)
        self.assertEqual(stderr, "")
        lines = stdout.splitlines()
        self.assertTrue(lines)
        self.assertEqual(lines[-1], trailer)
        self.assertTrue(stdout.endswith(f"{trailer}\n"))
        return lines[:-1]

    def test_c1_full_pass(self):
        # A valid non-live inventory must not be rejected by hard-coded live IDs.
        lines = self.assert_report(self.invoke_fixture(self.fixture()), 0, PASS)
        self.assertEqual(lines, ["defaults refs=4 name=fixture-name imageAlt=fixture-alt description=1 story=1"])

    def test_c2_findings_trailer(self):
        # A story failure must affect the exit even if all earlier fields passed.
        document = self.fixture()
        document["defaults"]["story"]["order"].append("absent-story")
        lines = self.assert_report(self.invoke_fixture(document), 1, FAIL)
        self.assertEqual(lines[1:], ["FAIL default-missing story absent-story"])

    def test_c2_1_default_missing(self):
        # The second rung is checked even when the first resolves.
        document = self.fixture()
        document["defaults"]["description"]["food"].append("absent-desc")
        lines = self.assert_report(self.invoke_fixture(document), 1, FAIL)
        self.assertEqual(lines[1:], ["FAIL default-missing description absent-desc"])

    def test_c2_2_default_wrong_field(self):
        # A present template for another field is not a valid match.
        document = self.fixture()
        document["defaults"]["imageAlt"] = "fixture-name"
        lines = self.assert_report(self.invoke_fixture(document), 1, FAIL)
        self.assertEqual(lines[1:], ["FAIL default-wrong-field imageAlt fixture-name"])

    def test_c2_3_default_key_missing(self):
        # Deleting any required section must not look like an empty, valid list.
        for key in ("name", "imageAlt", "description", "story"):
            with self.subTest(key=key):
                document = self.fixture()
                del document["defaults"][key]
                lines = self.assert_report(self.invoke_fixture(document), 1, FAIL)
                self.assertEqual(lines[1:], [f"FAIL default-key-missing {key}"])

    def test_c2_4_check_error(self):
        # A load failure must not be swallowed, leak detail, or produce a traceback.
        with patch.object(npp, "assets", side_effect=OSError("synthetic failure detail")) as loader:
            lines = self.assert_report(self.invoke(), 1, FAIL)
        loader.assert_called_once_with()
        self.assertEqual(lines, ["FAIL check-error"])

    def test_c3_usage_exit_2(self):
        # No positional arguments or flags (including implicit argparse help).
        for arg in ("positional", "--unknown", "--help", "--"):
            with self.subTest(arg=arg):
                code, stdout, stderr = self.cli(arg)
                self.assertEqual(code, 2)
                self.assertEqual(stdout, "")  # No stdout trailer on a usage error.
                self.assertTrue(stderr.startswith("usage:"))

    def test_c4_read_only(self):
        # Catch writes to either input tree, including new sidecars and cache files.
        def snapshot():
            result = {}
            for tree in (ROOT / "hass", ROOT / "storefront-mockup"):
                for path in (tree, *tree.rglob("*")):
                    info = path.lstat()
                    result[path.relative_to(ROOT)] = (info.st_size, info.st_mtime_ns)
            return result

        before = snapshot()
        self.assert_report(self.cli(), 0, PASS)
        self.assertEqual(snapshot(), before)

    def test_c5_output_shape(self):
        # A mixed failure must print the summary and all findings, without chatter.
        document = self.fixture()
        del document["defaults"]["name"]
        document["defaults"]["imageAlt"] = "fixture-story"
        document["defaults"]["description"]["food"] = ["absent-desc"]
        lines = self.assert_report(self.invoke_fixture(document), 1, FAIL)
        self.assertEqual(lines, [
            "defaults refs=3 name=- imageAlt=fixture-story description=1 story=1",
            "FAIL default-key-missing name",
            "FAIL default-wrong-field imageAlt fixture-story",
            "FAIL default-missing description absent-desc",
        ])

    def test_c6_fixture(self):
        # A set of IDs would lose the repeated short fallback for four ladders.
        _, files, _ = npp.assets()
        document = json.loads(files[ASSET])
        document["defaults"]["name"] = "story-full"
        document["templates"] = [row for row in document["templates"] if row["id"] != "desc-default-short"]
        lines = self.assert_report(self.invoke_fixture(document), 1, FAIL)
        self.assertEqual(lines[1:], ["FAIL default-wrong-field name story-full"] +
                         ["FAIL default-missing description desc-default-short"] * 5)

    def test_c7_live_pins(self):
        # A fixture-only loader or drift in the checked-in inventory must fail here.
        with patch.object(npp, "assets", wraps=npp.assets) as loader:
            lines = self.assert_report(self.invoke(), 0, PASS)
        loader.assert_called_once_with()
        self.assertEqual(lines, [LIVE_SUMMARY])
        _, files, _ = npp.assets()
        defaults = json.loads(files[ASSET])["defaults"]
        self.assertEqual((defaults["name"], defaults["imageAlt"]), ("name-item", "alt-name"))
        self.assertEqual(defaults["description"], {
            "food": ["desc-food-default", "desc-default-short"],
            "drink": ["desc-drink-default", "desc-default-short"],
            "fresh": ["desc-fresh-default", "desc-default-short"],
            "flowers": ["desc-flowers-default", "desc-default-short"],
            "non-food": ["desc-nonfood-default", "desc-default-short"],
        })
        self.assertEqual(defaults["story"]["order"], [
            "story-full", "story-nature-makes-town", "story-makes-founded",
            "story-nature-town", "story-makes-town", "story-founded",
        ])
