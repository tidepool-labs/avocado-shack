#!/usr/bin/env python3
"""Synthetic OFF rehearsal: Hass writer → loopback Market card → coded undo.

Run with the same PLAYWRIGHT_MODULE and CHROMIUM_PATH as the site's tests.
No shop root, site URL, owner data, recipient or credentials can be supplied.
The approval/transport fixture stands in for chat delivery and preview pixels;
the writer, Market HTML/JavaScript, HTTP responses and browser are real.
"""
from __future__ import annotations

from contextlib import contextmanager
from http.client import HTTPConnection
from importlib.util import module_from_spec, spec_from_file_location
from pathlib import Path
from shutil import copyfile
from urllib.parse import urlsplit
import json
import os
import re
import subprocess
import sys
import threading
import unittest

ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from hass.content_model import REPO_ROOT, SITE_DIR
from hass.preview import Previewer
from hass.tests import test_hidden_listing_served_projection as projection
from hass.tests import test_npp_undo_journey as journey
from hass.tests.test_editor import git

SERVER = 'community-server.py'
SHELL_FILES = ('style.css', 'script.js', 'shop.js', 'community.js', 'producers.js')
STATIC = {'/index.html', '/catalog-products.js', *('/' + f for f in SHELL_FILES)}
IMAGE = re.compile(r'/assets/products/[A-Za-z0-9_-]+\.(?:jpg|png|webp|jpeg)')

# Only the browser's requested, visible card counts. A catalog row alone could
# be correct while a broken or stale page displays something entirely different.
BROWSER = r'''
const {createHash} = require('node:crypto');
const {chromium} = require(process.env.PLAYWRIGHT_MODULE);
const [origin, id, before, permit] = process.argv.slice(2);
(async () => {
  const browser = await chromium.launch({executablePath: process.env.CHROMIUM_PATH || undefined,
    args:['--disable-background-networking']});
  try {
    const context = await browser.newContext({serviceWorkers:'block', viewport:{width:430,height:850}});
    try {
      const page = await context.newPage();
      const errors = [], responses = new Map();
      page.on('pageerror', () => errors.push(1));
      page.on('response', response => {
        if (response.request().resourceType() === 'image') responses.set(response.url(), response);
      });
      await context.route('**/*', route => {
        const req = route.request();
        const u = new URL(req.url());
        return u.origin === origin && req.method() === 'GET' ? route.continue() : route.abort();
      });
      page.setDefaultTimeout(5000);
      const path = `/index.html?item=${encodeURIComponent(id)}#market`;
      if (!(await page.goto(origin + path)).ok()) throw Error('page');
      if (!(await page.locator('#catalog-grid article').count())) throw Error('empty catalog');
      const card = page.locator(`#catalog-grid article[data-product-id=${JSON.stringify(id)}]`);
      let output = null;
      if (before === 'present') {
        if (await card.count() !== 1 || !await card.isVisible()) throw Error('card');
        const image = card.locator('img');
        const src = await image.getAttribute('src');
        if (src !== permit) throw Error('image path');
        await image.scrollIntoViewIfNeeded();
        if (!await image.evaluate(img => img.decode().then(() => img.naturalWidth > 0))) throw Error('image');
        const reply = responses.get(origin + '/' + src);
        if (!reply || !reply.ok()) throw Error('image response');
        output = {name:await card.locator('h3').innerText(),
          description:await card.locator('.food-description').innerText(),
          sellingPrice:await card.locator('.product-price').innerText(), imageAlt:await image.getAttribute('alt'),
          photo_sha256:createHash('sha256').update(await reply.body()).digest('hex')};
      } else if (await card.count() || !await page.locator('#catalog-item-status').isVisible()) {
        throw Error('item still on its deep link');
      }
      if (errors.length) throw Error('script');
      console.log(JSON.stringify(output));
    } finally { await context.close(); }
  } finally { await browser.close(); }
})().catch(() => { console.error('browser observation refused'); process.exitCode = 1; });
'''


