"""H64: a price-only edit keeps the wording the owner already saw on v1.

Found by the G-approved top-up recording (2026-11-25): render_listing asked the copy selector again for v2 with the
same input (pins and public IDs only), and the cloud gave a different description template in 10 of 16 jobs, so a
"make it $8" edit rewrote the description the owner never asked to change (strict cases fail `edit preserves
description`). Case 21 shows the same drift the other way: v1 went out at the segment cap with the default wording,
then v2 had time to ask and changed it. The stage now keeps the first wording outcome for an identical selector input
for the whole job. A changed input (a rename changes the eligible IDs) is still asked, other jobs are asked separately,
and a reply none of which was shown (prose, an unknown field, a handled selector error) leaves the default the owner saw,
which is held like any other outcome, so case 36 asks once.

Where the wording is kept (review RETURN at e0991752): in the job's own durable rows (npp_wording), written by Jobs
with the card it belongs to, never by the render itself:
- it survives a process restart (a fresh ProductionStages reads the same rows);
- a worker finishing after the segment cap cannot replace what the cap card showed;
- a reply is kept for what the Writer rendered from it, field by field, not accepted or refused as a whole.
"""
from datetime import timedelta
from types import SimpleNamespace
import unittest

from hass.npp.copy import Context, Fact, Writer
from hass.npp import assets, stages_for
from hass.tests import test_npp_stages as base

OPTIONS = {'kind': 'food', 'category': 'pantry',
           'templates': {'name': ['name-item', 'name-brand-item'], 'description': ['desc-a', 'desc-b'],
                         'imageAlt': ['alt-photo'], 'story': ['story-made']},
           'phrase_ids': ['food-open-1', 'food-use-1'], 'fact_ids': {'makes': 'f-makes'}}
# Real IDs for a food/pantry item: a nondefault description (three phrases) beside the two default rungs.
PLAIN = {'template_id': 'desc-food-plain', 'phrase_ids': ['food-open-1', 'food-use-1', 'food-close-1']}
SHORT = {'template_id': 'desc-default-short', 'phrase_ids': []}
DEFAULT = object()  # in a table: the reply showed nothing of itself, so the default wording is what is held


def commit(held, wording):
    """What Jobs.finish does with a card's wording: the first outcome for an input stays."""
    for digest, choice in wording.items():
        held.setdefault(digest, choice)


