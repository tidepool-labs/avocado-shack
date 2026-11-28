#!/usr/bin/env python3
"""Evaluate saved NPP preflight stdout and its separately recorded exit status.

Pass --default-off-confirmed only after the attended check of the reviewed
loader. This tool does not authenticate receipts, read settings, or authorize
installation. Use `before` first; `after` rechecks the supplied before capture.
"""

import argparse
import json
from pathlib import Path

if __package__:
    from .npp_preflight import SKILLS, STAGES
else:
    from npp_preflight import SKILLS, STAGES


SWITCHES = ("npp", "houseRender", "photo_polish")
READINESS = ("status", "present", "missing", "pins", "allowlist_count", "skills", "acceptance_fail_0")
PASS = "PASS"


def _unique_object(pairs):
    obj = {}
    for key, value in pairs:
        if key in obj:
            raise ValueError
        obj[key] = value
    return obj


def _reject_constant(_):
    raise ValueError


def _complete(group, roster):
    if not isinstance(group, dict) or group.get("missing") != []:
        return False
    present = group.get("present")
    if not isinstance(present, list) or not all(isinstance(path, str) for path in present):
        return False
    paths = set(present)
    return len(paths) == len(present) and paths == set(roster)


def _ready_report(stdout, exit_status):
    if type(exit_status) is not int or exit_status != 0:
        return None, "FAIL: preflight exit status"
    try:
        report = json.loads(stdout.partition(b"\n")[0].decode("utf-8"),
                            object_pairs_hook=_unique_object, parse_constant=_reject_constant)
    except (ValueError, RecursionError):
        return None, "FAIL: invalid first JSON line"
    if not isinstance(report, dict):
        return None, "FAIL: invalid first JSON line"
    if report.get("status") != "READY":
        return None, "FAIL: preflight not READY"
    if not _complete(report, STAGES):
        return None, "FAIL: incomplete stages"
    if not _complete(report.get("skills"), SKILLS):
        return None, "FAIL: incomplete skills"
    pins = report.get("pins")
    if (not isinstance(pins, dict) or pins.get("manifest_present") is not True
            or pins.get("mismatches") != [] or type(pins.get("checked")) is not int
            or pins["checked"] <= 0):
        return None, "FAIL: pins not verified"
    count = report.get("allowlist_count")
    if type(count) is not int or count < 0:
        return None, "FAIL: invalid allowlist count"
    if report.get("acceptance_fail_0") is not True:
        return None, "FAIL: acceptance not confirmed"
    switches = report.get("switches")
    current = switches.get("current") if isinstance(switches, dict) else None
    if not isinstance(current, dict) or any(
        key in current and type(current[key]) is not bool for key in SWITCHES
    ):
        return None, "FAIL: invalid current switches"
    return report, PASS


def _before_report(stdout, exit_status, default_off_confirmed):
    report, verdict = _ready_report(stdout, exit_status)
    if report is None:
        return None, verdict
    if report["switches"]["current"].get("npp") is True:
        return None, "FAIL: NPP already on"
    if default_off_confirmed is not True:
        return None, "FAIL: default-off not confirmed"
    return report, PASS


def before_verdict(stdout: bytes, exit_status: object, *, default_off_confirmed: object = False) -> str:
    """Return one fixed verdict for the before-switch capture."""
    return _before_report(stdout, exit_status, default_off_confirmed)[1]


def after_verdict(stdout: bytes, exit_status: object, *, before_stdout: bytes,
                  before_exit_status: object, default_off_confirmed: object = False) -> str:
    """Require a passing before capture and unchanged readiness after switching."""
    before, _ = _before_report(before_stdout, before_exit_status, default_off_confirmed)
    if before is None:
        return "FAIL: before report did not pass"
    after, verdict = _ready_report(stdout, exit_status)
    if after is None:
        return verdict
    switches = after["switches"]
    if any(switches["current"].get(key) is not True for key in SWITCHES):
        return "FAIL: current switches not all on"
    if switches.get("diff") != []:
        return "FAIL: switch diff not empty"
    if any(before[key] != after[key] for key in READINESS):
        return "FAIL: readiness changed"
    return PASS


class _Parser(argparse.ArgumentParser):
    def error(self, message):
        self.exit(2, "FAIL: invalid arguments\n")


def _first_line(path):
    with path.open("rb") as stream:
        return stream.readline()


def main(argv=None):
    parser = _Parser(description=__doc__, allow_abbrev=False)
    phases = parser.add_subparsers(dest="phase", required=True)
    before = phases.add_parser("before", allow_abbrev=False)
    after = phases.add_parser("after", allow_abbrev=False)
    for phase in (before, after):
        phase.add_argument("--stdout", type=Path, required=True, help="saved preflight stdout")
        phase.add_argument("--exit-status", type=int, required=True, help="recorded preflight exit status")
        phase.add_argument("--default-off-confirmed", action="store_true",
                           help="attest the independently verified before-switch loader default")
    after.add_argument("--before-stdout", type=Path, required=True)
    after.add_argument("--before-exit-status", type=int, required=True)
    args = parser.parse_args(argv)
    evidence = {"default_off_confirmed": args.default_off_confirmed}
    try:
        stdout = _first_line(args.stdout)
        if args.phase == "before":
            verdict = before_verdict(stdout, args.exit_status, **evidence)
        else:
            verdict = after_verdict(stdout, args.exit_status, before_stdout=_first_line(args.before_stdout),
                                    before_exit_status=args.before_exit_status, **evidence)
    except (OSError, ValueError):
        verdict = "FAIL: could not read saved stdout"
    print(verdict)
    return 0 if verdict == PASS else 1


if __name__ == "__main__":
    raise SystemExit(main())
