"""Fixture-only checks of the operator's saved-evidence CLI boundary."""

from contextlib import redirect_stderr, redirect_stdout
from io import StringIO
import json
import unittest
from unittest.mock import patch

from scripts.hass import install_runtime_readback


TARGET = "a" * 40
OTHER = "b" * 40
ROOT = "/fixture/hass/runtime"
RELEASED = "RELEASE prepared\nRELEASE switching\nRELEASE released\n"


def capture():
    return {
        "release": {"exit_code": 0, "output": RELEASED},
        "receipt": {"phase": "released", "target": TARGET, "runtime": ROOT},
        "checkout": {"root": ROOT, "head": TARGET, "status": {"exit_code": 0, "stdout": ""}},
        "running_pin": TARGET,
        "units": {
            "hass-receiver.service": {
                "exit_code": 0, "state": "active", "restarts": {"exit_code": 0, "count": 0},
            },
            "hass-worker.service": {
                "exit_code": 0, "state": "active", "restarts": {"exit_code": 0, "count": 0},
            },
            "hass-health.timer": {"exit_code": 0, "state": "active"},
        },
        "health": {"exit_code": 0, "summary": "HASS-SELFTEST 2026-11-20T00:00:00Z pass=8 warn=1 fail=0 skip=2"},
    }


