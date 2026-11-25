"""AVO-LAUNCH-1 tests: ``sitegen.py --publish DIR`` builds only the website, and the PUBLISHED output carries no
commerce surface beyond the read-only selling price, pre-launch copy, private files, contact data or location metadata.

These checks read every file in the published folder, not just the home page: the archived commerce preview passed
the home-page-only catalog check because nothing looked anywhere else. Failure messages name files and counts only,
never matched values (the private research files hold third-party contact details).
Run: python3 -B -m unittest hass.tests.test_publish -v
"""

import contextlib
import datetime
import errno
import hashlib
import io
import json
import os
import re
import shutil
import stat
import struct
import tempfile
import unittest
from pathlib import Path
from unittest import mock

from hass import sitegen
from hass.live_policy import COMMERCE_WORDS, EMAIL, PHONE
from hass.content_model import REPO_ROOT, SITE_DIR, load_and_validate, shop_today

TEXT_EXT = {".html", ".js", ".json", ".css"}
ALLOWED_EXT = TEXT_EXT | {".jpg", ".png", ".webp"}
# Files that exist in storefront-mockup/ and must never be published (named, not just "anything else").
PRIVATE = ("producer-research-log.json", "held-products.json", "community-server.py", "community-qa.py",
           "catalog-only-qa.cjs", "community-ui-qa.cjs", "qa-env.cjs", "README.md", "catalog.js", "catalog.json",
           "shop-data.json", "catalog-extraction.csv", "new-products.json", "completion-new-products.json",
           "producers.json", "desktop.png", "mobile.png", "archive/commerce-preview/index.html",
           "assets/share.jpg", "assets/vegetables.jpg", "assets/pantry.jpg")
# Selectors catalog-only-qa.cjs refuses on the home page, as markup, plus the archived page's surface.
COMMERCE_MARKUP = re.compile(r"""(?:id|class)=["'][^"']*\b(?:bag|boxes|merch|owner|order-preview|price|basket|cart|"""
                             r"""checkout|subtotal)\b|data-add(?![-\w])|data-product(?![-\w])""", re.I)

PRELAUNCH = re.compile(r"sandbox|before (?:a public )?launch|during setup|not been checked|not connected|"
                       r"saved locally|local service|local signup|unsubscribe|proposed mailbox|lorem|ipsum|"
                       r"\bTODO\b|\bFIXME\b", re.I)

PLACEHOLDER_EMAILS = {"you@example.com"}
LOGO_SHA256 = "f958d2890a56b07894f0f53a2826cc9a57fe9c9fcfcef1a91098e419f0277387"  # assets/logo.png, kept unchanged
# Hosts a published page may link to or name (outbound links only; nothing is loaded from them).
SITE_LINK = re.compile(r"""(?:src|href)=["']([^"'#][^"']*)["']""")
JS_PATH = re.compile(r"""['"`(](/(?:assets/[A-Za-z0-9_./-]+|[A-Za-z0-9_-]+\.json))['"`)]""")


def _publish(out):
    content = load_and_validate()
    with contextlib.redirect_stdout(io.StringIO()):
        written = sitegen.publish(content, REPO_ROOT, out)
    return content, written


