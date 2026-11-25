"""Contract tests for turning successful Hass full-run artifacts into weights."""
import json
from pathlib import Path
from tempfile import TemporaryDirectory
import unittest

from scripts.hass.refresh_ci_weights import render_weights


def run(root, run_id, changes=None):
    records = [
        {"shard": str(i), "tier": "full", "modules": [f"test_m{i}"],
         "ok": True, "tests_run": 1, "errors": 0, "failures": 0,
         "unexpected_successes": 0, "module_seconds": {f"test_m{i}": 1.0}}
        for i in range(4)
    ]
    for i, fields in (changes or {}).items():
        records[i].update(fields)
    run_dir = root / run_id
    for i, record in enumerate(records):
        dest = run_dir / f"hass-record-{i}" / f"{i}.json"
        dest.parent.mkdir(parents=True)
        dest.write_text(json.dumps(record), encoding="utf-8")
    return run_dir


class RefreshWeightsTest(unittest.TestCase):
    def test_medians_filter_cross_shard_keys_and_keep_missing_modules_unweighted(self):
        # Last-writer-wins would overweight the re-exported test_m2 timing
        # or drop its later valid observation, and would not be repeatable.
        with TemporaryDirectory() as tmp:
            root = Path(tmp)
            first = run(root, "100", {0: {"module_seconds": {"test_m0": 2.1, "test_m2": 900}},
                                      1: {"module_seconds": {"test_m0": 800, "test_m1": 0}},
                                      3: {"module_seconds": {"test_m3": 99}}})
            second = run(root, "200", {0: {"module_seconds": {"test_m0": 4.1}},
                                       2: {"module_seconds": {"test_m2": 8.2}}})
            latest = run(root, "300", {0: {"module_seconds": {"test_m0": 6.1}}})
            modules = {"test_m0", "test_m1", "test_m2", "test_new"}
            output = render_weights([first, second, latest], modules)
            self.assertEqual(json.loads(output)["seconds"], {"test_m0": 6, "test_m1": 1, "test_m2": 5})
            self.assertEqual(output, render_weights([latest, first, second], modules))

    def test_invalid_receipts_cannot_contribute_weights(self):
        # A cancelled shard, a failed shard, overlapping modules, or a bad
        # sample must not be treated as successful observations.
        with TemporaryDirectory() as tmp:
            root = Path(tmp)
            partial = run(root, "100")
            (partial / "hass-record-2" / "2.json").rename(partial / "interrupted.json")
            valid = run(root, "101")
            for dirs in ([partial], [valid, valid]):
                with self.subTest(dirs=dirs), self.assertRaises((OSError, ValueError)):
                    render_weights(dirs, {"test_m0"})
            for i, fields in enumerate((
                {"ok": False, "failures": 1}, {"tier": "affected"}, {"shard": "1"},
                {"modules": ["test_m1"]}, {"tests_run": 0},
                *({"module_seconds": {"test_m0": n}} for n in (float("nan"), -1, True)),
            ), 110):
                broken = run(root, str(i), {0: fields})
                with self.subTest(fields=fields), self.assertRaises(ValueError):
                    render_weights([valid, broken], {"test_m0"})
