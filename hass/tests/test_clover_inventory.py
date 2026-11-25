"""Offline contracts for hass.clover.inventory.plan: one exact till change, or one question. Fake till and made-up values only."""
import ast
import copy
import inspect
from dataclasses import replace
from decimal import Decimal
from unittest import mock

from hass.clover import drafts, inventory, mapper
from hass.clover.client import CloverClient
from hass.clover.config import CloverConfig
from hass.clover.credential import Token
from hass.clover.qty_words import CountIntent
from hass.tests.clover_fake import FakeClover
from hass.tests.test_clover_client import FAKE_TOKEN, NoNetwork

MERCHANT = "FAKEMERCH0001"
CFG = CloverConfig("sandbox", MERCHANT, "", category_map={"pantry": "Pantry"})
CATS_RAW = [{"id": "FAKECAT000001", "name": "Pantry"}]
MUG, POT = "FAKEITEM00001", "FAKEITEM00002"
MUG_SKU = "AS-PAN-BLUE-MUG-01"


def prod(pid, name, price="14.35 each", status="active", available=None, category="pantry"):
    rec = {"id": pid, "name": name, "category": category, "status": status}
    if price is not None:
        rec["sellingPrice"] = price
    if available:
        rec["available"] = available
    return rec


def raw(item_id, name, sku, price=1435, stock=None, hidden=False, unit=None):
    item = {"id": item_id, "name": name, "sku": sku, "price": price, "hidden": hidden, "modifiedTime": 5,
            "priceType": "PER_UNIT" if unit else "FIXED", "categories": {"elements": []}}
    if unit:
        item["unitName"] = unit
    if stock is not None:
        item["itemStock"] = {"quantity": stock, "modifiedTime": 6}
    return item


def read_till(*items):
    """The till as the planner will see it: read through the real client over the HCI-01 fake, parsed by the real mapper."""
    client = CloverClient(MERCHANT, Token(FAKE_TOKEN), FakeClover(MERCHANT, items, CATS_RAW), min_interval=0, max_retries=0)
    parsed, skipped = mapper.parse_items(client.list_items())
    assert skipped == 0
    return parsed, [(c["id"], c["name"]) for c in client.list_categories()]


def say(query, qty=37, mode="count", unit=None):
    return CountIntent(mode, Decimal(qty), unit, query)


def link_of(item_id=MUG, sku=MUG_SKU):
    return {"cloverId": item_id, "sku": sku}


class PlanCase(NoNetwork):
    def plan(self, intent, products, items=(), links=None, config=CFG, **kw):
        till, cats = read_till(*items)
        return inventory.plan(intent, products, links or {}, till, cats, config, **kw)

    def only_writes(self, change, *paths):
        self.assertEqual([(r["method"], r["path"]) for r in change.draft.requests], list(paths))   # never a DELETE, never a price POST


class FindProductTests(PlanCase):
    def test_c1_find_product(self):
        # C1: a product is found by its whole name (exact norm_name, else one plural fold) among ACTIVE products only.
        # Bug caught: substring or word-overlap matching, a fold that outvotes an exact name, or a held product being counted.
        mug, lime, box, pea, peas, held = (prod("p-mug", "Blue mug"), prod("p-lime", "Limes"), prod("p-box", "Box"),
                                           prod("p-pea", "Pea"), prod("p-peas", "Peas"), prod("p-held", "Held tea", status="held"))
        products = [mug, lime, box, pea, peas, held, {"id": 7, "name": "bad record"}, "junk"]
        find = lambda q: inventory.find_product(q, products)
        for said in ("blue mug", "Blue  MUG", "blue mugs", "BLUE MUGS"):
            self.assertIs(find(said), mug, said)
        self.assertIs(find("lime"), lime)
        self.assertIs(find("limes"), lime)
        self.assertIs(find("boxes"), box)
        self.assertIs(find("pea"), pea)      # exact beats the fold
        self.assertIs(find("peas"), peas)
        for said in ("mug", "blue", "blue mug large", "tea", "", "   "):   # partial words, a held product and nothing are not matches
            with self.subTest(said=said):
                self.assertIsInstance(find(said), inventory.Ask)
        self.assertEqual(find("mug"), inventory.Ask("which-product"))
        twins = [prod("p-a", "Red mug"), prod("p-b", "Red mug"), prod("p-c", "Cup")]
        self.assertEqual(inventory.find_product("red mugs", twins), inventory.Ask("which-product", ("Red mug", "Red mug")))
        # plan() returns the same question, and never builds a draft for it
        self.assertEqual(self.plan(say("red mugs"), twins), inventory.Ask("which-product", ("Red mug", "Red mug")))
        self.assertEqual(self.plan(say("zebra"), twins), inventory.Ask("which-product"))
        self.assertEqual(inventory.KINDS, ("which-product", "price", "count-conflict", "price-mismatch", "not-live", "hidden"))


