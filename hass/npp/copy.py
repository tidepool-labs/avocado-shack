"""S5: select IDs remotely, bind and render locally from checked assets."""
from dataclasses import dataclass, field
import json
import re

from hass import claims, live_policy
from hass.content_model import CATEGORIES
from hass.cloud_codex import CodexTransport
from hass.interpreter_local import _Failed
from hass.npp import private_numbers as numbers
from hass.product_claims import drop_copy_claims

FIELDS = ('name', 'description', 'imageAlt', 'story')
TOKEN = re.compile(r'\{([^{}]+)\}')
SIZE = re.compile(r'\d+(?:\.\d+)?\s*(?:fl\.?\s*oz|oz|lb|lbs|g|kg|ml|l|ct|count|pack)', re.I)


@dataclass(frozen=True)
class Fact:
    """S4 kept-fact projection; only construct from verified evidence, never extraction output."""
    id: str
    slot: str
    value: str
    url: str
    quote: str
    verdict: str
    source: str = 'official_site'


@dataclass(frozen=True)
class Context:
    kind: str
    category: str
    variant: str
    item: str
    owner_words: str = field(default='', repr=False)
    brand: str = ''
    maker_name: str = ''
    town: str = ''
    size_text: str = ''
    source_read: str = ''
    label_claims: tuple[str, ...] = ()
    facts: tuple[Fact, ...] = ()
    private: frozenset = field(default=frozenset(), repr=False)
    other_descriptions: tuple[str, ...] = ()


@dataclass(frozen=True)
class Copy:
    text: dict
    selections: dict
    basic: bool
    dropped: tuple[str, ...]


def codex_selector(transport=None):
    """Production adapter for Writer.write; transport injection keeps qualification offline."""
    def select(step, prompt, schema, options):
        # This is a developer-owned projection of pins and typed IDs. It contains
        # no free-form data. Keep the unchanged finance-local guard on user text.
        instructions = prompt + '\nOutput schema: ' + json.dumps(schema) + '\nEligible IDs: ' + json.dumps(options)
        body = json.dumps({'model': step['model'], 'messages': [
            {'role': 'system', 'content': instructions},
            {'role': 'user', 'content': 'Choose matching template and phrase IDs. Return JSON only.'},
        ]}).encode()
        try:
            call = transport if transport is not None else CodexTransport(step['effort'])
            status, response = call(None, body, {}, step['timeout_s'])
            if status == 200:
                return json.loads(json.loads(response)['choices'][0]['message']['content'], object_pairs_hook=_unique)
        except (_Failed, OSError, TimeoutError, ValueError, KeyError, IndexError, TypeError):
            pass
        return None
    return select


def _unique(pairs):
    result = dict(pairs)
    if len(result) != len(pairs):
        raise ValueError('duplicate selection key')
    return result


def words(text):
    return re.findall(r'[^\W_]+', text.casefold())


def plain(value, maximum=12):
    return (isinstance(value, str) and value and len(value) <= 120 and len(words(value)) <= maximum
            and re.fullmatch(r"[^\W_][^\W_ '’&\-]*(?:[ '’&\-][^\W_]+)*", value) is not None)


def eligible(row, ctx):
    return (ctx.kind in row['kinds'] and ('categories' not in row or ctx.category in row['categories'])
            and ctx.category not in row.get('categories_except', ())
            and ('variants' not in row or ctx.variant in row['variants']))


def _meets_fact_requirements(row, bound):
    evidenced = {slot for slot in row['slots'].keys() & bound.keys() if bound[slot][1]}
    any_required = row.get('requires_facts_any', ())
    return ((not any_required or bool(evidenced.intersection(any_required)))
            and set(row.get('requires_facts_all', ())) <= evidenced)


