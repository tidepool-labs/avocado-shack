"""Fixture-only CLI contracts for the static publish source inventory."""

from contextlib import redirect_stderr, redirect_stdout
import importlib.util
from io import StringIO
import json
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest

from hass import sitegen


SCRIPT = Path(__file__).resolve().parents[2] / "scripts/hass/publish_sources_check.py"
SPEC = importlib.util.spec_from_file_location("publish_sources_check", SCRIPT)
assert SPEC is not None and SPEC.loader is not None
checker = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(checker)

IMAGE = "assets/products/sample-fruit.webp"
HOME_IMAGE = "assets/products/photo-0123456789abcdef.jpg"
HELD_IMAGE = "assets/products/held-fruit.webp"
PRODUCT_NAME = "Synthetic Orchard Canary"
STORE_NAME = "Synthetic Store Canary"
STATIC_COUNT = len(sitegen.PUBLISH_STATIC + sitegen.PUBLISH_ASSETS + sitegen.PUBLISH_PAGES)


class PublishSourcesCheckTests(unittest.TestCase):
    def setUp(self):
        temp = tempfile.TemporaryDirectory()
        self.addCleanup(temp.cleanup)
        self.root = Path(temp.name).resolve()
        self.repo = self.root / "checkout-path-canary"
        self.content = self.repo / "hass/content"
        self.site = self.repo / "storefront-mockup"

    def fixture(self, *, missing=(), directories=(), links=None, home=False, held=False):
        product: dict[str, object] = {
            "id": "sample-fruit", "name": PRODUCT_NAME, "producerKey": "sample-maker",
            "brand": "Sample Maker", "displayBrand": "Sample Maker", "category": "fruit",
            "image": IMAGE, "description": "A fixture fruit.", "status": "active",
        }
        products = [product]
        if held:
            products.append({
                **product, "id": "held-fruit", "name": "Held fixture fruit",
                "image": HELD_IMAGE, "status": "held", "hold": {
                    "reason": "Fixture review", "source": "https://example.com/",
                    "evidence": "Fixture evidence", "record": "Fixture record",
                },
            })
        store = {
            "name": STORE_NAME, "streetAddress": "Example Street", "town": "Testville",
            "hours": ["Monday-Friday 9am-5pm", "Closed Saturday-Sunday"],
        }
        if home:
            store["homeImage"] = {"image": HOME_IMAGE, "imageAlt": "Fixture orchard"}
        documents = {
            "products": {"products": products},
            "makers": {"makers": {"sample-maker": {
                "name": "Sample Maker", "place": "Testville, California", "story": "A fixture maker.",
            }}},
            "store": store,
            "community": {"club": {
                "clubName": "Fixture Club", "organizer": "Fixture Organizer",
                "intendedSender": "club@example.invalid", "emailConnected": False,
            }, "events": [], "routeIdeas": []},
        }
        self.content.mkdir(parents=True)
        for name, doc in documents.items():
            (self.content / f"{name}.json").write_text(json.dumps({"schemaVersion": 1, **doc}), encoding="utf-8")

        sources = [f"storefront-mockup/{name}" for name in (*sitegen.PUBLISH_STATIC, *sitegen.PUBLISH_ASSETS, IMAGE)]
        sources += [f"hass/templates/{name}" for name in sitegen.PUBLISH_PAGES]
        if home:
            sources.append(f"storefront-mockup/{HOME_IMAGE}")
        links = links or {}
        for rel in sources:
            if rel in missing or any(rel == link or rel.startswith(link + "/") for link in links):
                continue
            path = self.repo / rel
            path.parent.mkdir(parents=True, exist_ok=True)
            if rel in directories:
                path.mkdir()
            else:
                path.touch()
        for rel, target in links.items():
            path = self.repo / rel
            path.parent.mkdir(parents=True, exist_ok=True)
            path.symlink_to(target)

    def invoke(self, *args):
        return subprocess.run([sys.executable, "-B", str(SCRIPT), *args], cwd=self.root,
                              capture_output=True, text=True, timeout=10)

    def run_check(self, code, last_line, *args):
        result = self.invoke(*(args or ("--repo", str(self.repo))))
        self.assertEqual(result.returncode, code, result.stdout + result.stderr)
        self.assertEqual(result.stderr, "")
        lines = result.stdout.splitlines()
        self.assertEqual(lines[-1:], [last_line])
        return lines

    def test_c1_full_pass(self):
        # A successful scan must count the optional homepage image as well as the active image.
        self.fixture(home=True)
        lines = self.run_check(0, "PASS publish_sources_check")
        self.assertEqual(lines, [f"expected {STATIC_COUNT + 2}", "note unlisted-top-level 0",
                                 "PASS publish_sources_check"])

    def test_c2_1_unsafe_input(self):
        # Following a repo symlink would turn this valid checkout into a false pass.
        self.fixture()
        link = self.root / "linked-checkout"
        link.symlink_to(self.repo, target_is_directory=True)
        for unsafe in (str(link) + "/", str(self.content / "store.json"), str(self.root / "absent")):
            with self.subTest(unsafe=unsafe):
                lines = self.run_check(1, "FAIL publish_sources_check", "--repo", unsafe)
                self.assertEqual(lines, ["FAIL unsafe-input", "FAIL publish_sources_check"])

    def test_c2_2_content_invalid(self):
        # Malformed JSON and undecodable bytes both need a fixed reason, not a traceback.
        self.fixture()
        for raw in (b"{", b"\xff"):
            with self.subTest(raw=raw):
                (self.content / "products.json").write_bytes(raw)
                lines = self.run_check(1, "FAIL publish_sources_check")
                self.assertEqual(lines, ["FAIL content-invalid", "FAIL publish_sources_check"])

    def test_c2_3_source_missing(self):
        # An exists() check would accept this directory in place of a regular file.
        rel = f"storefront-mockup/{IMAGE}"
        self.fixture(directories={rel})
        lines = self.run_check(1, "FAIL publish_sources_check")
        self.assertEqual(lines, [f"expected {STATIC_COUNT + 1}", f"missing {rel}",
                                 "note unlisted-top-level 0", "FAIL source-missing 1", "FAIL publish_sources_check"])

    def test_c2_4_source_symlink(self):
        # A leaf-only check misses the linked template directory; is_file alone follows links.
        pages = self.root / "other-templates"
        pages.mkdir()
        for name in sitegen.PUBLISH_PAGES:
            (pages / name).touch()
        rel = f"storefront-mockup/{IMAGE}"
        self.fixture(links={rel: self.root / "dangling", "hass/templates": pages})
        lines = self.run_check(1, "FAIL publish_sources_check")
        self.assertEqual(lines, [f"expected {STATIC_COUNT + 1}",
                                 *(f"symlink hass/templates/{name}" for name in sorted(sitegen.PUBLISH_PAGES)),
                                 f"symlink {rel}", "note unlisted-top-level 0",
                                 f"FAIL source-symlink {len(sitegen.PUBLISH_PAGES) + 1}", "FAIL publish_sources_check"])

    def test_c3_usage_exit_2(self):
        # Usage errors are not source findings and must leave stdout empty.
        for args in ((), ("--repo",), ("--repo", str(self.repo), "--unknown")):
            with self.subTest(args=args):
                result = self.invoke(*args)
                self.assertEqual(result.returncode, 2)
                self.assertEqual(result.stdout, "")
                self.assertEqual(result.stderr.splitlines()[-1], "publish_sources_check.py: error: invalid arguments")

    def test_c4_read_only(self):
        # Rewriting identical bytes or creating an empty output folder must still fail this check.
        self.fixture()

        def snapshot():
            return {path: (path.stat().st_mtime_ns, path.read_bytes() if path.is_file() else None)
                    for path in (self.repo, *self.repo.rglob("*"))}

        before = snapshot()
        self.run_check(0, "PASS publish_sources_check")
        self.assertEqual(snapshot(), before)

    def test_c5_no_private_values(self):
        # Dumping loaded content, printing absolute source paths, or echoing bad argv leaks canaries.
        self.fixture(missing={f"storefront-mockup/{IMAGE}"})
        checked = self.invoke("--repo", str(self.repo))
        usage = self.invoke("--repo", str(self.repo), str(self.repo))
        self.assertEqual(checked.returncode, 1)
        self.assertEqual(checked.stdout.splitlines()[-1], "FAIL publish_sources_check")
        self.assertEqual(usage.returncode, 2)
        self.assertEqual(usage.stdout, "")
        for canary in (PRODUCT_NAME, STORE_NAME, str(self.repo)):
            for result in (checked, usage):
                self.assertNotIn(canary, result.stdout + result.stderr)

    def test_c6_held_picture_not_expected(self):
        # Traversing all products instead of active products would report the uncreated held image.
        self.fixture(held=True)
        stdout, stderr = StringIO(), StringIO()
        with redirect_stdout(stdout), redirect_stderr(stderr):
            self.assertEqual(checker.main(["--repo", str(self.repo)]), 0)
        self.assertEqual(stderr.getvalue(), "")
        self.assertEqual(stdout.getvalue().splitlines(), [
            f"expected {STATIC_COUNT + 1}", "note unlisted-top-level 0", "PASS publish_sources_check",
        ])

    def test_c7_unlisted_informational(self):
        # Counting symlinks, generated names or nested files would inflate the advisory count.
        self.fixture()
        extra = self.site / "extra.txt"
        extra.touch()
        (self.site / "link.txt").symlink_to(extra)
        for name in (*sitegen.PUBLISH_GENERATED, *sitegen.PUBLISH_PAGES, "community.json", "producers.json"):
            path = self.site / name
            path.parent.mkdir(parents=True, exist_ok=True)
            path.touch()
        lines = self.run_check(0, "PASS publish_sources_check")
        self.assertEqual(lines, [f"expected {STATIC_COUNT + 1}", "note unlisted-top-level 1",
                                 "PASS publish_sources_check"])

    def test_c8_all_missing_listed(self):
        # Stopping at the first source, omitting the home image, or suppressing a second finding fails here.
        missing = ["hass/templates/404.html", f"storefront-mockup/{HOME_IMAGE}", "storefront-mockup/style.css"]
        linked = f"storefront-mockup/{IMAGE}"
        self.fixture(home=True, missing=missing, links={linked: self.root / "dangling"})
        lines = self.run_check(1, "FAIL publish_sources_check")
        self.assertEqual(lines, [f"expected {STATIC_COUNT + 2}", *(f"missing {rel}" for rel in missing),
                                 f"symlink {linked}", "note unlisted-top-level 0", "FAIL source-missing 3",
                                 "FAIL source-symlink 1", "FAIL publish_sources_check"])
