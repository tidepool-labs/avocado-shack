"""Contract tests for the offline, counts-only Clover link checker."""

from contextlib import closing, redirect_stderr, redirect_stdout
from dataclasses import dataclass
import importlib.util
import io
import json
import os
from pathlib import Path
import shutil
import sqlite3
import subprocess
import sys
import tempfile
from types import SimpleNamespace
import unittest
from unittest.mock import patch

from hass.clover import mapper

SCRIPT = Path(__file__).resolve().parents[2] / "scripts/hass/clover_link_health.py"
SPEC = importlib.util.spec_from_file_location("clover_link_health", SCRIPT)
assert SPEC is not None and SPEC.loader is not None
health = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(health)

PASS = "PASS clover_link_health"
FAIL = "FAIL clover_link_health"
PID, CID = "synthetic-site-key", "synthetic-till-key"
SITE_NAME, TILL_NAME = "Synthetic site name", "Synthetic till name"
SKU, OLD_ID = "SYNTHETIC-SKU", "synthetic-old-till-key"
SCHEMA = "CREATE TABLE items (id TEXT PRIMARY KEY, name TEXT, sku TEXT, hidden INTEGER)"


@dataclass
class Fixture:
    root: Path

    def __post_init__(self):
        self.state = self.root / "synthetic-state"
        self.content = self.root / "synthetic-content"
        self.folder = self.state / "clover"
        self.folder.mkdir(mode=0o700, parents=True)
        self.content.mkdir()
        self.products_path = self.content / "products.json"
        self.links_path = self.folder / "links.json"
        self.store = self.folder / "cache.sqlite3"
        self.products(product())

    @property
    def args(self):
        return ["--state", str(self.state), "--content", str(self.content)]

    def products(self, *rows):
        self.products_path.write_text(json.dumps({"products": rows}), encoding="utf-8")

    def links(self, value):
        self.links_path.write_text(json.dumps(value), encoding="utf-8")
        self.links_path.chmod(0o600)

    def cache(self, *rows, wal=False):
        with closing(sqlite3.connect(self.store)) as db:
            if wal:
                db.execute("PRAGMA journal_mode=WAL")
            db.execute(SCHEMA)
            db.executemany("INSERT INTO items VALUES (?, ?, ?, ?)", rows)
            db.commit()

    def inventory(self):
        paths = [self.state, self.content, *self.state.rglob("*"), *self.content.rglob("*")]
        return {p: (p.lstat().st_mtime_ns, p.read_bytes() if p.is_file() else None) for p in paths}


def product(pid=PID, name=SITE_NAME, status="active"):
    return {"id": pid, "name": name, "status": status}


