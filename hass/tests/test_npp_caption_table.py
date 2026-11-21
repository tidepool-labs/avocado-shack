"""Synthetic shop captions replayed from the real splitter to NPP's first plan.

No photo files, live config, model runner, editor, or delivery. Prices and stock
counts are invented. An amount in the private set may still be the selling price
when a separate, explicitly tagged span licenses it (design 1.9).
"""
from contextlib import closing
from datetime import datetime, timedelta, timezone
from decimal import Decimal
import json
import sqlite3
from types import SimpleNamespace
import unittest
from unittest.mock import Mock, patch

from hass import answer_reader, cloud_codex
from hass.conversation import Conversation
from hass.npp import assets, private_numbers, stages
from hass.npp.job import Jobs, Work
from hass.skills import item_intake, openreq


# Caption, public price or 'ask', private numeric values (cost in dollars AND
# cents; counts in their stated units; unresolved alternatives quarantined).
CAPTIONS = (
    ('Apricot jam; bought 17 at 2.65; selling 4.85 each', '4.85 each', '17 2.65 265'),
    ('Cocoa nibs, 4 bucks each, paid 2', '4.00 each', '2 200'),
    ('Dried figs; bought 22 of them for $2.80; sell $4.60/each', '4.60 each', '22 2.80 280'),
    ('Chili crisp; got 19 jars; paid $3.12; retail $6.75 each', '6.75 each', '19 3.12 312'),
    ('Oat crackers; sell $3.65 per item; stock 26 packs; cost $1.10', '3.65 each', '26 1.10 110'),
    ('Lemon curd; cost $2.08; sell $2.08 each; qty 24 jars', '2.08 each', '24 2.08 208'),
    ('Date bars; selling $7 each; got 7 bars; paid $2.56', '7.00 each', '7 2.56 256'),
    ('Plums; bought 33 at $1.13; selling $3.40/lb', '3.40 per lb', '33 1.13 113'),
    ('Red pears; have 31 lb; cost $1.32; retail $2.68 per pound', '2.68 per lb', '31 1.32 132'),
    ('Fresh ginger; sell $8.18 a pound; paid $4.59; 16 lb in stock', '8.18 per lb', '16 4.59 459'),
    ('Shallots; bought 24 for $1.19; sell $2.74 per lb', '2.74 per lb', '24 1.19 119'),
    ('Dry lentils; paid 89 cents; sell $2.63 each; got 40 bags', '2.63 each', '40 .89 89'),
    ('Sesame sticks, cost ninety cents, sale price $2.16 each, qty 21 bags', '2.16 each', '21 .90 90'),
    ('Pickled radish\nSTOCK: 36 jars\nPAID $2.91\nSELL $5.06 EACH', '5.06 each', '36 2.91 291'),
    ('Peach spread; I bought 23 at $2.28 and sell $4.62 each', '4.62 each', '23 2.28 228'),
    ('Apple butter; paid $2.14. Selling $4.78 each', '4.78 each', '2.14 214'),
    ('Granola; sell $5.31 each and paid $2.29; have 14 boxes', '5.31 each', '14 2.29 229'),
    ('Orange marmalade; bought 13 at 2.62 and I’ll sell $4.17 each', '4.17 each', '13 2.62 262'),
    ('Bee pollen; paid $3.83; I will sell $6.91 each; stock 35 packs', '6.91 each', '35 3.83 383'),
    ('Butter beans; $1.37 / sell $2.83 each; got 29 cans', '2.83 each', '29 1.37 137'),
    ('Caper berries; cost two dollars; sell seven dollars each; have 27 jars', '7.00 each', '27 2 200'),
    ('Grape jelly; qty twelve jars; paid three dollars; sell five dollars each', '5.00 each', '12 3 300'),
    ('Rice crackers; got a dozen; cost $1.61; selling $3.32 each', '3.32 each', '12 1.61 161'),
    ('Candied pecans; got half a dozen; paid $2.40; sell $5.13 each', '5.13 each', '6 2.40 240'),
    ('Tea tins; have twenty five tins; paid two dollars and fifty cents; sell $5.70 each', '5.70 each', '25 2.50 250'),
    ('Corn chips; bought 18 for $1.57; 3 bucks each', '3.00 each', '18 1.57 157'),
    ('Caramel sauce $5.34 each; paid $2.73; got 32 jars', '5.34 each', '32 2.73 273'),
    ('Mushroom powder; bought 11 at $3.61; price $7.34', '7.34 each', '11 3.61 361'),
    ('Ginger snaps; bought 16 at $1.96; sell $3.71 each; 12 oz', '3.71 each', '16 1.96 196 12'),
    ('Tamarind paste; 28 jars; paid $1.92; selling $4.39 each', '4.39 each', '28 1.92 192'),
    ('Mint jelly; paid $2.34; stock 34', 'ask', '34 2.34 234'),
    ('Rye crisps; got 18 bags', 'ask', '18'),
    ('Nectarines; cost $1.15 per lb; sell $3.52; got 27 lb', 'ask', '27 1.15 115'),
    ('Berry baskets; bought 15 at $2.37; sell $5.62 per basket', 'ask', '15 2.37 237'),
    ('Pita chips; bought 16 at $1.73; sell $3.89 each; sell $4.19 each', 'ask', '16 1.73 173'),
    ('Smoked salt; got 21 tins; paid $2.83; sell $5.2O each', 'ask', '21 2.83 283 5.2'),
    ('Carrots; 4 or 5 bucks each; paid $1.41; have 36 lb', 'ask', '4 5 36 1.41 141'),
    ('Fig jam; about 3 bucks each; paid $1.55; 23 jars', 'ask', '3 23 1.55 155'),
    ('Hot sauce; 2.30, 4.75; got 29 bottles', 'ask', '2.30 4.75 29'),
    ('Oyster mushrooms; selling maybe $6.53/lb; paid $3.42; got 17 lb', 'ask', '6.53 17 3.42 342'),
    ('Beet chips; got 18 at 2.57 selling 4.31 each', '4.31 each', '18 2.57 257'),
    ('Pear preserves; got 16 at 2.51 selling 4.28', '4.28 each', '16 2.51 251'),
    ('Blackberry syrup; paid 2.56 selling 5.21 each; 15 bottles', '5.21 each', '2.56 256 15'),
    # Bare dictation 'three fifty' leaves the cost unresolved under the typed grammar.
    ('Pumpkin seeds; cost three fifty; sell $5.67 each; have 25 bags', 'ask', '3.50 350 25'),
    ('Cider vinegar; qty 1,200; paid 64 cents; sell $2.38 each', '2.38 each', '1200 .64 64'),
    ('Herb oil; bought 17 at $2.43; selling 4 dollars and 35 cents each', '4.35 each', '17 2.43 243'),
    ('Cranberry spread; wholesale $2.32; $6.14 retail; stock 17', '6.14 each', '2.32 232 17'),
    ("Rice cakes; cost $1.45; don't sell $4.50 each; have 28 bags", 'ask', '1.45 145 4.50 28'),
    ('Cocoa wafers; paid 2 dollars and 5 cents; sell $4.63 each', '4.63 each', '2.05 205'),
    ('Melon strips; cost $1.74/lb; sell $6.84 each; have 27 bags', '6.84 each', '1.74 174 27'),
    # A case price is not an item price; the public schema cannot display this unit.
    ('Oat clusters; paid $2.67; stock 19 cases; sell $8.95 per case', 'ask', '2.67 267 19'),
)
FRESH = {8, 9, 10, 11, 33, 34, 37, 40}  # fixture identification, not inferred from cost units
AMBIGUOUS = {35, 36, 37, 38, 39, 40, 44, 48}
NOW = datetime(2000, 1, 1, tzinfo=timezone.utc)
PHOTO_SHA = 'a' * 64
PHOTO = b'synthetic product photo'


