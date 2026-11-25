"""HCI-08: the one preview message that names the exact till change. Offline: fake till values only, sockets patched.
Run: python3 -B -m unittest hass.tests.test_clover_inventory_preview -v
"""
import re
from dataclasses import replace
from decimal import Decimal

from hass import voice
from hass.clover import config, drafts, mapper
from hass.clover import inventory_preview as preview
from hass.tests.test_clover_client import NoNetwork

NAME = "Blue mug"
CODE = "1a2b3c4d"
CFG = config.CloverConfig("sandbox", "FAKEMERCH0001", "", category_map={"pantry": "Pantry"})
CATS = (("FAKECAT000001", "Pantry"),)
SITE = {"id": "blue-mug", "name": NAME, "sellingPrice": "14.00 each", "status": "active", "available": "yes"}
LAST = f"Reply yes {CODE} to do this, or no {CODE} to drop it. Nothing changes until you say yes."
SKU = "AS-PAN-BLUE-MUG-01"
ASKS = ("which-product", "price", "count-conflict", "price-mismatch", "not-live", "hidden")


def created(price="14.00", quantity="30", name=NAME):
    return drafts.build_create_counted(name, price, "pantry", quantity, [], CFG, categories=CATS)


def counted(before, after, availability="no"):
    item = mapper.CloverItem("FAKEITEM00001", NAME, SKU, "", 1400, "FIXED", "", ("Pantry",), (), Decimal(before), 1, False, True, 1)
    site = mapper.parse_site_product({**SITE, "available": availability})
    return drafts.build_set_stock(item, after, CFG, site_product=site)


def plain(text):
    return voice.plain(text).split("\n")