class RuntimeReadbackTest(unittest.TestCase):
    def run_capture(self, text, target=TARGET, root=ROOT, *, expected_old=None):
        argv = ["--target", target, "--runtime", root]
        if expected_old is not None:
            argv += ["--expected-old", expected_old]
        stdout, stderr = StringIO(), StringIO()
        with patch("sys.stdin", StringIO(text)), redirect_stdout(stdout), redirect_stderr(stderr):
            try:
                code = install_runtime_readback.main(argv)
            except SystemExit as exc:
                code = exc.code
        return code, stdout.getvalue(), stderr.getvalue()

    def assert_refused(self, document, reason, *, expected_old=None):
        code, stdout, stderr = self.run_capture(json.dumps(document), expected_old=expected_old)
        self.assertEqual(code, 1)
        self.assertEqual(stdout, "")
        self.assertIn(reason, stderr)

    def test_completed_release_passes_without_attesting_to_process(self):
        # A successful release has progress before the final marker; an
        # attended terminal can record CRLF rather than LF.
        for line_end in ("\n", "\r\n"):
            with self.subTest(line_end=repr(line_end)):
                doc = capture()
                doc["release"]["output"] = RELEASED.replace("\n", line_end)
                code, stdout, stderr = self.run_capture(json.dumps(doc))
                self.assertEqual(code, 0)
                self.assertIn("not process attestation", stdout)
                self.assertEqual(stderr, "")
                self.assertNotIn(TARGET, stdout)
                self.assertNotIn(ROOT, stdout)

    def test_release_needs_zero_and_exact_uncontradicted_terminal_phase(self):
        # A zero-only, substring-only or any-line check would accept a plan,
        # rollback, misleading suffix, or a refusal next to a success marker.
        for code, output, reason in (
            (1, RELEASED, "exit status"),
            (False, RELEASED, "exit status"),
            (0, '{"result":"plan-only","apply":false}\n', "transcript"),
            (0, "RELEASE rolled-back\n", "transcript"),
            (0, RELEASED + "RELEASE refused preflight\n", "transcript"),
            (0, "RELEASE refused preflight\n" + RELEASED, "transcript"),
            (0, RELEASED.replace("released", "released but unverified"), "transcript"),
        ):
            with self.subTest(code=code, output=output):
                doc = capture()
                doc["release"] = {"exit_code": code, "output": output}
                self.assert_refused(doc, reason)

    def test_receipt_checkout_and_pin_are_separate_evidence(self):
        # Mutate just one observation. A checker taking identity/phase from only
        # one agreeing source (or treating an errored status as clean) misses it.
        for parent, key, value, reason in (
            (("receipt",), "phase", "switching", "receipt phase"),
            (("receipt",), "target", OTHER, "receipt target"),
            (("receipt",), "runtime", "/fixture/other", "receipt target"),
            (("checkout",), "root", "/fixture/other", "checkout root"),
            (("checkout",), "head", OTHER, "checkout HEAD"),
            (("checkout", "status"), "stdout", "?? local-file\n", "dirty"),
            (("checkout", "status"), "exit_code", 128, "checkout status"),
            ((), "running_pin", OTHER, "running pin"),
            ((), "running_pin", None, "running pin"),
        ):
            with self.subTest(field=(*parent, key), value=value):
                doc = capture()
                record = doc
                for part in parent:
                    record = record[part]
                record[key] = value
                self.assert_refused(doc, reason)

        # A target-only check would accept a stale or incomplete move receipt
        # even though the independent checkout and running pins still agree.
        doc = capture()
        doc["receipt"]["old"] = OTHER
        code, stdout, stderr = self.run_capture(json.dumps(doc), expected_old=OTHER)
        self.assertEqual((code, stderr), (0, ""))
        self.assertIn("receipt old pin matches pre-move selection", stdout)
        self.assertIn("not process attestation", stdout)
        self.assertNotIn(OTHER, stdout)

        doc["receipt"]["old"] = "c" * 40
        self.assert_refused(doc, "receipt old pin", expected_old=OTHER)
        code, stdout, stderr = self.run_capture(json.dumps(doc))
        self.assertEqual((code, stderr), (0, ""))
        self.assertNotIn("old", stdout)

        del doc["receipt"]["old"]
        self.assert_refused(doc, "receipt old pin", expected_old=OTHER)
        # Exact receipt equality alone is not evidence of a move.
        doc["receipt"]["old"] = TARGET
        self.assert_refused(doc, "not a move", expected_old=TARGET)

    def test_unit_observations_must_cover_each_unit_and_succeed(self):
        # A timer cannot stand in for a missing service; 'active' with a failed
        # query or nonzero restarts does not constitute a passing observation.
        for name in capture()["units"]:
            with self.subTest(missing=name):
                doc = capture()
                del doc["units"][name]
                self.assert_refused(doc, name)
        for fields in ({"state": "failed"}, {"exit_code": 3}, {"restarts": None},
                       {"restarts": {"exit_code": 0, "count": 1}},
                       {"restarts": {"exit_code": 1, "count": 0}}):
            with self.subTest(fields=fields):
                doc = capture()
                doc["units"]["hass-worker.service"].update(fields)
                self.assert_refused(doc, "hass-worker.service")

    def test_health_needs_both_exit_and_passing_summary(self):
        # A process can exit zero with no useful summary, or fail despite
        # having printed a success-looking summary before it exited.
        for fields in (None, {"exit_code": 1}, {"summary": None}, {"summary": "ok"},
                       {"summary": "HASS-SELFTEST now pass=8 warn=0 fail=1 skip=0"}):
            with self.subTest(fields=fields):
                doc = capture()
                if fields is None:
                    del doc["health"]
                else:
                    doc["health"].update(fields)
                self.assert_refused(doc, "health observation")

    def test_ambiguous_or_unreadable_capture_does_not_echo_input(self):
        # A default JSON decoder could silently use the later duplicate phase.
        raw = json.dumps(capture()).replace('"phase": "released"',
                                            '"phase": "synthetic-private", "phase": "released"')
        for text in (raw, raw[:-1], "[]"):
            with self.subTest(length=len(text)):
                code, stdout, stderr = self.run_capture(text)
                self.assertEqual(code, 1)
                self.assertEqual(stdout, "")
                self.assertIn("invalid capture JSON", stderr)
                self.assertNotIn("synthetic-private", stderr)

    def test_expected_selection_is_not_inferred_from_capture(self):
        # An internally consistent capture is not sufficient for another install.
        for target, root, code in ((OTHER, ROOT, 1), (TARGET, "/fixture/other", 1),
                                   (TARGET[:12], ROOT, 2), (TARGET, "runtime", 2)):
            with self.subTest(target=target, root=root):
                actual, stdout, stderr = self.run_capture(json.dumps(capture()), target, root)
                self.assertEqual(actual, code)
                self.assertEqual(stdout, "")
                self.assertIn("REFUSED", stderr)
        for malformed in ("", OTHER[:12], OTHER.upper(), "g" * 40):
            with self.subTest(expected_old=malformed):
                doc = capture()
                doc["receipt"]["old"] = malformed
                code, stdout, stderr = self.run_capture(json.dumps(doc), expected_old=malformed)
                self.assertEqual((code, stdout), (2, ""))
                self.assertIn("--expected-old must be a full lowercase 40-hex commit", stderr)