class FixtureConversation(Conversation):
    def __init__(self, db, local):
        # Do not construct a host Conversation: only supply ports used by
        # _npp_photo and _read_intake; state and simulated reader are in memory.
        self.db = db
        self._asker = 'fixture-owner'
        self._forwarded = None
        self.settings = {'mediaRoot': '.'}
        self.labels = None
        self.requests = openreq.OpenRequests(db)
        self._intake_fields = {'photo_fields': local}
        self.editor = Mock()
        self.editor.candidate.return_value = {'result': 'refused'}
        self.dispatch = Mock()
        self.dispatch.simple_intake.return_value = True

    def _code(self, hexdigest):
        return 'cafe'

    def _now(self):
        return NOW


def replay(caption, kind, pinned, local=None, *, reader=None):
    """Use real caption dispatch, Jobs.input, request store, and S2/S3 planner."""
    identify_calls, copy_calls = [], []

    def identify_runner(payload):
        identify_calls.append(payload)
        result = dict(kind=kind, item='Fixture product', brand_on_label=None,
                      size_text=None, label_words=[], visible_claims=[], category_guess=None,
                      has_person_or_screen=False, is_product=True,
                      confidence=dict(kind=1, item=1, brand=0, size=0, category=0))
        return dict(ok=True, model='fixture', text=json.dumps(result))

    def copy_transport(url, body, headers, timeout):
        copy_calls.append(json.loads(body))
        return 503, b''  # deterministic template fallback, no model calls

    with closing(sqlite3.connect(':memory:')) as db:
        db.row_factory = sqlite3.Row
        db.execute('CREATE TABLE messages (provider_id TEXT)')
        conv = FixtureConversation(db, local)
        pipeline = stages.ProductionStages(conv, pinned)
        pipeline.identifier = stages.identify.Identifier(pinned, runner=identify_runner)
        pipeline.selector = stages.copy.codex_selector(copy_transport)
        jobs = Jobs(conv, pipeline, pinned, executor=Mock())
        msg = SimpleNamespace(chat='fixture-chat', provider_id='fixture-caption', text=caption,
                              received_at=NOW.isoformat(), attachments=1, from_me=False, kind='new')
        if reader is not None:
            with (patch.object(conv, 'answer_reader', reader),
                  patch.object(conv, '_is_owner', return_value=True), patch.object(conv, 'stage')):
                conv._intake_fields = conv._read_intake(msg)
        disposition = conv._npp_photo(jobs, msg, NOW, [PHOTO_SHA])
        job = jobs.active(msg.chat, conv._asker)
        request = jobs.request(job, NOW) if job is not None else None
        if request is None:
            raise RuntimeError('fixture intake did not retain an active request')
        work = Work('cafe', request, None, NOW + timedelta(seconds=100))
        catalog = SimpleNamespace(products=(), makers={}, active_products=lambda: ())
        with (patch.object(pipeline, 'catalog', return_value=catalog),
              patch.object(pipeline, '_photo', return_value=PHOTO),
              patch.object(pipeline, '_research', wraps=pipeline._research) as research,
              patch.object(stages.OfficialPage, 'fetch', side_effect=RuntimeError('fixture research blocked')),
              patch.object(pipeline, '_picture', return_value=(SimpleNamespace(variant='raw'), PHOTO_SHA, '', []))):
            plan = pipeline.start_plan(work)
            if plan.listing is not None:
                # Use the real render-to-copy projection. The fake editor refuses
                # the candidate; no capture, persistence or delivery follows.
                pipeline.render_listing(work, plan.listing)
        return disposition, request, plan, identify_calls, copy_calls, research.call_args


