#!/usr/bin/env python3
"""Check Hass listing-code lengths against the NPP artifact store offline."""

import argparse
import ast
from pathlib import Path
import sys
from tempfile import TemporaryDirectory

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))
from hass.npp import receipt  # noqa: E402

SOURCE = ROOT / "hass/conversation.py"
NAME = "npp_job_code_artifact_shape"
CODE = "abcdef012345"
# A 1x1 grayscale PNG (black pixel, no metadata).
PNG = bytes.fromhex(
    "89504e470d0a1a0a0000000d49484452000000010000000108000000003a7e9b55"
    "0000000a49444154789c636000000002000148afa4710000000049454e44ae426082"
)


def code_sizes(tree):
    classes = [node for node in tree.body
               if isinstance(node, ast.ClassDef) and node.name == "Conversation"]
    if len(classes) != 1:
        return ()
    methods = [node for node in classes[0].body
               if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)) and node.name == "_code"]
    if len(methods) != 1:
        return ()
    nodes = list(ast.walk(methods[0]))
    calls = [node for node in nodes if isinstance(node, ast.Call)
             and isinstance(node.func, ast.Name) and node.func.id == "range"]
    if len(calls) != 1:
        return ()
    call = calls[0]
    if (not any(isinstance(node, ast.For) and node.iter is call for node in nodes)
            or call.keywords or len(call.args) != 3):
        return ()
    try:
        bounds = [ast.literal_eval(arg) for arg in call.args]
        if any(type(bound) is not int for bound in bounds):
            return ()
        sizes = range(*bounds)
        # Don't let an empty range pass, or let an oversized slice test a shorter code.
        if 1 <= min(sizes[0], sizes[-1]) and max(sizes[0], sizes[-1]) <= len(CODE):
            return tuple(sizes)
    except (ValueError, IndexError, RecursionError):
        pass
    return ()


def check_size(artifacts, size):
    code = CODE[:size]
    card = saved_receipt = "ok"
    try:
        try:
            path, _ = artifacts.write_card(code, PNG)
            receipt.read_artifact(path)
        except ValueError:
            card = "refused"
        try:
            artifacts.write_receipt(code, {"job_id": code})
            receipt.read_artifact(artifacts.folder(code) / "receipt.json")
        except ValueError:
            saved_receipt = "refused"
        print(f"code size={size} card={card} receipt={saved_receipt}")
    finally:
        # Preserve a known refusal if the other check is interrupted by an error.
        if "refused" in (card, saved_receipt):
            print(f"FAIL code-refused {size}")
    return "refused" in (card, saved_receipt)


def fail(reason):
    print(f"FAIL {reason}")
    print(f"FAIL {NAME}")
    return 1


def main(argv=None):
    # Even --help is an argument; this audit accepts none.
    argparse.ArgumentParser(description=__doc__, add_help=False).parse_args(argv)
    try:
        tree = ast.parse(SOURCE.read_text(encoding="utf-8"))
    except (OSError, UnicodeError, SyntaxError, RecursionError):
        return fail("parse-error")
    sizes = code_sizes(tree)
    if not sizes:
        return fail("sizes-not-found")

    print("codes sizes=" + ",".join(map(str, sizes)))
    refused = False
    try:
        with TemporaryDirectory() as tmp:
            artifacts = receipt.Artifacts(tmp)
            for size in sizes:
                if check_size(artifacts, size):
                    refused = True
    except Exception:  # Never expose exception text or a local path.
        return fail("check-error")
    print(f"{'FAIL' if refused else 'PASS'} {NAME}")
    return int(refused)


if __name__ == "__main__":
    sys.exit(main())
