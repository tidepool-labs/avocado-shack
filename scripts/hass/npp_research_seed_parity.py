#!/usr/bin/env python3
"""Report where S3 admits fixture maker names that S4 will not research."""

import argparse
from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from hass import label_reader, npp
from hass.npp import missing, research


NAMES = (
    "Etto Farm", "7 Sisters Farm", "Route 1 Farms", "Twenty Acres Farm",
    "Bee+Hive Honey", "Hill/Dale Farm", "St. Clair Farm", "O'Neil Ranch",
    "Café Ñandú", "Farm & Co",
)


def _check_refusal(index, name):
    calls = 0

    def port(*args, **kwargs):
        nonlocal calls
        calls += 1
        raise AssertionError("research port called")

    findings = []
    wrong_outcome = False
    try:
        result = research.research(
            npp.assets(), search=port, fetch=port, extract=port, verify=port,
            owner_maker=name, owner_town="Arroyo Grande",
        )
        wrong_outcome = result.receipt["outcome"] != "no-safe-identity-seed"
    except Exception:
        findings.append("check-error")
    if calls or wrong_outcome:
        findings.append(f"seed-reached-port {index}")
    return findings


def _check_seed(index, name):
    try:
        s3 = (label_reader.identity_text("brand", name) == name
              and missing._maker(name, {}, {}).research_allowed)
        s4 = research._identity_field(name)
    except Exception:
        return ["check-error"]

    print(f"seed {index} s3={'yes' if s3 else 'no'} s4={'yes' if s4 else 'no'}")
    findings = []
    if not s3:
        findings.append(f"s3-refused {index}")
    elif not s4:
        findings.append(f"seed-refused {index}")
    if not s4:
        findings.extend(_check_refusal(index, name))
    return findings


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__, add_help=False)
    argv = sys.argv[1:] if argv is None else argv
    parser.parse_args(argv)
    if argv:  # argparse accepts a bare end-of-options marker; this CLI accepts nothing.
        parser.error("unrecognized arguments: " + " ".join(argv))

    failed = False
    for index, name in enumerate(NAMES):
        for finding in _check_seed(index, name):
            print(f"FAIL {finding}")
            failed = True
    print(f"{'FAIL' if failed else 'PASS'} npp_research_seed_parity")
    return int(failed)


if __name__ == "__main__":
    raise SystemExit(main())
