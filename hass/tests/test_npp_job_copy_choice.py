"""H64: a price-only edit keeps the copy the cloud selector chose for v1.

Found by the G-approved top-up recording (2026-11-25): render_listing asked the copy selector again for v2 with the
same input (pins and public IDs only), and the cloud gave a different description template in 10 of 16 jobs, so a
"make it $8" edit rewrote the description the owner never asked to change (strict cases fail `edit preserves
description`). The stage now answers an identical selector input once per job. A changed input (a rename changes the
eligible IDs) is still asked, other jobs are asked separately, and a version without remote time reuses only an
answer it already holds.
"""
import unittest

from hass.tests import test_npp_stages as base


class JobCopyChoiceTests(unittest.TestCase):
    """Reuses the real stage port fixture (synthetic capture, no model, no network) without re-running its tests."""

    setUp = base.StageTests.setUp
    deny = base.StageTests.deny
    capture = base.StageTests.capture
    start_render = base.StageTests.start_render

    def drifting_selector(self):
        """Stands in for a cloud selector that answers the same input differently each time it is asked."""
        templates = ['desc-food-default', 'desc-default-short']
        self.asked = []

        def select(step, prompt, schema, options):
            self.asked.append(options)
            pick = templates[(len(self.asked) - 1) % len(templates)]
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
        select = self.port.selector
        first = select({}, '', {}, {'templates': {}})
        second = select({}, '', {}, {'templates': {}})
        self.assertNotEqual(first, second)

    def test_a_changed_input_is_asked_again(self):
        self.drifting_selector()
        held = self.port._job_selector('job-a', remote=True)
        one = held({'s': 1}, 'p', {}, {'templates': {'name': ['name-item']}})
        again = held({'s': 1}, 'p', {}, {'templates': {'name': ['name-item']}})
        other = held({'s': 1}, 'p', {}, {'templates': {'name': ['name-brand-item']}})
        self.assertEqual(one, again)
        self.assertEqual(len(self.asked), 2)
        self.assertNotEqual(one, other)

    def test_jobs_do_not_share_answers(self):
        self.drifting_selector()
        a = self.port._job_selector('job-a', remote=True)({}, 'p', {}, {})
        b = self.port._job_selector('job-b', remote=True)({}, 'p', {}, {})
        self.assertEqual(len(self.asked), 2)
        self.assertNotEqual(a, b)

    def test_without_remote_time_only_a_held_answer_is_used(self):
        self.drifting_selector()
        self.assertIsNone(self.port._job_selector('job-a', remote=False)({}, 'p', {}, {}))
        self.assertEqual(self.asked, [])
        held = self.port._job_selector('job-a', remote=True)({}, 'p', {}, {})
        self.assertEqual(self.port._job_selector('job-a', remote=False)({}, 'p', {}, {}), held)
        self.assertEqual(len(self.asked), 1)

    def test_a_returned_answer_cannot_change_the_held_one(self):
        self.drifting_selector()
        select = self.port._job_selector('job-a', remote=True)
        select({}, 'p', {}, {})['description']['template_id'] = 'tampered'
        self.assertEqual(select({}, 'p', {}, {})['description']['template_id'], 'desc-food-default')

    def test_no_selector_stays_no_selector(self):
        self.port.selector = None
        self.assertIsNone(self.port._job_selector('job-a', remote=True))


if __name__ == '__main__':
    unittest.main()
