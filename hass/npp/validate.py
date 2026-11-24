"""S7 checks on reviewed copy, exact draft records, OCR, and the rendered card."""
from dataclasses import dataclass
from hashlib import sha256
import re

from hass import claims, live_policy, publish_live
from hass.content_model import CATEGORIES, ID_RE, TEXT_LIMITS, iso_day, shop_today, valid_supplier
from hass.house_style import OWNER_IMAGE_RE
from hass.npp import private_numbers as numbers
from hass.npp.copy import words
from hass.ops.photos import MAX_ALT, _alt_problem

ORIGIN_UNKNOWN = 'Ask us about the source in store.'


def _spans(text, size):
    tokens = words(text)
    return {tuple(tokens[i:i + size]) for i in range(len(tokens) - size + 1)}


def _contact(text):
    normalized = claims.unhidden(text)
    return bool('/home/' in normalized.casefold() or live_policy.EMAIL.search(normalized)
                or any(rx.search(normalized) for rx in publish_live.PATTERNS.values()))


def field_problem(writer, key, text, permits, ctx):
    """Fixed verdicts suitable for a private receipt; no rejected text or amounts."""
    field = {'story': 'maker_story', 'imageAlt': 'image_alt'}.get(key, key)
    hard = writer.limits['limits'].get(field, {}).get('hard_max_chars')
    if hard is None:
        hard = TEXT_LIMITS['product'].get(key, MAX_ALT)
    if not text or len(text) > hard:
        return 'length'
    if key == 'description':
        rule = writer.limits['limits']['description']
        if not rule['sentences_min'] <= len(re.findall(r'[.!?](?=\s|$)', text)) <= rule['sentences_max']:
            return 'sentences'
    if _contact(text):
        return 'contact'
    if problem := numbers.problem(text, ctx.private, permitted=permits):
        return problem
    banned = writer.voice['banned_words']
    if key == 'description' and (ctx.kind == 'non-food' or ctx.category == 'flowers'):
        # The product identity is not a serving suggestion (e.g. a French Toast Candle).
        item = writer.bindings(ctx, key).get('item', ('', None))[0]
        prose = re.sub(r'(?<!\w)' + re.escape(item) + r'(?!\w)', '', text, flags=re.I) if item else text
        if any(numbers.literal_spans(prose, [term]) for term in writer.voice['non_food_banned_words']):
            return 'non-food-serving'
    if any(numbers.literal_spans(text, [term]) for term in banned):
        return 'hype'
    if 'health/awards/endorsements' in live_policy._protected(text)[1]:
        return 'unsupported-claim'
    # Only the exact typed slot value can excuse a shared four-word owner span.
    spans = _spans(text, 4) - {span for value, _ in writer.bindings(ctx, key).values() for span in _spans(value, 4)}
    if any(spans & _spans(turn, 4) for turn in ctx.owner_words.splitlines()):
        return 'owner-chatter'
    if key == 'description':
        ours = _spans(text, writer.spec['no_copying']['span_words'])
        if any(ours & _spans(other, 8) for other in ctx.other_descriptions):
            return 'copied-description'
    return None


def _flat(text):
    return ' '.join(text.split())


def _fixed_ui(maker, count, organic):
    """Closed table for storefront-mockup/shop.js badges(), makerStory() and card()."""
    return {
        ':scope > .card-link': ('Link to this',),
        '.food-badges > span': ('New', 'Organic') if organic else ('New',),
        '.maker-story > summary': ('Meet the maker',) if maker else (),
        '.maker-story-content > a': (f'Visit {maker} ↗',) if maker else (),
        '.maker-story-content > button.text-link[data-from]': (
            (f'See all {count} from {maker}',) if maker and type(count) is int and count >= 2 else ()),
        '.availability': (),
    }


def captured_dom(evidence, png, product_id):
    """Refuse fragments/index from a different capture, even for the same product."""
    if (not isinstance(evidence, dict) or not isinstance(png, bytes)
            or evidence.get('pngSha256') != sha256(png).hexdigest()
            or not product_id or evidence.get('productId') != product_id):
        return None, None, None
    return evidence.get('fragments'), evidence.get('priceIndex'), evidence.get('makerCount')


