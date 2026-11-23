"""Offline host write-mode contracts; no real token files or till calls."""
import contextlib
import io
import json
import os
from types import SimpleNamespace
from unittest import mock

from hass import host
from hass.clover import apply, chat, config, credential, dryrun
from hass.clover.client import CloverClient, CloverWriteClient
from hass.tests import test_clover_client, test_host

MIKE = "mike@example.invalid"
G = "g@example.invalid"
MIKE_CHAT = f"iMessage;-;{MIKE}"
G_CHAT = f"iMessage;-;{G}"


class CloverHostEngineTests(test_clover_client.NoNetwork, test_host.HostCase):
    def setUp(self):
        super().setUp()
        self.read_file = self.hostdir / "fixture-read"
        self.write_file = self.hostdir / "fixture-write"
        self.base = {"environment": "sandbox", "merchantId": test_clover_client.MID, "tokenFile": str(self.read_file)}
        self.gates = {"liveApproved": True, "writes": True, "writeTokenFile": str(self.write_file)}
        self.read_token = credential.Token(test_clover_client.FAKE_TOKEN)
        self.write_token = credential.Token(test_clover_client.FAKE_TOKEN + "-WRITE")
        read_patch = mock.patch.object(credential, "load_token", return_value=self.read_token)
        write_patch = mock.patch.object(credential, "load_write_token", return_value=self.write_token)
        self.read_loader = self.enterContext(read_patch)
        self.write_loader = self.enterContext(write_patch)
        self.enterContext(mock.patch.object(apply, "load_write_token", self.write_loader))

    def build_clover_worker(self, block, *, g_is_owner=False):
        raw = {"ownerSenders": [MIKE.upper()], "ownerChat": MIKE_CHAT, "approvalTtlSeconds": 600,
               "gSenders": [G.upper()], "gChat": G_CHAT, "gIsOwner": g_is_owner}
        with mock.patch.object(host.conversation, "_config_bytes", return_value=json.dumps({"settings": raw}).encode()):
            settings = host.conversation.load_settings(self.repo.state)
        conv = SimpleNamespace(editor=None, settings=settings)
        with mock.patch.object(host, "_worktree", return_value=str(self.hostdir)), \
                mock.patch.object(host.conversation, "Conversation", return_value=conv), \
                mock.patch.object(host.inbox_mod, "Inbox"), mock.patch.object(host.receiver, "Receiver"), \
                mock.patch.object(host, "Worker"):
            host.make_worker(host.load_host(self.host_json(clover=block)), self.store, editor=object(), build=lambda: None)
        return conv

    def check(self, block):
        path = self.host_json(clover=block)
        stdout = io.StringIO()
        with contextlib.redirect_stdout(stdout), mock.patch.object(host, "runtime_problem", return_value=False):
            status = host.main(["check", "--host", str(path)])
        return status, json.loads(stdout.getvalue())

    def test_c1_write_mode_setting(self):
        # C1: a typo, explicit null, or any missing live gate must not enable writes or echo a value.
        self.assertIsNone(config.from_settings(self.base).write_mode)
        self.assertEqual(config.from_settings({**self.base, "writeMode": "dry-run"}).write_mode, "dry-run")
        live = {**self.base, **self.gates, "writeMode": "live"}
        self.assertEqual(config.from_settings(live).write_mode, "live")
        for field in self.gates:
            with self.subTest(missing=field), self.assertRaises(config.ConfigProblem) as error:
                config.from_settings({k: v for k, v in live.items() if k != field})
            self.assertEqual(error.exception.fields, ("writeMode",))
            self.assertEqual(str(error.exception), "writeMode")
        for mode in ("off", "typo-sentinel", None):
            with self.subTest(mode=mode), self.assertRaises(config.ConfigProblem) as error:
                config.from_settings({**live, "writeMode": mode})
            self.assertEqual(error.exception.fields, ("writeMode",))
        self.assertEqual(self.check({**self.base, "writeMode": "live"}),
                         (2, {"result": "config", "fields": ["clover.writeMode"]}))

    def test_c2_engine_by_mode(self):
        # C2: write gates alone must not attach an engine; the wrong factory or unconditional G ownership would leak authority.
        self.assertFalse(hasattr(self.build_clover_worker(None), "till"))
        off = self.build_clover_worker({**self.base, **self.gates}).till
        self.assertIsInstance(off, chat.TillDesk)
        self.assertIsNone(off.engine)
        rehearsal = self.build_clover_worker({**self.base, "writeMode": "dry-run"}).till.engine
        self.assertIsInstance(rehearsal, dryrun.DryRunEngine)
        dry_client = rehearsal.factory()
        self.assertIsInstance(dry_client, dryrun.DryRunWriteClient)
        self.assertIs(type(dry_client._read_client), CloverClient)
        self.assertIs(dry_client._read_client._token, self.read_token)
        self.read_loader.assert_called_once_with(str(self.read_file))
        self.read_loader.reset_mock()
        self.write_loader.assert_not_called()
        for is_owner in (False, True):
            with self.subTest(gIsOwner=is_owner):
                live = self.build_clover_worker({**self.base, **self.gates, "writeMode": "live"}, g_is_owner=is_owner).till.engine
                self.assertIs(type(live), chat.BundleEngine)
                self.assertNotEqual(rehearsal.journal.path, live.journal.path)
                self.assertEqual(live.owners, {(MIKE, MIKE_CHAT)} | ({(G, G_CHAT)} if is_owner else set()))
                self.write_loader.assert_not_called()
                client = live._client()
                self.assertIsInstance(client, CloverWriteClient)
                self.assertIs(client._token, self.write_token)
                self.write_loader.assert_called_once_with(live.config)
                self.write_loader.reset_mock()
        self.read_loader.assert_not_called()

    def test_c3_check_reports_mode(self):
        # C3: emitting an off key breaks legacy check output; opening a token or skipping a live file check is unsafe.
        self.write(self.read_file, b"not a token")
        self.write(self.write_file, b"not a token")

        def guard(original):
            def checked(path, *args, **kwargs):
                if not isinstance(path, int) and os.fsdecode(path) in {str(self.read_file), str(self.write_file)}:
                    self.fail("check opened a token path")
                return original(path, *args, **kwargs)
            return checked

        live = {**self.base, **self.gates, "writeMode": "live"}
        with mock.patch("os.open", side_effect=guard(os.open)), mock.patch("io.open", side_effect=guard(io.open)), \
                mock.patch("builtins.open", side_effect=guard(open)), \
                mock.patch.object(credential, "inspect", wraps=credential.inspect) as inspect:
            for block, clover, mode, files in (
                (None, "not configured", None, []),
                ({**self.base, **self.gates}, "ok", None, [self.read_file]),
                ({**self.base, **self.gates, "writeMode": "dry-run"}, "ok", "dry-run", [self.read_file]),
                (live, "ok", "live", [self.read_file, self.write_file]),
            ):
                with self.subTest(mode=mode, clover=clover):
                    inspect.reset_mock()
                    expected = {"result": "ok", "clover": clover}
                    if mode is not None:
                        expected["writeMode"] = mode
                    self.assertEqual(self.check(block), (0, expected))
                    self.assertEqual(inspect.call_args_list, [mock.call(str(path)) for path in files])
            self.write_file.chmod(0o640)
            self.assertEqual(self.check(live), (2, {"result": "clover", "clover": "mode", "writeMode": "live"}))
            self.read_file.chmod(0o640)
            self.assertEqual(self.check(self.base), (2, {"result": "clover", "clover": "mode"}))
        self.read_loader.assert_not_called()
        self.write_loader.assert_not_called()

    def test_c4_no_token_in_dry_run(self):
        # C4: configured write gates must not cause a write-token read at startup or when rehearsal obtains its client.
        for mode in ({}, {"writeMode": "dry-run"}):
            with self.subTest(mode=mode):
                self.read_loader.reset_mock()
                engine = self.build_clover_worker({**self.base, **self.gates, **mode}).till.engine
                self.read_loader.assert_not_called()
                if mode:
                    self.assertIsInstance(engine._client(), dryrun.DryRunWriteClient)
                    self.read_loader.assert_called_once_with(str(self.read_file))
                else:
                    self.assertIsNone(engine)
                self.write_loader.assert_not_called()
