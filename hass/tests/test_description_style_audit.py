"""Offline contract tests for the counts-only description audit."""

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

from hass import content_model, house_style


SCRIPT = Path(__file__).resolve().parents[2] / "scripts/hass/description_style_audit.py"
PASS = "PASS description_style_audit"
FAIL = "FAIL description_style_audit"
CLAIM = "no unstated claim term"
DESCRIPTION = (
    "These pears have a mellow sweetness and a firm bite when sliced. "
    "Cut them into wedges for a snack, or scatter thin slices over a bowl of greens."
)


def product(pid="fixture-pear", description=DESCRIPTION, **fields):
    return {
        "id": pid, "name": "Fixture pear", "brand": "Fixture grower",
        "displayBrand": "Fixture grower", "producerKey": "fixture-grower", "category": "fruit",
        "image": f"assets/products/{pid}.webp", "description": description, "status": "active",
        **fields,
    }


def write_json(path, document):
    path.write_text(json.dumps(document), encoding="utf-8")


class DescriptionStyleAuditTests(unittest.TestCase):
    def setUp(self):
        temp = TemporaryDirectory()
        self.addCleanup(temp.cleanup)
        self.root = Path(temp.name).resolve()
        self.content = self.root / "content-canary"
        self.content.mkdir()
        self.spec = self.root / "spec-canary.json"
        self.write_content(product())
        self.write_spec()

    def write_content(self, *products):
        documents = {
            "products": {"products": products},
            "makers": {"makers": {"fixture-grower": {
                "name": "Fixture grower", "place": "Testville, California", "story": "A test grower.",
            }}},
            "community": {"club": {
                "clubName": "Fixture club", "organizer": "Fixture organizer",
                "intendedSender": "Fixture sender", "emailConnected": False,
            }, "events": [], "routeIdeas": []},
            "store": {
                "name": "Fixture store", "streetAddress": "Test Lane", "town": "Testville",
                "hours": ["Monday-Friday 9am-5pm", "Closed Saturday-Sunday"],
            },
        }
        for name, document in documents.items():
            write_json(self.content / f"{name}.json", {"schemaVersion": 1, **document})

    def write_spec(self, *, min_chars=40, max_sentences=4):
        write_json(self.spec, {"descriptions": {
            "hype_words_absent": [], "limit_chars": 600, "count": 1,
            "chars": {"min": min_chars, "max": 300, "p05": min_chars, "p95": 300},
            "sentences": {"min": 1, "max": max_sentences},
            "words_per_sentence": {"min": 4, "max": 30},
            "texts_with": {"digits": 0, "exclaims": 0, "questions": 0, "straight_apostrophes": 0},
        }})

    def run_cli(self, *args):
        return subprocess.run(
            [sys.executable, "-B", str(SCRIPT), *map(str, args)],
            cwd=self.root, capture_output=True, text=True, timeout=10,
        )

    def audit(self):
        return self.run_cli("--content", self.content, "--spec", self.spec)

    def assert_result(self, result, code, *lines):
        self.assertEqual(result.returncode, code, result.stdout + result.stderr)
        self.assertEqual(result.stderr, "")
        self.assertEqual(result.stdout.splitlines(), list(lines))

    def test_c1_full_pass(self):
        # The direct script must find the committed default even outside the repo cwd.
        self.assert_result(self.run_cli("--content", self.content), 0,
                           "checked 1", "pass 1", "note unstated-claim 0", PASS)

    def test_c2_1_unsafe_input(self):
        # A symlink to an otherwise valid copy must not be traversed.
        alias = self.root / "alias"
        alias.symlink_to(self.content, target_is_directory=True)
        for path in (alias, self.spec, self.root / "missing"):
            with self.subTest(path=path.name):
                self.assert_result(self.run_cli("--content", path, "--spec", self.spec), 1,
                                   "FAIL unsafe-input", FAIL)

    def test_c2_2_content_invalid(self):
        # Decode errors and structurally invalid content use the same path-free reason.
        for raw in (b'{"schemaVersion": 0, "products": []}', b"{", b"\xff",
                    b'{"schemaVersion": 1, "products": [{"id": []}]}'):
            with self.subTest(raw=raw):
                (self.content / "products.json").write_bytes(raw)
                self.assert_result(self.audit(), 1, "FAIL content-invalid", FAIL)

    def test_c2_3_spec_unreadable(self):
        # No fallback to the default for path, parse, or incompatible shape errors.
        alias = self.root / "spec-alias"
        alias.symlink_to(self.spec)
        for path in (alias, self.root / "missing.json", self.content):
            with self.subTest(path=path.name):
                self.assert_result(self.run_cli("--content", self.content, "--spec", path), 1,
                                   "FAIL spec-unreadable", FAIL)
        for raw in (b"{", b"\xff", b"{}", b'{"descriptions": {}}'):
            with self.subTest(raw=raw):
                self.spec.write_bytes(raw)
                self.assert_result(self.audit(), 1, "FAIL spec-unreadable", FAIL)

    def test_c2_4_description_hard(self):
        # Count products, not hard checks; sort check names and IDs independently.
        self.write_spec(max_sentences=1)
        self.write_content(product("fixture-z", "Fresh. Crisp."), product("fixture-a", "Fresh."))
        self.assert_result(self.audit(), 1, "checked 2", "pass 0",
                           "check 2 length like the others", "check 1 sentence count like the others",
                           "check 2 sentence length like the others", "note unstated-claim 0",
                           "hard fixture-a 1", "hard fixture-z 2", "FAIL description-hard 2", FAIL)

    def test_c3_usage_exit_2(self):
        # CLI syntax errors retain argparse's usage status without echoing private extras.
        for args in ((), ("--content",), ("--content", self.content, "--unknown", self.spec),
                     ("--content", self.content, "--spec")):
            with self.subTest(options=tuple(arg for arg in args if isinstance(arg, str))):
                result = self.run_cli(*args)
                self.assertEqual(result.returncode, 2)
                self.assertEqual(result.stdout, "")
                self.assertTrue(result.stderr.startswith("usage:"))
                self.assertNotIn(str(self.content), result.stderr)
                self.assertNotIn(str(self.spec), result.stderr)

    def test_c4_read_only(self):
        # A rewritten input or a new sidecar changes the fixture snapshot.
        # This override also proves the CLI does not use the default spec instead.
        self.write_spec(min_chars=1)
        self.write_content(product(description="Fresh."))

        def snapshot():
            return {path.relative_to(self.root): (path.stat().st_mtime_ns,
                    path.read_bytes() if path.is_file() else None)
                    for path in (self.root, *self.root.rglob("*"))}

        before = snapshot()
        self.assert_result(self.audit(), 0, "checked 1", "pass 1",
                           "check 1 sentence length like the others", "note unstated-claim 0", PASS)
        self.assertEqual(snapshot(), before)

    def test_c5_no_private_values(self):
        # Both a scored finding and validator errors could accidentally print raw fields.
        name = "Canary name quartz"
        description = "Canary description feldspar."
        bad_category = "Canary category mica"

        def check_canaries(result):
            for value in (name, description, bad_category, str(self.content), str(self.spec)):
                self.assertNotIn(value, result.stdout + result.stderr)

        self.write_content(product(description=description, name=name))
        result = self.audit()
        check_canaries(result)
        self.assert_result(result, 1, "checked 1", "pass 0", "check 1 length like the others",
                           "check 1 sentence length like the others", "note unstated-claim 0",
                           "hard fixture-pear 1", "FAIL description-hard 1", FAIL)
        self.write_content(product(description=description, name=name, category=bad_category))
        result = self.audit()
        check_canaries(result)
        self.assert_result(result, 1, "FAIL content-invalid", FAIL)

    def test_c6_short_description_hard(self):
        # This valid catalog record must fail the committed length rule, not validation.
        score = house_style.check_description("Fresh.")
        self.assertIn("length like the others", score["hard_failures"])
        self.write_content(product(description="Fresh."))
        result = self.run_cli("--content", self.content)
        self.assertEqual(result.returncode, 1, result.stderr)
        self.assertEqual(result.stderr, "")
        lines = result.stdout.splitlines()
        self.assertEqual(lines[-1], FAIL)
        self.assertIn("check 1 length like the others", lines)
        self.assertIn(f"hard fixture-pear {len(score['hard_failures'])}", lines)
        self.assertIn("FAIL description-hard 1", lines)

    def test_c7_claim_only_informational(self):
        # Treating a raw scorer rejection as an audit finding would block this product.
        description = DESCRIPTION.replace("These pears", "These organic pears")
        score = house_style.check_description(description, house_style.load_spec(self.spec))
        self.assertEqual(score["hard_failures"], [CLAIM])
        self.assertFalse(score["pass"])
        self.write_content(product(description=description))
        self.assert_result(self.audit(), 0, "checked 1", "pass 0", f"check 1 {CLAIM}",
                           "note unstated-claim 1", PASS)

    def test_c8_only_active(self):
        # Either inactive record would fail if grading ignored the status filter.
        held = product("fixture-held", "Fresh.", status="held", hold={
            "reason": "Fixture hold", "source": "https://example.com/hold",
            "evidence": "Fixture evidence", "record": "Fixture record",
        })
        self.write_content(product(), held, product("fixture-hidden", "Fresh.", status="hidden"))
        self.assert_result(self.audit(), 0, "checked 1", "pass 1", "note unstated-claim 0", PASS)

    def test_invalid_id_not_printed(self):
        # The real validator refuses invalid IDs. Exercise the output guard if
        # such an ID ever comes back from the loader after validation changes.
        pid = "fixture-pear\n"
        self.write_content(product() | {"id": pid})
        self.assert_result(self.audit(), 1, "FAIL content-invalid", FAIL)
        loader = importlib.util.spec_from_file_location("description_style_audit", SCRIPT)
        assert loader is not None and loader.loader is not None
        audit_module = importlib.util.module_from_spec(loader)
        loader.loader.exec_module(audit_module)
        content = content_model.Content([product(description="Fresh.") | {"id": pid}], {}, {}, {})
        out, err = StringIO(), StringIO()
        with patch.object(content_model, "load_and_validate", return_value=content):
            with redirect_stdout(out), redirect_stderr(err):
                code = audit_module.main(["--content", str(self.content), "--spec", str(self.spec)])
        self.assertEqual(code, 1)
        self.assertEqual(err.getvalue(), "")
        self.assertEqual(out.getvalue().splitlines(), [
            "checked 1", "pass 0", "check 1 length like the others", "check 1 sentence length like the others",
            "note unstated-claim 0", "note invalid-id 1", "FAIL description-hard 1", FAIL,
        ])
