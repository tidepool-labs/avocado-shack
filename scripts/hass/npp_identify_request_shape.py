#!/usr/bin/env python3
"""Check the S2 photo request at the transport boundary, without a model call."""

import argparse
import base64
import json
from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
from hass import interpreter_local, label_reader, media, npp
from hass.npp import identify


PHOTOS = (media.KINDS["png"] + b"fixture-one",
          media.KINDS["jpeg"] + b"fixture-two",
          media.KINDS["png"] + b"fixture-three")
USER_TEXT = "Inspect the attached photos."
PHOTO_GUIDANCE = "\nThe first photo is the main view; any others show label details of the same product."


def _unused_runner(*args, **kwargs):
    raise AssertionError("the offline check must not run a model")


def _request_checks(body, name, prompt):
    """Return image count and separate image and prompt verdicts."""
    messages = json.loads(body).get("messages")
    if not isinstance(messages, list):
        messages = []
    system = messages[0] if messages else None
    user = messages[1] if len(messages) > 1 and isinstance(messages[1], dict) else {}
    # Still check the photo payload when only the message order is wrong.
    if user.get("role") != "user":
        user = next((message for message in messages
                     if isinstance(message, dict) and message.get("role") == "user"), user)
    prompt_ok = len(messages) == 2 and system == {
        "role": "system", "content": prompt + PHOTO_GUIDANCE,
    }
    encoded = [base64.b64encode(photo).decode("ascii") for photo in PHOTOS]
    if name == "local":
        images = user.get("images")
        user_ok = {key: value for key, value in user.items() if key != "images"} == {
            "role": "user", "content": USER_TEXT,
        }
        expected = encoded
    else:
        parts = user.get("content")
        if not isinstance(parts, list):
            parts = []
        text = {"type": "text", "text": USER_TEXT}
        images = [part for part in parts if not isinstance(part, dict) or part.get("type") != "text"]
        user_ok = user == {"role": "user", "content": [text, *images]}
        expected = [
            {"type": "image_url", "image_url": {
                "url": f"data:{interpreter_local.image_type(photo)};base64,{data}",
            }}
            for photo, data in zip(PHOTOS, encoded)
        ]
    return len(images) if isinstance(images, list) else 0, images == expected, prompt_ok and user_ok


def _check_reader(name, url, api, ident, pinned_prompt_ok):
    bodies = []
    images = 0

    def transport(url, body, headers, timeout):
        bodies.append(body)
        return 500, b""

    try:
        reader = label_reader.LabelReader(url, "m-1", timeout=5, api=api, transport=transport)
        failure = None
        try:
            identify._read_batch(reader, PHOTOS, ident.prompt, ident.schema)
        except interpreter_local._Failed as exc:
            failure = exc.args
        if len(bodies) != 1:
            return [f"no-request {name}"]
        images, photos_ok, prompt_ok = _request_checks(bodies[0], name, ident.prompt)
        if failure != ("http-500",):
            return ["check-error"]
        findings = []
        if not photos_ok:
            findings.append(f"photo-order {name}")
        if not (prompt_ok and pinned_prompt_ok):
            findings.append(f"prompt-shape {name}")
        return findings
    except Exception:
        return ["check-error"]
    finally:
        print(f"reader {name} requests={len(bodies)} images={images}")


def main(argv=None):
    # This command has no options, including --help.
    argparse.ArgumentParser(description=__doc__, add_help=False).parse_args(argv)
    try:
        pinned = npp.assets()
        ident = identify.Identifier(pinned, None, runner=_unused_runner)
        files = pinned[1]
        schema = json.loads(files[identify.ASSET + "identify.schema.json"])
        examples = json.loads(files[identify.ASSET + "examples.json"])["examples"]
        pinned_prompt_ok = (ident.schema == schema and json.dumps(ident.schema) in ident.prompt
                            and json.dumps([row["output"] for row in examples]) in ident.prompt)
    except Exception:
        findings = {"check-error"}
        print("FAIL check-error")
    else:
        findings = set()
        for name, url, api in (("cloud", None, "codex"), ("local", "http://127.0.0.1:9", "ollama")):
            for reason in _check_reader(name, url, api, ident, pinned_prompt_ok):
                if reason not in findings:
                    print(f"FAIL {reason}")
                    findings.add(reason)
    print(f"{'FAIL' if findings else 'PASS'} npp_identify_request_shape")
    return 1 if findings else 0


if __name__ == "__main__":
    raise SystemExit(main())
