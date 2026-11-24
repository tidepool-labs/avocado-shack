"""M4b: one till pull never fails on a repeated item id (a paged Clover list can return an item twice when the shop edits it mid-pull).
Synthetic fake merchant only, no network, a temporary private state folder. Run: python3 -B -m unittest hass.tests.test_clover_sync_duplicates -v

Contract: sync.rows() hands the cache ONE row per item id, so cache.write_items() (one transaction, items.id primary key) always succeeds.
Plausible regression: rows() passes both copies through, write_items() raises IntegrityError, the whole pull rolls back and the sync
fails the same way on every run until the till stops shifting.
"""
import os
import shutil
import sqlite3
import tempfile
import unittest
from datetime import datetime, timezone
from pathlib import Path

from hass.clover import cache, sync

IDENT = cache.Identity("production", "FAKEMERCH0001")
T0 = datetime(2026, 11, 24, 8, 0, tzinfo=timezone.utc)


def item(iid, name, modified=None, **extra):
    raw = {"id": iid, "name": name, "price": 100, **extra}
    if modified is not None:
        raw["modifiedTime"] = modified
    return raw


def stock(iid, quantity, modified=None):
    el = {"item": {"id": iid}, "quantity": quantity}
    if modified is not None:
        el["modifiedTime"] = modified
    return el


class SyncDuplicateCase(unittest.TestCase):
    def setUp(self):
        self.state = Path(tempfile.mkdtemp(prefix="clover-dupes-"))
        self.addCleanup(shutil.rmtree, self.state, True)
        os.chmod(self.state, 0o700)

    def test_duplicate_item_ids_write_one_row(self):
        # Contract: a repeated id never reaches the cache twice. Bug caught: both copies are emitted and write_items raises IntegrityError.
        rows, skipped = sync.rows([item("AAA111", "Apples", 1000), item("AAA111", "Apples", 2000), item("BBB222", "Bananas", 500)], [])
        self.assertEqual(sorted(r["id"] for r in rows), ["AAA111", "BBB222"])
        self.assertEqual(skipped, 1)
        try:
            cache.write_items(self.state, rows, T0, IDENT)
        except sqlite3.IntegrityError as exc:   # the baseline failure, reported as a test failure rather than an error
            self.fail(f"one repeated id aborted the whole write: {exc}")
        snapshot, _ = cache.read(self.state, IDENT)
        self.assertIsNotNone(snapshot)
        self.assertEqual(sorted(i.id for i in snapshot.items), ["AAA111", "BBB222"])

    def test_every_extra_copy_is_counted_and_never_echoed(self):
        # Contract: each dropped duplicate adds one to skipped, and nothing from it is kept. Bug caught: counting once per id, or leaking the dropped copy.
        rows, skipped = sync.rows([item("AAA111", "Apples", 3), item("AAA111", "Dropped one", 2), item("AAA111", "Dropped two", 1)], [])
        self.assertEqual((len(rows), skipped), (1, 2))
        self.assertNotIn("Dropped", repr(rows))

    def test_duplicate_item_keeps_newer_modified_time(self):
        # Contract: the copy with the greater modifiedTime wins, wherever it is listed; a missing time is lowest; a tie keeps the first listed.
        # Bug caught: first-wins or last-wins keeps the stale copy of an item the shop just edited.
        cases = {
            "newer second": ([("Old name", 1000), ("New name", 2000)], "New name"),
            "newer first": ([("New name", 2000), ("Old name", 1000)], "New name"),
            "missing time is lowest, listed first": ([("Old name", None), ("New name", 1)], "New name"),
            "missing time is lowest, listed second": ([("New name", 1), ("Old name", None)], "New name"),
            "tie keeps first listed": ([("First name", 700), ("Second name", 700)], "First name"),
            "both missing keeps first listed": ([("First name", None), ("Second name", None)], "First name"),
        }
        for label, (copies, expected) in cases.items():
            with self.subTest(label):
                rows, skipped = sync.rows([item("AAA111", name, mod) for name, mod in copies], [])
                self.assertEqual(([r["name"] for r in rows], skipped), ([expected], 1))

    def test_duplicate_stock_record_keeps_newest(self):
        # Contract: of two stock records for one item the greater modifiedTime wins (None lowest, tie keeps first listed).
        # Bug caught: the last listed record wins, so an older count (9 at 1000) replaces the newer one (4 at 2000).
        cases = {
            "newer first": ([(4, 2000), (9, 1000)], ("4", 2000)),
            "newer second": ([(9, 1000), (4, 2000)], ("4", 2000)),
            "missing time is lowest": ([(4, 1), (9, None)], ("4", 1)),
            "missing time listed first": ([(9, None), (4, 1)], ("4", 1)),
            "tie keeps first listed": ([(4, 500), (9, 500)], ("4", 500)),
        }
        for label, (records, expected) in cases.items():
            with self.subTest(label):
                self.assertEqual(sync.stock_by_item([stock("AAA111", q, m) for q, m in records]), {"AAA111": expected})
        rows, skipped = sync.rows([item("AAA111", "Apples", 1)], [stock("AAA111", 9, 1000), stock("AAA111", 4, 2000)])
        self.assertEqual((rows[0]["stock"], rows[0]["stock_modified"], skipped), ("4", 2000, 0))

    def test_distinct_items_unchanged(self):
        # Healthy control: distinct ids keep every row, in pull order, with skipped 0 and the stock text rules as before.
        # Bug caught: the dedupe drops or reorders rows that were never repeated, or counts a malformed element differently.
        items = [item("AAA111", "Apples", 10), item("BBB222", "Bananas"), {"id": "bad id", "name": "Malformed"}, item("CCC333", "Cherries", 30)]
        stocks = [stock("AAA111", 12, 5), stock("BBB222", "1.50", 6), stock("ZZZ999", 3, 7)]
        rows, skipped = sync.rows(items, stocks)
        self.assertEqual([r["id"] for r in rows], ["AAA111", "BBB222", "CCC333"])
        self.assertEqual(skipped, 1)
        self.assertEqual([(r["stock"], r["stock_modified"]) for r in rows], [("12", 5), ("1.5", 6), (None, None)])
        self.assertEqual([r["modified_time"] for r in rows], [10, 0, 30])
        self.assertEqual(sync.stock_by_item(stocks), {"AAA111": ("12", 5), "BBB222": ("1.5", 6), "ZZZ999": ("3", 7)})
        cache.write_items(self.state, rows, T0, IDENT)
        snapshot, _ = cache.read(self.state, IDENT)
        self.assertIsNotNone(snapshot)
        self.assertEqual(sorted(i.id for i in snapshot.items), ["AAA111", "BBB222", "CCC333"])


if __name__ == "__main__":
    unittest.main()