class Refused(ValueError):
    pass


def require(ok, reason):
    if not ok:
        raise Refused(reason)


class Target:
    """Read via the already-bound literal address; no DNS, redirects or proxy."""

    def __init__(self, server, root):
        self.address, self.root = server.server_address, root
        self.base = 'http://%s:%s' % self.address

    def bind(self, writer, baseline):
        require(self.address[0] == '127.0.0.1' and self.address[1] > 0, 'target-not-loopback')
        require(self.root == writer.resolve(), 'wrong-writer-root')
        require(self.get(projection.CATALOG_URL) == baseline, 'baseline-catalog-mismatch')
        require(projection.page_loads_catalog(self.get(projection.MARKET_URL) or b'',
                                              self.base + projection.MARKET_URL), 'market-script-not-served')

    def get(self, path):
        require(self.address[0] == '127.0.0.1' and allowed(path), 'target-or-route-refused')
        conn = HTTPConnection(*self.address, timeout=4)
        try:
            conn.request('GET', path)
            with conn.getresponse() as response:
                if response.status == 404:
                    return None
                require(response.status == 200, 'http-observation-refused')
                body = response.read(8 * 1024 * 1024 + 1)
                require(len(body) <= 8 * 1024 * 1024, 'response-too-large')
                return body
        finally:
            conn.close()


def allowed(path):
    return path in STATIC or IMAGE.fullmatch(path) is not None


@contextmanager
def serve(root, scratch):
    """Actual community-server static handler; no POST, community DB or state routes."""
    root, scratch = root.resolve(), scratch.resolve()
    require(root.is_relative_to(scratch) and root != scratch, 'non-disposable-root')
    source = root / SERVER
    require(source.is_file() and not source.is_symlink(), 'sandbox-server-missing')
    spec = spec_from_file_location('off_market', source)
    if spec is None or spec.loader is None:
        raise Refused('sandbox-server-loader-missing')
    module = module_from_spec(spec)
    # Loading the sandbox server must not write storefront-mockup/__pycache__ into the sandbox worktree
    # (it would show as untracked there); some other test module may have flipped this flag, so pin it here.
    previous, sys.dont_write_bytecode = sys.dont_write_bytecode, True
    try:
        spec.loader.exec_module(module)
    finally:
        sys.dont_write_bytecode = previous
    vars(module).update(CONFIG=scratch / 'unused-community.json', DB=scratch / 'unused-community.sqlite3')

    class MarketOnly(module.Handler):
        def do_GET(self):
            path = urlsplit(self.path).path
            file = root / path.lstrip('/')
            if not allowed(path) or not file.is_file() or file.resolve() != file:
                self.send_error(404)
                return
            super().do_GET()

        do_HEAD = do_POST = lambda self: self.send_error(405)

    with module.ThreadingHTTPServer(('127.0.0.1', 0), MarketOnly) as server:
        thread = threading.Thread(target=server.serve_forever, kwargs={'poll_interval': 0.05}, daemon=True)
        thread.start()
        try:
            yield Target(server, module.ROOT)
        finally:
            server.shutdown()
            thread.join()


def observe(target, pid, approved):
    served = projection.served_card(target, pid)
    require(not projection.mismatches(approved, served), 'served-card-mismatch')
    return served


def browser(target, program, pid, image=None):
    require(target.address[0] == '127.0.0.1', 'target-not-loopback')
    runtime = Previewer(ROOT).env
    require('PLAYWRIGHT_MODULE' in runtime, 'playwright-runtime-missing')
    env = {key: runtime[key] for key in ('PATH', 'PLAYWRIGHT_MODULE', 'CHROMIUM_PATH',
                                           'PLAYWRIGHT_BROWSERS_PATH') if key in runtime}
    env.update(HOME=str(program.parent), TMPDIR=str(program.parent))
    result = subprocess.run(['node', str(program), target.base, pid,
                             'present' if image else 'absent', image or ''],
                            env=env, capture_output=True, text=True, timeout=40, check=False)
    require(result.returncode == 0, 'browser-observation-refused')
    return json.loads(result.stdout)


