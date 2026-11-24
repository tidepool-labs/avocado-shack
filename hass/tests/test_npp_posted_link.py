"""Offline S13 link coverage at the writer → generated shelf → shop.js boundary."""

import json
import re
import shutil
import subprocess
import unittest
from html.parser import HTMLParser

from hass import editor, npp
from hass.content_model import SITE_DIR
from hass.npp.reply import posted
from hass.tests.test_set_photo import FIXTURES, PhotoRepo

SITE = 'storefront-mockup/'
NAME = 'Fixture Moon Quince'
GONE = 'That item is not in our catalog right now. Here is everything else.'

# Execute the scripts, not a copy of their item logic. The DOM stand-in just
# reflects inserted markup and records which article receives scroll/focus.
SHOP_RUNNER = r"""
const fs = require('node:fs');
const path = require('node:path');
const vm = require('node:vm');
const [built, sources, href, trigger, initialFocus] = process.argv.slice(2);
const location = new URL(href);
const elements = new Map();
const element = () => ({value: '', textContent: '', options: [], hidden: false,
  append(option) { this.options.push(option); }, addEventListener() {},
  focus() { document.activeElement = this; }});
for (const selector of ['#catalog-grid', '#brand-filter', '#product-search', '#market',
                        '#catalog-count', '#catalog-sentinel', '#more-products',
                        '#clear-filters', '#dialog', '.close', '[data-policy]']) {
  elements.set(selector, element());
}
const all = {...element(), dataset: {filter: 'all'}, classList: {toggle() {}},
  setAttribute() {}};
elements.set('[data-filter="all"]', all);
elements.set('[data-filter].selected', all);
const grid = elements.get('#catalog-grid');
const search = elements.get('#product-search');
let scrolled = null;
const articles = [];
Object.defineProperty(grid, 'innerHTML', {set() { articles.length = 0; }});
grid.insertAdjacentHTML = (position, html) => {
  if (position === 'beforebegin') {
    const id = html.match(/\bid="([^"]+)"/)?.[1];
    const cls = html.match(/\bclass="([^"]+)"/)?.[1];
    elements.set(id ? '#' + id : '.' + cls, {...element(), hidden: /\bhidden\b/.test(html)});
  } else if (position === 'beforeend') {
    for (const [, id] of html.matchAll(/<article\s[^>]*\bdata-product-id="([^"]+)"/g)) {
      articles.push({dataset: {productId: id}, setAttribute() {},
        scrollIntoView() { scrolled = id; }, focus() { document.activeElement = this; }});
    }
  }
};
const document = {
  readyState: trigger === 'complete' ? 'complete' : 'loading',
  body: element(), documentElement: element(), createElement: element, addEventListener() {},
  getElementById(id) { return elements.get('#' + id) ?? null; },
  querySelector(selector) { return elements.get(selector) ?? null; },
  querySelectorAll(selector) {
    if (selector === '[data-filter]') return [all];
    if (selector === '#catalog-grid article') return articles;
    return [];
  },
};
document.activeElement = document.body;
const timers = new Map(), frames = [];
let nextTimer = 0, onLoad;
const context = vm.createContext({document, location, URLSearchParams,
  history: {replaceState(_state, _unused, url) { location.href = new URL(url, location).href; }},
  addEventListener(type, fn) { if (type === 'load') onLoad = fn; },
  setTimeout(fn) { timers.set(++nextTimer, fn); return nextTimer; },
  clearTimeout(id) { timers.delete(id); },
  requestAnimationFrame(fn) { return frames.push(fn); },
  window: {addEventListener() {}}});
for (const [dir, file] of [[built, 'catalog-products.js'], [built, 'producers.js'],
                           [sources, 'script.js'], [sources, 'shop.js']]) {
  vm.runInContext(fs.readFileSync(path.join(dir, file), 'utf8'), context, {filename: file});
}
if (trigger === 'load') onLoad(); // The focus change can happen even after load queued its frame.
if (initialFocus === 'search') search.focus();
if (initialFocus === 'root') document.documentElement.focus();
if (trigger === 'load') frames.shift()();
if (trigger.startsWith('fallback')) {
  const [[id, fn]] = timers;
  timers.delete(id);
  fn();
  if (trigger === 'fallback-then-load') {
    scrolled = null; // Simulate the browser's subsequent anchor jump.
    onLoad();
    frames.shift()();
  }
}
const active = document.activeElement;
const focused = active === search ? 'search' : active.dataset?.productId ?? null;
const status = document.getElementById('catalog-item-status');
console.log(JSON.stringify({cards: articles.map(a => a.dataset.productId), focused, scrolled,
  status: status && !status.hidden ? status.textContent : null}));
"""


