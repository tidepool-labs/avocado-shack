"""Behavioural contract for the offline maker sources review CLI."""

from contextlib import redirect_stderr, redirect_stdout
import importlib.util
import io
import json
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest


SCRIPT = Path(__file__).resolve().parents[2] / "scripts/hass/npp_sources_review.py"
PASS = "PASS npp_sources_review"
FAIL = "FAIL npp_sources_review"


def entry(maker="Sample Grove", domain="sample.example", **changes):
    return {"maker": maker, "domain": domain, "added_by": "G", "reviewed_in": "example review"} | changes


def sources(*entries, **changes):
    return {"allowlist": list(entries), "allowlist_entry_shape": {
        "maker": "maker name", "domain": "domain", "added_by": "G", "reviewed_in": "PR number",
    }, "deny_domains": [], "schema": 1} | changes


class SourcesReviewTests(unittest.TestCase):
    def setUp(self):
        temporary = tempfile.TemporaryDirectory()
        self.addCleanup(temporary.cleanup)
        self.root = Path(temporary.name)
        self.current = self.save("current.json", sources())
        self.proposed = self.save("proposed.json", sources())

    def save(self, name, value):
        path = self.root / name
        path.write_text(json.dumps(value), encoding="utf-8")
        return path

    def args(self, **overrides):
        paths = {"current": self.current, "proposed": self.proposed} | overrides
        return [arg for name, path in paths.items() for arg in (f"--{name}", str(path))]

    def run_cli(self, *args):
        return subprocess.run([sys.executable, "-B", str(SCRIPT), *args], cwd=self.root,
                              capture_output=True, text=True, encoding="utf-8", timeout=10)

    def assert_status(self, result, code, last):
        self.assertEqual(result.returncode, code, result.stderr)
        self.assertEqual(result.stderr, "")
        lines = result.stdout.splitlines()
        self.assertEqual(lines[-1:], [last])
        return lines

    def assert_findings(self, result, *reasons):
        lines = self.assert_status(result, 1, FAIL)
        self.assertEqual([line for line in lines[:-1] if line.startswith("FAIL")],
                         [f"FAIL {reason}" for reason in reasons])
        return lines

    def test_c1_full_pass(self):
        # Comparing entire entries would turn a review-note edit into a site change.
        retained = entry(domain="b" + "c" * 61 + "d.example")
        self.save(self.current.name, sources(retained, entry("Old Grove", "old.example"),
                                             deny_domains=["old-deny.example"], retired=None,
                                             discovery={"enabled": True}, stable={"a": 1, "b": 2}))
        self.save(self.proposed.name, sources(retained | {"reviewed_in": "other review"},
                                              entry("New Grove", "new.example"),
                                              entry("New Grove", "b.new.example"),
                                              deny_domains=["new-deny.example"], introduced=None,
                                              discovery={"enabled": 1}, stable={"b": 2, "a": 1}))
        result = self.run_cli(*self.args())
        lines = self.assert_status(result, 0, PASS)
        self.assertCountEqual(lines[:-1], [
            "allowlist-added New Grove new.example", "allowlist-added New Grove b.new.example",
            "allowlist-removed Old Grove old.example", "deny-added new-deny.example",
            "deny-removed old-deny.example", "changed-key discovery", "changed-key introduced",
            "changed-key retired", "entries 3",
        ])

    def test_c2_1_unreadable(self):
        # Loading a symlink, using a permissive decoder, or defaulting a missing list hides bad inputs.
        valid = self.save("valid.json", sources())
        alias = self.root / "alias.json"
        alias.symlink_to(valid)
        bad_utf8 = self.root / "nonutf8.json"
        bad_utf8.write_bytes(b'{"allowlist":[],"note":"\xff"}')
        bad_json = self.root / "broken.json"
        bad_json.write_bytes(b'{"allowlist":[],"note":NaN}')
        for bad in (self.root / "absent.json", alias, bad_utf8, bad_json,
                    self.save("missing-list.json", {}), self.save("wrong-list.json", {"allowlist": {}})):
            for role in ("current", "proposed"):
                with self.subTest(input=bad.name, role=role):
                    self.assert_findings(self.run_cli(*self.args(**{role: bad})), f"unreadable {role}")
        self.assert_findings(self.run_cli(*self.args(current=alias, proposed=bad_json)),
                             "unreadable current", "unreadable proposed")

    def test_c2_2_entry_shape(self):
        # Subset checks, truthiness-only checks, and arbitrary added_by values would all pass bad rows.
        for invalid in ([], entry(extra="extra"), entry(reviewed_in=""), entry(reviewed_in=1),
                        entry(added_by="other"), {"maker": "Sample Grove", "domain": "sample.example",
                                                  "added_by": "G"}):
            with self.subTest(entry=invalid):
                self.save(self.proposed.name, sources(entry(domain="valid.example"), invalid))
                self.assert_findings(self.run_cli(*self.args()), "entry-shape 1")
        # The proposed schema supplies the key set; printing its change is still informational.
        proposal = sources(entry(review_tag="example"))
        proposal["allowlist_entry_shape"]["review_tag"] = "an example field"
        self.save(self.proposed.name, proposal)
        lines = self.assert_status(self.run_cli(*self.args()), 0, PASS)
        self.assertIn("changed-key allowlist_entry_shape", lines)

    def test_c2_3_domain_form(self):
        # URL parsing or a loose suffix regex would let invalid host spellings through.
        for domain in ("Sample.example", "sámple.example", "https://sample.example", "sample.example/path",
                       "sample.example:443", "*.sample.example", ".sample.example", "sample.example.",
                       "192.0.2.1", "2001:db8::1", "localhost", "sample..example", "-sample.example",
                       "sample-.example", "a_b.example", "a" * 64 + ".example", "sample.example\n"):
            with self.subTest(domain=domain):
                self.save(self.proposed.name, sources(entry(domain=domain)))
                self.assert_findings(self.run_cli(*self.args()), "domain-form 0")

    def test_c2_4_domain_punycode(self):
        # Checking only the first label misses an A-label in a later position.
        self.save(self.proposed.name, sources(entry(domain="a.xn--bcher-kva.example"),
                                              entry(domain="a.foxn--ample.example"),
                                              entry(domain="xn--malformed-.example")))
        self.assert_findings(self.run_cli(*self.args()), "domain-punycode 0", "domain-form 2")

    def test_c2_5_domain_denied(self):
        # Exact-only matching misses subdomains; raw endswith overmatches neighbors.
        self.save(self.current.name, sources(deny_domains=["formerly-denied.example"]))
        self.save(self.proposed.name, sources(entry(domain="denied.example"),
                                              entry(domain="sub.denied.example"),
                                              entry(domain="notdenied.example"),
                                              entry(domain="formerly-denied.example"),
                                              deny_domains=["denied.example", "example.invalid"]))
        self.assert_findings(self.run_cli(*self.args()), "domain-denied 0", "domain-denied 1")

    def test_c2_6_duplicate_entry(self):
        # Raw/case-only matching misses accents and spaces; domain-only matching overflags.
        self.save(self.proposed.name, sources(entry(maker="Sámple  Grove"), entry(maker="SAMPLE GROVE"),
                                              entry(maker="Other Grove"), entry(domain="other.example"),
                                              entry()))
        self.assert_findings(self.run_cli(*self.args()), "duplicate-entry 1", "duplicate-entry 4")

    def test_c2_7_maker_unknown(self):
        # The copied registry permits either its key or its name, and is only consulted on request.
        makers = self.save("makers.json", {"schemaVersion": 1, "makers": {
            "sámple-key": {"name": "Sample Gróve"},
        }})
        self.save(self.proposed.name, sources(entry(maker="SAMPLE-KEY"), entry(maker="sample  grove"),
                                              entry(maker="Unlisted Grove")))
        self.assert_findings(self.run_cli(*self.args(makers=makers)), "maker-unknown 2")
        self.assert_status(self.run_cli(*self.args()), 0, PASS)

    def test_c3_usage_exit_2(self):
        # Parser errors must not look like review findings or echo unrecognized arguments.
        for args in ([], self.args() + ["--unknown", "synthetic-argument"],
                     self.args() + ["--makers"], self.args(makers=self.root / "absent-makers.json")):
            with self.subTest(args=args):
                result = self.run_cli(*args)
                self.assertEqual(result.returncode, 2)
                self.assertEqual(result.stdout, "")
                self.assertEqual(result.stderr.splitlines()[-1],
                                 "npp_sources_review.py: error: invalid arguments or makers file; see --help")

    def test_c4_read_only(self):
        # Even a byte-identical rewrite or transient file in an input directory changes an mtime.
        self.save(self.proposed.name, sources(entry()))
        makers = self.save("makers.json", {"makers": {"Sample Grove": {}}})
        files = (self.current, self.proposed, makers)

        def snapshot():
            return ([(path.read_bytes(), path.stat().st_mtime_ns) for path in files],
                    set(self.root.rglob("*")), self.root.stat().st_mtime_ns)

        before = snapshot()
        self.assert_status(self.run_cli(*self.args(makers=makers)), 0, PASS)
        self.assertEqual(snapshot(), before)

    def test_c5_no_private_values(self):
        # A document dump, traceback, or CLI error echo would disclose unrelated input data.
        canaries = {"message": "synthetic-message-canary", "chat": "synthetic-chat-canary",
                    "sender": "synthetic-sender-canary", "id": "synthetic-id-canary",
                    "digest": "synthetic-digest-canary"}
        self.save(self.current.name, sources(entry(reviewed_in=canaries["id"]), notes=canaries))
        self.save(self.proposed.name, sources(entry("Other Grove", "other.example", reviewed_in=canaries["digest"]),
                                              notes={**canaries, "input_path": str(self.current)}))
        success = self.run_cli(*self.args())
        self.assertIn("changed-key notes", self.assert_status(success, 0, PASS))
        self.save(self.proposed.name, sources(entry(domain=str(self.current)), notes=canaries))
        finding = self.run_cli(*self.args())
        self.assert_findings(finding, "domain-form 0")
        usage = self.run_cli(*self.args(), str(self.proposed), canaries["message"])
        self.assertEqual((usage.returncode, usage.stdout), (2, ""))
        for result in (success, finding, usage):
            for value in (*canaries.values(), str(self.current), str(self.proposed)):
                self.assertNotIn(value, result.stdout + result.stderr)

    def test_c6_identical_pass(self):
        # An unchanged shipped-shape empty list must not invent additions or findings.
        spec = importlib.util.spec_from_file_location("npp_sources_review", SCRIPT)
        assert spec is not None and spec.loader is not None
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)
        with redirect_stdout(io.StringIO()) as out, redirect_stderr(io.StringIO()) as err:
            code = module.main(self.args())
        self.assertEqual(code, 0)
        self.assertEqual(err.getvalue(), "")
        self.assertEqual(out.getvalue().splitlines(), ["entries 0", PASS])

    def test_c7_removal_only_pass(self):
        # Reviewing removed rows would flag an old malformed domain no longer in the proposal.
        self.save(self.current.name, sources(entry(), entry("Old Grove", "Old.example")))
        lines = self.assert_status(self.run_cli(*self.args()), 0, PASS)
        self.assertCountEqual(lines[:-1], ["allowlist-removed Old Grove Old.example",
                                           "allowlist-removed Sample Grove sample.example", "entries 0"])
