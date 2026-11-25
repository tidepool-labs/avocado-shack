"""L6: what a visitor is actually served for a listing, compared with the version the owner approved.

The journey tests read the repo files. A visitor does not: the browser asks the web server for the Market page, the
catalog script and the item photo. This module serves the writer worktree's site folder on a loopback port, fetches
those three things over HTTP, and compares them with the approved draft across publish, edit and take-down. A stale
photo on the served page fails even when the catalog record is right, and the other way round. Fixtures only: a throwaway
repo, 127.0.0.1, no Clover, no live site, no browser.
"""

import functools
import hashlib
import http.server
import json
import threading
import unittest
import urllib.error
import urllib.request

from hass.tests import test_npp_undo_journey as journey
from hass.tests.test_conversation import CHAT, OWNER

PUBLIC_KEYS = {"id", "name", "brand", "category", "image", "description", "producerKey", "displayBrand",
               "imageAlt", "sellingPrice", "addedOn"}
PRIVATE_WORDS = ("cost", "qty", "quantity", "stock", "count", "margin", "wholesale", "supplier")
SHOWN = ("name", "description", "sellingPrice", "imageAlt")
CATALOG_URL, MARKET_URL = "/catalog-products.js", "/index.html"


def sha(data):
    return hashlib.sha256(data).hexdigest()


class Site:
    """A loopback web server over one site folder. `stale` maps a URL path to the bytes a stale cache would serve."""

    def __init__(self, root):
        self.stale = {}
        site = self

        class Handler(http.server.SimpleHTTPRequestHandler):
            def log_message(self, *args, **kwargs):
                pass

            def do_GET(self):
                path = self.path.split("?", 1)[0]
                if path in site.stale:
                    body = site.stale[path]
                    self.send_response(200)
                    self.send_header("Content-Length", str(len(body)))
                    self.end_headers()
                    self.wfile.write(body)
                    return
                super().do_GET()

        self.server = http.server.ThreadingHTTPServer(("127.0.0.1", 0), functools.partial(Handler, directory=str(root)))
        self.thread = threading.Thread(target=self.server.serve_forever, daemon=True)
        self.thread.start()
        self.base = f"http://127.0.0.1:{self.server.server_address[1]}"

    def close(self):
        self.server.shutdown()
        self.server.server_close()
        self.thread.join(5)

    def get(self, path):
        try:
            with urllib.request.urlopen(self.base + path, timeout=10) as response:
                return response.read()
        except urllib.error.HTTPError as err:
            if err.code == 404:
                return None
            raise


def served_card(site, pid):
    """What a visitor gets for item `pid`: (record or None, photo SHA-256 or None, catalog bytes, problems about the page)."""
    problems = []
    page = site.get(MARKET_URL)
    if page is None or b"catalog-products.js" not in page:
        problems.append("the served Market page does not load the catalog script")
    script = site.get(CATALOG_URL)
    if script is None:
        return None, None, b"", problems + ["the catalog script is not served"]
    records = json.loads(script.split(b"\n", 1)[0][len(b"const catalog="):].rstrip(b";"))
    record = next((p for p in records if p["id"] == pid), None)
    if record is None:
        return None, None, script, problems
    photo = site.get("/" + record["image"])
    return record, (sha(photo) if photo is not None else None), script, problems


def mismatches(approved, served):
    """Every way the served card differs from the approved version. Empty means a visitor sees what was approved."""
    record, photo, script, problems = served
    out = list(problems)
    if record is None:
        return out + ["the card is not on the served page"]
    for key in SHOWN:
        if record.get(key) != approved[key]:
            out.append(f"served {key} is not the approved one")
    if photo is None:
        out.append("the photo is not served")
    elif photo != approved["photo_sha256"]:
        out.append("the served photo is not the approved photo")
    if not set(record) <= PUBLIC_KEYS:
        out.append("the served record has a non-public field")
    lowered = json.dumps(record).lower()
    out.extend(f"the served record mentions {word}" for word in PRIVATE_WORDS if f'"{word}' in lowered)
    out.extend(f"the served catalog carries {secret_name}" for secret_name, secret in (("a chat id", CHAT), ("a sender id", OWNER))
               if secret.encode() in script)
    return out


