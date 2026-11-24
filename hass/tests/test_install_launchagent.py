"""Fixture-only tests for the offline LaunchAgent check."""

from contextlib import redirect_stderr, redirect_stdout
from copy import deepcopy
import importlib.util
from io import StringIO
from pathlib import Path
import plistlib
from tempfile import TemporaryDirectory
import unittest


ROOT = Path(__file__).resolve().parents[2]
SPEC = importlib.util.spec_from_file_location(
    "install_launchagent", ROOT / "scripts/hass/install_launchagent.py",
)
assert SPEC is not None and SPEC.loader is not None
CHECKER = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(CHECKER)

FORWARDER = "/fixture/checkout/mac/hass_forwarder.py"
BEFORE_MARKER = "synthetic-before-private-value"
AFTER_MARKER = "synthetic-after-private-value"


class InstallLaunchAgentTests(unittest.TestCase):
    def setUp(self):
        temporary = TemporaryDirectory()
        self.addCleanup(temporary.cleanup)
        root = Path(temporary.name)
        self.before = root / "before.plist"
        self.after = root / "after.plist"
        template = ROOT / "mac/com.avocadoshack.hass-forwarder.plist.template"
        rendered = template.read_text(encoding="utf-8")
        for token, path in {
            "@PYTHON@": "/fixture/bin/python3",
            "@REPO@": "/fixture/checkout",
            "@CONFIG@": "/fixture/config.json",
            "@LOGDIR@": "/fixture/log",
        }.items():
            rendered = rendered.replace(token, path)
        self.document = plistlib.loads(rendered.encode())

    def invoke(self, forwarder=FORWARDER):
        output, errors = StringIO(), StringIO()
        with redirect_stdout(output), redirect_stderr(errors):
            status = CHECKER.main([
                "--before", str(self.before), "--after", str(self.after),
                "--forwarder", forwarder,
            ])
        self.assertEqual(errors.getvalue(), "")
        for marker in (BEFORE_MARKER, AFTER_MARKER, forwarder):
            self.assertNotIn(marker, output.getvalue())
        return status, output.getvalue().splitlines()

    def write_pair(self, before, after):
        self.before.write_bytes(plistlib.dumps(before))
        self.after.write_bytes(plistlib.dumps(after))

    def assert_failed(self, *findings, forwarder=FORWARDER):
        self.assertEqual(self.invoke(forwarder), (
            1, [*(f"FAIL {finding}" for finding in findings), "FAIL install_launchagent"],
        ))

    def test_template_pair_passes_for_xml_and_binary(self):
        # Comparing serialized bytes or assuming a fixed argument slot would fail.
        for before_fmt, after_fmt, index in (
            (plistlib.FMT_XML, plistlib.FMT_XML, 2),
            (plistlib.FMT_BINARY, plistlib.FMT_BINARY, 2),
            (plistlib.FMT_XML, plistlib.FMT_BINARY, 3),
        ):
            with self.subTest(before_fmt=before_fmt, after_fmt=after_fmt):
                doc = deepcopy(self.document)
                doc["EnvironmentVariables"] = {"FIXTURE_KEY": BEFORE_MARKER}
                if index == 3:
                    doc["ProgramArguments"].insert(1, "-u")
                self.before.write_bytes(plistlib.dumps(doc, fmt=before_fmt))
                self.after.write_bytes(plistlib.dumps(doc, fmt=after_fmt, sort_keys=False))
                self.assertEqual(self.invoke(), (0, [f"forwarder_arg {index}", "PASS install_launchagent"]))

    def test_bad_plist(self):
        # I/O and parser failures must neither traceback nor quote the input.
        for payload in (None, f"<plist><string>{BEFORE_MARKER}".encode(), b"bplist00"):
            with self.subTest(missing=payload is None, binary=payload == b"bplist00"):
                self.before.unlink(missing_ok=True)
                if payload is not None:
                    self.before.write_bytes(payload)
                self.after.write_bytes(plistlib.dumps(self.document))
                self.assert_failed("bad-plist")

    def test_not_dict(self):
        # A parseable array isn't a LaunchAgent; check both input positions.
        for before, after in (([], self.document), (self.document, [])):
            self.write_pair(before, after)
            self.assert_failed("not-dict")

    def test_label_changed(self):
        # An otherwise identical plist can't stand in for a different service.
        changed = {**self.document, "Label": AFTER_MARKER}
        self.write_pair(self.document, changed)
        self.assert_failed("label-changed")

    def test_missing_labels_do_not_match(self):
        # Two missing labels aren't evidence of the same LaunchAgent identity.
        del self.document["Label"]
        self.write_pair(self.document, self.document)
        self.assert_failed("label-changed")

    def test_changed_environment_value_reports_only_key_path(self):
        # Reporting a dict repr or a value diff would disclose environment values.
        old = {**self.document, "EnvironmentVariables": {"FIXTURE_KEY": BEFORE_MARKER}}
        new = {**self.document, "EnvironmentVariables": {"FIXTURE_KEY": AFTER_MARKER}}
        self.write_pair(old, new)
        self.assert_failed("changed EnvironmentVariables.FIXTURE_KEY")

    def test_changed_key_presence_ordered_indexes_and_types(self):
        # A shallow diff, treating argv as a set, or using bool == int misses drift.
        old, new = deepcopy(self.document), deepcopy(self.document)
        old["Extra"] = {"Entries": [BEFORE_MARKER, True], "Removed": 0}
        new["Extra"] = {"Entries": [True, BEFORE_MARKER, AFTER_MARKER], "Added": 0}
        new["RunAtLoad"] = 1
        self.write_pair(old, new)
        self.assert_failed(
            "changed Extra.Added", "changed Extra.Entries[0]", "changed Extra.Entries[1]",
            "changed Extra.Entries[2]", "changed Extra.Removed", "changed RunAtLoad",
        )

    def test_unrendered_template(self):
        # A substring nested away from argv still blocks a match on otherwise equal copies.
        for token in ("@PYTHON@", "@REPO@", "@CONFIG@", "@LOGDIR@"):
            with self.subTest(token=token):
                doc = {**self.document, "Extra": [{"Setting": f"prefix-{token}-suffix"}]}
                self.write_pair(doc, doc)
                self.assert_failed("unrendered-template")

    def test_forwarder_not_loaded(self):
        # Match an argv list element exactly, not a substring or dict key.
        for arguments in ([f"flag={FORWARDER}"], {FORWARDER: True}, None):
            doc = self.document.copy()
            if arguments is None:
                del doc["ProgramArguments"]
            else:
                doc["ProgramArguments"] = arguments
            self.write_pair(doc, doc)
            self.assert_failed("forwarder-not-loaded")

    def test_forwarder_ambiguous(self):
        # Finding the first match is not sufficient; repeated entries are refused.
        self.document["ProgramArguments"].append(FORWARDER)
        self.write_pair(self.document, self.document)
        self.assert_failed("forwarder-ambiguous")

    def test_forwarder_must_be_script_not_option_value(self):
        # A membership check accepts a stale script with the forwarder as --config;
        # skipping arbitrary flags also accepts an interpreter option's operand.
        python = self.document["ProgramArguments"][0]
        other_script = f"/fixture/{BEFORE_MARKER}.py"
        for case, arguments, extra in (
            ("config", [python, "-B", other_script, "serve", "--config", FORWARDER], {}),
            ("warning option", [python, "-W", FORWARDER, other_script], {}),
            ("module mode", [python, "-m", FORWARDER], {}),
            ("argv zero", [FORWARDER], {}),
            ("program override", [python, "-B", FORWARDER], {"Program": other_script}),
        ):
            with self.subTest(case=case):
                doc = {**self.document, "ProgramArguments": arguments, **extra}
                self.write_pair(doc, doc)
                self.assert_failed("forwarder-not-script")

    def test_not_absolute(self):
        # A verbatim match on a relative argument still fails with exit 1, not 2.
        relative = "fixture/mac/hass_forwarder.py"
        self.document["ProgramArguments"][2] = relative
        self.write_pair(self.document, self.document)
        self.assert_failed("not-absolute", forwarder=relative)

    def test_relative_forwarder_reports_load_findings_independently(self):
        relative = "fixture/mac/hass_forwarder.py"
        for count, extra in ((0, "forwarder-not-loaded"), (2, "forwarder-ambiguous")):
            with self.subTest(count=count):
                doc = deepcopy(self.document)
                doc["ProgramArguments"] = [relative] * count
                self.write_pair(doc, doc)
                self.assert_failed("not-absolute", extra, forwarder=relative)

    def test_args_usage_exit_two(self):
        # Missing required CLI options remain argparse errors, not plist findings.
        output, errors = StringIO(), StringIO()
        with redirect_stdout(output), redirect_stderr(errors), self.assertRaises(SystemExit) as exc:
            CHECKER.main(["--before", str(self.before), "--after", str(self.after)])
        self.assertEqual(exc.exception.code, 2)
        self.assertEqual(output.getvalue(), "")
        self.assertTrue(errors.getvalue().startswith("usage:"))
        self.assertIn("--forwarder", errors.getvalue())
