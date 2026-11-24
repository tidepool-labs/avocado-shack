#!/usr/bin/env python3
"""Read-only Hass NPP install preflight. READY is not install authority.

Run with python3 -B. Standard output starts with one JSON object on a single
line, followed by human-readable checks and a switch-only diff (not a patch
for the entire settings file). The optional saved acceptance run is not
re-executed or authenticated by this tool.
"""

import argparse
from contextlib import contextmanager
import hashlib
import json
import os
from pathlib import Path
import re
import stat
import sys
from typing import BinaryIO, Callable, TypeVar, overload

STAGES = (
    "hass/npp/job.py",
    "hass/npp/identify.py",
    "hass/npp/missing.py",
    "hass/npp/research.py",
    "hass/npp/copy.py",
    "hass/npp/validate.py",
    "hass/npp/private_numbers.py",
    "hass/npp/picture.py",
    "hass/npp/reply.py",
    "hass/npp/edits.py",
    "hass/npp/stages.py",
    "hass/tests/npp/run_npp.py",
)
SKILLS = (
    "docs/hass/skills/hass-npp-maintain/SKILL.md",
    "docs/hass/skills/hass-npp-review/SKILL.md",
)
PINS = "hass/npp/pins.json"
ASSETS = "hass/npp/assets"
SOURCES = f"{ASSETS}/hass-maker-research/sources.json"
SWITCHES = ("npp", "houseRender", "photo_polish")
DIR_FLAGS = os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW
FILE_FLAGS = os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK
T = TypeVar("T")


@contextmanager
def directory(parts, root=None):
    """Anchor each descent at an open directory; never resolve symlinks."""
    if root is None:
        fd = os.open(parts[0], DIR_FLAGS)
        parts = parts[1:]
    else:
        fd = os.dup(root)
    try:
        for name in parts:
            child = os.open(name, DIR_FLAGS, dir_fd=fd)
            os.close(fd)
            fd = child
        yield fd
    finally:
        os.close(fd)


def require_regular(parent, name):
    if not stat.S_ISREG(os.stat(name, dir_fd=parent, follow_symlinks=False).st_mode):
        raise ValueError("expected a regular file, not a symlink or special file")


@overload
def inspect_file(path: str | Path, root: int | None = None, *, read: Callable[[BinaryIO], T]) -> T | None: ...


@overload
def inspect_file(path: str | Path, root: int | None = None, *, read: None = None) -> bool | None: ...


def inspect_file(path, root=None, *, read=None):
    path = Path(path) if root is not None else Path.cwd() / path
    try:
        with directory(path.parent.parts, root) as parent:
            require_regular(parent, path.name)
            if read is None:
                return True
            # NOFOLLOW and fstat also guard a leaf replaced after the stat;
            # NONBLOCK prevents a swapped FIFO from hanging the preflight.
            with os.fdopen(os.open(path.name, FILE_FLAGS, dir_fd=parent), "rb") as stream:
                if not stat.S_ISREG(os.fstat(stream.fileno()).st_mode):
                    raise ValueError("expected a regular file")
                return read(stream)
    except FileNotFoundError:
        if root is not None:
            return None  # Absent release members are NOT-READY, not bad CLI inputs.
        raise ValueError(f"{str(path)!r}: file not found") from None
    except (OSError, ValueError) as exc:
        raise ValueError(f"{str(path)!r}: {exc}") from None


def unique_keys(pairs):
    result = {}
    for key, value in pairs:
        if key in result:
            raise ValueError("duplicate JSON key")
        result[key] = value
    return result


def read_object(stream):
    try:
        obj = json.load(stream, object_pairs_hook=unique_keys)
    except (json.JSONDecodeError, UnicodeError, RecursionError):
        raise ValueError("expected a valid JSON object") from None
    if not isinstance(obj, dict):
        raise ValueError("expected a JSON object")
    return obj


def sha256(stream):
    digest = hashlib.sha256()
    for chunk in iter(lambda: stream.read(65536), b""):
        digest.update(chunk)
    return digest.hexdigest()


def pin_check(root):
    manifest = inspect_file(PINS, root, read=read_object)
    if manifest is None:
        return {"manifest_present": False, "checked": 0, "mismatches": []}
    assets = manifest.get("assets")
    if not isinstance(assets, dict) or not assets:
        raise ValueError(f"{PINS}: expected a nonempty assets map")
    mismatches = []
    for name, expected in sorted(assets.items()):
        if (any(part in ("", ".", "..") for part in name.split("/"))
                or "\x00" in name or "\\" in name):
            raise ValueError(f"{PINS}: unsafe asset path {name!r}")
        if not isinstance(expected, str) or not re.fullmatch(r"[0-9a-fA-F]{64}", expected):
            raise ValueError(f"{PINS}: invalid SHA-256 for {name!r}")
        actual = inspect_file(f"{ASSETS}/{name}", root, read=sha256)
        if actual != expected.lower():
            mismatches.append({"asset": name, "reason": "missing" if actual is None else "sha256"})
    return {"manifest_present": True, "checked": len(assets), "mismatches": mismatches}


