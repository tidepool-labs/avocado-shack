#!/usr/bin/env python3
"""Rehearse the NPP switch and rollback on a disposable synthetic config."""

import json
import os
from pathlib import Path
import shutil
import stat
import sys
from tempfile import TemporaryDirectory

SWITCHES = ("npp", "houseRender", "photo_polish")
PRIVATE_MODE = 0o600
FIXTURE = b'''{
 "settings": {"npp": false, "houseRender": true, "itemIntake": true},
 "extension": {"keep": ["synthetic-marker", 1]}
}
'''


def write_private(path, payload):
    with path.open("xb") as stream:
        os.fchmod(stream.fileno(), PRIVATE_MODE)
        stream.write(payload)
        stream.flush()
        os.fsync(stream.fileno())


def replace(config, stage_name, payload):
    stage = config.with_name(stage_name)
    write_private(stage, payload)
    stage.replace(config)
    fd = os.open(config.parent, os.O_RDONLY | os.O_DIRECTORY)
    try:
        os.fsync(fd)
    finally:
        os.close(fd)


def _restore_if_current(config, candidate, backup):
    # Only a byte check in a private fixture, not synchronization with writers.
    if config.read_bytes() != candidate:
        return False
    replace(config, ".rollback.tmp", backup.read_bytes())
    return True


def private(path):
    return stat.S_IMODE(path.stat().st_mode) == PRIVATE_MODE


def unique_object(pairs):
    obj = dict(pairs)
    if len(obj) != len(pairs):
        raise ValueError
    return obj


def fail(step, reason):
    print(f"FAIL {step}: {reason}")
    return 1


def main(argv=None):
    args = sys.argv[1:] if argv is None else argv
    if args:
        return fail("arguments", "this rehearsal takes no arguments")

    step = "backup"
    try:
        with TemporaryDirectory(prefix="npp-rehearsal-") as directory:
            root = Path(directory)
            config = root / "config.json"
            backup = root / "config.before"
            write_private(config, FIXTURE)
            shutil.copyfile(config, backup)
            backup.chmod(PRIVATE_MODE)
            original = backup.read_bytes()
            if original != FIXTURE or config.read_bytes() != original:
                return fail(step, "backup bytes do not match the fixture")
            if not (private(backup) and private(config)):
                return fail(step, "config and backup must both have mode 0600")
            print("PASS backup")

            step = "edit"
            expected = json.loads(original)
            expected["settings"].update(dict.fromkeys(SWITCHES, True))
            expected_json = json.dumps(expected, sort_keys=True)
            candidate = expected_json.encode() + b"\n"
            replace(config, ".switch.tmp", candidate)
            if config.read_bytes() == original:
                return fail(step, "replace did not change the config")
            print("PASS edit")

            step = "readback"
            try:
                actual = json.loads(config.read_text(encoding="utf-8"), object_pairs_hook=unique_object)
                # Compare JSON, not Python equality (where true == 1, for example).
                actual = json.dumps(actual, sort_keys=True, allow_nan=False)
            except (ValueError, RecursionError):
                return fail(step, "config is not valid unambiguous JSON")
            if actual != expected_json:
                return fail(step, "switches or unrelated values do not match")
            if not private(config):
                return fail(step, "config does not have mode 0600")
            print("PASS readback")

            step = "rollback"
            if not _restore_if_current(config, candidate, backup):
                return fail(step, "config drifted; restore refused")
            if config.read_bytes() != original:
                return fail(step, "restored bytes do not match the original")
            if not private(config):
                return fail(step, "config does not have mode 0600")

            # A separate trial changes only the unrelated extension marker.
            drifted = candidate.replace(b'"synthetic-marker"', b'"synthetic-change"')
            if drifted == candidate or len(drifted) != len(candidate):
                return fail(step, "invalid drift fixture")
            drift_config = root / "config.drifted"
            write_private(drift_config, drifted)
            if _restore_if_current(drift_config, candidate, backup) or drift_config.read_bytes() != drifted:
                return fail(step, "drift fixture was not refused and preserved")
            step = "cleanup"
    except OSError:
        # Do not echo exception text: it may contain paths or fixture contents.
        return fail(step, "filesystem operation failed")
    print("PASS rollback")
    return 0


if __name__ == "__main__":
    sys.exit(main())