class NewItemTests(PlanCase):
    def test_c2_new_item(self):
        # C2: no link and no till item of that name -> the real build_create_counted draft plus link {product_id, sku}.
        # Bug caught: a create that drops the count, uses another price/category, or links a made-up SKU instead of the draft's.
        products = [prod("p-mug", "Blue mug", available="no")]
        other = raw(POT, "Teal pot", "AS-PAN-TEAL-POT-01", 900, stock=3)
        till, cats = read_till(other)
        change = inventory.plan(say("blue mugs"), products, {}, till, cats, CFG)
        want = drafts.build_create_counted("Blue mug", "14.35 each", "pantry", Decimal(37), till, CFG, categories=cats)
        self.assertIsInstance(change, inventory.Change)
        self.assertEqual(change.draft.draft_hash, want.draft_hash)
        self.assertEqual((change.draft.kind, change.draft.after["stock"], change.draft.after["price"]), ("create_item", "37", 1435))
        self.assertEqual(change.link, {"product_id": "p-mug", "sku": want.after["sku"]})
        self.assertEqual(want.after["sku"], MUG_SKU)
        self.assertEqual(change.site_word, "yes")   # the site said Sold out and the new count is above 0
        self.only_writes(change, ("POST", "/items"), ("POST", "/category_items"), ("PUT", "/item_stocks/{newItemId}"))
        # the same product with the site already agreeing needs no site word; a received sentence on a new item still starts at that number
        agreed = self.plan(say("blue mug", mode="add"), [prod("p-mug", "Blue mug", available="yes")], [other])
        self.assertEqual((agreed.draft.after["stock"], agreed.site_word), ("37", None))
        # a weighed product is created per lb, and the unit Mike says has to be its unit
        pears = [prod("p-pear", "Pears", price="8.00 per lb", category="fruit")]
        weighed = self.plan(say("pears", qty="2.5", unit="lb"), pears)
        self.assertEqual((weighed.draft.requests[0]["json"]["priceType"], weighed.draft.requests[0]["json"]["unitName"]), ("PER_UNIT", "lb"))
        for intent, products_ in ((say("pears"), pears), (say("blue mug", unit="lb"), products)):
            with self.subTest(intent=intent), self.assertRaisesRegex(drafts.DraftRefused, "cannot take that count"):
                self.plan(intent, products_)

    def test_c2_no_price_asks(self):
        # C2: a website product with no readable sellingPrice cannot be copied to the till. Bug caught: creating at $0 or with a guessed price.
        for price in (None, "", "free", 14, "14.5", "$14.00"):
            with self.subTest(price=price):
                self.assertEqual(self.plan(say("blue mug"), [prod("p-mug", "Blue mug", price=price)]), inventory.Ask("price", ("Blue mug",)))

    def test_c2_builder_refusals_pass_through(self):
        # C2: the builder's own plain refusal is the reply. Bug caught: swallowing it into a Change/Ask, or a bad count reaching the till.
        for qty, why in (("0.5", "whole items"), ("-1", "less than 0"), ("9999999", "too high")):
            with self.subTest(qty=qty), self.assertRaisesRegex(drafts.DraftRefused, why):
                self.plan(say("blue mug", qty=qty), [prod("p-mug", "Blue mug")])
        with self.assertRaisesRegex(drafts.DraftRefused, "know these categories"):
            self.plan(say("blue mug"), [prod("p-mug", "Blue mug", category="mugs")])
        with self.assertRaises(ValueError):
            self.plan(say("blue mug", mode="sell"), [prod("p-mug", "Blue mug")])