def switch_check(settings):
    current = {key: settings[key] for key in SWITCHES if key in settings}
    if any(type(value) is not bool for value in current.values()):
        raise ValueError("settings: npp, houseRender and photo_polish must be JSON booleans when set")
    proposed = dict.fromkeys(SWITCHES, True)
    diff = []
    for key in SWITCHES:
        if current.get(key) is not True:
            if key in current:
                diff.append(f'- "{key}": false')
            diff.append(f'+ "{key}": true')
    return {"current": current, "proposed": proposed, "diff": diff}


def acceptance_check(stream):
    """Use the final summary, not an incidental 'fail 0' in diagnostics."""
    summary_line = ""
    for line in stream:
        if line.strip():
            summary_line = line.decode("utf-8").strip()
    if summary_line == "fail 0":
        return True
    try:
        obj = json.loads(summary_line, object_pairs_hook=unique_keys)
    except (ValueError, RecursionError):
        return False
    summary = obj.get("summary") if isinstance(obj, dict) else None
    fail = summary.get("fail") if isinstance(summary, dict) else None
    return type(fail) is int and fail == 0


def check(release, settings, acceptance_output):
    switches = switch_check(inspect_file(settings, read=read_object))
    with directory((Path.cwd() / release).parts) as root:
        missing = [path for path in STAGES if inspect_file(path, root) is None]
        present = [path for path in STAGES if path not in missing]
        pins = pin_check(root)
        sources = inspect_file(SOURCES, root, read=read_object)
        if sources is not None and not isinstance(sources.get("allowlist"), list):
            raise ValueError(f"{SOURCES}: expected an allowlist array")
        count = None if sources is None else len(sources["allowlist"])
        skills = [path for path in SKILLS if inspect_file(path, root) is not None]
    missing_skills = [path for path in SKILLS if path not in skills]
    acceptance = None if acceptance_output is None else inspect_file(acceptance_output, read=acceptance_check)
    ready = (not missing and pins["manifest_present"] and not pins["mismatches"]
             and count is not None and not missing_skills and acceptance is not False)
    return {"status": "READY" if ready else "NOT-READY", "present": present, "missing": missing,
            "pins": pins, "allowlist_count": count, "switches": switches,
            "skills": {"present": skills, "missing": missing_skills}, "acceptance_fail_0": acceptance}


def print_report(report):
    print(json.dumps(report))
    print(f"Stages: {len(report['present'])}/{len(STAGES)} present; missing: "
          + (", ".join(report["missing"]) or "none"))
    pins = report["pins"]
    mismatches = ", ".join(f"{row['asset']!r} ({row['reason']})" for row in pins["mismatches"])
    print(f"Pins: {pins['checked']} checked; mismatches: {mismatches or 'none'}" if pins["manifest_present"]
          else f"Pins: missing {PINS}")
    count = report["allowlist_count"]
    print(f"Maker allowlist: {count} entries (unchanged)" if count is not None
          else f"Maker allowlist: missing {SOURCES}")
    switches = report["switches"]
    current = ", ".join(f"{key}={json.dumps(switches['current'][key]) if key in switches['current'] else 'absent'}"
                        for key in SWITCHES)
    print(f"Switches: {current}; proposed diff below (not applied)" if switches["diff"]
          else f"Switches: {current}; no changes needed")
    skills = report["skills"]
    print(f"Fleet skills: {len(skills['present'])}/{len(SKILLS)} present; missing: "
          + (", ".join(skills["missing"]) or "none"))
    accepted = report["acceptance_fail_0"]
    print("Acceptance: not supplied" if accepted is None else
          "Acceptance: fail 0 found" if accepted else "Acceptance: fail 0 not found in final summary")
    for line in switches["diff"]:
        print(line)


def main(argv=None):
    parser = argparse.ArgumentParser(description="Read-only Hass NPP install preflight")
    parser.add_argument("--release", type=Path, required=True, help="checkout or release directory")
    parser.add_argument("--settings", type=Path, required=True, help="editor settings JSON (not changed)")
    parser.add_argument("--acceptance-output", type=Path, help="saved hass/acceptance.py stdout")
    args = parser.parse_args(argv)
    try:
        report = check(args.release, args.settings, args.acceptance_output)
    except (OSError, ValueError) as exc:
        parser.exit(2, f"preflight: {exc}\n")
    print_report(report)
    return 0 if report["status"] == "READY" else 3


if __name__ == "__main__":
    sys.exit(main())
