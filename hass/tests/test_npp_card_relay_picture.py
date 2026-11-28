"""Fixture-only tests for scripts/hass/npp_card_relay_picture.py.

Each test names the contract item it pins (C1..C7 of the card) and the believable
bug that would make it fail. Every relay fixture is built by the script itself in a
TemporaryDirectory; nothing here touches real state, the network or a process
other than the script under test.
"""

import contextlib
import importlib.util
import io
import os
from pathlib import Path
import re
import subprocess
import sys
import unittest
from unittest import mock

ROOT = Path(__file__).resolve().parents[2]
SCRIPT = ROOT / "scripts/hass/npp_card_relay_picture.py"
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from hass import relay  # noqa: E402

TRAILER_FAIL = "FAIL npp_card_relay_picture"
TRAILER_PASS = "PASS npp_card_relay_picture"
MEDIA_NO = "relay media_card pictured=no confirmed=no"
MEDIA_YES = "relay media_card pictured=yes confirmed=yes"
SHOTS_YES = "relay screenshots_card pictured=yes confirmed=yes"
CHECK_ERROR = ["FAIL check-error", TRAILER_FAIL]


def load_script():
    spec = importlib.util.spec_from_file_location("npp_card_relay_picture_under_test", SCRIPT)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def run_main(module, argv=()):
    out, err = io.StringIO(), io.StringIO()
    with contextlib.redirect_stdout(out), contextlib.redirect_stderr(err):
        code = module.main(list(argv))
    return code, out.getvalue().splitlines(), err.getvalue()


def run_subprocess(*args, cwd=None):
    return subprocess.run([sys.executable, "-B", str(SCRIPT), *args], cwd=cwd or ROOT,
                          capture_output=True, text=True, timeout=60)


def tree_snapshot():
    snapshot = {}
    for top in ("hass", "storefront-mockup"):
        for directory, _names, files in os.walk(ROOT / top):
            for name in (".", *files):
                path = Path(directory) / name
                info = path.stat()
                snapshot[str(path.relative_to(ROOT))] = (info.st_size, info.st_mtime_ns)
    return snapshot


def media_checked_against_its_own_folder():
    """relay.read_shot, but the one frozen card in the media store is read against its own parent."""
    original, calls = relay.read_shot, []

    def read(path, base):
        p = Path(path)
        if p.name.startswith("card-") and p.parent.parent.name == "npp":
            calls.append(("media", Path(base)))
            return original(path, p.parent)
        calls.append(("other", Path(base)))
        return original(path, base)

    return read, calls


