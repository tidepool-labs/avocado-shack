#!/usr/bin/env python3
"""Check S4's base-town reasons on offline maker-page fixtures."""

import argparse
import json
from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
from hass.npp import assets, research


OWN = (
    "Miners Orchards picks apples in October.",
    "Miners Orchards ships in California.",
    "Miners Orchards won a blue ribbon in Sacramento.",
    "Miners Orchards sells at markets in San Luis Obispo.",
    "Miners Orchards grows apples in Arroyo Grande.",
    "Miners Orchards is based in Arroyo Grande, California.",
)
OTHER = (
    "Miners Orchards is based in Paso Robles.",
    "Miners Orchards grows apples in Paso Robles.",
)


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__, add_help=False)
    parser.parse_args(argv)

    try:
        _, files, _ = assets()
        markers = research._markers(json.loads(files["hass-maker-research/facts.schema.json"]))
    except Exception:
        print("FAIL check-error")
        print("FAIL npp_base_town_sentences")
        return 1

    failed = False
    for label, sentences, expected, finding in (
        ("own", OWN, "official", "town-refused"),
        ("other", OTHER, "different-base-town", "other-town-accepted"),
    ):
        for index, sentence in enumerate(sentences):
            try:
                page = research.Page(
                    "https://miners.example/", "2026-11-21",
                    titles=["Miners Orchards"], ownership=["© 2024 Miners Orchards."],
                    blocks=[sentence, "We farm in Arroyo Grande."],
                )
                reason = research._own_site(page, "Miners Orchards", "Arroyo Grande", markers)
            except Exception:
                print("FAIL check-error")
                failed = True
                continue
            print(f"{label} {index} reason={reason}")
            if reason != expected:
                print(f"FAIL {finding} {index}")
                failed = True

    print(f"{'FAIL' if failed else 'PASS'} npp_base_town_sentences")
    return int(failed)


if __name__ == "__main__":
    raise SystemExit(main())