class ExistingItemTests(PlanCase):
    def setUp(self):
        super().setUp()
        self.products = [prod("p-mug", "Blue mug"), prod("p-big", "Blue mug large"), prod("p-pot", "Teal pot", available="no")]
        self.mug = raw(MUG, "Blue mug", MUG_SKU, stock=12)
        self.pot = raw(POT, "Teal pot", "AS-PAN-TEAL-POT-01", stock=0)
        self.till, self.cats = read_till(self.mug, self.pot)
        self.site = mapper.parse_site_product(self.products[0])

    def test_c3_existing_item(self):
        # C3: a linked item (cloverId, else its one SKU, as links.reserved resolves it) -> the real build_set_stock / build_received draft.
        # Bug caught: planning a second create, the wrong count builder, or losing the website word that goes with the count.
        links = {"p-mug": link_of(), "p-pot": link_of(POT, "AS-PAN-TEAL-POT-01")}
        mug = self.till[0]
        for mode, qty, builder in (("set", 30, drafts.build_set_stock), ("add", 5, drafts.build_received)):
            with self.subTest(mode=mode):
                change = self.plan(say("blue mugs", qty=qty, mode=mode), self.products, [self.mug, self.pot], links)
                self.assertEqual(change.draft.draft_hash, builder(mug, Decimal(qty), CFG, site_product=self.site).draft_hash)
                self.assertEqual((change.link, change.draft.item_id, change.draft.kind), (None, MUG, "set_stock"))
                self.only_writes(change, ("PUT", f"/item_stocks/{MUG}"))
        self.assertEqual(self.plan(say("blue mug", qty=5, mode="add"), self.products, [self.mug], links).draft.after["stock"], "17")
        # the link's SKU finds a recreated item whose id changed
        recreated = replace(mug, id="FAKEITEM00009")
        found = inventory.plan(say("blue mug", mode="set"), self.products, {"p-mug": link_of()}, [recreated], self.cats, CFG)
        self.assertEqual(found.draft.item_id, "FAKEITEM00009")
        # the count and the website word are decided together: 0 -> 30 on a Sold out product says Available today in the same change
        pot = self.plan(say("teal pot", qty=30), self.products, [self.mug, self.pot], links)
        self.assertEqual(pot.site_word, "yes")
        self.assertEqual(pot.draft.site_ops, ({"op": "product.set_availability", "args": {"id": "p-pot", "available": "yes"}},))
        limited = self.plan(say("blue mug", qty=3, mode="set"), self.products, [self.mug], links, config=replace(CFG, site_stock_words="limited"))
        self.assertEqual((limited.site_word, limited.draft.site_ops[0]["args"]["available"]), ("limited", "limited"))
        # a linked item hidden on the till still gets its change, with the draft's own warning in the preview
        hidden = self.plan(say("blue mug", mode="set"), self.products, [raw(MUG, "Blue mug", MUG_SKU, stock=12, hidden=True)], links)
        self.assertIn("this item is hidden on the till", hidden.draft.warnings)
        # a link whose item is gone is not a reason to create another one
        with self.assertRaisesRegex(drafts.DraftRefused, "no longer has"):
            self.plan(say("blue mug"), self.products, [self.pot], links)
        # builder refusals pass through: same count, adding to an uncounted item
        with self.assertRaisesRegex(drafts.DraftRefused, "Nothing to change"):
            self.plan(say("blue mug", qty=12, mode="set"), self.products, [self.mug], links)
        with self.assertRaisesRegex(drafts.DraftRefused, "not counting"):
            self.plan(say("blue mug", mode="add"), self.products, [raw(MUG, "Blue mug", MUG_SKU)], links)

    def test_c3_conflicting_claim_is_refused(self):
        # C3: a till item is planned only for the product whose link really holds it, resolved against ALL links as mapper.match does.
        # Bug caught: resolving only the named product's link, so a second product linked to the same till item got a stock change for
        # an item the first product already owns.
        products = [prod("p-a", "Blue mug"), prod("p-b", "Tea", price="14.35 each")]
        both = {"p-a": link_of(), "p-b": link_of()}
        site = [mapper.parse_site_product(r) for r in products]
        self.assertEqual(mapper.match(site, self.till, both).broken_links, ("p-b",))   # the rest of the till code calls p-b's link broken
        with self.assertRaisesRegex(drafts.DraftRefused, "already holds"):
            self.plan(say("tea", qty=30, mode="set"), products, [self.mug], both)
        owner = self.plan(say("blue mug", qty=30, mode="set"), products, [self.mug], both)   # the first holder still plans normally
        self.assertEqual((owner.draft.item_id, owner.draft.after["stock"]), (MUG, "30"))
        # the same claim by SKU only (a recreated item under a new id) is refused the same way
        recreated = raw("FAKEITEM00009", "Blue mug", MUG_SKU, stock=12)
        by_sku = {"p-a": link_of(), "p-b": {"cloverId": "GONE", "sku": MUG_SKU}}
        with self.assertRaisesRegex(drafts.DraftRefused, "already holds"):
            self.plan(say("tea", qty=30, mode="set"), products, [recreated], by_sku)

    def test_c3_unlinked_same_name(self):
        # C3: one unlinked visible exact-name till item -> the same change plus link {product_id, sku}; two, or a hidden one, ask.
        # Bug caught: linking a hidden or duplicated item, or taking an item another product's link already holds.
        till, _ = read_till(raw(MUG, "BLUE  mug", MUG_SKU, stock=12))
        change = self.plan(say("blue mug", mode="set"), self.products, [raw(MUG, "BLUE  mug", MUG_SKU, stock=12)])
        self.assertEqual(change.link, {"product_id": "p-mug", "sku": MUG_SKU})
        self.assertEqual(change.draft.draft_hash, drafts.build_set_stock(till[0], Decimal(37), CFG, site_product=self.site).draft_hash)
        self.assertEqual((change.draft.item_id, change.draft.after["stock"]), (MUG, "37"))
        twin = raw("FAKEITEM00003", "Blue mug", "AS-PAN-BLUE-MUG-02", stock=1)
        two = inventory.Ask("which-product", ("Blue mug (SKU AS-PAN-BLUE-MUG-01)", "Blue mug (SKU AS-PAN-BLUE-MUG-02)"))
        self.assertEqual(self.plan(say("blue mug", mode="set"), self.products, [self.mug, twin]), two)
        shadow = raw("FAKEITEM00003", "Blue mug", "AS-PAN-BLUE-MUG-02", stock=1, hidden=True)   # a hidden twin is still a second item
        self.assertEqual(self.plan(say("blue mug", mode="set"), self.products, [self.mug, shadow]), two)
        self.assertEqual(self.plan(say("blue mug", mode="set"), self.products, [shadow]), inventory.Ask("hidden", ("Blue mug",)))
        # the item the large mug's link holds is never offered to the plain mug, even though the names are alike
        held = {"p-big": link_of()}
        with self.assertRaisesRegex(drafts.DraftRefused, "already in the till"):
            self.plan(say("blue mug", mode="set"), self.products, [self.mug], held)