INPUT_TREES = ('hass', 'storefront-mockup')


def tracked_inputs_only(root):
    """Refuse unless the trees the inherited sandbox copies are exactly Git's tracked files.

    The PhotoRepo/WriterRepo harness copies all of hass/ (skipping only
    __pycache__), listed storefront files and every assets/products entry. Any
    untracked or ignored file in those trees (for example a local .env or a
    private photo), or a tracked file changed from HEAD, stops the run before
    anything is copied. Only interpreter caches outside storefront assets (CI's
    syntax step compiles storefront-mockup), which the harness does not copy,
    are allowed.
    """
    try:
        result = subprocess.run(
            ['git', '-C', str(root), 'status', '--porcelain=v1', '-z', '--ignored=traditional',
             '--untracked-files=all', '--', *INPUT_TREES],
            capture_output=True, timeout=60, check=False)
    except (OSError, subprocess.SubprocessError):
        raise Refused('input-tree-unverified') from None
    require(result.returncode == 0, 'input-tree-unverified')
    for entry in filter(None, result.stdout.split(b'\0')):
        state, path = entry[:2], entry[3:].decode('utf-8', 'replace')
        parts = path.split('/')
        require(state == b'!!' and '__pycache__' in parts[:-1] and parts[:2] != ['storefront-mockup', 'assets'],
                'untracked-or-changed-input')