class CloverLinkHealthTests(unittest.TestCase):
    def fixture(self):
        temp = tempfile.TemporaryDirectory()
        self.addCleanup(temp.cleanup)
        return Fixture(Path(temp.name).resolve())

    def invoke(self, args, *, cli=False, cwd=None, env=None):
        if cli:
            result = subprocess.run([sys.executable, "-B", str(SCRIPT), *args],
                                    cwd=cwd, env=env, capture_output=True, text=True, timeout=10)
            return result.returncode, result.stdout, result.stderr
        out, err = io.StringIO(), io.StringIO()
        with redirect_stdout(out), redirect_stderr(err):
            code = health.main(args)
        return code, out.getvalue(), err.getvalue()

    def assert_report(self, result, code, *lines):
        self.assertEqual(result, (code, "\n".join((*lines, PASS if code == 0 else FAIL)) + "\n", ""))

    def test_c1_full_pass(self):
        # A mismatched saved SKU must not defeat a valid ID; an unlinked name match is not a link.
        fixture = self.fixture()
        fixture.products(product(), product("synthetic-unlinked", "Name-only example"))
        fixture.links({PID: {"cloverId": CID, "sku": "synthetic-earlier-sku"}})
        fixture.cache((CID, TILL_NAME, SKU, 0), ("synthetic-unlinked-item", "Name-only example", "", 1))
        self.assert_report(self.invoke(fixture.args, cli=True, cwd=fixture.root), 0, "links 1", "by-id 1", "by-sku 0")

    def test_c2_1_unsafe_state(self):
        # Following a symlink or accepting a public link table exposes an unapproved input.
        for leaf, kind in (
            ("state", "absent"), ("state", "file"), ("state", "symlink"),
            ("folder", "file"), ("folder", "symlink"), ("folder", "public"),
            ("store", "symlink"), ("store", "directory"),
            ("links_path", "symlink"), ("links_path", "directory"), ("links_path", "public"),
            ("links_path", "list"), ("links_path", "syntax"), ("links_path", "owner"),
        ):
            with self.subTest(leaf=leaf, kind=kind):
                fixture = self.fixture()
                fixture.links({PID: {"cloverId": CID}})
                path = getattr(fixture, leaf)
                if kind in ("absent", "file", "symlink", "directory"):
                    target = fixture.root / "synthetic-other"
                    if path.exists():
                        path.rename(target)
                    if kind == "file":
                        path.touch()
                    elif kind == "directory":
                        path.mkdir()
                    elif kind == "symlink":
                        path.symlink_to(target)
                elif kind == "public":
                    path.chmod(path.stat().st_mode | 0o004)
                elif kind == "list":
                    fixture.links([])
                elif kind == "syntax":
                    path.write_text("[", encoding="utf-8")
                elif kind == "owner":
                    lstat = Path.lstat

                    def different_owner(candidate):
                        st = lstat(candidate)
                        if candidate == path:
                            return SimpleNamespace(st_mode=st.st_mode, st_uid=st.st_uid + 1)
                        return st

                    with patch.object(Path, "lstat", different_owner):
                        self.assert_report(self.invoke(fixture.args), 1, "FAIL unsafe-state")
                    continue
                prefix = ("links 1",) if leaf == "store" else ()
                self.assert_report(self.invoke(fixture.args), 1, *prefix, "FAIL unsafe-state")

    def test_c2_2_unreadable_products(self):
        # A malformed, non-UTF-8, missing or redirected catalog must not mean zero products.
        for raw in (None, "symlink", "directory", b"\xff", b"{", b"[]", b"{}", b'{"products": {}}'):
            with self.subTest(raw=raw):
                fixture = self.fixture()
                path = fixture.products_path
                original = fixture.root / "synthetic-original.json"
                path.rename(original)
                if raw == "symlink":
                    path.symlink_to(original)
                elif raw == "directory":
                    path.mkdir()
                elif raw is not None:
                    path.write_bytes(raw)
                self.assert_report(self.invoke(fixture.args), 1, "FAIL unreadable products")

    def test_c2_3_malformed(self):
        # Bad shapes count only as malformed, even if their site ID is missing or SKU could pair.
        fixture = self.fixture()
        fixture.links({PID: {"cloverId": 47, "sku": SKU}, "synthetic-missing": [CID],
                       "synthetic-no-id": {"sku": SKU}})
        fixture.cache((CID, SITE_NAME, SKU, 1))
        self.assert_report(self.invoke(fixture.args), 1, "links 3", "FAIL malformed 3", "by-id 0", "by-sku 0")

    def test_c2_4_inactive_site(self):
        # Hidden and absent site rows cannot claim an item or inflate the duplicate count.
        fixture = self.fixture()
        fixture.products(product(), product("a-inactive", status="hidden"))
        fixture.links({pid: {"cloverId": CID} for pid in (PID, "a-inactive", "b-missing")})
        fixture.cache((CID, TILL_NAME, SKU, 0))
        self.assert_report(self.invoke(fixture.args), 1, "links 3", "FAIL inactive-site 2", "by-id 1", "by-sku 0")

    def test_c2_5_stale_id(self):
        # Resolving a stale ID by SKU is not a clean pass.
        fixture = self.fixture()
        fixture.links({PID: {"cloverId": OLD_ID, "sku": SKU}})
        fixture.cache((CID, TILL_NAME, SKU, 0))
        self.assert_report(self.invoke(fixture.args), 1, "links 1", "by-id 0", "by-sku 1", "FAIL stale-id 1")

    def test_c2_6_broken(self):
        # A missing target or ambiguous SKU cannot be repaired with an exact name.
        fixture = self.fixture()
        fixture.products(product(), product("synthetic-second", "Different site name"))
        fixture.links({PID: {"cloverId": OLD_ID, "sku": SKU}, "synthetic-second": {"cloverId": "synthetic-missing"}})
        fixture.cache((CID, SITE_NAME, SKU, 0), ("synthetic-twin", TILL_NAME, SKU, 0))
        self.assert_report(self.invoke(fixture.args), 1, "links 2", "by-id 0", "by-sku 0", "FAIL broken 2")

    def test_c2_7_shared(self):
        # Count all links in the collision, not just the losing links or one per ID.
        fixture = self.fixture()
        fixture.products(product("a"), product("b"), product("c"))
        fixture.links({"c": {"cloverId": CID}, "b": {"cloverId": CID, "sku": SKU}, "a": {"cloverId": CID}})
        fixture.cache((CID, TILL_NAME, "", 0), ("synthetic-fallback", "Fallback example", SKU, 0))
        self.assert_report(self.invoke(fixture.args), 1, "links 3", "by-id 1", "by-sku 1",
                           "FAIL stale-id 1", "FAIL broken 1", "FAIL shared 3")

    def test_c2_8_hidden_target(self):
        # Hidden items still resolve and must count in both resolution modes.
        fixture = self.fixture()
        fixture.products(product(), product("synthetic-second"))
        fixture.links({PID: {"cloverId": CID}, "synthetic-second": {"cloverId": OLD_ID, "sku": SKU}})
        fixture.cache((CID, TILL_NAME, "", 1), ("synthetic-fallback", "Fallback example", SKU, 1))
        self.assert_report(self.invoke(fixture.args), 1, "links 2", "by-id 1", "by-sku 1",
                           "FAIL stale-id 1", "FAIL hidden-target 2")

    def test_c2_9_cache_absent(self):
        # sqlite3.connect on the original would create a missing DB and obscure the reason.
        fixture = self.fixture()
        fixture.links({PID: {"cloverId": CID}})
        self.assert_report(self.invoke(fixture.args), 1, "links 1", "FAIL cache-absent")
        self.assertFalse(fixture.store.exists())

    def test_c2_10_not_sqlite(self):
        # Bad bytes/schema and unsafe sidecars have one fixed, path-free refusal.
        for bad in ("bytes", "table", "column", "-wal", "-journal"):
            with self.subTest(bad=bad):
                fixture = self.fixture()
                fixture.links({PID: {"cloverId": CID}})
                if bad == "bytes":
                    fixture.store.write_bytes(b"not a database")
                elif bad in ("table", "column"):
                    with closing(sqlite3.connect(fixture.store)) as db:
                        db.execute("CREATE TABLE unrelated (id TEXT)" if bad == "table" else
                                   "CREATE TABLE items (id TEXT, name TEXT, sku TEXT)")
                else:
                    fixture.cache((CID, TILL_NAME, SKU, 0))
                    path = fixture.store.with_name(fixture.store.name + bad)
                    if bad == "-wal":
                        path.symlink_to(fixture.root / "missing-sidecar-target")
                    else:
                        path.mkdir()
                self.assert_report(self.invoke(fixture.args), 1, "links 1", "FAIL not-sqlite cache.sqlite3")

    def test_c2_11_temp_unavailable(self):
        # Neither input roots nor a nonexistent alternative may be used as scratch.
        fixture = self.fixture()
        fixture.links({PID: {"cloverId": CID}})
        fixture.cache((CID, TILL_NAME, SKU, 0))
        before = fixture.inventory()
        with patch.object(health, "_temp_candidates", return_value=[fixture.folder, fixture.content, fixture.root / "missing"]):
            self.assert_report(self.invoke(fixture.args), 1, "links 1", "FAIL temp-unavailable")
        self.assertEqual(fixture.inventory(), before)

    def test_c3_usage_exit_2(self):
        # Argparse owns syntax failures; they are not ordinary report findings.
        fixture = self.fixture()
        for args in ([], [*fixture.args, "--unknown"], [*fixture.args, "--state"]):
            with self.subTest(args=args):
                code, out, err = self.invoke(args, cli=True, cwd=fixture.root)
                self.assertEqual(code, 2)
                self.assertEqual(out, "")
                self.assertTrue(err.startswith("usage:"))
                self.assertIn("error:", err.splitlines()[-1])

    def test_c4_read_only(self):
        # Opening a WAL-mode input directly can leave sidecars or change directory mtimes.
        fixture = self.fixture()
        fixture.links({PID: {"cloverId": CID}})
        fixture.cache((CID, TILL_NAME, SKU, 0), wal=True)
        safe = fixture.root / "synthetic-scratch"
        safe.mkdir()
        before = fixture.inventory()
        with patch.object(health, "_temp_candidates", return_value=[safe]):
            self.assert_report(self.invoke(fixture.args), 0, "links 1", "by-id 1", "by-sku 0")
        self.assertEqual(fixture.inventory(), before)
        self.assertEqual(list(safe.iterdir()), [])

    def test_c5_no_private_values(self):
        # Even a report with findings may emit only counts and fixed reason words.
        fixture = self.fixture()
        private_link_value = "synthetic-private-extra-link-value"
        fixture.links({PID: {"cloverId": OLD_ID, "sku": SKU, "extra": private_link_value}})
        fixture.cache((CID, TILL_NAME, SKU, 1))
        result = self.invoke(fixture.args, cli=True, cwd=fixture.root)
        for canary in (PID, CID, OLD_ID, SITE_NAME, TILL_NAME, SKU, private_link_value,
                       str(fixture.state), str(fixture.content)):
            self.assertNotIn(canary, result[1] + result[2])
        self.assert_report(result, 1, "links 1", "by-id 0", "by-sku 1", "FAIL stale-id 1", "FAIL hidden-target 1")

    def test_c6_links_absent_pass(self):
        # Neither absence nor an empty object should try to open a missing cache.
        for empty_file in (False, True):
            with self.subTest(empty_file=empty_file):
                fixture = self.fixture()
                if empty_file:
                    fixture.links({})
                self.assert_report(self.invoke(fixture.args), 0, "links absent")
                self.assertFalse(fixture.store.exists())

    def test_c7_match_parity(self):
        # A case-variant SKU on a recreated item is a pair in the merged mapper, not a broken link.
        fixture = self.fixture()
        fixture.products(product(), product("synthetic-recreated-site", "Recreated example"))
        links = {PID: {"cloverId": CID}, "synthetic-recreated-site": {"cloverId": OLD_ID, "sku": SKU.lower()}}
        fixture.links(links)
        fixture.cache((CID, TILL_NAME, "", 0), ("synthetic-recreated-till", "New till name", SKU, 0))
        direct = mapper.match(
            [SimpleNamespace(id=PID, name=SITE_NAME), SimpleNamespace(id="synthetic-recreated-site", name="Recreated example")],
            [SimpleNamespace(id=CID, name=TILL_NAME, sku=""),
             SimpleNamespace(id="synthetic-recreated-till", name="New till name", sku=SKU)], links)
        self.assertCountEqual([pair.how for pair in direct.pairs], ["link", "sku"])
        self.assertEqual(direct.broken_links, ())
        with patch.object(mapper, "match", wraps=mapper.match) as run_match:
            self.assert_report(self.invoke(fixture.args), 1, "links 2", "by-id 1", "by-sku 1", "FAIL stale-id 1")
        run_match.assert_called_once()

    def test_c8_wal_rows_counted(self):
        # An immutable open or base-only copy misses a committed but uncheckpointed row.
        fixture = self.fixture()
        fixture.links({PID: {"cloverId": CID}})
        original = fixture.root / "synthetic-writer.sqlite3"
        base_only = fixture.root / "synthetic-checkpoint.sqlite3"
        wal = fixture.store.with_name(fixture.store.name + "-wal")
        shm = fixture.store.with_name(fixture.store.name + "-shm")
        with closing(sqlite3.connect(original)) as writer:
            self.assertEqual(writer.execute("PRAGMA journal_mode=WAL").fetchone(), ("wal",))
            writer.execute("PRAGMA wal_autocheckpoint=0")
            writer.execute(SCHEMA)
            writer.execute("PRAGMA wal_checkpoint(TRUNCATE)").fetchone()
            writer.execute("INSERT INTO items VALUES (?, ?, ?, ?)", (CID, TILL_NAME, SKU, 0))
            writer.commit()
            shutil.copyfile(original, fixture.store)
            shutil.copyfile(original.with_name(original.name + "-wal"), wal)
            shutil.copyfile(original, base_only)
        with closing(sqlite3.connect(base_only)) as db:
            self.assertEqual(db.execute("SELECT id FROM items").fetchall(), [])
        before = fixture.inventory()
        self.assert_report(self.invoke(fixture.args), 0, "links 1", "by-id 1", "by-sku 0")
        self.assertEqual(fixture.inventory(), before)
        self.assertFalse(shm.exists())
        # The input SHM is never consulted, even if it is a dangling symlink.
        shm.symlink_to(fixture.root / "synthetic-missing-shm")
        self.assert_report(self.invoke(fixture.args), 0, "links 1", "by-id 1", "by-sku 0")
        self.assertTrue(shm.is_symlink())

    def test_c9_tmpdir_inside_input(self):
        # tempfile's own probing can modify an input directory even if it leaves no file.
        fixture = self.fixture()
        fixture.links({PID: {"cloverId": CID}})
        fixture.cache((CID, TILL_NAME, SKU, 0))
        nested = fixture.content / "synthetic-nested"
        nested.mkdir()
        alias = fixture.root / "synthetic-alias"
        alias.symlink_to(nested, target_is_directory=True)
        safe = fixture.root / "synthetic-scratch"
        safe.mkdir()
        for candidate in (fixture.state, nested, alias):
            with self.subTest(candidate=candidate.name):
                before = fixture.inventory()
                env = {**os.environ, "TMPDIR": str(candidate), "TEMP": str(safe)}
                self.assert_report(self.invoke(fixture.args, cli=True, cwd=fixture.root, env=env),
                                   0, "links 1", "by-id 1", "by-sku 0")
                self.assertEqual(fixture.inventory(), before)
                self.assertEqual(list(safe.iterdir()), [])
