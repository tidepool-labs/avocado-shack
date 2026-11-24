"""Offline CLI contract for scripts/hass/npp_preflight.py."""

import hashlib
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
from typing import Any
import unittest

SCRIPT = Path(__file__).resolve().parents[2] / "scripts/hass/npp_preflight.py"
STAGES = [f"hass/npp/{name}.py" for name in (
    "job", "identify", "missing", "research", "copy", "validate", "private_numbers", "picture", "reply", "edits",
    "stages",
)] + ["hass/tests/npp/run_npp.py"]
SKILLS = [f"docs/hass/skills/hass-npp-{name}/SKILL.md" for name in ("maintain", "review")]
ASSETS = "hass/npp/assets"
PIN = "hass/npp/pins.json"
SOURCE = "hass-maker-research/sources.json"
ASSET = "hass-listing-copy/SKILL.md"
OFF = {"npp": False, "houseRender": False, "photo_polish": False}


class PreflightTests(unittest.TestCase):
    def setUp(self):
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        # A TMPDIR alias is not part of the fixture being tested.
        self.root = Path(tmp.name).resolve()
        self.release = self.root / "release"
        self.settings = self.root / "editor-settings.json"
        self.acceptance = self.root / "acceptance.out"
        self.settings.write_text(json.dumps({**OFF, "other": "not-for-the-report"}), encoding="utf-8")
        self.acceptance.write_text("fail 0\n", encoding="utf-8")
        for name in STAGES + SKILLS:
            self.put(name, b"fixture\n")
        self.pinned = {ASSET: b"fixture copy instructions\n", SOURCE: b'{"allowlist": []}\n'}
        self.pin_assets()

    def put(self, name, content):
        path = self.release / name
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(content)
        return path

    def pin_assets(self):
        pins = {}
        for name, content in self.pinned.items():
            self.put(f"{ASSETS}/{name}", content)
            pins[name] = hashlib.sha256(content).hexdigest()
        self.put(PIN, json.dumps({"schema": 1, "assets": pins}).encode())

    def preflight(self, code, *, settings=None, check_acceptance=True, release=None) -> Any:
        paths = [self.settings, *[path for path in self.release.rglob("*")
                                 if not path.is_symlink() and path.is_file()]]
        if check_acceptance:
            paths.append(self.acceptance)
        before = {path: (path.read_bytes(), path.stat().st_mtime_ns) for path in paths}
        entries = set(self.root.rglob("*"))
        args = ["--release", str(release or self.release), "--settings", str(settings or self.settings)]
        if check_acceptance:
            args.extend(["--acceptance-output", str(self.acceptance)])
        proc = subprocess.run([sys.executable, "-B", str(SCRIPT), *args], cwd=self.root,
                              capture_output=True, text=True, timeout=10)
        self.assertEqual(set(self.root.rglob("*")), entries)
        self.assertEqual({path: (path.read_bytes(), path.stat().st_mtime_ns) for path in before}, before)
        self.assertEqual(proc.returncode, code, proc.stdout + proc.stderr)
        self.assertNotIn("not-for-the-report", proc.stdout + proc.stderr)
        if code == 2:
            self.assertFalse(proc.stdout)
            return proc.stderr
        self.assertFalse(proc.stderr)
        first, *lines = proc.stdout.splitlines()
        result = json.loads(first)
        self.assertEqual(result["status"], "READY" if code == 0 else "NOT-READY")
        self.assertEqual([line for line in lines if line.startswith(("- ", "+ "))], result["switches"]["diff"])
        return result

    def test_npp_preflight(self):
        # Catches wrong switch names, unrelated edits, and a checker that never reaches READY.
        result = self.preflight(0)
        self.assertEqual(result["present"], STAGES)
        self.assertEqual(result["missing"], [])
        self.assertEqual(result["pins"], {"manifest_present": True, "checked": 2, "mismatches": []})
        self.assertEqual(result["allowlist_count"], 0)
        self.assertEqual(result["skills"], {"present": SKILLS, "missing": []})
        self.assertIs(result["acceptance_fail_0"], True)
        self.assertEqual(result["switches"], {"current": OFF, "proposed": dict.fromkeys(OFF, True), "diff": [
            '- "npp": false', '+ "npp": true', '- "houseRender": false', '+ "houseRender": true',
            '- "photo_polish": false', '+ "photo_polish": true',
        ]})

    def test_missing_stage_and_fleet_skill_block_independently(self):
        # Neither a partially merged release nor an unrelated skill may satisfy readiness.
        # All constituent modules can be present while the driver that composes them is missing.
        for missing in (STAGES[2], "hass/npp/stages.py", SKILLS[1]):
            with self.subTest(missing=missing):
                (self.release / missing).unlink()
                result = self.preflight(3)
                group = result if missing in STAGES else result["skills"]
                self.assertEqual(group["missing"], [missing])
                self.put(missing, b"fixture\n")
                self.preflight(0)

    def test_changed_and_deleted_assets_are_named(self):
        # A file's existence, length or extension doesn't establish its pinned bytes.
        path = self.put(f"{ASSETS}/{ASSET}", b"Fixture copy instructions\n")
        for reason in ("sha256", "missing"):
            with self.subTest(reason=reason):
                self.assertEqual(self.preflight(3)["pins"]["mismatches"], [{"asset": ASSET, "reason": reason}])
                if reason == "sha256":
                    path.unlink()

    def test_allowlist_count_and_absent_or_already_enabled_switches(self):
        # Counting the policy object's keys or reporting an already-on switch as changed is wrong.
        self.pinned[SOURCE] = b'{"schema": 1, "allowlist": [{"domain": "example.test"}]}\n'
        self.pin_assets()
        self.settings.write_text('{"houseRender": true, "photo_polish": false}', encoding="utf-8")
        result = self.preflight(0, check_acceptance=False)
        self.assertEqual(result["allowlist_count"], 1)
        self.assertIsNone(result["acceptance_fail_0"])
        self.assertEqual(result["switches"]["current"], {"houseRender": True, "photo_polish": False})
        self.assertEqual(result["switches"]["diff"], [
            '+ "npp": true', '- "photo_polish": false', '+ "photo_polish": true',
        ])

    def test_acceptance_requires_a_zero_failure_summary(self):
        # A substring in a diagnostic, a per-ID row or a true/false value is not a passing total.
        for output, code in (
            ('{"id":"H01","result":"pass"}\n{"summary":{"ids":1,"pass":1,"fail":0,"not covered":0}}\n', 0),
            ('fail 1\n', 3),
            ('note: previous run fail 0\n{"summary":{"fail":1}}\n', 3),
            ('{"summary":{"fail":false}}\n', 3),
            ('{"result":"pass"}\n', 3),
        ):
            with self.subTest(output=output):
                self.acceptance.write_text(output, encoding="utf-8")
                self.assertIs(self.preflight(code)["acceptance_fail_0"], code == 0)

    def test_unsafe_input_types_are_refused(self):
        # A leaf symlink, a symlinked ancestor and a FIFO must not be followed or read.
        link = self.root / "settings-link.json"
        link.symlink_to(self.settings)
        self.assertIn(link.name, self.preflight(2, settings=link))
        alias = self.root / "release-link"
        alias.symlink_to(self.release, target_is_directory=True)
        self.preflight(2, release=alias)
        settings_parent_alias = self.root / "ancestor"
        settings_parent_alias.symlink_to(self.root, target_is_directory=True)
        self.preflight(2, settings=settings_parent_alias / self.settings.name)
        fifo = self.root / "pipe.json"
        os.mkfifo(fifo)
        self.assertIn(fifo.name, self.preflight(2, settings=fifo))
        path = self.release / ASSETS / ASSET
        path.unlink()
        path.symlink_to(self.settings)
        self.assertIn(ASSET, self.preflight(2))

    def test_missing_manifest_and_missing_allowlist_block_independently(self):
        # A pre-NPP tree must get a missing report, not silently pass or fail as malformed input.
        (self.release / PIN).unlink()
        self.assertFalse(self.preflight(3)["pins"]["manifest_present"])
        del self.pinned[SOURCE]
        self.pin_assets()
        (self.release / ASSETS / SOURCE).unlink()
        self.assertIsNone(self.preflight(3)["allowlist_count"])

    def test_bad_json_or_pin_path_is_input_error(self):
        # Don't interpret malformed settings or permit a manifest to request outside files.
        self.settings.write_text('{"npp": false, "npp": true}', encoding="utf-8")
        self.assertIn("duplicate JSON key", self.preflight(2))
        self.settings.write_text(json.dumps(OFF), encoding="utf-8")
        self.put(PIN, json.dumps({"assets": {"../pins.json": "0" * 64}}).encode())
        self.assertIn("unsafe asset path", self.preflight(2))


if __name__ == "__main__":
    unittest.main()
