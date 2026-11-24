#!/usr/bin/env python3
"""Project the editor's three NPP switches for the flat preflight input."""

import argparse
from contextlib import contextmanager
import json
import os
from pathlib import Path
import stat
import sys


SWITCHES = ("npp", "houseRender", "photo_polish")


class ProjectionError(ValueError):
    """A validation error safe to report without exposing config data."""


def unique_object(pairs):
    result = {}
    for key, value in pairs:
        if key in result:
            raise ProjectionError("config contains a duplicate JSON key")
        result[key] = value
    return result


def reject_constant(_token):
    raise ProjectionError("config contains a non-JSON number")


@contextmanager
def open_directory(directory):
    dir_flags = os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW
    directory_fd = os.open(directory.anchor or ".", dir_flags)
    try:
        parts = directory.parts[1:] if directory.anchor else directory.parts
        # Open every component relative to its pinned parent, without following links.
        for part in parts:
            next_fd = os.open(part, dir_flags, dir_fd=directory_fd)
            os.close(directory_fd)
            directory_fd = next_fd
        yield directory_fd
    finally:
        os.close(directory_fd)


def project(config):
    try:
        with open_directory(config.parent) as parent_fd:
            # A FIFO without a writer must not block before the descriptor check.
            flags = os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK
            fd = os.open(config.name, flags, dir_fd=parent_fd)
            try:
                if not stat.S_ISREG(os.fstat(fd).st_mode):
                    raise ProjectionError("config must be a regular file")
                with os.fdopen(fd, encoding="utf-8", closefd=False) as source:
                    document = json.load(source, object_pairs_hook=unique_object,
                                         parse_constant=reject_constant)
            finally:
                os.close(fd)
    except ProjectionError:
        raise
    except (ValueError, RecursionError):
        raise ProjectionError("config must be valid UTF-8 JSON") from None
    except OSError:
        raise ProjectionError("could not read config") from None

    settings = document.get("settings") if isinstance(document, dict) else None
    if not isinstance(settings, dict):
        raise ProjectionError("config must contain a settings object")
    projection = {}
    for key in SWITCHES:
        if key in settings:
            if type(settings[key]) is not bool:
                raise ProjectionError(f"settings.{key} must be a JSON boolean")
            projection[key] = settings[key]
    return projection


def write_new_private(path, payload):
    parent, name = os.path.split(path)
    if not name:
        raise ProjectionError("output path must name a new file")
    with open_directory(Path(parent)) as parent_fd:
        fd = os.open(name, os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW,
                     0o600, dir_fd=parent_fd)
        with os.fdopen(fd, "w", encoding="utf-8") as output:
            os.fchmod(output.fileno(), 0o600)  # Exact even with a restrictive umask.
            output.write(payload)


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--config", required=True, type=Path, help="editor config JSON (read only)")
    destination = parser.add_mutually_exclusive_group(required=True)
    destination.add_argument("--out", help="new private JSON file (mode 0600)")
    destination.add_argument("--stdout", action="store_true", help="print only the switch projection")
    args = parser.parse_args(argv)
    try:
        payload = json.dumps(project(args.config)) + "\n"
        if args.stdout:
            sys.stdout.write(payload)
            sys.stdout.flush()
        else:
            write_new_private(args.out, payload)
    except ProjectionError as error:
        print(f"error: {error}", file=sys.stderr)
        return 1
    except (OSError, ValueError):
        print("error: could not write projection (output file must be new and symlink-free)",
              file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
