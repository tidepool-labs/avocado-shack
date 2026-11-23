"""Fixture-only CLI contracts for the offline maker precheck."""

import json
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest


SCRIPT = Path(__file__).resolve().parents[2] / "scripts/hass/npp_maker_precheck.py"
ITEM = "Zindle crisps"
MAKER = "Quenvalo"
CAPTION = f"{ITEM} made by {MAKER}"
CATALOG = json.dumps({"makers": {"first": {"name": MAKER}}}).encode()
NOTE = "note whole-caption"
PASS = "PASS npp_maker_precheck"
FAIL = "FAIL npp_maker_precheck"


def row(caption=CAPTION):
    return json.dumps({"item": ITEM, "caption": caption}, ensure_ascii=False)


class MakerPrecheckTests(unittest.TestCase):
    def fixture(self, captions=None, makers=None):
        temporary = tempfile.TemporaryDirectory()
        self.addCleanup(temporary.cleanup)
        root = Path(temporary.name).resolve()
        content = root / "fixture-catalog"
        content.mkdir()
        captions_path = root / "fixture-caption-input.jsonl"
        makers_path = content / "makers.json"
        if captions is not None:
            captions_path.write_bytes(captions if isinstance(captions, bytes) else captions.encode("utf-8"))
        if makers is not None:
            makers_path.write_bytes(makers)
        return captions_path, makers_path

    def run_cli(self, captions, makers, *extra, content_arg=True, captions_arg=True):
        args = []
        if content_arg:
            args += ["--content", str(makers.parent)]
        if captions_arg:
            args += ["--captions", str(captions)]
        return subprocess.run(
            [sys.executable, "-B", str(SCRIPT), *args, *extra],
            cwd=captions.parent, capture_output=True, encoding="utf-8", timeout=10,
        )

    def assert_report(self, result, code, *lines):
        self.assertEqual(result.returncode, code)
        self.assertEqual(result.stderr, "")
        self.assertEqual(result.stdout, "\n".join((NOTE, *lines, PASS if code == 0 else FAIL)) + "\n")

    def test_c1_full_pass(self):
        # An ambiguous match must be reported but must not be treated like near.
        paths = self.fixture(row(), json.dumps({"makers": {
            "first": {"name": MAKER}, "second": {"name": MAKER},
        }}).encode())
        self.assert_report(self.run_cli(*paths), 0, "caption 1 maker ambiguous")

    def test_c2_1_bad_captions(self):
        # Missing, undecodable, and blank-only files must not pass as an empty batch.
        for name, raw in (("missing", None), ("symlink", None),
                          ("utf8", row().encode() + b"\n\xff"), ("blank", b"\n \t\r\n")):
            with self.subTest(case=name):
                captions, makers = self.fixture(raw, b'{"makers":{}}')
                if name == "symlink":
                    target = captions.with_suffix(".target")
                    target.write_text(row(), encoding="utf-8")
                    captions.symlink_to(target)
                self.assert_report(self.run_cli(captions, makers), 1, "FAIL bad-captions")

    def test_c2_2_bad_line(self):
        # Blank lines don't take an index, and malformed rows don't stop later checks.
        cases = ('{"item":', '[]', '{}', '{"item":1,"caption":"text"}',
                 '{"item":"text","caption":null}', '{"item":"a","caption":"b","extra":NaN}')
        paths = self.fixture("\n".join(("", row(), " \t", *cases, row(ITEM))), b'{"makers":{}}')
        self.assert_report(self.run_cli(*paths), 1, "caption 1 maker new",
                           *(f"FAIL bad-line {i}" for i in range(2, 8)), "caption 8 maker absent")

    def test_c2_3_unreadable_makers(self):
        # A schema or read error must not silently fall back to an empty catalogue.
        cases = (None, b"\xff", b"{", b"[]", b"{}", b'{"makers":[]}',
                 b'{"makers":{"first":{"name":"Sample"},"second":false}}',
                 b'{"makers":{"first":{}}}', b'{"makers":{"first":{"name":4}}}')
        for index, raw in enumerate(cases):
            with self.subTest(case=index):
                self.assert_report(self.run_cli(*self.fixture(row(), raw)), 1, "FAIL unreadable makers")
        captions, makers = self.fixture(row())
        target = makers.with_suffix(".target")
        target.write_bytes(b'{"makers":{}}')
        makers.symlink_to(target)
        self.assert_report(self.run_cli(captions, makers), 1, "FAIL unreadable makers")

    def test_c2_4_near(self):
        # A state-only report would miss an operator-facing question; keep checking after it.
        paths = self.fixture("\n".join((row(f"{ITEM} made by Quen-valo"), "{}", row(ITEM))), CATALOG)
        self.assert_report(self.run_cli(*paths), 1, "caption 1 maker near", "FAIL near 1",
                           "FAIL bad-line 2", "caption 3 maker absent")

    def test_c3_usage_exit_2(self):
        # Parser errors are distinct from findings and never start the stdout report.
        paths = self.fixture(row(), b'{"makers":{}}')
        cases = (
            ((), {"content_arg": False}),
            ((), {"captions_arg": False}),
            (("--unknown",), {}),
            (("--captions",), {"captions_arg": False}),
        )
        for extra, options in cases:
            with self.subTest(extra=extra, options=options):
                result = self.run_cli(*paths, *extra, **options)
                self.assertEqual(result.returncode, 2)
                self.assertEqual(result.stdout, "")
                self.assertTrue(result.stderr.startswith("usage: "))

    def test_c4_read_only(self):
        # Snapshot bytes, file mtimes and directory entries (including directories).
        captions, makers = self.fixture(row(), b'{"makers":{}}')

        def snapshot():
            return {p: (p.read_bytes() if p.is_file() else None, p.stat().st_mtime_ns)
                    for p in (captions.parent, *captions.parent.rglob("*"))}

        before = snapshot()
        self.assert_report(self.run_cli(captions, makers), 0, "caption 1 maker new")
        self.assertEqual(snapshot(), before)

    def test_c5_no_private_values(self):
        # Neither report text, invalid-row diagnostics, nor usage errors may echo inputs.
        near = f"{ITEM} made by {MAKER}s"
        captions, makers = self.fixture(row(near) + '\n{"caption":"Zymber syntax marker"', CATALOG)
        report = self.run_cli(captions, makers)
        usage = self.run_cli(captions, makers, str(captions), str(makers.parent))
        canaries = (near, ITEM, MAKER, "Zymber syntax marker", str(captions), str(makers), str(makers.parent))
        for result in (report, usage):
            for stream in (result.stdout, result.stderr):
                self.assertFalse(any(value in stream for value in canaries), "input canary leaked")
        self.assert_report(report, 1, "caption 1 maker near", "FAIL near 1", "FAIL bad-line 2")
        self.assertEqual(usage.returncode, 2)
        self.assertEqual(usage.stdout, "")

    def test_c6_owner_forms(self):
        # Using only one owner form, or dropping the hedge before matching, changes these states.
        paths = self.fixture("\n".join((row(), row(f"{MAKER}'s {ITEM}"), row(CAPTION + " maybe"))), CATALOG)
        self.assert_report(self.run_cli(*paths), 0, "caption 1 maker known",
                           "caption 2 maker known", "caption 3 maker absent")

    def test_c7_near_and_new(self):
        # Plural normalization should find the near match, not turn all unknowns into findings.
        self.assert_report(self.run_cli(*self.fixture(row(f"{CAPTION}s"), CATALOG)),
                           1, "caption 1 maker near", "FAIL near 1")
        self.assert_report(self.run_cli(*self.fixture(row(f"{ITEM} made by Brivuno"), CATALOG)),
                           0, "caption 1 maker new")


if __name__ == "__main__":
    unittest.main()
