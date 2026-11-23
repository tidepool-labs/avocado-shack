"""Offline CLI coverage for the NPP regression-case scaffolder."""

import json
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import patch

from hass.tests import test_npp_assets as assets

SCRIPT = assets.ROOT / "scripts" / "hass" / "npp_case_new.py"
DAY = "2040-02-29"
TITLE = "Synthetic regression case"


class NppCaseNewTest(unittest.TestCase):
    def setUp(self):
        with_temp = tempfile.TemporaryDirectory()
        self.addCleanup(with_temp.cleanup)
        self.cases = Path(with_temp.name) / "cases"
        self.cases.mkdir()
        for source in assets.CASES.glob("*.json"):
            shutil.copyfile(source, self.cases / source.name)

    def cli(self, *, day=DAY, slug="fixture-regression", path="question", cases=None):
        return self.run_cli("--cases", str(cases or self.cases), "--day", day,
                            "--slug", slug, "--path", path, "--title", TITLE)

    def run_cli(self, *args):
        return subprocess.run([sys.executable, "-B", str(SCRIPT), *args], cwd=assets.ROOT,
                              capture_output=True, text=True, timeout=15)

    def assert_pass(self, result, filename):
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        self.assertEqual(result.stdout.splitlines()[-1], f"PASS npp_case_new {filename}")

    def assert_fail(self, result):
        self.assertEqual(result.returncode, 1, result.stdout + result.stderr)
        self.assertRegex(result.stdout.splitlines()[-1], r"^FAIL \S")

    def test_c1_next_id_valid(self):
        # Sparse IDs and serials catch count-based allocation and string sorting;
        # the larger serial on another day must not affect this day's tag.
        case = assets.load(next(self.cases.glob("case-18-*.json")))
        for case_id, slug in [(60, "npp-20400229-11-older"), (81, "npp-20400229-2"),
                              (98, "npp-20400228-90-other-day")]:
            existing = dict(case, id=case_id, slug=slug)
            (self.cases / f"case-{case_id}-{slug}.json").write_text(json.dumps(existing), encoding="utf-8")
        words = "a" * 40
        filename = f"case-99-npp-20400229-12-{words}.json"
        self.assert_pass(self.cli(slug=words, path="listing"), filename)
        schema = assets.load(self.cases / "case.schema.json")
        created = assets.load(self.cases / filename)
        self.assertEqual(assets.validate(schema, created), [])
        self.assertEqual((created["id"], created["slug"], created["path"], created["title"]),
                         (99, f"npp-20400229-12-{words}", "listing", TITLE))
        self.assert_pass(self.cli(day="2040-03-01", path="contract"),
                         "case-100-npp-20400301-1-fixture-regression.json")

    def test_c2_never_overwrite(self):
        # A pre-existing filename with stale JSON identity can collide with the
        # computed name; an ordinary write would destroy that file.
        highest = max(assets.load(p)["id"] for p in self.cases.glob("case-*.json"))
        collision = self.cases / f"case-{highest + 1:02d}-npp-20400229-1-fixture-regression.json"
        shutil.copyfile(next(self.cases.glob("case-18-*.json")), collision)
        before = {p.name: p.read_bytes() for p in self.cases.iterdir()}
        self.assert_fail(self.cli())
        for slug in ("ab", "a" * 41, "Upper", "two words", "../escape", "ok-\n"):
            with self.subTest(slug=slug):
                self.assert_fail(self.cli(slug=slug))
        self.assertEqual({p.name: p.read_bytes() for p in self.cases.iterdir()}, before)

    def test_c3_unfinished_fails(self):
        # A schema-valid but ready-looking state would let an unfinished case
        # through the existing expectation check. Exercise that check unchanged.
        result = self.cli()
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        target = next(self.cases.glob("case-*-npp-20400229-1-fixture-regression.json"))
        check = assets.CaseInputsTest("test_expect_keys_and_checks_are_in_the_documented_vocabulary")
        with patch.object(assets, "CASES", self.cases):
            check.setUp()
            with self.assertRaisesRegex(AssertionError, r"'TODO' != 'asking'"):
                check.test_expect_keys_and_checks_are_in_the_documented_vocabulary()
            created = assets.load(target)
            created["expect"]["state"] = created["terminal"]
            target.write_text(json.dumps(created), encoding="utf-8")
            check.setUp()
            check.test_expect_keys_and_checks_are_in_the_documented_vocabulary()

    def test_c4_exit(self):
        # Missing target data is an operational failure; missing CLI flags are
        # usage errors. Scripts must be able to distinguish both from success.
        highest = max(assets.load(p)["id"] for p in self.cases.glob("case-*.json"))
        self.assert_pass(self.cli(), f"case-{highest + 1:02d}-npp-20400229-1-fixture-regression.json")
        self.assert_fail(self.cli(cases=self.cases / "not-found"))
        self.assert_fail(self.cli(day="2040-02-30"))
        usage = self.run_cli("--cases", str(self.cases))
        self.assertEqual(usage.returncode, 2, usage.stdout + usage.stderr)
        self.assertIn("usage:", usage.stderr)
        self.assertNotIn("PASS", usage.stdout)

    def write_ledger(self, *rows):
        ledger = self.cases.parent / "findings.tsv"
        with ledger.open("x", encoding="utf-8") as out:
            out.write("id\tweek\tstage\tclass\tsummary\tcase_id\tcard\tstate\treason\n")
            for serial, (stage, summary, state, card, reason) in enumerate(rows, 1):
                out.write(f"F-2040-W09-{serial}\t2040-W09\t{stage}\tfixture\t{summary}\t\t{card}\t{state}\t{reason}\n")
        ledger.chmod(0o600)
        return ledger

    def from_finding(self, ledger, serial):
        return self.run_cli("--cases", str(self.cases), "--day", DAY, "--slug", "fixture-regression",
                            "--finding", f"F-2040-W09-{serial}", "--ledger", str(ledger))

    def test_c5_from_finding(self):
        # Distinct summaries catch using the wrong row; S8/S9 and S13 catch
        # off-by-one mapping, and the schema-valid title must retain the pointer.
        examples = [("S3", "Synthetic question", "question", "asking"),
                    ("S8", "Synthetic rendering", "listing", "published"),
                    ("S9", "Synthetic card", "contract", "card_out"),
                    ("S10", "Synthetic edits", "contract", "card_out"),
                    ("S11", "Synthetic approval", "contract", "card_out"),
                    ("S12", "Synthetic installation", "contract", "card_out"),
                    ("S13", "Synthetic confirmation", "contract", "card_out")]
        ledger = self.write_ledger(*[(stage, summary, "open", "", "") for stage, summary, _, _ in examples])
        schema = assets.load(self.cases / "case.schema.json")
        highest = max(assets.load(p)["id"] for p in self.cases.glob("case-*.json"))
        for serial, (stage, summary, path, terminal) in enumerate(examples, 1):
            with self.subTest(stage=stage):
                name = f"case-{highest + serial:02d}-npp-20400229-{serial}-fixture-regression.json"
                self.assert_pass(self.from_finding(ledger, serial), name)
                case = assets.load(self.cases / name)
                self.assertEqual(assets.validate(schema, case), [])
                self.assertEqual(case["title"], f"{summary} [F-2040-W09-{serial}]")
                self.assertEqual((case["path"], case["terminal"]), (path, terminal))

    def test_c6_refuse_closed(self):
        # Testing only state == 'closed' would accept a resolved repeat.
        ledger = self.write_ledger(("S3", "Synthetic resolved question", "closed", "fixture-card", "resolved"),
                                   ("S3", "Synthetic resolved repeat", "repeat", "fixture-repeat", "resolved"))
        before = set(self.cases.iterdir())
        for serial in (1, 2):
            with self.subTest(serial=serial):
                result = self.from_finding(ledger, serial)
                self.assert_fail(result)
                self.assertIn("closed", result.stdout.splitlines()[-1])
                self.assertEqual(set(self.cases.iterdir()), before)

    def test_c7_ledger_untouched(self):
        # A successful scaffold must not close the finding, rewrite unchanged
        # bytes, or invoke the ledger update path and create a lock sidecar.
        ledger = self.write_ledger(("S9", "Synthetic first finding", "closed", "fixture-card", "resolved"),
                                   ("S9", "Synthetic pending repeat", "repeat", "", ""))
        before = (ledger.read_bytes(), ledger.stat().st_mtime_ns, set(ledger.parent.iterdir()))
        highest = max(assets.load(p)["id"] for p in self.cases.glob("case-*.json"))
        self.assert_pass(self.from_finding(ledger, 2),
                         f"case-{highest + 1:02d}-npp-20400229-1-fixture-regression.json")
        self.assertEqual((ledger.read_bytes(), ledger.stat().st_mtime_ns, set(ledger.parent.iterdir())), before)


if __name__ == "__main__":
    unittest.main()