def dom_problem(nodes, price_index, price, name, approved=(), private=(), allowed=None, required=(), *,
                maker=None, maker_count=None, organic=False):
    """`nodes` are visible DOM text fragments in order, with the exact price element identified.

    Keep numbers licensed in copy only in exact, already checked fields; no numeric-value
    allowlist. Pass only the numeric-bearing fields (name and/or story) as `approved`.
    When `allowed` is given, every other public fragment must equal one of those approved
    strings (whitespace-folded) and every `required` string must be rendered, so a swapped
    description or any extra claim fails even if it has no contact or number in it.
    """
    if not isinstance(nodes, (tuple, list)):
        return 'card-text'
    texts, roles = [], []
    for node in nodes:
        if isinstance(node, str):
            node = {'text': node, 'role': None}
        if (not isinstance(node, dict) or set(node) != {'text', 'role'} or not isinstance(node['text'], str)
                or node['role'] is not None and not isinstance(node['role'], str)):
            return 'card-text'
        texts.append(node['text'])
        roles.append(node['role'])
    if not any(text == name and role is None for text, role in zip(texts, roles)):
        return 'card-text'
    if (type(price_index) is not int or not 0 <= price_index < len(texts)
            or roles[price_index] is not None or texts[price_index] != '$' + price):
        return 'card-price'
    remaining = list(approved)
    ui = _fixed_ui(maker, maker_count, organic)
    scan, shown = [], []
    for index, (text, role) in enumerate(zip(texts, roles)):
        if _contact(text):
            return 'card-contact'
        if index == price_index:
            scan.append(' ; ')
            continue
        if role is not None:
            if text not in ui.get(role, ()):
                return 'card-copy'
            # Only the renderer's checked count is exempt from the numeric scan.
            scan.append(f'from {maker}' if role == '.maker-story-content > button.text-link[data-from]' else text)
            continue
        shown.append(_flat(text))
        if text in remaining:
            remaining.remove(text)
            scan.append(' ; ')
            continue
        if numbers.problem(text, private):
            return 'card-number'
        scan.append(text)
    # Also inspect adjacent fragments for OCR-like/spoken splits of numbers and money.
    if numbers.problem(' '.join(scan), private):
        return 'card-number'
    if allowed is not None:
        if any(text and text not in allowed for text in shown):
            return 'card-copy'
        if any(_flat(text) not in shown for text in required):
            return 'card-copy'
    return None


def _panel_clean(value):
    """A maker-panel string may be shown on the card only if it carries no protected claim (a plain farm-noun name is fine)."""
    if not isinstance(value, str):
        return False
    skeleton = claims.skeleton(value)
    names = (claims._pattern(skeleton),) if skeleton and live_policy._plain_name(skeleton) else ()
    return not live_policy._protected(value, 'makers', names)[1]


@dataclass(frozen=True)
class Verdict:
    problems: tuple[str, ...]
    warnings: tuple[str, ...]

    @property
    def ok(self):
        return not self.problems


