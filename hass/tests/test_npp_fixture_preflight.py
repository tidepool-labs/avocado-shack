"""Public stand-ins for case 30's two independent blockers and case 7's twin."""
import contextlib
import io
import json
import tempfile
import unittest
from pathlib import Path

from scripts.hass import npp_fixture_preflight as preflight


class FixturePreflightTests(unittest.TestCase):
    def test_case_30_url_and_label_are_independent(self):
        # A hostname repair must not hide the contradiction introduced by donor copy.
        base = {"item": "Dried figs", "owner_maker": "Miners",
                "label": {"brand": "MINERS", "confidence": .99}, "products": []}
        for url, maker, expected in (
            ("https://minersfigs.example/about", "Miners", ["reserved_owner_url"]),
            ("https://example.com/miners", "Bee Happy Farm", ["label_identity_conflict"]),
            ("https://minersfigs.example/about", "Bee Happy Farm",
             ["reserved_owner_url", "label_identity_conflict"]),
            ("https://example.com/miners", "Miners", []),
        ):
            with self.subTest(url=url, maker=maker):
                self.assertEqual(preflight.lint(dict(base, owner_url=url, owner_maker=maker)), expected)

    def test_case_7_duplicate_depends_on_existing_catalog_not_maker(self):
        # A matched maker is not a duplicate; adding the catalog twin changes the result.
        fixture = {"item": "Dried mushrooms", "owner_maker": "Mighty Cap Mushrooms",
                   "label": {"brand": "MIGHTY CAP", "confidence": .99}, "products": []}
        self.assertEqual(preflight.lint(fixture), [])
        twin = {"name": "DRIED MUSHROOMS", "status": "active"}
        self.assertEqual(preflight.lint(dict(fixture, products=[twin])), ["catalog_duplicate"])
        self.assertEqual(preflight.lint(dict(fixture, products=[dict(twin, status="held")])), [])

    def test_low_confidence_label_does_not_assert_conflicting_identity(self):
        # A weak label read is not the same as the .99 observed in the conflict control.
        fixture = {"item": "Dried figs", "owner_maker": "Miners", "products": [],
                   "label": {"brand": "Another Farm", "confidence": .79}}
        self.assertEqual(preflight.lint(fixture), [])

    def test_command_reports_only_codes_and_distinguishes_bad_input(self):
        # A malformed or omitted snapshot must not return a clean compatibility result.
        fixture = {"item": "Dried figs", "products": [], "owner_url": "https://user:sentinel@example.com/"}
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "fixture.json"
            for text, code, status, reasons in (
                (json.dumps(dict(fixture, owner_url="https://example.com/")), 0, "CLEAR", []),
                (json.dumps(fixture), 1, "HOLD", ["invalid_owner_url"]),
                ('{"item":"Dried figs"}', 2, "INVALID", ["invalid_fixture"]),
                ('{"item":"Dried figs","products":[null]}', 2, "INVALID", ["invalid_fixture"]),
                ('{"item":"Dried figs","products":[],"products":[]}', 2, "INVALID", ["invalid_fixture"]),
            ):
                with self.subTest(code=code, text=text), contextlib.redirect_stdout(io.StringIO()) as out:
                    path.write_text(text, encoding="utf-8")
                    self.assertEqual(preflight.main([str(path)]), code)
                    self.assertEqual(json.loads(out.getvalue()), {"status": status, "issues": reasons})
                    self.assertEqual(path.read_text(encoding="utf-8"), text)