class JobCopyChoiceTests(unittest.TestCase):
    """Reuses the real stage port fixture (synthetic capture, no model, no network) without re-running its tests."""

    setUp = base.StageTests.setUp
    deny = base.StageTests.deny
    capture = base.StageTests.capture
    start_render = base.StageTests.start_render

    def drifting_selector(self, reply=None):
        """Stands in for a cloud selector that answers the same input differently each time it is asked (both replies render)."""
        self.asked = []

        def select(step, prompt, schema, options):
            self.asked.append(options)
            if reply is not None:
                return reply
            return {'description': (PLAIN, SHORT)[(len(self.asked) - 1) % 2]}

        self.port.selector = select

    def replies(self, *replies, during=None):
        """A selector that gives these replies in order (the last one again after that); `during` runs inside the first ask."""
        self.asked = []

        def select(step, prompt, schema, options):
            self.asked.append(options)
            if during is not None and len(self.asked) == 1:
                during()
            return replies[min(len(self.asked), len(replies)) - 1]

        self.port.selector = select

    def wording(self, held, *, remote):
        return self.port._job_selector(SimpleNamespace(wording=held), remote=remote)

    def restart(self):
        """A new process: a new stage object that shares only what is durable (the database), none of the old one's memory."""
        old = self.port
        fresh = stages_for(self.conv, assets())
        fresh.identifier.read, fresh.selector, fresh.mapper, fresh.persist = old.identifier.read, old.selector, old.mapper, old.persist
        self.port = self.conv.npp.stages = fresh

    def drafts(self, first, edit=None, *, between=None):
        self.start_render(first)
        self.case.work()
        if between:
            between()
        if edit:
            self.case.say(edit)
            self.case.work()
        return [draft['ops'][-1]['args'] for draft in self.saved]

    def changed(self, v1, v2):
        return {k for k in v1.keys() | v2.keys() if v1.get(k) != v2.get(k)}

    def test_price_only_edit_reuses_the_v1_choice(self):
        self.drifting_selector()
        v1, v2 = self.drafts('$7 each', 'make it $8')
        self.assertEqual(len(self.asked), 1)  # asked once; v2 had the identical input
        self.assertEqual((v1['sellingPrice'], v2['sellingPrice']), ('7.00 each', '8.00 each'))
        self.assertEqual(self.changed(v1, v2), {'sellingPrice'})
        self.case.assert_unpublished()

    def test_a_restart_between_versions_keeps_the_shown_wording(self):
        # Return item 1. Bug: the held choice lived only in the stage object, so after a restart a price edit asked again
        # and the cloud could give the description the owner never saw. The job's rows are durable; so is the choice.
        self.replies({'description': PLAIN}, {'description': SHORT})
        v1, v2 = self.drafts('$7 each', 'make it $8', between=self.restart)
        self.assertEqual(len(self.asked), 1)  # the new process did not ask again
        self.assertNotIn('Pick up', v1['description'])  # v1 really is the cloud's nondefault pick
        self.assertEqual(self.changed(v1, v2), {'sellingPrice'})

    def test_a_late_remote_answer_cannot_replace_the_cap_wording(self):
        # Return item 2. Bug: the pump runs the cap fallback while the worker is still waiting on the remote selector;
        # the cap card showed the default and held "no choice", then the worker's reply replaced it, so the next edit
        # used wording the owner never saw. Here the cap runs inside the worker's ask, and the reply comes after it.
        def cap_arrives():
            self.case.now += timedelta(seconds=100)
            self.case.flush()

        self.replies({'description': PLAIN}, during=cap_arrives)
        self.start_render('$7 each')
        self.case.scheduler.run()  # the worker asks, the cap card goes out meanwhile, then the worker's reply returns
        self.case.flush()
        self.assertEqual(len(self.saved), 1)  # one card: the cap's, with the default wording
        self.case.say('make it $8')
        self.case.work()
        v1, v2 = [draft['ops'][-1]['args'] for draft in self.saved]
        self.assertEqual(len(self.asked), 1)  # v2 replays the cap's default; it does not ask or use the late reply
        self.assertTrue(v1['description'].startswith('Pick up'))  # the default wording the owner saw
        self.assertEqual(self.changed(v1, v2), {'sellingPrice'})

    def test_a_partly_invalid_reply_holds_what_was_shown(self):
        # Return item 3. Bug: the whole reply was refused for one bad field, but the Writer shows the valid fields, so a
        # valid nondefault description beside an invalid name went out unheld and the next price edit could change it.
        self.replies({'name': {'template_id': 'name-not-offered'}, 'description': PLAIN}, {'description': SHORT})
        v1, v2 = self.drafts('$7 each', 'make it $8')
        self.assertEqual(len(self.asked), 1)
        self.assertEqual(self.changed(v1, v2), {'sellingPrice'})
        self.assertNotIn('Pick up', v1['description'])  # the valid field was what the owner saw

    def test_a_default_shown_for_an_unusable_reply_keeps_its_wording(self):
        # Return item 4 (second review). Bug: a reply the Writer did not apply (prose, empty, no answer after a handled
        # selector error) showed the reviewed default but held nothing, so the price edit asked again and a valid pick
        # replaced the description the owner had seen.
        def first_ask(step, prompt, schema, options):
            self.asked.append(options)
            if len(self.asked) > 1:
                return {'description': PLAIN}  # a valid pick, offered if the job ever asks again
            if self.failure:
                raise TimeoutError('selector timed out')
            return self.failure_reply

        for name, reply, failure in (('prose', {'description': 'fabricated prose'}, False), ('empty', {}, False), ('error', None, True)):
            for restarted in (False, True):
                with self.subTest(first=name, restarted=restarted):
                    self.setUp()
                    self.asked, self.failure, self.failure_reply = [], failure, reply
                    self.port.selector = first_ask
                    v1, v2 = self.drafts('$7 each', 'make it $8', between=self.restart if restarted else None)
                    self.assertEqual(len(self.asked), 1)  # v2 replays the default; it does not ask again
                    self.assertTrue(v1['description'].startswith('Pick up'))  # v1 is the reviewed default
                    self.assertEqual(self.changed(v1, v2), {'sellingPrice'})

    def test_the_drifting_selector_really_drifts(self):
        # Negative control: without the per-job answer, the second ask gives v2 another description.
        self.drifting_selector()
        first = self.port.selector({}, '', {}, OPTIONS)
        second = self.port.selector({}, '', {}, OPTIONS)
        self.assertNotEqual(first, second)

    def test_a_changed_input_is_asked_again(self):
        self.drifting_selector()
        held = {}
        renamed = {**OPTIONS, 'templates': {**OPTIONS['templates'], 'name': ['name-item']}}
        replies = []
        for options in (OPTIONS, OPTIONS, renamed):
            select = self.wording(held, remote=True)
            replies.append(select({'s': 1}, 'p', {}, options))
            commit(held, select.keep({'description': replies[-1]['description']}))
        self.assertEqual(replies[0], replies[1])
        self.assertEqual(len(self.asked), 2)
        self.assertNotEqual(replies[0], replies[2])

    def test_each_job_holds_its_own_wording_and_it_ends_with_the_job(self):
        npp, db = self.conv.npp, self.conv.db
        db.execute("INSERT INTO npp_wording VALUES ('job-a','d1','null'), ('job-b','d1','{\"story\":null}'), ('job-a','d2','not json')")
        self.assertEqual(npp.wording('job-a'), {'d1': None})  # an unreadable row holds nothing
        self.assertEqual(npp.wording('job-b'), {'d1': {'story': None}})
        self.drifting_selector()
        self.start_render('$7 each')
        self.case.work()
        jid = self.case.job()['job_id']
        [(digest, held)] = npp.wording(jid).items()
        self.assertEqual(held, {'description': PLAIN})  # only what the Writer rendered from the reply, IDs only
        self.case.say(f'no {jid}')
        self.assertEqual(npp.wording(jid), {})
        self.assertEqual(npp.wording('job-b'), {'d1': {'story': None}})

    def test_a_held_answer_is_reused_without_remote_time(self):
        self.drifting_selector()
        held = {}
        first = self.wording(held, remote=True)
        answer = first({}, 'p', {}, OPTIONS)
        commit(held, first.keep({'description': answer['description']}))
        self.assertEqual(self.wording(held, remote=False)({}, 'p', {}, OPTIONS), answer)
        self.assertEqual(len(self.asked), 1)

    def test_a_version_without_remote_time_keeps_its_default_for_later_versions(self):
        # Case 21: v1 goes out at the segment cap with the default wording; v2 has time but must not change it.
        self.drifting_selector()
        held = {}
        cap = self.wording(held, remote=False)
        self.assertIsNone(cap({}, 'p', {}, OPTIONS))
        commit(held, cap.keep({'description': SHORT}))
        self.assertIsNone(self.wording(held, remote=True)({}, 'p', {}, OPTIONS))
        self.assertEqual(self.asked, [])
        # Another job (no rows), or a changed input in the same job, is still asked.
        self.wording({}, remote=True)({}, 'p', {}, OPTIONS)
        self.wording(held, remote=True)({}, 'p2', {}, OPTIONS)
        self.assertEqual(len(self.asked), 2)

    def test_a_reply_none_of_which_was_shown_holds_the_default(self):
        # Case 36: fabricated prose is never a choice; the Writer gives the default, and that default is what the owner
        # saw, so the next version replays it instead of asking (and maybe getting another description).
        prose = {'description': 'The beans are roasted in copper pans.'}
        self.drifting_selector(reply=prose)
        held = {}
        for expected in (prose, None):
            select = self.wording(held, remote=True)
            self.assertEqual(select({}, 'p', {}, OPTIONS), expected)
            commit(held, select.keep({'description': SHORT}))
        self.assertEqual((len(self.asked), list(held.values())), (1, [None]))

    def test_a_reply_is_held_for_the_fields_the_writer_applied(self):
        # Return item 3, unit level: field by field, what was rendered, and nothing a model said that was not shown.
        for reply, shown, kept in (
                ({'name': {'template_id': 'bogus'}, 'description': PLAIN}, {'name': {'template_id': 'name-item'}, 'description': PLAIN}, {'description': PLAIN}),
                ({'description': 'prose', 'imageAlt': {'template_id': 'alt-photo'}}, {'imageAlt': {'template_id': 'alt-photo'}}, {'imageAlt': {'template_id': 'alt-photo'}}),
                ({'story': None, 'description': 'prose'}, {}, {'story': None}),  # a declined story is an answer
                # a copied description is re-rendered with other phrases of the same template: still the reply's pick
                ({'description': PLAIN}, {'description': {**PLAIN, 'phrase_ids': ['food-open-2', 'food-use-1', 'food-close-1']}}, {'description': PLAIN}),
                # nothing applied: the card shows the default wording, held as "no choice"
                ({'name': {'template_id': 'bogus'}}, {'name': {'template_id': 'name-item'}}, DEFAULT),
                ({'description': PLAIN, 'price': 1}, {'description': PLAIN}, DEFAULT),  # an unknown field voids the whole reply
                ({'description': PLAIN, 'story': 'prose'}, {'description': {'template_id': 'desc-food-default', 'phrase_ids': []}}, DEFAULT),
                ('desc-a', {}, DEFAULT), ({}, {}, DEFAULT), (None, {}, DEFAULT)):
            with self.subTest(reply=reply):
                self.replies(reply)
                select = self.wording({}, remote=True)
                select({}, 'p', {}, OPTIONS)
                self.assertEqual(select.keep(shown), {select.digest: None if kept is DEFAULT else kept})

    def test_a_returned_answer_cannot_change_the_held_one(self):
        held = {}
        self.drifting_selector()
        first = self.wording(held, remote=True)
        answer = first({}, 'p', {}, OPTIONS)
        commit(held, first.keep({'description': answer['description']}))
        for _ in range(2):
            self.wording(held, remote=True)({}, 'p', {}, OPTIONS)['description']['template_id'] = 'tampered'
        self.assertEqual(self.wording(held, remote=True)({}, 'p', {}, OPTIONS), answer)

    def test_no_selector_stays_no_selector(self):
        self.port.selector = None
        self.assertIsNone(self.wording({}, remote=True))


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