def listing(writer, ctx, copy, draft, *, finance, origin, makers, live_site, photo_sha,
            frozen_sha, rendered_sha, picture_read, card_nodes=None, price_index=None, label_words=(),
            card_evidence=None, card_png=None, added_on_now=None):
    """Check a fully assembled S7/S8 listing; this function cannot publish or send.

    `makers` is the existing catalog, `photo_sha` is the source photo and `frozen_sha`
    and `rendered_sha` are independent evidence from S6 and S8. G calls with the actual
    prepared draft and DOM text; never use the expected text in place of a capture.
    `added_on_now`, when supplied, is the clock reading used by the editor's product.add.
    """
    problems, warnings = [], []
    if not finance.private <= ctx.private or not writer.conform(copy.text, copy.selections, ctx):
        problems.append('template-conformance')
    records = draft.get('records', ())
    products = [r for r in records if r.get('collection') == 'products']
    new_makers = [r for r in records if r.get('collection') == 'makers']
    if (len(products) != 1 or not isinstance(products[0].get('after'), dict) or len(new_makers) > 1
            or len(records) != len(products) + len(new_makers) or products[0].get('before') is not None
            or [op.get('op') for op in draft.get('ops', ())] != (['maker.add'] if new_makers else []) + ['product.add']):
        return Verdict(('listing-records',), ())
    product = products[0]['after']
    key = products[0].get('key')
    if not isinstance(key, str) or not ID_RE.fullmatch(key) or key != product.get('id'):
        return Verdict(('listing-records',), ())
    text = copy.text
    if (ctx.category not in CATEGORIES or product.get('category') != ctx.category
            or any(not text.get(key) or text[key] != product.get(key) for key in ('name', 'description', 'imageAlt'))):
        problems.append('listing-fields')
    known = makers or {}
    maker = known.get(product.get('producerKey'))
    if new_makers:
        row = new_makers[0]
        maker = row.get('after')
        if (not isinstance(maker, dict) or row.get('key') != product.get('producerKey') or row.get('before') is not None
                or (maker.get('story') or None) != text.get('story') or not (maker.get('story') or maker.get('url'))
                or maker.get('name') != ctx.maker_name or live_policy._town(maker.get('place')) != ctx.town):
            problems.append('maker-panel')
    elif text.get('story'):
        problems.append('maker-panel')
    maker = maker if isinstance(maker, dict) else {}
    supplier = product.get('supplier')
    wanted = f'From {supplier}' if supplier else f"Based in {maker['place']}" if maker.get('place') else ORIGIN_UNKNOWN
    if (origin != wanted or supplier and (not valid_supplier(supplier) or not live_policy._owner_said(supplier, '\n'.join(map(claims.fold, ctx.owner_words.splitlines()))))
            or not maker and product.get('producerKey')):
        problems.append('origin')
    brands = writer.bindings(ctx, 'name')
    for key in ('brand', 'displayBrand'):
        shown = product.get(key)
        if not shown and key == 'displayBrand':
            continue
        if shown not in (claims.PLACEHOLDER, 'From the market', brands.get('brand', (None,))[0]) or not shown:
            problems.append('brand')
    price = finance.selling_price
    if not price or not finance.price_span or product.get('sellingPrice') != price:
        problems.append('price-provenance')
    private = ctx.private | finance.private
    # Only the editor-stamped shop day can extend the existing copy/price exceptions.
    stamped_day = shop_today(added_on_now) if added_on_now is not None else None
    for key, value in {**product, 'origin': origin}.items():
        if key in {'id', 'image', 'sellingPrice', 'labelSource', 'ownerSource'}:
            continue
        if not isinstance(value, str):
            continue
        stamped = key == 'addedOn' and stamped_day is not None and iso_day(value) == stamped_day
        if _contact(value) or (not stamped and numbers.problem(value, private) and key not in {'name', 'description', 'imageAlt'}):
            problems.append('public-text')
    for key, value in maker.items():
        if key == 'story' and new_makers:
            continue  # conforming story, including a typed founded year
        if isinstance(value, str) and (_contact(value) or numbers.problem(value, private, digits_allowed=not new_makers and key == 'story')):
            problems.append('public-text')
    image, alt = product.get('image'), product.get('imageAlt')
    if (not isinstance(image, str) or not OWNER_IMAGE_RE.fullmatch(image)
            or not re.fullmatch(r'[0-9a-f]{64}', frozen_sha or '') or not re.fullmatch(r'[0-9a-f]{64}', photo_sha or '')
            or draft.get('assets', {}).get(image) != 'sha256:' + frozen_sha or frozen_sha != rendered_sha
            or not isinstance(alt, str) or '(illustration)' in alt.casefold() or _alt_problem(alt, photo_sha)):
        problems.append('picture-binding')
    if problem := numbers.picture_problem(picture_read, ctx.source_read, label_words, private):
        problems.append(problem)
    elif _contact(picture_read):
        problems.append('picture-contact')
    # The card may show only the validated copy, the checked brand/origin lines and the maker panel. Every maker-panel
    # fragment (name, place, story) is bound: a new maker's name/place are tied to ctx above and its story is text['story'];
    # an existing maker's catalog name, place and story are not part of this copy, so each is shown only when it carries
    # no protected claim (health/awards/endorsements, superlatives, ...).
    panel = [maker.get(key) for key in ('name', 'place') if _panel_clean(maker.get(key))]
    if not new_makers and _panel_clean(maker.get('story')):
        panel.append(maker.get('story'))
    # The computed origin line is derived from the maker's place ("Based in <place>"), so it is bound the same way: it is
    # shown only when its source is clean (an owner-said supplier, no place, or a place with no protected claim).
    origin_ok = bool(supplier) or not maker.get('place') or (_panel_clean(maker.get('place')) and _panel_clean(origin))
    shown_ok = {_flat(v) for v in (text.get('name'), text.get('description'), text.get('story'), product.get('displayBrand'), product.get('brand'),
                                   *([origin] if origin_ok else []), *panel) if isinstance(v, str) and v.strip()}
    claims_passed = not claims.unstated(draft, ctx.owner_words, makers)
    maker_count = None
    if card_evidence is not None or card_png is not None:
        card_nodes, price_index, maker_count = captured_dom(card_evidence, card_png, product.get('id'))
    if price and (problem := dom_problem(card_nodes, price_index, price, text.get('name'),
                                        tuple(text[k] for k in ('name', 'story') if text.get(k)), private,
                                        allowed=shown_ok,
                                        maker=maker['name'] if _panel_clean(maker.get('name')) else None,
                                        maker_count=maker_count,
                                        organic=claims_passed and bool(re.search(r'\borganic\b', product.get('name') or '', re.I)),
                                        required=tuple(text[k] for k in ('name', 'description', 'story') if text.get(k)))):
        problems.append(problem)
    if not claims_passed:
        problems.append('existing-claims')
    if live_site:
        if live_policy.unsaid(draft, ctx.owner_words):
            problems.append('existing-identity')
        if live_policy.check(draft):
            problems.append('existing-live-policy')
    measured = {**text, 'brand': product.get('displayBrand') or product.get('brand') or '', 'origin': origin,
                'image_alt': alt or '', 'maker_story': text.get('story', ''), 'maker_name': maker.get('name', ''),
                'maker_place': maker.get('place', ''), 'maker_url': maker.get('url', '')}
    for key, stats in writer.limits['fields'].items():
        value = measured.get(key, '')
        if isinstance(value, str) and (len(value) > stats['chars']['p90'] or len(value.split()) > stats['words']['p90']):
            warnings.append(key + '-p90')
    return Verdict(tuple(dict.fromkeys(problems)), tuple(warnings))
