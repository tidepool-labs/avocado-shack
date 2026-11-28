#!/usr/bin/env python3
"""Check offline that NPP evidence recording and validation agree."""

import argparse
from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
from hass.npp import evidence


CASES = (
    *(("approval", dict(version=1, role="G", approved_at=time,
                        change_id="chg-1", draft_hash="abcdef1"))
      for time in ("2026-11-21T05:10:00Z", "2026-11-21T05:10:00-08:00",
                   "2026-11-21T05:10:00+00:00", "2026-02-30T00:00:00Z", 1.5, True)),
    ("stage", dict(stage="S13", started_ms=0, ended_ms=1, outcome="ok", code=None)),
    ("stage", dict(stage="S14", started_ms=0, ended_ms=1, outcome="ok", code=None)),
    ("stage", dict(stage="S1", started_ms=5, ended_ms=1, outcome="ok", code=None)),
    ("check", dict(name="Bad", verdict="pass", private=None)),
    ("model", dict(step="copy_select", pinned="gpt@x", returned=None)),
    ("publish", dict(change_id="chg-1", commit="abc123", live_verify=None)),
    ("publish", dict(change_id="chg-1", commit=None, live_verify="seen")),
    ("fallback", dict(code="basic")),
)
EXPECTED = ("ok", "ok", "refused", "refused", "ok", "refused", "ok", "refused",
            "refused", "refused", "refused", "refused", "ok", "ok")


def _case_verdicts(method, fields):
    record = getattr(evidence.Evidence(), method)
    try:
        record(**fields)
    except ValueError:
        builder_ok = False
    else:
        builder_ok = True

    # Build the validator input independently, even when recording was refused.
    doc = evidence.Evidence().doc()
    if method in ("approval", "publish"):
        doc[method] = dict(fields)
    elif method == "fallback":
        doc["fallbacks"] = [fields["code"]]
    else:
        row = dict(fields)
        if method == "model":
            row["drift"] = evidence._drift(row["pinned"], row["returned"])
        doc[method + "s"] = [row]
    return builder_ok, evidence.validate(doc) == []


def _built_doc():
    receipt = evidence.Evidence()
    receipt.stage("S1", 0, 5, "ok")
    receipt.model("copy_select", "m1", "m2")
    receipt.check("n", "pass")
    receipt.fallback("basic")
    receipt.approval(1, "Mike", 0, "chg-1", "abcdef1")
    receipt.publish("chg-1", "abcdef1", "seen")
    return receipt.doc()


def main(argv=None):
    argparse.ArgumentParser(description=__doc__, add_help=False).parse_args(argv)
    failed = False

    def fail(reason):
        nonlocal failed
        failed = True
        print(f"FAIL {reason}")

    for i, (method, fields) in enumerate(CASES):
        try:
            builder_ok, validator_ok = _case_verdicts(method, fields)
        except Exception:
            fail("check-error")
            continue
        builder = "ok" if builder_ok else "refused"
        validator = "ok" if validator_ok else "problems"
        print(f"case {i} builder={builder} validate={validator}")
        if builder_ok != validator_ok:
            fail(f"parity {i}")
        if builder != EXPECTED[i]:
            fail(f"verdict-changed {i}")

    try:
        problems = evidence.validate(_built_doc())
    except Exception:
        fail("check-error")
    else:
        if problems != []:
            fail("doc-invalid")

    print(f"{'FAIL' if failed else 'PASS'} npp_evidence_builder_parity")
    return int(failed)


if __name__ == "__main__":
    sys.exit(main())