class PublishedSite(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls._tmp = tempfile.TemporaryDirectory()
        cls.out = Path(cls._tmp.name) / "site"
        cls.content, cls.written = _publish(cls.out)
        cls.files = sorted(p.relative_to(cls.out).as_posix() for p in cls.out.rglob("*") if p.is_file())
        cls.text = {rel: (cls.out / rel).read_text("utf-8") for rel in cls.files if Path(rel).suffix in TEXT_EXT}

    @classmethod
    def tearDownClass(cls):
        cls._tmp.cleanup()

    def test_only_the_allowlist_is_published(self):
        images = sorted({p["image"] for p in self.content.active_products()})
        expected = sorted(set(sitegen.PUBLISH_GENERATED + sitegen.PUBLISH_PAGES + sitegen.PUBLISH_STATIC + sitegen.PUBLISH_ASSETS)
                          | set(images) | {"community.json"})
        self.assertEqual(self.files, expected)
        self.assertEqual(sorted(self.written), expected)
        self.assertGreaterEqual(len(images), 1)  # HASS-LIVE-ADD-1: not 170: a live add or hide changes it; `expected` above is the exact check
        self.assertEqual({Path(rel).suffix for rel in self.files} - ALLOWED_EXT, set())
        for rel in PRIVATE:
            with self.subTest(rel=rel):
                self.assertTrue((SITE_DIR / rel).is_file(), "fixture: the private file exists in the working folder")
                self.assertFalse((self.out / rel).exists())
        self.assertFalse((self.out / "archive").exists())

    def test_no_commerce_surface_in_any_published_file(self):
        # Positive control: the same patterns find the archived commerce page in the working folder.
        archived = (SITE_DIR / "archive/commerce-preview/index.html").read_text("utf-8")
        self.assertTrue(COMMERCE_MARKUP.search(archived) and COMMERCE_WORDS.search(archived))
        for rel, text in self.text.items():
            if rel.endswith(".css"):
                continue  # stylesheet selectors are not a visitor surface; markup and copy are checked below
            if rel == "shop.js":  # HASS-SITE-PRICE-1: exempt only the approved read-only card fragment
                text = text.replace('<p class="product-meta product-price">$${esc(p.sellingPrice)}</p>', '', 1)
            with self.subTest(rel=rel):
                self.assertEqual(len(COMMERCE_MARKUP.findall(text)), 0, f"commerce markup in {rel}")
                self.assertEqual(len(COMMERCE_WORDS.findall(text)), 0, f"commerce wording in {rel}")

    def test_no_foreign_share_tags_or_retired_domain(self):
        self.assertIn("slofishreport", (SITE_DIR / "archive/commerce-preview/index.html").read_text("utf-8"))
        for rel, text in self.text.items():
            with self.subTest(rel=rel):
                self.assertNotIn("slofishreport", text)
                self.assertNotRegex(text, r"og:url|og:image")

    def test_no_pre_launch_or_internal_copy(self):
        self.assertTrue(PRELAUNCH.search((SITE_DIR / "community-server.py").read_text("utf-8")))  # control
        for rel, text in self.text.items():
            with self.subTest(rel=rel):
                self.assertEqual(len(PRELAUNCH.findall(text)), 0, f"pre-launch or internal wording in {rel}")

    def test_no_contact_details_published(self):
        log = (SITE_DIR / "producer-research-log.json").read_text("utf-8")
        self.assertTrue(EMAIL.search(log) and PHONE.search(log))  # control: the private log is caught
        for rel, text in self.text.items():
            with self.subTest(rel=rel):
                emails = set(EMAIL.findall(text)) - PLACEHOLDER_EMAILS
                self.assertEqual(len(emails), 0, f"{len(emails)} email address(es) in {rel}")
                self.assertEqual(len(PHONE.findall(text)), 0, f"phone number(s) in {rel}")
        club = json.loads(self.text["community.json"])
        self.assertLessEqual(set(club), set(sitegen.PUBLIC_COMMUNITY_KEYS))  # AV1422-10: showSamples only when false
        self.assertLessEqual({"clubName", "events", "routeIdeas"}, set(club))
        self.assertEqual(len(club["routeIdeas"]), 3)

    def test_images_carry_no_camera_or_location_metadata(self):
        for rel in self.files:
            data = (self.out / rel).read_bytes()
            with self.subTest(rel=rel):
                if rel.endswith(".jpg"):
                    self.assertNotIn(b"Exif\x00\x00", data)
                elif rel.endswith(".png"):
                    self.assertNotIn(b"eXIf", data)
                elif rel.endswith(".webp"):
                    self.assertNotIn(b"EXIF", data[:4096])

    def test_hero_image_is_phone_sized(self):
        self.assertLess((self.out / "assets/store.jpg").stat().st_size, 500_000)

    def test_every_local_reference_resolves(self):
        published = set(self.files)
        checked = 0
        for rel, text in self.text.items():
            refs = []
            if rel.endswith(".html"):
                refs = [r for r in SITE_LINK.findall(text) if not re.match(r"[a-z]+:", r)]
            elif rel.endswith(".js"):
                refs = JS_PATH.findall(text)
            for ref in refs:
                if ref.startswith("/api/") or "${" in ref:
                    continue
                path = ref.split("#")[0].split("?")[0]
                target = path.lstrip("/") if path.startswith("/") else (Path(rel).parent / path).as_posix()
                target = target.removeprefix("./")
                if target in ("", "hike") or target.endswith("/"):
                    target = target + "index.html" if target != "hike" else "hike/index.html"
                with self.subTest(ref=ref, page=rel):
                    self.assertTrue(target in published, f"{target} is not published")
                checked += 1
        self.assertGreater(checked, 15)

    def test_header_logo_and_favicon_are_small_copies_and_logo_png_is_unchanged(self):
        def ihdr(path):  # width, height from the PNG header, no image library
            data = path.read_bytes()
            self.assertEqual(data[:8], b"\x89PNG\r\n\x1a\n")
            return struct.unpack(">II", data[16:24]), len(data)
        self.assertEqual(ihdr(self.out / "assets/logo-header.png")[0], (148, 116))
        self.assertLess(ihdr(self.out / "assets/logo-header.png")[1], 40_960)
        self.assertEqual(ihdr(self.out / "assets/favicon.png")[0], (48, 48))
        self.assertLess(ihdr(self.out / "assets/favicon.png")[1], 8_192)
        self.assertEqual(hashlib.sha256((SITE_DIR / "assets/logo.png").read_bytes()).hexdigest(), LOGO_SHA256)

    def test_pages_use_the_header_logo_and_link_one_resolving_favicon(self):
        self.assertNotIn("assets/logo.png", self.files)
        pages = [rel for rel in self.files if rel.endswith(".html")]
        self.assertEqual(sorted(pages), ["404.html", "hike/index.html", "index.html"])
        for rel in pages:
            with self.subTest(page=rel):
                self.assertNotIn("logo.png", self.text[rel])
                self.assertIn("assets/logo-header.png", self.text[rel])
                icons = re.findall(r"<link rel=\"icon\"[^>]*>", self.text[rel])
                self.assertEqual(len(icons), 1)
                href = re.search(r'href="([^"]+)"', icons[0]).group(1)
                target = href.lstrip("/") if href.startswith("/") else (Path(rel).parent / href).as_posix()
                self.assertEqual(target, "assets/favicon.png")
                self.assertIn(target, self.files)

    def test_publish_refuses_a_folder_inside_the_repo_or_one_with_files(self):
        content = load_and_validate()
        with self.assertRaises(ValueError):
            sitegen.publish(content, REPO_ROOT, REPO_ROOT / "storefront-mockup" / "published")
        self.assertFalse((REPO_ROOT / "storefront-mockup" / "published").exists())
        with tempfile.TemporaryDirectory() as tmp:
            (Path(tmp) / "stale.txt").write_text("old")
            with self.assertRaises(OSError):
                sitegen.publish(content, REPO_ROOT, Path(tmp))
            self.assertEqual(sorted(p.name for p in Path(tmp).iterdir()), ["stale.txt"])

    def test_published_club_pages_say_there_is_no_club_service(self):
        # AV-08: the published pages carry the marker that stops community.js asking for /api/community (a 404 per load).
        for rel in sitegen.NO_CLUB_SERVICE_PAGES:
            with self.subTest(page=rel):
                self.assertEqual(self.text[rel].count(sitegen.NO_CLUB_SERVICE_MARKER), 1)
                self.assertLess(self.text[rel].index(sitegen.NO_CLUB_SERVICE_MARKER), self.text[rel].index("</head>"))
                # the working pages the local club service serves never carry it, so the local page still asks
                self.assertNotIn("club-service", (SITE_DIR / rel).read_text("utf-8"))
        self.assertNotIn("club-service", self.text["404.html"])
        self.assertIn('meta[name="club-service"]', self.text["community.js"])
        self.assertIn('content="none"', self.text["community.js"])
        with self.assertRaises(ValueError):
            sitegen._mark_no_club_service("x.html", b"<html><head></head></html>")
        with self.assertRaises(ValueError):
            sitegen._mark_no_club_service("x.html", b'<meta charset="utf-8"><meta charset="utf-8">')

    def test_cli_publish(self):
        with tempfile.TemporaryDirectory() as tmp:
            out = io.StringIO()
            with contextlib.redirect_stdout(out):
                code = sitegen.main(["--publish", str(Path(tmp) / "site")])
            self.assertEqual(code, 0)
            self.assertIn(f"published {len(self.files)} files", out.getvalue())


def _run(*argv):
    out, err = io.StringIO(), io.StringIO()
    with contextlib.redirect_stdout(out), contextlib.redirect_stderr(err):
        code = sitegen.main(list(argv))
    return code, out.getvalue(), err.getvalue()


def _tree(root):
    """{relative path: (kind, bytes or link target, mtime_ns)} for every entry, never following a link or opening a FIFO."""
    snap = {}
    for path in sorted(Path(root).rglob("*")):
        st = path.lstat()
        kind = "link" if path.is_symlink() else "dir" if path.is_dir() else "file" if stat.S_ISREG(st.st_mode) else "special"
        snap[path.relative_to(root).as_posix()] = (kind, os.readlink(path) if kind == "link" else
                                                   path.read_bytes() if kind == "file" else None, st.st_mtime_ns)
    return snap


def _groups(text):
    """{'missing'|'changed'|'extra': [paths]} parsed back from a --check-publish report (JSON-quoted lines)."""
    found, label = {}, None
    for line in text.splitlines():
        head = re.fullmatch(r"(missing|changed|extra) \((\d+)\):", line)
        if head:
            label = head.group(1)
            found[label] = []
        elif line.startswith('  "') and label:
            found[label].append(json.loads(line[2:]))
        else:
            label = None
    return found


class CheckPublish(unittest.TestCase):
    """AV1622-08: ``--check-publish DIR`` compares an existing folder with what --publish would write now, read-only.
    Fixture repo only (copied content and templates; the real working folder linked read-only); no deployed tree."""

    SECRET = b"PRIVATE-NOTE-9917"

    @classmethod
    def setUpClass(cls):
        cls._tmp = tempfile.TemporaryDirectory()
        cls.base_repo = Path(cls._tmp.name).resolve() / "repo"
        cls._fixture_repo(cls.base_repo)
        cls.base = Path(cls._tmp.name).resolve() / "base"
        content = load_and_validate(cls.base_repo / "hass" / "content", cls.base_repo / "storefront-mockup")
        with contextlib.redirect_stdout(io.StringIO()):
            cls.files = sorted(sitegen.publish(content, cls.base_repo, cls.base))

    @classmethod
    def tearDownClass(cls):
        cls._tmp.cleanup()

    @staticmethod
    def _fixture_repo(root):
        shutil.copytree(REPO_ROOT / "hass" / "content", root / "hass" / "content")
        shutil.copytree(REPO_ROOT / "hass" / "templates", root / "hass" / "templates")
        (root / "storefront-mockup").symlink_to(SITE_DIR, target_is_directory=True)

    def setUp(self):
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        self.tmp = Path(tmp.name).resolve()
        self.repo, self.site, self.outside = self.tmp / "repo", self.tmp / "site", self.tmp / "outside"
        self._fixture_repo(self.repo)
        shutil.copytree(self.base, self.site, symlinks=True)
        self.outside.mkdir()
        self.sentinel = self.outside / "sentinel.txt"
        self.sentinel.write_bytes(self.SECRET)
        os.utime(self.sentinel, ns=(1_000_000_000, 1_000_000_000))

    def check(self, target=None, *extra):
        return _run("--check-publish", str(target or self.site), "--repo", str(self.repo), *extra)

    def assertSentinelUntouched(self):
        self.assertEqual((self.sentinel.read_bytes(), self.sentinel.stat().st_mtime_ns), (self.SECRET, 1_000_000_000))

    def assertNoPrivate(self, *texts):
        for text in texts:
            self.assertNotIn(self.SECRET.decode(), text)

    def test_check_publish_exact(self):
        before, parent = _tree(self.site), sorted(p.name for p in self.tmp.iterdir())
        boom = mock.Mock(side_effect=AssertionError("a read-only check must not write"))
        with mock.patch.object(sitegen, "publish", boom), mock.patch.object(sitegen, "write_files", boom), \
                mock.patch.object(sitegen.tempfile, "mkstemp", boom), mock.patch.object(os, "mkdir", boom):
            code, out, err = self.check()
        self.assertEqual((code, err), (0, ""))
        self.assertEqual(out, f"ok: {len(self.files)} published files match current content\n")
        self.assertTrue(_tree(self.site) == before, "the checked folder changed")
        self.assertEqual(sorted(p.name for p in self.tmp.iterdir()), parent)

    def test_check_publish_reports_missing_changed_extra(self):
        (self.site / "style.css").unlink()
        (self.site / "script.js").write_bytes(b"changed")
        (self.site / "private-notes.txt").write_bytes(self.SECRET)
        before = _tree(self.site)
        code, out, err = self.check()
        self.assertEqual(code, 1)
        self.assertEqual(_groups(out), {"missing": ["style.css"], "changed": ["script.js"], "extra": ["private-notes.txt"]})
        self.assertLess(out.index("missing ("), out.index("changed ("))
        self.assertLess(out.index("changed ("), out.index("extra ("))
        self.assertNoPrivate(out, err)
        self.assertTrue(_tree(self.site) == before, "the check repaired or altered the folder")

    def test_check_publish_uses_current_render(self):
        index = self.repo / "hass" / "templates" / "index.html"
        index.write_bytes(index.read_bytes() + b"<!-- edited after publish -->\n")
        code, out, _ = self.check()
        self.assertEqual((code, _groups(out)), (1, {"changed": ["index.html"]}))  # the committed index.html is not the truth
        index.write_bytes((self.base_repo / "hass" / "templates" / "index.html").read_bytes())
        self.assertEqual(self.check()[0], 0)
        store = self.repo / "hass" / "content" / "store.json"
        data = json.loads(store.read_text("utf-8"))
        data["name"] = data["name"] + " Two"
        store.write_text(json.dumps(data, indent=2) + "\n", "utf-8")
        code, out, _ = self.check()
        self.assertEqual(code, 1)
        self.assertIn("index.html", _groups(out)["changed"])

    def test_check_publish_same_day_passes_and_stale_date_fails(self):
        today = shop_today()
        store = self.repo / "hass" / "content" / "store.json"
        data = json.loads(store.read_text("utf-8"))
        data["selection_checked_on"] = today.isoformat()
        store.write_text(json.dumps(data, indent=2) + "\n", "utf-8")
        dated = self.tmp / "dated"
        content = load_and_validate(self.repo / "hass" / "content", self.repo / "storefront-mockup")
        with mock.patch.object(sitegen, "shop_today", return_value=today), contextlib.redirect_stdout(io.StringIO()):
            sitegen.publish(content, self.repo, dated)
            self.assertEqual(self.check(dated)[0], 0)
        with mock.patch.object(sitegen, "shop_today", return_value=today + datetime.timedelta(days=30)):
            code, out, _ = self.check(dated)
        self.assertEqual(code, 1)
        self.assertEqual(_groups(out)["changed"], ["index.html"])

    def test_check_publish_rejects_unsafe_root(self):
        link_repo, link_out, dangling = self.tmp / "link-repo", self.tmp / "link-out", self.tmp / "dangling"
        link_repo.symlink_to(self.repo, target_is_directory=True)
        link_out.symlink_to(self.outside, target_is_directory=True)
        dangling.symlink_to(self.tmp / "nowhere")
        parent = self.tmp / "parent-link"
        parent.symlink_to(self.tmp, target_is_directory=True)
        cases = {"repo root": self.repo, "repo descendant": self.repo / "hass", "missing repo descendant": self.repo / "new",
                 "link to repo": link_repo, "link to external": link_out, "dangling link": dangling,
                 "symlinked ancestor": parent / "site", "file": self.sentinel, "nonexistent": self.tmp / "nowhere"}
        before = sorted(p.as_posix() for p in self.tmp.rglob("*") if "site" not in p.relative_to(self.tmp).parts[:1])
        walker = mock.Mock(side_effect=AssertionError("a refused folder must not be read"))
        for name, target in cases.items():
            with self.subTest(name), mock.patch.object(sitegen, "check_publish", walker):
                code, out, err = self.check(target)
                self.assertEqual((code, out), (2, ""))
                self.assertIn("check-publish refused", err)
        self.assertEqual(sorted(p.as_posix() for p in self.tmp.rglob("*") if "site" not in p.relative_to(self.tmp).parts[:1]), before)
        self.assertSentinelUntouched()

    def test_check_publish_dotdot_is_checked_before_it_is_collapsed(self):
        """The path as given is what is checked: ``link/../site`` and ``missing/../site`` must not fall back to the
        lexically collapsed (and here exact) ``tmp/site``; a ``..`` through real folders stays fine."""
        nested = self.outside / "nested"
        nested.mkdir()
        (self.tmp / "link").symlink_to(nested, target_is_directory=True)
        self.assertEqual(self.check(self.site)[0], 0)  # the collapsed target really is an exact copy
        walker = mock.Mock(side_effect=AssertionError("a refused folder must not be read"))
        for name, target in {"symlink then ..": f"{self.tmp}/link/../site", "missing then ..": f"{self.tmp}/nowhere/../site",
                             "file then ..": f"{self.sentinel}/../site"}.items():
            with self.subTest(name), mock.patch.object(sitegen, "check_publish", walker):
                code, out, err = self.check(target)
                self.assertEqual((code, out), (2, ""))
                self.assertIn("check-publish refused", err)
        self.assertEqual(self.check(f"{self.tmp}/outside/../site")[0], 0)
        self.assertSentinelUntouched()

    def test_check_publish_nested_links_and_special_files(self):
        trails = self.site / "assets" / "trails"
        moved = self.outside / "trails"
        trails.rename(moved)
        trails.symlink_to(moved, target_is_directory=True)
        (self.site / "style.css").unlink()
        (self.site / "style.css").symlink_to(self.sentinel)
        (self.site / "hiking.css").unlink()
        os.mkfifo(self.site / "hiking.css")
        os.mkfifo(self.site / "pipe")
        (self.site / "dangling").symlink_to(self.outside / "nowhere")
        (self.outside / "linked-secret.txt").write_bytes(self.SECRET)
        (self.site / "linkdir").symlink_to(self.outside, target_is_directory=True)
        opened, real_open = [], os.open

        def spy(path, *args, **kwargs):
            opened.append(Path(path).name)
            return real_open(path, *args, **kwargs)
        with mock.patch.object(os, "open", spy):
            code, out, err = self.check()
        self.assertEqual(code, 1)
        self.assertEqual(_groups(out), {"missing": sorted(f for f in self.files if f.startswith("assets/trails/")),
                                        "changed": ["assets/trails", "hiking.css", "style.css"],
                                        "extra": ["dangling", "linkdir", "pipe"]})
        self.assertFalse({"style.css", "hiking.css", "pipe", "dangling", "linkdir", "trails"} & set(opened), opened)
        self.assertNoPrivate(out, err)
        self.assertNotIn("linked-secret", out)
        self.assertSentinelUntouched()

    def test_check_publish_extra_directories(self):
        (self.site / "empty-extra").mkdir()
        hidden = self.site / "assets" / ".private"
        hidden.mkdir()
        (hidden / ".env").write_bytes(self.SECRET)
        (self.site / "bad\nname.txt").write_bytes(self.SECRET)
        code, out, err = self.check()
        self.assertEqual(code, 1)
        self.assertEqual(_groups(out), {"extra": ["assets/.private", "assets/.private/.env", "bad\nname.txt", "empty-extra"]})
        self.assertIn('"bad\\nname.txt"', out)
        self.assertTrue(all(line.startswith(("  \"", "published", "extra")) for line in out.splitlines()), out)
        self.assertNoPrivate(out, err)

    def test_check_publish_read_error_and_race(self):
        real_open, real_scandir = os.open, os.scandir
        script = self.site / "script.js"

        def deny_open(path, *args, **kwargs):
            if Path(path) == script:
                raise PermissionError(errno.EACCES, "Permission denied")
            return real_open(path, *args, **kwargs)

        def swap_open(path, *args, **kwargs):
            if Path(path) == script:
                script.unlink()
                script.symlink_to(self.sentinel)
            return real_open(path, *args, **kwargs)

        def deny_scandir(path="."):
            if Path(path) == self.site / "assets":
                raise PermissionError(errno.EACCES, "Permission denied")
            return real_scandir(path)
        for name, target, fn in (("read denied", "open", deny_open), ("file swapped for a link", "open", swap_open),
                                 ("listing denied", "scandir", deny_scandir)):
            with self.subTest(name), mock.patch.object(os, target, fn):
                code, out, err = self.check()
                self.assertEqual((code, out), (2, ""))
                self.assertIn("check-publish refused", err)
            script.unlink(missing_ok=True)
            shutil.copyfile(self.base / "script.js", script)
        self.assertSentinelUntouched()

    def test_check_publish_cli_exclusive(self):
        for other in (["--check"], ["--write"], ["--out", "x"], ["--publish", "x"]):
            with self.subTest(other=other), contextlib.redirect_stderr(io.StringIO()) as err:
                with self.assertRaises(SystemExit) as raised:
                    sitegen.main(["--check-publish", str(self.site), *other])
                self.assertEqual(raised.exception.code, 2)
                self.assertIn("not allowed with argument", err.getvalue())
        with contextlib.redirect_stderr(io.StringIO()), self.assertRaises(SystemExit) as raised:
            sitegen.main(["--check-publish"])
        self.assertEqual(raised.exception.code, 2)
        self.assertEqual(self.check()[0], 0)  # --repo honored: the fixture repo, not the checkout, is compared
        self.assertEqual(_run("--check-publish", str(self.site))[0], 0)  # and the checkout renders the same site


if __name__ == "__main__":
    unittest.main()
