#!/usr/bin/env python3
"""NPP-H: weekly consistency metrics from the private job receipts (design 4e).

    python3 -B scripts/hass/npp_metrics.py --receipts <mediaRoot>/npp --week 2026-W47 [--findings findings.json] [--judge scores.json]
        [--out ~/agent-work/reports/hass-npp/metrics.tsv]

Reads `<job>/receipt.json` files (ids, times and digests only, never owner text) for jobs created in the requested ISO
week and appends one row to the private metrics.tsv. Quantities the receipts do not carry (wording and maker fallbacks,
guard replies, repeat incidents, judge scores) come from the redacted weekly findings file and the judge run, and are left
`n/a` when absent: an absent figure is never reported as zero.
"""
import argparse
import json
import sys
from datetime import datetime
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]
OUT = Path("~/agent-work/reports/hass-npp/metrics.tsv").expanduser()
TARGETS = {"judge_mean": 4.2, "approved_no_edit": 0.70, "picture_fallback": 0.10, "p90_s": 75.0, "repeat_incidents": 0}
COLUMNS = ["week", "jobs", "listings", "first_card_pass_rate", "judge_mean", "judge_min", "approved_no_edit_share",
           "edits_per_listing", "questions_per_listing", "fallback_picture", "fallback_wording", "fallback_maker",
           "time_to_card_p50_s", "time_to_card_p90_s", "guard_replies_per_listing", "repeat_incidents", "pin_drift_jobs",
           "targets_missed"]


def load_receipts(directory):
    found = []
    for path in sorted(Path(directory).glob("*/receipt.json")):
        data = json.loads(path.read_text(encoding="utf-8"))
        if isinstance(data, dict) and "job_id" in data:
            found.append(data)
    return found


def receipt_week(receipt):
    try:
        year, week, _ = datetime.fromisoformat(receipt.get("created_at")).isocalendar()
    except (TypeError, ValueError):
        return None
    return f"{year:04d}-W{week:02d}"


def seconds(row):
    try:
        return (datetime.fromisoformat(row["ended_at"]) - datetime.fromisoformat(row["accepted_at"])).total_seconds()
    except (KeyError, TypeError, ValueError):
        return None


def percentile(values, q):
    if not values:
        return None
    values = sorted(values)
    # nearest rank: a measured value, never an interpolated one
    return values[max(0, min(len(values) - 1, -(-len(values) * q // 100) - 1))]


def ratio(num, den):
    return None if not den else num / den


def compute(receipts, *, pins=None, findings=None, judge=None):
    """One row of figures. `receipts` are parsed receipt.json dicts."""
    findings = findings or {}
    listings = [r for r in receipts if r.get("versions")]
    # segments are listed newest first in the receipt; the first card of a job is the oldest 'card' or failed render
    first = []
    questions = 0
    times = []
    for r in listings:
        segments = sorted(r["segments"], key=lambda s: s.get("accepted_at") or "")
        decided = [s for s in segments if s.get("outcome") in ("card", "render-failed")]
        if decided:
            first.append(decided[0]["outcome"] == "card")
        questions += sum(1 for s in segments if s.get("outcome") == "question")
        times += [t for s in segments if s.get("outcome") == "card" and (t := seconds(s)) is not None]
    approved = [r for r in listings if any(v.get("state") == "approved" for v in r["versions"])]
    no_edit = [r for r in approved if len(r["versions"]) == 1]
    edits = sum(len(r["versions"]) - 1 for r in listings)
    versions = [v for r in listings for v in r["versions"] if v.get("image_variant")]
    drift = sum(1 for r in receipts if pins is not None and r.get("asset_pins") not in (None, pins))
    n = len(listings)
    row = {
        "jobs": len(receipts), "listings": n,
        "first_card_pass_rate": ratio(sum(first), len(first)),
        "judge_mean": (judge or {}).get("mean"), "judge_min": (judge or {}).get("min"),
        "approved_no_edit_share": ratio(len(no_edit), len(approved)),
        "edits_per_listing": ratio(edits, n), "questions_per_listing": ratio(questions, n),
        "fallback_picture": ratio(sum(1 for v in versions if v["image_variant"] == "raw"), len(versions)),
        "fallback_wording": ratio(findings.get("fallback", {}).get("wording"), n) if "wording" in findings.get("fallback", {}) else None,
        "fallback_maker": ratio(findings.get("fallback", {}).get("maker"), n) if "maker" in findings.get("fallback", {}) else None,
        "time_to_card_p50_s": percentile(times, 50), "time_to_card_p90_s": percentile(times, 90),
        "guard_replies_per_listing": ratio(findings["guard_replies"], n) if "guard_replies" in findings else None,
        "repeat_incidents": findings.get("repeat_incidents"), "pin_drift_jobs": drift if pins is not None else None,
    }
    missed = []
    if row["judge_mean"] is not None and row["judge_mean"] < TARGETS["judge_mean"]:
        missed.append("judge_mean")
    if row["approved_no_edit_share"] is not None and row["approved_no_edit_share"] < TARGETS["approved_no_edit"]:
        missed.append("approved_no_edit")
    if row["fallback_picture"] is not None and row["fallback_picture"] > TARGETS["picture_fallback"]:
        missed.append("picture_fallback")
    if row["time_to_card_p90_s"] is not None and row["time_to_card_p90_s"] > TARGETS["p90_s"]:
        missed.append("p90")
    if row["repeat_incidents"]:
        missed.append("repeat_incidents")
    row["targets_missed"] = ",".join(missed) if missed else "none"
    return row


def fmt(value):
    if value is None:
        return "n/a"
    return f"{value:.3f}" if isinstance(value, float) else str(value)


def write_row(path, week, row):
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    new = not path.exists() or not path.read_text(encoding="utf-8").strip()
    with path.open("a", encoding="utf-8") as out:
        if new:
            out.write("\t".join(COLUMNS) + "\n")
        out.write("\t".join(fmt(week if c == "week" else row.get(c)) for c in COLUMNS) + "\n")


def main(argv=None):
    p = argparse.ArgumentParser(description="NPP weekly metrics")
    p.add_argument("--receipts", required=True)
    p.add_argument("--week", required=True)
    p.add_argument("--findings")
    p.add_argument("--judge", help="JSON {mean, min} from the judge run")
    p.add_argument("--out", default=str(OUT))
    args = p.parse_args(sys.argv[1:] if argv is None else argv)
    pins = json.loads((REPO / "hass" / "npp" / "pins.json").read_text(encoding="utf-8"))["assets"]
    findings = json.loads(Path(args.findings).read_text()) if args.findings else None
    judge = json.loads(Path(args.judge).read_text()) if args.judge else None
    receipts = [r for r in load_receipts(args.receipts) if receipt_week(r) == args.week]
    row = compute(receipts, pins=pins, findings=findings, judge=judge)
    write_row(args.out, args.week, row)
    print(json.dumps({"week": args.week, **row}, sort_keys=True))
    return 0


if __name__ == "__main__":
    sys.exit(main())
