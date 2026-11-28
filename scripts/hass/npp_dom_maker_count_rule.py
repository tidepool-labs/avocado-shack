#!/usr/bin/env python3
"""Check the storefront's maker-count button against the S7 DOM rule offline."""

import argparse
from html.parser import HTMLParser
import json
import os
from pathlib import Path
import subprocess
import sys
from tempfile import TemporaryDirectory

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))
if __name__ == '__main__':
    sys.dont_write_bytecode = True

from hass.npp import validate

SITE = ROOT / 'storefront-mockup'
COUNTS = [0, 1, 2, 3, True, '2', None, 2.0]
ROLE = '.maker-story-content > button.text-link[data-from]'
PRODUCT_ID = 'fixture-honey'
MAKER_KEY = 'fixture-farm'
MAKER = 'Fixture Farm'
NAME = 'Honey'
PRICE = '4.00 each'
TOOL = 'npp_dom_maker_count_rule'

# The stub only supplies inputs and records insertion. It does not decide which
# cards or buttons to draw. Define the DOM objects inside each fresh context.
RUNNER = r"""
const fs = require('node:fs');
const vm = require('node:vm');
const [scriptPath, shopPath, fixtures] = process.argv.slice(2);
const script = fs.readFileSync(scriptPath, 'utf8');
const shop = fs.readFileSync(shopPath, 'utf8');
const rows = [];
for (let count = 0; count <= 3; count++) {
  const context = vm.createContext({URLSearchParams}, {
    codeGeneration: {strings: false, wasm: false}
  });
  const run = (source, filename) => vm.runInContext(source, context, {filename, timeout: 1000});
  run(`
    const {target, producers, peers, decoys} = ${fixtures};
    const catalog = [ ...decoys, ...[target, ...peers].slice(0, ${count}) ];
    const element = () => ({value: '', options: [],
      append(option) { this.options.push(option); }, addEventListener() {}});
    const elements = new Map();
    for (const selector of ['#catalog-grid', '#brand-filter', '#product-search', '#market',
                            '#catalog-count', '#catalog-sentinel', '#more-products',
                            '#clear-filters', '#dialog', '.close', '[data-policy]']) {
      elements.set(selector, element());
    }
    const all = {dataset: {filter: 'all'}, classList: {toggle() {}}};
    elements.set('[data-filter].selected', all);
    const grid = elements.get('#catalog-grid');
    grid.insertAdjacentHTML = (position, html) => {
      if (position === 'beforebegin') {
        const id = html.match(/\\bid="([^"]+)"/)?.[1];
        const cls = html.match(/\\bclass="([^"]+)"/)?.[1];
        elements.set(id ? '#' + id : '.' + cls, element());
      } else if (position === 'beforeend') {
        grid.innerHTML += html;
      }
    };
    const document = {
      createElement: element, addEventListener() {}, getElementById() { return null; },
      querySelector: selector => elements.get(selector) ?? null,
      querySelectorAll: selector => selector === '[data-filter]' ? [all] : [],
    };
    const location = {search: '', hash: ''};
    const window = {addEventListener() {}};
  `, 'fixture');
  run(script, 'script.js');
  run(shop, 'shop.js');
  // There cannot be a Honey article in the grid when its maker has no rows.
  rows.push(run(count === 0 ? 'card(target)' : 'grid.innerHTML', 'capture'));
}
process.stdout.write(JSON.stringify(rows));
"""


def storefront_rows():
    target = dict(id=PRODUCT_ID, name=NAME, producerKey=MAKER_KEY, sellingPrice=PRICE,
                  category='pantry', brand=MAKER, description='A jar of honey.')
    fixtures = dict(
        target=target,
        producers={MAKER_KEY: dict(name=MAKER, story='A small farm.', place='Fixture Valley')},
        peers=[dict(target, id=f'fixture-peer-{i}', name='Jam') for i in range(2)],
        decoys=[dict(target, id=f'fixture-decoy-{i}', name='Tea', producerKey='fixture-other',
                     brand='Other Farm') for i in range(2)],
    )
    with TemporaryDirectory() as tmp:
        runner = Path(tmp) / 'maker_count.cjs'
        runner.write_text(RUNNER, encoding='utf-8')
        result = subprocess.run(
            ['node', str(runner), str(SITE / 'script.js'), str(SITE / 'shop.js'),
             json.dumps(fixtures)],
            cwd=tmp, env={'PATH': os.environ.get('PATH', os.defpath)},
            stdin=subprocess.DEVNULL, capture_output=True, text=True, encoding='utf-8',
            check=True, timeout=15,
        )
    rows = json.loads(result.stdout)
    if result.stderr or not isinstance(rows, list) or len(rows) != 4 or not all(
        isinstance(html, str) and html.strip() for html in rows
    ):
        raise ValueError('invalid storefront runner output')
    return rows