class NppCardRelayPictureTests(unittest.TestCase):
    def setUp(self):
        self.module = load_script()

    def patched_pass_run(self):
        read, calls = media_checked_against_its_own_folder()
        with mock.patch.object(relay, "read_shot", read):
            return run_main(self.module), calls

    def with_measure(self, media, shots):
        return mock.patch.object(self.module, "measure",
                                 lambda: {"media": media, "screenshots": shots})

    # C1: a relay that can read the card passes. Bug: PASS hardcoded, or a pass that
    # skips the pull/ACK lifecycle so nothing was really confirmed.
    def test_c1_full_pass(self):
        (code, lines, err), _calls = self.patched_pass_run()
        self.assertEqual((code, err), (0, ""))
        self.assertEqual(lines, [MEDIA_YES, SHOTS_YES, TRAILER_PASS])

    # C2: every finding run ends in the FAIL trailer with exit 1, findings in check order.
    # Bug: findings printed without the trailer, or exit 0 after a FAIL line.
    def test_c2_findings_trailer(self):
        with self.with_measure((False, False), (True, True)):
            code, lines, err = run_main(self.module)
        self.assertEqual((code, err), (1, ""))
        self.assertEqual(lines, [MEDIA_NO, SHOTS_YES, "FAIL card-picture-dropped",
                                 "FAIL card-unconfirmed", TRAILER_FAIL])

    # C2.1: picture missing but receipt confirmed names only the dropped picture.
    # Bug: both findings are printed for any media problem.
    def test_c2_1_card_picture_dropped(self):
        with self.with_measure((False, True), (True, True)):
            code, lines, _err = run_main(self.module)
        self.assertEqual(code, 1)
        self.assertEqual(lines[2:], ["FAIL card-picture-dropped", TRAILER_FAIL])

    # C2.2: pictured but unconfirmed names only the unconfirmed receipt.
    def test_c2_2_card_unconfirmed(self):
        with self.with_measure((True, False), (True, True)):
            code, lines, _err = run_main(self.module)
        self.assertEqual(code, 1)
        self.assertEqual(lines[2:], ["FAIL card-unconfirmed", TRAILER_FAIL])

    # C2.3: a control that is not pictured and confirmed fails closed, whichever half broke,
    # and its media findings are not reported as evidence. Bug: a broken control still passes.
    def test_c2_3_reference_broken(self):
        for shots in ((False, True), (True, False), (False, False)):
            with self.subTest(shots=shots), self.with_measure((False, False), shots):
                code, lines, _err = run_main(self.module)
                self.assertEqual(code, 1)
                self.assertEqual(lines[2:], ["FAIL reference-broken", TRAILER_FAIL])

    # C2.4: a probe that cannot complete prints only check-error. Bug: a traceback, a
    # silent skip, or a pass when the pull was omitted, the id reused or the I/O failed.
    def test_c2_4_check_error(self):
        original_pull = relay.RelayStore.pull

        def pull_without_cards(store, n, now, *, card_receipts=False):
            return original_pull(store, n, now)  # default pull omits card rows

        def wrong_identity(store, n, now, *, card_receipts=False):
            return [{"id": 999, "card": True}]

        cases = {
            "pull omitted": mock.patch.object(relay.RelayStore, "pull", pull_without_cards),
            "wrong pull identity": mock.patch.object(relay.RelayStore, "pull", wrong_identity),
            "id 7 reused": mock.patch.object(self.module, "SCREENSHOTS_OUTBOX_ID", 7),
            "setup I/O error": mock.patch.object(self.module.receipt.Artifacts, "write_card",
                                                 side_effect=OSError("disk")),
            "measure raises": mock.patch.object(self.module, "measure", side_effect=ValueError("x")),
        }
        for name, patcher in cases.items():
            with self.subTest(name), patcher:
                code, lines, err = run_main(self.module)
                self.assertEqual((code, lines, err), (1, CHECK_ERROR, ""))

    # C3: any argument is an argparse usage error. Bug: ignoring arguments (or --help on stdout).
    def test_c3_usage_exit_2(self):
        for args in (("extra",), ("--unknown",), ("--help",)):
            with self.subTest(args=args):
                result = run_subprocess(*args)
                self.assertEqual((result.returncode, result.stdout), (2, ""))
                self.assertIn("usage:", result.stderr)

    # C4: no file under hass/ or storefront-mockup/ is created or changed (incl. no .pyc).
    def test_c4_read_only(self):
        before = tree_snapshot()
        result = run_subprocess()
        self.assertEqual(result.returncode, 1, result.stderr)
        self.assertEqual(result.stdout.splitlines()[-1], TRAILER_FAIL)
        self.assertEqual(tree_snapshot(), before)

    # C5: only the named line forms on stdout, nothing on stderr, and no fixture path leaks.
    def test_c5_output_shape(self):
        allowed = re.compile(r"relay (media|screenshots)_card pictured=(yes|no) confirmed=(yes|no)"
                             r"|FAIL (card-picture-dropped|card-unconfirmed|reference-broken|check-error)"
                             r"|(PASS|FAIL) npp_card_relay_picture")
        result = run_subprocess(cwd=tree_root_elsewhere())
        self.assertEqual(result.stderr, "")
        for line in result.stdout.splitlines():
            self.assertRegex(line, allowed)
            self.assertNotIn("/", line)
        (code, lines, err), _calls = self.patched_pass_run()
        self.assertEqual(err, "")
        for line in lines:
            self.assertRegex(line, allowed)

    # C6: with the one media read allowed against its own folder, the same lifecycle passes,
    # so the failure is the base folder alone. Bug: the control or ACK path is what broke.
    def test_c6_fixture(self):
        (code, lines, err), calls = self.patched_pass_run()
        self.assertEqual((code, err, lines[-1]), (0, "", TRAILER_PASS))
        self.assertEqual([kind for kind, _base in calls], ["media", "other"])
        self.assertEqual(calls[1][1].name, "screenshots")  # every other read keeps the original base

    # C7: unpatched, today's relay drops the media card's picture and the receipt is failed.
    # Bug: the probe hardcodes a result, or a pull/ACK change turns the gap into a pass.
    # Also: omitting the pull or reusing id 7 must fail as a control, never pass as reference.
    def test_c7_live_pins(self):
        result = run_subprocess()
        self.assertEqual(result.returncode, 1, result.stderr)
        self.assertEqual(result.stderr, "")
        self.assertEqual(result.stdout.splitlines(), [
            MEDIA_NO, SHOTS_YES, "FAIL card-picture-dropped", "FAIL card-unconfirmed", TRAILER_FAIL])
        original_pull = relay.RelayStore.pull
        with mock.patch.object(relay.RelayStore, "pull",
                               lambda s, n, now, *, card_receipts=False: original_pull(s, n, now)):
            self.assertEqual(run_main(self.module)[1], CHECK_ERROR)
        with mock.patch.object(self.module, "SCREENSHOTS_OUTBOX_ID", 7):
            self.assertEqual(run_main(self.module)[1], CHECK_ERROR)


def tree_root_elsewhere():
    return Path(SCRIPT.anchor)  # not the repo: the script must find the repo root itself


if __name__ == "__main__":
    unittest.main()