class HiddenListingServedProjectionTests(journey.NppUndoJourneyTests):
    def setUp(self):
        super().setUp()
        self.shown, show = {}, self.engine.show

        def spy(change_id, *args, **kw):
            out = show(change_id, *args, **kw)
            if "draft" in out:
                self.shown[change_id] = out["draft"]
            return out
        self.engine.show = spy
        self.web = Site(self.repo.wt / "storefront-mockup")
        self.addCleanup(self.web.close)

    def approved_card(self):
        """The version the owner approved, taken from the approved draft and its photo digest (not from the site)."""
        draft = self.shown[self.change]
        add = next(op["args"] for op in draft["ops"] if op["op"] == "product.add")
        (_path, digest), = draft["assets"].items()
        return {**{key: add[key] for key in SHOWN}, "photo_sha256": digest.removeprefix("sha256:")}

    def served(self):
        return served_card(self.web, self.pid)

    def apply(self, *ops):
        out = self.engine.prepare(list(ops))
        self.assertEqual(out["result"], "ok", out)
        draft = out["draft"]
        self.assertEqual(self.engine.apply(draft["change_id"], draft["draft_hash"])["result"], "applied")
        return draft

    def test_s1_served_card_is_the_approved_card_through_edit_and_takedown(self):
        self.publish()
        approved = self.approved_card()
        self.assertEqual(mismatches(approved, self.served()), [])
        self.assertEqual(approved["sellingPrice"], journey.PRICE)

        draft = self.apply({"op": "product.edit", "args": {"id": self.pid, "description": "Quince jelly, edited."}})
        edit = next(op["args"] for op in draft["ops"] if op["op"] == "product.edit")
        edited = dict(approved, description=edit["description"])
        self.assertNotEqual(mismatches(approved, self.served()), [])  # the old approval no longer describes the page
        self.assertEqual(mismatches(edited, self.served()), [])  # the edit changed the descriptor, nothing else

        self.apply({"op": "product.hide", "args": {"id": self.pid}})
        record, _photo, script, problems = self.served()
        self.assertEqual((record, problems), (None, []))
        self.assertEqual(script, self.base_site[0])  # the served catalog is the pre-publication one
        self.assertEqual(mismatches(edited, self.served()), ["the card is not on the served page"])

    def test_s2_chat_undo_takes_the_served_card_down_in_one_yes(self):
        self.publish()
        self.assertEqual(mismatches(self.approved_card(), self.served()), [])
        self.draft_hide()
        self.assertEqual(mismatches(self.approved_card(), self.served()), [])  # undo alone changes nothing a visitor sees
        self.confirm_hide()
        self.assertIsNone(self.served()[0])

    def test_s3_a_stale_photo_fails_even_when_the_catalog_is_right(self):
        self.publish()
        approved = self.approved_card()
        record = self.served()[0]
        self.web.stale["/" + record["image"]] = b"an older photo a cache still holds"
        self.assertEqual(mismatches(approved, self.served()), ["the served photo is not the approved photo"])
        self.web.stale.clear()
        self.assertEqual(mismatches(approved, self.served()), [])

    def test_s4_a_stale_catalog_fails_even_when_the_photo_is_right(self):
        self.publish()
        approved = self.approved_card()
        self.web.stale[CATALOG_URL] = self.base_site[0]  # the page still serves the catalog from before publication
        self.assertEqual(mismatches(approved, self.served()), ["the card is not on the served page"])
        self.web.stale.clear()
        self.apply({"op": "product.edit", "args": {"id": self.pid, "description": "Quince jelly, edited."}})
        edited_catalog = self.repo.read(journey.CATALOG)
        self.apply({"op": "product.edit", "args": {"id": self.pid, "description": "Quince jelly."}})
        self.web.stale[CATALOG_URL] = edited_catalog  # right photo, but a catalog from a different version
        self.assertEqual(mismatches(approved, self.served()), ["served description is not the approved one"])

    def test_s5_a_missing_photo_or_private_field_or_missing_script_fails(self):
        self.publish()
        approved = self.approved_card()
        record, _photo, script, _problems = self.served()
        self.web.stale["/" + record["image"]] = b""
        self.assertEqual(mismatches(approved, self.served()), ["the served photo is not the approved photo"])
        self.web.stale.clear()
        leaked = dict(record, costPrice="1.00")
        self.web.stale[CATALOG_URL] = script.replace(json.dumps(record).encode(), json.dumps(leaked).encode())
        self.assertNotEqual(script, self.web.stale[CATALOG_URL])  # the tamper really changed the served bytes
        found = mismatches(approved, self.served())
        self.assertIn("the served record has a non-public field", found)
        self.assertIn("the served record mentions cost", found)
        self.web.stale.clear()
        self.web.stale[MARKET_URL] = b"<html>no script here</html>"
        self.assertEqual(mismatches(approved, self.served()), ["the served Market page does not load the catalog script"])

    def test_s6_a_chat_id_in_the_served_catalog_fails(self):
        self.publish()
        approved = self.approved_card()
        script = self.served()[2]
        self.web.stale[CATALOG_URL] = script + b"\n// " + CHAT.encode()
        self.assertEqual(mismatches(approved, self.served()), ["the served catalog carries a chat id"])


# Run only this module's own journeys, not the inherited HRM-04 ones (those have their own module).
for _name in dir(journey.NppUndoJourneyTests):
    if _name.startswith("test_c"):
        setattr(HiddenListingServedProjectionTests, _name, None)


if __name__ == "__main__":
    unittest.main()