class PolicyTests(PlanCase):
    def setUp(self):
        super().setUp()
        self.products = [prod("p-mug", "Blue mug")]
        self.links = {"p-mug": link_of()}

    def count(self, stock, mode="count", qty=37, **kw):
        return self.plan(say("blue mug", qty=qty, mode=mode), self.products, [raw(MUG, "Blue mug", MUG_SKU, stock=stock)], self.links, **kw)

    def test_c4_policy_defaults(self):
        # C4 (Q1): "count" on a different number above 0 asks unless the policy says set or add; explicit set/add and an empty shelf never ask.
        # Bug caught: silently overwriting a real count, or asking when the sentence was already clear.
        ask = inventory.Ask("count-conflict", ("Blue mug",))
        self.assertEqual(self.count(12), ask)
        self.assertEqual(self.count(12, policy=inventory.Policy()), ask)
        for odd in ("", "SET", "replace", None):
            self.assertEqual(self.count(12, policy=inventory.Policy(odd)), ask, odd)
        self.assertEqual(self.count(12, policy=inventory.Policy("set")).draft.after["stock"], "37")
        self.assertEqual(self.count(12, policy=inventory.Policy("add")).draft.after["stock"], "49")
        self.assertEqual(self.count(12, mode="set").draft.after["stock"], "37")
        self.assertEqual(self.count(12, mode="add").draft.after["stock"], "49")
        for quiet in (0, None):
            self.assertEqual(self.count(quiet).draft.after["stock"], "37")
        with self.assertRaisesRegex(drafts.DraftRefused, "Nothing to change"):
            self.count(37)    # the same number is not a conflict, and it is not a change either

    def test_c4_price_and_not_live(self):
        # C4 (Q3, Q2): a till price that differs from the website's asks and never becomes a price change; a product that is not live asks.
        # Bug caught: counting an item whose price disagrees with the website, a price write riding along, or a count for a held product.
        for item, unit in ((raw(MUG, "Blue mug", MUG_SKU, price=1200, stock=0), None), (raw(MUG, "Blue mug", MUG_SKU, price=None, stock=0), None),
                           (raw(MUG, "Blue mug", MUG_SKU, stock=0, unit="lb"), "lb")):   # right cents, but per lb on the till and each on the site
            with self.subTest(item=item):
                self.assertEqual(self.plan(say("blue mug", unit=unit), self.products, [item], self.links), inventory.Ask("price-mismatch", ("Blue mug",)))
        item = raw(MUG, "Blue mug", MUG_SKU, price=1200, stock=12)
        self.assertEqual(self.plan(say("blue mug"), self.products, [item], self.links), inventory.Ask("price-mismatch", ("Blue mug",)))   # before the count question
        self.assertEqual(self.plan(say("blue mug"), self.products, [item]), inventory.Ask("price-mismatch", ("Blue mug",)))   # unlinked too
        same = self.count(0)
        self.only_writes(same, ("PUT", f"/item_stocks/{MUG}"))
        weighed = self.plan(say("pears", qty=4, unit="lb"), [prod("p-pear", "Pears", price="8.00 per lb")],
                            [raw("FAKEITEM00004", "Pears", "AS-FRU-PEARS-01", price=800, stock=0, unit="lb")], {"p-pear": link_of("FAKEITEM00004", "AS-FRU-PEARS-01")})
        self.assertEqual(weighed.draft.after["stock"], "4")   # per-lb price and unit agree
        # no website price: nothing to disagree with; a price Hass cannot read asks
        self.assertEqual(self.plan(say("blue mug", mode="set"), [prod("p-mug", "Blue mug", price=None)], [item], self.links).draft.after["stock"], "37")
        self.assertEqual(self.plan(say("blue mug"), [prod("p-mug", "Blue mug", price="free")], [item], self.links), inventory.Ask("price", ("Blue mug",)))
        # not live: held or hidden products ask, even when the till already has the item; a name nobody has is which-product
        for status in ("held", "hidden"):
            with self.subTest(status=status):
                gone = [prod("p-mug", "Blue mug", status=status)]
                self.assertEqual(self.plan(say("blue mugs"), gone, [raw(MUG, "Blue mug", MUG_SKU, stock=0)], self.links), inventory.Ask("not-live", ("Blue mug",)))
                self.assertEqual(self.plan(say("blue mug"), gone), inventory.Ask("not-live", ("Blue mug",)))
        self.assertEqual(self.plan(say("blue mug"), []), inventory.Ask("which-product"))
        live_and_held = [prod("p-old", "Blue mug", status="held"), prod("p-mug", "Blue mug")]
        self.assertEqual(self.plan(say("blue mug"), live_and_held).link["product_id"], "p-mug")


