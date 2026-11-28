#!/usr/bin/env python3
"""Report whether the offline S4 extract request starves a fixture page."""

import argparse
from collections import Counter
import json
from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

import hass.npp
from hass.npp import research_hermes

HOME = "https://miners.example/"
ABOUT = "https://miners.example/about/"
CASES = (
    {HOME: ["h" * 1600, "h" * 10], ABOUT: ["a" * 100]},
    {HOME: ["h" * 1600] * 15, ABOUT: ["a" * 100]},
    {HOME: ["h" * 1601], ABOUT: ["a" * 100]},
    {HOME: ["h" * 1600] * 14 + ["h" * 1599], ABOUT: ["a" * 2]},
)
REQUEST_KEYS = {"model", "effort", "timeout", "images", "instructions", "text"}
DATA_KEYS = {"maker", "pages"}


def _decode(text):
    if not isinstance(text, str):
        return None
    lines = text.split("\n")
    if len(lines) < 3 or lines[0] != "<<<DATA>>>" or lines[-1] != "<<<END DATA>>>":
        return None
    try:
        return json.loads("\n".join(lines[1:-1]))
    except ValueError:
        return None


def _check_case(index, pages):
    requests = []

    def fake(request):
        requests.append(request)
        return {"ok": True, "model": "m", "ms": 1, "text": '{"facts": []}'}

    try:
        model = research_hermes.Models(hass.npp.assets(), runner=fake)
        model.extract("Miners", pages, 60)
    except Exception:
        print("FAIL check-error")
        return False

    if len(requests) != 1 or not isinstance(requests[0], dict):
        print(f"FAIL wrong-request {index}")
        return False
    request = requests[0]
    data = _decode(request.get("text"))
    ok = (
        request.keys() == REQUEST_KEYS and request.get("images") == []
        and isinstance(data, dict) and data.keys() == DATA_KEYS
    )
    if not ok:
        print(f"FAIL wrong-request {index}")

    sent = data.get("pages") if isinstance(data, dict) else None
    if not isinstance(sent, dict) or any(
        not isinstance(blocks, list) or not all(isinstance(block, str) for block in blocks)
        for blocks in sent.values()
    ):
        if ok:
            print("FAIL check-error")
        return False

    for page, (url, blocks) in enumerate(pages.items()):
        # Count whole original blocks, respecting repeated text within a page.
        kept = sum((Counter(blocks) & Counter(sent.get(url, []))).values())
        print(f"case {index} page {page} kept {kept} of {len(blocks)}")
        if not kept and any(len(block) <= 1600 for block in blocks):
            print(f"FAIL page-starved {index} {page}")
            ok = False
    return ok


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__, add_help=False)
    parser.parse_args(argv)
    passed = True
    for index, pages in enumerate(CASES):
        if not _check_case(index, pages):
            passed = False
    print(f"{'PASS' if passed else 'FAIL'} npp_research_extract_budget")
    return 0 if passed else 1


if __name__ == "__main__":
    raise SystemExit(main())
