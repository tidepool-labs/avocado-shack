"""Fixture-only tests for scripts/hass/npp_host_receipt_wiring.py (SAA0300-01).

The tool builds a real worker through host.make_worker and asks whether the NPP job runner gets the relay's delivery
receipts. Each contract test names the believable bug that makes it fail. The in-process cases subclass the real
Worker and change only the binding of conv.npp.receipt_for; the factory, dispatch, store, ACK and consumer are the
production ones. The script's own run never does that."""

import ast
import contextlib
import importlib.util
import io
import os
from pathlib import Path
import re
import subprocess
import sys
import tempfile
import unittest
from unittest import mock

from hass import host

REPO = Path(__file__).resolve().parents[2]
SCRIPT = REPO / "scripts/hass/npp_host_receipt_wiring.py"
spec = importlib.util.spec_from_file_location("npp_host_receipt_wiring", SCRIPT)
tool = importlib.util.module_from_spec(spec)
spec.loader.exec_module(tool)

TRAILER = "FAIL npp_host_receipt_wiring"
PASS = "PASS npp_host_receipt_wiring"
BASELINE = ["host card_dispatched=no relay_receipt_consumed=no", "FAIL card-not-dispatched", "FAIL receipt-unwired", TRAILER]
HEALTHY = ["host card_dispatched=yes relay_receipt_consumed=yes", PASS]
LINE_FORMS = (re.compile(r"host card_dispatched=(yes|no) relay_receipt_consumed=(yes|no)"),
              re.compile(r"FAIL (card-not-dispatched|receipt-unwired|check-error|npp_host_receipt_wiring)"),
              re.compile(r"PASS npp_host_receipt_wiring"))


def own_receipts(worker):
    """What the host should do: hand the sender's own receipt reader to the job runner."""
    worker.conv.npp.receipt_for = worker.sender.receipt_for


def bound(binder):
    """A real Worker whose constructor runs unchanged, then only the receipt binding is set by `binder`."""
    class Bound(host.Worker):
        def __init__(self, *args, **kwargs):
            super().__init__(*args, **kwargs)
            binder(self)
    return Bound


def run_main(worker_class=None):
    out, err = io.StringIO(), io.StringIO()
    with contextlib.ExitStack() as stack:
        if worker_class is not None:
            stack.enter_context(mock.patch.object(host, "Worker", worker_class))
        stack.enter_context(contextlib.redirect_stdout(out))
        stack.enter_context(contextlib.redirect_stderr(err))
        rc = tool.main([])
    assert err.getvalue() == "", err.getvalue()
    return rc, out.getvalue().splitlines()


def run_script(*args):
    return subprocess.run([sys.executable, "-B", str(SCRIPT), *args], cwd=REPO, capture_output=True, text=True, timeout=120)


def snapshot():
    seen = {}
    for top in ("hass", "storefront-mockup"):
        for path in sorted((REPO / top).rglob("*")):
            info = path.lstat()
            seen[str(path.relative_to(REPO))] = (info.st_size, info.st_mtime_ns)
    return seen


