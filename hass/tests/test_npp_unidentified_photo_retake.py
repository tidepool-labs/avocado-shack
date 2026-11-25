"""NPP first plan: a priced item whose photo cannot be used gets the retake, not "what is it?" (case 28b/28c).

Contract (case 28, R1.1): a photo that would be published raw but fails a raw condition gets the existing retake
sentence, no draft and no prompt. When S2 cannot identify the item because the photo shows a phone screen or is
blurry, and he has already given the price, the only useful next step is a new photo. A blurry or non-product photo
with nothing else said ("add this", case 18) still gets the one identity question; an unidentified photo that is
sharp and has no screen also still asks what it is. Real caption dispatch, Jobs.input and S2/S3 planner with the
public case-28 photos; a fixture S2 reader, no model, network or private recording.
"""
from contextlib import closing
from datetime import timedelta
import json
from pathlib import Path
import sqlite3
from types import SimpleNamespace
import unittest
from unittest.mock import Mock, patch

from hass.npp import assets, picture, stages
from hass.npp.job import Jobs, Work
from hass.ops import photos
from hass.tests.test_npp_caption_table import NOW, PHOTO_SHA, FixtureConversation

PHOTOS = Path(__file__).resolve().parent / 'npp' / 'cases' / 'photos'


def unread(*, screen, is_product=False):
    """What S2 returned on the recorded case-28 screen/blurry photos: nothing identified."""
    return dict(kind='food', item=None, brand_on_label=None, size_text=None, label_words=[], visible_claims=[],
                category_guess=None, has_person_or_screen=screen, is_product=is_product,
                confidence=dict(kind=0.3, item=0, brand=0, size=0, category=0))


def first_plan(caption, photo, reading, pinned):
    with closing(sqlite3.connect(':memory:')) as db:
        db.row_factory = sqlite3.Row
        db.execute('CREATE TABLE messages (provider_id TEXT)')
        conv = FixtureConversation(db, None)
        pipeline = stages.ProductionStages(conv, pinned)
        pipeline.identifier = stages.identify.Identifier(
            pinned, runner=lambda payload: dict(ok=True, model='fixture', text=json.dumps(reading)))
        jobs = Jobs(conv, pipeline, pinned, executor=Mock())
        msg = SimpleNamespace(chat='fixture-chat', provider_id='fixture-caption', text=caption,
                              received_at=NOW.isoformat(), attachments=1, from_me=False, kind='new')
        conv._npp_photo(jobs, msg, NOW, [PHOTO_SHA])
        request = jobs.request(jobs.active(msg.chat, conv._asker), NOW)
        work = Work('cafe', request, None, NOW + timedelta(seconds=100))
        catalog = SimpleNamespace(products=(), makers={}, active_products=lambda: ())
        with (patch.object(pipeline, 'catalog', return_value=catalog),
              patch.object(pipeline, '_photo', return_value=(PHOTOS / photo).read_bytes()),
              patch.object(pipeline, 'render_listing', side_effect=AssertionError('no render after a retake'))):
            return pipeline.start_plan(work)


class UnidentifiedPhotoRetake(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.pinned = assets()

    def test_raw_conditions_on_the_public_photos(self):
        blurry, screen, sharp = ((PHOTOS / name).read_bytes() for name in
                                 ('honey-blurry.jpg', 'phone-screen.jpg', 'honey.jpg'))
        self.assertEqual(picture.unidentified_retake(blurry, False).reason, photos.RETAKE['blurry'])
        self.assertEqual(picture.unidentified_retake(screen, True).reason, photos.RETAKE['style'])
        self.assertIsNone(picture.unidentified_retake(sharp, False))
        self.assertIsNone(picture.unidentified_retake(sharp, None))  # only an explicit S2 True means a screen
        self.assertIsNone(picture.unidentified_retake(b'not an image', False))  # unreadable: keep the question

    def test_priced_screen_photo_gets_the_retake(self):
        plan = first_plan('new honey $9 each', 'phone-screen.jpg', unread(screen=True), self.pinned)
        self.assertEqual((plan.retake, plan.questions, plan.listing, plan.identified),
                         (photos.RETAKE['style'], (), None, False))

    def test_priced_blurry_photo_gets_the_retake(self):
        plan = first_plan('new honey $9 each', 'honey-blurry.jpg', unread(screen=False, is_product=True), self.pinned)
        self.assertEqual((plan.retake, plan.questions, plan.listing), (photos.RETAKE['blurry'], (), None))

    def test_blurry_photo_with_nothing_said_still_asks_what_it_is(self):
        plan = first_plan('add this', 'honey-blurry.jpg', unread(screen=False), self.pinned)
        self.assertIsNone(plan.retake)
        self.assertEqual([qid for qid, _ in plan.questions], ['identity'])

    def test_priced_sharp_unidentified_photo_still_asks_what_it_is(self):
        plan = first_plan('new honey $9 each', 'honey.jpg', unread(screen=False), self.pinned)
        self.assertIsNone(plan.retake)
        self.assertEqual([qid for qid, _ in plan.questions], ['identity'])


if __name__ == '__main__':
    unittest.main()
