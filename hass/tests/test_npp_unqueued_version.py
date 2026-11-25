"""NPP acceptance runner: a version that never left the building step is not a draft.

Case 28a ("an unsafe raw photo gets the existing retake sentence, no draft and no prompt"): production builds a
version row, the picture step refuses the raw photo, and Jobs.finish sends the retake sentence and marks that unqueued
row `superseded`. The runner counted every non-building row as a draft, so a correct retake still failed `no_draft`.
Contract: a building row and a superseded row with no card PNG, chat row, queued or delivered time do not count; a row
that was queued or delivered counts whatever its later state, including a partly written one. Rows come from the real
npp_versions schema with the same statements production uses. Fixtures only: no model, network or private recording.
"""
import importlib.util
import sqlite3
import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))


def _load(name, path):
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module
    spec.loader.exec_module(module)
    return module


run_npp = _load("npp_run_unqueued_version_under_test", ROOT / "hass" / "tests" / "npp" / "run_npp.py")
from hass.npp import job  # noqa: E402

# The statements production runs (hass/npp/job.py): build, queue, deliver, and the two supersede forms.
BUILD = ("INSERT INTO npp_versions(job_id,n,parent_n,segment_id,listing_json,listing_sha,patch_json,state) "
         "VALUES (?,?,?,?,'{}','sha','{}','building')")
QUEUE = ("UPDATE npp_versions SET card_png_sha=?,outbox_id=?,queued_at=?,state='queued' WHERE job_id=? AND n=?")
DELIVER = "UPDATE npp_versions SET delivered_at=?, state=CASE WHEN state='queued' THEN 'delivered' ELSE state END WHERE job_id=? AND n=?"
SUPERSEDE_ONE = "UPDATE npp_versions SET state='superseded' WHERE job_id=? AND n=?"
CLOSE = "UPDATE npp_versions SET state='superseded' WHERE job_id=? AND state IN ('building','queued','delivered')"


class UnqueuedVersion(unittest.TestCase):
    def setUp(self):
        self.db = sqlite3.connect(":memory:")
        self.db.row_factory = sqlite3.Row
        self.db.executescript(job.SCHEMA)
        self.segment = 0

    def build(self, jid, n):
        self.segment += 1
        self.db.execute(BUILD, (jid, n, n - 1 or None, self.segment))

    def count(self):
        # Exactly how the runner reads the table.
        return run_npp.frozen_version_rows([dict(v) for v in self.db.execute("SELECT * FROM npp_versions ORDER BY n")])

    def test_production_marks_the_refused_build_superseded_without_queue_fields(self):
        self.build("a", 1)
        self.assertEqual(self.count(), 0)
        self.db.execute(SUPERSEDE_ONE, ("a", 1))  # Jobs.finish after a retake/question/render failure
        row = dict(self.db.execute("SELECT * FROM npp_versions").fetchone())
        self.assertEqual(row["state"], "superseded")
        self.assertTrue(all(row[k] is None for k in run_npp.UNQUEUED))
        self.assertEqual(self.count(), 0)
        self.build("b", 1)
        self.db.execute(CLOSE, ("b",))  # Jobs.close on a still-building row
        self.assertEqual(self.count(), 0)

    def test_queued_or_delivered_versions_count_after_supersession(self):
        self.build("q", 1)
        self.db.execute(QUEUE, ("png", 11, "t", "q", 1))
        self.assertEqual(self.count(), 1)
        self.db.execute(CLOSE, ("q",))
        self.assertEqual(self.count(), 1)  # a queued card that reached the outbox stays a draft
        self.build("d", 1)
        self.db.execute(QUEUE, ("png2", 12, "t", "d", 1))
        self.db.execute(DELIVER, ("t2", "d", 1))
        self.assertEqual(dict(self.db.execute("SELECT state FROM npp_versions WHERE job_id='d'").fetchone())["state"],
                         "delivered")
        self.db.execute(SUPERSEDE_ONE, ("d", 1))
        self.assertEqual(self.count(), 2)

    def test_any_single_queue_field_keeps_a_superseded_row_counted(self):
        base = {"state": "superseded", **dict.fromkeys(run_npp.UNQUEUED)}
        self.assertEqual(run_npp.frozen_version_rows([base]), 0)
        for key in run_npp.UNQUEUED:
            with self.subTest(field=key):
                self.assertEqual(run_npp.frozen_version_rows([{**base, key: "x"}]), 1)

    def test_other_states_count_as_before(self):
        rows = [{"state": state, **dict.fromkeys(run_npp.UNQUEUED)} for state in ("queued", "delivered", "approved")]
        self.assertEqual(run_npp.frozen_version_rows(rows), 3)
        self.assertEqual(run_npp.frozen_version_rows([{"state": "building", **dict.fromkeys(run_npp.UNQUEUED)}]), 0)

    def test_queue_columns_exist_in_the_schema(self):
        columns = {row[1] for row in self.db.execute("PRAGMA table_info(npp_versions)")}
        self.assertLessEqual(set(run_npp.UNQUEUED), columns)


if __name__ == "__main__":
    unittest.main()
