"""Offline CLI contract for the NPP routing drift guard."""

from contextlib import redirect_stderr, redirect_stdout
import importlib.util
import io
from pathlib import Path
import subprocess
import sys
from tempfile import TemporaryDirectory
import unittest
from unittest.mock import patch

from hass.npp import job
from hass.skills import openreq

ROOT = Path(__file__).resolve().parents[2]
SCRIPT = ROOT / "scripts/hass/npp_input_request_routing.py"
PASS = "PASS npp_input_request_routing"
FAIL = "FAIL npp_input_request_routing"
LIVE = [
    "case 0 npp-expired jobs=a1b2:expired turn=answer outbox=1 duplicate=answered",
    "case 1 npp-working jobs=a1b2:expired,3668:working turn=start outbox=0 duplicate=answered",
    "case 2 None jobs=- turn=- outbox=0 duplicate=-",
    "case 3 None jobs=- turn=- outbox=0 duplicate=-",
    "case 4 npp-working jobs=293f:working turn=start outbox=0 duplicate=-",
    "case 5 npp-working jobs=a1b2:working turn=edit outbox=0 duplicate=answered",
    "case 6 npp-working jobs=a1b2:working turn=answer outbox=0 duplicate=answered",
    "case 7 npp-working jobs=a1b2:editing turn=photo outbox=0 duplicate=expired",
]


def load_script():
    spec = importlib.util.spec_from_file_location(SCRIPT.stem, SCRIPT)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    with patch.object(sys, "path", sys.path[:]):
        spec.loader.exec_module(module)
    return module


def hide_unrelated():
    original = openreq.OpenRequests.get

    def get(store, owner, now):
        request = original(store, owner, now)
        return None if request and request["skill"] != "npp" else request

    return patch.object(openreq.OpenRequests, "get", get)


def skip_close():
    return patch.object(job.Jobs, "close", return_value=None)


def snapshot():
    entries = {}
    for tree in (ROOT / "hass", ROOT / "storefront-mockup"):
        for path in (tree, *tree.rglob("*")):
            stat = path.lstat()
            entries[path.relative_to(ROOT)] = stat.st_size, stat.st_mtime_ns
    return entries


class NppInputRequestRoutingTests(unittest.TestCase):
    def cli(self, *args):
        # Run outside the checkout so success requires the script's own import setup.
        with TemporaryDirectory() as cwd:
            return subprocess.run([sys.executable, "-B", str(SCRIPT), *args], cwd=cwd,
                                  capture_output=True, text=True, timeout=15)

    def in_process(self, code, trailer):
        stdout, stderr = io.StringIO(), io.StringIO()
        with redirect_stdout(stdout), redirect_stderr(stderr):
            actual = load_script().main([])
        lines = stdout.getvalue().splitlines()
        self.assertEqual(actual, code, lines)
        self.assertEqual(lines[-1:], [trailer])
        self.assertEqual(stderr.getvalue(), "")
        return lines[:-1]

    def assert_cli_pass(self, result):
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(result.stdout.splitlines()[-1:], [PASS])
        self.assertEqual(result.stderr, "")

    def test_c1_full_pass(self):
        # A broken CLI entrypoint or lost trailer can hide an otherwise successful replay.
        self.assert_cli_pass(self.cli())

    def test_c2_findings_trailer(self):
        # Failing fast after the first mismatch can hide later findings or lose the trailer.
        with skip_close(), hide_unrelated():
            lines = self.in_process(1, FAIL)
        self.assertEqual([line for line in lines if line.startswith("FAIL ")], [
            "FAIL route-changed 0", "FAIL route-changed 1",
            "FAIL replaced-unrelated 3", "FAIL route-changed 3",
        ])

    def test_c2_1_replaced_unrelated(self):
        # Using get() to verify preservation would miss the same row the router missed.
        with hide_unrelated():
            lines = self.in_process(1, FAIL)
        self.assertEqual([line for line in lines if not line.startswith("case ")], [
            "FAIL replaced-unrelated 3", "FAIL route-changed 3",
        ])

    def test_c2_2_route_changed(self):
        # The return token alone stays unchanged even if a listing fails to close.
        with skip_close():
            lines = self.in_process(1, FAIL)
        self.assertEqual([line for line in lines if not line.startswith("case ")], [
            "FAIL route-changed 0", "FAIL route-changed 1",
        ])

    def test_c2_3_check_error(self):
        # A failed real loader is not a pass and must not disclose exception details.
        with patch("hass.npp.assets", side_effect=RuntimeError("fixture error")):
            self.assertEqual(self.in_process(1, FAIL), ["FAIL check-error"])

    def test_c3_usage_exit_2(self):
        # No argument (including argparse's usual help flag) should be consumed silently.
        for arg in ("extra", "--unknown", "--help", "--"):
            with self.subTest(arg=arg):
                result = self.cli(arg)
                self.assertEqual(result.returncode, 2)
                self.assertEqual(result.stdout, "")
                self.assertEqual(result.stderr.splitlines()[-1:], [
                    f"{SCRIPT.name}: error: unrecognized arguments: {arg}",
                ])

    def test_c4_read_only(self):
        # A fixture accidentally rooted at the checkout could leave state or update assets.
        before = snapshot()
        self.assert_cli_pass(self.cli())
        self.assertEqual(snapshot(), before)

    def test_c5_output_shape(self):
        # Debug output or an extra line breaks consumers even if routing still passes.
        result = self.cli()
        self.assert_cli_pass(result)
        self.assertEqual(result.stdout, "\n".join([*LIVE, PASS, ""]))

    def test_c6_fixture(self):
        # Only the two expired routes depend on close(); keep the other six as controls.
        with skip_close():
            lines = self.in_process(1, FAIL)
        self.assertEqual(lines, [
            "case 0 npp-expired jobs=a1b2:editing turn=answer outbox=1 duplicate=answered",
            "FAIL route-changed 0",
            "case 1 npp-working jobs=a1b2:editing,3668:working turn=start outbox=0 duplicate=answered",
            "FAIL route-changed 1",
            *LIVE[2:],
        ])

    def test_c7_live_pins(self):
        # Snapshot independent of EXPECTED; also verify the fake outbox got the expiry reply,
        # since the CLI's informational line deliberately reports only the count.
        original = job.Jobs.input
        replies = []

        def observe(jobs, msg, *args):
            result = original(jobs, msg, *args)
            if msg.provider_id == "p-route-0":
                replies.extend(tuple(row) for row in jobs.db.execute(
                    "SELECT chat,text,attachments,reply_to,ids_ok FROM outbox"))
            return result

        with patch.object(job.Jobs, "input", observe):
            self.assertEqual(self.in_process(0, PASS), LIVE)
        self.assertEqual(replies, [("chat-owner", job.EXPIRED, "[]", "2026-11-21T15:40:00+00:00", 0)])
