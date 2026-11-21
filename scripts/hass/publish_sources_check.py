#!/usr/bin/env python3
"""List missing or symlinked static publish sources without publishing."""

import argparse
from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from hass import content_model, sitegen


class ArgumentParser(argparse.ArgumentParser):
    def error(self, message):
        # Argparse's detailed errors can echo a private path from the command line.
        self.print_usage(sys.stderr)
        self.exit(2, f"{self.prog}: error: invalid arguments\n")


def fail(reason):
    print(f"FAIL {reason}")
    print("FAIL publish_sources_check")
    return 1


def expected_paths(content):
    images = {product["image"] for product in content.active_products()}
    home = content.store.get("homeImage")
    if home:
        images.add(home["image"])
    return sorted(
        {f"storefront-mockup/{name}" for name in (*sitegen.PUBLISH_STATIC, *sitegen.PUBLISH_ASSETS, *images)}
        | {f"hass/templates/{name}" for name in sitegen.PUBLISH_PAGES}
    )


def unlisted_top_level(site):
    excluded = {
        *sitegen.PUBLISH_STATIC, *sitegen.PUBLISH_GENERATED, *sitegen.PUBLISH_PAGES,
        "community.json", "producers.json",
    }
    if site.is_symlink() or not site.is_dir():
        return 0
    return sum(p.name not in excluded and not p.is_symlink() and p.is_file() for p in site.iterdir())


def main(argv=None):
    parser = ArgumentParser(prog="publish_sources_check.py", description=__doc__, allow_abbrev=False)
    parser.add_argument("--repo", required=True, help="checkout copy to check")
    args = parser.parse_args(argv)
    repo = Path(args.repo)
    if not args.repo or repo.is_symlink() or not repo.is_dir():
        return fail("unsafe-input")

    try:
        content = content_model.load_and_validate(repo / "hass/content", None)
    except (content_model.ContentError, UnicodeDecodeError, OSError):
        return fail("content-invalid")

    expected = expected_paths(content)
    missing, symlinks = [], []
    for rel in expected:
        if sitegen._linked(repo, rel):
            symlinks.append(rel)
        elif not (repo / rel).is_file():
            missing.append(rel)

    print(f"expected {len(expected)}")
    for rel in missing:
        print(f"missing {rel}")
    for rel in symlinks:
        print(f"symlink {rel}")
    print(f"note unlisted-top-level {unlisted_top_level(repo / 'storefront-mockup')}")
    if missing:
        print(f"FAIL source-missing {len(missing)}")
    if symlinks:
        print(f"FAIL source-symlink {len(symlinks)}")
    if missing or symlinks:
        print("FAIL publish_sources_check")
        return 1
    print("PASS publish_sources_check")
    return 0


if __name__ == "__main__":
    sys.exit(main())