class HostReceiptWiringTests(unittest.TestCase):
    def test_c1_full_pass(self):
        # A probe that cannot reach yes/yes (wrong store, ids or a lost PNG) never exits 0 with the exact last line.
        rc, lines = run_main(bound(own_receipts))
        self.assertEqual((rc, lines), (0, HEALTHY))
        self.assertEqual(lines[-1], PASS)

    def test_c2_findings_trailer(self):
        # Both findings, in the listed order, then the trailer; a host that never binds the callback is the baseline red.
        rc, lines = run_main(bound(lambda worker: setattr(worker.conv.npp, "receipt_for", None)))
        self.assertEqual((rc, lines), (1, BASELINE))
        self.assertEqual(lines[-1], TRAILER)

    def test_c2_1_card_not_dispatched(self):
        # dispatch() that returns False, or True without queueing, must not count; the fallback send never counts either.
        for result in (False, True):
            with self.subTest(returns=result), mock.patch.object(tool.npp_job.Jobs, "dispatch", lambda *a, _r=result: _r):
                rc, lines = run_main(bound(own_receipts))
                self.assertEqual((rc, lines), (1, ["host card_dispatched=no relay_receipt_consumed=yes",
                                                   "FAIL card-not-dispatched", TRAILER]))

    def test_c2_2_receipt_unwired(self):
        # A callable is not evidence: one that reads another outbox row or another store must not be consumed.
        with tempfile.TemporaryDirectory() as other:
            os.chmod(other, 0o700)
            elsewhere = tool.relay.RelayStore(Path(other))
            self.addCleanup(elsewhere.db.close)
            for label, binder in (("wrong id", lambda w: setattr(w.conv.npp, "receipt_for", lambda row: w.sender.receipt_for(row + 1))),
                                  ("other store", lambda w: setattr(w.conv.npp, "receipt_for", elsewhere.receipt_for))):
                with self.subTest(label):
                    rc, lines = run_main(bound(binder))
                    self.assertEqual((rc, lines), (1, ["host card_dispatched=yes relay_receipt_consumed=no",
                                                       "FAIL receipt-unwired", TRAILER]))

    def test_c2_3_check_error(self):
        # Setup failures, premature delivery, a raised check or a network/process attempt print only the fixed finding.
        confirmed = {"state": "confirmed", "png_sha256": tool.hashlib.sha256(tool.PNG).hexdigest(),
                     "provider_guid": tool.GUID, "confirmed_at": tool.FIXED.isoformat()}

        def raising(worker):
            def refuse(row):
                raise TypeError("synthetic private text")
            worker.conv.npp.receipt_for = refuse

        def calls(function):
            return lambda worker: (own_receipts(worker), function())

        cases = {
            "missing jobs": (None, mock.patch.object(tool.npp, "assets", side_effect=ValueError("synthetic private text"))),
            "premature delivery": (bound(lambda w: setattr(w.conv.npp, "receipt_for", lambda row: confirmed)), None),
            "raised check": (bound(raising), None),
            "process attempt": (bound(calls(lambda: tool.host.subprocess.run(["true"]))), None),
            "network attempt": (bound(calls(lambda: tool.host.socket.create_connection(("127.0.0.1", 9)))), None),
        }
        for label, (worker_class, patcher) in cases.items():
            with self.subTest(label), contextlib.ExitStack() as stack:
                if patcher is not None:
                    stack.enter_context(patcher)
                rc, lines = run_main(worker_class)
                self.assertEqual((rc, lines), (1, ["FAIL check-error", TRAILER]))

    def test_c3_usage_exit_2(self):
        # argparse's own refusal: nothing on stdout, exit 2, for a positional or an unknown flag.
        for args in (("extra",), ("--unknown",)):
            with self.subTest(args=args):
                result = run_script(*args)
                self.assertEqual((result.returncode, result.stdout), (2, ""))
                self.assertIn("usage:", result.stderr)

    def test_c4_read_only(self):
        # A run that leaves a card, database or bytecode under hass/ or the storefront changes this snapshot.
        before = snapshot()
        result = run_script()
        self.assertIn(result.returncode, (0, 1), result.stderr)
        self.assertEqual(snapshot(), before)

    def test_c5_output_shape(self):
        # Only the three named line forms on stdout, and nothing at all on stderr.
        result = run_script()
        self.assertEqual(result.stderr, "")
        self.assertTrue(result.stdout.endswith("\n"))
        for line in result.stdout.splitlines():
            self.assertTrue(any(form.fullmatch(line) for form in LINE_FORMS), line)

    def test_c6_fixture(self):
        # The measurement reads the real Worker: binding None fails both; a wrong-id callable still dispatches but
        # never consumes, so the receipt check is independent of the dispatch check.
        def measured(binder):
            with mock.patch.object(host, "Worker", bound(binder)):
                return tool.measure()

        self.assertEqual(measured(own_receipts), (True, True))
        self.assertEqual(measured(lambda w: setattr(w.conv.npp, "receipt_for", None)), (False, False))
        self.assertEqual(measured(lambda w: setattr(w.conv.npp, "receipt_for", lambda row: w.sender.receipt_for(row + 1))),
                         (True, False))

    def test_c7_live_pins(self):
        # Measured at b9bfaf6e and again on the current base: the host did not bind the callback (baseline red). If the
        # host is fixed the unpatched run turns healthy; the red fixture below must keep reporting the baseline either way.
        result = run_script()
        self.assertEqual(result.stderr, "")
        lines = result.stdout.splitlines()
        self.assertIn((result.returncode, lines), ((1, BASELINE), (0, HEALTHY)))
        rc, red = run_main(bound(lambda w: setattr(w.conv.npp, "receipt_for", None)))
        self.assertEqual((rc, red), (1, BASELINE))

    def test_s1_imports(self):
        # S1: stdlib plus the named hass modules only; no network or process module is imported by the script.
        tree = ast.parse(SCRIPT.read_text())
        names = set()
        for node in ast.walk(tree):
            if isinstance(node, ast.Import):
                names.update(alias.name for alias in node.names)
            elif isinstance(node, ast.ImportFrom):
                names.add(node.module)
        self.assertFalse(names & {"socket", "urllib.request", "http.client", "requests", "subprocess"})
        self.assertTrue({n for n in names if n.split(".")[0] == "hass"} <= {"hass", "hass.npp"})


if __name__ == "__main__":
    unittest.main()
