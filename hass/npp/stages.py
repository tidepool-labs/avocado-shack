"""Production NPP composition. Workers build evidence; only Jobs may retain a draft."""
from datetime import date, datetime
from decimal import Decimal
import hashlib
from pathlib import Path
import re
import time

from hass import claims, editor, live_policy, maker_site, media, photo_polish
from hass.content_model import load_content
from hass.npp import copy, edits, identify, missing, picture, private_numbers, research, research_hermes, validate
from hass.npp.job import Card, Plan, owner_item
from hass.npp.reply import Stages, compose
from hass.ops import photos


class OfficialPage:
    """Only the independently admitted page and its robots policy may be requested.

    Use the unchanged bounded, pinned HTTPS reader. A redirect is not another
    admission, and an About link is not authority to fetch a second page.
    """
    def __init__(self, url):
        self.url = url

    def search(self, *_):
        return ()

    def fetch(self, url, seconds):
        if url != self.url:
            raise maker_site.PageError('address')

        def get(target, headers, timeout, **options):
            if headers['Accept'] == 'text/html' and target != self.url:
                raise maker_site.PageError('address')
            response = maker_site._http_get(target, headers, timeout, **options)
            if response[0] in maker_site.REDIRECTS:
                raise maker_site.PageError('address')
            return response

        clock = time.monotonic
        budget = maker_site._Budget(clock, min(seconds, maker_site.DEADLINE))
        try:
            status, kind, body = maker_site._read(url, 'text/html', get, True, time.sleep, clock, {}, robots=True, budget=budget)
        finally:
            budget.release()
        if status != 200 or not body or 'text/html' not in kind.lower() or len(body) >= maker_site.MAX_BYTES:
            raise maker_site.PageError('unreadable')
        return research.parse_page(url, date.today().isoformat(), body.decode('utf-8', 'replace'))


def _finance(work, unit):
    slot = work.request['slots'].get('intake', {})
    amount, span = slot.get('price'), slot.get('price_span')
    return private_numbers.Finance('', f'{amount} {unit}' if amount and span else None,
                                   tuple(span) if span else None,
                                   frozenset(Decimal(n) for n in slot.get('private', ())))


def _widest_claims(found):
    """One printed claim read at several widths ('Immune', 'Immune support') is one claim: keep each phrase that is not
    a contiguous run of words inside another read claim, in first-seen order (exact repeats once)."""
    words = [tuple(re.findall(r'\w+', claim.casefold())) for claim in found]
    kept, seen = [], set()
    for claim, mine in zip(found, words):
        inside = any(len(other) > len(mine) and any(other[i:i + len(mine)] == mine for i in range(len(other) - len(mine) + 1))
                     for other in words)
        if mine and not inside and mine not in seen:
            seen.add(mine)
            kept.append(claim)
    return kept


def _site_words(phrase, texts):
    """Only explicit, unambiguous owner wording; never infer a town or URL from S2/S4."""
    lines = '\n'.join(map(claims.fold, texts))
    towns = set()
    urls = set()
    # Finance parsing normalizes comma-delimited clauses to semicolons. Require
    # the town clause to immediately follow the exact owner-named maker.
    maker_clause = re.compile(r'\s*made by\s+' + re.escape(phrase or '') + r'\s*', re.I)
    for text in texts:
        follows_maker = False
        for clause in re.split(r'[;,\n]', text):
            explicit = re.fullmatch(r'\s*(?:based in|town:)\s+([\w .’\'-]+)\s*', clause, re.I)
            attached = (re.fullmatch(r"\s*([\w ’'-]+?)(?:\.\s+.+|\s+(https://\S+)(?:\s.*)?)\s*", clause, re.I)
                        if follows_maker else None)
            if found := explicit or attached:
                value = found[1].strip(' .')
                if (research._identity_field(value) and live_policy._owner_said(value, lines)
                        and (explicit or all(word[0].isupper() for word in value.split()))):
                    towns.add(value)
            standalone = re.fullmatch(r'\s*(?:(?:website|site):?\s+)?(https://\S+)\s*', clause, re.I)
            url = standalone[1] if standalone else attached[2] if attached else None
            # The anchored forms above bind the literal URL. The prose matcher
            # splits on ':' and '.' and cannot recognize an intact URL.
            if url and research._url(url):
                urls.add(url)
            follows_maker = bool(phrase and maker_clause.fullmatch(clause))
    return (next(iter(towns)) if len(towns) == 1 and phrase else '', next(iter(urls)) if len(urls) == 1 else '')


