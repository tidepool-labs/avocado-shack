#!/usr/bin/env python3
"""Compare the stage and research allowlist selectors without requesting pages."""

import argparse
import json
from pathlib import Path
import sys
from types import SimpleNamespace
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from hass import claims, maker_site, npp
from hass.npp import missing, research, research_hermes, stages


TOOL = "npp_allowlist_rule_parity"
SOURCES = research.ASSETS + "sources.json"
MAKER = "Etto Farm"
TOWN = "Arroyo Grande"


def _entry(maker="etto farm", domain="farm.example", added_by="G", reviewed_in="fixture-review"):
    return dict(maker=maker, domain=domain, added_by=added_by, reviewed_in=reviewed_in)


# Keep indices stable: each index is the public finding ID for that fixture.
CASES = (
    [_entry()],
    [_entry(added_by="other")],
    [_entry(reviewed_in="")],
    [_entry(), _entry(domain="second-farm.example")],
    [_entry(maker="Etto Farm")],
    [_entry(maker="other farm")],
    [],
    [_entry(maker="café farm")],
)


def _stage_url(pinned, entries):
    port = object.__new__(stages.ProductionStages)
    port.sources = {"allowlist": entries}
    port.pinned = pinned
    port._remaining = lambda work: 500
    with patch.object(research_hermes, "run", return_value=SimpleNamespace(story_facts=())) as run:
        port._research(object(), missing.Maker("new", MAKER), TOWN, "", {})
    return run.call_args.kwargs["owner_url"] if run.called else None


def _research_url(pinned, sources, entries):
    pins, files, replies = pinned
    fixture = json.dumps({**sources, "allowlist": entries}).encode("utf-8")
    fetched = []

    def fetch(url, _seconds):
        fetched.append(url)
        raise maker_site.PageError("unreadable")

    def unexpected_model_call(*_):
        raise AssertionError("no page should reach a model port")

    research.research(
        (pins, {**files, SOURCES: fixture}, replies),
        search=lambda *_: (), fetch=fetch, extract=unexpected_model_call,
        verify=unexpected_model_call, known=False, owner_maker=MAKER,
        owner_town=TOWN, clock=lambda: 0.0,
    )
    return fetched[0] if fetched else None


def main(argv=None):
    argparse.ArgumentParser(prog=TOOL, description=__doc__, add_help=False).parse_args(argv)
    findings = []
    disagree = 0
    try:
        pinned = npp.assets()
        sources = json.loads(pinned[1][SOURCES])
        live = sources["allowlist"]
        if not isinstance(live, list):
            raise ValueError("allowlist is not a list")
        print(f"allowlist live_entries={len(live)}")
    except Exception:
        findings.append("check-error")
    else:
        try:
            makers = [entry["maker"] for entry in live]
            if any(maker != claims.fold(maker) for maker in makers):
                findings.append("live-entry-unfolded")
        except Exception:
            findings.append("check-error")

        # Do not call the address checker or any real page/model port. URL
        # admission is outside this comparison; both selectors share this stub.
        with patch.object(maker_site, "check_address", new=lambda url: url):
            for index, entries in enumerate(CASES):
                try:
                    stage_url = _stage_url(pinned, entries)
                    research_url = _research_url(pinned, sources, entries)
                except Exception:
                    if "check-error" not in findings:
                        findings.append("check-error")
                    continue
                if stage_url != research_url:
                    disagree += 1
                    findings.append(f"rule-disagree {index}")

    for finding in findings:
        print(f"FAIL {finding}")
    print(f"allowlist cases={len(CASES)} disagree={disagree}")
    print(f"{'FAIL' if findings else 'PASS'} {TOOL}")
    return int(bool(findings))


if __name__ == "__main__":
    sys.exit(main())
