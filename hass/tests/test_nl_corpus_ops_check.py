"""Offline CLI contract tests for the corpus-to-registry check."""

import json
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile
import unittest

from hass import nl_eval


ROOT = Path(__file__).resolve().parents[2]
SCRIPT = ROOT / "scripts/hass/nl_corpus_ops_check.py"
PASS = "PASS nl_corpus_ops_check"
FAIL = "FAIL nl_corpus_ops_check"


def call(op, **args):
    return {"op": op, "args": args}


def case(case_id, *calls, text="A synthetic owner request."):
    return {
        "id": case_id, "text": text, "intent": "maker", "pending": [],
        "ask": not calls, "refuse": False,
        "expect": {"ops": list(calls), "revises": None} if calls else {"question": True},
    }


class NlCorpusOpsCheckTests(unittest.TestCase):
    def setUp(self):
        temporary = tempfile.TemporaryDirectory(prefix=".nl-corpus-", dir=ROOT)
        self.addCleanup(temporary.cleanup)
        self.root = Path(temporary.name)
        self.content = self.root / "content-copy"
        self.content.mkdir()
        self.corpus = self.root / "corpus-copy.jsonl"
        documents = {
            "makers": {"makers": {"harbor-lane": {
                "name": "Harbor Lane", "place": "Testville, California", "story": "Makes jam.",
            }}},
            "products": {"products": [{
                "id": "photo-product-001", "name": "Test Jam", "brand": "Harbor Lane",
                "displayBrand": "Harbor Lane", "category": "pantry", "producerKey": "harbor-lane",
                "image": "assets/products/photo-product-001.webp", "description": "A berry jam.",
                "status": "active",
            }]},
            "community": {"club": {"clubName": "Test Walk Club", "organizer": "Test Organizer",
                                   "intendedSender": "club@example.com", "emailConnected": False},
                          "events": [], "routeIdeas": []},
            "store": {"name": "Test Shop", "streetAddress": "1 Example Way", "town": "Testville",
                      "hours": ["Monday-Friday 9am-5pm", "Closed Saturday-Sunday"]},
        }
        for name, document in documents.items():
            (self.content / f"{name}.json").write_text(
                json.dumps({"schemaVersion": 1, **document}), encoding="utf-8",
            )

    def write_rows(self, rows):
        self.corpus.write_text("".join(json.dumps(row) + "\n" for row in rows), encoding="utf-8")

    def fixture_corpus(self, *special):
        padding = (case(f"pad-{n}") for n in range(nl_eval.MIN_CASES - len(special)))
        self.write_rows([*special, *padding])

    def cli(self, *args):
        return subprocess.run([sys.executable, "-B", str(SCRIPT), *map(str, args)],
                              cwd=self.root, capture_output=True, text=True, timeout=15)

    def check(self, *, content=None, corpus=None):
        return self.cli("--content", content or self.content, "--corpus", corpus or self.corpus)

    def assert_report(self, result, code, *lines):
        self.assertEqual(result.returncode, code)
        self.assertEqual(result.stderr, "")
        trailer = PASS if code == 0 else FAIL
        self.assertEqual(result.stdout, "\n".join((*lines, trailer)) + "\n")

    def assert_fixture_report(self, result, code, calls, missing, *lines):
        self.assert_report(result, code, f"cases {nl_eval.MIN_CASES}", f"calls {calls}",
                           f"missing-required {missing}", *lines)

    def test_c1_full_pass(self):
        # A missing argument is informational; alternate expectations are not scanned.
        primary = case("primary", call("maker.restore", key="harbor-lane"), call("maker.edit"))
        primary["also"] = [{"ops": [call("synthetic.absent")], "revises": None}]
        self.fixture_corpus(primary)
        self.assert_fixture_report(self.check(), 0, 2, 1)

    def test_c2_findings_trailer(self):
        # Neither condition may stop scanning or replace the fixed final marker.
        self.fixture_corpus(case("both", call("product.edit", id="photo-product-001",
                                            producerKey="missing-maker"),
                                 call("synthetic.absent")),
                            case("later", call("synthetic.absent")))
        self.assert_fixture_report(self.check(), 1, 3, 0, "FAIL arg-problem both",
                                   "FAIL unknown-op both", "FAIL unknown-op later")

    def test_c2_1_unsafe_input(self):
        # Following a symlink would let a valid target pass the entry-type guard.
        self.fixture_corpus()
        content_link = self.root / "content-link"
        content_link.symlink_to(self.content, target_is_directory=True)
        corpus_link = self.root / "corpus-link"
        corpus_link.symlink_to(self.corpus)
        missing = self.root / "absent"
        for content, corpus in ((content_link, self.corpus), (self.corpus, self.corpus),
                                (missing, self.corpus), (self.content, corpus_link),
                                (self.content, self.content), (self.content, missing)):
            with self.subTest(content=content.name, corpus=corpus.name):
                self.assert_report(self.check(content=content, corpus=corpus), 1,
                                   "FAIL unsafe-input")

    def test_c2_2_content_invalid(self):
        # Valid JSON can violate the content schema, and UTF-8 decoding can fail too.
        self.fixture_corpus()
        for invalid_store in (b'{"schemaVersion": 1, "store": {}}', b"\xff"):
            with self.subTest(raw=invalid_store):
                (self.content / "store.json").write_bytes(invalid_store)
                self.assert_report(self.check(), 1, "FAIL content-invalid")

    def test_c2_3_corpus_invalid(self):
        # A direct JSONL reader could skip the scorer's minimum case requirement.
        self.write_rows([case("short")])
        self.assert_report(self.check(), 1, "FAIL corpus-invalid")

    def test_c2_4_unknown_op(self):
        # Two missing registry entries are two calls but one finding for the case.
        self.fixture_corpus(case("unknown", call("synthetic.absent"), call("synthetic.gone")))
        self.assert_fixture_report(self.check(), 1, 2, 0, "FAIL unknown-op unknown")

    def test_c2_5_arg_problem(self):
        # A name-only checker (or an empty maker table) would misreport these calls.
        self.fixture_corpus(
            case("good", call("product.edit", id="photo-product-001", producerKey="harbor-lane")),
            case("bad", call("product.edit", id="photo-product-001", producerKey="missing-maker"),
                 call("maker.edit", key="harbor-lane", url="not-a-url")),
        )
        self.assert_fixture_report(self.check(), 1, 3, 0, "FAIL arg-problem bad")

        # No site directory is supplied; an uncheckable image must not pass or crash.
        self.fixture_corpus(case("image", call("product.edit", id="photo-product-001",
                                              image="assets/products/photo-product-001.webp")))
        self.assert_fixture_report(self.check(), 1, 1, 0, "FAIL arg-problem image")

    def test_c3_usage_exit_2(self):
        # Usage errors must not become exit-1 findings or write a report trailer.
        for args in ((), ("--content",), ("--content", self.content, "--unknown")):
            with self.subTest(args=len(args)):
                result = self.cli(*args)
                self.assertEqual(result.returncode, 2)
                self.assertEqual(result.stdout, "")
                self.assertTrue(result.stderr.startswith("usage:"))

    def test_c4_read_only(self):
        # Compare contents and mtimes: a same-byte rewrite or new sidecar still fails.
        self.fixture_corpus(case("write-check", call("maker.restore", key="harbor-lane")))

        def snapshot():
            return {
                path.relative_to(self.root): (path.stat().st_mtime_ns,
                                              None if path.is_dir() else path.read_bytes())
                for path in (self.root, *self.root.rglob("*"))
            }

        before = snapshot()
        self.assert_fixture_report(self.check(), 0, 1, 0)
        self.assertEqual(snapshot(), before)

    def test_c5_no_private_values(self):
        # Registry diagnostics can name argument keys; argparse can echo extra paths.
        arg_key = "synthetic-argument-key"
        arg_value = "synthetic-argument-value"
        owner_text = "Synthetic owner text privacy marker."
        invalid_id = "Private_Case"
        self.fixture_corpus(case(invalid_id, call("maker.edit", key="harbor-lane",
                                                 **{arg_key: arg_value}), text=owner_text))
        result = self.check()
        usage = self.cli("--content", self.content, "--corpus", self.corpus, self.root / "extra")
        for run in (result, usage):
            for marker in (arg_key, arg_value, owner_text, invalid_id, str(self.root)):
                self.assertNotIn(marker, run.stdout + run.stderr)
        self.assert_fixture_report(result, 1, 1, 0, "note invalid-id 1", "FAIL arg-problem")
        self.assertEqual((usage.returncode, usage.stdout), (2, ""))

    def test_c6_live_corpus(self):
        # The default path must work outside the checkout; pin all real findings.
        content = shutil.copytree(ROOT / "hass/content", self.root / "repo-copy")
        result = self.cli("--content", content)
        self.assert_report(result, 1, "cases 357", "calls 213", "missing-required 32",
                           "FAIL arg-problem n090", "FAIL arg-problem n093")

    def test_c7_clean_corpus(self):
        # Removing the two rows must clear the findings, not hide a fixed failure list.
        content = shutil.copytree(ROOT / "hass/content", self.root / "repo-copy")
        clean = [row for row in nl_eval.load_corpus(nl_eval.CORPUS)
                 if row["id"] not in {"n090", "n093"}]
        self.write_rows(clean)
        result = self.check(content=content)
        self.assert_report(result, 0, "cases 355", "calls 211", "missing-required 31")


if __name__ == "__main__":
    unittest.main()
