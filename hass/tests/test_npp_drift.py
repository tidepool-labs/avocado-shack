"""Offline contract tests for the NPP model-drift report CLI (HRM-29)."""

import hashlib
import json
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest

from hass.npp.evidence import Evidence


SCRIPT = Path(__file__).resolve().parents[2] / "scripts/hass/npp_drift.py"
STEPS = dict(identify=dict(model="model-a"), copy_select=dict(model="model-a"),
             picture=dict(model="vendor:image-b"), judge=dict(effort="medium"))
PINS = dict(schema=1, steps=STEPS)


def snapshot(root):
    """Map every file under root to its bytes digest, to prove the run wrote nothing."""
    return {str(p.relative_to(root)): hashlib.sha256(p.read_bytes()).hexdigest()
            for p in sorted(root.rglob("*")) if p.is_file()}


class NppDriftTests(unittest.TestCase):
    def setUp(self):
        self.root = Path(self.enterContext(tempfile.TemporaryDirectory()))
        self.receipts = self.root / "npp"
        self.receipts.mkdir()
        self.repo = self.root / "checkout"
        self.pins()

    def pins(self, pins=PINS):
        path = self.repo / "hass/npp/pins.json"
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(pins), encoding="utf-8")

    def receipt(self, job, models=(), day="2031-02-03", doc=None, **override):
        built = Evidence()
        for step, pinned, returned in models:
            built.model(step, pinned, returned)
        row = dict(job_id=job, state="card_out", created_at=f"{day}T08:45:00+00:00", segments=[], versions=[],
                   evidence=built.doc() if doc is None else doc) | override
        path = self.receipts / job / "receipt.json"
        path.parent.mkdir(exist_ok=True)
        path.write_text(json.dumps(row), encoding="utf-8")

    def run_cli(self, *extra):
        before = snapshot(self.root)
        result = subprocess.run(
            [sys.executable, "-B", str(SCRIPT), "--receipts", str(self.receipts), "--repo", str(self.repo), *extra],
            capture_output=True, text=True, check=False, timeout=15, cwd=self.root)
        self.assertEqual(result.stderr, "")
        self.assertEqual(snapshot(self.root), before, "the report must not write receipts or the checkout")
        return result.returncode, result.stdout.splitlines()

    def test_c1_report(self):
        # C1: per-step calls, drifted calls and returned ids; any drift exits 1 with the FAIL trailer.
        self.receipt("a1b2", [("identify", "model-a", "model-a"), ("copy_select", "model-a", "model-a"),
                              ("picture", "vendor:image-b", "vendor:image-b")])
        self.receipt("a1b3", [("identify", "model-a", "model-a-2"), ("identify", "model-a", None),
                              ("picture", "vendor:image-b", "vendor:image-b")])
        self.receipt("a1b4", [("identify", "model-a", "model-a"), ("picture", "vendor:image-b", "vendor:image-c")])
        code, lines = self.run_cli()
        self.assertEqual(code, 1)
        self.assertEqual(lines, [
            "step copy_select calls=1 drifted=0 pinned=model-a returned=model-a",
            "step identify calls=4 drifted=1 pinned=model-a returned=model-a,model-a-2",
            "step picture calls=3 drifted=1 pinned=vendor:image-b returned=vendor:image-b,vendor:image-c",
            "FAIL npp_drift identify picture",
        ])
        # No drift: same steps, every returned id equals its pin (or is absent), exit 0 and PASS.
        self.receipt("a1b3", [("identify", "model-a", None)])
        self.receipt("a1b4", [("picture", "vendor:image-b", "vendor:image-b")])
        code, lines = self.run_cli()
        self.assertEqual(code, 0)
        self.assertEqual(lines[-1], "PASS npp_drift")
        self.assertIn("step identify calls=2 drifted=0 pinned=model-a returned=model-a", lines)
        # --since leaves out receipts created before the day, so their drift is not reported.
        self.receipt("a1b5", [("identify", "model-a", "model-z")], day="2031-01-27")
        self.assertEqual(self.run_cli()[0], 1)
        code, lines = self.run_cli("--since", "2031-02-01")
        self.assertEqual((code, lines[-1]), (0, "PASS npp_drift"))
        self.assertNotIn("model-z", "\n".join(lines))

    def test_c2_bad(self):
        # C2: evidence failing evidence.validate is skipped with a NOTE; the rest still reports.
        self.receipt("c0de", [("identify", "model-a", "model-a")])
        drifted = dict(step="identify", pinned="model-a", returned="model-q", drift=False)  # inconsistent drift
        bad = Evidence().doc() | dict(models=[drifted])
        self.receipt("c0df", doc=bad)
        self.receipt("c0e0", doc=dict(evidence_version=1))
        code, lines = self.run_cli()
        self.assertEqual(code, 0)
        self.assertEqual(lines, ["NOTE bad-evidence c0df", "NOTE bad-evidence c0e0",
                                 "step identify calls=1 drifted=0 pinned=model-a returned=model-a",
                                 "PASS npp_drift"])
        self.assertNotIn("model-q", "\n".join(lines))
        # A receipt from before HRM-11 has no evidence at all; it is noted, not called bad.
        self.receipt("c0e1", doc=None, evidence=None)
        self.assertIn("NOTE no-evidence c0e1", self.run_cli()[1])

    def test_empty_model_is_unpinned_even_when_returned_id_is_null(self):
        self.pins(dict(schema=1, steps=STEPS | dict(identify=dict(model=""))))
        self.receipt("d00d", [("identify", "model-a", None)])
        self.assertEqual(self.run_cli(), (1, [
            "step identify calls=1 drifted=0 pinned=- returned=-",
            "FAIL unpinned identify",
            "FAIL npp_drift identify",
        ]))

    def test_c3_pins(self):
        # C3: pins come from --repo's pins.json, not from the pinned value written in the evidence.
        self.receipt("d00d", [("identify", "model-old", "model-new"), ("copy_select", "model-a", "model-a")])
        code, lines = self.run_cli()
        self.assertEqual((code, lines[-1]), (1, "FAIL npp_drift identify"))
        self.assertIn("step identify calls=1 drifted=1 pinned=model-a returned=model-new", lines)
        self.pins(dict(schema=1, steps=STEPS | dict(identify=dict(model="model-new"))))
        self.assertEqual(self.run_cli(), (0, [
            "step copy_select calls=1 drifted=0 pinned=model-a returned=model-a",
            "step identify calls=1 drifted=0 pinned=model-new returned=model-new",
            "PASS npp_drift"]))
        # A step absent from pins (or pinned without a model id) is FAIL unpinned and fails the run.
        self.receipt("d00e", [("judge", "model-a", "model-a"), ("research_extract", "model-a", None)])
        code, lines = self.run_cli()
        self.assertEqual(code, 1)
        self.assertIn("step judge calls=1 drifted=0 pinned=- returned=model-a", lines)
        self.assertIn("FAIL unpinned judge", lines)
        self.assertIn("FAIL unpinned research_extract", lines)
        self.assertEqual(lines[-1], "FAIL npp_drift judge research_extract")
        # A checkout without a usable pins.json is refused outright.
        (self.repo / "hass/npp/pins.json").write_text("[]", encoding="utf-8")
        self.assertEqual(self.run_cli(), (2, ["FAIL bad-pins"]))


if __name__ == "__main__":
    unittest.main()