class ProductionStages(Stages):
    def __init__(self, conversation, pinned):
        super().__init__(pinned, start=self.start_plan, render=self.render_listing, mapper=edits.codex_mapper(step=pinned[0]['steps']['edit_map']))
        self.c, self.pinned = conversation, pinned
        labels = conversation.labels
        self.identifier = identify.Identifier(pinned, labels if getattr(labels, 'api', None) in ('ollama', 'openai')
                                              else getattr(labels, 'fallback', None))
        self.missing = missing.MissingInfo(pinned)
        self.writer = copy.Writer(pinned)
        self.selector = copy.codex_selector()

    def catalog(self):
        return load_content(editor._load(str(self.c.sdir))[2] / 'hass' / 'content')

    def clover(self):
        desk = getattr(self.c, 'till', None)
        return desk._snapshot()[0] if desk is not None else None

    def _remaining(self, work):
        return (work.deadline - self.c._now()).total_seconds()

    def _photo(self, sha):
        web = media.web_copy(self.c.settings['mediaRoot'], sha)
        data = Path(web['path']).read_bytes()
        if hashlib.sha256(data).hexdigest() != web['web_sha256']:
            raise ValueError('unbound web copy')
        return data

    def _research(self, work, maker, town, owner_url, reading):
        if not (maker.research_allowed and town):
            return ()
        url = research._url(owner_url) if owner_url else ''
        budget = self._remaining(work) - self.pinned[0]['steps']['copy_select']['timeout_s'] - 10
        if url is None or budget <= 0:
            return ()
        result = research_hermes.run(self.pinned, web=OfficialPage(url) if url else research_hermes.Web(), owner_maker=maker.phrase,
                                     owner_town=town, owner_url=url, label_brand=reading.get('brand_on_label') or '',
                                     label_confidence=reading.get('confidence', {}).get('brand', 0), budget=budget)
        return result.story_facts

    def start_plan(self, work, *, local=False):
        texts = work.request['texts']
        content = self.catalog()
        shas = work.request['attachments']
        reading = {} if local else self.identifier.read(self._photo(s) for s in shas).evidence or {}
        slot = work.request['slots'].get('intake', {})
        amount = slot.get('price') if slot.get('price_span') else None
        named_item = next((item for text in reversed(texts) if (item := owner_item(text))), None)
        decision = self.missing.decide(reading, price=missing.OwnerPrice(amount, slot.get('sold_by')),
                                       owner_item=named_item, owner_texts=texts, products=content.products, makers=content.makers,
                                       clover=self.clover(), ask_counts=work.ask_counts, answered=work.answered,
                                       duplicate_confirmed=work.answers.get('duplicate') is True,
                                       near_maker_confirmed=work.answers.get('near_maker'))
        if not decision.ready:
            return Plan(questions=decision.questions, identified=decision.identified)
        maker = decision.maker
        town, url = _site_words(maker.phrase, texts)
        facts = self._research(work, maker, town, url, reading) if not local else ()
        private = _finance(work, '').private
        label = reading.get('brand_on_label') if maker.state == 'contradictory' else None
        if label and (validate._contact(label) or private_numbers.problem(label, private)):
            label = None
        label_words = [word for word in reading.get('label_words', []) if not validate._contact(word)
                       and not private_numbers.problem(word, private)]
        # Printed claims reach only the Writer's drop list and the owner's card note, never public text.
        label_claims = _widest_claims([claim for claim in reading.get('visible_claims') or [] if isinstance(claim, str)
                                       and not validate._contact(claim) and not private_numbers.problem(claim, private)])
        # The durable listing is a narrow projection, not a caption, full model read, or research transcript.
        return Plan(listing={
            'name': decision.item, 'category': decision.category or 'general', 'kind': reading.get('kind') or 'non-food',
            'sellingPrice': decision.price.amount, 'priceUnit': 'lb' if decision.price.unit == 'pound' else 'each',
            'maker': maker.phrase if maker.state in ('known', 'new') else None,
            'contradictoryLabel': label,
            'makerKey': maker.key, 'newMaker': maker.state == 'new', 'town': town, 'url': url,
            'facts': [{**{k: fact[k] for k in ('id', 'slot', 'value', 'url', 'quote')}, 'verdict': 'supports'} for fact in facts],
            'photo': shas[0], 'personOrScreen': reading.get('has_person_or_screen'),
            'size': reading.get('size_text'), 'labelWords': label_words, 'labelClaims': label_claims,
        }, identified=True)

    def _picture(self, work, listing, private, *, local):
        sha = work.request['attachments'][0]
        settings = self.c.settings
        source = picture.read_text(self._photo(sha))
        source_text = ' '.join((source or '').split())
        words, person = listing['labelWords'], listing['personOrScreen']
        if sha != listing['photo']:
            current = {} if local else self.identifier.read(self._photo(s) for s in work.request['attachments']).evidence or {}
            words, person = current.get('label_words', ()), current.get('has_person_or_screen')
        # A typed net size may equal private inventory. Bind that exact printed
        # phrase independently to this source photo, not to the caption's count.
        elif (size := listing.get('size')) and copy.SIZE.fullmatch(size) and private_numbers.literal_spans(source_text, [size]):
            words = [*words, size]
        if not local and settings.get('houseRender') is True and photo_polish.enabled(settings):
            # Only the runner launches polish. Leave time for S5 and S8 before the cap.
            end = time.monotonic() + max(0, min(self._remaining(work) - 26, self.pinned[0]['steps']['picture']['hard_s']))
            while time.monotonic() < end and photo_polish.decision(settings['mediaRoot'], sha) is None:
                time.sleep(min(0.2, max(0, end - time.monotonic())))
        frozen = picture.choose(settings, sha, has_person_or_screen=person, label_words=words,
                                source_label_words=[word for word in words if private_numbers.literal_spans(source_text, [word])],
                                private_numbers_clear=lambda text, allowed: not private_numbers.picture_problem(text, source, allowed, private),
                                ocr=picture.read_text)
        return frozen, sha, source, words

    def render_listing(self, work, listing, *, local=False):
        unit = 'per lb' if listing['priceUnit'] == 'lb' else 'each'
        finance = _finance(work, unit)
        if finance.selling_price != f"{listing['sellingPrice']} {unit}" or not finance.price_span:
            return None
        frozen, sha, source, label_words = self._picture(work, listing, finance.private, local=local)
        if isinstance(frozen, photos.Retake):
            return Plan(retake=frozen.reason)
        content = self.catalog()
        texts = work.request['texts']
        owner = '\n'.join(texts)
        value = listing.get('maker')
        resolved = missing._maker(value, {}, content.makers)
        key = resolved.key if (resolved.state == 'known' or resolved.state == 'near'
                               and resolved.key == listing.get('makerKey') and work.answers.get('near_maker') is True) else None
        name = content.makers[key]['name'] if key else value or ''
        town, url = _site_words(value, texts)
        fresh = bool(value and not key and listing.get('newMaker') and value == listing.get('maker') and town)
        facts = tuple(copy.Fact(**fact) for fact in listing['facts']) if fresh and town == listing['town'] and url == listing['url'] else ()
        brand = name if live_policy._owner_said(name, '\n'.join(map(claims.fold, texts))) else ''
        context = copy.Context(listing['kind'], listing['category'], frozen.variant, listing['name'], owner,
                               brand=brand, maker_name=name if fresh else '', town=town if fresh else '',
                               size_text=(listing['size'] or '') if sha == listing['photo'] else '', source_read=source or '',
                               facts=facts, private=finance.private, label_claims=tuple(listing.get('labelClaims') or ()),
                               other_descriptions=tuple(p['description'] for p in content.active_products() if p.get('description')))
        selector = None if local or self._remaining(work) < 26 else self.selector
        draft, written, origin = self._candidate(context, listing, finance, content.makers, key, fresh, url, sha, selector)
        if draft is None or written is None or not frozen.matches_draft(draft):
            return None
        shot = self.c._capture(draft, candidate=True)
        if shot.get('ok') is not True or not isinstance(shot.get('picture'), bytes):
            return None
        with Path(shot['png']).open('rb') as file:
            png = file.read(media.MAX_BYTES + 1)
        if len(png) > media.MAX_BYTES or not png.startswith(media.KINDS['png']):
            return None
        image = shot['picture']
        # SiteEditor passes one clock reading to product.add and the candidate's
        # created_at. Do not read the clock again after capture (it may be a new shop day).
        added_on_now = datetime.fromisoformat(draft['created_at'])
        verdict = validate.listing(self.writer, context, written, draft, finance=finance, origin=origin,
                                   makers=content.makers, live_site=self.c.settings.get('liveSite'), photo_sha=sha,
                                   frozen_sha=frozen.image_sha256, rendered_sha=hashlib.sha256(image).hexdigest(),
                                   picture_read=picture.read_text(image), label_words=label_words,
                                   card_evidence=shot['cardEvidence'], card_png=png, added_on_now=added_on_now)
        if not verdict.ok:
            return None
        parts = {}
        if frozen.note:
            parts['picture_own_photo' if frozen.variant == 'raw' else 'picture_house'] = {}
        if written.basic:
            parts['basic_wording'] = {}
        if written.dropped:
            parts['claim_left_off'] = {'claim': ', '.join(written.dropped)}
        if fresh and 'story' not in written.text:
            parts['story_not_found'] = {}
        label = None
        if not key and not brand:
            label = listing.get('contradictoryLabel')
            parts['maker_left_off_label' if label else 'maker_left_off'] = {'brand': label} if label else {}
        note = compose(self.replies, parts)
        if label and label not in note:
            # Case 31b explicitly explains the omission. Keep the one-bracket
            # cap and omit the optional picture annotation if both won't fit.
            note = compose(self.replies, {'maker_left_off_label': {'brand': label}}) or note
        return Card(draft, png, frozen.variant, frozen.image_path, frozen.image_sha256,
                    note, candidate=True)

    def _candidate(self, context, listing, finance, makers, key, fresh, url, sha, selector):
        written = self.writer.write(context, selector)
        if written is None:
            return None, None, None
        text = written.text
        operations = []
        place = makers[key].get('place') if key else None
        if fresh and (text.get('story') or url):
            key = re.sub(r'[^a-z0-9]+', '-', claims.fold(context.maker_name)).strip('-')
            place = context.town
            operations.append({'op': 'maker.add', 'args': {'key': key, 'name': context.maker_name, 'place': place,
                               **({'story': text['story']} if text.get('story') else {}), **({'url': url} if url else {})}})
        args = {**{k: text[k] for k in ('name', 'description', 'imageAlt')}, 'category': context.category,
                'brand': context.brand or claims.PLACEHOLDER, 'photo': sha, 'sellingPrice': finance.selling_price}
        if key:
            args['producerKey'] = key
        if supplier := listing.get('supplier'):
            args['supplier'] = supplier
        origin = f'From {supplier}' if supplier else f'Based in {place}' if place else validate.ORIGIN_UNKNOWN
        operations.append({'op': 'product.add', 'args': args})
        result = self.c.editor.candidate(operations)
        return result.get('draft') if result.get('result') == 'ok' else None, written, origin

    def persist(self, draft):
        return self.c.editor.persist_candidate(draft)

    def cap(self, work, listing):
        if listing is not None:
            return self.render_listing(work, listing, local=True)
        if work.parent is not None:
            return None  # no remote mapping at the cap
        plan = self.start_plan(work, local=True)
        return (plan, self.render_listing(work, plan.listing, local=True)) if plan.listing is not None else plan


def build(conversation, pinned):
    if conversation is None or conversation.previewer is None or not all(
        callable(getattr(conversation.editor, name, None)) for name in ('candidate', 'render_candidate', 'persist_candidate')
    ):
        return None
    return ProductionStages(conversation, pinned)