def fixture_pass():
    """One fixture with positive and counterfactual observations; return digest-only evidence."""
    require(REPO_ROOT.resolve() == ROOT and SITE_DIR.resolve() == ROOT / 'storefront-mockup',
            'input-tree-unverified')
    tracked_inputs_only(ROOT)
    facts = {}

    class Walk(journey.NppUndoJourneyTests):
        def say(self, text, *, photos=0):
            if text.startswith('yes ') and 'preview' not in facts:
                draft = self.engine.show(self.change)['draft']
                add, = (op['args'] for op in draft['ops'] if op['op'] == 'product.add')
                (self.image, photo), = draft['assets'].items()
                self.preview = {**{key: add[key] for key in projection.SHOWN},
                                'photo_sha256': photo.removeprefix('sha256:')}
                self.target.bind(self.writer, self.before)
                self.assertIsNone(browser(self.target, self.program, self.pid))
                (outbox, digest, state), = self.conv.db.execute(
                    'SELECT outbox_id,card_png_sha,state FROM npp_versions WHERE change_id=?', (self.change,))
                _, png, sent_digest = self.transport.cards[outbox]
                self.assertEqual((state, projection.sha(png), sent_digest), ('delivered', digest, digest))
                facts['preview'] = {'delivered_fixture_png_sha256': digest,
                                    'approved_photo_sha256': self.preview['photo_sha256'],
                                    'approved_public_fields_sha256': projection.sha(
                                        json.dumps(self.preview, sort_keys=True).encode())}
            return super().say(text, photos=photos)

        def walk(self):
            self.writer = (self.repo.wt / 'storefront-mockup').resolve()
            scratch = self.repo.state.parent.resolve()
            for name in SHELL_FILES:
                if not (self.writer / name).exists():
                    copyfile(ROOT / 'storefront-mockup' / name, self.writer / name)
            git(self.repo.wt, 'add', '--', 'storefront-mockup')
            if self.repo.status():
                git(self.repo.wt, 'commit', '-q', '-s', '-m', 'synthetic Market shell')
            self.program = scratch / 'observe.cjs'
            self.program.write_text(BROWSER, encoding='utf-8')
            self.before = (self.writer / 'catalog-products.js').read_bytes()

            # A public address is rejected before any socket/client can be opened.
            public = object.__new__(Target)
            public.address = ('0.0.0.0', 80)
            with self.assertRaisesRegex(Refused, '^target-not-loopback$'):
                public.bind(self.writer, self.before)
            with serve(self.repo.main / 'storefront-mockup', scratch) as wrong:
                # This independent root initially serves the SAME catalog bytes.
                self.assertEqual(wrong.get(projection.CATALOG_URL), self.before)
                with self.assertRaisesRegex(Refused, '^wrong-writer-root$'):
                    wrong.bind(self.writer, self.before)

            with serve(self.writer, scratch) as self.target:
                facts['market_html_sha256'] = projection.sha(self.target.get(projection.MARKET_URL))
                facts['server_sha256'] = projection.sha((self.writer / SERVER).read_bytes())
                facts['initial_catalog_sha256'] = projection.sha(self.before)
                self.publish()
                record, photo, catalog, _ = observe(self.target, self.pid, self.preview)
                self.assertIsNotNone(record)
                assert record is not None
                self.assertEqual((record['image'], photo), (self.image, self.preview['photo_sha256']))
                want = {**self.preview, 'sellingPrice': '$' + self.preview['sellingPrice']}
                actual = browser(self.target, self.program, self.pid, self.image)
                self.assertEqual(actual, want)
                facts['browser_public_fields_sha256'] = projection.sha(json.dumps(
                    {**actual, 'sellingPrice': actual['sellingPrice'].removeprefix('$')}, sort_keys=True).encode())
                facts['served_catalog_sha256'] = projection.sha(catalog)
                facts['readback_photo_sha256'] = photo

                # The same bound endpoint with a stale catalog must fail even
                # when it still serves the committed photo. Restore in finally.
                catalog_file = self.writer / 'catalog-products.js'
                try:
                    catalog_file.write_bytes(self.before)
                    self.assertEqual(self.target.get('/' + self.image), (self.writer / self.image).read_bytes())
                    with self.assertRaisesRegex(Refused, '^served-card-mismatch$'):
                        observe(self.target, self.pid, self.preview)
                finally:
                    catalog_file.write_bytes(catalog)
                self.assertEqual(self.repo.status(), '')
                self.draft_hide()
                self.assertEqual(self.target.get(projection.CATALOG_URL), catalog)
                self.confirm_hide()
                record, _, restored, problems = projection.served_card(self.target, self.pid)
                self.assertEqual((record, restored, problems), (None, self.before, []))
                self.assertIsNone(browser(self.target, self.program, self.pid))
                facts['restored_catalog_sha256'] = projection.sha(restored)
                facts['publish_commits'] = facts['takedown_commits'] = 1

    result = unittest.TestResult()
    Walk('walk').run(result)
    if not result.wasSuccessful():
        # The fixture owns only public/synthetic bytes. The CLI still emits
        # no error traces, paths, owner identifiers or confirmation codes.
        raise Refused('offline-fixture-did-not-pass') from AssertionError(result.failures + result.errors)
    return {**facts, 'checks': ['public-target-refused', 'wrong-root-refused', 'absent-before-yes',
                               'browser-and-photo-match', 'stale-catalog-refused',
                               'one-coded-takedown', 'browser-absent-and-catalog-restored'],
            'scope': 'synthetic OFF only; no live listing, Clover or private replay'}


def main():
    if sys.argv[1:] or not Previewer(ROOT).env.get('PLAYWRIGHT_MODULE'):
        print('HOLD: run without arguments and with the pinned local Playwright test runtime', file=sys.stderr)
        return 2
    try:
        result = fixture_pass()
    except (Refused, OSError, subprocess.SubprocessError):
        print('HOLD: offline fixture did not pass', file=sys.stderr)
        return 1
    print(json.dumps({'result': 'PASS', **result}, sort_keys=True))
    return 0


if __name__ == '__main__':
    sys.exit(main())