class PureTests(PlanCase):
    def test_c5_pure(self):
        # C5: plan only reads its arguments (no file, no socket, no model) and the repr of a Change or Ask shows no price or count.
        # Bug caught: a plan that mutates the caller's tables, reads a file or the network, or prints a price or count in a log line.
        products = [prod("p-mug", "Blue mug"), prod("p-pot", "Teal pot")]
        links = {"p-pot": link_of(POT, "AS-PAN-TEAL-POT-01")}
        till, cats = read_till(raw(POT, "Teal pot", "AS-PAN-TEAL-POT-01", stock=12), raw(MUG, "Blue mug", MUG_SKU, price=1200, stock=0))
        before = copy.deepcopy((products, links, till, cats))
        with mock.patch("builtins.open", side_effect=AssertionError("plan opened a file")):
            outcomes = [inventory.plan(say("teal pot", mode="set"), products, links, till, cats, CFG),
                        inventory.plan(say("teal pot"), products, links, till, cats, CFG),
                        inventory.plan(say("blue mug"), products, links, till, cats, CFG),
                        inventory.plan(say("zebra"), products, links, till, cats, CFG),
                        self.plan(say("blue mug"), [prod("p-mug", "Blue mug")])]
            again = inventory.plan(say("teal pot", mode="set"), products, links, till, cats, CFG)
        self.assertEqual((products, links, till, cats), before)
        self.assertEqual(again.draft.draft_hash, outcomes[0].draft.draft_hash)
        self.assertEqual([type(o).__name__ for o in outcomes], ["Change", "Ask", "Ask", "Ask", "Change"])
        for out in outcomes:
            text = repr(out)
            self.assertLess(len(text), 200, text)
            for value in ("14.35", "1435", "1200", "37", "12", "$", "AS-"):
                self.assertNotIn(value, text)
        self.assertEqual(repr(outcomes[0]), "Change(kind='set_stock', product_id='p-pot', linked=False)")
        self.assertEqual(repr(outcomes[4]), "Change(kind='create_item', product_id='p-mug', linked=True)")
        self.assertEqual(repr(outcomes[1]), "Ask(kind='count-conflict', names=('Teal pot',))")
        # S1 read as a test: the module imports only the standard library helpers it needs and hass.*, nothing that can open a connection
        tree = ast.parse(inspect.getsource(inventory))
        imported = {a.name.split(".")[0] for n in ast.walk(tree) if isinstance(n, ast.Import) for a in n.names}
        imported |= {n.module.split(".")[0] for n in ast.walk(tree) if isinstance(n, ast.ImportFrom)}
        self.assertEqual(imported, {"dataclasses", "decimal", "hass"})
        self.assertNotIn("DELETE", inspect.getsource(inventory))