class PreviewTests(NoNetwork):
    def test_c1_layout(self):
        # C1: the order and wording of the preview are what Mike reads before one yes; a field dropped, reordered or a second
        # yes line added would let a change be approved without being seen.
        cases = {
            "match": (SITE, {"sku": SKU}, f'Website: matches "{NAME}" at $14.00 each', f'Link: "{NAME}" on the website is tied to SKU {SKU}'),
            "new link": (SITE, {"sku": SKU, "new": True}, f'Website: matches "{NAME}" at $14.00 each',
                         f'Link: "{NAME}" on the website will be tied to SKU {SKU}'),
            "no website product": (None, None, "Website: no matching product, so nothing changes there",
                                   f'Link: "{NAME}" on the website is not tied to a till item'),
            "other price": ({**SITE, "sellingPrice": "15.00 each"}, {"sku": "AS-PAN-OTHER-01"},
                            f'Website: "{NAME}" is there, but its price is not $14.00 each',
                            f'Link: "{NAME}" on the website is tied to SKU AS-PAN-OTHER-01, not SKU {SKU}'),
            "no price": ({**SITE, "sellingPrice": None}, {}, f'Website: "{NAME}" is there, but I cannot read its price',
                         f'Link: "{NAME}" on the website is not tied to a till item'),
        }
        for label, (site, link, website, link_line) in cases.items():
            with self.subTest(label):
                self.assertEqual(plain(preview.render(created(), site, link, CODE)), [
                    "Add Blue mug to the till with 30 in stock?", "  Item: Blue mug",
                    f"  SKU: {SKU} (made up by me, the next free number)", "  Price: $14.00 each", "  Category: Pantry",
                    "  Count: not in the till yet -> 30", "  On the register: showing", website, link_line, LAST])
        weighed = plain(preview.render(created("8.00 per lb", "2.375"), {**SITE, "sellingPrice": "8.00 per lb"}, {"sku": SKU}, CODE))
        self.assertEqual((weighed[0], weighed[3], weighed[7]), ("Add Blue mug to the till with 2.375 in stock?", "  Price: $8.00 per lb",
                                                                f'Website: matches "{NAME}" at $8.00 per lb'))
        change = plain(preview.render(counted(0, 30), SITE, {"sku": SKU}, CODE))   # sold out on the site: 30 brings the word back
        self.assertEqual(change, ["Set the till count of Blue mug?", "  Item: Blue mug", f"  SKU: {SKU}", "  Count: 0 -> 30",
                                  f'Website: marks "{NAME}" as Available today', f'Link: "{NAME}" on the website is tied to SKU {SKU}', LAST])
        self.assertEqual(plain(preview.render(counted(12, 30, "yes"), SITE, None, CODE))[4], f'Website: no change to "{NAME}"')
        for bad in (drafts.build_create_item(NAME, 1400, "pantry", [], CFG), drafts.build_set_price(
                mapper.CloverItem("FAKEITEM00001", NAME, SKU, "", 1400, "FIXED", "", (), (), None, 1, False, True, 1), 1500, CFG)):
            with self.subTest(kind=bad.kind), self.assertRaises(ValueError):   # a draft with no count to show has no till preview
                preview.render(bad, SITE, None, CODE)
        for code in ("", "yes", "1A2B3C4D", "1a2b3c4", None):
            with self.subTest(code=code), self.assertRaises(ValueError):   # a code Mike could not type back is no preview
                preview.render(created(), SITE, None, code)

    def test_c2_only_exact_values(self):
        # C2: the yes writes the draft's `after` values and nothing else; showing a cost, tax or barcode line the draft carried, or a
        # rounded/other number, would name a change that is not the one written. A yes before the last line could be read as the answer.
        for draft, expected in ((created(), {"14.00", "30"}), (created("8.00 per lb", "2.375"), {"8.00", "2.375"})):
            with self.subTest(after=draft.after):
                lines = plain(preview.render(draft, SITE, {"sku": SKU}, CODE))
                body = [line for line in lines[:-1] if not line.lstrip().startswith(("SKU:", "Link:"))]
                shown = set(re.findall(r"\d+(?:\.\d+)?", "\n".join(body)))
                self.assertEqual(shown, expected)
                self.assertEqual(shown, {f"{draft.after['price'] / 100:.2f}", draft.after["stock"]})
        poisoned = replace(created(), lines=created().lines + ("  Cost: $9.00", "  Tax: 8.5%", "  Barcode: 012345678905", "  Code: 012345678905"))
        for draft in (poisoned, counted(0, 30)):
            with self.subTest(kind=draft.kind):
                text = voice.plain(preview.render(draft, SITE, {"sku": SKU}, CODE))
                self.assertNotRegex(text, r"(?i)cost|tax|barcode|9\.00|8\.5|0123456|token|bearer")
                self.assertEqual(sum("yes" in line.lower() for line in text.split("\n")), 1)
                self.assertTrue(text.endswith(LAST))
        for label in ("Yes mug", "Mug 012345678905", "x" * 40, "Bearer mug"):   # a name that reads as an answer, a barcode or a token fails closed
            with self.subTest(name=label), self.assertRaises(ValueError):
                preview.render(replace(created(), label=label), SITE, None, CODE)

    def test_c3_questions(self):
        # C3: a question is not a request for approval; a code or a yes line on it would let one yes approve a change that was never
        # shown, and an ask that names no product or runs on past one line is not a plain question.
        for kind in ASKS:
            for names in ((), (NAME,), (NAME, "Blue mug large")):
                with self.subTest(kind=kind, names=names):
                    text = preview.render_ask(kind, names)
                    self.assertEqual(len(plain(text)), 1)
                    self.assertTrue(text.endswith("?"))
                    self.assertNotRegex(text, r"(?i)\byes\b|[0-9a-f]{8}")
                    self.assertEqual(voice.check(text), [])
                    if names and kind != "which-product" or len(names) > 1:
                        self.assertIn(voice.quote(names[0]), text)
        self.assertIn(voice.quote("Blue mug large"), preview.render_ask("which-product", (NAME, "Blue mug large")))
        self.assertEqual(preview.render_ask("hidden"), preview.render_ask("hidden", ()))
        for kind in ("", "yes", "unknown", None):
            with self.subTest(kind=kind), self.assertRaises(ValueError):
                preview.render_ask(kind, (NAME,))

    def test_c4_voice(self):
        # C4: these messages go through the outbox voice check; a SKU, arrow or code left unmarked, an unquoted name, a long line or
        # a text that changes between two renders of one draft would be blocked or would make the hash HCI-09 binds unstable.
        for label, draft in (("create", created()), ("weighed", created("8.00 per lb", "2.375")), ("count", counted(12, 30, "yes"))):
            with self.subTest(label):
                text = preview.render(draft, SITE, {"sku": SKU}, CODE)
                self.assertEqual(voice.check(text), [])
                self.assertEqual(voice.check(text, ids_ok=False), [])
                lines = plain(text)
                self.assertLessEqual(len(lines), 12)
                self.assertLessEqual(max(map(len, lines)), 160)
                self.assertIn(voice.quote(NAME), text)
                self.assertEqual(text, preview.render(draft, SITE, {"sku": SKU}, CODE))
                self.assertEqual(text, preview.render(replace(draft), dict(SITE), dict(sku=SKU), CODE))
        text = preview.render(created(), SITE, {"sku": SKU}, CODE)
        self.assertIn(voice.quote(" -> "), text)
        self.assertIn(voice.quote(f"yes {CODE}"), text)
        self.assertEqual(preview.render_ask("price", (NAME,)), preview.render_ask("price", (NAME,)))
        long_label = "x " * 80
        with self.assertRaises(ValueError):   # a line past 160 characters is refused, not cut
            preview.render(replace(created(), label=long_label), SITE, None, CODE)
