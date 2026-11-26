"""H64: a price-only edit keeps the wording the owner already saw on v1.

Found by the G-approved top-up recording (2026-11-25): render_listing asked the copy selector again for v2 with the
same input (pins and public IDs only), and the cloud gave a different description template in 10 of 16 jobs, so a
"make it $8" edit rewrote the description the owner never asked to change (strict cases fail `edit preserves
description`). Case 21 shows the same drift the other way: v1 went out at the segment cap with the default wording,
then v2 had time to ask and changed it. The stage now keeps the first wording outcome for an identical selector input
for the whole job. A changed input (a rename changes the eligible IDs) is still asked, other jobs are asked separately,
and a reply that is not a valid choice is asked again on the next version (case 36 counts both asks).
"""
import unittest

from hass.npp.copy import Context, Fact, Writer
from hass.npp import assets
from hass.npp.stages import _eligible_choice
from hass.tests import test_npp_stages as base

OPTIONS = {'kind': 'food', 'category': 'pantry',
           'templates': {'name': ['name-item', 'name-brand-item'], 'description': ['desc-a', 'desc-b'],
                         'imageAlt': ['alt-photo'], 'story': ['story-made']},
           'phrase_ids': ['food-open-1', 'food-use-1'], 'fact_ids': {'makes': 'f-makes'}}


class JobCopyChoiceTests(unittest.TestCase):
    """Reuses the real stage port fixture (synthetic capture, no model, no network) without re-running its tests."""

    setUp = base.StageTests.setUp
    deny = base.StageTests.deny
    capture = base.StageTests.capture
    start_render = base.StageTests.start_render

    def drifting_selector(self, reply=None):
        """Stands in for a cloud selector that answers the same input differently each time it is asked."""
        self.asked = []

        def select(step, prompt, schema, options):
            self.asked.append(options)
            if reply is not None:
                return reply
            offered = options['templates']['description']
            pick = offered[(len(self.asked) - 1) % len(offered)]
            return {'description': {'template_id': pick, 'phrase_ids': []}}

        self.port.selector = select

    def drafts(self, first, edit=None):
        self.start_render(first)
        self.case.work()
        if edit:
            self.case.say(edit)
            self.case.work()
        return [draft['ops'][-1]['args'] for draft in self.saved]

    def test_price_only_edit_reuses_the_v1_choice(self):
        self.drifting_selector()
        v1, v2 = self.drafts('$7 each', 'make it $8')
        self.assertEqual(len(self.asked), 1)  # asked once; v2 had the identical input
        self.assertEqual((v1['sellingPrice'], v2['sellingPrice']), ('7.00 each', '8.00 each'))
        self.assertEqual({k for k in v1.keys() | v2.keys() if v1.get(k) != v2.get(k)}, {'sellingPrice'})
        self.case.assert_unpublished()

    def test_the_drifting_selector_really_drifts(self):
        # Negative control: without the per-job answer, the second ask gives v2 another description.
        self.drifting_selector()
        first = self.port.selector({}, '', {}, OPTIONS)
        second = self.port.selector({}, '', {}, OPTIONS)
        self.assertNotEqual(first, second)

    def test_a_changed_input_is_asked_again(self):
        self.drifting_selector()
        held = self.port._job_selector('job-a', remote=True)
        renamed = {**OPTIONS, 'templates': {**OPTIONS['templates'], 'name': ['name-item']}}
        one, again, other = held({'s': 1}, 'p', {}, OPTIONS), held({'s': 1}, 'p', {}, OPTIONS), held({'s': 1}, 'p', {}, renamed)
        self.assertEqual(one, again)
        self.assertEqual(len(self.asked), 2)
        self.assertNotEqual(one, other)

    def test_jobs_do_not_share_answers(self):
        self.drifting_selector()
        a = self.port._job_selector('job-a', remote=True)({}, 'p', {}, OPTIONS)
        b = self.port._job_selector('job-b', remote=True)({}, 'p', {}, OPTIONS)
        self.assertEqual(len(self.asked), 2)
        self.assertNotEqual(a, b)

    def test_a_held_answer_is_reused_without_remote_time(self):
        self.drifting_selector()
        held = self.port._job_selector('job-a', remote=True)({}, 'p', {}, OPTIONS)
        self.assertEqual(self.port._job_selector('job-a', remote=False)({}, 'p', {}, OPTIONS), held)
        self.assertEqual(len(self.asked), 1)

    def test_a_version_without_remote_time_keeps_its_default_for_later_versions(self):
        # Case 21: v1 goes out at the segment cap with the default wording; v2 has time but must not change it.
        self.drifting_selector()
        self.assertIsNone(self.port._job_selector('job-a', remote=False)({}, 'p', {}, OPTIONS))
        self.assertIsNone(self.port._job_selector('job-a', remote=True)({}, 'p', {}, OPTIONS))
        self.assertEqual(self.asked, [])
        # Another job, or a changed input in the same job, is still asked.
        self.port._job_selector('job-b', remote=True)({}, 'p', {}, OPTIONS)
        self.port._job_selector('job-a', remote=True)({}, 'p2', {}, OPTIONS)
        self.assertEqual(len(self.asked), 2)

    def test_a_reply_that_is_not_a_valid_choice_is_asked_again(self):
        # Case 36: fabricated prose is never a choice; the Writer gives the default and the next version asks again.
        self.drifting_selector(reply={'description': 'The beans are roasted in copper pans.'})
        select = self.port._job_selector('job-a', remote=True)
        for _ in range(2):
            self.assertEqual(select({}, 'p', {}, OPTIONS), {'description': 'The beans are roasted in copper pans.'})
        self.assertEqual(len(self.asked), 2)

    def test_a_returned_answer_cannot_change_the_held_one(self):
        self.drifting_selector()
        select = self.port._job_selector('job-a', remote=True)
        select({}, 'p', {}, OPTIONS)['description']['template_id'] = 'tampered'
        self.assertEqual(select({}, 'p', {}, OPTIONS)['description']['template_id'], 'desc-a')
        select({}, 'p', {}, OPTIONS)['description']['template_id'] = 'tampered'
        self.assertEqual(select({}, 'p', {}, OPTIONS)['description']['template_id'], 'desc-a')

    def test_no_selector_stays_no_selector(self):
        self.port.selector = None
        self.assertIsNone(self.port._job_selector('job-a', remote=True))