class Writer:
    def __init__(self, pinned):
        pins, assets, _ = pinned  # same bytes that passed npp.assets(), never reread by path
        folder = 'hass-listing-copy/'
        self.spec = json.loads(assets[folder + 'copy-templates.json'])
        self.voice = json.loads(assets[folder + 'voice-phrases.json'])
        self.schema = json.loads(assets[folder + 'listing.schema.json'])
        self.prompt = assets[folder + 'SKILL.md'].decode()
        self.step = pins['steps']['copy_select']
        self.templates = {t['id']: t for t in self.spec['templates']}
        self.phrases = {p['id']: p for p in self.voice['phrases']}
        self.limits = json.loads(assets['hass-gallery-style/limits.json'])
        self.fact_rules = json.loads(assets['hass-maker-research/facts.schema.json'])

    def bindings(self, ctx, field_name):
        bindings, facts = {}, {}
        for fact in ctx.facts:
            quote = claims.fold(fact.quote)
            if (not re.fullmatch(r'[a-zA-Z][a-zA-Z0-9_-]{0,39}', fact.id)
                    or fact.verdict != 'supports' or not fact.quote
                    or not claims._said(fact.value, quote)
                    or any(claims._said(marker, quote) for marker in self.fact_rules['negation_hedge_markers'])):
                continue
            if fact.source == 'official_site' and re.fullmatch(r'https?://[^\s]+', fact.url):
                pass  # S4 attests identity, visible quote, and entailment; this boundary has no fetcher
            elif fact.source != 'owner_words' or fact.quote not in ctx.owner_words:
                continue
            facts.setdefault(fact.slot, []).append(fact)
        # Ambiguous fact ids or competing facts cannot license a slot.
        all_ids = [f.id for rows in facts.values() for f in rows]
        kept = {slot: rows[0] for slot, rows in facts.items() if len(rows) == 1 and all_ids.count(rows[0].id) == 1}
        item, _ = drop_copy_claims(ctx.item, ctx.owner_words)
        if plain(item):
            bindings['item'] = (item, None)
        for slot, fact_slot in (('brand', 'name'), ('maker_name', 'name'), ('town', 'town')):
            value = getattr(ctx, slot)
            if not plain(value):
                continue
            if live_policy._owner_said(value, '\n'.join(map(claims.fold, ctx.owner_words.splitlines()))):
                bindings[slot] = (value, None)
            elif field_name != 'description' and (fact := kept.get(fact_slot)) and fact.value == value:
                bindings[slot] = (value, fact.id if field_name == 'story' else None)
        if SIZE.fullmatch(ctx.size_text) and numbers.literal_spans(' '.join(ctx.source_read.split()), [ctx.size_text]):
            bindings['size_text'] = (ctx.size_text, None)
        if field_name == 'story':
            for slot in ('makes', 'nature', 'founded'):
                fact = kept.get(slot)
                valid = fact and (plain(fact.value, 6) if slot == 'makes' else
                                  fact.value in self.fact_rules['nature_enum'] if slot == 'nature' else
                                  re.fullmatch(r'[0-9]{4}', fact.value) and 1800 <= int(fact.value) <= 2026)
                if fact and valid:
                    bindings[slot] = (fact.value, fact.id)
        return bindings

    def _render(self, field_name, choice, ctx, name=''):
        if not isinstance(choice, dict) or not isinstance(choice.get('template_id'), str):
            return None
        row = self.templates.get(choice['template_id'])
        if not row or row['field'] != field_name or not eligible(row, ctx):
            return None
        keys = self.schema['properties'][field_name]['required']
        ids = choice.get('phrase_ids', [])
        fact_ids = choice.get('fact_ids', [])
        if (set(choice) != set(keys) or not isinstance(ids, list) or not isinstance(fact_ids, list)
                or any(not isinstance(i, str) for i in ids + fact_ids)):
            return None
        bound = self.bindings(ctx, field_name)
        if name:
            bound['name'] = (name, None)
        if not row['slots'].keys() <= bound.keys() or not _meets_fact_requirements(row, bound):
            return None
        expected = {bound[slot][1] for slot in row['slots'] if bound[slot][1]}
        if set(fact_ids) != expected or len(fact_ids) != len(expected):
            return None
        banks = [m[1][7:] for m in TOKEN.finditer(row['text']) if m[1].startswith('phrase:')]
        if len(banks) != len(ids):
            return None
        phrase_text = {}
        for bank, phrase_id in zip(banks, ids):
            phrase = self.phrases.get(phrase_id)
            if not phrase or phrase['bank'] != bank or not eligible(phrase, ctx):
                return None
            phrase_text[bank] = phrase['text']
        text, permits, end = '', [], 0
        for m in TOKEN.finditer(row['text']):
            text += row['text'][end:m.start()]
            key, _, transform = m[1].partition('|')
            if key.startswith('phrase:'):
                value = phrase_text[key[7:]]
            else:
                value = bound[key][0]
                if transform == 'cap':
                    value = value[:1].upper() + value[1:]
                elif transform == 'a':
                    value = ('an ' if value[0].lower() in 'aeiou' else 'a ') + value
            if (field_name, key) in {('name', 'size_text'), ('story', 'founded')}:
                permits.append((len(text), len(text) + len(value)))
            text += value
            end = m.end()
        return text + row['text'][end:], tuple(permits)

    def _defaults(self, field_name, ctx):
        defaults = self.spec['defaults']
        if field_name == 'description':
            key = 'flowers' if ctx.category == 'flowers' else ctx.kind
            return ({'template_id': i, 'phrase_ids': []} for i in defaults['description'].get(key, ()))
        if field_name == 'story':
            bound = self.bindings(ctx, field_name)
            return ({'template_id': i,
                     'phrase_ids': [p['id'] for p in self.phrases.values() if p.get('default') and p['bank'] in self.templates[i].get('phrases', {})],
                     'fact_ids': sorted({bound[s][1] for s in self.templates[i]['slots'] if s in bound and bound[s][1]})}
                    for i in defaults['story']['order'])
        return iter(({'template_id': defaults[field_name]},))

    def _options(self, ctx):
        # IDs, never slot values, raw owner words, photo, stock, or selling price.
        result = {}
        for key in FIELDS:
            bound = self.bindings(ctx, key)
            result[key] = [r['id'] for r in self.templates.values() if r['field'] == key and eligible(r, ctx)
                           and (r['slots'].keys() - {'name'}) <= bound.keys() and _meets_fact_requirements(r, bound)]
        return {'kind': ctx.kind, 'category': ctx.category, 'templates': result,
                'phrase_ids': [p['id'] for p in self.phrases.values() if eligible(p, ctx)],
                'fact_ids': {key: ref for key, (_value, ref) in self.bindings(ctx, 'story').items() if ref}}

    def _usable(self, key, rendered, ctx):
        from hass.npp.validate import field_problem
        return rendered is not None and not field_problem(self, key, rendered[0], rendered[1], ctx)

    def _alt_name(self, choices, ctx):
        # Alt copy has no digit permit. Re-render the same identity without the label-size slot.
        name_choice = choices['name'].copy()
        name_choice['template_id'] = name_choice['template_id'].removesuffix('-size')
        rendered = self._render('name', name_choice, ctx)
        return rendered[0] if rendered else ''

    def write(self, ctx, select=None, *, proposed=None):
        """Selector adapter takes (pinned step, prompt, schema, public IDs); timeout is enforced by adapter.

        Optional `proposed` is an existing public projection to check (e.g. replay/edit).
        Returns None when a required field has no compliant rendering. Nothing here sends or persists.
        """
        if ctx.kind not in {'food', 'drink', 'fresh', 'non-food'} or ctx.category not in CATEGORIES:
            return None
        try:
            choices = select(dict(self.step), self.prompt, self.schema, self._options(ctx)) if select else None
        except (TimeoutError, OSError, ValueError):
            choices = None
        if not isinstance(choices, dict) or choices.keys() - set(FIELDS):
            choices = {}
        if proposed is not None and (not isinstance(proposed, dict) or proposed.keys() - set(FIELDS)):
            choices, proposed = {}, None
        basic, text, used = False, {}, {}
        for key in FIELDS:
            choice = choices.get(key)
            if key == 'story' and key in choices and choice is None and (not proposed or key not in proposed):
                continue
            alt = self._alt_name(used, ctx) if key == 'imageAlt' else ''
            rendered = self._render(key, choice, ctx, alt)
            conforms = proposed is None or (rendered is not None and proposed.get(key) == rendered[0])
            if conforms and rendered is not None and self._usable(key, rendered, ctx):
                text[key], used[key] = rendered[0], choice
                continue
            if conforms and key == 'description' and rendered and isinstance(choice, dict):
                from hass.npp.validate import field_problem
                if field_problem(self, key, *rendered, ctx) == 'copied-description':
                    ids = choice['phrase_ids']
                    for pos, old in enumerate(ids):
                        for new, phrase in self.phrases.items():
                            if new == old or phrase['bank'] != self.phrases[old]['bank']:
                                continue
                            swap = {**choice, 'phrase_ids': [*ids[:pos], new, *ids[pos + 1:]]}
                            attempt = self._render(key, swap, ctx)
                            if attempt is not None and self._usable(key, attempt, ctx):
                                text[key], used[key] = attempt[0], swap
                                break
                        if key in used:
                            break
                    if key in used:
                        basic = True
                        continue
            for default in self._defaults(key, ctx):
                rendered = self._render(key, default, ctx, alt)
                if rendered is not None and self._usable(key, rendered, ctx):
                    text[key], used[key] = rendered[0], default
                    break
            if key != 'story' and key not in used:
                return None
            basic |= key != 'story' or key in used or choice is not None or proposed is not None and key in proposed
        _, dropped = drop_copy_claims(ctx.item, ctx.owner_words, (*ctx.label_claims, *ctx.owner_words.splitlines()))
        return Copy(text, used, basic, dropped)

    def conform(self, text, choices, ctx):
        """S7 independently rebuilds every final field from pinned assets and trusted bindings."""
        if set(text) != set(choices) or not set(FIELDS[:3]) <= text.keys() <= set(FIELDS):
            return False
        for key, value in text.items():
            alt = self._alt_name(choices, ctx) if key == 'imageAlt' else ''
            rendered = self._render(key, choices[key], ctx, alt)
            if rendered is None or rendered[0] != value or not self._usable(key, rendered, ctx):
                return False
        return True
