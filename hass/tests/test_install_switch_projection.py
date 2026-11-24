"""Fixture-only CLI tests for the private preflight projection."""

import json
import os
from pathlib import Path
import stat
import subprocess
import sys
import tempfile
import unittest


SCRIPT = Path(__file__).resolve().parents[2] / "scripts/hass/install_switch_projection.py"
SECRET = "synthetic-private-marker"


class InstallSwitchProjectionTests(unittest.TestCase):
    def setUp(self):
        temporary = tempfile.TemporaryDirectory()
        self.addCleanup(temporary.cleanup)
        # Use the physical temp root so a runner's TMPDIR alias isn't a symlink test.
        self.root = Path(temporary.name).resolve()
        self.config = self.root / "source.json"
        self.out = self.root / "projection.json"

    def invoke(self, raw, *options, umask=-1):
        self.config.write_bytes(raw)
        result = self.run_projection(self.config, *options, umask=umask)
        self.assertEqual(self.config.read_bytes(), raw)
        return result

    def run_projection(self, config, *options, umask=-1):
        result = subprocess.run(
            [sys.executable, "-B", str(SCRIPT), "--config", str(config), *options],
            cwd=self.root, capture_output=True, text=True, timeout=10, umask=umask,
        )
        self.assertNotIn(SECRET, result.stdout + result.stderr)
        return result

    def assert_refused(self, result, reason):
        self.assertEqual(result.returncode, 1, result.stderr)
        self.assertEqual(result.stdout, "")
        self.assertIn(reason, result.stderr)
        self.assertNotIn("Traceback", result.stderr)

    def test_stdout_uses_only_nested_switches_and_preserves_absence(self):
        # A flat lookup, defaults, or printing all settings would break this.
        for settings, expected in (
            ({"npp": True, "houseRender": False, "ignored": SECRET},
             {"npp": True, "houseRender": False}),
            ({}, {}),
        ):
            with self.subTest(settings=settings):
                raw = json.dumps({"settings": settings, "npp": False,
                                  "photo_polish": True, "private": SECRET}).encode()
                result = self.invoke(raw, "--stdout")
                self.assertEqual(result.returncode, 0, result.stderr)
                self.assertEqual(result.stderr, "")
                projection = json.loads(result.stdout)
                self.assertEqual(projection.keys(), expected.keys())
                for key, value in expected.items():
                    self.assertIs(projection[key], value)
                self.assertEqual(set(self.root.iterdir()), {self.config})

    def test_reads_only_the_selected_regular_config(self):
        # A plain path open could report staged bytes as disk readback, or hang
        # on a FIFO before checking that the opened object is a regular file.
        expected = dict.fromkeys(("npp", "houseRender", "photo_polish"), True)
        raw = json.dumps({"settings": {**expected, "ignored": SECRET}}).encode()
        self.config.write_bytes(raw)
        staged = self.root / "staged" / "nested"
        staged.mkdir(parents=True)
        staged_config = staged / self.config.name
        staged_config.write_bytes(raw)

        regular = self.run_projection(staged_config.relative_to(self.root), "--stdout")
        self.assertEqual((regular.returncode, regular.stderr), (0, ""))
        self.assertEqual(json.loads(regular.stdout), expected)
        selected = self.run_projection(self.config.name, "--stdout")
        self.assertEqual((selected.returncode, selected.stdout, selected.stderr),
                         (0, regular.stdout, ""))

        leaf = self.root / "leaf.json"
        leaf.symlink_to(staged_config)
        parent = self.root / "alias"
        parent.symlink_to(staged.parent, target_is_directory=True)
        fifo = self.root / "fifo"
        os.mkfifo(fifo)
        for label, config, reason in (
            ("leaf-link", leaf, "could not read config"),
            ("parent-link", parent / "nested" / self.config.name, "could not read config"),
            ("fifo", fifo, "config must be a regular file"),
        ):
            with self.subTest(input=label, output="stdout"):
                self.assert_refused(self.run_projection(config, "--stdout"), reason)
            with self.subTest(input=label, output="file"):
                destination = self.root / f"{label}.projection.json"
                self.assert_refused(self.run_projection(config, "--out", destination), reason)
                self.assertFalse(destination.exists())
        self.assertEqual(self.config.read_bytes(), raw)
        self.assertEqual(staged_config.read_bytes(), raw)

    def test_writes_only_a_new_mode_0600_file(self):
        # An ordinary text open can use a permissive umask and overwrite on retry.
        raw = b'{"settings":{"photo_polish":false,"houseRender":true,"npp":false}}'
        for umask in (0o000, 0o777):
            with self.subTest(umask=oct(umask)):
                destination = self.out.name if umask == 0o000 else str(self.out)
                result = self.invoke(raw, "--out", destination, umask=umask)
                self.assertEqual((result.returncode, result.stdout, result.stderr), (0, "", ""))
                saved = self.out.read_bytes()
                self.assertEqual(json.loads(saved),
                                 {"photo_polish": False, "houseRender": True, "npp": False})
                self.assertEqual(stat.S_IMODE(self.out.stat().st_mode), 0o600)
                self.assert_refused(self.invoke(b'{"settings":{}}', "--out", str(self.out)),
                                    "could not write projection")
                self.assertEqual(self.out.read_bytes(), saved)
                self.out.unlink()
        self.assert_refused(self.invoke(raw, "--out", str(self.config)), "could not write projection")

    def test_refuses_symlink_output_and_symlink_parent(self):
        # Following an existing leaf could alter its target; a dangling leaf or
        # a symlinked ancestor could write to an unintended directory entry.
        raw = b'{"settings":{"npp":true}}'
        target = self.root / "target.json"
        target.write_text(SECRET, encoding="utf-8")
        self.out.symlink_to(target)
        self.assert_refused(self.invoke(raw, "--out", str(self.out)), "could not write projection")
        self.assertTrue(self.out.is_symlink())
        self.assertEqual(target.read_text(encoding="utf-8"), SECRET)
        target.unlink()
        self.assert_refused(self.invoke(raw, "--out", str(self.out)), "could not write projection")
        self.assertTrue(self.out.is_symlink())
        self.assertFalse(target.exists())

        actual = self.root / "actual"
        actual.mkdir()
        (actual / "nested").mkdir()
        alias = self.root / "alias"
        alias.symlink_to(actual, target_is_directory=True)
        self.assert_refused(self.invoke(raw, "--out", str(alias / "nested" / "projection.json")),
                            "could not write projection")
        self.assertEqual(list((actual / "nested").iterdir()), [])

    def test_refuses_duplicate_keys_without_echoing_names_or_values(self):
        # Default json.load silently picks the last value, including escaped aliases.
        cases = (
            rb'{"settings":{"npp":true},"s\u0065ttings":{}}',
            rb'{"settings":{"npp":false,"\u006epp":true}}',
            b'{"settings":{},"synthetic-private-marker":1,"synthetic-private-marker":2}',
            b'{"settings":{"other":[{"x":1,"x":2}]}}',
        )
        for raw in cases:
            with self.subTest(raw=raw):
                self.assert_refused(self.invoke(raw, "--out", str(self.out)), "duplicate JSON key")
                self.assertFalse(self.out.exists())

    def test_refuses_missing_or_non_object_settings(self):
        # A fallback to {} would wrongly report malformed settings as all absent.
        documents = [[], None, {}, {"npp": True}]
        documents.extend({"settings": value} for value in (None, [], 0, False, SECRET))
        for document in documents:
            with self.subTest(document=document):
                self.assert_refused(self.invoke(json.dumps(document).encode(), "--stdout"),
                                    "settings object")

    def test_refuses_every_non_boolean_switch_type(self):
        # Truthiness and int/bool equality must not let malformed values through.
        for key in ("npp", "houseRender", "photo_polish"):
            for value in (0, 1, 1.0, None, [True], {}, "true", SECRET):
                with self.subTest(key=key, value=value):
                    raw = json.dumps({"settings": {key: value}}).encode()
                    self.assert_refused(self.invoke(raw, "--stdout"), f"settings.{key}")

    def test_refuses_invalid_json_and_utf8_without_echoing_source(self):
        # Raw parser exceptions or permissive non-JSON numbers must not escape.
        for raw, reason in (
            (b'{"settings":{},"synthetic-private-marker":}', "valid UTF-8 JSON"),
            (b'{"settings":{}} synthetic-private-marker', "valid UTF-8 JSON"),
            (b'{"settings":{},"other":"synthetic-private-marker\xff"}', "valid UTF-8 JSON"),
            *((b'{"settings":{},"other":' + value + b'}', "non-JSON number")
              for value in (b"NaN", b"Infinity", b"-Infinity")),
        ):
            with self.subTest(raw=raw):
                self.assert_refused(self.invoke(raw, "--out", str(self.out)), reason)
                self.assertFalse(self.out.exists())


if __name__ == "__main__":
    unittest.main()
