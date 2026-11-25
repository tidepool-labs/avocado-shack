// NPP replay observer (offline harness only; run_npp.py swaps it in for hass/screenshot.cjs when it replays case 26).
// Runs hass/screenshot.cjs UNCHANGED in this same process and, at the moment that script screenshots the product
// card, writes {alt, imageSha256, pngSha256} to target.observeTo (an absolute path):
//   alt         the card's first <img> alt attribute as the DOM holds it
//   imageSha256 SHA-256 of the body of the image resource the browser loaded for that <img> (currentSrc), read from
//               the network response of this page; only when the browser reports the image complete and decoded
//   pngSha256   SHA-256 of the card PNG that screenshot returned (the bytes written to OUT)
// No file is written when any of these is unavailable (data: URL, cache hit, undecoded image): run_npp.py reads that
// as "no observation" and reports not-run, never pass. The renderer itself (and its pinned sha) is not modified.
'use strict';
const path = require('node:path');
const fs = require('node:fs');
const {createHash} = require('node:crypto');
const {createRequire} = require('node:module');
const script = path.resolve(__dirname, '..', '..', 'screenshot.cjs');
const {chromium} = createRequire(script)(process.env.PLAYWRIGHT_MODULE || 'playwright');
const sink = JSON.parse(process.env.TARGET || '{}').observeTo;
if (typeof sink !== 'string' || !path.isAbsolute(sink)) {
  console.error('observeTo must be an absolute path');
  process.exit(1);
}
const sha = bytes => createHash('sha256').update(bytes).digest('hex');
const launch = chromium.launch.bind(chromium);
chromium.launch = async (...args) => {
  const browser = await launch(...args), newPage = browser.newPage.bind(browser);
  browser.newPage = async (...pageArgs) => {
    const page = await newPage(...pageArgs), images = new Map();
    page.on('response', r => { if (r.request().resourceType() === 'image') images.set(r.url(), r); });
    const locator = Object.getPrototypeOf(page.locator('html')), shoot = locator.screenshot;
    locator.screenshot = async function (...shotArgs) {
      const seen = await this.locator('img').first().evaluate(e => ({alt: e.getAttribute('alt'), src: e.currentSrc,
        decoded: e.complete && e.naturalWidth > 0})).catch(() => null);
      const response = seen && seen.decoded ? images.get(seen.src) : null;
      const body = response ? await response.body().catch(() => null) : null;
      const png = await shoot.apply(this, shotArgs);
      if (seen && typeof seen.alt === 'string' && body) {
        fs.writeFileSync(sink, JSON.stringify({alt: seen.alt, imageSha256: sha(body), pngSha256: sha(png)}), {mode: 0o600});
      }
      return png;
    };
    return page;
  };
  return browser;
};
require(script);