class EligibleChoiceTests(unittest.TestCase):
    def test_only_offered_ids_make_a_choice(self):
        good = {'name': {'template_id': 'name-item'}, 'description': {'template_id': 'desc-a', 'phrase_ids': ['food-open-1']},
                'story': {'template_id': 'story-made', 'phrase_ids': [], 'fact_ids': ['f-makes']}}
        self.assertTrue(_eligible_choice(good, OPTIONS))
        self.assertTrue(_eligible_choice({**good, 'story': None}, OPTIONS))
        for bad in (None, {}, 'desc-a', {'price': {'template_id': 'name-item'}},
                    {'description': 'The beans are roasted in copper pans.'},
                    {'description': {'template_id': 'desc-c'}},
                    {'name': {'template_id': 'desc-a'}},
                    {'description': {'template_id': 'desc-a', 'phrase_ids': ['food-close-9']}},
                    {'description': {'template_id': 'desc-a', 'phrase_ids': 'food-open-1'}},
                    {'description': {'template_id': 'desc-a', 'phrase_ids': [{'x': 1}]}},
                    {'story': {'template_id': 'story-made', 'phrase_ids': [], 'fact_ids': ['f-other']}},
                    {'name': None}):
            with self.subTest(bad=bad):
                self.assertFalse(_eligible_choice(bad, OPTIONS))
        self.assertFalse(_eligible_choice(good, None))


class DeclinedStoryTests(unittest.TestCase):
    """Case 31a: the cloud declined the story although a kept fact supports one; the maker story stays."""

    @classmethod
    def setUpClass(cls):
        cls.writer = Writer(assets())

    def setUp(self):
        self.found = Fact('f-year', 'founded', '1982', 'https://orchard.example/about', 'Bay Orchard was founded in 1982.',
                          'supports')
        self.ctx = Context('food', 'pantry', 'raw', 'beans', owner_words='Made by Bay Orchard', maker_name='Bay Orchard',
                           facts=(self.found,))

    def declined(self, *_):
        return {'name': {'template_id': 'name-item'}, 'imageAlt': {'template_id': 'alt-photo'},
                'description': {'template_id': 'desc-food-plain', 'phrase_ids': ['food-open-1', 'food-use-1', 'food-close-1']},
                'story': None}

    def test_declined_story_with_a_kept_fact_takes_the_reviewed_default(self):
        result = self.writer.write(self.ctx, self.declined)
        self.assertEqual(result.text['story'], self.writer.write(self.ctx).text['story'])
        self.assertIn('founded in 1982.', result.text['story'])
        self.assertTrue(result.basic)
        self.assertEqual(result.text['description'], self.writer.write(self.ctx, self.declined).text['description'])

    def test_declined_story_without_a_kept_fact_stays_absent(self):
        for ctx in (Context('food', 'pantry', 'raw', 'beans'),
                    *(Context('food', 'pantry', 'raw', 'beans', owner_words='Made by Bay Orchard', maker_name='Bay Orchard',
                              facts=(evidence,))
                      for evidence in (Fact('f-year', 'founded', '1982', 'https://orchard.example/about',
                                            'Bay Orchard was founded in 1982.', 'unclear'),
                                       Fact('f-year', 'founded', '1982', '', 'Bay Orchard was founded in 1982.',
                                            'supports')))):
            with self.subTest(ctx=ctx):
                result = self.writer.write(ctx, self.declined)
                self.assertNotIn('story', result.text)
                self.assertFalse(result.basic)


if __name__ == '__main__':
    unittest.main()