class PageWiring(HTMLParser):
    """Capture the actual generated elements and executable script tags."""

    def __init__(self, page):
        super().__init__(convert_charrefs=True)
        self.elements = []
        self.scripts = []
        self.market_depth = 0
        self.feed(page)

    def handle_starttag(self, tag, attrs):
        attrs = dict(attrs)
        if tag == 'section' and (self.market_depth or attrs.get('id') == 'market'):
            self.market_depth += 1
        self.elements.append((tag, attrs, bool(self.market_depth)))
        if tag == 'script' and 'src' in attrs:
            self.scripts.append((attrs, len(self.elements)))

    def handle_endtag(self, tag):
        if tag == 'section' and self.market_depth:
            self.market_depth -= 1


class PostedLinkTests(unittest.TestCase):
    def _check_wiring(self, repo):
        page = PageWiring(repo.read(SITE + 'index.html').decode())
        required = {
            'market': 'section', 'catalog-grid': 'div', 'brand-filter': 'select',
            'product-search': 'input', 'catalog-count': 'p', 'catalog-sentinel': 'div',
            'more-products': 'button', 'clear-filters': 'button', 'dialog': 'dialog',
            'dialog-content': 'div',
        }
        for element_id, tag in required.items():
            matches = [(i, t, inside) for i, (t, a, inside) in enumerate(page.elements)
                       if a.get('id') == element_id]
            self.assertEqual(len(matches), 1, element_id)
            self.assertEqual(matches[0][1], tag, element_id)
            if element_id not in ('dialog', 'dialog-content'):
                self.assertTrue(matches[0][2], element_id + ' must be in market')
        filters = [(i, t, a) for i, (t, a, inside) in enumerate(page.elements)
                   if inside and 'data-filter' in a]
        all_buttons = [i for i, t, a in filters if t == 'button' and a.get('data-filter') == 'all'
                       and 'selected' in a.get('class', '').split()]
        close = [i for i, (_, a, _) in enumerate(page.elements)
                 if 'close' in a.get('class', '').split()]
        policy = [i for i, (_, a, _) in enumerate(page.elements) if 'data-policy' in a]
        self.assertEqual(len(all_buttons), 1)
        self.assertTrue(close)
        self.assertTrue(policy)
        expected = ['catalog-products.js', 'producers.js', 'script.js', 'shop.js']
        sources = [a['src'] for a, _ in page.scripts]
        for source in expected:
            self.assertEqual(sources.count(source), 1, source)
        positions = [sources.index(source) for source in expected]
        self.assertEqual(positions, sorted(positions))
        for index in positions:
            attrs, position = page.scripts[index]
            self.assertFalse({'async', 'defer', 'nomodule'} & attrs.keys(), attrs)
            self.assertIn(attrs.get('type', '').lower(), ('', 'text/javascript', 'application/javascript'))
            self.assertGreater(position, max([*all_buttons, close[0], policy[0],
                                              *(i for i, (_, a, _) in enumerate(page.elements)
                                                if a.get('id') in required)]))

    def _add_listing(self):
        repo = PhotoRepo()
        self.addCleanup(repo.cleanup)
        # Same fields as stages._candidate for a photo and price with no maker.
        draft = repo.run(('product.add', {
            'name': NAME, 'description': 'A quince with yellow skin.',
            'brand': 'Producer not identified', 'category': 'fruit',
            'photo': repo.store((FIXTURES / 'pixel.jpg').read_bytes()),
            'imageAlt': 'A quince on a plain surface', 'sellingPrice': '7.13',
        }))
        change_id = draft['change_id']
        # Use the applied change record, as Conversation.npp_posted does, not
        # a hard-coded id or an id taken from the catalog being checked.
        change = editor.show(change_id, state=str(repo.state))['change']
        [key] = [r['key'] for r in change['records'] if r['collection'] == 'products']
        _, _, replies = npp.assets()
        line = posted(replies, key)
        self.assertTrue(line.startswith('Posted: '))
        url = line.split()[1]
        self.assertEqual(url, f'https://theavocadoman.com/?item={key}#market')
        return repo, change_id, key, url

    def _node22(self):
        node = shutil.which('node')
        if not node:
            self.skipTest('NOT-RUN: Node 22 is not installed')
        result = subprocess.run([node, '--version'], capture_output=True, text=True, timeout=10)
        self.assertEqual(result.returncode, 0, result.stderr)
        if not result.stdout.startswith('v22.'):
            self.skipTest('NOT-RUN: Node 22 is required')
        return node

    def _open(self, node, repo, url, trigger='complete', initial_focus='body'):
        self._check_wiring(repo)
        script = repo.state / 'posted-link.cjs'
        script.write_text(SHOP_RUNNER, encoding='utf-8')
        result = subprocess.run([node, str(script), str(repo.wt / SITE), str(SITE_DIR), url,
                                 trigger, initial_focus],
                                capture_output=True, text=True, timeout=10)
        self.assertEqual(result.returncode, 0, result.stderr)
        return json.loads(result.stdout)

    def test_c1_id_in_site(self):
        # An add could succeed while the generated market data omits its id.
        repo, _, key, _ = self._add_listing()
        self._check_wiring(repo)
        self.assertEqual([(p['name'], p['category']) for p in repo.catalog() if p['id'] == key],
                         [(NAME, 'fruit')])
        page = repo.read(SITE + 'index.html').decode()
        market = re.search(r'<section\b[^>]*\bid="market"[^>]*>(.*?)</section>', page, re.S)
        if market is None:
            self.fail('generated homepage has no market section')
        self.assertIn('id="catalog-grid"', market[1])
        scripts = re.findall(r'<script\b[^>]*\bsrc="([^"]+)"', page)
        self.assertIn('catalog-products.js', scripts)
        self.assertIn('shop.js', scripts)
        self.assertLess(scripts.index('catalog-products.js'), scripts.index('shop.js'))

    def test_c2_item_param(self):
        # A fruit is off the default packaged shelf. The linked load must
        # render and focus the exact card, not merely show a catalog grid.
        node = self._node22()
        repo, _, key, url = self._add_listing()
        self.assertNotIn(key, self._open(node, repo, url.split('?')[0] + '#market')['cards'])
        page = self._open(node, repo, url)
        self.assertIn(key, page['cards'])
        self.assertEqual((page['focused'], page['scrolled'], page['status']), (key, key, None))

        # The first queued callback must not treat "not shown yet" as permission
        # to take focus or scroll after the visitor tabs to the search input.
        for trigger in ('load', 'fallback'):
            for initial_focus, expected in [('search', ('search', None)),
                                            ('body', (key, key)), ('root', (key, key))]:
                with self.subTest(trigger=trigger, initial_focus=initial_focus):
                    page = self._open(node, repo, url, trigger, initial_focus)
                    self.assertIn(key, page['cards'])
                    self.assertEqual((page['focused'], page['scrolled']), expected)

        # If fallback focused the card and it still owns focus, load may re-center it.
        page = self._open(node, repo, url, 'fallback-then-load')
        self.assertEqual((page['focused'], page['scrolled']), (key, key))

    def test_c3_hidden_not_shown(self):
        # A reverted row still exists privately; leaking it to the shelf or
        # silently ignoring the old link would both break the visitor flow.
        repo, change_id, key, url = self._add_listing()
        self.assertIn(key, [p['id'] for p in repo.catalog()])
        repo.run(('history.revert', {'changeId': change_id}))
        self.assertEqual(repo.product(key)['status'], 'hidden')
        self.assertNotIn(key, [p['id'] for p in repo.catalog()])
        page = self._open(self._node22(), repo, url)
        self.assertNotIn(key, page['cards'])
        self.assertTrue(page['cards'], 'other listings should remain visible')
        self.assertEqual((page['focused'], page['scrolled'], page['status']), (None, None, GONE))