class Element:
    def __init__(self, tag, attrs, parent):
        self.tag = tag
        self.attrs = attrs
        self.parent = parent
        self.text = []

    def has_class(self, name):
        return name in (self.attrs.get('class') or '').split()

    def content(self):
        # Match screenshot.cjs's whitespace folding for DOM text.
        return ' '.join(''.join(self.text).split())

    def matches_button_role(self):
        return (self.parent is not None and self.parent.has_class('maker-story-content')
                and self.has_class('text-link') and 'data-from' in self.attrs)


class TargetArticle(HTMLParser):
    """Collect only the target's anchors and buttons, not its neighbors' text."""

    VOID = frozenset('area base br col embed hr img input link meta param source track wbr'.split())

    def __init__(self, html):
        super().__init__()
        self.matches = 0
        self.stack = []
        self.names = []
        self.prices = []
        self.buttons = []
        self.feed(html)
        self.close()
        if (self.matches != 1 or self.stack or len(self.names) != 1 or len(self.prices) != 1
                or not self.names[0].content() or not self.prices[0].content()):
            raise ValueError('missing or ambiguous card anchors')

    def handle_starttag(self, tag, attrs):
        attrs = dict(attrs)
        if not self.stack:
            if tag == 'article' and attrs.get('data-product-id') == PRODUCT_ID:
                self.matches += 1
                self.stack.append(Element(tag, attrs, None))
            return
        element = Element(tag, attrs, self.stack[-1])
        if tag == 'h3':
            self.names.append(element)
        if element.has_class('product-price'):
            self.prices.append(element)
        if tag == 'button' and (any(
            p.has_class('maker-story') or p.has_class('maker-story-content') for p in self.stack
        ) or 'data-from' in attrs):
            self.buttons.append(element)
        if tag not in self.VOID:
            self.stack.append(element)

    def handle_startendtag(self, tag, attrs):
        self.handle_starttag(tag, attrs)
        if tag not in self.VOID:
            self.handle_endtag(tag)

    def handle_endtag(self, tag):
        for index in range(len(self.stack) - 1, -1, -1):
            if self.stack[index].tag == tag:
                del self.stack[index:]
                break

    def handle_data(self, data):
        for element in self.stack:
            element.text.append(data)


def button_text(count):
    return f'See all {count} from {MAKER}'


def dom_verdict(nodes, count, maker: str | None = MAKER):
    problem = validate.dom_problem(nodes, 1, PRICE, NAME, maker=maker, maker_count=count)
    if problem is None:
        return 'ok'
    if problem not in ('card-text', 'card-price', 'card-contact', 'card-copy', 'card-number'):
        raise ValueError('unexpected S7 verdict')
    return problem


def fragments(name=NAME, price='$' + PRICE, buttons=()):
    return [{'text': name, 'role': None}, {'text': price, 'role': None},
            *({'text': text, 'role': ROLE} for text in buttons)]


def findings():
    for count, html in enumerate(storefront_rows()):
        article = TargetArticle(html)
        buttons = article.buttons
        selected = [button.content() for button in buttons if button.matches_button_role()]
        nodes = fragments(article.names[0].content(), article.prices[0].content(), selected)
        verdict = dom_verdict(nodes, count if count else None)
        print(f'storefront {count} buttons={len(buttons)} verdict={verdict}')
        if count < 2:
            expected = not buttons
        else:
            expected = (len(buttons) == 1 and selected == [button_text(count)]
                        and buttons[0].attrs.get('type') == 'button'
                        and buttons[0].attrs.get('data-from') == MAKER_KEY)
        if not expected or verdict != 'ok':
            yield f'storefront-drift {count}'

    for index, count in enumerate(COUNTS):
        verdict = dom_verdict(fragments(buttons=[button_text(count)]), count)
        print(f'count {index} verdict={verdict}')
        licensed = type(count) is int and count >= 2
        if verdict == 'ok' and not licensed:
            yield f'count-allowed {index}'
        elif verdict != 'ok' and licensed:
            yield f'count-refused {index}'

    neutral = dom_verdict(fragments(), None)
    no_maker = dom_verdict(fragments(buttons=[button_text(2)]), 2, maker=None)
    if (neutral, no_maker) != ('ok', 'card-copy'):
        yield 'control-broken'


def main(argv=None):
    argparse.ArgumentParser(description=__doc__).parse_args(argv)
    failed = False
    try:
        for reason in findings():
            print(f'FAIL {reason}')
            failed = True
    except Exception:
        # Runner/validator errors can contain paths or rendered text. Never echo them.
        print('FAIL check-error')
        failed = True
    print(f'{"FAIL" if failed else "PASS"} {TOOL}')
    return int(failed)


if __name__ == '__main__':
    sys.exit(main())