class CaptionTable(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.pinned = assets()
        cls.clean = {kind: replay('Sell $8.42 each', kind, cls.pinned)[3:5]
                     for kind in ('fresh', 'food')}
        cls.rows = {}
        for index, (caption, _, _) in enumerate(CAPTIONS, 1):
            kind = 'fresh' if index in FRESH else 'food'
            observed = replay(caption, kind, cls.pinned)
            cls.rows[index] = (kind, *item_intake.caption_answers(caption), *observed)

    def _check_private(self, index):
        _, _, private = CAPTIONS[index - 1]
        request = self.rows[index][4]
        self.assertEqual({Decimal(n) for n in request['slots']['intake']['private']}, set(map(Decimal, private.split())))

    def _check_price(self, index):
        caption, expected, _ = CAPTIONS[index - 1]
        _, _, parsed, disposition, request, plan, *_ = self.rows[index]
        self.assertEqual(disposition, 'npp-working')
        slot, listing = request['slots']['intake'], plan.listing
        if expected == 'ask':
            self.assertIsNone(listing)
            ids = {qid for qid, _ in plan.questions}
            self.assertTrue(ids & {'selling_price', 'price_unit'}, plan.questions)
            if 'selling_price' in ids:
                self.assertIsNone(slot['price'])
                self.assertIsNone(slot['price_span'])
            if index == 33:  # the only "per lb" belongs to the cost, not to the unitless sale
                self.assertNotIn('sold_by', parsed)
            return

        amount, _, basis = expected.partition(' ')
        self.assertEqual(parsed.get('price'), amount)
        span = slot['price_span']
        self.assertIsNotNone(span, plan.questions)
        assert span is not None
        start, end = span
        self.assertTrue(0 <= start < end <= len(caption))
        _, tagged = item_intake.caption_answers(caption[start:end])
        self.assertEqual(tagged.get('price'), amount)
        self.assertNotIn('cost', tagged)
        self.assertEqual(parsed.get('sold_by'), tagged.get('sold_by'))
        if 'sold_by' in tagged:
            self.assertEqual(tagged['sold_by'], 'pound' if basis == 'per lb' else 'item')
        self.assertIsNotNone(listing, plan.questions)
        assert listing is not None
        self.assertEqual((listing['sellingPrice'], listing['priceUnit']), (amount, 'lb' if basis == 'per lb' else basis))

    def test_c1_table(self):
        # C1: catch an amount selected from cost/count, a dropped tagged price,
        # or a unit silently borrowed from a private span.
        for index in self.rows:
            with self.subTest(row=index, check='private-set'):
                self._check_private(index)
            with self.subTest(row=index, check='plan'):
                self._check_price(index)

    def test_c2_private_never_public(self):
        # C2: catch forwarding an unresolved clause or copying the complete
        # work request (private slots included) into a model prompt.
        for index, (_, _, private) in enumerate(CAPTIONS, 1):
            kind, remainder, _, _, request, plan, identify, copy, research = self.rows[index]
            texts = [item_intake.without_unresolved_finance(remainder), *request['texts']]
            for boundary, text in enumerate(texts):
                with self.subTest(row=index, remainder=boundary):
                    self.assertFalse(item_intake.unresolved_finance(text), text)
                    self.assertFalse(any(c.isnumeric() for c in text), text)
                    blocked = set(map(Decimal, private.split()))
                    self.assertFalse(any(word.amounts & blocked for word in private_numbers.values(text)), text)
            with self.subTest(row=index, check='model-payloads'):
                clean_identify, clean_copy = self.clean[kind]
                self.assertEqual(len(clean_identify), 1)
                self.assertEqual(len(clean_copy), 1)
                # Full-payload equality distinguishes owner data from coincidental
                # numeric constants in the trusted schema/examples or encoded photo.
                self.assertEqual(identify, clean_identify)
                self.assertEqual(copy, clean_copy if plan.listing is not None else [])
                if research is not None:
                    self.assertFalse(research.args[1].research_allowed)
                    self.assertFalse(research.args[2] or research.args[3])

    def test_c3_ambiguous_asks(self):
        # C3: even a shape-valid finance-local reader answer cannot pick an
        # alternative, turn an estimate into an exact amount, or assign roles.
        local = dict(price_cents=498, cost_cents=None, quantity=None)
        for index in sorted(AMBIGUOUS):
            caption, expected, _ = CAPTIONS[index - 1]
            kind = self.rows[index][0]
            disposition, request, plan, *_ = replay(caption, kind, self.pinned, local)
            with self.subTest(row=index):
                self.assertEqual(expected, 'ask')
                if index != 44:  # row 44 tags a price, but the still-unresolved cost blocks it
                    self.assertNotIn('price', self.rows[index][2])
                self.assertEqual(disposition, 'npp-working')
                self.assertIsNone(request['slots']['intake']['price'])
                self.assertIsNone(request['slots']['intake']['price_span'])
                self.assertIsNone(plan.listing)
                self.assertIn('selling_price', {qid for qid, _ in plan.questions})

    def test_c2_private_never_public_local_reader(self):
        # A cloud-configured finance reader must not call its remote runner;
        # only the real loopback fallback's model payload may contain raw words.
        caption = CAPTIONS[43][0]  # spoken cost and digit count
        local_bodies = []
        cloud_runner = Mock(return_value={'ok': False, 'code': 'model'})

        def local_transport(url, body, headers, timeout):
            local_bodies.append(json.loads(body))
            result = json.dumps(dict(price_cents=None, cost_cents=350, quantity=25))
            return 200, json.dumps(dict(done=True, message={'content': result})).encode()

        fallback = answer_reader.AnswerReader('http://127.0.0.1:11434', 'fixture', transport=local_transport)
        reader = answer_reader.AnswerReader(None, 'fixture', api='codex', fallback=fallback,
                                            transport=cloud_codex.CodexTransport(runner=cloud_runner))
        _, request, plan, identify, copy, research = replay(caption, 'food', self.pinned, reader=reader)
        self.assertEqual([m['content'] for b in local_bodies for m in b['messages'] if m['role'] == 'user'], [caption])
        cloud_runner.assert_not_called()
        self.assertIsNone(plan.listing)
        self.assertEqual(request['texts'], ['Pumpkin seeds'])
        self.assertEqual(identify, self.clean['food'][0])
        self.assertEqual(copy, [])
        self.assertIsNone(research)
